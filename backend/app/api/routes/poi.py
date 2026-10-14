"""POI相关API路由"""

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional
from ...services.amap_service import get_amap_service
from ...services.unsplash_service import get_unsplash_service

router = APIRouter(prefix="/poi", tags=["POI"])


class POIDetailResponse(BaseModel):
    """POI详情响应"""
    success: bool
    message: str
    data: Optional[dict] = None


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

        # 调用高德地图POI详情API (同步阻塞调用, 放线程池)
        result = await run_in_threadpool(amap_service.get_poi_detail, poi_id)

        # get_poi_detail 失败时返回 None (MCP 调用失败会返回错误文本而非抛异常),
        # 不能包装成 success=True 把错误文本当详情数据返回给调用方。
        if result is None:
            return POIDetailResponse(
                success=False,
                message="获取POI详情失败: 未获取到有效数据",
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
        result = await run_in_threadpool(amap_service.search_poi, keywords, city)

        # search_poi 调用失败返回 None, 成功但确实没结果返回 []。
        # 必须区分这两种情况: 失败要如实上报, 不能包装成 success=True + 空列表,
        # 否则调用方无法分辨"没搜到"和"接口挂了"。
        if result is None:
            return {
                "success": False,
                "message": "搜索POI失败: 未获取到有效数据",
                "data": []
            }

        return {
            "success": True,
            "message": f"搜索成功, 共 {len(result)} 条结果",
            "data": [poi.model_dump() for poi in result]
        }

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

        # 搜索景点图片 (同步阻塞的 requests 调用, 放线程池)
        photo_url = await run_in_threadpool(
            unsplash_service.get_photo_url, f"{name} China landmark"
        )

        if not photo_url:
            # 如果没找到,尝试只用景点名称搜索
            photo_url = await run_in_threadpool(unsplash_service.get_photo_url, name)

        # 取不到图不是"成功": 未配置 Unsplash key 或没搜到结果时如实报失败,
        # 前端 Result.vue 依赖 success 字段判断是否使用该 URL。
        if not photo_url:
            return {
                "success": False,
                "message": "未找到匹配的图片",
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

