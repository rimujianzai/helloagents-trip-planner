"""高德地图MCP服务封装"""

import json
import re
from typing import List, Dict, Any, Optional
from hello_agents.tools import MCPTool
from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo

# 全局MCP工具实例
_amap_mcp_tool = None


def _as_text(value: Any) -> str:
    """把高德返回的字段安全地转成字符串

    高德接口在字段缺失时返回的是空列表 [] 而不是 null, 直接 str() 会得到
    字面量 "[]"; 这里统一规整成空字符串, 避免脏数据渗进 POIInfo。
    """
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return "" if not value else str(value)
    return str(value)


def get_amap_mcp_tool() -> MCPTool:
    """
    获取高德地图MCP工具实例(单例模式)
    
    Returns:
        MCPTool实例
    """
    global _amap_mcp_tool
    
    if _amap_mcp_tool is None:
        settings = get_settings()
        
        if not settings.amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        
        # 创建MCP工具
        # 必须钉住 pydantic<2.12: amap-mcp-server 解析出的 mcp 1.8.1 会 import
        # pydantic 内部符号 eval_type_backport, 该符号在 pydantic 2.12 起已被移除,
        # 不钉住则子进程启动即 ImportError, 所有高德接口静默返回空数据。
        _amap_mcp_tool = MCPTool(
            name="amap",
            description="高德地图服务,支持POI搜索、路线规划、天气查询等功能",
            server_command=["uvx", "--with", "pydantic<2.12", "amap-mcp-server"],
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
    
    return _amap_mcp_tool


class AmapService:
    """高德地图服务封装类"""
    
    def __init__(self):
        """初始化服务"""
        self.mcp_tool = get_amap_mcp_tool()
    
    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> Optional[List[POIInfo]]:
        """
        搜索POI

        Args:
            keywords: 搜索关键词
            city: 城市
            citylimit: 是否限制在城市范围内

        Returns:
            POI信息列表; 调用失败或返回内容不是合法JSON时返回 None

        注意:
            None 表示"调用失败", [] 表示"调用成功但确实没有结果", 调用方必须区分。
            另外高德关键词搜索不返回经纬度, 需要坐标时用 get_poi_detail(poi_id) 补齐。
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

            print(f"POI搜索结果: {result[:200]}...")  # 打印前200字符

            # mcp_tool.run() 失败时返回的是错误文本而不是抛异常,
            # 所以"提取不到 JSON"就等于调用失败, 返回 None 让上层如实报错。
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if not json_match:
                print("⚠️ POI搜索返回内容中未找到JSON, 视为调用失败")
                return None

            data = json.loads(json_match.group())

            # amap-mcp-server 在接口报错时返回 {"error": "..."} 而不是抛异常
            if "error" in data:
                print(f"⚠️ POI搜索接口返回错误: {data['error']}")
                return None

            # maps_text_search 返回 {"suggestion": {...}, "pois": [{id, name, address, typecode}]}
            pois = [
                POIInfo(
                    id=_as_text(item.get("id")),
                    name=_as_text(item.get("name")),
                    typecode=_as_text(item.get("typecode")) or None,
                    address=_as_text(item.get("address")),
                )
                for item in (data.get("pois") or [])
            ]

            return pois

        except Exception as e:
            print(f"❌ POI搜索失败: {str(e)}")
            return None
    
    def get_weather(self, city: str) -> List[WeatherInfo]:
        """
        查询天气
        
        Args:
            city: 城市名称
            
        Returns:
            天气信息列表
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
            
            print(f"天气查询结果: {result[:200]}...")
            
            # TODO: 解析实际的天气数据
            return []
            
        except Exception as e:
            print(f"❌ 天气查询失败: {str(e)}")
            return []
    
    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking"
    ) -> Optional[Dict[str, Any]]:
        """
        规划路线

        Args:
            origin_address: 起点地址
            destination_address: 终点地址
            origin_city: 起点城市
            destination_city: 终点城市
            route_type: 路线类型 (walking/driving/transit)

        Returns:
            路线信息; 调用出错或解析不出数据时返回 None
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
            arguments = {
                "origin_address": origin_address,
                "destination_address": destination_address
            }

            # 城市参数能提高起终点地址的解析准确度, 所有路线类型都适用
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

            print(f"路线规划结果: {result[:200]}...")

            # TODO: 解析实际的路线数据
            return None

        except Exception as e:
            print(f"❌ 路线规划失败: {str(e)}")
            return None
    
    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        """
        地理编码(地址转坐标)

        Args:
            address: 地址
            city: 城市

        Returns:
            经纬度坐标
        """
        try:
            arguments = {"address": address}
            if city:
                arguments["city"] = city

            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_geo",
                "arguments": arguments
            })

            print(f"地理编码结果: {result[:200]}...")

            # TODO: 解析实际的坐标数据
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
            POI详情信息; 调用出错或返回内容不是合法JSON时返回 None
        """
        try:
            result = self.mcp_tool.run({
                "action": "call_tool",
                "tool_name": "maps_search_detail",
                "arguments": {
                    "id": poi_id
                }
            })

            print(f"POI详情结果: {result[:200]}...")

            # mcp_tool.run() 失败时返回的是错误文本而不是抛异常, 这里必须区分:
            # 提取不到 JSON 就说明调用失败, 返回 None 让上层报错,
            # 不能把错误文本当成详情数据交给调用方。
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            print("⚠️ POI详情返回内容中未找到JSON, 视为调用失败")
            return None

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

