# 第 17 课:外部服务集成与 HTTP 客户端

> 所属模块:模块四「服务层与数据质量」(第 15–18 课)
> 预计时长:1.5–2 小时(含动手实验;实验建议新建一个干净的虚拟环境来复现 ImportError)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第 16 课:地理数据进阶——把真实世界接进规划](./第16课-地理数据进阶-把真实世界接进规划.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量   ← 你在这里(第 17 课)
模块五 工程化
模块六 产品化与进阶
```

前两课你补完了服务层的功能。本课换一个视角:**不看功能,看"每一通外部电话打得专不专业"。** 打电话的四个要素——超时(timeout)、重试(retry)、退避(backoff)、错误分类——决定了你的服务在网络抖动面前是"抖一下就恢复"还是"直接瘫掉"。

本课还有个彩蛋:你在验证理论的过程中会抓到一个**真实的依赖缺失 Bug**——`requirements.txt` 里根本没有 `requests`,但代码 import 了它。这不是编造的教学案例,是你自己项目里的真问题,本课的实验之一就是在新环境里亲手触发它。

## 学习目标

完成本课后,你应该能够:

1. 列出全项目 5 处外部调用及其超时/重试现状,指出哪些是"裸奔";
2. 说清 `requests` 与 `httpx` 的核心差异,以及本项目为什么应该用 httpx;
3. 把错误分成"可重试"与"不可重试"两类,并实现指数退避重试;
4. 亲手复现并修复"依赖未声明"的 ImportError,理解"能跑 ≠ 依赖正确"。

## 课前自检

- [ ] 你记得第 12 课"async def 路由里跑同步代码会卡死事件循环"的结论;
- [ ] 你的后端虚拟环境能正常启动(本课会另建一个干净环境做对照实验);
- [ ] 你用过 `pip show 包名` 查看某个包的信息(本课会用,没用了也没关系,步骤里给命令);
- [ ] 第 15 课改过的 `unsplash_service.py` 相关路由(`GET /api/poi/photo`)还没动过。

---

## 3.1 全项目的外部世界盘点:谁在跟谁打电话

先把项目里所有"出网"的调用列成一张表(这张表本身就是本课实验的产出,现在先建立全貌):

| # | 外部依赖 | 发起位置 | 客户端 | 超时 | 重试 |
|---|---|---|---|---|---|
| 1 | LLM API | `llm_service.py:24`(`HelloAgentsLLM()`) | 框架内部实现 | 由框架读取环境变量,`backend/.env.example` 里有 `LLM_TIMEOUT=60`(注释:默认60秒) | 未知,待到 hello-agents 源码确认 |
| 2 | 高德 MCP server | `trip_planner_agent.py:168-175`、`amap_service.py:28-34`(`uvx amap-mcp-server` 子进程) | MCP stdio 通道 | 未知 | 未知 |
| 3 | Unsplash API | `unsplash_service.py:35`(`requests.get`) | 同步 `requests` | `timeout=10` | **无** |
| 4 | 高德 JS API | `frontend/src/views/Result.vue:792`(`AMapLoader.load`) | 浏览器端 SDK | 浏览器默认 | 无(第 25 课展开) |
| 5 | 你自己的后端 | `frontend/src/services/api.ts:8` | Axios | `timeout: 120000`(2 分钟) | 无(第 27 课会改) |

看表的方法:每一行问三个问题——**超时了吗?会重试吗?重试的是对的错误吗?** 表里只有第 3 行是本仓库内可以直接改造的 HTTP 调用,它是本课的主角;第 1、2 行的配置点在框架里,本课只教你定位方法(见 3.6 步骤 4),严禁编造框架行为。

## 3.2 精读 `unsplash_service.py`:一个"三无"服务

打开 `backend/app/services/unsplash_service.py`,全文 87 行,核心是 35–36 行:

```python
response = requests.get(url, params=params, timeout=10)
response.raise_for_status()
```

它的三个问题,由轻到重:

**问题一:同步阻塞。** 它的唯一调用方 `GET /api/poi/photo`(`poi.py:89-128`)是 `async def`,却在 105–112 行直接调用这个同步方法——正是第 12 课压测复现过的"卡死事件循环"模式。图片搜索一慢,整个后端的所有请求都陪着等。

**问题二:零容错。** 没有 `try` 以外的任何保护:`timeout=10` 是唯一的盾牌,超时或一次网络抖动直接抛异常,被 54–56 行的 `except` 捕获后返回 `[]`——用户看到的是"没图",却不知道是"真没图"还是"网络抖了一下"。对 GET 这种**幂等**操作,重试是几乎零成本的收益。

**问题三:依赖未声明(下一节的真问题)。** 第 3 行 `import requests`,但这个包不在项目依赖清单里。

顺带说一句它的优点:`timeout=10` **有**——很多真实项目连这个都没有;`raise_for_status()` **有**——4xx/5xx 会被转成异常而不是静默读 body。本课改造是在这些正确做法上叠加,不是推倒重来。

再看它的调用方(`poi.py:104-112`),确认问题一的现场:

```python
unsplash_service = get_unsplash_service()

# 搜索景点图片
photo_url = unsplash_service.get_photo_url(f"{name} China landmark")

if not photo_url:
    # 如果没找到,尝试只用景点名称搜索
    photo_url = unsplash_service.get_photo_url(name)
```

注意一个隐藏细节:最坏情况下这里会**串行发两次 HTTP 请求**(第一次没图,换关键词再来一次),每次最长 10 秒——也就是说这个 `async def` 路由最坏要同步阻塞事件循环约 20 秒。改造后这两次调用依然串行(第二次依赖第一次的结果,没法并行),但阻塞问题会消失。

## 3.3 本课的真实发现:`requirements.txt` 里没有 `requests`

动手验证(三步,都在仓库根目录执行):

```bash
# 1. 代码里谁在用 requests?
grep -rn "requests" backend/app --include="*.py"
#    → 只有 backend/app/services/unsplash_service.py 的第 3 行和第 35 行

# 2. 依赖清单里声明了吗?
grep -n "requests" backend/requirements.txt
#    → 什么都没有。第 10-12 行的"HTTP客户端"一节只有 httpx 和 aiohttp

# 3. 当前环境里它从哪来的?
pip show requests
#    → 看输出里的 "Required-by" 字段
```

第 3 步通常会揭示真相:**`requests` 是作为其他包的传递依赖被顺带装上的**——本项目的依赖清单里有 `huggingface_hub`(`requirements.txt:29`),它声明了 `requests` 作为自身依赖,于是你的环境"碰巧"有它。用 `pip show huggingface_hub` 看 `Requires` 字段可以确认这条链。

所以现状是:`pip install -r requirements.txt` 之后项目**多半能跑**,但这是**运气,不是设计**。什么时候会爆?——任何一个环节断了:未来某个版本 `huggingface_hub` 换掉 HTTP 库;你用 `pip install --no-deps` 精简安装;或者按本课实验的方式,装一个不带传递依赖的环境。爆的时候就是一行:

```
ModuleNotFoundError: No module named 'requests'
```

而且爆点很刁:导入链是 `api/main.py` → `routes/poi.py:7`(`from ...services.unsplash_service import get_unsplash_service`)→ `unsplash_service.py:3`(`import requests`)——**服务一启动就炸,连接口都进不去**。

**教训只有一句话:import 了什么,就必须在依赖清单里声明什么;"现在能跑"只说明传递依赖还没变卦。** 修复有两条路:往 `requirements.txt` 加 `requests`,或改用已声明的 `httpx`——本项目选后者,理由见下一节。

## 3.4 `requests` vs `httpx`:为什么选后者

| 维度 | requests | httpx |
|---|---|---|
| 同步 API | 有 | 有(`httpx.Client`) |
| **异步 API** | **无**(asyncio 生态用 aiohttp) | **有**(`httpx.AsyncClient`),且与 requests 的 API 高度相似,迁移成本低 |
| 超时粒度 | 单值 | 可分 `connect` / `read` / `write` / `pool` |
| 连接池复用 | Session | AsyncClient(异步下复用更重要:省 TLS 握手) |
| 项目现状 | 未声明(3.3 的坑) | **已在清单里**(`requirements.txt:11`) |

本项目选 httpx 的三个理由:已声明(零新增依赖)、原生异步(和模块三的全异步方向一致)、API 几乎是"requests 的镜像",迁移基本就是改 import。

对照着看,同一次请求在两个库里长什么样:

```python
# requests(现在的写法,unsplash_service.py:35)
response = requests.get(url, params=params, timeout=10)

# httpx 异步(目标写法)
import httpx
async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
    response = await client.get(url, params=params)
```

`httpx.Timeout(10.0, connect=5.0)` 的含义:总超时 10 秒,但建立 TCP/TLS 连接最多给 5 秒——**连不上和等响应是两种病,分开计时才好诊断**。

## 3.5 超时、重试与指数退避:错误分类学

重试不是万能药,**重试错对象比不重试更糟**。第三方 API 的错误分两类:

| 类别 | 典型形态 | 该做什么 |
|---|---|---|
| **可重试** | 超时、连接被重置(`httpx.TimeoutException` / `TransportError`)、**5xx**(对端自己病了)、**429**(限流,通常带 `Retry-After` 响应头) | 指数退避后重试,封顶 3 次左右 |
| **不可重试** | **4xx**:`401`(key 错)、`404`(参数错)、`422`(请求格式错) | 立刻失败——重试一百次结果一样,只会烧配额、拖慢响应 |

429 特殊:它是"可重试的 4xx",且尊重 `Retry-After` 头是最礼貌的做法。

**指数退避(exponential backoff)**:第 n 次重试前等 `base × 2^n` 秒(0.5 → 1 → 2 → 4…),再叠加随机抖动(**jitter**),避免大量客户端在同一时刻整齐划一地重试、把刚恢复的服务又打垮。一个可直接用的实现:

```python
import asyncio
import random
import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

async def get_with_retry(client: httpx.AsyncClient, url: str, params: dict,
                         max_retries: int = 3) -> httpx.Response:
    """带指数退避的 GET。仅对可重试错误重试;4xx 立刻抛出"""
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.get(url, params=params)
            if response.status_code < 400:
                return response
            if response.status_code in RETRYABLE_STATUS:
                last_error = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response)
            else:
                response.raise_for_status()   # 其余 4xx:不重试,直接炸
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_error = e                    # 超时/网络错误:可重试

        if attempt < max_retries:
            delay = 0.5 * (2 ** attempt) + random.uniform(0, 0.3)   # 退避 + jitter
            print(f"⚠️ 请求失败({last_error}),{delay:.1f}s 后进行第 {attempt + 1} 次重试")
            await asyncio.sleep(delay)

    raise last_error
```

最后一个纪律:**重试只对幂等操作免费**。GET 重试无副作用;但如果哪天你重试一个"下单/扣费"类 POST,可能造成重复扣款——那种场景需要幂等键(idempotency key),本课程里先记住分界线即可。

## 3.6 动手实验:复现 ImportError + 异步化改造 + 配置表(本课核心任务)

### 步骤

1. **复现真实发现**:新建一个干净虚拟环境,只装 `requirements.txt` 里的包,然后:
   - `python -c "import requests"` 观察结果——如果报 `ModuleNotFoundError`,Bug 坐实;如果不报,用 `pip show requests` 查 `Required-by`,找到是哪个"好心人"带进来的,把这条传递依赖链记进笔记。**两种结果都是有效结论,关键是把证据留档。**
2. **改写 `unsplash_service.py`**:
   - `import requests` → `import httpx`(保留 `requirements.txt` 不加 requests——改完代码后它就不需要了);
   - `search_photos` 改为 `async def`,内部用 `async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))` 发请求,走 3.5 的 `get_with_retry`;
   - `get_photo_url` 同步改异步(它只是 `search_photos` 的薄封装);
   - 保留原有的字段提取逻辑(42–51 行)和"失败返回 `[]` / `None`"的降级语义。

   改造后的 `search_photos` 骨架长这样(字段提取部分留给你自己填):

```python
import httpx
from typing import List, Optional

class UnsplashService:
    """Unsplash图片服务类(httpx 异步版)"""

    def __init__(self):
        settings = get_settings()
        self.access_key = settings.unsplash_access_key
        self.base_url = "https://api.unsplash.com"

    async def search_photos(self, query: str, per_page: int = 5) -> List[dict]:
        try:
            url = f"{self.base_url}/search/photos"
            params = {"query": query, "per_page": per_page, "client_id": self.access_key}
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                response = await get_with_retry(client, url, params)
            data = response.json()
            results = data.get("results", [])
            # ↓↓ 与原版 42-51 行相同的字段提取,原样保留 ↓↓
            ...
            return photos
        except httpx.HTTPError as e:
            print(f"❌ Unsplash搜索失败(重试耗尽): {e}")
            return []
```

   两个签名变化要注意:方法多了 `async`;异常类型从 `Exception` 收窄为 `httpx.HTTPError`——`get_with_retry` 重试耗尽后抛出的正是它(超时、连接错误、HTTP 状态错误都是它的子类),收窄后你不会误吞无关异常。
3. **改调用方**: `poi.py:108、112` 两处加 `await`;路由本身已是 `async def`,不用动。
4. **补齐配置表**:对 3.1 表格的第 1、2 行做"定位练习"——在 hello-agents 框架源码里搜 `LLM_TIMEOUT` / `timeout`、`MCPTool` 的 `run` 与进程管理,查到什么写什么,**查不到就写"未定位,线索:从 XXX 入口继续查"**。这份诚实比一个编造的"框架超时 30 秒"有价值一百倍。
5. **验证**:
   - 正常路径:`GET /api/poi/photo?name=故宫` 返回图片 URL;
   - 重试路径:临时把 URL 改成不存在的域名(触发超时),观察日志出现 3 次递增间隔的重试后才失败;
   - 不重试路径:把 `UNSPLASH_ACCESS_KEY` 改错(4xx),确认**立刻**失败、零重试。

### 完成标准

- [ ] 干净环境实验的结论与证据链(`pip show` 输出)记入 `docs/lesson17-external-calls.md`;
- [ ] `unsplash_service.py` 不再 import 任何未声明依赖,`grep -rn "requests" backend/app` 零命中;
- [ ] `/api/poi/photo` 在 `async def` 路由里全程 `await`,事件循环不再被阻塞(用第 12 课的双请求压测法感受);
- [ ] 日志能区分三种结局:成功 / 重试后成功 / 重试耗尽失败;
- [ ] `docs/lesson17-external-calls.md` 的 5 行配置表完整,框架相关的两行标注了定位线索而非编造数字。

### 常见卡点

- **"`await` 忘了加,日志里出现 `coroutine was never awaited`?"** —— `poi.py:108` 改了 `:112` 忘了改,是这次改造最高频的翻车点;Python 只会警告不会报错,图片悄悄变空。
- **"429 一直重试一直 429?"** —— 退避太短或没尊重 `Retry-After`;Unsplash 免费额度有限(以官方文档为准),演示用途本来就会撞墙,撞墙本身就是 429 重试的最佳观察样本。
- **"改造后 `get_photo_url` 在哪都返回 `None`?"** —— 八成是调用方没加 `await`(见上一条卡点),拿到的是 coroutine 对象,`if photos` 永远为假;也可能是 key 没配(4xx 直接失败)。看日志属于哪种。
- **"httpx 报 `Connect timeout` 而不是 `Read timeout`?"** —— 这正是超时分级的价值:连接超时多半是网络/代理问题,读超时才是对端慢。把两种超时分开记录,排查方向完全不同。

---

## 3.7 课后作业与思考题

**必做:**

1. 完成改造与验证,`docs/lesson17-external-calls.md` 落盘;
2. 回答并写进文档:如果 `GET /api/trip/plan` 在网关层被自动重试 3 次,会发生什么?这和你在 Unsplash 上加的 GET 重试是同一种问题吗?

**选做(思考,不用交):**

1. 给 `amap_service.py` 的 `mcp_tool.run` 调用套一层计时器,统计每类工具的耗时分布——第 18 课讨论缓存收益时,这些数字就是论据;
2. `httpx.AsyncClient` 每次请求都新建一个实例(本课为了简单)——它应该像 `get_llm` 一样做成单例吗?在 FastAPI 里正确的做法是什么?(提示:查 httpx 文档里 client 的生命周期与 FastAPI lifespan 的关系,这与第 21 课要修的 `@app.on_event` 会相遇)

## 下节预告

**第 18 课:缓存与成本控制。** 同一座城市的天气半小时内不会变,但你每次生成都真金白银地查一遍、调一遍 LLM。本课用 30 行代码给 MCP 查询加 TTL 缓存,给每次规划请求算出 token 消耗和估算成本——并给模块四画上里程碑句号。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
