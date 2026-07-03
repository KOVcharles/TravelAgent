"""
登录相关路由。

当前登录只是收集 user_id 并跳转到聊天页，没有真正认证/鉴权。
后续如果加入 session、cookie 或 token，可以从这个模块开始扩展。
"""
from fastapi import APIRouter

from webui_new.core.errors import ValidationError
from webui_new.schemas.requests import LoginRequest


def create_auth_router():
    """创建 auth router，保持 /login 路径和原返回结构不变。"""
    router = APIRouter()

    @router.post("/login")
    async def login(data: LoginRequest):
        """提交用户 ID"""
        user_id = data.user_id.strip()
        if not user_id:
            raise ValidationError("BAD_REQUEST", "请输入用户 ID")
        return {"redirect": f"/chat/{user_id}"}

    return router
