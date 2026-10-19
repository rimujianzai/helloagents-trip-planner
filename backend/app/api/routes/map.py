"""地图 / POI 服务 API 路由

早期这里有两个 router：map.py（搜索/天气/路线）与 poi.py（详情/搜索/配图）。
「搜索 POI」在两个文件里各有一套实现，调用方不知道该用哪个，参数也略有差异
（/map/poi 支持 citylimit，/poi/search 不支持）。现已合并为本文件：

    GET  /api/map/poi                 搜索 POI（唯一入口）
    GET  /api/map/poi/detail/{poi_id} POI 详情
    GET  /api/map/photo               景点配图（Unsplash）
    GET  /api/map/weather             天气
    POST /api/map/route               路线规划
    GET  /api/map/health              健康检查
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from ...models.schemas import (
    POIDetailResponse,
    POISearchResponse,
    RouteRequest,
    RouteResponse,
    WeatherResponse
)
from ...services.amap_service import get_amap_service
from ...services.unsplash_service import get_unsplash_service

router = APIRouter(prefix="/map", tags=["地图服务"])


@router.get(
    "/poi",
    response_model=POISearchResponse,
    summary="搜索POI",
    description="根据关键词搜索POI(兴趣点)"
)
async def search_poi(
    keywords: str = Query(..., description="搜索关键词", examples=["故宫"]),
    city: str = Query(..., description="城市", examples=["北京"]),
    citylimit: bool = Query(True, description="是否限制在城市范围内")
):
    """
    搜索POI
    
    Args:
        keywords: 搜索关键词
        city: 城市
        citylimit: 是否限制在城市范围内
        
    Returns:
        POI搜索结果
    """
    try:
        # 获取服务实例
        service = get_amap_service()
        
        # 搜索POI (同步阻塞的 MCP 调用, 放线程池避免卡住事件循环)
        pois = await run_in_threadpool(service.search_poi, keywords, city, citylimit)
        
        if pois is None:
            # 服务层用 None 表示调用失败, 不能包装成"搜索成功但没结果"
            return POISearchResponse(
                success=False,
                message="POI搜索失败, 请稍后重试",
                data=[]
            )
        
        return POISearchResponse(
            success=True,
            message="POI搜索成功",
            data=pois
        )
        
    except Exception as e:
        print(f"❌ POI搜索失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"POI搜索失败: {str(e)}"
        )


@router.get(
    "/poi/detail/{poi_id}",
    response_model=POIDetailResponse,
    summary="获取POI详情",
    description="根据POI ID获取详细信息（含图片）"
)
async def get_poi_detail(poi_id: str):
    """获取 POI 详情。

    从原 poi.py 迁移而来。保留独立端点而不是塞进 /poi 的返回体：
    详情接口的调用频次低、返回体积大，按需请求更省流量。
    """
    try:
        amap_service = get_amap_service()

        # 同步阻塞的 MCP 调用, 放线程池避免卡住事件循环
        result = await run_in_threadpool(amap_service.get_poi_detail, poi_id)

        if result is None:
            # 服务层用 None 表示调用失败, 不能把错误内容当详情返回
            return POIDetailResponse(
                success=False,
                message="获取POI详情失败, 请稍后重试",
                data=None
            )

        return POIDetailResponse(
            success=True,
            message="获取POI详情成功",
            data=result
        )

    except Exception as e:
        print(f"❌ 获取POI详情失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取POI详情失败: {str(e)}"
        )


@router.get(
    "/photo",
    summary="获取景点图片",
    description="根据景点名称从Unsplash获取图片"
)
async def get_attraction_photo(name: str):
    """获取景点配图。

    从原 poi.py 迁移而来。虽然它不调用高德，但同属「地点信息」能力，
    放在 /map 下比单独开一个 /poi 前缀更符合调用方的心智模型。
    """
    try:
        unsplash_service = get_unsplash_service()

        # 同步阻塞的 requests 调用, 放线程池避免卡住事件循环
        photo_url = await run_in_threadpool(
            unsplash_service.get_photo_url, f"{name} China landmark"
        )

        if not photo_url:
            # 加了地名没搜到, 退回只用景点名称再试一次
            photo_url = await run_in_threadpool(unsplash_service.get_photo_url, name)

        if not photo_url:
            # 没配 key 或确实搜不到图时如实报失败, 让前端走占位图逻辑,
            # 而不是返回 success=true + 空 URL 假装成功
            return {
                "success": False,
                "message": "未找到景点图片",
                "data": {
                    "name": name,
                    "photo_url": None
                }
            }

        return {
            "success": True,
            "message": "获取图片成功",
            "data": {
                "name": name,
                "photo_url": photo_url
            }
        }

    except Exception as e:
        print(f"❌ 获取景点图片失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取景点图片失败: {str(e)}"
        )


@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="查询天气",
    description="查询指定城市的天气信息"
)
async def get_weather(
    city: str = Query(..., description="城市名称", examples=["北京"])
):
    """
    查询天气
    
    Args:
        city: 城市名称
        
    Returns:
        天气信息
    """
    try:
        # 获取服务实例
        service = get_amap_service()
        
        # 查询天气 (同步阻塞调用, 放线程池避免卡住事件循环)
        weather_info = await run_in_threadpool(service.get_weather, city)
        
        if weather_info is None:
            return WeatherResponse(
                success=False,
                message="天气查询失败, 请稍后重试",
                data=[]
            )
        
        return WeatherResponse(
            success=True,
            message="天气查询成功",
            data=weather_info
        )
        
    except Exception as e:
        print(f"❌ 天气查询失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"天气查询失败: {str(e)}"
        )


@router.post(
    "/route",
    response_model=RouteResponse,
    summary="规划路线",
    description="规划两点之间的路线"
)
async def plan_route(request: RouteRequest):
    """
    规划路线
    
    Args:
        request: 路线规划请求
        
    Returns:
        路线信息
    """
    try:
        # 获取服务实例
        service = get_amap_service()
        
        # 规划路线 (同步阻塞调用, 放线程池避免卡住事件循环)
        route_info = await run_in_threadpool(
            service.plan_route,
            request.origin_address,
            request.destination_address,
            request.origin_city,
            request.destination_city,
            request.route_type
        )
        
        if route_info is None:
            return RouteResponse(
                success=False,
                message="路线规划失败, 请检查地址是否正确后重试",
                data=None
            )
        
        return RouteResponse(
            success=True,
            message="路线规划成功",
            data=route_info
        )
        
    except Exception as e:
        print(f"❌ 路线规划失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"路线规划失败: {str(e)}"
        )


@router.get(
    "/health",
    summary="健康检查",
    description="检查地图服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        # 检查服务是否可用
        service = get_amap_service()
        
        return {
            "status": "healthy",
            "service": "map-service",
            "mcp_tools_count": len(service.mcp_tool._available_tools)
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )

