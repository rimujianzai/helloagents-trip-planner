"""高德地图MCP服务封装"""

import json
import re
from typing import List, Dict, Any, Optional

from .persistent_mcp import PersistentMCPTool

from ..config import get_settings
from ..models.schemas import Location, POIInfo, RouteInfo, WeatherInfo

# 全局MCP工具实例
_amap_mcp_tool = None


# ============ MCP 返回解析辅助 ============
#
# 为什么需要这一层:
# 1. hello_agents 的 MCPTool.run() 返回的是字符串(形如 "工具 'xxx' 执行结果:\n{...}"),
#    不是结构化数据, 得自己从文本里把 JSON 抠出来。
# 2. amap-mcp-server 在上游接口失败时返回 {"error": "..."}, 既不抛异常也不给错误码,
#    所以"调用到底成功没有"必须由我们显式判定。
#
# 全文件统一的哨兵语义:
#   None -> 调用失败(网络错误 / MCP 报错 / 返回内容不可解析)
#   []   -> 调用成功, 但确实没有数据
# 这样调用方才能区分"服务挂了"和"这里就是没结果", 而不是把失败伪装成空数据。


def _as_text(value: Any) -> str:
    """把高德返回的字段规整成字符串。

    高德在字段缺失时经常返回空列表 [] 而不是 null,
    直接 str() 会得到 "[]" 这种字面量脏数据。
    """
    if value is None or isinstance(value, (list, dict)):
        return ""
    return str(value).strip()


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """把高德返回的数字字符串转成 int(可能是 "1234.0" 这种), 失败时返回 default"""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _parse_mcp_json(result: Any) -> Optional[Dict[str, Any]]:
    """从 MCP 工具返回的文本中提取 JSON 对象。

    Returns:
        解析成功且不含 error 键时返回 dict; 否则返回 None
    """
    match = re.search(r'\{.*\}', str(result or ""), re.DOTALL)
    if not match:
        print("⚠️ MCP 返回内容中未找到 JSON, 视为调用失败")
        return None

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"⚠️ MCP 返回的 JSON 解析失败: {e}")
        return None

    if not isinstance(data, dict):
        print("⚠️ MCP 返回的 JSON 不是对象, 视为调用失败")
        return None

    # MCP server 报错时返回 {"error": ...}, 这里统一拦掉, 不让它流到业务层
    if "error" in data:
        print(f"⚠️ MCP 工具返回错误: {data['error']}")
        return None

    return data


def _parse_location(value: Any) -> Optional[Location]:
    """解析高德的 "经度,纬度" 坐标字符串"""
    text = _as_text(value)
    if not text:
        return None

    parts = text.split(",")
    if len(parts) != 2:
        return None

    try:
        return Location(longitude=float(parts[0]), latitude=float(parts[1]))
    except ValueError:
        return None


def get_amap_mcp_tool() -> PersistentMCPTool:
    """
    获取高德地图MCP工具实例(单例模式)
    
    Returns:
        PersistentMCPTool实例
    """
    global _amap_mcp_tool
    
    if _amap_mcp_tool is None:
        settings = get_settings()
        
        if not settings.amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        
        # 创建MCP工具
        # 用 PersistentMCPTool: 原生 MCPTool 每次调用都重开一个 uvx 子进程
        # (实测每次约 2.37s 启动+握手), 这里整个进程复用同一个常驻会话。
        _amap_mcp_tool = PersistentMCPTool(
            name="amap",
            description="高德地图服务,支持POI搜索、路线规划、天气查询等功能",
            server_command=settings.get_amap_mcp_command(),
            env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
            auto_expand=True  # 自动展开为独立工具
        )
        
        print(f"✅ 高德地图MCP工具初始化成功")
        print(f"   工具数量: {len(_amap_mcp_tool._available_tools)}")
        
        # 打印可用工具列表
        if _amap_mcp_tool._available_tools:
            print("   可用工具:")
            for tool in _amap_mcp_tool._available_tools[:5]:  # 只打印前5个
                print(f"     - {tool.get('name', 'unknown')}")
            if len(_amap_mcp_tool._available_tools) > 5:
                print(f"     ... 还有 {len(_amap_mcp_tool._available_tools) - 5} 个工具")
        else:
            # hello_agents 的 _discover_tools 会静默吞掉发现阶段的异常,
            # 这里必须显式告警, 否则后续只会看到莫名其妙的"工具未找到"。
            print("⚠️  高德地图MCP工具发现失败: 未获取到任何工具。")
            print("    常见原因: uvx 不可用 / 网络不通 / MCP 子进程启动即崩溃")
            print(f"    启动命令: {' '.join(settings.get_amap_mcp_command())}")
    
    return _amap_mcp_tool


class AmapService:
    """高德地图服务封装类"""
    
    def __init__(self):
        """初始化服务"""
        self.mcp_tool = get_amap_mcp_tool()
    
    def search_poi(
        self,
        keywords: str,
        city: str,
        citylimit: bool = True
    ) -> Optional[List[POIInfo]]:
        """
        搜索POI

        Args:
            keywords: 搜索关键词
            city: 城市
            citylimit: 是否限制在城市范围内

        Returns:
            POI信息列表; None 表示调用失败

        注意: maps_text_search 只返回 id/name/address/typecode, 不含经纬度。
        需要坐标时用 get_poi_detail() 按 id 补齐。
        """
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

            print(f"POI搜索结果: {str(result)[:200]}...")

            data = _parse_mcp_json(result)
            if data is None:
                return None

            pois: List[POIInfo] = []
            for item in data.get("pois") or []:
                if not isinstance(item, dict):
                    continue

                poi_id = _as_text(item.get("id"))
                name = _as_text(item.get("name"))
                if not poi_id or not name:
                    # id/name 是 POIInfo 的必填字段, 缺任意一个都拼不出合法对象
                    continue

                pois.append(POIInfo(
                    id=poi_id,
                    name=name,
                    typecode=_as_text(item.get("typecode")) or None,
                    address=_as_text(item.get("address")),
                ))

            return pois

        except Exception as e:
            print(f"❌ POI搜索失败: {str(e)}")
            return None
    
    def get_weather(self, city: str) -> Optional[List[WeatherInfo]]:
        """
        查询天气
        
        Args:
            city: 城市名称
            
        Returns:
            天气信息列表(通常是未来几天); None 表示调用失败
        """
        try:
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_weather",
                "arguments": {
                    "city": city
                }
            })

            print(f"天气查询结果: {str(result)[:200]}...")

            data = _parse_mcp_json(result)
            if data is None:
                return None

            weather_list: List[WeatherInfo] = []
            for cast in data.get("forecasts") or []:
                if not isinstance(cast, dict):
                    continue

                date_str = _as_text(cast.get("date"))
                if not date_str:
                    # date 是 WeatherInfo 的必填字段
                    continue

                weather_list.append(WeatherInfo(
                    date=date_str,
                    day_weather=_as_text(cast.get("dayweather")),
                    night_weather=_as_text(cast.get("nightweather")),
                    # 温度原样交给 WeatherInfo 的 parse_temperature 校验器处理,
                    # 它会洗掉 "°C" 之类的单位; 这里提前转 int 反而会丢掉这个能力
                    day_temp=cast.get("daytemp") or 0,
                    night_temp=cast.get("nighttemp") or 0,
                    wind_direction=_as_text(cast.get("daywind")),
                    wind_power=_as_text(cast.get("daypower")),
                ))

            return weather_list

        except Exception as e:
            print(f"❌ 天气查询失败: {str(e)}")
            return None
    
    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking"
    ) -> Optional[RouteInfo]:
        """
        规划路线
        
        Args:
            origin_address: 起点地址
            destination_address: 终点地址
            origin_city: 起点城市
            destination_city: 终点城市
            route_type: 路线类型 (walking/driving/transit)
            
        Returns:
            路线信息; None 表示调用失败

        说明: 三种路线类型的返回结构并不一致 ——
        步行/驾车是 route.paths[], 公共交通是 route.transits[],
        这里统一归一化成 RouteInfo(距离/时长/描述)。
        """
        try:
            # 根据路线类型选择工具
            tool_map = {
                "walking": "maps_direction_walking_by_address",
                "driving": "maps_direction_driving_by_address",
                "transit": "maps_direction_transit_integrated_by_address"
            }
            
            tool_name = tool_map.get(route_type, "maps_direction_walking_by_address")
            
            # 构建参数
            arguments: Dict[str, Any] = {
                "origin_address": origin_address,
                "destination_address": destination_address
            }

            # 提供城市参数可以提高地址解析(geocode)的准确性; 公共交通则必须传
            if origin_city:
                arguments["origin_city"] = origin_city
            if destination_city:
                arguments["destination_city"] = destination_city
            
            # 调用MCP工具
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": tool_name,
                "arguments": arguments
            })
            
            print(f"路线规划结果: {str(result)[:200]}...")

            data = _parse_mcp_json(result)
            if data is None:
                return None

            route = data.get("route")
            if not isinstance(route, dict):
                print("⚠️ 路线规划返回中缺少 route 字段")
                return None

            # 公共交通的返回结构与步行/驾车完全不同, 单独归一化
            if route_type == "transit":
                return self._parse_transit_route(route, origin_address, destination_address)

            paths = route.get("paths") or []
            if not paths or not isinstance(paths[0], dict):
                print("⚠️ 路线规划未返回可用路径")
                return None

            path = paths[0]
            distance = _as_int(path.get("distance"))
            duration = _as_int(path.get("duration"))
            if distance is None or duration is None:
                print("⚠️ 路线规划返回的距离/时长为空")
                return None

            description = self._describe_steps(path.get("steps"))
            if not description:
                description = f"{origin_address} → {destination_address}"

            return RouteInfo(
                distance=float(distance),
                duration=duration,
                route_type=route_type,
                description=description
            )
            
        except Exception as e:
            print(f"❌ 路线规划失败: {str(e)}")
            return None

    @staticmethod
    def _describe_steps(steps: Any) -> str:
        """把路线 steps 里的导航指令拼成一句话"""
        if not isinstance(steps, list):
            return ""

        instructions = [
            _as_text(step.get("instruction"))
            for step in steps
            if isinstance(step, dict)
        ]
        instructions = [text for text in instructions if text]

        return " → ".join(instructions[:3])

    @staticmethod
    def _parse_transit_route(
        route: Dict[str, Any],
        origin_address: str,
        destination_address: str
    ) -> Optional[RouteInfo]:
        """归一化公共交通路线。

        transit 的结构是 route.transits[] -> segments[] -> bus.buslines[],
        这里取第一条方案, 用沿途公交/地铁线路名拼出描述。
        """
        transits = route.get("transits") or []
        if not transits or not isinstance(transits[0], dict):
            print("⚠️ 公共交通路线未返回可用方案")
            return None

        transit = transits[0]

        duration = _as_int(transit.get("duration"))
        if duration is None:
            print("⚠️ 公共交通路线缺少时长")
            return None

        # route.distance 是方案总距离; 缺失时用步行距离兜底
        distance = _as_int(route.get("distance"))
        if distance is None:
            distance = _as_int(transit.get("walking_distance"), 0)

        lines: List[str] = []
        for segment in transit.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            bus = segment.get("bus")
            if not isinstance(bus, dict):
                continue
            for busline in bus.get("buslines") or []:
                if not isinstance(busline, dict):
                    continue
                name = _as_text(busline.get("name"))
                if name and name not in lines:
                    lines.append(name)

        description = " → ".join(lines) if lines else f"{origin_address} → {destination_address}"

        return RouteInfo(
            distance=float(distance or 0),
            duration=duration,
            route_type="transit",
            description=description
        )

    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        """
        地理编码(地址转坐标)

        Args:
            address: 地址
            city: 城市

        Returns:
            经纬度坐标; None 表示调用失败或该地址解析不出坐标
        """
        try:
            arguments: Dict[str, Any] = {"address": address}
            if city:
                arguments["city"] = city

            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_geo",
                "arguments": arguments
            })

            print(f"地理编码结果: {str(result)[:200]}...")

            data = _parse_mcp_json(result)
            if data is None:
                return None

            # maps_geo 的结果放在 "return" 键下(是个列表, 可能为空)
            for item in data.get("return") or []:
                if not isinstance(item, dict):
                    continue
                location = _parse_location(item.get("location"))
                if location:
                    return location

            print(f"⚠️ 地理编码未解析出坐标: {address}")
            return None

        except Exception as e:
            print(f"❌ 地理编码失败: {str(e)}")
            return None

    def get_poi_detail(self, poi_id: str) -> Optional[Dict[str, Any]]:
        """
        获取POI详情

        Args:
            poi_id: POI ID

        Returns:
            POI详情信息; None 表示调用失败
        """
        try:
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_search_detail",
                "arguments": {
                    "id": poi_id
                }
            })

            print(f"POI详情结果: {str(result)[:200]}...")

            return _parse_mcp_json(result)

        except Exception as e:
            print(f"❌ 获取POI详情失败: {str(e)}")
            return None


# 创建全局服务实例
_amap_service = None


def get_amap_service() -> AmapService:
    """获取高德地图服务实例(单例模式)"""
    global _amap_service
    
    if _amap_service is None:
        _amap_service = AmapService()
    
    return _amap_service

