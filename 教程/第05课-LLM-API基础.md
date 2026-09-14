# 第 5 课:LLM API 基础

> 所属模块:模块二「Agent 核心原理」(第 5–10 课)
> 预计时长:1.5–2 小时(实验需要一把可用的 LLM API Key)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第 4 课:Python 异步编程基础](./第04课-Python异步编程基础.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理   ← 你在这里(第 5 课)
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶
```

从本课起进入 Agent 的心脏。第 1 课说过,Agent 的四要素里"大脑"就是 LLM——但框架把它包了起来,你只是填了几个环境变量。**本课剥掉这层壳**:先看清 LLM API 的本体(一次 HTTP 请求),再用一个 20 行的裸脚本绕开框架直连它,最后回到项目精读 `llm_service.py`——全项目最短的模块文件,却决定了四个 Agent 共用的大脑。你还将学到一项贯穿全课程的基本功:**如何在框架源码里亲自验证结论,而不是轻信任何文档(包括本讲义)**。

## 学习目标

完成本课后,你应该能够:

1. 手写一个 OpenAI 兼容的 `chat/completions` 请求:组织 messages、设置 temperature 与 max_tokens;
2. 读懂响应里的 `usage`,估算一次调用的真实成本;
3. 讲清项目的 LLM 配置链:`.env` → 环境变量 → `HelloAgentsLLM` 自动读取,以及 `LLM_*` 与 `OPENAI_*` 两套变量名的关系;
4. 用"单例"视角精读 `llm_service.py`,并掌握"定位框架源码、以源码为准"的通用方法。

## 课前自检

- [ ] 第 3 课后端能启动,`backend/.env` 里 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_ID` 三项有效(实验要花真钱,几十次调用通常不到一分钱,但 Key 必须是真的);
- [ ] 知道 `python -c "print(1)"` 怎么用(定位框架源码要用);
- [ ] 记得第 3 课 1.3 节的结论:改 LLM 配置 = 改环境变量,改完必须重启进程;
- [ ] 知道 Python 的 dict 取值写法(响应解析要用)。

---

## 1.1 LLM API 的本体:一次 HTTP 请求

剥到最底层,"调大模型"就是一个带鉴权的 HTTP POST。以 OpenAI 兼容接口为例(**事实标准**——OpenAI、DeepSeek、Kimi、GLM 等几乎所有供应商都兼容它,切换供应商只需换 base_url、model、key 三样):

```http
POST {LLM_BASE_URL}/chat/completions
Authorization: Bearer {LLM_API_KEY}
Content-Type: application/json

{
  "model": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "你是旅行规划专家。"},
    {"role": "user", "content": "帮我规划北京两日游。"}
  ],
  "temperature": 0.7,
  "max_tokens": 2000
}
```

逐字段拆解:

**messages —— 对话历史数组。** 每个元素是一个带角色的消息:

| role | 含义 | 在本项目中的影子 |
|---|---|---|
| `system` | 给模型的"长期指令":身份、规则、格式 | 每个 SimpleAgent 的 `system_prompt`(trip_planner_agent.py:182 等) |
| `user` | 用户的本次输入 | `plan_trip` 里拼出的各步 query |
| `assistant` | 模型自己说过的话 | 多轮对话/工具调用回填时使用(第 7 课) |

**模型没有记忆。** 你以为的"多轮对话",实际是每次把历史 messages 原样重发。这个认知是理解第 7 课"工具结果回填后再次请求 LLM"的地基——所谓 Agent 循环,不过是往 messages 数组里不断追加内容、反复调用同一个接口。

**temperature —— 随机性旋钮(通常 0–2)。** 越低输出越稳定、可复现;越高越发散。实验环节你会亲眼对比 0 与 0.7 的差异。

**max_tokens —— 输出长度上限。** 超限即截断(响应里 `finish_reason` 会是 `length`)。对本项目是个隐形炸弹:规划 Agent 要吐一整份行程 JSON,上限太小会被拦腰斩断——而第 13 课你会看到,截断的 JSON 正是 `_parse_response` 解析失败的常见来源之一。

---

## 1.2 token 与计费:钱是怎么算的

LLM 不按"句"收费,按 **token** 收——模型词表里的最小单位。粗略换算:1 个汉字约 0.6–1 个 token,1 个英文单词约 1.3 个 token,具体因模型而异。计费公式:

```
本次成本 = prompt_tokens × 输入单价 + completion_tokens × 输出单价
```

响应里自带用量统计(实验会亲手打印):

```json
"usage": {
  "prompt_tokens": 52,
  "completion_tokens": 418,
  "total_tokens": 470
}
```

对照本项目算笔账:每次规划,四个 Agent 各带一份系统提示词(其中规划 Agent 的模板有 78 行,trip_planner_agent.py:75-152),步骤 4 还要把前三步的完整结果拼进输入(`_build_planner_query`,294–326 行)——**输入 token 才是大头,而且同一个城市的天气、POI 查询结果每次都重新花一遍钱**。这就是第 18 课"缓存与成本控制"要治的病,今天先建立"每次调用都在烧 token"的直觉。

---

## 1.3 项目的 LLM 配置链:.env → 环境变量 → 框架

第 3 课 1.3 节留了个尾巴:`.env` 里写的是 `LLM_*`,Settings 里却是 `openai_*`,而真正干活的是框架。现在把整条链打通:

**第一环:`backend/.env.example` 定义了配置面**(2–13 行):

```
LLM_MODEL_ID=deepseek-flash                  # 模型名
LLM_API_KEY=YOUR_API_KEY                     # 密钥
LLM_BASE_URL=https://api.deepseek.com/v1     # OpenAI 兼容服务地址
LLM_TIMEOUT=60                               # 超时(可选,默认 60 秒)
```

**第二环:这些变量不在 Settings 里**。`config.py:42-44` 的 `openai_api_key` / `openai_base_url` / `openai_model` 只是带默认值的占位字段;真正消费 `LLM_*` 的代码用 `os.getenv` 直接读环境变量:

```python
# config.py:103-105(print_config 内)
llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
llm_base_url = os.getenv("LLM_BASE_URL") or settings.openai_base_url
llm_model = os.getenv("LLM_MODEL_ID") or settings.openai_model
```

可以看到兜底顺序:`LLM_API_KEY` 优先,退而求其次用 `OPENAI_API_KEY`;URL 和模型名同理。你启动后端时看到的横幅里"提供商 / 模型"两行,数据就出自这里。

**第三环:框架自己读环境变量**。`llm_service.py:22-24` 的注释写明了这一点(下节精读全文)。`Settings` 全程没有参与 LLM 配置的传递——它只负责"提醒你配没配"(validate_config)和"打印给你看"(print_config)。

> 为什么要花一整节讲这个"绕路设计"?因为这是真实项目的常态:**框架的约定与项目自己的配置体系并行,新同学最容易在 Settings 里改半天 LLM 参数然后疑惑"为什么没生效"**。记住:LLM 配置的唯一真源是环境变量。

---

## 1.4 精读 llm_service.py:一个单例标本

全文如下(注释略作保留):

```python
# backend/app/services/llm_service.py(全文)
"""LLM服务模块"""

from hello_agents import HelloAgentsLLM
from ..config import get_settings

# 全局LLM实例
_llm_instance = None


def get_llm() -> HelloAgentsLLM:
    """
    获取LLM实例(单例模式)

    Returns:
        HelloAgentsLLM实例
    """
    global _llm_instance

    if _llm_instance is None:
        settings = get_settings()

        # HelloAgentsLLM会自动从环境变量读取配置
        # 包括OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL等
        _llm_instance = HelloAgentsLLM()

        print(f"✅ LLM服务初始化成功")
        print(f"   提供商: {_llm_instance.provider}")
        print(f"   模型: {_llm_instance.model}")

    return _llm_instance


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None
```

四个看点:

1. **单例三件套**:模块级变量 `_llm_instance`(7 行)+ `is None` 检查(19 行)+ `global` 声明(17 行)。首次调用才创建,之后所有调用者拿到同一个对象。为什么必须单例?客户端初始化有真实开销(读环境变量、建立 HTTP 通道),而且全项目四个 Agent 应该共用同一份模型配置——否则改了 `.env` 可能只影响半个系统。
2. **无参构造**(`HelloAgentsLLM()`,24 行):一个参数都没传,配置完全来自环境变量。`provider` 和 `model` 是框架暴露的公开属性(27–28 行打印的就是它们)——启动后端时你在横幅里见过。
3. **`reset_llm`(33–36 行)**:把全局变量置回 None,下次 `get_llm()` 会重新创建。注释说"用于测试或重新配置"——这是单例的标配逃生门:单例带来共享,也带来"想换配置就得拆"的麻烦。
4. **家族认证**:`get_llm` 和你已经认识的 `get_trip_planner_agent`(trip_planner_agent.py:422-429)、`get_amap_mcp_tool`(amap_service.py:12-47)是同一个模式。第 1 课架构图上你标过"三个单例",现在你知道它们为什么长得一模一样。

---

## 1.5 定位框架源码:不猜,去看(全课程通用基本功)

准确性红线先立在此处:**hello-agents 框架的源码不在本仓库里**,它被 pip 装在虚拟环境的 `site-packages` 中。本讲义不会引用任何"框架第 X 行"——凡涉及框架内部,一律教你怎么自己找到、亲自验证。

**第一步:找到框架住在哪。**

```bash
# 用你第 3 课建好的虚拟环境
python -c "import hello_agents; print(hello_agents.__file__)"
# 输出形如:.../backend/venv/Lib/site-packages/hello_agents/__init__.py
```

**第二步:顺着用到的名字往下挖。** `from hello_agents import SimpleAgent, HelloAgentsLLM` 说明两者都在包的顶层命名空间。打开包目录,搜 `class HelloAgentsLLM`,阅读它的 `__init__`:哪些环境变量被读取、优先级如何、`provider` / `model` 属性怎么来的、`LLM_TIMEOUT`(backend/.env.example:13)用没用上。把你的发现写进笔记——**不同版本实现可能有差异,你读到的才是事实**(本仓库 `requirements.txt:2` 用 `hello-agents[protocols]>=0.2.4,<=0.2.9` 锁定了版本范围,以你环境里实际安装的版本为准)。

**第三步:善用在线镜像。** 框架 GitHub 仓库:https://github.com/datawhalechina/hello-agents (学习建议.md 第 124 行),配合本地版本对照阅读。

这个"三步法"在第 7 课要动真格:大纲要求你顺着 `SimpleAgent.run` 往下挖出 `[TOOL_CALL]` 的解析循环。今天先用一个小问题练手(放进实验)。

---

## 2. 动手实验:20 行裸脚本直调 LLM API(本课核心任务)

### 任务

完全绕开 hello-agents,用 `httpx`(第 3 课已随 requirements 安装,requirements.txt:11)直接发一次 `chat/completions`,打印回复与 token 用量;再用 temperature 做一组对照。做完这个实验,"LLM API"对你而言不再是黑盒。

### 步骤

1. 新建 `docs/lesson05_bare_llm_call.py`,内容如下(核心调用约 20 行):

```python
"""第 5 课实验:绕开框架,直接调 OpenAI 兼容接口"""
import os
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "backend" / ".env")   # 直接借后端的 .env

base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
api_key = os.getenv("LLM_API_KEY")
model = os.getenv("LLM_MODEL_ID", "gpt-4o-mini")

resp = httpx.post(
    f"{base_url}/chat/completions",
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个简洁的中文助手,回答不超过两句话。"},
            {"role": "user", "content": "用一句话解释什么是 AI Agent。"},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    },
    timeout=60,
)
data = resp.json()

print(data["choices"][0]["message"]["content"])
print("usage:", json.dumps(data["usage"], ensure_ascii=False))
```

2. 用后端虚拟环境的 Python 运行(确保 httpx 与 dotenv 就位):

```bash
python docs/lesson05_bare_llm_call.py
```

3. **对照组一(temperature)**:把 `temperature` 改成 0,连跑两次;再改回 0.7 连跑两次。记录:哪组两次输出一致?
4. **对照组二(max_tokens)**:把 `max_tokens` 改成 20,观察输出被截断的样子,并在响应 JSON 里找到 `finish_reason` 字段确认;
5. **框架对照**:去掉 `max_tokens` 字段,再跑一次,记录默认行为;
6. **源码验证(1.5 节练手)**:用 `python -c "import hello_agents; print(hello_agents.__file__)"` 定位框架,确认 `HelloAgentsLLM.__init__` 实际读取的环境变量清单(至少回答:支持 `LLM_API_KEY` 还是 `OPENAI_API_KEY`?`LLM_TIMEOUT` 生效吗?),写进笔记。

### 完成标准

- [ ] 裸脚本跑通,屏幕上有回复文本和 usage 三项;
- [ ] 用你供应商的单价算出这一次调用的成本(公式见 1.2 节),写进笔记;
- [ ] temperature 0 与 0.7 的可复现性差异有记录;
- [ ] `finish_reason` 的 `stop` 与 `length` 两种取值你都亲眼见过;
- [ ] 笔记里有框架源码验证结论:环境变量清单 + 是否支持 `LLM_TIMEOUT`,并注明你读的框架版本。

### 常见卡点

- **"401 Unauthorized?"** —— key 没被读到(`load_dotenv` 的路径是相对 `docs/` 上级写的,别挪脚本位置),或 key 本身无效。先 `python -c "import os; from dotenv import load_dotenv; load_dotenv('backend/.env'); print(os.getenv('LLM_API_KEY')[:6])"` 验证加载。
- **"404 model not found?"** —— 三选一排查:`LLM_MODEL_ID` 拼写与供应商不符;`LLM_BASE_URL` 少了或多了 `/v1`;供应商换了但 .env 忘改。OpenAI 兼容≠模型名通用。
- **"响应里没有 usage 字段?"** —— 个别供应商在流式或特定参数下不返回 usage;把整个 `data` 打印出来看结构,以实际响应为准。
- **"Windows 终端中文乱码?"** —— `chcp 65001`(第 3 课讲过 start.bat 第 2 行的作用),或在 IDE 内置终端里跑。

---

## 3. 课后作业与思考题

**必做:**

1. 实验全部完成,`docs/lesson05-notes.md` 记录:一次真实 usage 与成本估算、temperature 对照结论、框架源码验证清单(含版本号);
2. 回答并写进笔记:如果把 `LLM_BASE_URL` 从 DeepSeek 换成另一家 OpenAI 兼容供应商,理论上要改哪几个变量?哪些东西(提示词、代码、schema)可以完全不动?——这就是"OpenAI 兼容"四个字的工程价值;
3. 算一笔账:按 1.3 节的观察,一次规划要发 4 个不同的系统提示词;假设每次规划输入合计 6000 token、输出 1500 token,用你供应商的单价算出单次规划成本,乘以 1000 次请求——这个数字是第 18 课做缓存的动机。

**选做(思考,不用交):**

1. 把裸脚本改造成三轮对话(把上一轮 assistant 的回答 append 回 messages 再问一句"你刚才说了什么"),体会"模型无记忆";
2. 试出你所用模型的上下文窗口极限:从 1.2 节的账目推算,本项目 `_build_planner_query` 拼进的三份字符串(294–326 行)最长可能占多少 token?什么场景下会爆窗口?

## 下节预告

**第 6 课:提示词工程。** 大脑接通了,该研究"对大脑说什么"。精读 `trip_planner_agent.py` 顶部 4 份提示词与 `_build_planner_query`,用"角色/任务/格式约束/示例/红线"五件套拆解它们,亲自动手找缺陷——编号重复、约束模糊——并用 5 次生成的 JSON 合规率验证你的改进是否真的有效。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
