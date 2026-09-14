# 第 26 课:SSE 流式输出(后端)

> 所属模块:模块六「产品化与进阶」(第 25–30 课)
> 预计时长:1.5–2 小时(含动手实验,需要后端能跑起来)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第 25 课-地图可视化深入](./第25课-地图可视化深入.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶   ← 你在这里(第 26 课)
```

你的项目性能上已经没有大毛病:三路并行、缓存、日志、测试都齐了。但还有一个体验上的"硬伤"——**一次规划要等 30 秒到 2 分钟,而这 2 分钟里用户和后端之间是"哑巴"的**:请求发出去,连接上再没有任何字节流动,直到最后一刻 JSON 一次性砸回来。`frontend/src/services/api.ts:8` 那个 `timeout: 120000`(2 分钟超时)就是为这次漫长等待准备的。本课把后端四个步骤的真实进度变成 **SSE(Server-Sent Events)事件流**——用户将实时看到"开始搜索景点 → 景点完成 → 开始查天气 → …… → 完成"。

## 学习目标

完成本课后,你应该能够:

1. 说清为什么这个项目需要流式:算一笔"时间账"和"感知账";
2. 对比 SSE 与 WebSocket 的取舍,并能解释本场景为什么 SSE 够用;
3. 掌握 FastAPI `StreamingResponse` + 异步生成器,以及用 `asyncio.Queue` 桥接"规划任务"与"响应流"的模式;
4. 实现 `POST /api/trip/plan/stream`,把 `plan_trip` 的四个步骤变成 `event: step` 与 `event: plan` 事件流,并用 `curl -N` 验证。

## 课前自检

- [ ] 第 11 课的并行化已完成:景点/天气/酒店三路已用 `asyncio.gather` 并行(若没有,本课照常可做,只是事件顺序是串行的);
- [ ] 第 12 课的异步改造已完成:`async def` 路由不再被同步代码卡死事件循环;
- [ ] 能用 `/docs` 或 curl 调通现有的 `POST /api/trip/plan`;
- [ ] 记得 `plan_trip` 的结构:`backend/app/agents/trip_planner_agent.py:223-279`,四个步骤在 242–264 行。

---

## 1.1 为什么需要流式:先算一笔时间账

打开 `backend/app/agents/trip_planner_agent.py`,看 `plan_trip` 的主体(223–279 行),四个步骤在 242–264 行:

```python
# 步骤1: 景点搜索Agent搜索景点
attraction_response = self.attraction_agent.run(attraction_query)      # 245
# 步骤2: 天气查询Agent查询天气
weather_response = self.weather_agent.run(weather_query)               # 251
# 步骤3: 酒店推荐Agent搜索酒店
hotel_response = self.hotel_agent.run(hotel_query)                     # 257
# 步骤4: 行程规划Agent整合信息生成计划
planner_response = self.planner_agent.run(planner_query)               # 263
```

每个 `agent.run()` 内部至少是一轮 LLM 调用,景点/天气/酒店三步还各自夹着 MCP 工具调用往返(第 10 课)。估算一下:三路并行(第 11 课之后)约 15–60 秒;第 4 步要生成几千 token 的完整 JSON,单是输出就要 30 秒到 1 分多钟。**总计 30 秒–2 分钟,这还是一切顺利的情况。**

缩短这段"真实时长"很难——LLM 的生成速度不由你决定。但用户的痛苦主要来自**"不知道系统死没死"**:`Home.vue:261-277` 现在用一个 `setInterval` 每 500ms 把假进度加 10%,状态文案"正在搜索景点/正在查天气"完全是猜的(注释原话:"模拟进度更新")。

这就是流式的价值公式:**当真实时长无法压缩时,把过程透明化是缩短"感知时长"的唯一办法。** 而且对你的项目还有一个额外红利:第 26 课之后你会看到,三个"开始"事件几乎同时到达——**事件流本身就是第 11 课并行化的可视化证明。**

---

## 1.2 SSE vs WebSocket:一次务实的选型

一提"流式/实时",很多人第一反应是 WebSocket。先把两者摆在一起看:

| 维度 | SSE | WebSocket |
|---|---|---|
| 底层 | 普通 HTTP(响应体不结束) | 独立协议(`ws://`,需升级握手) |
| 方向 | 单向:服务器 → 客户端 | 双向 |
| 数据格式 | 文本(事件流) | 文本/二进制 |
| 断线重连 | 浏览器 `EventSource` 原生自动重连(带 `Last-Event-ID`) | 自己实现 |
| 代理/网关友好度 | 高(就是 HTTP) | 需要额外配置 Upgrade |
| 典型场景 | 进度推送、通知、LLM 输出流 | 聊天室、协同编辑、游戏 |

用第 1 课学过的"杀鸡用牛刀"判据来审这个场景:进度推送是**纯单向下行**——客户端的全部输入(城市、天数、偏好)在建立连接时一次性带上即可,连接建立后客户端不需要再说什么。WebSocket 的双向能力在这里是纯开销,还额外背上"独立协议、代理配置、自己实现重连"三座山。**结论:SSE。** 顺带一提,各家 LLM API 的流式输出(Chat Completions 的 `stream=true`)走的也是 SSE,你第 5 课看过的接口日志里可能已经有它的身影——这是业界已经用脚投票的场景。

---

## 1.3 SSE 协议本体:报文长什么样

第 10 课你手动发过一条 JSON-RPC 看 MCP 协议本体;现在用同样的方法论看 SSE。一条 SSE 流就是若干"事件块"拼成的纯文本,**每个事件块由若干行组成,块与块之间用空行分隔**:

```
event: step
data: {"stage": "attractions", "message": "开始搜索景点", "ts": 1730000000}

event: step
data: {"stage": "weather", "message": "开始查天气", "ts": 1730000005}

event: plan
data: {"city": "北京", "days": [...]}

```

格式规则(记这四条就够):

1. 每行是 `字段名: 值`,常用字段只有三个:`event`(事件类型,缺省为 `message`)、`data`(载荷)、`id`(事件编号,配合自动重连的 `Last-Event-ID`);
2. **空行是事件边界**——解析器靠 `\n\n` 切分,所以 `data` 里不能有裸换行(把载荷做成单行 JSON 就天然安全);
3. 整个流的 `Content-Type` 是 `text/event-stream`;
4. 一个块可以有多行 `data:`,它们会被拼接——你不需要用这个特性,单行 JSON 更好解析。

---

## 1.4 FastAPI 的流式基建:StreamingResponse 与异步生成器

普通 FastAPI 路由是"算完 → 一次性返回";`StreamingResponse` 则接受一个**生成器**,框架边迭代边把产出的每个字符串作为一个 HTTP chunk 发出去——"边算边发"由此而来。最小可运行示例:

```python
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

async def demo_stream():
    for i in range(3):
        payload = json.dumps({"n": i}, ensure_ascii=False)
        yield f"event: step\ndata: {payload}\n\n"
        await asyncio.sleep(1)

@router.post("/demo/stream")
async def demo_stream_api():
    return StreamingResponse(
        demo_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

注意两个响应头:`Cache-Control: no-cache` 防止中间层缓存这个"永不结束的响应";`X-Accel-Buffering: no` 专门说给 nginx 听——别把我的 chunk 攒成一坨再发(第 30 课配 nginx 时还会再遇到它,那里是流式上线最常见的翻车点)。

用 curl 感受一下(每秒蹦出一条,而不是 3 秒后一次性全出):

```bash
curl -N -X POST http://localhost:8000/api/trip/demo/stream
```

`-N` 是 `--no-buffer`,关掉 curl 自己的接收缓冲——验证流式必须带它,否则你看到的"一次性输出"可能只是 curl 在攒。

---

## 1.5 核心设计:asyncio.Queue 桥接"规划任务"与"事件流"

真正的难点来了:`plan_trip` 是一个**整体函数**,它不会中途 yield。而 StreamingResponse 的生成器又必须"边算边产"。怎么把两者接起来?答案是经典的**生产者-消费者桥**:

```
plan_trip(生产者) --emit()--> asyncio.Queue(桥) --> 异步生成器(消费者) --> StreamingResponse --> 浏览器
```

生产者是规划流程本身:在关键节点调用 `emit(stage, message)`,把事件塞进队列,然后继续干活,**不等待**;消费者是响应生成器:不断 `queue.get()`,拿到什么就 yield 什么,直到收到哨兵(sentinel)结束事件。

### 第一步:给 plan_trip 插上 emit 回调(可选参数,不破坏旧接口)

给 `plan_trip` 增加一个可选的 `emit` 参数,默认 `None`——**旧的一切行为保持不变**(这是第 26 课的兼容性红线):

```python
# trip_planner_agent.py,plan_trip 签名改为:
def plan_trip(self, request, emit=None):
    def report(stage, message, **extra):
        if emit:
            emit({"event": "step",
                  "data": {"stage": stage, "message": message, **extra}})

    # 步骤1 前: report("attractions", "开始搜索景点…")
    # 三路并行完成(第 11 课的 asyncio.gather 返回)后:
    #   report("attractions", f"景点完成 {n} 个结果")
    #   report("weather", "天气完成")
    #   report("hotel", "酒店完成")
    # 步骤4 前: report("planner", "开始生成计划…")
    # 解析成功后: report("planner", "计划生成完成")
```

插桩位置对照(以你并行化后的版本为准,行号基于改造前的 main):三路 `gather` 的前后、`planner_query` 构建前(262 行)、`_parse_response` 成功后(267 行)、以及 `275-279 行`的异常分支(发 `error` 事件,呼应第 14 课"诚实报错"——**失败也要流式地告诉用户,而不是让连接沉默地断掉**)。

> 如果你第 11–12 课把 `plan_trip` 改成了 `async def` 且跑在事件循环里,`emit` 里直接 `queue.put_nowait(...)` 即可(同一线程,不会阻塞)。但如果 `plan_trip` 仍以同步方式跑在线程池(`run_in_executor`)里,**必须**用 `loop.call_soon_threadsafe(queue.put_nowait, event)` 跨线程投递,否则会出现"事件永远躺在另一个线程的队列里"的诡异静默。这是本课最容易踩的异步坑。

### 第二步:路由层把队列变成响应流

在 `backend/app/api/routes/trip.py` 新增端点(与现有 `POST /plan` 平级,**保留旧接口**——接口退役是渐进的,不是替换):

```python
import asyncio, json
from fastapi.responses import StreamingResponse

@router.post("/plan/stream", summary="生成旅行计划(流式)")
async def plan_trip_stream(request: TripRequest):
    queue: asyncio.Queue = asyncio.Queue()

    async def run_planning():
        try:
            agent = get_trip_planner_agent()
            plan = await agent.plan_trip_async(request, emit=queue.put_nowait)  # 你的异步版本
            await queue.put({"event": "plan", "data": json.loads(plan.model_dump_json())})
        except Exception as e:
            await queue.put({"event": "error",
                             "data": {"message": f"生成失败: {e}"}})
        finally:
            await queue.put({"event": "done", "data": {}})   # 哨兵:无论如何都要发

    asyncio.create_task(run_planning())

    async def event_stream():
        while True:
            event = await queue.get()
            if event["event"] == "done":
                yield "event: done\ndata: {}\n\n"
                return
            payload = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event['event']}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

读这段代码的三个要点:

1. **`asyncio.create_task` 让规划立刻开始**,不等生成器被迭代——否则第一个事件要等客户端来"要"才产生,时序就乱了;
2. **`finally` 里的哨兵是生命线**:任务半路抛异常、客户端中途断开,队列消费者都不至于永久 `await queue.get()` 挂死。这类"无论如何都要执行"的收尾,永远放 `finally`(第 9 课 ReAct 循环的最大轮数保护、第 13 课重试循环的上限,是同一种防御思维);
3. **队列是请求级局部变量**,每个请求各有一座桥,天然隔离,不存在并发串台——但注意底层 `agent` 是单例(第 2 课),多个流式请求并发时,MCP 工具与 LLM 的并发安全在第 12 课压测时你已经验过一遍,这次再用 curl 双开验证一次。

### 事件清单(实验要求实现的最小集合)

| event | 触发点 | data 示例 |
|---|---|---|
| `step` | 开始搜索景点 | `{"stage": "attractions", "message": "开始搜索景点"}` |
| `step` | 景点完成 | `{"stage": "attractions", "message": "景点完成 8 个结果"}` |
| `step` | 开始查天气 / 天气完成 | `stage: "weather"` |
| `step` | 开始查酒店 / 酒店完成 | `stage: "hotel"` |
| `step` | 开始生成计划 / 完成 | `stage: "planner"` |
| `plan` | 解析成功 | 最终 `TripPlan` JSON(单行) |
| `error` | 任何失败 | `{"message": "…"}` |
| `done` | 流结束哨兵 | `{}` |

`plan` 事件也可以**分段**发(比如按天拆成多条 `plan_day` 事件,前端边收边渲染)——体验更激进,实现也更复杂;实验先做"一条 `plan` 事件发整包",分段留作选做。

---

## 1.6 动手实验:实现 /api/trip/plan/stream

### 任务

实现上文的流式端点,并保留旧 `POST /api/trip/plan` 完全可用;用 `curl -N` 验证事件是**实时逐条**到达的。

### 步骤

1. 给 `MultiAgentTripPlanner.plan_trip` 加可选 `emit` 参数(见 1.5 第一步),四个步骤与异常分支插桩;若你的版本还没有异步化,先只发"阶段级"粗粒度事件(每个 `agent.run` 前后各一条),不影响本课主线;
2. `trip.py` 新增 `POST /trip/plan/stream`(见 1.5 第二步):队列 + `create_task` + 异步生成器 + 哨兵;
3. 先写一个 20 行的 `POST /trip/demo/stream` 最小示例(1.4 节代码)验证基础设施,再上真端点——**分层验证,别一上来就在真实链路里调 Bug**;
4. 用 `curl -N -X POST http://localhost:8000/api/trip/plan/stream -H "Content-Type: application/json" -d @request.json` 跑一次真实规划(`request.json` 从 `/docs` 的请求示例里抄);
5. 双开两个 curl 窗口同时请求,观察两个流是否互不干扰;
6. 中途 Ctrl+C 断开 curl,看后端日志:任务是否正常收尾、有没有报错刷屏。

### 完成标准

- [ ] `curl -N` 下 step 事件**逐条实时出现**,不是最后一次性吐出;
- [ ] (若已并行化)三个"开始"事件时间戳几乎相同,三个"完成"事件按真实完成顺序交错到达;
- [ ] `plan` 事件的 data 能被 `python -c "import json,sys; json.loads(sys.stdin.read())"` 解析通过;
- [ ] 旧接口 `POST /api/trip/plan` 在 `/docs` 里照常工作,`/api/trip/plan/stream` 失败时发出 `error` 事件而不是静默断流;
- [ ] 一次请求的全程能在 loguru 日志里用 request_id 回放(第 19 课的基建在流式路径上没有失灵)。

### 常见卡点

- **"事件全部最后一次性到达,毫无流式感?"** 按顺序排查三层:① 生成器是不是 `async` 生成器(函数体里有没有 `yield`,是不是在生成器**外部**先把规划任务 `await` 完了);② 中间层缓冲(curl 忘了 `-N`;浏览器下看 Network 的 EventStream/Response 面板);③ 事件被 `await queue.get()` 之外的慢操作卡住(比如在生成器里做了同步 IO)。
- **"客户端断开后,`queue.get()` 永远挂着?"** 消费者应感知断连:客户端断开时 uvicorn 会终止对生成器的迭代(生成器被 GC/关闭),但**规划任务还在跑**——这正是 `finally` 哨兵存在的意义;更完整的做法是用 `request.is_disconnected()` 轮询或 `asyncio.wait_for(queue.get(), timeout=30)` 兜底。
- **"plan 事件里的中文变成 `\uXXXX`?"** `json.dumps` 默认 `ensure_ascii=True`。功能上没错(前端 `JSON.parse` 能还原),但 curl 调试时可读性差,按 1.5 的代码加 `ensure_ascii=False`。

---

## 1.7 课后作业与思考题

**必做:**

1. 完成实验,全部完成标准打勾;
2. 把一次真实规划的 curl 输出(含时间戳)存到 `docs/lesson26/stream-sample.txt`,并在旁边用 3 行话回答:并行化之后,事件的时间顺序证明了什么?

**选做(思考或动手):**

1. 给每个事件加 `id:` 行,并实现服务端在收到 `Last-Event-ID` 时跳过已完成步骤的恢复逻辑——想清楚:对"一次性规划任务",断线恢复真的值得做吗,还是"重试整次"更简单?
2. 实现心跳:每 15 秒没有真实事件就发一条 `event: ping`。想想它防的是什么(代理掐断空闲连接),以及前端解析时如何忽略未知事件类型(第 27 课马上会用到这个兼容性设计)。

## 下节预告

**第 27 课:流式消费与体验打磨(前端)。** 后端的事件流已经就绪,但浏览器原生 `EventSource` 发不了 POST——我们将用 `fetch + ReadableStream` 手写一个能处理"事件被 TCP 拆到两个 chunk"的 SSE 解析器,给 `Result.vue` 接上步骤时间线,并送走 `api.ts:8` 那个 2 分钟超时。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
