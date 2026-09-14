# 第 28 课:Agent 评估:让"变好"可度量

> 所属模块:模块六「产品化与进阶」(第 25–30 课)
> 预计时长:1.5–2 小时(含动手实验;评测会消耗真实 LLM 额度)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第 27课-流式消费与体验打磨-前端](./第27课-流式消费与体验打磨-前端.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化
模块六 产品化与进阶   ← 你在这里(第 28 课)
```

12 周课程里你做过很多"变好"的断言:第 6 课改提示词后"JSON 合规率提升了"、第 8 课"原生 Function Calling 成功率更高"、第 13 课"重试解析器提高了一次通过率"、第 16 课"数据驱动排序减少了绕路"。**但这些证据全部是一次性的、局部的、不可复现的。** 本课把散落各处的临时实验固化成一套**可重复运行的评测体系**:固定的评测集、五个量化指标、一个评分脚本、一份自动生成的 markdown 报告。从此每次改动,你都能跑一条命令回答"到底变好了没有、变好了多少"。

## 学习目标

完成本课后,你应该能够:

1. 设计一份合格的评测集:输入多样性(城市 × 天数 × 偏好)与金标准的两种来源(规则型指标 + 人工抽检);
2. 说出五个指标的定义与算法:JSON 一次通过率、工具调用成功率(代理指标)、行程合理性抽检分、景点绕路率、成本与耗时;
3. 编写 `scripts/evaluate.py`:加载评测集 → 逐项调用 → 打分 → 输出 markdown 报告;
4. 建立"回归评估"工作流,并对课程至今的全部改造做一次总评,生成前后对比报告存入 `docs/`。

## 课前自检

- [ ] 第 14 课已完成:假数据 fallback 已换成诚实错误响应(若未完成,1.3 节会教你识别 fallback"指纹",评测照常可做);
- [ ] 第 16 课已把真实地理数据接进规划(绕路率指标依赖它;未完成也能用直线距离做近似基线);
- [ ] 第 18 课的 token 消耗日志已加(没有也不阻塞,耗时指标照常);
- [ ] 后端能跑,LLM Key 有一点余额——**评测花真钱**,先跑 3 个 case 试水;
- [ ] 仓库里 `pytest` 能通过(第 20 课的测试没被改坏)。

---

## 1.1 为什么"我觉得变好了"不算数

回想你做过的一次典型实验(第 6 课):改提示词 → 随手生成 5 次 → 数出 4 次合规 → 写下"80% 合规率"。这个实验至少有三个漏洞:

1. **样本不可复现**——5 次生成的输入是什么?没记录;下次换个输入,数字就变了;
2. **条件不可比**——改前 5 次、改后 5 次,LLM 本身就有随机性,4/5 和 5/5 的差异可能在噪声范围内;
3. **口径不统一**——"合规"这次指能解析,下次指字段齐全,第三次又指坐标正确。

评估体系要解决的正是这三件事:**固定输入(评测集)、固定口径(指标定义)、固定流程(脚本 + 报告)**。此后你的迭代闭环变成:

```
改动(提示词/代码/模型) → 跑评测 → 对比上一份报告 → 数据说话:保留 / 回滚
```

这就是业界说的**回归评估**(regression eval):把"Agent 质量"当成有测试保护的代码——第 20 课你为 `_parse_response` 建立了 pytest 回归保护,本课为 Agent 的**行为**建立同样的东西。两者层次不同:pytest 保护"逻辑没写坏",评测集保护"效果没有变差"。

---

## 1.2 评测集设计:输入多样性与金标准

评测集 = 一组**固定输入** + 每条输入的**期望属性**。注意:不是完整期望输出——旅行规划没有唯一正确答案,你无法写出"标准行程",只能写出"合格行程必须满足的性质"。

### 输入格式与多样性

在 `docs/eval/cases.json` 建评测集(这个目录和文件会被实验固化并入库):

```json
[
  {
    "id": "bj-3d-history",
    "note": "一线城市 + 单偏好",
    "request": {
      "city": "北京",
      "start_date": "2026-10-01",
      "end_date": "2026-10-03",
      "travel_days": 3,
      "transportation": "公共交通",
      "accommodation": "经济型酒店",
      "preferences": ["历史文化"],
      "free_text_input": ""
    }
  },
  {
    "id": "cs-1d-none",
    "note": "小城市 + 一日游 + 无偏好",
    "request": { "city": "长沙", "travel_days": 1, "...": "..." }
  }
]
```

多样性的三个维度要刻意覆盖(**10–15 条足够起步**,每条都是真金白银):

| 维度 | 覆盖什么 | 为什么 |
|---|---|---|
| 城市规模 | 一线 / 热门旅游 / 小城市 | POI 密度差异会暴露工具调用与排序问题 |
| 天数 | 1 / 3 / 5 天 | 1 天考验取舍,5 天考验"每天 2–3 景点"约束的持久性 |
| 偏好 | 无 / 单 / 多偏好 | `preferences[0]` 被静默丢弃的 Bug(第 21 课)就是靠多偏好 case 抓的 |

### 金标准怎么定:两条腿走路

**腿一:规则型指标(机器自动判分)。** 凡是能写成代码判定的性质:

- 返回可解析、结构合法(`days` 非空、每 `day` 含 `meals` 三餐);
- 天数与请求一致;日期连续且等于 `start_date` 起算;
- 每天 2–3 个景点(与 `PLANNER_AGENT_PROMPT` 第 143 行的约束对齐——**提示词里的每条"要求"都是潜在评测点**,这叫"提示词即合同"的验收侧);
- 景点带非零坐标,且坐标落在目标城市附近(用坐标围栏粗判,防"北京行程里混进上海经纬度");
- `budget` 存在且各项非负、`total` 约等于各项之和。

**腿二:人工抽检(1–5 分 rubric)。** 自动化判不了"看起来对不对":行程顺路吗?时间安排现实吗(上午故宫下午长城再回市区吃晚饭)?推荐的餐厅真实存在吗?给 3–5 分制 rubric(5 = 可以直接出发;3 = 大体可用但有明显瑕疵;1 = 存在事实硬伤),每轮评测抽 3–5 条 case 人工打分。**人的作用不是算分,是发现新失败模式**——人工看到的怪现象,往往能反哺成新的规则型指标。

> 评测集是"测量仪器",仪器本身也要版本管理:`cases.json` 入库;改动评测集就换版本号并重新跑一次基线——否则前后对比失去意义。

---

## 1.3 五个指标:定义、算法与陷阱

| # | 指标 | 定义 | 判定方式 |
|---|---|---|---|
| 1 | JSON 一次通过率 | 不经重试 / 不落 fallback 就成功返回合法 `TripPlan` 的比例 | 自动(响应 success + 无 fallback 指纹;有重试日志则区分"一次"与"重试后") |
| 2 | 工具调用成功率(代理) | 结果里能看到 MCP 数据痕迹的比例(天气非空、景点坐标真实) | 自动(代理指标,见下) |
| 3 | 行程合理性抽检分 | 人工 rubric 均分 | 抽检 |
| 4 | 景点绕路率 | 实际游览顺序路径长 / 贪心最短参考长 | 自动(haversine + 最近邻) |
| 5 | 成本与耗时 | 每案 wall time(+ token 成本,若有日志) | 自动 |

**指标 1 的陷阱:你怎么知道"一次通过"?** 评测脚本在 API 之外,看不到内部重试循环。两个办法:① 第 14 课之后失败是诚实报错(`ErrorResponse`,`schemas.py:201-205`),`success=false` 即失败,fallback 已死则无歧义;② 若你的仓库还留着 fallback,直接识别它的**指纹**——`_create_fallback_plan`(`trip_planner_agent.py:371-415`)生成的景点名固定是 `f"{request.city}景点{j+1}"`(391 行),坐标是公式化的 `116.4 + i*0.01 + j*0.005`(393 行)。脚本检测到该模式直接判"未通过"。**能被指纹识破的假数据,本身就是第 14 课"编造假数据不如诚实报错"的最好论据。**

**指标 2 为什么叫"代理指标"?** 工具调用发生在 Agent 内部的文本协议循环里(第 7 课),外部脚本看不见。但 MCP 数据会在结果里留下痕迹:`weather_info` 非空说明 `maps_weather` 调通了;景点坐标与真实 POI 吻合说明 `maps_text_search` 干了活。**看不见过程时,用"结果的痕迹"替代**——这是黑盒评测的常用手法,同时也逼你明白:想精确度量过程,就得靠第 19 课的日志体系(工具调用成功率可以从 loguru 日志里统计,作为代理指标的升级版)。

**指标 4,本项目最有含金量的指标,第 16 课成果的"验收官"。** 算法:

```
对每个 day:
  S_actual = 相邻景点(按返回顺序)两两 haversine 距离之和
  S_greedy = 从该天第一个景点出发,最近邻贪心重排后的路径长(近似下界)
  ratio = S_actual / S_greedy
绕路率 = 所有天的 ratio 平均
```

`ratio = 1.0` 说明顺序近乎最优;`> 1.5` 说明明显绕路。haversine(球面两点距离,第 16 课你已用过)代码十几行;最近邻贪心只需双重循环。**注意两个坑**:① 最近邻是近似最优不是精确最优,`ratio` 略小于 1(如 0.97)正常,把它理解为"参考线";② 它衡量"顺序合理性",不衡量"选点合理性"(选了三个都不该去的景点,顺序再顺也白搭——那归人工抽检管)。这正是第 16 课说的"以绕路程度衡量"数据驱动排序是否生效的量化出口。

---

## 1.4 scripts/evaluate.py:评测脚本骨架

新建 `scripts/evaluate.py`(依赖 `httpx`,已在 `requirements.txt:11`)。核心结构:

```python
"""Agent 评测:加载评测集 → 逐项调用 → 打分 → 输出 markdown 报告

用法:
  python scripts/evaluate.py --cases docs/eval/cases.json --tag baseline
  python scripts/evaluate.py --smoke 3        # 只跑前 3 条,省钱试水
"""
import argparse, json, math, time
from datetime import datetime
from pathlib import Path
import httpx

BASE_URL = "http://localhost:8000"

def haversine(a: tuple, b: tuple) -> float:
    """两点球面距离(米)"""
    lon1, lat1, lon2, lat2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((lat2-lat1)/2)**2
         + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)
    return 2 * 6371000 * math.asin(math.sqrt(h))

def detour_ratio(day: dict) -> float | None:
    """单日绕路率:实际顺序 / 最近邻贪心参考"""
    pts = [(a["location"]["longitude"], a["location"]["latitude"])
           for a in day["attractions"]]
    if len(pts) < 2:
        return None
    actual = sum(haversine(pts[i], pts[i+1]) for i in range(len(pts)-1))
    remaining, order, cur, greedy = pts[1:], [pts[0]], pts[0], 0.0
    while remaining:
        nxt = min(remaining, key=lambda p: haversine(cur, p))
        greedy += haversine(cur, nxt); cur = nxt
        remaining.remove(nxt)
    return actual / greedy if greedy > 0 else None

def is_fallback(plan: dict, city: str) -> bool:
    """识别 _create_fallback_plan 的指纹(未做第 14 课改造时防误判)"""
    names = [a["name"] for d in plan.get("days", []) for a in d["attractions"]]
    return bool(names) and all(n.startswith(city) and "景点" in n for n in names)

def score_case(case: dict, resp: dict, elapsed: float) -> dict:
    plan = (resp or {}).get("data") or {}
    days = plan.get("days", [])
    ratios = [r for d in days if (r := detour_ratio(d)) is not None]
    checks = {
        "json_ok":      bool(plan),
        "fallback":     is_fallback(plan, case["request"]["city"]) if plan else False,
        "days_match":   len(days) == case["request"]["travel_days"],
        "meals_ok":     all(len(d.get("meals", [])) >= 3 for d in days),
        "coords_ok":    all(a["location"]["longitude"] and a["location"]["latitude"]
                            for d in days for a in d["attractions"]),
        "weather_ok":   bool(plan.get("weather_info")),
        "budget_ok":    (plan.get("budget") or {}).get("total", 0) > 0,
    }
    return {"id": case["id"], "elapsed": round(elapsed, 1),
            "detour": round(sum(ratios)/len(ratios), 3) if ratios else None,
            **checks}

def main():
    args = argparse.ArgumentParser().parse_args()
    cases = json.loads(Path(args.cases).read_text("utf-8"))[: args.smoke or None]
    results = []
    for case in cases:
        t0 = time.time()
        try:
            resp = httpx.post(f"{BASE_URL}/api/trip/plan",
                              json=case["request"], timeout=300).json()
        except Exception as e:
            resp, _ = {}, print(f"[{case['id']}] 请求异常: {e}")
        results.append(score_case(case, resp, time.time() - t0))
    write_report(results, args.tag)   # 汇总各指标 → markdown,写 docs/eval/report-<date>-<tag>.md
```

三个工程要点:

1. **失败 case 也要记录**——单条请求 500 不能中断整轮评测(所以 `try/except` 包住请求),报告里它就是一行醒目的失败;
2. **支持断点续跑(选做)**:每完成一条就把结果追加到临时文件,重跑时跳过——评测跑到第 8 条欠费的感觉,你不会想体验第二次;
3. **报告要能与上一份对比**:`write_report` 读取 `docs/eval/` 下最近一份报告的汇总数字,并排输出"本次 / 上次 / 变化"三列。报告汇总长这样:

```markdown
# 评测报告 2026-09-11 (tag: v2-reflection)
| 指标 | 本次 | 上次(baseline) | 变化 |
|---|---|---|---|
| JSON 一次通过率 | 90% (9/10) | 70% | +20pp |
| 工具调用成功率(代理) | 100% | 60% | +40pp |
| 景点绕路率(均值) | 1.18 | 1.52 | ↓0.34 |
| 平均耗时 | 71s | 95s | ↓24s |
| 人工抽检分 | 4.2 (抽 5 条) | 3.0 | +1.2 |
```

---

## 1.5 回归评估的工作流:什么时候跑、跑多少

- **触发时机**:改提示词(第 6 课)、改解析器(第 13 课)、换模型 / 换供应商(第 5 课)、加新范式(第 29 课的 Reflection)——**凡是可能改变 Agent 行为的 diff**;
- **成本控制**:日常用 `--smoke 3` 冒烟(固定跑同 3 条,便于横向比较);周末 / 发版前跑全量。**同一份评测集 + 同一个模型温度设置**,前后对比才有意义;
- **报告归档**:`docs/eval/report-<日期>-<tag>.md`,tag 用改动语义命名(`baseline` / `parallel` / `reflection`)——三个月后你要能看懂每份报告对应哪个版本的代码;
- **诚实原则**:报告里写清环境(模型名、温度、日期)。评测数字脱离环境就是废纸。

---

## 1.6 动手实验:评测集 + 总评脚本 + 前后对比报告

### 任务

构建 10 城市 × 不同天数/偏好的评测集,写 `scripts/evaluate.py`,对课程至今的全部改造做一次总评,生成前后对比报告存 `docs/`。

### 步骤

1. 建 `docs/eval/cases.json`:10 条,覆盖至少 6 个城市、1/3/5 天、无偏好与多偏好(抄 1.2 节格式);
2. 写 `scripts/evaluate.py`(1.4 节骨架补全):`haversine`、`detour_ratio`、`is_fallback`、`score_case`、`write_report`(markdown 汇总 + 与上一份 diff),支持 `--smoke N` 与 `--tag`;
3. 准备"前"基线:优先用 git——改造前后的代码都在你的 commit 历史里,`git stash` 或 checkout 旧 commit(数据库/缓存不受影响的纯 Python 项目可以直接切)跑"改前"一轮,tag 记为 `baseline`;没有历史可切的话,以"当前版"为基线并明确记录;
4. `--smoke 3` 试水 → 全量 10 条跑完,确认 `docs/eval/` 出报告;
5. **人工抽检**:随机抽 3 条 case 的输出,按 1.2 节 rubric 打分,把分数和一句话理由写进报告;
6. 写 5 行结论:哪个指标最好?哪个最差、为什么?哪个最意外?(意外往往孕育下一课的改造点。)

### 完成标准

- [ ] `python scripts/evaluate.py` 一条命令产出完整 markdown 报告,存 `docs/eval/`;
- [ ] 报告含 5 个指标(人工抽检分标注"抽检 n 条");
- [ ] 至少完成一组"改前 vs 改后"对比(哪怕"改前"只能通过 fallback 指纹统计体现);
- [ ] 评测集与报告已入库,`.gitignore` 没有误伤 `docs/eval/`(根 `.gitignore:41` 的 `*.log` 之类规则检查一下);
- [ ] 你能不看笔记说出:五个指标里,哪两个是全自动的,哪两个需要日志/代理,哪个必须人。

### 常见卡点

- **"跑到一半 LLM 报 429 / 欠费?"** 先 `--smoke 3`;给脚本加请求间隔(`time.sleep(2)`)降低限流概率;实现断点续跑(1.4 节要点 2)。评测是长跑,不是冲刺。
- **"绕路率算出来 0.96,比 1 还小?"** 正常——最近邻是近似基线不是理论最优(1.3 节指标 4 的坑①)。别去"修"它,理解它。
- **"工具调用成功率(代理)是 0,天气全空?"** 分层定位,别急着怪 Agent:先手动 `curl /api/map/weather`(第 15 课补完的接口)确认 MCP 层是否正常,再看 Agent 日志里工具调用的解析(第 19 课 request_id 回放)。**评测告诉你"哪里坏了",定位还要靠你已经建好的观测体系。**

---

## 1.7 课后作业与思考题

**必做:**

1. 完成实验:评测集 + 脚本 + 报告入库;
2. 在 `docs/eval/README.md` 写 200 字"评测体系说明书":怎么跑、五个指标口径、报告命名规则——给三个月后的自己(和第 29 课的你自己)看。

**选做(思考或动手):**

1. 把"JSON 一次通过率"细化成**失败模式直方图**:markdown 围栏包裹 / 字段缺失 / 坐标越界 / 结构错误各占几例——失败模式的分布比总失败率更能指明改进方向;
2. 用第 18 课的 token 日志给报告加成本列:每案 prompt/completion tokens 与估算成本,体会"指标 5"里钱的部分;
3. 给 `detour_ratio` 换 2-opt 改进基线(选点局部交换优化),观察绕路率数字如何变化——想清楚:**基线变准了,历史数字还能直接对比吗?**

## 下节预告

**第 29 课:范式进阶:从 Pipeline 到自主 Agent。** 有了度量,就可以做一次"奢侈"的实验:给规划环节加 Reflection(生成后自我批判再修正),明知要多花 30–50% 的 LLM 成本——然后用今天这套评测集裁决:它到底值不值。同时回答一个大问题:什么时候该从 workflow 升级到自主 Agent。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
