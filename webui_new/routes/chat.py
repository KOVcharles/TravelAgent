"""
聊天 API 路由。

包含普通 chat 和 NDJSON stream 两个入口。路由层只做输入检查、调用
HommeyWebInstance，以及把异常转换成当前统一错误响应。
具体意图识别、编排、记忆更新等业务逻辑仍在 manager/agents 中。
"""
import json
import logging
import asyncio
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from utils.logging_safety import sanitize_for_log
from utils.observability import COMPONENT_HTTP, record_app_error, record_http_request
from webui_new.core.errors import AppError, BusinessError, InternalError, request_id, stream_error_event
from webui_new.schemas.requests import ChatRequest

logger = logging.getLogger(__name__)


def create_chat_router(manager):
    """创建聊天 router；manager 由 server.py 注入，避免反向 import server。"""
    router = APIRouter()

    @router.post("/api/{user_id}/chat")
    async def send_message(request: Request, user_id: str, data: ChatRequest):
        """发送消息并获取回复"""
        instance = manager.get(user_id)
        if not instance or not instance.initialized:
            raise BusinessError("NOT_INITIALIZED", "系统未初始化，请刷新页面")

        if not data.message.strip():
            raise BusinessError("EMPTY_MESSAGE", "请输入消息")

        try:
            logger.info(f"[{user_id}] ➤ {data.message}")
            result = await instance.process_message(data.message)
            logger.info(f"[{user_id}] ◀ {result.get('response', '')[:80]}...")
            return result
        except AppError:
            raise
        except Exception as e:
            logger.error("Chat failed request_id=%s user_id=%s error=%s", request_id(request), user_id, sanitize_for_log(e))
            raise InternalError("CHAT_FAILED", "处理失败，请稍后重试")

    @router.post("/api/{user_id}/chat/stream")
    async def stream_message(request: Request, user_id: str, data: ChatRequest):
        """Stream chat progress and response chunks as newline-delimited JSON."""
        instance = manager.get(user_id)
        if not instance or not instance.initialized:
            raise BusinessError("NOT_INITIALIZED", "系统未初始化，请刷新页面")

        if not data.message.strip():
            raise BusinessError("EMPTY_MESSAGE", "请输入消息")

        async def event_stream():
            """把 instance.stream_message() 的事件逐行编码为 NDJSON。"""
            started_at = time.perf_counter()
            try:
                logger.info(f"[{user_id}] -> {data.message}")
                async for event in instance.stream_message(data.message):
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except asyncio.CancelledError:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                record_app_error(COMPONENT_HTTP, "STREAM_CANCELLED", 499)
                record_http_request(request.url.path, request.method, 499, duration_ms)
                logger.warning(
                    "stream_cancelled",
                    extra={
                        "request_id": request_id(request),
                        "user_id": user_id,
                        "route": request.url.path,
                        "method": request.method,
                        "status_code": 499,
                        "error_code": "STREAM_CANCELLED",
                        "component": COMPONENT_HTTP,
                        "duration_ms": duration_ms,
                        "debug_message": "client disconnected while reading stream",
                    },
                )
                raise
            except Exception as e:
                rid = request_id(request)
                logger.error("Streaming chat failed request_id=%s user_id=%s error=%s", rid, user_id, sanitize_for_log(e))
                stream_exc = e if isinstance(e, AppError) else InternalError("STREAM_FAILED", "处理失败，请稍后重试")
                yield json.dumps(stream_error_event(request, stream_exc), ensure_ascii=False) + "\n"

        return StreamingResponse(
            event_stream(),
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Cache-Control": "no-cache"},
        )

    return router
