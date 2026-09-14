# 第 8 课:工具调用机制(下):原生 Function Calling

> 所属模块:模块二「Agent 核心原理」(第 5–10 课)
> 预计时长:2 小时(本课实验是模块二里程碑,需要 3 组 × 10 次真实调用,请确认 LLM API Key 与高德 Key 额度充足)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:第 7 课:工具调用机制(上):文本协议

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理 ← 你在这里(第 8 课)
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶
```

第 7 课你把 `[TOOL_CALL:...]` 文本协议的闭环拆到了正则级别,并攒下了一张失败模式清单。本课把同一条闭环换成**结构化协议**重走一遍:OpenAI `tools` API 让模型直接返回结构化的 `tool_calls` 对象,结果用专门的 `role="tool"` 消息回填。然后是本模块的里程碑实验——**A/B/C 三组对照**:注入版、纯提示词版、原生 Function Calling 版,各跑 10 次,用数据回答"文本协议到底损失了什么"。这份对比实验报告就是大纲为模块二规定的里程碑产出。

## 学习目标

完成本课后,你应该能够:

1. 说出 OpenAI tools API 三件套(`tools` 数组、assistant 消息的 `tool_calls`、`role="tool"` 回填)的位置和作用,并解释 hello-agents 的 `FunctionCallAgent` 为什么必须绕过 `HelloAgentsLLM.invoke` 直连底层客户端;
2. 讲清一个 MCP server 如何被展开成多个 LLM 可见函数,以及 `trip_planner_agent.py:175` 那行 `expandable=True` 不写会发生什么;
3. 从可靠性、token 成本、失败形态三个维度对比文本协议与结构化协议;
4. 完成三组对照实验,把成功率/耗时/token 数据写成一份诚实的实验报告并存入 `docs/`。

## 课前自检

- [ ] 第 7 课实验你跑通了 `TOOL_TRACE` 日志,亲眼见过一次 `run()` 内部的 2 轮 LLM 往返;
- [ ] 你能默写出闭环六步,知道工具结果当前是以 `user` 角色回填的;
- [ ] 你手上有第 7 课那张失败模式清单(7.7 节的表),本课要用它做预测;
- [ ] `git` 基本操作没问题(本课要开分支做改动,避免污染 main);
- [ ] 后端环境正常,`uvx amap-mcp-server` 能被拉起(第 3 课跑通过 `/api/trip/plan`)。

---

## 8.1 两种协议,一条闭环

先建立一个不慌的框架:文本协议和 Function Calling,**闭环的六步骨架完全一样**——LLM 输出 → 解析 → 执行工具 → 结果回填 → 再请求 → 终止判断。变的只有两处:

| 环节 | 文本协议(第 7 课) | 原生 Function Calling(本课) |
|---|---|---|
| LLM 怎么"说"要调工具 | 输出一串长得像调用的**文本** `[TOOL_CALL:...]` | 响应对象里携带结构化的 **`tool_calls` 字段** |
| 结果怎么回填 | 包装成一句 user 消息 | 专门的 **`role="tool"`** 消息 |

也就是说,你第 7 课画的时序图**几乎可以原样复用**——本课学的是同一个骨架的"工业级接头"。

## 8.2 OpenAI tools API:三件套

Function Calling 是 OpenAI 定义、后被几乎所有兼容接口(DeepSeek、Qwen、GLM……)跟进的事实标准。一次带工具的对话由三部分组成。

**第一件:请求里带 `tools` 数组**——把每个工具的 JSON Schema 交给模型:

```json
{
  "model": "deepseek-chat",
  "messages": [{"role": "user", "content": "请搜索北京的历史文化景点"}],
  "tool_choice": "auto",
  "tools": [{
    "type": "function",
    "function": {
      "name": "amap_maps_text_search",
      "description": "关键词搜索POI",
      "parameters": {"type": "object",
        "properties": {
          "keywords": {"type": "string", "description": "搜索关键词"},
          "city": {"type": "string", "description": "城市名"}},
        "required": ["keywords"]}}}]
}
```

对比第 7 课 7.3 节:文本协议下模型只能看到"`- amap_maps_text_search: 一句话描述`";现在,**每个参数的名字、类型、描述、是否必填,全都摆在模型面前**。7.7 节的失败模式 3(参数名拼错)在这里从根源上被消解。

**第二件:响应里返回 `tool_calls`**——模型不再把调用"写"在正文里,而是作为结构化字段返回:

```json
{"choices": [{
  "message": {
    "role": "assistant",
    "content": null,
    "tool_calls": [{
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "amap_maps_text_search",
        "arguments": "{\"keywords\": \"历史文化\", \"city\": \"北京\"}"}}}]}}
```

注意两点:`arguments` 是一个 **JSON 字符串**(需要 `json.loads`,但格式由服务端保证合法);`id` 是这次调用的唯一凭证,回填时要靠它对号入座。

**第三件:用 `role="tool"` 消息回填结果**,凭 `tool_call_id` 关联:

```json
[
  {"role": "assistant", "content": null, "tool_calls": [{"id": "call_abc123", "type": "function", "function": {"name": "amap_maps_text_search", "arguments": "{\"keywords\": \"历史文化\", \"city\": \"北京\"}"}}]},
  {"role": "tool", "tool_call_id": "call_abc123", "name": "amap_maps_text_search", "content": "{\"status\": \"1\", \"pois\": [...]}"},
  {"role": "user", "content": "请基于以上结果给出完整回答"}
]
```

回填后再发一次请求,模型基于工具结果给出最终回答;若它还想调工具,就再次返回 `tool_calls`,循环继续。另外记住 `tool_choice` 这个旋钮:`"auto"`(模型自己决定)、`"none"`(禁止调用)、`"required"`(必须调用)——第 9 课以后做评测时会用到它。

## 8.3 框架里的原生实现:FunctionCallAgent

hello-agents 为这套协议提供了专门的 Agent。先看它怎么把注册表里的工具变成第一件套:

```python
def _build_tool_schemas(self) -> list[dict[str, Any]]:
    ...
    for tool in self.tool_registry.get_all_tools():
        properties: Dict[str, Any] = {}
        try:
            parameters = tool.get_parameters()
        except Exception:
            parameters = []

        for param in parameters:
            properties[param.name] = {
                "type": _map_parameter_type(param.type),
                "description": param.description or ""
            }
            ...
        schema: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": {"type": "object", "properties": properties}
            }
        }
        ...
```

(0.2.9 `function_call_agent.py` 62–126 行,节选)

`get_parameters()` 这个方法你其实见过——第 7 课 7.4 节,`SimpleAgent` 用它做**事后**类型转换;`FunctionCallAgent` 用它做**事前** schema 暴露。同一个接口,两种用法,高下立判。

再看一次关键决策——它为什么绕开 `HelloAgentsLLM.invoke`:

```python
def _invoke_with_tools(self, messages, tools, tool_choice, **kwargs):
    """调用底层OpenAI客户端执行函数调用"""
    client = getattr(self.llm, "_client", None)
    ...
    return client.chat.completions.create(
        model=self.llm.model,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        **client_kwargs,
    )
```

(0.2.9 `function_call_agent.py` 226–243 行)

答案在 `core/llm.py` 320–335 行:`HelloAgentsLLM.invoke` 的返回值写死为 `response.choices[0].message.content`——**就算你把 `tools` 塞给它,`tool_calls` 字段也会在返回前被丢掉**。所以 `FunctionCallAgent` 只好直接伸手拿 `llm._client`(那个第 5 课讲过的 OpenAI SDK 客户端)自己发请求。这是读框架源码的价值之一:你会看到框架作者自己也被这个封装绊了一下。

`run` 循环(0.2.9 `function_call_agent.py` 278–340 行)与第 7 课的循环逐段对得上,但回填变了:

```python
for tool_call in tool_calls:
    tool_name = tool_call.function.name
    arguments = self._parse_function_call_arguments(tool_call.function.arguments)
    result = self._execute_tool_call(tool_name, arguments)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_name,
            "content": result,
        }
    )
```

(0.2.9 `function_call_agent.py` 308–319 行,节选)

对比第 7 课 `simple_agent.py` 306 行——同样是"结果进 messages",一个是伪装的 user,一个是持 `id` 的 tool 消息。前者的模型只能靠文字猜"哦,刚才那个调用的结果来了";后者协议层就保证了对应关系,多工具并发时也不会张冠李戴。

还有一个第 7 课隐患的"官方修正版":文本协议超限后补发的 `invoke` 不再检查 `[TOOL_CALL]`;`FunctionCallAgent` 超限后的补发**显式带了 `tool_choice="none"`**(0.2.9 `function_call_agent.py` 328–336 行)——强制模型收工,结构化协议连"最后一步兜底"都有开关。

## 8.4 MCP 工具如何变成 LLM 可见的 functions

现在把视角拉回项目。`trip_planner_agent.py` 168–175 行:

```python
self.amap_tool = MCPTool(
    name="amap",
    description="高德地图服务",
    server_command=["uvx", "amap-mcp-server"],
    env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
    auto_expand=True
)
self.amap_tool.expandable=True
```

这里有三个环环相扣的机制,都是我逐行读过框架源码后确认的:

**1. `auto_expand=True`:一个 server,多个函数。** MCPTool 初始化时会连上 amap-mcp-server 做一次工具发现,把服务器的每个工具包装成独立的 `MCPWrappedTool`(0.2.9 `protocol_tools.py` 的 `get_expanded_tools`,314–337 行)。几十个地图工具在 LLM 眼里就是几十个独立函数。

**2. 前缀从哪来。** `MCPTool.__init__` 里有这么一行:`self.prefix = f"{name}_" if auto_expand else ""`(0.2.9 `protocol_tools.py` 114 行)。`name="amap"` 加上服务器的原始工具名 `maps_text_search`,得到 `amap_maps_text_search`。**前缀只是 hello-agents 的本地命名约定,MCP 协议本身没有它**(第 10 课你会亲手给服务器发不带前缀的 `maps_text_search`)。

**3. `expandable=True` 是给谁看的?** 这是项目里最隐蔽的一行,不读注册表源码根本想不通。`SimpleAgent.add_tool` 最终走到 `ToolRegistry.register_tool`,而展开的开关长这样:

```python
if auto_expand and hasattr(tool, 'expandable') and tool.expandable:
    expanded_tools = tool.get_expanded_tools()
```

(0.2.9 `registry.py` 29–30 行)

MCPTool 自己定义的是 `auto_expand` 属性,**没有** `expandable`。所以若删掉 175 行,注册表只会把整个 MCPTool 当**一个**名叫 `amap` 的工具注册——LLM 将不得不输出 `[TOOL_CALL:amap:action=call_tool,tool_name=maps_text_search,arguments=...]` 这种嵌套调用串,难度陡增。175 行是给注册表看的"准许展开"通行证。

顺带修正一个容易混的点:`FunctionCallAgent.add_tool` 走的是另一条路——它检查的是 `auto_expand` 属性(0.2.9 `function_call_agent.py` 350–358 行),**不需要** `expandable=True`。同一个 MCPTool,两种 Agent,两种展开判据。这种"同一个概念两套判据"的不一致,读第三方框架时要保持第 1 课练出的批判性。

到这里,大纲第 8 课知识点"MCP 工具如何注册为 LLM 可见函数"的完整答案:发现(连 server 拿工具清单)→ 展开(每个工具包成 MCPWrappedTool,`input_schema` 转成参数定义)→ 注册(进 ToolRegistry)→ 暴露(文本协议走一行式描述,Function Calling 走 `_build_tool_schemas`)。

## 8.5 两种协议的正面交锋:可靠性与 token 成本

把 7.7 的清单升级成一张对仗表。**先别往下看实验结果——基于此表写出你的预测**,这是本课实验的科学味所在:

| 维度 | 文本协议 `[TOOL_CALL]` | 原生 Function Calling |
|---|---|---|
| 格式约束由谁保证 | 正则事后解析,赌 LLM 守约 | API 服务端结构化解码,格式违约不可能 |
| 参数 schema 可见性 | 不可见,只有一行式描述 | 完整 JSON Schema(名字/类型/必填) |
| 失败形态 | **静默**:格式错了循环照常走,LLM 继续编 | **显式**:解码失败/参数缺失在协议层就暴露 |
| 多工具并发 | 一段文本塞多个标记,易错 | 一次响应原生携带多个 `tool_calls` |
| 超限兜底 | 补发不再检查,可能泄漏调用串 | 补发强制 `tool_choice="none"` |
| 每轮固定开销 | 工具清单(一行式)+ 格式说明 + few-shot 示例(+ 291 行注入) | `tools` 数组(schema 更大,但可省掉格式说明与示例) |
| 模型兼容性 | 任何会输出文本的模型 | 要求 API 支持 tools(主流兼容端点基本都支持) |

关于 token 成本,要说一句诚实的话:**结构化协议并不天然更省**。`tools` 数组每次请求照样原样重发;它省掉的是格式说明、few-shot 示例和"参数猜谜"导致的重试轮次。省不省、省多少,正是你要用实验量出来的——这正是它成为模块二里程碑的原因:结论不是背来的,是你自己测的。

---

## 8.6 动手实验:三组对照(模块二里程碑)

### 指标与成功定义(先钉死,再动手)

对每次调用记录:**是否成功、LLM 往返次数、耗时、输入/输出字符数**(进阶:精确 token)。"成功"的定义要可判定:**Agent 真实调用了工具且工具未报错,并且最终回答里包含了工具返回的真实 POI 名**(防止"没调工具但编了一段像模像样的景点"被误判为成功)。统一条件:同一任务("搜索北京的历史文化景点")、同一模型、`temperature=0`、每组 10 次。

### 步骤 1:公共测量脚手架(A/B 组共用)

在 `backend/` 下新建 `lesson08_ab.py`。注意观察点全部用 monkey-patch 注入,**不改任何源码**:

```python
"""第 8 课 A/B 组实验:文本协议(注入 vs 纯提示词)
运行:cd backend 后执行 python lesson08_ab.py
"""
import json, re, time
from hello_agents import HelloAgentsLLM, SimpleAgent
from hello_agents.tools import MCPTool
from app.config import get_settings
from app.agents.trip_planner_agent import ATTRACTION_AGENT_PROMPT, MultiAgentTripPlanner
from app.models.schemas import TripRequest

GROUP = "A"   # B 组:先把 trip_planner_agent.py 第 291 行的注入删掉,再把这里改成 "B"
N = 10

def json_extract(text):   # 从工具结果前 150 字符里抽 POI 名,用于严格判成功
    return re.findall(r'"name"\s*:\s*"([^"]+)"', text)[:3]

# ---- 观察点 1:统计 LLM 往返与字符量 ----
stats = {"llm_calls": 0, "chars_in": 0, "chars_out": 0}
_orig_invoke = HelloAgentsLLM.invoke
def counting_invoke(self, messages, **kwargs):
    stats["llm_calls"] += 1
    stats["chars_in"] += sum(len(m["content"]) for m in messages)
    resp = _orig_invoke(self, messages, **kwargs)
    stats["chars_out"] += len(resp)
    return resp
HelloAgentsLLM.invoke = counting_invoke

# ---- 观察点 2:记录工具调用 ----
tool_log = []
_orig_exec = SimpleAgent._execute_tool_call
def logged_exec(self, tool_name, parameters):
    result = _orig_exec(self, tool_name, parameters)
    tool_log.append({"tool": tool_name, "ok": not result.startswith("❌"), "head": result[:150]})
    return result
SimpleAgent._execute_tool_call = logged_exec

# ---- 组装:与项目完全一致的系统提示词与 MCP 工具 ----
settings = get_settings()
amap = MCPTool(name="amap", description="高德地图服务",
               server_command=["uvx", "amap-mcp-server"],
               env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
               auto_expand=True)
amap.expandable = True            # trip_planner_agent.py:175
agent = SimpleAgent(name="景点搜索专家", llm=HelloAgentsLLM(),
                    system_prompt=ATTRACTION_AGENT_PROMPT)
agent.add_tool(amap)

# ---- query 直接取自真实代码路径(第 291 行改没改,实验就测什么)----
request = TripRequest(city="北京", start_date="2026-10-01", end_date="2026-10-03",
                      travel_days=3, transportation="公共交通",
                      accommodation="经济型酒店", preferences=["历史文化"])

print(f"===== 组 {GROUP} | 任务: 搜索北京的历史文化景点 =====")
for i in range(N):
    stats.update(llm_calls=0, chars_in=0, chars_out=0)
    tool_log.clear()
    query = MultiAgentTripPlanner._build_attraction_query(None, request)  # 该方法不使用 self
    t0 = time.perf_counter()
    answer = agent.run(query, temperature=0)
    secs = time.perf_counter() - t0
    poi_names = [n for t in tool_log if t["ok"] for n in json_extract(t["head"])]
    ok = (len(tool_log) > 0 and all(t["ok"] for t in tool_log)
          and any(n in answer for n in poi_names))
    print(json.dumps({"run": i + 1, "group": GROUP, "ok": ok, "tool_calls": len(tool_log),
                      "llm_rounds": stats["llm_calls"], "sec": round(secs, 1),
                      "chars_in": stats["chars_in"], "chars_out": stats["chars_out"],
                      "answer_head": answer[:80]}, ensure_ascii=False))
```

关于严格判成功的两行:先从工具结果里抽出真实 POI 名,再检查它们是否出现在最终回答里——"没调工具但编了一段像模像样的景点"在这里会现出原形。

关于 `MultiAgentTripPlanner._build_attraction_query(None, request)`:我核对过它的函数体(281–292 行),**没有用到 `self`**,所以传 `None` 调用是安全的。这个技巧的价值是:A/B 两组实验的输入永远来自仓库的真实代码路径,你改了 291 行,实验自动跟着变,不存在"实验脚本和仓库代码不一致"的造假空间。

### 步骤 2:A 组——现状(注入版)

保持 291 行原样,`GROUP="A"`,跑 10 次,把每行 JSON 输出存下来。

### 步骤 3:B 组——删掉注入,仅靠系统提示词

先开分支,避免污染 main:

```bash
git checkout -b lesson08-experiment
```

把 `trip_planner_agent.py` 291 行改为(只删 `[TOOL_CALL:...]` 注入,系统提示词一个字不动):

```python
        query = f"请搜索{request.city}的{keywords}相关景点。"
```

`GROUP="B"`,再跑 10 次。**预期会有若干次直接失败**(LLM 编景点或格式漂移)——如实记录,那正是实验的价值;别偷偷把注入加回去。

### 步骤 4:C 组——原生 Function Calling

新建 `backend/lesson08_fc.py`:

```python
"""第 8 课 C 组实验:原生 Function Calling"""
import json, time
from hello_agents import HelloAgentsLLM, FunctionCallAgent
from hello_agents.tools import MCPTool
from app.config import get_settings

N = 10
tool_log = []
_orig_exec = FunctionCallAgent._execute_tool_call
def logged_exec(self, tool_name, arguments):
    result = _orig_exec(self, tool_name, arguments)
    tool_log.append({"tool": tool_name, "ok": not result.startswith("❌")})
    return result
FunctionCallAgent._execute_tool_call = logged_exec

settings = get_settings()
amap = MCPTool(name="amap", description="高德地图服务",
               server_command=["uvx", "amap-mcp-server"],
               env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
               auto_expand=True)          # FunctionCallAgent 不需要 expandable=True
agent = FunctionCallAgent(name="景点搜索FC", llm=HelloAgentsLLM(),
    system_prompt="你是景点搜索专家。你必须搜索真实景点,禁止编造。",
    max_tool_iterations=3)
agent.add_tool(amap)
print("展开的函数:", agent.list_tools())

for i in range(N):
    tool_log.clear()
    t0 = time.perf_counter()
    answer = agent.run("请搜索北京的历史文化景点", temperature=0)
    secs = time.perf_counter() - t0
    ok = len(tool_log) > 0 and all(t["ok"] for t in tool_log)
    print(json.dumps({"run": i + 1, "group": "C", "ok": ok, "tool_calls": len(tool_log),
                      "sec": round(secs, 1), "answer_head": answer[:80]}, ensure_ascii=False))
```

注意 C 组连 `expandable=True` 都不用写(8.4 节讲过原因)——脚本里那行注释就是提醒你验证这一点。

### 步骤 5:进阶——精确 token 消耗(可选但推荐)

A/B 组的 `HelloAgentsLLM.invoke` 丢掉了 `usage`,但底层客户端拿得到。在创建 `llm` 之后加一段包装(非流式响应自带 `usage`):

```python
llm = HelloAgentsLLM()
usage_log = []
_orig_create = llm._client.chat.completions.create
def create_with_usage(*args, **kwargs):
    resp = _orig_create(*args, **kwargs)
    usage_log.append(resp.usage)   # prompt_tokens / completion_tokens
    return resp
llm._client.chat.completions.create = create_with_usage
```

C 组的 `FunctionCallAgent` 同样走 `llm._client`,这段包装原样可用。若无精力,8.5 节说过:字符数是可接受的 token 代理指标,报告里注明即可。

### 步骤 6:写实验报告

汇总 30 行数据,写 `docs/lesson08-tool-calling-experiment.md`,至少包含:

1. **数据表**:每组 10 行(成功/工具调用次数/LLM 往返/耗时/字符数或 token);
2. **汇总对比**:成功率、平均耗时、平均每轮输入体量,三组并排;
3. **预测 vs 实测**:对照 8.5 的表,你预测中了哪几条、哪条被打脸;
4. **失败样本归因**:把 B 组失败案例的原始输出贴进报告,用第 7 课 7.7 的五类失败模式编号归类;
5. **一句话结论**:如果只能保留一种协议给这个项目,你选哪个,为什么。

实验完成后,`git add` 报告与脚本,但 **291 行的删除留在 `lesson08-experiment` 分支上**,main 保持现状——这个改动是否会最终合入,等第 9 课后你对比过 ReAct 的决策模式再定。

### 完成标准

- [ ] 三组各 10 次数据齐全(同一任务、同一模型、temperature=0);成功判定用了"工具真实执行 + 回答含真实 POI 名"的双重校验,而不是肉眼看回答顺不顺;
- [ ] 报告存于 `docs/lesson08-tool-calling-experiment.md`,含预测对照与失败归因;
- [ ] 能回答大纲附录 B 模块二自检问题 2:"`[TOOL_CALL]` 文本协议和原生 Function Calling,各自的失败模式是什么?"——用你自己的数据;
- [ ] main 分支上 291 行保持原样,实验改动都在分支或 `docs/` 里。

### 常见卡点

- **"B 组大多数时候直接编景点,实验没法看了"** —— 这就是结果,不是事故。第 7 课 7.7 失败模式 1 的现场复现。补一句技术背景:项目里天气 Agent(`trip_planner_agent.py` 250 行)和酒店 Agent(256 行)**本来就处在 B 组形态**——它们的 query 从来没有注入过工具调用,靠的正是系统提示词。所以 B 组不是假设,而是这个项目一半 Agent 的日常;它俩的稳定性你可以顺便观察对照。
- **"C 组报错,说 tools/tool_choice 不支持"** —— 部分第三方 OpenAI 兼容网关对 `tools` 的转发放得不完整。先用 DeepSeek 官方端点(或 OpenAI 官方)验证脚本本身没问题,再排查你的网关;确认是端点问题时,这本身就是"结构化协议对基础设施有要求"的实证,写进报告的兼容性一节。
- **"同样条件 10 次结果忽好忽坏"** —— 先确认 `temperature=0` 真的传进去了(A/B 组:`agent.run(query, temperature=0)`;C 组同理)。设了 0 仍有波动(工具返回内容变化、服务端采样),如实报告方差并给出解释——把方差写清楚,比只报平均值更像一份合格的实验记录。

---

## 8.7 课后作业与思考题

**必做:**

1. 完成三组实验与报告(8.6 完成标准全勾),这是模块二的里程碑产出;
2. 在报告末尾回答:为什么说"结构化协议把格式错误的检测从'事后正则'前移到了'协议层'"?这句话对调试体验意味着什么?

**选做(思考,不用交):**

1. 给 C 组换 `tool_choice={"type": "function", "function": {"name": "amap_maps_text_search"}}` 强制调用,对比 `auto` 的成功率与行为差异——这个旋钮在大纲第 28 课(评测)会正式登场;
2. 数一数 A 组一次 `run()` 的输入里,有多少字符花在"教 LLM 格式"上(项目提示词格式段 + 框架注入的格式段 + 注入的调用串),占输入总量的百分之几——这是提示词工程在工具调用上的隐性税。

## 下节预告

**第 9 课:ReAct 范式与手写迷你 Agent。** 文本协议和 Function Calling 都解决"怎么调工具",但还没回答"什么时候该收工、要不要先想再动手"。下节课你将认识 ReAct(Reason + Act)范式——Thought → Action → Observation 的显式推理循环、`Finish` 终止令牌与最大轮数保护——然后抛开一切框架,亲手写一个 100 行以内的迷你 ReAct Agent,和第 7 课见过的 SimpleAgent 面对面比武。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。框架源码行号基于 hello-agents 0.2.9(用 `pip show hello-agents` 定位你本地的同一份)。课程问题优先回看 [课程大纲.md](./课程大纲.md) 附录 B 的自检问题。*
