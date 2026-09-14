# 第 4 课:Python 异步编程基础

> 所属模块:模块一「打地基:读懂这个项目」(第 1–4 课)
> 预计时长:1.5–2 小时(实验只需一个 Python 环境,不要求后端在跑)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第 3 课:环境搭建与调试基本功](./第03课-环境搭建与调试基本功.md)

---

## 本课在课程中的位置

```
模块一 打地基   ← 你在这里(第 4 课)
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶
```

这是模块一的最后一课,补上读懂本项目最关键的一块语言知识:**异步**。你已经在第 2 课标红了那个位置——`trip.py:44` 在 `async def` 路由里同步调用 `agent.plan_trip()`,事件循环会被卡死。要理解这句话的每个词,就得理解事件循环;要修好它(第 12 课)并让三个 Agent 并行(第 11 课),就得会写 `asyncio`。本课学到的每个概念都会在两周内派上真实用场。

## 学习目标

完成本课后,你应该能够:

1. 解释事件循环、协程、`async`/`await` 三者的关系,以及"调用协程函数不会执行它"这个新手第一坑;
2. 正确使用 `asyncio.gather` 并发执行多个协程,并解释为什么总耗时约等于最慢的一个;
3. 说清协程、线程、进程的适用边界,以及 `time.sleep` 与 `asyncio.sleep` 的本质区别;
4. 在项目里准确指出"异步外壳包同步内核"的位置(trip.py:44 等),说明危害,并预告第 11、12 课的修复路线。

## 课前自检

- [ ] 第 3 课的虚拟环境可用(本课实验建议就用它的 Python);
- [ ] 见过 `trip.py:20` 的 `async def plan_trip` 和第 2 课标红的 44 行;
- [ ] 知道函数调用的基本模型(调用 → 执行 → 返回),不要求懂并发;
- [ ] 做好心理准备:异步的反直觉点很多,第一遍读不懂是正常的,实验跑一遍就通了。

---

## 1.1 为什么这个项目必须懂异步:时间都花在哪了

回顾第 2 课的数据流:一次规划 = 4 次串行 LLM 调用,而每次 LLM 调用内部还可能触发 MCP 工具调用高德 API。全程没有任何一步在做重计算——**时间全部花在"等网络"上**。

这类任务叫 **I/O 密集型**:CPU 利用率接近零,大部分时间进程处于等待状态。与之相对的是 CPU 密集型(如视频转码、Pydantic 解析大 JSON)。I/O 密集型任务有一个诱人的性质:**多个等待可以重叠**。等高德响应的 200 ms 和等 LLM 响应的 5 s 本可以同时发生,但第 2 课看到的四步是排队的。

异步就是 Python 重叠这些等待的标准答案。一个真实的对照:景点、天气、酒店三步各约需一次 LLM 往返(设 3 s),串行 9 s,并行约 3 s——第 11 课你会亲手把这个 9 s 变成 3 s。本课先在玩具模型上把原理吃透。

---

## 1.2 协程与事件循环:心智模型

先建立三个词的关系:

- **协程(coroutine)**:`async def` 定义的函数。它和普通函数的根本区别是**可以在中途暂停,把控制权让出去,稍后从暂停点恢复**。
- **事件循环(event loop)**:一个单线程的调度器,维护着"谁在等什么事件(定时器/网络响应)",谁的等待对象就绪了就恢复谁。它是异步世界的唯一执行者。
- **`await`**:暂停点。`await xxx` 意思是"我依赖 xxx 的结果,期间事件循环你可以去干别的"。

看最小可运行示例:

```python
import asyncio

async def hello():                 # async def 定义的是"协程函数"
    print("A")
    await asyncio.sleep(1)         # 暂停 1 秒,期间事件循环可以跑别的协程
    print("B")

asyncio.run(hello())               # 创建事件循环并驱动协程到结束
```

**新手第一坑:调用协程函数不会执行它。**

```python
hello()        # 只返回一个协程对象,函数体一行都没执行!
# RuntimeError: asyncio.run() cannot be called from a running event loop(若已在循环内)
# 另外你会看到 RuntimeWarning: coroutine 'hello' was never awaited
```

协程必须被 `await`(在另一个协程里)、被 `asyncio.run`(程序入口)或被 `asyncio.gather` 收走才有意义。"看起来调用了、其实没执行"是异步代码 90% 诡异 bug 的来源。

第二个关键认知:`await` 是**唯一的切换点**。两个 `await` 之间,代码是独占线程顺序执行的。这其实是好消息——协程里不需要考虑"半路被人插队"的竞态,比线程模型好推理得多。

---

## 1.3 串行与并发:asyncio.gather

把三个模拟请求(各 1 秒)先串行、再并发:

```python
async def fetch(name: str, seconds: float) -> str:
    await asyncio.sleep(seconds)          # 模拟一次网络等待
    return f"{name} 完成"

async def serial():                       # 串行:一个等完再下一个
    for name in ["景点", "天气", "酒店"]:
        await fetch(name, 1)

async def parallel():                     # 并发:三个一起挂起
    await asyncio.gather(
        fetch("景点", 1),
        fetch("天气", 1),
        fetch("酒店", 1),
    )
```

`serial()` 总耗时约 3 s;`parallel()` 约 1 s。`gather` 的执行模型:把三个协程全部交给事件循环,它们轮流挂起等待,谁的超时到了谁被恢复——**总耗时 ≈ 最慢的那个**,而不是求和。

关于 `gather` 的三条军规:

1. **结果有序**:`gather` 返回结果列表,顺序与传入顺序一致(与完成先后无关),所以"并发执行、按原顺序取结果"是安全的;
2. **异常默认一损俱损**:任一协程抛异常,`gather` 立即把它抛给你,其余协程仍在后台跑完(但结果拿不到了);想"谁失败就收谁的错误、其他照常",用 `return_exceptions=True`;
3. **gather ≠ 并行加急**:它只是"同时挂起",如果每个协程内部有 CPU 重活或同步阻塞,并发优势立刻消失——见下一节。

---

## 1.4 协程 vs 线程 vs 进程

| 维度 | 协程(asyncio) | 线程(threading) | 进程(multiprocessing) |
|---|---|---|---|
| 调度方式 | 事件循环单线程,`await` 处主动让出 | 操作系统抢占式,随时可能切换 | 多个独立 Python 解释器 |
| 切换成本 | 极低(函数级) | 中(线程栈) | 高(进程隔离) |
| 被 GIL 限制? | 单线程,无所谓 | 是(CPU 计算无法并行) | 否(真并行) |
| 适用场景 | **I/O 密集 + 海量并发**(本项目) | 阻塞库的兼容层、旧代码 | CPU 密集 |
| 典型风险 | 一处同步阻塞,全盘皆卡 | 竞态、锁 | 内存开销、通信复杂 |

重点解释表格最后一列第一行——本项目的命门。对比两个 sleep:

```python
time.sleep(1)      # 同步阻塞:把整个线程钉住,事件循环也在这条线程上 → 所有协程陪葬
await asyncio.sleep(1)   # 异步挂起:仅本协程让出,事件循环继续调度别人
```

CPU 密集任务交给协程则不划算:计算时事件循环根本插不进手,协程退化成普通函数。**记住判据:等待多,用协程;计算多,用进程;被迫和阻塞库共存,用线程池兜底**(`run_in_executor`,第 12 课的修复手段之一)。

---

## 1.5 对照项目:地雷埋在哪,雷区有多大

现在用新知识回到项目。第 2 课标红的位置,现在可以完整读出它的含义了:

```python
# trip.py:20-44(节选)
async def plan_trip(request: TripRequest):     # async:声明自己会在等待时让出事件循环
    ...
    agent = get_trip_planner_agent()           # 40 行
    trip_plan = agent.plan_trip(request)       # 44 行:普通 def 方法,同步执行!
```

`plan_trip`(`trip_planner_agent.py:223`)是 `def` 定义的**同步方法**,内部四次 `self.xxx_agent.run(query)` 也都是同步调用(`SimpleAgent.run` 是框架的同步接口,框架源码不在本仓库——如何定位它,第 5 课 1.4 节会专门教方法)。同步调用不会 `await`、不会让出,**它执行的几秒到几十秒里,事件循环被完全霸占**。后果:

1. 同一进程内**所有其他请求全部停摆**——连 `/health` 都查不动(它们也在排队等这个循环);
2. 两个用户同时规划,第二个请求的等待时间 = 自己的全部耗时 + 第一个的全部耗时;
3. 前端 `api.ts:8` 的 2 分钟超时可能被别人"连坐"触发。

同样的模式不止一处:`map.py` 的三个路由(`search_poi` 23 行、`get_weather` 66 行、`plan_route` 105 行)都是 `async def` 调同步的 `amap_service` 方法;`amap_service.py` 内部用 `mcp_tool.run(...)`(71 行)同步等 MCP。**整条链路是"异步外壳、同步内核"。**

修复路线已经排好,不用你现在动手:

- **第 11 课**:景点/天气/酒店三步用 `asyncio.gather` 并行化——本课 1.3 节的玩具模型直接放大到生产代码;
- **第 12 课**:用并发压测复现"第二个请求被卡住",再用异步化或 `run_in_executor` 修复,压测验证。

本课你要做的,是把 1.1 节架构图上的那个红点,升级成一句你能解释清楚的话:**"async def 里跑同步阻塞代码,等于一个人占住整个餐厅的厨房。"**

---

## 1.6 写异步代码的三条纪律

1. **协程函数里禁止出现同步阻塞调用**:`time.sleep`、`requests`、同步的文件/DB 操作都不行——用 `asyncio.sleep`、`httpx.AsyncClient`、`aiohttp` 替代(后两者都已在 `requirements.txt:11-12` 里,第 17 课会系统对比);
2. **程序入口只有一个 `asyncio.run`**,且不能在已运行的事件循环里再嵌套一个(在 Jupyter 或框架托管的环境里写 `asyncio.run` 报错,就是这个原因);
3. **并发要收集,顺序要保住**:多个独立等待用 `gather` 一次收走,别手写循环里 `await` 逐个等(那是伪并发);需要结果按完成顺序处理时另有一套(`asyncio.as_completed`,第 11 课实战遇到再讲)。

---

## 2. 动手实验:串行 vs gather vs 被同步拖垮的循环(本课核心任务)

### 任务

手写三个模拟网络请求,分别用串行和 `asyncio.gather` 执行并对比耗时;再模拟一次"async def 路由调同步函数",亲眼看事件循环被卡。这个脚本就是第 11、12 课改造前的"理论基准线"。

### 步骤

1. 新建 `docs/lesson04_async_demo.py`(不依赖项目包,任何 Python 3.10+ 均可运行),内容如下:

```python
"""第 4 课实验:串行 vs asyncio.gather vs 被同步代码拖垮的事件循环"""
import asyncio
import time


def fake_plan_trip():                # 模拟项目里的同步 agent.plan_trip(trip_planner_agent.py:223)
    time.sleep(1)                    # 同步 sleep:钉死整条线程(对照 fetch 里的 asyncio.sleep)


async def fetch(name: str, seconds: float) -> str:   # 模拟一次网络请求(LLM/高德)
    await asyncio.sleep(seconds)                     # 异步挂起:让出事件循环
    return f"{name} 完成"


async def serial():                  # 场景1:串行,即 plan_trip 今天的四步
    for name, sec in [("景点", 1), ("天气", 1), ("酒店", 1)]:
        await fetch(name, sec)


async def parallel():                # 场景2:gather 并行,即第 11 课改造后的三步
    await asyncio.gather(
        fetch("景点", 1),
        fetch("天气", 1),
        fetch("酒店", 1),
    )


async def blocked_request():         # 场景3:模拟 trip.py:20 的 async def 路由
    fake_plan_trip()                 # 没有 await——事件循环在这里被卡 1 秒
    return "完成"


async def two_requests():            # 两个用户同时请求
    return await asyncio.gather(blocked_request(), blocked_request())


if __name__ == "__main__":
    t0 = time.perf_counter(); asyncio.run(serial())
    print(f"串行三步:      {time.perf_counter() - t0:.2f}s   (预期约 3s)")

    t0 = time.perf_counter(); asyncio.run(parallel())
    print(f"gather 并发:    {time.perf_counter() - t0:.2f}s   (预期约 1s)")

    t0 = time.perf_counter(); asyncio.run(two_requests())
    print(f"两个'请求'撞上同步阻塞: {time.perf_counter() - t0:.2f}s   (预期约 2s——这就是第 12 课要修的 Bug)")
```

2. 运行(用第 3 课的虚拟环境 Python 也行):

```bash
python docs/lesson04_async_demo.py
```

3. 修改参数做二阶观察,每次只改一处:
   - 把场景 2 的三个耗时改成 3/1/1,验证"总耗时 ≈ 最慢者"而非"平均值";
   - 在 `fetch` 内部加一句 `time.sleep(0.5)`,再看场景 2 耗时——体会"协程里混入同步阻塞,并发优势蒸发";
   - 给 `gather` 加 `return_exceptions=True`,并让一个 `fetch` 抛异常,观察两种写法的行为差异。

### 完成标准

- [ ] 三行耗时输出与预期一致(约 3s / 约 1s / 约 2s),且能口头解释每一个数字的来历;
- [ ] 二阶观察三组结果都已记录;
- [ ] `docs/lesson04-notes.md` 写下两条结论:(a) 为什么本项目三 Agent 该用 gather 并行;(b) `trip.py:44` 的阻塞用一句话向非程序员解释;
- [ ] 对第 11 课写下你的耗时预测(当前后端实测一次规划的总秒数 × 你的并行化预期)。

### 常见卡点

- **"`RuntimeWarning: coroutine ... was never awaited`?"** —— 调用了协程函数却没 `await`/`run`/`gather`,函数体根本没执行。回到 1.2 节的第一坑。
- **"场景 2 耗时不是 1 秒出头?"** —— 检查是否手滑写成了循环里 `await`(伪并发);确认三个协程是在同一次 `gather` 调用里交出去的。
- **"场景 3 理论上应该是 1 秒,怎么真成 2 秒了?这不是更糟吗?"** —— 恰恰是重点:两个请求在**单个事件循环**里本可以重叠,却被同步调用强制排队。真实项目里这 1 秒是几十秒,排队的是几十个用户——这正是第 12 课压测会看到的形状。

---

## 3. 课后作业与思考题

**必做:**

1. 实验三场景全部跑通,`docs/lesson04-notes.md` 完成两条结论 + 耗时预测;
2. 把项目里所有"async def 调同步函数"的位置列成清单(trip.py 一处,map.py 三处),存入笔记——第 12 课按单施工;
3. 在第 1 课架构图上,给 `trip.py:44` 与三次 `agent.run` 补上"同步阻塞"标注,完成模块一里程碑的阻塞点要求。

**选做(思考,不用交):**

1. 把 demo 里的假请求换成真请求:用 `httpx.AsyncClient` 并发请求三次 `https://httpbin.org/delay/1`,对比串行——`httpx` 已在 `requirements.txt:11`,这是第 17 课的预习;
2. 读一读学习建议.md 第 130 行给出的 FastAPI 异步官方文档("Concurrency and async / await"),提前回答:FastAPI 对 `def` 路由会怎么处理?(它不会卡循环——为什么?第 12 课揭晓)
3. 如果三个 Agent 并行了,"步骤 4 必须等前三个"仍然成立——流水线的最短理论耗时由什么决定?

---

## 🏁 模块一里程碑(第 1–4 课收官)

到本课为止,模块一的知识点全部就位。按大纲要求,完成你的**"请求生命周期"手绘图**(画在纸上拍照或用 excalidraw,存入 `docs/`),硬性要求:

- [ ] 四层 + 8 个请求站点(第 2 课 1.1 节的表)全部在图上;
- [ ] 至少标出 2 个数据格式转换点(如 Dayjs→字符串、字符串→TripPlan);
- [ ] 阻塞点(`trip.py:44`)+ Bug 位置(`trip.py:78-79`)用醒目颜色标出;
- [ ] 对附录 B"模块一后"的自检问题(大纲 247 行)能不看笔记回答。

下个模块起,我们进入 Agent 的心脏:先拆开 LLM 调用本身。

## 下节预告

**第 5 课:LLM API 基础。** 剥掉 hello-agents 框架的外壳,直视 Agent 的大脑——一次 OpenAI 兼容的 HTTP 调用:messages、角色、temperature、token 计费;精读全项目最短的模块文件 `llm_service.py`,并学会一套"定位框架源码"的通用方法。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
