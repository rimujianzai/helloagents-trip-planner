# 第 12 课:FastAPI 异步实战

> 所属模块:模块三「多智能体系统设计与实现」(第 11–14 课)
> 预计时长:1.5–2 小时(实验含多次真实规划调用,注意控制成本与限流)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第11课-多智能体编排模式.md](./第11课-多智能体编排模式.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排 ← 你在这里(第 12 课)
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶
```

第 11 课你把三路 Agent 并行化了,但改造还停留在脚本层。本课把它接进 Web 服务——然后你会撞上本项目埋得最深的一个坑:`async def` 路由里调用同步的 `agent.plan_trip()`,**一个请求就能卡死整个服务**。你将复现它、理解它、修复它、压测证明它被修复了。这一课的内容(学习建议阶段二的后半段)是这套课程里"原理—危害—修复—验证"链条最完整的一环。

## 学习目标

完成本课后,你应该能够:

1. 说清 `def` 与 `async def` 路由的本质区别:FastAPI 对二者走两条完全不同的执行路径;
2. 解释"同步代码阻塞事件循环"的原理,以及"阻塞"和"慢"的本质不同;
3. 用并发探针复现"一个规划请求卡死整个服务"的现象,修复后用同一探针验证;
4. 面对一段同步阻塞代码,能在"换异步库 / `asyncio.to_thread` / `run_in_executor` / 进程池"之间做出正确选型;
5. 说出 `lifespan` 相对 `@app.on_event` 的改进点(原理层面;完整迁移安排在第 21 课)。

## 课前自检

- [ ] 第 11 课的 `plan_trip_async`(`asyncio.gather` + `to_thread` 版)已作为新方法加入 `MultiAgentTripPlanner`,且计时数据完整;
- [ ] 你能解释"事件循环是单线程的,`await` 是主动让出控制权"(第 4 课);
- [ ] 你能从命令行启动后端并用 `/docs` 手工调用一次接口(第 3 课);
- [ ] 知道 `httpx` 已在 `requirements.txt` 里(本课实验的探针脚本要用它)。

---

## 12.1 一分钟复习:事件循环为什么怕"阻塞"

把事件循环想成**一个只有一名服务员的餐厅**:所有请求都由这位服务员接待。`await` 的含义是"我在等外部回应(网络/磁盘),先去接待下一位";而一段**同步阻塞**调用(不带 `await` 的网络请求、`time.sleep`、大计算)的含义是"服务员站在原地盯着这口锅,直到菜炒好"——期间没有任何人被接待。

两个词要分清:

- **慢**:只影响这一个请求,别人该多快还多快;
- **阻塞**:占用事件循环本身,整个服务里**所有**并发请求一起陪等。

第 11 课的三路并行解决的是"单个请求慢";本课要解决的是"单个请求拖垮所有人"。

## 12.2 def 与 async def:FastAPI 的两条隐藏路径

FastAPI 对两种路由声明执行完全不同的策略:

| 路由写法 | FastAPI 怎么执行它 | 会阻塞事件循环吗 | 并发来源 |
|---|---|---|---|
| `def` | 自动丢进**线程池**(AnyIO 实现,默认约 40 个工作线程) | 否(线程池未被耗尽时) | 线程 |
| `async def` | 直接跑在**事件循环**上,不进线程池 | 函数内**所有**同步长调用都会 | 协程——前提是内部真的在 `await` |

FastAPI 官方文档"Concurrency and async / await"一节专门警告过这件事,大意是:如果你被迫使用同步阻塞库,**就用普通 `def`**,FastAPI 会替你把它放到线程池;千万别写成 `async def` 再在里面调同步阻塞代码。

由此得出本课最重要的结论:**`async def` 不是性能开关,而是并发模型的选择。** `async def` + 内部纯同步 = 最差组合:占着事件循环,又没有任何 `await` 让出控制权。声明成 `def` 反而更安全。

## 12.3 精读:trip.py 里的一次"负优化"

打开 `backend/app/api/routes/trip.py`,看 14–44 行:

```python
@router.post(
    "/plan",
    response_model=TripPlanResponse,
    ...
)
async def plan_trip(request: TripRequest):        # ← 第 20 行:声明为异步
    ...
    # 获取Agent实例
    print("🔄 获取多智能体系统实例...")
    agent = get_trip_planner_agent()              # ← 第 40 行

    # 生成旅行计划
    print("🚀 开始生成旅行计划...")
    trip_plan = agent.plan_trip(request)          # ← 第 44 行:纯同步调用!
```

`agent.plan_trip()` 是我们第 11 课精读过的纯同步方法:4 个步骤串行,每步可能多轮 LLM 往返,总耗时几十秒到几分钟。而现在它被包在一个 `async def` 路由里,**直接跑在事件循环上**。

后果的时间线(单 worker 进程):

```
t=0s    请求A:POST /api/trip/plan 开始(事件循环开始被占用)
t=1s    请求B:GET /health 到达 ······ 排队,无人处理
t=1s    请求C:GET /docs 到达 ········ 排队,无人处理
t=60s   请求A 完成 → B、C 才被处理(B 的"耗时"显示为 59s,尽管它只需要 1ms)
```

讽刺的对照:如果第 20 行写成 `def plan_trip(request: TripRequest)`,FastAPI 会把它丢进线程池,`/health` 照常毫秒级响应——**当前写法比不写 async 更糟**。这不是代码作者的失误,而是"async 一定更快"的普遍误解:第 20 行的 `async def` 只在内部存在真正的 `await`(比如本课末尾我们要加的 `await asyncio.to_thread(...)`)时才有意义。

顺带一提:函数里那些 `print` 都是微秒级,不构成阻塞;阻塞主体就是第 44 行那一次同步调用(以及它内部四次 `agent.run()`)。

## 12.4 lifespan:@app.on_event 的继任者(原理速览)

打开 `backend/app/api/main.py`,第 35 和 60 行用的是这样的写法:

```python
@app.on_event("startup")      # ← 第 35 行
async def startup_event():
    ...

@app.on_event("shutdown")     # ← 第 60 行
async def shutdown_event():
    ...
```

FastAPI 已经**弃用** `on_event`,推荐 `lifespan`。它的动机不只是"换个 API":

- `on_event` 的启动逻辑和关闭逻辑是两个**互不相干的函数**,要共享状态(比如启动时建立的连接池、启动时拉起的子进程),只能塞模块级全局变量;
- `lifespan` 用一个带 `yield` 的异步上下文管理器把两者包在一起,`yield` 之前是启动、之后是关闭,`yield` 前定义的变量天然可用:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # —— 启动:相当于原 startup ——
    resource = create_something_expensive()
    yield                       # ← 应用整个运行期停在这一行
    # —— 关闭:相当于原 shutdown ——
    await resource.close()

app = FastAPI(lifespan=lifespan)
```

本项目 `startup_event` 目前只做配置打印与校验(main.py 43–52 行),暂时没有需要跨启动/关闭共享的资源,所以迁移收益不大——**完整迁移已排进第 21 课 Bug 狩猎清单第 4 项**,本课只要求你读懂写法与动机,不动 `main.py`。

## 12.5 同步代码异步化:一棵选型决策树

遇到一段同步阻塞代码,按顺序问:

```
这段代码是哪种阻塞?
├─ 有现成的异步实现可换?(requests → httpx,裸 SDK → Async SDK)
│    └─ 换异步库,直接 await(首选,零线程开销)
├─ 是外部框架的方法,改不了?(如 hello-agents 的 SimpleAgent.run)
│    └─ asyncio.to_thread(fn, *args) 桥接(第 11 课的做法)
├─ 是 CPU 密集计算?(加密、图像处理、大矩阵)
│    └─ 进程池 loop.run_in_executor(ProcessPoolExecutor, ...) —— 线程没用,GIL 挡着
└─ 需要精细控制线程数/专用线程池?
     └─ 显式 executor + run_in_executor(to_thread 的底层通用形态)
```

两点背景知识:

- `asyncio.to_thread` 是 Python 3.9+ 的便捷封装,内部就是"用默认线程池执行 `run_in_executor`";需要**限制并发上限**(比如最多同时 2 个 LLM 请求)时,才退到显式 executor;
- AnyIO 默认线程池约 40 个线程——对本项目绰绰有余,但不是无限,压测时别开几百路并发把自己绕进去。

对照本项目的三处同步调用:`agent.run()`(框架方法 → to_thread,第 11 课已做)、`unsplash_service.py` 的 `requests`(第 17 课换 httpx)、`amap_service.py` 的 MCP 查询(第 15 课)。本课只处理第一处。

---

## 12.6 动手实验:复现 → 修复 → 验证

实验采用课程一贯的三段式:先让坏现象**可重复**,再修复,再用同一把尺子证明修好了。

### 步骤 1:写并发探针,复现"第二个请求被卡住"

新建 `backend/probe_concurrency.py`:

```python
"""并发探针:观察规划请求进行中,其他请求是否被卡住
用法:先启动后端(cd backend && python run.py),另开终端运行 python probe_concurrency.py
"""
import asyncio
import time

import httpx

BASE = "http://localhost:8000"
PLAN_BODY = {
    "city": "北京",
    "start_date": "2026-10-01",
    "end_date": "2026-10-01",
    "travel_days": 1,
    "transportation": "公共交通",
    "accommodation": "经济型酒店",
    "preferences": ["历史文化"],
    "free_text_input": "",
}


async def timed(client, name, coro):
    t0 = time.perf_counter()
    resp = await coro
    print(f"{name:<14} 耗时 {time.perf_counter() - t0:6.1f}s  状态码 {resp.status_code}")
    return resp


async def main():
    # 超时放宽:规划可能耗时数分钟(对照前端 api.ts 第 8 行的 2 分钟超时)
    timeout = httpx.Timeout(300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 预热:首次请求含 uvx 拉起 amap-mcp-server,不计入数据
        print("预热请求(不计数据)...")
        await timed(client, "warmup-plan", client.post(f"{BASE}/api/trip/plan", json=PLAN_BODY))

        print("\n=== 复现:plan 进行中,/health 是否被卡住 ===")
        plan_task = asyncio.create_task(
            timed(client, "plan", client.post(f"{BASE}/api/trip/plan", json=PLAN_BODY))
        )
        await asyncio.sleep(1)  # 确保 plan 先进入服务端并开始占用事件循环
        await timed(client, "health", client.get(f"{BASE}/health"))
        await plan_task


if __name__ == "__main__":
    asyncio.run(main())
```

两个注意点:

- 探针用的是**全局 `/health`**(`main.py` 80–87 行,不碰 Agent)。别用 `/api/trip/health`——它有第 21 课才修的 Bug(第 78–79 行访问不存在的 `agent.agent` 属性,永远 503),混进来会污染观察;
- `await asyncio.sleep(1)` 是为了让 plan 先在服务端"跑起来",确保 health 是在事件循环被占用期间到达的。

**修复前预期**:`health` 的耗时 ≈ `plan` 总耗时 − 1s。一个"什么都不做"的接口陪跑了整整一次规划——这就是 12.1 说的"阻塞"与"慢"的区别,现在有了实测数字。

### 步骤 2:修复(两个方案都做,体会差异)

**方案 A(最小改动):路由内 to_thread。** `trip.py` 顶部加 `import asyncio`,第 44 行改为:

```python
trip_plan = await asyncio.to_thread(agent.plan_trip, request)
```

一行修复:`plan_trip` 整体进线程池,事件循环解放,`/health` 恢复毫秒级。但请求内部三步仍串行(第 11 课的并行化还没接进来)。

**方案 B(叠加第 11 课成果):换异步方法。** 第 44 行改为:

```python
trip_plan = await agent.plan_trip_async(request)
```

`plan_trip_async` 本身是协程,直接 `await`;它内部的三路 `to_thread` + `gather` 负责并行。两个层级的改造是**正交的**:A 解决"事件循环被占"(服务级),B 解决"单请求太慢"(请求级)。

### 步骤 3:压测验证 + 双请求并发

每改一版,重跑 `probe_concurrency.py`:修复后 `health` 应稳定在毫秒~几十毫秒级。再往探针里加一轮"两个 plan 同时发"(把 `plan_task` 写成 `asyncio.gather(两个 timed(...))`):

- 修复前:第二个 plan 完全排队,两份耗时 ≈ 2 × 单次;
- 修复后(方案 B):两个请求的三路分别并行,总耗时明显小于 2 × 单次(受线程池上限与 LLM 供应商限流约束,不会理想化地除以 2)。

### 完成标准

- [ ] `backend/probe_concurrency.py` 入库;
- [ ] 修复前的数据已记录:`health` 延迟 ≈ `plan` 耗时(填具体数字);
- [ ] 方案 A、方案 B 修复后 `health` 延迟均恢复毫秒级(两行数据);
- [ ] 双 plan 并发数据已记录(修复前 vs 修复后);
- [ ] 能口头回答:`async def` 路由里的同步调用,为什么不会被 FastAPI 的线程池救?(答:线程池只服务 `def` 路由;`async def` 跑在事件循环上,没有任何机制把它移出去)

### 常见卡点

- **Q:`health` 还是慢?** 三查:改动是否保存且 uvicorn `reload` 生效(终端有没有重载日志);探针是否用的全局 `/health` 而不是 `/api/trip/health`;预热是否做足(首请求含 MCP 进程拉起,混进数据会把结论带偏)。
- **Q:两个并发 plan 出现 LLM 限流或工具结果串台?** 与第 11 课 11.5 卡点同源:瞬时并发翻倍。生产上要加并发上限(第 18 课限流思想);实验阶段先降低并发,把现象记录在案。
- **Q:探针报 ReadTimeout?** `httpx.Timeout` 给足(脚本里的 300s);或者把 `travel_days` 降到 1。这也解释了前端为什么要设 2 分钟超时(`api.ts:8`)——慢是真实的产品问题。

---

## 12.7 课后作业与思考题

**必做:**

1. 选定最终方案(建议 B,叠加并行)落进 `trip.py`,commit 并在 message 里附压测数据;
2. 把方案 A/B 的探针数据整理进 `docs/lesson12-notes.md`,表格至少含:修复前 / 方案 A / 方案 B 三列,`health` 延迟与双 plan 总耗时两行;
3. 在笔记里用一句话写下判断标准:什么时候一个 FastAPI 路由应该声明成 `async def`?(参考答案方向:仅当函数体内存在真正的 `await` 且不包含同步长阻塞)

**选做(思考,不必交代码):**

1. 写一个 `async def` 探针路由,内部分别调用 `time.sleep(3)` 和 `await asyncio.sleep(3)`,用并发请求实测差别——亲手确认 12.2 的表格;
2. 思考:多开几个 uvicorn worker 能否替代本课修复?代价是什么?(提示:worker 之间内存不共享,单例 Agent 每个进程各建一份、各连各的 MCP;这个问题在第 26 课做 SSE 时会再遇到)
3. 给 `/health` 加响应耗时日志,把它留成长期观测点,记录一周内它的 p95 延迟。

## 下节预告

**第 13 课:结构化输出(上):解析与重试。** 服务不卡了,但规划 Agent 返回的 JSON 依然时好时坏:有时带 markdown 围栏,有时缺字段,有时温度带个"°C"。我们将精读 `_parse_response` 的三种 JSON 提取策略并找出它们的漏洞,然后手写一个 Instructor 风格的重试解析器,用 20 次真实生成把"输出稳定性"变成数字。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
