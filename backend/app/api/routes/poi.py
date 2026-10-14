"""POI相关API路由"""

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from ...models.schemas import POIDetailResponse, POISearchResponse
from ...services.amap_service import get_amap_service
from ...services.unsplash_service import get_unsplash_service

router = APIRouter(prefix="/poi", tags=["POI"])


@router.get(
    "/detail/{poi_id}",
    response_model=POIDetailResponse,
    summary="获取POI详情",
    description="根据POI ID获取详细信息,包括图片"
)
async def get_poi_detail(poi_id: str):
    """
    获取POI详情
    
    Args:
        poi_id: POI ID
        
    Returns:
        POI详情响应
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
    "/search",
    response_model=POISearchResponse,
    summary="搜索POI",
    description="根据关键词搜索POI"
)
async def search_poi(keywords: str, city: str = "北京"):
    """
    搜索POI

    Args:
        keywords: 搜索关键词
        city: 城市名称

    Returns:
        搜索结果
    """
    try:
        amap_service = get_amap_service()

        # 同步阻塞的 MCP 调用, 放线程池避免卡住事件循环
        result = await run_in_threadpool(amap_service.search_poi, keywords, city)

        if result is None:
            # 区分"服务挂了"(None) 和"确实没搜到"(空列表)
            return POISearchResponse(
                success=False,
                message="搜索POI失败, 请稍后重试",
                data=[]
            )

        return POISearchResponse(
            success=True,
            message="搜索成功",
            data=result
        )

    except Exception as e:
        print(f"❌ 搜索POI失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"搜索POI失败: {str(e)}"
        )


@router.get(
    "/photo",
    summary="获取景点图片",
    description="根据景点名称从Unsplash获取图片"
)
async def get_attraction_photo(name: str):
    """
    获取景点图片

    Args:
        name: 景点名称

    Returns:
        图片URL
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

