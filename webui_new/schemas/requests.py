"""
WebUI API 请求体模型。

这里只放入站 request body 的 Pydantic schema，避免路由文件里散落模型定义。
响应结构暂时保持现状，没有在这里建 response schema。
"""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    user_id: str


class ChatRequest(BaseModel):
    message: str


class OnboardingPreferenceRequest(BaseModel):
    key: str
    value: str
