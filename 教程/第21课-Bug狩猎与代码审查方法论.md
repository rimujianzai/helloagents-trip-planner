# 第 21 课:Bug 狩猎与代码审查方法论

> 所属模块:模块五「工程化:从"能跑"到"能上线"」(第 19–24 课)
> 预计时长:2–2.5 小时(本课是模块五核心课;每个 Bug 都要完整走"复现→定位→修复→回归"四步)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第20课-自动化测试.md](./第20课-自动化测试.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化   ← 你在这里(第 21 课)
模块六 产品化与进阶
```

前两课给了你工具(日志、测试),本课教你**猎人自己的眼睛**。这个项目从第 2 课起就陆续暴露过一些真实 Bug——比如第 2 课你发现的那个"健康检查一调就 503"——它们一直躺在代码里等你。**本课先建立一套系统的代码审查方法论,然后用它逐个猎杀 4 个已知 Bug(每个都走完整的复现→定位→修复流程),再给每个修复配上第 20 课风格的回归测试,最后把经验沉淀成一份可复用的"Bug 狩猎复盘"清单存进 `docs/`。**

> 一个诚实的勘误:学习建议里说重复的"3."在规划提示词(约 319 行)——**实测它不在 `PLANNER_AGENT_PROMPT` 常量里,而在 `_build_planner_query` 的要求列表里(精确行号见 21.4)**。本课所有行号都以实测为准,这本身就是一次"先验证再相信"的示范。

## 学习目标

完成本课后,你应该能够:

1. 复述代码审查三步法(先读调用方、再核对契约、再追边界条件),并在真实代码上执行它;
2. 独立完成 4 个真实 Bug 的复现→定位→修复,理解每个 Bug 背后的"类型学"(契约失配/静默丢弃/文档漂移/依赖过时);
3. 为每个修复编写回归测试,让红灯变成绿灯并永远守住;
4. 输出一份个人化的 Bug 狩猎 checklist 存入 `docs/`。

## 课前自检

- [ ] `pytest -v` 全绿(第 20 课),你知道怎么给一个函数写参数化测试;
- [ ] 后端能启动,你知道怎么用 curl 或 `/docs` 打一个 GET 接口;
- [ ] 读过 `trip_planner_agent.py` 的 `__init__`(158–221 行),对 MultiAgentTripPlanner 的属性有印象;
- [ ] 第 6 课你精读过提示词,记得"提示词即合同"这句话。

---

## 21.1 方法论:审查代码的三步法

随机翻代码靠运气,系统审查靠流程。面对任何一段可疑代码,按固定顺序问三组问题:

**第一步:先读调用方。** 这段代码被谁调用?调用方**假设**它提供什么?(方法名、属性名、参数、返回值)很多 Bug 根本不在"出错的行"里,而在调用方与被调方的**想象错位**里——健康检查 Bug 就是典型:写 `agent.agent.name` 的人,想象了一个不存在的属性。

**第二步:再核对契约。** 调用方与被调方之间"约定"的形状,和真实定义一致吗?契约有三种载体:类型与属性(IDE 能查一半)、接口文档(README/**docstring**/`schemas.py`)、以及行为约定(提示词就是 LLM 的契约)。第 1 课你对比过 README 与代码的出入——那是文档契约漂移;本课的 Bug ② 是数据契约失配(前端允许多选,后端只取一个)。

**第三步:再追边界条件。** 空列表、单元素、最大值、非法值、并发——正常路径人人会测,Bug 藏在边界里。本项目三个现成的"边界重灾区":`preferences` 为空/多元素(281–292 行)、`travel_days` 的上下限(`schemas.py` 15 行 `ge=1, le=30`)、`_parse_response` 的各种畸形输出(第 13 课已系统排过)。

三步法的运用顺序也有讲究:**先跑后读**——先让 Bug 在你眼前复现,拿到第一手报错,再开始读代码。没有复现的"修复"都是猜。

下面四个 Bug,每个都按这个流程走。

## 21.2 Bug ①:健康检查永远 503

**复现。** 启动后端,然后:

```bash
curl http://localhost:8000/api/trip/health
# {"detail":"服务不可用: 'MultiAgentTripPlanner' object has no attribute 'agent'"}
```

日志里(第 19 课的战果)能看到完整堆栈。接口的存在意义就是"快速告诉我服务好不好",而它现在**必然**回答"不好"。

**定位。** 读 `backend/app/api/routes/trip.py` 69–85 行,问题代码在 73–79 行:

```python
async def health_check():
    try:
        # 检查Agent是否可用
        agent = get_trip_planner_agent()          # 73 行:拿到 MultiAgentTripPlanner

        return {
            "status": "healthy",
            "service": "trip-planner",
            "agent_name": agent.agent.name,        # 78 行:访问 .agent —— 不存在!
            "tools_count": len(agent.agent.list_tools())   # 79 行:同样不存在!
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")
```

**用三步法核对:** 第一步,73 行的调用方是 `get_trip_planner_agent()`,跳到 `trip_planner_agent.py` 422–429 行——返回 `MultiAgentTripPlanner` 实例。第二步,核对该类的真实属性:看 `__init__`(158–221 行),它创建了 `self.llm`、`self.amap_tool`、`self.attraction_agent`、`self.weather_agent`、`self.hotel_agent`、`self.planner_agent`(164–210 行)——**没有 `.agent` 这个属性**。`agent.agent` 抛 `AttributeError`,被 81 行的 `except` 捕获,转手变成 503。第三步,边界条件追问:这个 `except` 太宽了,它把"服务真的坏了"和"健康检查自己写错了"混成一团——这也是它潜伏至今没被发现的原因:报错太"像真的"。

**为什么审查能抓到它?** 因为第一步"先读调用方"的标准动作就是**对着被调方的类定义逐个核对属性访问**。IDE 的静态检查其实早就画了黄线,`python -m pyflakes` 或装个 linter 也能自动抓——工程化的重要一课:能自动化的检查不要靠肉眼。

**修复。** 报告真实的健康信息——四个 Agent 与各自工具数(`list_tools()` 是框架方法,仓库里 213–215 行本来就在用):

```python
@router.get("/health", summary="健康检查", description="检查旅行规划服务是否正常")
async def health_check():
    """健康检查"""
    try:
        agent = get_trip_planner_agent()
        return {
            "status": "healthy",
            "service": "trip-planner",
            "agents": {
                "attraction": len(agent.attraction_agent.list_tools()),
                "weather": len(agent.weather_agent.list_tools()),
                "hotel": len(agent.hotel_agent.list_tools()),
                "planner": len(agent.planner_agent.list_tools()),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"服务不可用: {str(e)}")
```

**一个值得停下来想的设计问题(选做深挖):** 健康检查调用 `get_trip_planner_agent()`,而它是单例 getter——第一次访问 `/health` 会**顺手初始化整个多智能体系统**(创建 LLM 客户端、拉起 uvx 子进程)。一个健康检查触发放大成本的副作用,合理吗?生产实践通常把"进程活着"和"依赖齐了"分成两个接口。想清楚后,你可以把修复改成只检查"单例是否已存在"的轻量版。

**回归测试**(`tests/test_bugfixes.py`,复用第 20 课的打桩手法,mock 掉单例 getter):

```python
from fastapi.testclient import TestClient
from app.api.main import app


class _StubSimpleAgent:
    def list_tools(self):
        return ["amap_maps_text_search"]


class _StubPlanner:
    attraction_agent = _StubSimpleAgent()
    weather_agent = _StubSimpleAgent()
    hotel_agent = _StubSimpleAgent()
    planner_agent = _StubSimpleAgent()


def test_trip_health_reports_agents(monkeypatch):
    from app.api.routes import trip as trip_routes
    monkeypatch.setattr(trip_routes, "get_trip_planner_agent", lambda: _StubPlanner())

    resp = TestClient(app).get("/api/trip/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["agents"]["attraction"] == 1
```

修复前跑它:红灯 503;修复后:绿灯。这条测试从此守住了"健康检查必须说实话"。

## 21.3 Bug ②:多偏好被静默丢弃

**复现。** 不用发请求,直接测纯函数(第 20 课必做作业里那条红灯测试):

```python
request = make_request(preferences=["历史文化", "美食"])
query = planner._build_attraction_query(request)
print(query)
# 请使用amap_maps_text_search工具搜索北京的历史文化相关景点。
# [TOOL_CALL:amap_maps_text_search:keywords=历史文化,city=北京]
#                    "美食"去哪了?
```

**定位。** `trip_planner_agent.py` 281–292 行,病灶在 284–288 行:

```python
keywords = []
if request.preferences:
    # 只取第一个偏好作为关键词
    keywords = request.preferences[0]      # 286 行:多选偏好在这里被砍掉
else:
    keywords = "景点"
```

前端 `Home.vue` 131–139 行的 checkbox 组允许用户勾选任意多个偏好,`schemas.py` 18 行的类型也是 `List[str]`——**数据契约明明是多值,实现却只取 `[0]`**,而且不报错、不记日志。这是最阴险的 Bug 类型:**静默丢弃**——结果看起来"正常",只是悄悄变差,用户永远不知道自己的选择被无视了。

**修复,但先看清下游协议。** 直接想到的写法是 `keywords = ", ".join(request.preferences)`——**这是错的**。回看 291 行:`[TOOL_CALL:amap_maps_text_search:keywords=...,city=北京]` 的参数是**按逗号分隔**的(第 7 课的文本协议),关键词里混入逗号会把 `city=北京` 挤进 keywords,把整条工具调用解析炸掉。高德 text search 的 `keywords` 参数支持用 `|` 分隔多个关键词(以高德官方文档为准,实验时在 `/docs` 里验证搜索结果是否确实包含两类 POI),这才是既尊重上游数据又尊重下游协议的修复:

```python
def _build_attraction_query(self, request: TripRequest) -> str:
    """构建景点搜索查询 - 直接包含工具调用"""
    prefs = [p.strip() for p in request.preferences if p and p.strip()]
    keywords = "|".join(prefs) if prefs else "景点"          # 多偏好用 | 连接
    query = (
        f"请使用amap_maps_text_search工具搜索{request.city}的{('、'.join(prefs) if prefs else '')}相关景点。\n"
        f"[TOOL_CALL:amap_maps_text_search:keywords={keywords},city={request.city}]"
    )
    return query
```

**回归测试**(第 20 课作业那条,现在扶正并扩展):

```python
@pytest.mark.parametrize("prefs,expected", [
    ([], "景点"),
    (["历史文化"], "历史文化"),
    (["历史文化", "美食"], "历史文化|美食"),
    (["历史文化", "美食", "购物"], "历史文化|美食|购物"),
])
def test_build_attraction_query_keeps_all_preferences(prefs, expected):
    planner = object.__new__(MultiAgentTripPlanner)
    query = planner._build_attraction_query(make_request(preferences=prefs))
    assert f"keywords={expected}," in query
```

## 21.4 Bug ③:要求列表里出现两个"3."

**复现。** 一样不花 token:

```bash
cd backend
grep -n "^\s*[0-9]\." app/agents/trip_planner_agent.py
```

逐行核对输出,你会发现 316–321 行的要求列表是这样的:

```
316	1. 每天安排2-3个景点
317	2. 每天必须包含早中晚三餐
318	3. 每天推荐一个具体的酒店(从酒店信息中选择)
319	3. 考虑景点之间的距离和交通方式        ← 第二个 "3."
320	4. 返回完整的JSON格式数据
321	5. 景点的经纬度坐标要真实准确
```

再次勘误:这对重复的"3."不在 `PLANNER_AGENT_PROMPT`(75–152 行,那里的"重要提示"是干净的 1–7),而在 `_build_planner_query` 的 `**要求:**` 列表——318 与 319 行。**为什么这类"提示词里的编号 Bug"值得和代码 Bug 平起平坐?** 第 6 课讲过:提示词是 LLM 的合同。条款编号错乱,模型引用"第 3 条"时就有歧义;重复编号也会稀释"每条约束都被认真对待"的暗示。工程上它还说明一个更普遍的问题:**模板是手写的,没有校验**——这正是它能存活到第 21 课的原因。

**修复**就是把 316–321 行重新编号为 1–6:

```python
**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 返回完整的JSON格式数据
6. 景点的经纬度坐标要真实准确
```

**回归测试**——提示词也能测(它只是个函数的返回值):

```python
import re

def test_planner_query_numbering_is_sequential():
    planner = object.__new__(MultiAgentTripPlanner)
    query = planner._build_planner_query(make_request(), "景点", "天气", "酒店")
    nums = [int(m) for m in re.findall(r"^(\d+)\. ", query, flags=re.M)]
    assert nums == sorted(nums) and len(nums) == len(set(nums)), f"编号错乱: {nums}"
```

**顺手的观察(选做):** "每天安排2-3个景点"这条约束在 `PLANNER_AGENT_PROMPT`(143 行)和 `_build_planner_query`(316 行)里**重复出现**——两处约束将来改成一处忘另一处,就是下一个 Bug。要不要收敛成单一来源?想清楚利弊,写进复盘。

## 21.5 Bug ④:已弃用的 @app.on_event

**复现。** 启动后端,盯着控制台第一屏:

```
DeprecationWarning: The on_event decorator is deprecated, and will be removed in a future version...
```

`backend/app/api/main.py` 第 35 行 `@app.on_event("startup")` 与第 60 行 `@app.on_event("shutdown")` 是 FastAPI 已弃用的生命周期写法(官方文档"Lifespan Events"一节明确建议迁移)。弃用不是"错了",而是"倒计时"——现在不修,将来升级 FastAPI 时它会在最糟糕的时刻炸掉。

**修复:迁移到 lifespan。** 新写法把"启动"和"关闭"放进同一个上下文管理器,`yield` 之前是启动逻辑,之后是关闭逻辑;`main.py` 38–57 行的启动体搬进 `yield` 前,63–65 行的关闭体搬到 `yield` 后:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:yield 前启动,yield 后关闭"""
    print("\n" + "="*60)
    print(f"🚀 {settings.app_name} v{settings.app_version}")
    print("="*60)
    print_config()
    try:
        validate_config()
        print("\n✅ 配置验证通过")
    except ValueError as e:
        print(f"\n❌ 配置验证失败:\n{e}")
        raise
    print("\n" + "="*60)
    print("📚 API文档: http://localhost:8000/docs")
    print("="*60 + "\n")

    yield                                    # ← 应用在此运行

    print("\n👋 应用正在关闭...\n")            # ← shutdown 逻辑


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于HelloAgents框架的智能旅行规划助手API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,        # ← 挂载点从装饰器变成构造参数
)
```

(记得删掉原来的 `startup_event`/`shutdown_event` 两个函数与两个 `@app.on_event`;第 19 课若已把 `setup_logging()` 放进 startup,一并搬进 `yield` 之前。)lifespan 相比 on_event 的实质好处:启动与关闭共享同一个作用域,可以自然地创建/释放资源(比如将来在这里起停数据库连接池),不再靠两个隔离的全局函数。

**回归测试**——TestClient 用 `with` 语法进入时会完整执行 lifespan:

```python
def test_lifespan_startup_runs():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "healthy"
    # 离开 with 时 shutdown 段也会执行——不抛异常即通过
```

**完成标准里再加一条人工验收:** 重启后端,启动日志不再出现任何 `DeprecationWarning`。

## 21.6 收官:回归保护与提交纪律

四个修复 + 四条回归测试都在 `tests/test_bugfixes.py` 里(加上第 20 课的存量测试)后:

```bash
pytest -v        # 必须全绿
```

提交纪律(这一课的工程化训练不止于代码):**一个 Bug 一个 commit,commit message 里写清"根因 + 修复 + 测试"**,例如:

```
fix(api): 健康检查访问不存在的 agent.agent 属性导致恒为 503

根因: 调用方想象的属性与 MultiAgentTripPlanner 真实属性不符
修复: 改为报告四个子 Agent 的工具数
测试: test_trip_health_reports_agents (回归保护)
```

这样将来 `git log` 就是本次 Bug 狩猎的完整档案。

## 21.7 动手实验:写一份 Bug 狩猎复盘

### 任务

完成 21.2–21.6 的全部四猎,然后把过程沉淀成模板文件 **`docs/lesson21-bug-hunt-checklist.md`**(这个模板以后每次改代码前都过一遍)。结构如下:

```markdown
# Bug 狩猎复盘 checklist

## 本次狩猎战果
| # | Bug | 类型 | 根因一句话 | 修复 | 回归测试 |
|---|-----|------|-----------|------|---------|
| 1 | /api/trip/health 恒 503 | 契约失配(属性) | ... | ... | ✅ |
| 2 | 多偏好被静默丢弃 | 契约失配(数据形状) | ... | ... | ✅ |
| 3 | 提示词编号重复 | 文档/合同漂移 | ... | ... | ✅ |
| 4 | on_event 已弃用 | 依赖过时 | ... | ... | ✅ |

## 三步法执行记录(挑一个最难的 Bug 回放)
- 先读调用方: 我先看了 ______,发现 ______
- 再核对契约: 我核对了 ______,契约说 ______,实现是 ______
- 再追边界: 边界条件 ______,现状是 ______

## 我的狩猎武器库(本次新增的规律)
- [ ] 属性访问先对着类定义核对一遍(或直接上 linter)
- [ ] 用户输入是 List 时,实现必须回答"取一个还是取全部"
- [ ] 手写模板(提示词/SQL/格式串)要有结构性校验
- [ ] 弃用警告(DeprecationWarning)当 Bug 修,不当背景噪音
- [ ] 宽 except 会把"自己写错"伪装成"服务坏了"

## 狩猎新目标(本次没来得及查的疑点)
- ...
```

### 完成标准

- [ ] 四个 Bug 全部"复现→定位→修复→回归"四步走完,`pytest -v` 全绿;
- [ ] 修复前每条回归测试**先红灯**验证过(先跑测试看它红,再修——证明测试真的在测这个 Bug);
- [ ] 四个独立 commit,格式符合 21.6;
- [ ] `docs/lesson21-bug-hunt-checklist.md` 完成并存档;
- [ ] `/api/trip/health` 手工验证返回 200,启动日志零 DeprecationWarning。

### 常见卡点

- **Q:修复后健康检查还是 503?** 看异常信息:如果是"LLM_API_KEY 未配置"或 MCPTool 初始化失败,那是**依赖真的坏了**——健康检查这次说了实话,它在暴露另一个问题,不是本 Bug 复发。
- **Q:`|` 连接关键词后搜索结果没变化?** 先确认请求真的发到了高德(看第 19 课日志里的原始响应);再查高德官方文档对多关键词的语法约定。若 `|` 不生效,备选方案是循环为每个偏好各发一次工具调用——代价是工具调用次数翻倍,把它当一道工程取舍题写进复盘。
- **Q:改了提示词,行号全变了,大纲/前课对不上?** 预期行为。课程行号基于 2026-09-11 的 main 分支,改完之后按语义(函数名、消息文本)定位即可——你正在经历"文档随代码漂移",这正是 21.1 契约一节的活教材。

---

## 21.8 课后作业与思考题

**必做:**

1. 完成四猎 + 复盘 checklist,存 `docs/lesson21-bug-hunt-checklist.md`;
2. 用三步法**再自主 hunting 一轮**:重新审视 `map.py` 147–162 行的健康检查(它访问了 `service.mcp_tool._available_tools`——一个下划线开头的私有属性,调用外部约定,算不算同类契约风险?)与 `unsplash_service.py` 的异常路径,找到几个算几个,走完四步流程。

**选做(思考,可动手):**

1. 给 `trip.py` 的 `/plan` 路由补一个"契约测试":断言响应体结构(`success/message/data` 三键)与 `TripPlanResponse` 定义一致——契约失配既然是最常见 Bug 类型,就应该在 API 边界上有一道专门的网;
2. 思考题:这四个 Bug 分别对应"契约失配 / 静默丢弃 / 合同漂移 / 依赖过时"。**哪一类在你的工作里最难在上线前发现?为什么?** 答案决定你以后的自动化投入方向(类型检查?契约测试?依赖扫描?)。

## 下节预告

**第 22 课:配置、安全与提示词注入。** Bug 猎完了,该看"被人打"的场景:三层 `.gitignore` 到底护住了密钥没有;CORS 到底在拦什么、为什么本项目的配置可以直接抄;以及本课程最刺激的实验——用一句"忽略以上所有指令"攻击你自己的规划 Agent,看它会不会背叛你。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
