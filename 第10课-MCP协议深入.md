# 第 10 课:MCP 协议深入

> 所属模块:模块二「Agent 核心原理」(第 5–10 课)
> 预计时长:1.5–2 小时(实验需要高德 Key;工具发现与调用各需启动一次 `uvx`,首次运行会下载依赖,稍慢属正常)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:第 9 课:ReAct 范式与手写迷你 Agent

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理 ← 你在这里(第 10 课)
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶
```

模块二的最后一块拼图。前四课里,`MCPTool` 一直是个黑盒:你知道它会在初始化时"变出"几十个地图工具(第 8 课 8.4 节),知道每次 `run` 会真去调高德 API(第 7 课 7.5 节)。但**按下调用按钮之后,消息是怎么走到 `uvx amap-mcp-server` 的?** 本课掀开盖板:host/client/server 架构、stdio 传输、JSON-RPC 报文本体。实验环节你要绕开一切封装,用 `stdin`/`stdout` 和 MCP 服务器徒手对话——亲眼看过协议本体之后,`MCPTool` 对你而言就再也不存在"魔法"了。

## 学习目标

完成本课后,你应该能够:

1. 画出 MCP 的三方架构(host / client / server),并指出每一方在本项目里对应的具体进程或对象;
2. 解释 stdio 传输的本质(子进程 stdin/stdout 上的 JSON-RPC),说出一次 MCP 会话的四步生命周期;
3. 徒手实现一个 stdio MCP 客户端:发送 `initialize` → `notifications/initialized` → `tools/list` → `tools/call`,并读懂每一份响应;
4. 说出项目实际使用的 7 个高德工具(服务器原名)及其在 `amap_service.py` 中的位置;
5. 讲清 MCP 与 Function Calling 的分工:一个管"应用↔工具",一个管"模型↔应用",为什么说它们是正交的。

## 课前自检

- [ ] 你知道 `trip_planner_agent.py` 168–175 行创建了 `MCPTool`,`server_command=["uvx", "amap-mcp-server"]`;
- [ ] 第 7 课你在工具结果回填的消息里见过原始 JSON(高德 API 的返回),对 `pois`、`status` 这些字段混过脸熟;
- [ ] 你知道 JSON 是什么样的,听说过"序列化"(对象 ↔ 文本)的概念;
- [ ] 终端里 `uvx --version` 有输出(第 3 课装 uv 时带的;没有就 `pip install "uv>=0.8.0"`,与 `requirements.txt` 第 25 行一致)。

---

## 10.1 为什么需要 MCP:从 M×N 到 M+N

在 MCP 出现之前(它是 Anthropic 在 2024 年 11 月开源发布的协议),让一个 AI 应用接外部工具是纯手工活:高德有一套 SDK、GitHub 有另一套 API、数据库有自己的驱动,每个应用都要为每个工具源写一层专用胶水代码。M 个应用 × N 个工具源,就是 M×N 份胶水。

MCP 的思路是把这个乘法变成加法:**工具源把能力包装成 MCP 服务器(做 M 份里的 N 份),应用实现一次 MCP 客户端(做 N 份里的 M 份),中间用统一协议对话**。M+N 份工作,替代 M×N。这就是第 1 课 1.3 节那句"让接工具像插 USB 一样标准化"的完整含义——USB 之前,每个外设都要一张专用接口卡。

你的项目已经在享受这个红利:`amap-mcp-server` 不是你写的,是高德官方维护的 MCP 服务器;你的代码里没有一行直接调高德 REST API 的胶水,却拥有了它全部的地图能力。

## 10.2 架构:Host、Client、Server,以及 stdio 这根"管子"

MCP 的角色只有三个,对着你的项目一一对号:

| 角色 | 协议定义 | 在本项目里 |
|---|---|---|
| **Host(宿主)** | 面向用户的 AI 应用,内部管理一个或多个 client | 你的 FastAPI 后端进程(`MCPTool`、`AmapService` 都活在里面) |
| **Client(客户端)** | Host 内部的一条连接,与一个 server **1:1** 对话 | hello-agents 的 `MCPClient`(0.2.9 `protocols/mcp/client.py`),底层是 fastmcp 的 `Client` |
| **Server(服务器)** | 独立进程,对外暴露工具(tools)、资源(resources)、提示词(prompts) | `uvx amap-mcp-server` 拉起的子进程 |

client 与 server 是 1:1 的:项目里创建一个 `MCPTool`(name="amap"),就对应一条到 amap-mcp-server 的连接;若再接一个 GitHub MCP 服务器,就是第二条独立的 client。

**传输层**回答"消息怎么走"。本项目用的是最朴素的一种——**stdio**:client 启动一个子进程,把 JSON-RPC 消息一行一行写进它的 stdin,从它的 stdout 一行一行读回响应。子进程在哪,工具就在哪;没有端口、没有网络、没有序列化之外的协议开销。远程场景另有 HTTP / SSE 传输(0.2.9 `client.py` 113–119 行可见对应分支),本课聚焦 stdio——它是理解协议本体最短的路。

JSON-RPC 是报文格式标准:每条消息是一个 JSON 对象,`method` 说明要干什么,`id` 是请求编号,响应凭 `id` 对号入座;**没有 `id` 的是通知(notification)**——发出去就完,不期待回应。

## 10.3 一次会话的四步:报文本体

一次完整的 stdio MCP 会话按顺序发生四件事。下面每份报文都是协议标准形态,10.6 节实验里你会收到 amap-mcp-server 的**真实回声**——现在先混脸熟。

**① initialize:握手并协商版本。** 客户端自报家门:

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize",
 "params": {
   "protocolVersion": "2024-11-05",
   "capabilities": {},
   "clientInfo": {"name": "lesson10-manual", "version": "0.0.1"}
 }}
```

服务器回应自己的信息(名字、版本、支持的能力、它选定的协议版本)。版本协商的意义:协议在演进,双方先对齐"我们说哪一版的方言"。

**② notifications/initialized:确认握手。** 客户端发一条**通知**(没有 `id`),告诉服务器"握手完成,可以干活了"。

**③ tools/list:工具发现。** 客户端问"你有什么工具",服务器返回工具清单——每个工具带名字、描述和 `inputSchema`(JSON Schema 格式的参数定义):

```json
{"jsonrpc": "2.0", "id": 2,
 "result": {"tools": [
   {"name": "maps_weather",
    "description": "查询行政区划的天气",
    "inputSchema": {"type": "object",
      "properties": {"city": {"type": "string", "description": "城市名"}},
      "required": ["city"]}}
   ...
 }}
```

这一步就是第 8 课 8.4 节"工具如何变成 LLM 可见函数"的第一环:`MCPTool._discover_tools`(0.2.9 `protocol_tools.py` 244–278 行)在 `__init__` 时拉起服务器、执行 list_tools、把结果存进 `_available_tools`——你后端启动日志里打印的"工具数量"与"可用工具"列表(见 `amap_service.py` 37–45 行)就来自这里。

**④ tools/call:真实调用。** 客户端指名道姓:

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
 "params": {"name": "maps_weather", "arguments": {"city": "北京"}}}
```

响应的 `result.content` 是一个内容数组,文本工具的结果通常在 `content[0].text` 里——**那里躺着的,正是你第 7 课日志里看到的"工具执行结果"原文**(高德返回的原始 JSON)。四步走完,闭环合龙。

最后请注意一个本项目每天都在付的隐藏成本:`MCPTool.run` 的实现是 `async with MCPClient(...) as client:`(0.2.9 `protocol_tools.py` 381 行)——**每一次工具调用都新建连接、走一遍完整握手、用完即断**。也就是说,一次 Agent 工具调用 ≈ 起一个 `uvx` 子进程 + 握手 + 调用 + 收尸。功能完全正确,但每次几百毫秒到几秒的起停开销,这就是 10.6 实验要你亲手计时去感受的东西。

## 10.4 项目里的映射:谁在用哪 7 个工具

`AmapService` 是不经 Agent 的直连通道(第 1 课 1.4 节"双通道"),它把项目用到的 MCP 工具全部点名了。通读 `amap_service.py`,7 个工具的落点如下(全部为**服务器原名**,不带 `amap_` 前缀):

| MCP 工具(服务器原名) | 项目中的封装方法 | 代码位置 |
|---|---|---|
| `maps_text_search` | `search_poi`(同时被景点/酒店 Agent 用) | `amap_service.py` 73 行;Agent 侧注入点 `trip_planner_agent.py` 291 行 |
| `maps_weather` | `get_weather` | `amap_service.py` 107 行 |
| `maps_geo` | `geocode`(地址 → 坐标) | `amap_service.py` 206 行 |
| `maps_search_detail` | `get_poi_detail`(POI 详情) | `amap_service.py` 232 行 |
| `maps_direction_walking_by_address` | `plan_route`(步行) | `amap_service.py` 146 行(tool_map) |
| `maps_direction_driving_by_address` | `plan_route`(驾车) | `amap_service.py` 147 行 |
| `maps_direction_transit_integrated_by_address` | `plan_route`(公交) | `amap_service.py` 148 行 |

四个封装方法(`search_poi` / `get_weather` / `plan_route` / `geocode`)目前都还是返回空数据的 TODO 桩——但注意,**桩返回空 ≠ 没调通**:它们个个都真实执行了 `mcp_tool.run({"action": "call_tool", ...})`,只是拿到结果后没解析(`get_poi_detail` 是唯一完成解析的,219–254 行)。怎么补全它们是第 15 课的主线,本课不展开。

再核对一遍封装的统一形状(以 105–111 行为例):

```python
result = self.mcp_tool.run({
    "action": "call_tool",
    "tool_name": "maps_weather",
    "arguments": {"city": city}
})
```

`action` / `tool_name` / `arguments` 三个键,和 10.3 的 ④ 号报文一一对应——`MCPTool.run` 的这个参数字典,本来就是 tools/call 报文的 Python 化身。

## 10.5 MCP 与 Function Calling:正交的两层协议

本模块讲了两种"协议",最后把它们的分工说透,防止搅成一锅粥:

- **Function Calling(第 8 课)是"模型 ↔ 应用"的合同**:LLM 用结构化 `tool_calls` 告诉应用"我想调 X";它不关心 X 背后是本地函数、HTTP API 还是 MCP 服务器;
- **MCP(本课)是"应用 ↔ 工具"的合同**:应用用 JSON-RPC 告诉工具源"执行 Y";它不关心调用它的那个大脑是 OpenAI 还是 DeepSeek。

两层各自独立、可以自由组合。第 8 课的 `FunctionCallAgent` 就是一个现成的组合范例:MCP 工具(应用↔工具走 MCP)被 `_build_tool_schemas` 桥接成 OpenAI functions(模型↔应用走 Function Calling)。理解了这层正交性,你就明白为什么 MCP 能撑起"工具生态":**任何**实现了 MCP 的工具源,天然可以被**任何**实现了 Function Calling 的模型使用,不需要任何一方认识对方。

顺便预告第 30 课(毕业项目):届时用 docker-compose 编排前后端 + MCP 服务器,amap-mcp-server 会以独立容器的身份出现在部署清单里——正是"工具源独立于应用"这个架构性质的红利。

---

## 10.6 动手实验:徒手实现 stdio MCP 客户端(本课核心任务)

### 任务

绕开 hello-agents 与 fastmcp,用标准库 `subprocess` 启动 `uvx amap-mcp-server`,按 10.3 的四步手动发送 JSON-RPC 消息,亲眼看到协议本体,并给每一步计时。

### 步骤 1:写脚本

在 `backend/` 下新建 `manual_mcp_client.py`:

```python
"""manual_mcp_client.py —— 第 10 课:徒手实现 MCP stdio 客户端
运行:cd backend 后执行 python manual_mcp_client.py
"""
import json, os, subprocess
from dotenv import load_dotenv

load_dotenv()  # 读取 backend/.env 的 AMAP_API_KEY

# 注意:env 必须包含 os.environ(否则 uvx 找不到 PATH),
# 再把高德要求的环境变量名 AMAP_MAPS_API_KEY 叠加进去
proc = subprocess.Popen(
    ["uvx", "amap-mcp-server"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,           # 服务器日志走 stderr,别混进协议流
    env={**os.environ, "AMAP_MAPS_API_KEY": os.getenv("AMAP_API_KEY")},
    text=True, encoding="utf-8")

import time
_seq = {"id": 0}

def request(method, params=None):
    _seq["id"] += 1
    msg = {"jsonrpc": "2.0", "id": _seq["id"], "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    return _seq["id"]

def notification(method, params=None):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()

def read_response(want_id):
    """按行读取,直到拿到 id 匹配的响应(中间可能夹杂服务器通知)"""
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("服务器关闭了 stdout,检查 Key 与 uvx 安装")
        msg = json.loads(line)
        if msg.get("id") == want_id:
            return msg

# ① initialize:握手 + 协商协议版本
t0 = time.perf_counter()
rid = request("initialize", {
    "protocolVersion": "2024-11-05", "capabilities": {},
    "clientInfo": {"name": "lesson10-manual", "version": "0.0.1"}})
init = read_response(rid)
print(f"== ① initialize(耗时 {time.perf_counter()-t0:.2f}s)==")
print(json.dumps(init, ensure_ascii=False, indent=2)[:800])

# ② notifications/initialized:通知握手完成(无 id,不期待响应)
notification("notifications/initialized")

# ③ tools/list:工具发现
t0 = time.perf_counter()
rid = request("tools/list")
tools = read_response(rid)
print(f"\n== ③ tools/list(耗时 {time.perf_counter()-t0:.2f}s)==")
names = [t["name"] for t in tools["result"]["tools"]]
print(f"服务器共提供 {len(names)} 个工具:\n{names}")

weather = next(t for t in tools["result"]["tools"] if t["name"] == "maps_weather")
print("\nmaps_weather 的 inputSchema:")
print(json.dumps(weather["inputSchema"], ensure_ascii=False, indent=2))

# ④ tools/call:真实调用
t0 = time.perf_counter()
rid = request("tools/call", {"name": "maps_weather", "arguments": {"city": "北京"}})
call = read_response(rid)
print(f"\n== ④ tools/call(耗时 {time.perf_counter()-t0:.2f}s)==")
print(json.dumps(call, ensure_ascii=False, indent=2)[:1200])

proc.terminate()  # 用完关掉子进程——记住:MCPTool 每次调用都在重复这套起停
```

### 步骤 2:跑通并核对五个观察点

1. **握手回声**:`initialize` 响应里的 `serverInfo` 叫什么名字?`protocolVersion` 是不是你发的那版(服务器有权改协商结果,如实记录)?
2. **工具清单对账**:`tools/list` 数出来的数量,与后端启动日志打印的"工具数量"(`amap_service.py` 37 行)**应当一致**;名单里的名字**不带 `amap_` 前缀**——验证第 8 课 8.4 节的结论(前缀是 hello-agents 的本地约定);
3. **schema 对账**:`maps_weather.inputSchema` 的字段,与第 7 课框架"参数猜谜"用的 `get_parameters()` 来源一一对应(0.2.9 `mcp_wrapper_tool.py` 62–89 行消费的就是这份 schema);
4. **结果回声**:`tools/call` 响应 `result.content[0].text` 里的 JSON,与第 7 课日志里"工具执行结果"的原文**应当一致**——闭环合龙;
5. **计时感受**:记录 ① initialize 和 ④ tools/call 各自耗时。再跑第二遍实验,计时是否仍然如此?这就是"每次 run 起停一个进程"的固定成本(第 18 课缓存与成本控制会正面处理它)。

### 步骤 3:对照封装层

打开 hello-agents 的 `protocols/mcp/client.py`(用 `pip show hello-agents` 定位,第 7 课练过):`__aenter__`/`__aexit__`(0.2.9:198–213 行)对应你脚本的启动/终止,`list_tools`(215–237 行)与 `call_tool`(239–258 行,注意它取 `content[0].text`)对应你的 ③④。在笔记里标注:fastmcp 的 `Client` 替你做了哪些事(自动握手、发初始化通知、逐行读 stdout、按 id 匹配响应)——你手写的每一行,都是它的内部。

### 完成标准

- [ ] 脚本跑通,四步报文原文(你的请求 + 服务器响应)完整保存到 `docs/lesson10-mcp-notes.md`;
- [ ] 五个观察点全部核对并有记录,工具清单数量与后端启动日志对上;
- [ ] 两个关键耗时(initialize / tools/call)有数字;
- [ ] 能不看资料说出:host/client/server 在本项目各对应什么,stdio 上跑的是什么格式的东西;
- [ ] (模块二总复习)能凭记忆画出一条完整链路:`plan_trip` 245 行 → SimpleAgent 循环 → 正则/`tool_calls` → `MCPWrappedTool` → `MCPTool.run` → 你的四步报文 → 高德 API。

### 常见卡点

- **"子进程秒退,readline 抛 RuntimeError"** —— 三查:一是 `stderr=subprocess.DEVNULL` 必须有(服务器日志写 stderr,若与 stdout 混管会导致协议流被污染);二是 env 里保留 `os.environ`(丢掉 PATH 则 uvx 找不到);三是手动跑一次 `uvx amap-mcp-server` 看它是否能独立启动(首次运行要下载依赖,耐心等)。排障时临时把 stderr 放开到终端(`stderr=None`)能看到服务器日志。
- **"收到一堆像日志的行,json.loads 报错"** —— 说明 stderr 混进了 stdout(通常是环境变量或管道参数问题);真正的协议流每一行都是合法 JSON。过滤不是正道,修管道才是。
- **"tools/call 返回 isError: true"** —— 打开响应看 `content` 里的错误描述,常见是参数名不符(对照 inputSchema)或高德 Key 无效(Key 报错形态会在响应文本里明说)。顺便体会:错误以**正常响应**的形态返回,这正是第 8 课 8.5 节说的"MCP 层显式失败"——比文本协议的静默错好查得多。

---

## 10.7 课后作业与思考题

**必做:**

1. 完成实验并存档 `docs/lesson10-mcp-notes.md`(完成标准全勾);
2. 在笔记里回答模块二的自检闭环题:从 291 行的注入字符串到高德 API 的 HTTP 请求,数据一共经历了哪几次"形态转换"?(文本 → 正则捕获组 → 参数字典 → JSON-RPC 报文 → 高德 JSON → 文本回填)

**选做(思考,不用交):**

1. 把 ④ 换成 `tools/call` 调 `maps_geo`(`{"address": "故宫博物院", "city": "北京"}`),看看地理编码返回什么——第 16 课(真实通勤时间驱动规划)的原料就是这个工具;
2. 改造你的手动客户端:在一次连接里连续调用 `tools/call` 三次(不重启子进程),对比"三次起停 + 三次握手"与"一次连接三次调用"的总耗时——量化 10.3 节说的隐藏成本,你会更理解第 18 课为什么要给 MCP 查询加缓存。

## 下节预告

**第 11 课:多智能体编排模式。** 模块二你已经吃透了单个 Agent 的五脏六腑;从下节课起视角抬高一层:多个 Agent 如何组织?你将用依赖分析的眼光重新审视 `plan_trip` 的四步串行,发现它其实是"并行扇出 + 串行汇总"结构,并亲手用 `asyncio.gather` 把三个前置 Agent 并行化,量出端到端提速——模块三的大幕由此拉开。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。框架源码行号基于 hello-agents 0.2.9(用 `pip show hello-agents` 定位你本地的同一份)。课程问题优先回看 [课程大纲.md](./课程大纲.md) 附录 B 的自检问题。*
