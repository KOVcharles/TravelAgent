"""
WebUI API 请求体模型。

这里只放入站 request body 的 Pydantic schema，避免路由文件里散落模型定义。
响应结构暂时保持现状，没有在这里建 response schema。
"""
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    user_id: str


class ChatRequest(BaseModel):
    message: str


class SkillToggleRequest(BaseModel):
    enabled: bool


class OnboardingPreferenceRequest(BaseModel):
    key: str
    value: str


# ---------------------------------------------------------------------------
# 鉴权（v1.0，design.md §3.7）：注册 / 登录 / 刷新 的请求与响应模型。
# email 用 pydantic EmailStr；密码策略默认 min_length=8（questions.md Q-D）。
# 422 触发：email 非法 / password 长度不达标 → pydantic 校验失败 →
# 现有 validation_exception_handler 自动产出统一 422 结构（无需手写）。
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """注册 / JWT 登录入参：{email, password}（登录复用同一形状，见 design.md §3.8）。"""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    """登录/刷新返回体（严格遵循 PRD §3.4，不含 id；canonical id 由 token sub 承载）。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """注册成功返回体（仅 id/email；password_hash 与明文绝不外泄）。"""

    id: int
    email: EmailStr
