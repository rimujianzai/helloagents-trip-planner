# 第 9 课:ReAct 范式与手写迷你 Agent

> 所属模块:模块二「Agent 核心原理」(第 5–10 课)
> 预计时长:1.5–2 小时(实验用假工具,只消耗少量 LLM 调用,不需要高德 Key)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:第 8 课:工具调用机制(下):原生 Function Calling

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理 ← 你在这里(第 9 课)
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶
```

第 7、8 课解决的都是"怎么调工具"(文本协议与结构化协议),但有一个问题被我们悄悄跳过了:**LLM 凭什么决定调不调、调几个、什么时候收工?** 本课引入 Agent 界最经典的答案——ReAct 范式:把"想"(Thought)和"做"(Action)摆上台面轮流进行,用 `Finish` 令牌显式收工,用最大轮数保护兜底。然后你要做一件整个模块二最有仪式感的事:**抛开 hello-agents,抛开一切框架,亲手写一个 100 行以内的 ReAct 循环**——写完它,你再看任何 Agent 框架都只剩"语法糖"。

## 学习目标

完成本课后,你应该能够:

1. 说出 ReAct(Reason + Act)的核心思想,以及 Thought → Action → Observation 循环每一步的职责;
2. 列出 ReAct 循环的三种终止条件,并解释"最大轮数保护"防的是什么(死循环烧钱);
3. 独立实现一个 100 行以内、直调 OpenAI 兼容 API 的迷你 ReAct Agent,接入至少两个假工具;
4. 从消息组织、终止机制、错误处理三个维度,说清你的迷你版与 SimpleAgent / ReActAgent 的异同;
5. 兑现第 1 课留下的悬念:把"固定三步"变成"Agent 自己决定步骤",到底需要改变什么。

## 课前自检

- [ ] 第 7 课你追踪过 `SimpleAgent.run` 的循环,知道它的终止条件是"输出里不再出现 `[TOOL_CALL]`";
- [ ] 第 8 课你对比过两种协议,理解"错误即信息"为什么比"静默失败"好;
- [ ] 第 5 课你写过裸脚本直调 LLM API,知道 `messages`、`temperature` 怎么传;
- [ ] Python 基本功在线:字典、正则、`try/except`、命令行参数(`sys.argv`)都不陌生。

---

## 9.1 ReAct:让"想"和"做"轮流上台

ReAct 出自论文《ReAct: Synergizing Reasoning and Acting in Language Models》(Yao 等,2022),名字就是 **Rea**son + **Act** 的拼接。它的洞察用一句话说:让 LLM **先把推理写出来,再决定行动;看到行动结果后,接着推理**——推理和行动交替进行,而不是一口气想完再动手。

一轮标准的 ReAct 长这样:

```
Thought: 我需要先知道北京今天的天气,才能判断该不该安排户外景点。
Action: weather[北京]
Observation: 晴,12~24℃

Thought: 天气不错,可以安排户外。接下来查景点门票,算 4 人预算。
Action: calculator[60 * 4]
Observation: 240

Thought: 我已经有足够信息了。
Action: Finish[北京明天晴,适合安排户外景点;4 人门票共 240 元。]
```

三个角色的分工:

| 角色 | 谁产出 | 职责 |
|---|---|---|
| **Thought** | LLM | 显式推理:我现在知道什么、缺什么、下一步做什么 |
| **Action** | LLM | 决定:调哪个工具、传什么参数;或者宣布收工(`Finish`) |
| **Observation** | **你的代码** | 执行工具,把真实世界的结果还给 LLM |

注意 Observation 行的产出方变了——Thought 和 Action 是模型的输出,**Observation 是你的循环代码写进去的**。ReAct 的"引擎"不在模型里,而在你写的那个 for 循环里。

回看第 7 课的闭环,你会发现一个有趣的事实:`SimpleAgent` 其实是一个**没有 Thought 频道的 ReAct 变体**——同样有"输出→解析→执行→观察→再输出"的循环,但它不要求模型把推理显式写出来,终止也不靠专门令牌,而是"输出里没有调用标记就算完"。显式 Thought 不是装饰:它让推理**可观测**(你能看到它在想什么)、**可纠错**(错的想法在下一步有机会自我修正)、**可规划**(多步任务先拆解再执行)。这就是 ReAct 至今仍是 Agent 教学第一课的原因。

> **兑现第 1 课的承诺。** 第 1 课选做题问过:"如果把'查景点、查天气、查酒店'从固定三步改成让 LLM 自己决定先查哪个、查几次,需要改变什么?"现在可以回答了:把所有工具一次性交给一个 ReAct 循环,把 `plan_trip` 里写死的四步(242–264 行)换成一个"目标 + 工具箱 + 循环"。LLM 会在 Thought 里自己排序、自己决定查几轮、自己用 `Finish` 收工。代价也立刻显现:步数不可预测、token 消耗不可预算、失败路径指数增多——这正是第 1 课说"本项目选 workflow 是正确的工程选择"的另一面。改不改、改哪部分,第 29 课(范式进阶)会正面回答,今天先把引擎造出来。

## 9.2 循环的骨架与三种终止条件

剥掉所有细节,任何 ReAct 实现都是这个骨架:

```
history ← 空
循环 step = 1 .. max_steps:
    prompt ← 模板(工具清单, 问题, history)        # 把"记忆"嵌进提示词
    text ← LLM(prompt)                            # 模型输出 Thought + Action
    Action ← 解析(text)
    若 Action == Finish[答案]:  返回 答案          # 终止条件 1:显式收工
    若 Action 解析失败:        Observation ← 错误提示,继续  # 终止条件 2 前奏:自纠
    Observation ← 执行工具(Action)
    history ← history + 本轮三元组
返回 "已达最大步数"                                 # 终止条件 3:硬保护
```

三种终止条件,一个都不能少:

1. **`Finish` 令牌**——正常出口。把"我要收工了"做成协议的一部分,而不是让模型靠说"以上就是答案"来暗示;
2. **解析失败的自纠**——模型格式跑偏时,不崩溃、不静默,把"你的格式错了"作为 Observation 喂回去,给它一次重来的机会;
3. **最大轮数保护(`max_steps`)**——硬保险丝。想清楚它防的是什么:ReAct 循环里**每一步都是一次全量计费的 LLM 调用**,而且历史越滚越长;一旦模型陷入"同一个错误 Action 无限重试"(失败模式见第 7 课 7.7 表),没有上限就是一台烧钱的永动机。`max_steps` 不解决任何问题,它只是保证亏损有界——工程上的说法叫**止损**。

成本直觉题:若每步 prompt 包含此前全部历史,单步平均 `c` 个字符,跑满 `N` 步的总输入字符约是 `c·(1+2+…+N) = O(c·N²)`。步数翻倍,token 翻的不止一倍——这就是为什么生产级 Agent 都会把 Observation 截断、把历史压缩(选做作业会让你体验一次)。

## 9.3 框架里的 ReActAgent:先看别人怎么写

动手之前,先读一遍 hello-agents 的标准答案(0.2.9 `react_agent.py`;另外 Datawhale 教程第四章《ReAct 范式》有配套讲解,可对照阅读)。它的提示词模板把规则钉得很死:

```python
DEFAULT_REACT_PROMPT = """你是一个具备推理和行动能力的AI助手。...
## 工作流程
请严格按照以下格式进行回应，每次只能执行一个步骤：

Thought: 分析问题，确定需要什么信息，制定研究策略。
Action: 选择合适的工具获取信息，格式为：
- `{{tool_name}}[{{tool_input}}]`：调用工具获取信息。
- `Finish[研究结论]`：当你有足够信息得出结论时。
...
```

(0.2.9 `react_agent.py` 12–37 行,节选)

`run` 循环(119–200 行)与我们 9.2 的骨架几乎一一对应,三处实现细节值得抄进你的笔记:

```python
while current_step < self.max_steps:
    current_step += 1
    ...
    # 构建提示词
    tools_desc = self.tool_registry.get_tools_description()
    history_str = "\n".join(self.current_history)
    prompt = self.prompt_template.format(
        tools=tools_desc, question=input_text, history=history_str)

    # 调用LLM
    messages = [{"role": "user", "content": prompt}]
    response_text = self.llm.invoke(messages, **kwargs)
```

(0.2.9 `react_agent.py` 135–150 行,节选)

第一,**每一步都重建完整提示词,历史作为文本嵌进去**——不是像 SimpleAgent 那样往 `messages` 里累积消息,而是每轮只发一条 user 消息,把所有 Thought/Action/Observation 拼在正文里。两种"记忆"组织方式各有取舍,9.4 节对比。

第二,**解析失败也是一条 Observation**(180–181 行:`"Observation: 无效的Action格式,请检查。"`)——错误进入历史,模型下一步能看到它,这就是自纠。

第三,超限兜底是一句固定的话(193–194 行:`"抱歉,我无法在限定步数内完成这个任务。"`)。对比第 7 课 SimpleAgent 超限后"补发一次、可能泄漏 `[TOOL_CALL]`"的隐患:ReActAgent 的兜底**不会产生新调用**,也就不会泄漏——止损设计里连"最后一步"都要想清楚。

它解析 Action 的正则:`re.match(r"(\w+)\[(.*)\]", action_text)`(0.2.9 `react_agent.py` 212–217 行)。`max_steps` 默认 5(59 行)。注意这套语法**每步只允许一个 Action**——和第 7 课"一段输出可塞多个 `[TOOL_CALL]`"是两种并发观。

## 9.4 三代同堂:SimpleAgent、ReActAgent、你的迷你版

| 维度 | SimpleAgent(第 7 课精读) | ReActAgent(9.3 精读) | 你的迷你版(本课实验) |
|---|---|---|---|
| 显式 Thought | 无(推理藏在生成里) | 有 | 有 |
| 记忆组织 | `messages` 列表累积,角色分明 | 每步重建单条 user 消息,历史嵌正文 | 同 ReActAgent |
| 行动语法 | `[TOOL_CALL:name:k=v,...]`,一段可多个 | `Tool[input]`,一步一个 | 同 ReActAgent |
| 终止信号 | 输出里没有调用标记(隐式) | `Finish[...]` 令牌(显式) | 同 ReActAgent |
| 轮数上限 | `max_tool_iterations=3` | `max_steps=5` | 你定(建议 6) |
| 超限行为 | 补发一次,可能泄漏调用串 | 固定道歉语,不再调用 | 固定放弃语,不再调用 |
| 错误处理 | 错误文本回填,LLM 可能自纠 | 错误即 Observation,历史可见 | 同 ReActAgent |

这张表是模块二的"总复习索引":三列其实是同一台引擎的三种装配方式。看完它你应该确信一件事——**框架没有魔法**。接下来自己证明。

---

## 9.5 动手实验:手写 100 行以内的迷你 ReAct(本课核心任务)

### 任务

不用 hello-agents,不用任何 Agent 框架,只用 `openai` SDK 直调 OpenAI 兼容 API(第 5 课的裸脚本功夫),实现 9.2 的完整骨架:两个假工具(calculator + weather stub)、显式 Thought、`Finish` 终止、格式错误自纠、`max_steps` 保护。**全文件 ≤ 100 行**(不含空行与注释也可以,你自定标准,写进笔记)。

### 参考实现(约 75 行,建议先跑通再自己重写一遍)

在 `backend/` 下新建 `mini_react.py`:

```python
"""mini_react.py —— 第 9 课:100 行以内的迷你 ReAct Agent
运行:cd backend 后执行
python mini_react.py "北京今天适合穿短袖吗?另外故宫门票60元一张,我们4个人,500元预算买完票还剩多少?"
"""
import ast, operator, os, re, sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()  # 读取 backend/.env 的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID
client = OpenAI(api_key=os.getenv("LLM_API_KEY"), base_url=os.getenv("LLM_BASE_URL"))
MODEL = os.getenv("LLM_MODEL_ID")

# ---------- 两个假工具 ----------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv}

def calculator(expr: str) -> str:
    """只允许四则运算的安全求值器(绝不 eval 原始字符串)"""
    def _ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
        raise ValueError("不支持的表达式")
    try:
        return str(_ev(ast.parse(expr, mode="eval").body))
    except Exception as e:
        return f"错误: {e}"

_WEATHER = {"北京": "晴,12~24℃", "上海": "小雨,18~26℃", "广州": "多云,25~32℃"}

def weather(city: str) -> str:
    return _WEATHER.get(city.strip(), f"暂无{city}的数据(假工具只收录3个城市)")

TOOLS = {"calculator": calculator, "weather": weather}

# ---------- ReAct 提示词与循环 ----------
PROMPT = """你用 ReAct 方式解决问题,每轮只走一步,严格遵循格式:
Thought: 分析当前局面,决定下一步
Action: 工具名[输入] 或 Finish[最终答案]
可用工具: {tools}
题目: {question}
历史步骤:
{history}
现在输出这一步(只输出一组 Thought/Action):"""

def llm(prompt: str) -> str:
    resp = client.chat.completions.create(model=MODEL, temperature=0,
        messages=[{"role": "user", "content": prompt}])
    return resp.choices[0].message.content

def run_react(question: str, max_steps: int = 6) -> str:
    history = []
    for step in range(1, max_steps + 1):
        text = llm(PROMPT.format(tools=list(TOOLS), question=question,
                                 history="\n".join(history) or "(无)"))
        print(f"\n--- 第 {step} 步 ---\n{text.strip()}")
        thought = re.search(r"Thought:\s*(.+)", text)
        action = re.search(r"Action:\s*(.+)", text)
        if not action:                                   # 自纠:格式缺失
            history.append("Observation: 输出缺少 Action,请重试")
            continue
        m = re.match(r"(\w+)\[(.*)\]", action.group(1).strip(), re.S)
        if m and m.group(1) == "Finish":                 # 终止条件1:Finish 令牌
            return m.group(2)
        if not m:                                        # 自纠:格式错误
            history.append("Observation: Action 格式错误,应为 工具名[输入]")
            continue
        obs = TOOLS.get(m.group(1), lambda x: f"错误: 未知工具 {m.group(1)}")(m.group(2))
        print(f">>> Observation: {obs}")
        history.append(f"Thought: {thought.group(1) if thought else ''}\n"
                       f"Action: {m.group(0)}\nObservation: {obs}")
    return f"已达到最大步数({max_steps}),放弃。"          # 终止条件3:硬保护

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "故宫门票60元一张,4个人,500元预算买完票还剩多少?"
    print("最终答案:", run_react(q))
```

安全提醒:计算器工具**必须**走 `ast` 白名单求值(像上面这样),直接 `eval(expr)` 等于让模型在你机器上执行任意 Python——这个坑第 22 课讲提示词注入时还会以更大的面目出现。

### 观察任务:三问一对照

跑通之后,用它做四个观察,把答案写进笔记:

1. **多步推理行为**:示例问题至少需要 `weather[北京]` + `calculator[500-60*4]` 两步。它实际走了几步?Thought 是在"规划下一步",还是原地打转复读上一句?
2. **错误自纠**:故意问"巴黎今天天气怎样,适合穿短袖吗?"——假工具没有巴黎的数据,Observation 会报"暂无数据"。它下一步做什么?换工具、换说法,还是硬编一个答案?把原始输出摘下来。
3. **止损**:把 `max_steps` 改成 `1` 和 `2` 各跑一次,观察兜底文案;再算一笔账:若不加上限、模型每步都重复同一个错误 Action,按你模型的单价,一晚上循环能烧多少钱?
4. **对照第 7 课**:用第 7 课的 `tool_trace.py`(或回忆日志)与本次输出并排,按 9.4 的表逐行填写"实测确认/实测不符"。

### 完成标准

- [ ] `mini_react.py` 全文件 ≤ 100 行(空行注释是否计入,由你声明并遵守);
- [ ] 三个假问题都能得到正确最终答案:天气判断题、两步计算题、故意给假工具不收录的城市;
- [ ] 三种终止条件都在输出中亲眼见过:Finish 正常收工、格式错误自纠后继续、max_steps 触发放弃;
- [ ] 9.4 对照表逐行核对完毕,与 SimpleAgent 的 2 处以上行为差异写进了 `docs/lesson09-react-notes.md`;
- [ ] 有一段你亲手摘录的"模型从错误 Observation 中恢复"的对话原文。

### 常见卡点

- **"模型不按 Thought/Action 格式输出"** —— 先确认提示词里给了完整格式说明和"每轮只走一步"的硬约束;再把 `temperature` 设为 0;仍不行就把一条错误 Observation 写进历史重试(你的循环本来就该这么做)。若模型反复跑偏,换成能力更强的模型再试——格式遵循度是模型能力的一部分,这本身就是要记录的实验事实。
- **"calculator 报语法错误"** —— 模型可能传进 `60×4`(乘号是 Unicode)或 `500 - 60*4 = 260`(带等号和答案)。两个选择:在工具里清洗常见字符(如 `×`→`*`),或把原始错误作为 Observation 还给模型让它重写——推荐后者,这正是 ReAct 的用法。
- **"为什么不用 messages 列表,非得每轮重建 prompt?"** —— 不是"非得",是取舍:ReAct 的历史本来就是一份"推理笔记",嵌在正文里便于模型整体回顾;messages 列表的好处是角色分明、便于复用对话基础设施。两种都写一遍(第 7 课一种、本课一种),你就有了判断的坐标系。

---

## 9.6 课后作业与思考题

**必做:**

1. 完成迷你 ReAct 与观察任务(`docs/lesson09-react-notes.md` 存档);
2. 回答:第 7 课的 SimpleAgent、第 8 课的 FunctionCallAgent、本课的 ReAct 循环,各自的"终止判断"由什么触发?哪一种对"模型说谎/跑偏"最鲁棒?为什么?

**选做(思考,不用交):**

1. 给循环加"Observation 截断":超过 300 字的工具结果只保留前 300 字,重跑两步计算题,观察 token 节省与答案质量的变化——9.2 节 `O(c·N²)` 的直觉验证;
2. 把天气假工具换成真实的高德 MCP 工具(用第 10 课之前的方式:直接调 `MCPTool.run({"action": "call_tool", ...})`,参考 `amap_service.py` 105–111 行的写法),让 ReAct 循环驱动真地图数据——这是你第一个"不靠框架的全自动 Agent",留着,第 11 课开头会用到。

## 下节预告

**第 10 课:MCP 协议深入。** 整个模块二你都在通过 hello-agents 的 `MCPTool` 使用工具,但"按下调用按钮"之后,消息是怎么走到 `uvx amap-mcp-server` 的?下节课掀开最后一块盖板:host/client/server 架构、stdio 传输、JSON-RPC 消息本体——你会亲手用 stdin/stdout 和 MCP 服务器对话,亲眼看到 `initialize`、`tools/list`、`tools/call` 的原始报文。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。框架源码行号基于 hello-agents 0.2.9(用 `pip show hello-agents` 定位你本地的同一份)。课程问题优先回看 [课程大纲.md](./课程大纲.md) 附录 B 的自检问题。*
