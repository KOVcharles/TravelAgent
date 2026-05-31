"""
Aligo 商旅助手 - FastAPI Web 服务
提供聊天 API 和页面路由
"""
import json
import logging
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)

# ── FastAPI 应用 ──────────────────────────────────────────
app = FastAPI(title="Aligo 商旅助手", version="2.0.0")

# ── 静态文件 & 模板 ──────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
jinja_env = Environment(
    loader=FileSystemLoader(templates_dir),
    enable_async=False,
)


def _render(template_name: str, **context) -> HTMLResponse:
    """Render a Jinja2 template and return HTMLResponse."""
    template = jinja_env.get_template(template_name)
    html = template.render(**context)
    return HTMLResponse(html)

# ── 管理器 ────────────────────────────────────────────────
from webui_new.manager import WebAligoManager

manager = WebAligoManager()


# ── 数据模型 ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    user_id: str


class ChatRequest(BaseModel):
    message: str


# ── 页面路由 ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def login_page():
    """登录页"""
    return _render("login.html")


@app.post("/login")
async def login(data: LoginRequest):
    """提交用户 ID"""
    user_id = data.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="请输入用户 ID")
    return {"redirect": f"/chat/{user_id}"}


@app.get("/chat/{user_id}", response_class=HTMLResponse)
async def chat_page(user_id: str):
    """聊天主页面"""
    return _render("chat.html", user_id=user_id)


# ── API 路由 ──────────────────────────────────────────────

@app.post("/api/{user_id}/init")
async def initialize_user(user_id: str):
    """初始化用户实例"""
    try:
        instance = await manager.initialize_user(user_id)
        return {
            "success": True,
            "initialized": instance.initialized,
        }
    except Exception as e:
        logger.error(f"Init failed for {user_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )


@app.get("/api/{user_id}/status")
async def get_status(user_id: str):
    """获取用户实例状态"""
    return manager.get_status(user_id)


@app.get("/api/{user_id}/is-new")
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


@app.get("/api/{user_id}/summary")
async def get_user_summary(user_id: str):
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
        logger.error(f"Summary failed for {user_id}: {e}")
        return {
            "user_id": user_id,
            "name_display": user_id,
            "preferences": [],
            "member_level": "",
            "member_tag": "",
            "initialized": True,
        }


@app.post("/api/{user_id}/chat")
async def send_message(user_id: str, data: ChatRequest):
    """发送消息并获取回复"""
    instance = manager.get(user_id)
    if not instance or not instance.initialized:
        return JSONResponse(
            status_code=400,
            content={"error": "系统未初始化，请刷新页面"},
        )

    if not data.message.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "请输入消息"},
        )

    try:
        logger.info(f"[{user_id}] ➤ {data.message}")
        result = await instance.process_message(data.message)
        logger.info(f"[{user_id}] ◀ {result.get('response', '')[:80]}...")
        return result
    except Exception as e:
        logger.error(f"Chat failed for {user_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"处理失败: {str(e)}"},
        )
