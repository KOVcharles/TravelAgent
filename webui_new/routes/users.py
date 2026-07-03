"""
用户实例相关 API。

本模块负责 user init/status/is-new/summary 这些围绕 WebHommeyManager
实例生命周期和用户摘要的接口。业务逻辑仍在 manager/instance 内部，
这里主要做 HTTP 边界处理和错误响应转换。
"""
import logging

from fastapi import APIRouter, Request

from utils.logging_safety import sanitize_for_log
from webui_new.core.errors import InternalError, request_id

logger = logging.getLogger(__name__)


def create_users_router(manager):
    """创建用户 router；manager 由 server.py 注入，便于测试替换。"""
    router = APIRouter(prefix="/api/{user_id}")

    @router.post("/init")
    async def initialize_user(request: Request, user_id: str):
        """初始化用户实例"""
        try:
            instance = await manager.initialize_user(user_id)
            return {"success": True, "initialized": instance.initialized}
        except Exception as e:
            logger.error("Init failed request_id=%s user_id=%s error=%s", request_id(request), user_id, sanitize_for_log(e))
            raise InternalError("INIT_FAILED", "初始化失败，请稍后刷新页面重试")

    @router.get("/status")
    async def get_status(user_id: str):
        """获取用户实例状态"""
        return manager.get_status(user_id)

    @router.get("/is-new")
    async def is_new_user(user_id: str):
        """检查是否为新用户"""
        instance = manager.get(user_id)
        if not instance or not instance.initialized:
            return {"is_new": True}
        try:
            is_new = await instance.is_new_user()
            return {"is_new": is_new}
        except Exception:
            return {"is_new": True}

    @router.get("/summary")
    async def get_user_summary(request: Request, user_id: str):
        """获取用户摘要信息（右侧面板）"""
        instance = manager.get(user_id)
        if not instance or not instance.initialized:
            return {
                "user_id": user_id,
                "name_display": user_id,
                "preferences": [],
                "member_level": "",
                "member_tag": "",
                "initialized": False,
            }
        try:
            summary = await instance.get_user_summary()
            summary["initialized"] = True
            return summary
        except Exception as e:
            logger.error("Summary failed request_id=%s user_id=%s error=%s", request_id(request), user_id, sanitize_for_log(e))
            return {
                "user_id": user_id,
                "name_display": user_id,
                "preferences": [],
                "member_level": "",
                "member_tag": "",
                "initialized": True,
            }

    return router
