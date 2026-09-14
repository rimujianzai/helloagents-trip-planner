# 第 15 课:MCP 结果解析实战

> 所属模块:模块四「服务层与数据质量」(第 15–18 课)
> 预计时长:1.5–2 小时(含动手实验;需要能启动后端,且 `AMAP_API_KEY` 已按第 3 课配置好)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:第 14 课「结构化输出(下):失败降级与产品伦理」

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量   ← 你在这里(第 15 课)
模块五 工程化
模块六 产品化与进阶
```

模块三里你已经把 Agent 改造成"并行 + 异步 + 重试解析 + 诚实报错"。但有一个事实被掩盖至今:**Agent 的"眼睛"是瞎的**——服务层 `amap_service.py` 里负责查 POI、天气、路线、坐标的四个方法全是返回空数据的 TODO 桩。你的 Agent 一直靠 LLM 的内部知识在"想象"世界。

**本课开始修眼睛:先学会"已完成的那个方法"是怎么解析 MCP 返回的,再把四个桩补掉两个(search_poi、get_weather),让两个 API 接口第一次吐出真实数据。** 剩下的 geocode 和 plan_route 留给第 16 课——它们是"把真实世界接进行程规划"的钥匙。

## 学习目标

完成本课后,你应该能够:

1. 说清 `mcp_tool.run({"action": "call_tool", ...})` 这条 MCP 调用链的三个要素,以及为什么拿回来的东西是**字符串**;
2. 读懂 `get_poi_detail` 的正则提取写法,并指出它在什么情况下会失败;
3. 写出一个三层兜底的健壮 JSON 解析器,解析失败时**把完整原始响应留在日志里**;
4. 把高德 API 的返回字段映射到 `POIInfo` / `WeatherInfo`,让 `GET /api/map/poi` 和 `GET /api/map/weather` 真正出数据。

## 课前自检

- [ ] 后端能正常启动,`AMAP_API_KEY` 有效(第 3 课验证过 `uvx amap-mcp-server` 能被拉起);
- [ ] 你用过 `/docs` 交互式调用接口(第 3 课);
- [ ] 你知道 Pydantic 模型的基本写法,读过 `schemas.py` 里的 `TripRequest`(第 2、13 课);
- [ ] 你的 `trip_planner_agent.py` 已完成模块三改造(并行 + 异步 + 重试解析 + 移除假数据 fallback)。

---

## 1.1 现状盘点:四个"空转"的桩

打开 `backend/app/services/amap_service.py`,把 5 个业务方法列成一张表:

| 方法 | 位置 | 当前返回 | 对应接口 | 状态 |
|---|---|---|---|---|
| `search_poi` | 57–91 行 | `[]`(87 行) | `GET /api/map/poi`(`map.py:44` 调用)、`GET /api/poi/search`(`poi.py:73` 调用) | 空转 |
| `get_weather` | 93–120 行 | `[]`(116 行) | `GET /api/map/weather`(`map.py:83` 调用) | 空转 |
| `plan_route` | 122–186 行 | `{}`(182 行) | `POST /api/map/route`(`map.py:120` 调用) | 空转,还会引发 500 |
| `geocode` | 188–217 行 | `None`(213 行) | 未暴露任何接口 | 空转 |
| `get_poi_detail` | 219–254 行 | 真实数据 | `GET /api/poi/detail/{poi_id}`(`poi.py:39` 调用) | **唯一能用** |

看 `search_poi` 的身体(69–91 行)——其余三个桩的结构和它一模一样:

```python
try:
    # 调用MCP工具
    result = self.mcp_tool.run({
        "action": "call_tool",
        "tool_name": "maps_text_search",
        "arguments": {
            "keywords": keywords,
            "city": city,
            "citylimit": str(citylimit).lower()
        }
    })

    # 解析结果
    # 注意: MCP工具返回的是字符串,需要解析
    # 这里简化处理,实际应该解析JSON
    print(f"POI搜索结果: {result[:200]}...")  # 打印前200字符

    # TODO: 解析实际的POI数据
    return []
```

MCP 调用**发生了、也成功了**(84 行能打印出结果),问题只出在最后一步:拿到结果后直接 `return []` 把它扔掉了。所以本课的工作量集中且明确——**调用不用动,只补"解析"这一段**。

### 顺带发现一个隐藏 500

`POST /api/map/route` 现在不只是"没数据",而是**一调就 500**:服务层返回 `{}`,而 `RouteResponse.data` 的类型是 `Optional[RouteInfo]`(`schemas.py:185-189`),其中 `distance`、`duration` 是必填字段(`schemas.py:177-182`)。空字典过不了 Pydantic 校验,异常被 `map.py:134-139` 的 `except` 捕获,变成 500。你现在就可以在 `/docs` 里调用它复现。第 16 课补全 `plan_route` 时会顺手修掉它。

## 1.2 解剖一次 MCP 调用:`mcp_tool.run` 的三个要素

`self.mcp_tool` 是 `MCPTool` 的实例(28–34 行创建):

```python
_amap_mcp_tool = MCPTool(
    name="amap",
    description="高德地图服务,支持POI搜索、路线规划、天气查询等功能",
    server_command=["uvx", "amap-mcp-server"],
    env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
    auto_expand=True  # 自动展开为独立工具
)
```

`MCPTool` 来自 `hello_agents.tools`(第 4 行 import)——**框架代码不在本仓库**,它的内部机制我们只讲原理、教你怎么定位,不编行号(第 10 课已经练过这套方法)。

调用协议就藏在 71–79 行那个字典里,**三要素**:

| 键 | 含义 | 本项目的取值 |
|---|---|---|
| `action` | 对 MCP 工具做什么 | `"call_tool"`(调用某个工具;发现工具是另一个 action,框架源码里可查) |
| `tool_name` | 调 MCP server 的哪个工具 | `"maps_text_search"` / `"maps_weather"` / `"maps_geo"` / `"maps_direction_*"` |
| `arguments` | 传给工具的参数字典 | 关键词、城市、地址等 |

### 两个值得注意的观察

**观察一:返回值是字符串。** 82–83 行的注释写明"MCP工具返回的是字符串,需要解析",84 行的 `result[:200]` 也证明它支持切片。MCP 协议里工具结果本质是文本内容,所以你的代码要自己做"字符串 → JSON → Pydantic 模型"三级转换。

**观察二:两处工具名不一样。** 服务层用 `"maps_text_search"`(73 行),而 Agent 提示词里教 LLM 写的是 `amap_maps_text_search`(`trip_planner_agent.py:20`)。对照 `MCPTool(name="amap", ...)` 和 `auto_expand=True`(33 行)可以推断:`auto_expand` 把 server 的每个工具展开注册成了 `amap_` 前缀的独立工具供 Agent 调用。这是一个推断,验证方法:去 hello-agents 源码里搜 `auto_expand` 的实现(不在本仓库,严禁编造行号);或看启动日志——`amap_service.py:40-45` 会打印展开后的工具列表。

## 1.3 参考答案:唯一完成的 `get_poi_detail` 怎么写的

`get_poi_detail`(219–254 行)是全文件唯一"跑通了全链路"的方法,核心是 241–250 行:

```python
# 解析结果并提取图片
import json
import re

# 尝试从结果中提取JSON
json_match = re.search(r'\{.*\}', result, re.DOTALL)
if json_match:
    data = json.loads(json_match.group())
    return data

return {"raw": result}
```

这个写法的思路是:**不假设 `result` 是纯 JSON**(它可能带 MCP 的包装文字),用正则从第一个 `{` 贪婪匹配到最后一个 `}`,把中间当 JSON 解析。

它的三个弱点(也是本课要改进的):

1. **贪婪匹配会误伤**:`re.DOTALL` 下 `\{.*\}` 会从第一个 `{` 抓到最后一个 `}`。如果返回文本里有多个 JSON 对象、或 JSON 后面还有花括号文字,抓出来的就是非法字符串,`json.loads`(247 行)直接抛异常——而这个异常没有任何兜底,直接跳进 `except` 打印一句就返回 `{}`(252–254 行)。
2. **不留证据**:失败时只在 238 行打印过前 200 字符(`print(f"POI详情结果: {result[:200]}...")`),出了问题你永远看不到完整响应,没法排查是字段错了还是接口本身报错了。
3. **不校验业务状态**:高德的返回里有业务级成败(`status` 字段),HTTP 层成功不代表查询成功。直接 `return data` 会把错误响应当数据透传给调用方。

## 1.4 更健壮的解析器:三层策略 + 完整留底

我们写一个公共辅助方法 `_extract_json`,挂在 `AmapService` 类里(建议放在 `geocode` 和 `get_poi_detail` 之间),以后四个桩共用:

```python
import json
import re  # 已在 get_poi_detail 内局部 import,建议提到文件顶部

def _extract_json(self, raw: str) -> Optional[dict]:
    """从 MCP 返回的字符串中提取 JSON 对象;失败时返回 None 并保留原始响应"""
    if not raw:
        return None

    # 策略1:本身就是合法 JSON(最理想情况)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 策略2:正则兜底——JSON 嵌在文字里(参考 get_poi_detail 245 行的思路)
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 策略3:彻底失败——把完整原始响应写进日志,给排查留证据
    print(f"⚠️ [amap_service] JSON 解析失败,原始响应完整保留如下:\n{raw}")
    return None
```

三个设计决策,每一条都是针对性加固:

- **先试 `json.loads` 再用正则**:正则是"可能出错的重操作",能不走就不走;
- **失败打印完整 `raw`,不是 `raw[:200]`**:这是本课的硬性要求(也是大纲知识点"解析失败时的日志保留原始响应")。你以后会感谢这几行——第 19 课它们会被 loguru 正式接管落盘;
- **返回 `None` 而不是抛异常**:和四个桩现有的 `except` 风格一致——服务层降级,让 API 层决定怎么向用户表达失败(第 14 课的"诚实报错"原则:返回空列表 + 日志有据,而不是编数据)。

## 1.5 高德返回结构:从原始响应到 Pydantic 模型

补解析之前,先做一次**侦察**:把 84 行临时改成 `print(f"POI搜索结果: {result}")`(去掉 `[:200]`),启动后端,在 `/docs` 里调 `GET /api/map/poi?keywords=故宫&city=北京`,把完整响应抄进笔记。

按高德公开 API 的典型结构,你会看到类似这样的 JSON(**字段名以你侦察到的为准**,这是本课方法论的一部分):

```json
{
  "status": "1",
  "info": "OK",
  "infocode": "10000",
  "count": "10",
  "pois": [
    {
      "id": "B000A8UIN8",
      "name": "故宫博物院",
      "type": "风景名胜;风景名胜;国家级景点",
      "address": "北京市东城区景山前街4号",
      "location": "116.397026,39.918056",
      "tel": "010-85007073"
    }
  ]
}
```

三个关键认知:

1. **业务状态在 `status`**:`"1"` 成功、`"0"` 失败(看 `info`/`infocode`,常见原因是 key 无效、配额用尽、参数非法)。解析前必须先判它。
2. **`location` 是一个字符串**,格式 `"经度,纬度"`——而 `schemas.py` 里的 `Location`(54–57 行)要求两个独立的 float。**拆分 + 类型转换是字段映射的核心动作**,而且注意顺序:高德是**经度在前**。
3. 天气接口的结构是 `forecasts[0].casts[]` 数组,每天一个元素,字段名是**小写连写**:`dayweather`、`nightweather`、`daytemp`、`nighttemp`、`winddirection`、`windpower`。

### 字段映射表一:`maps_text_search` → `POIInfo`(schemas.py:160–167)

| 高德字段 | POIInfo 字段 | 需要的转换 |
|---|---|---|
| `pois[].id` | `id` | 转 `str` |
| `pois[].name` | `name` | 直接用 |
| `pois[].type` | `type` | 直接用(分号分隔的分类串) |
| `pois[].address` | `address` | 可能为空,兜底 `""` |
| `pois[].location` | `location.longitude` / `location.latitude` | **字符串拆分,经度在前,转 float** |
| `pois[].tel` | `tel` | 可能为空,兜底 `None` |

### 字段映射表二:`maps_weather` → `WeatherInfo`(schemas.py:109–130)

| 高德字段 | WeatherInfo 字段 | 需要的转换 |
|---|---|---|
| `forecasts[].casts[].date` | `date` | 直接用 |
| `casts[].dayweather` | `day_weather` | **改名** |
| `casts[].nightweather` | `night_weather` | **改名** |
| `casts[].daytemp` | `day_temp` | 字符串 `"25"`;`WeatherInfo` 的温度校验器(119–130 行)会自动去单位转 int,你只需透传 |
| `casts[].nighttemp` | `night_temp` | 同上 |
| `casts[].winddirection` | `wind_direction` | **改名** |
| `casts[].windpower` | `wind_power` | 直接用(如 `"1-3"`) |

注意第 13/20 课打过照面的那个温度校验器在这里"白捡"了一层保护:`day_temp` 声明为 `Union[int, str]` 且有 `mode='before'` 校验器,传 `"25"` 进来会变成 `25`。**服务层不必强行转型,但要理解为什么可以不转。**

## 1.6 动手实验:补全 `search_poi` 与 `get_weather`(本课核心任务)

### 任务

用 1.4 的 `_extract_json` + 1.5 的映射表,把两个桩补成真实实现,让 `GET /api/map/poi` 和 `GET /api/map/weather` 在 `/docs` 里返回真实数据。

### 步骤

1. **侦察**:按 1.5 开头的方法拿到两个接口的完整原始响应,存进笔记(后面写映射全靠它)。
2. **加辅助方法**:把 `_extract_json` 加进 `AmapService`(`import json` / `import re` 移到文件顶部)。
3. **改写 `search_poi`** 的解析段(71 行的 MCP 调用不动),参考实现:

```python
data = self._extract_json(result)
if data is None:
    return []
if str(data.get("status")) != "1":
    print(f"❌ 高德返回错误: status={data.get('status')}, info={data.get('info')}, 完整响应:\n{result}")
    return []

pois = []
for item in data.get("pois", []):
    loc = item.get("location", "")            # "116.397026,39.918056"
    lon_str, _, lat_str = loc.partition(",")
    try:
        location = Location(longitude=float(lon_str), latitude=float(lat_str))
    except ValueError:
        print(f"⚠️ 跳过坐标异常的POI: {item.get('name')} location={loc!r}")
        continue
    pois.append(POIInfo(
        id=str(item.get("id", "")),
        name=item.get("name", ""),
        type=item.get("type", ""),
        address=item.get("address", "") or "",
        location=location,
        tel=item.get("tel") or None,
    ))
return pois
```

4. **改写 `get_weather`** 的解析段,同样先判 `status`,再遍历 `data.get("forecasts", [])[0].get("casts", [])`,按映射表二构造 `WeatherInfo` 列表。注意 `forecasts` 可能为空数组,先取 `[0]` 前判空,避免 `IndexError`。
5. **失败留底**:两个方法的"返回空"分支(解析失败、`status != "1"`、异常)都必须打印**完整**原始响应。
6. **验证**:重启后端,`/docs` 里依次调 `GET /api/map/poi?keywords=故宫&city=北京` 和 `GET /api/map/weather?city=北京`,确认返回真实数据;再调 `GET /api/poi/search?keywords=公园&city=上海`(`poi.py:73` 也走 `search_poi`)确认同步复活。

### 完成标准

- [ ] `/api/map/poi` 返回的每个 POI 都有真实名称、地址、经纬度(拿经纬度去任意地图产品反查可验证);
- [ ] `/api/map/weather` 返回多天预报,温度是纯数字(校验器生效);
- [ ] 故意查一个不存在的城市(如 `city=阿特兰蒂斯`),接口返回空列表而非 500,且后端日志里有**完整**原始响应;
- [ ] 临时加的侦察 `print` 已删除或恢复为截断打印;
- [ ] `_extract_json` 被两个方法共用,没有复制粘贴两份。

### 常见卡点

- **"`json.loads` 报错,提示不是合法 JSON?"** —— 先 `print(repr(result))` 看看有没有 MCP 的包装文字或转义问题;这正是策略 2(正则兜底)存在的意义。如果正则抓出来仍解析失败,说明返回里有多个 JSON 片段,打印完整 `raw` 按实际情况收紧匹配。
- **"`POIInfo` 校验失败,提示 location 类型错误?"** —— 你忘了把 `"116.39,39.91"` 拆成两个 float,`Pydantic` 不会替你拆字符串。
- **"`status` 明明是 1,`pois` 却是空的?"** —— 检查关键词和 `citylimit`;另外部分词在高德属于"无结果"而非"错误",`count` 为 `"0"` 时 `pois` 就是空数组,这是正常数据,别当异常处理。

---

## 1.7 课后作业与思考题

**必做:**

1. 完成实验,`/api/map/poi`、`/api/map/weather` 真实出数据(完成标准全勾);
2. 用 `_extract_json` 顺手加固 `get_poi_detail`:替换它 245 行的裸正则,失败时同样完整留底——注意保留它"拿不到 JSON 就返回 `{"raw": result}`"的降级行为(`poi.py:41-45` 的响应模型是自由 dict,不会因此 500);
3. 在 `docs/lesson15-notes.md` 里写下你侦察到的两份原始响应,并各标注一个"如果没判 `status` 就会出的事故"。

**选做(思考,不用交):**

1. `search_poi` 是同步方法,却被 `async def` 路由直接调用(`map.py:44`)——按第 12 课的标准,这算不算阻塞事件循环?量级上和 `plan_trip` 的阻塞一样严重吗?
2. 同一个"查北京景点"的动作,现在存在两条通道:Agent 走 `[TOOL_CALL]`,服务层走 `mcp_tool.run`。如果你是架构师,什么时候该走哪条?(第 16 课会真的把两条通道拧在一起用)

## 下节预告

**第 16 课:地理数据进阶——把真实世界接进规划。** 你将补完剩下两个桩(geocode、plan_route),用 haversine 和真实通勤时间,把"LLM 凭感觉排景点"升级成"数据驱动排序"——并用同一城市对比改造前后的绕路程度。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
