"""旅行规划API路由"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ...models.schemas import (
    TripRequest,
    TripPlanResponse
)
from ...agents.trip_planner_agent import (
    get_trip_planner_agent,
    is_trip_planner_initialized,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trip", tags=["旅行规划"])

# SSE 心跳间隔（秒）。planner 那一步可能跑几十秒且中间没有阶段事件，
# 部分反向代理/浏览器会认为连接空闲而断开，定期发注释行保活。
SSE_HEARTBEAT_SECONDS = 15


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应

    注意降级语义:
        多智能体链路失败时, Agent 会返回 is_fallback=True 的占位计划而不是抛异常
        (保留可用性)。此时 HTTP 仍是 200, 但 message 会如实说明, 且 data 里带
        is_fallback 标记 —— 前端必须据此显示警告, 不能把占位内容当真实行程展示。
    """
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'='*60}\n")

        # 获取Agent实例
        print("🔄 获取多智能体系统实例...")
        agent = get_trip_planner_agent()

        # 生成旅行计划
        # 走并发版: 景点/天气/酒店三路并行, 第四个 Agent 等前三步完成。
        # (同步版 agent.plan_trip 仍保留, 供既有调用方与测试使用)
        print("🚀 开始生成旅行计划...")
        trip_plan = await agent.plan_trip_async(request)

        if trip_plan.is_fallback:
            # 降级了: 200 保留(前端能拿到结构化数据), 但必须如实告知
            logger.warning("行程生成降级为占位数据: %s", trip_plan.fallback_reason)
            print("⚠️ 旅行计划生成降级为占位数据\n")
            return TripPlanResponse(
                success=True,
                message="未能生成真实行程，当前为占位数据，请稍后重试",
                data=trip_plan
            )

        print("✅ 旅行计划生成成功,准备返回响应\n")
        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan
        )

    except Exception:
        # 详细堆栈只写日志。回传给客户端的信息必须是不含内部细节的通用文案,
        # 否则会泄漏文件路径、依赖版本, 甚至异常信息里夹带的密钥片段。
        logger.exception("生成旅行计划失败")
        raise HTTPException(
            status_code=500,
            detail="生成旅行计划失败，请稍后重试"
        )


@router.post(
    "/plan-stream",
    summary="生成旅行计划（SSE 实时进度）",
    description=(
        "与 POST /api/trip/plan 返回相同的最终结果，但以 text/event-stream "
        "逐条推送真实执行进度。事件格式：data: {\"stage\",\"percent\",\"status\"[,\"data\"]}\n\n"
        "前端用 fetch + ReadableStream 读取（EventSource 只支持 GET，无法携带请求体）。"
    )
)
async def plan_trip_stream(request: TripRequest):
    """SSE 版生成旅行计划。

    为什么需要它：
        原先前端进度条是 setInterval 每 1.5s 硬涨 5%，和真实执行毫无关系 ——
        「正在查询天气」时后端可能还在搜景点。这里把 Agent 流水线各阶段的
        真实完成情况推给前端，进度条才可信。

    实现要点：
        - 用 asyncio.Queue 解耦「生产事件」与「消费事件」：
          Agent 在后台任务里跑，事件流在响应生成器里读。
        - 队列里放 None 作为结束哨兵（区别于正常事件字典）。
        - 客户端断开时生成器被关闭，finally 里取消后台任务，
          避免白跑一次完整的 LLM 调用。
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(stage: str, percent: int, status: str, data=None) -> None:
        payload = {"stage": stage, "percent": percent, "status": status}
        if data is not None:
            payload["data"] = data
        await queue.put(payload)

    async def run() -> None:
        """后台执行完整流水线，把进度与最终结果写进队列。"""
        try:
            agent = get_trip_planner_agent()
            trip_plan = await agent.plan_trip_async(request, progress=emit)

            if trip_plan.is_fallback:
                logger.warning("行程生成降级为占位数据: %s", trip_plan.fallback_reason)
                message_text = "未能生成真实行程，当前为占位数据，请稍后重试"
            else:
                message_text = "旅行计划生成成功"

            # 最终结果放在 done 事件里，结构刻意与 /plan 的响应体保持一致，
            # 前端可以直接复用同一套处理逻辑。
            await emit("done", 100, "✅ 完成", {
                "success": True,
                "message": message_text,
                "data": trip_plan.model_dump(mode="json"),
            })
        except Exception:
            # 详细堆栈只写日志，回传给客户端的是不含内部细节的通用文案
            logger.exception("生成旅行计划失败(SSE)")
            await emit("error", 0, "生成旅行计划失败，请稍后重试")
        finally:
            await queue.put(None)

    task = asyncio.create_task(run())

    async def event_stream():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=SSE_HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    # SSE 注释行：客户端会忽略，但能保活连接
                    yield ": keep-alive\n\n"
                    continue

                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关闭 nginx 的响应缓冲，否则事件会被攒起来一次性下发
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查。

    只报告进程状态与「是否已初始化」, **不主动触发初始化**。
    早期版本在这里直接调用 get_trip_planner_agent(), 首次探活会同步执行
    MCP 握手 + 4 个 Agent 创建(约 5 秒), 监控系统很容易判定为超时。
    """
    initialized = is_trip_planner_initialized()

    result = {
        "status": "healthy",
        "service": "trip-planner",
        "agent_initialized": initialized,
    }

    # 已经初始化过就顺带报出详情(此时取实例没有额外成本)
    if initialized:
        try:
            planner = get_trip_planner_agent()
            sub_agents = planner.list_agents()
            result.update({
                "agent_name": planner.name,
                "agents_count": len(sub_agents),
                "agents": {
                    role: len(sub_agent.list_tools())
                    for role, sub_agent in sub_agents.items()
                },
                "tools_count": len(planner.list_tools()),
            })
        except Exception as e:
            logger.exception("读取多智能体状态失败")
            result["status"] = "degraded"
            result["error"] = type(e).__name__

    return result
