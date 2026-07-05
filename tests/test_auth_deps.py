"""
get_current_user / require_path_user 依赖链测试（design.md §9.3）。

通过 monkeypatch `webui_new.auth.deps` 里导入的 `get_conn` / `get_user_by_id` 注入
内存存储，使 **真实的 token 解码 + 身份一致性校验** 完整跑通，覆盖：
- 未登录 / 无效 / 篡改 / 过期 / refresh 当 access → 401
- 已登录但访问他人 path user_id → 403 FORBIDDEN（IDOR 防护，方案 B）
- 本人访问 → 200
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from webui_new.auth import security
from webui_new.auth.deps import require_path_user
from webui_new.auth.security import create_access_token, create_refresh_token
from webui_new.auth.storage import User
from webui_new.core.errors import register_error_handlers
import webui_new.auth.deps as deps_module

_TEST_SECRET = "test-secret-not-for-production-0123456789"


class _FakeStore:
    def __init__(self):
        self.by_id: dict[int, User] = {}

    def get_conn(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add(self, user: User):
        self.by_id[user.id] = user

    def get_user_by_id(self, conn, user_id):
        return self.by_id.get(int(user_id))


def _make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/api/{user_id}/ping")
    async def ping(user_id: str, current_user: User = Depends(require_path_user)):
        return {"ok": True, "uid": current_user.id}

    return app


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setitem(security.AUTH_CONFIG, "jwt_secret", _TEST_SECRET)
    store = _FakeStore()
    monkeypatch.setattr(deps_module, "get_conn", store.get_conn)
    monkeypatch.setattr(deps_module, "get_user_by_id", store.get_user_by_id)
    return TestClient(_make_app()), store


def _add_user(store, uid=42) -> User:
    user = User(id=uid, email=f"u{uid}@example.com", password_hash="x", created_at="2026-01-01T00:00:00+00:00")
    store.add(user)
    return user


# ---------------------------------------------------------------------------
# 401：未登录 / token 问题
# ---------------------------------------------------------------------------

def test_missing_token_is_401(env):
    c, store = env
    _add_user(store, 42)
    assert c.get("/api/42/ping").status_code == 401


def test_tampered_token_is_401(env):
    c, store = env
    _add_user(store, 42)
    token = create_access_token(42)
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    r = c.get("/api/42/ping", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


def test_expired_access_token_is_401(env, monkeypatch):
    c, store = env
    _add_user(store, 42)
    monkeypatch.setitem(security.AUTH_CONFIG, "access_expire_minutes", -1)
    token = create_access_token(42)
    r = c.get("/api/42/ping", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_refresh_token_used_as_access_is_401(env):
    c, store = env
    _add_user(store, 42)
    token = create_refresh_token(42)
    r = c.get("/api/42/ping", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_token_for_unknown_user_is_401(env):
    c, _ = env  # 不添加任何用户
    token = create_access_token(999)
    r = c.get("/api/999/ping", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 403：横向越权（IDOR）防护 —— 方案 B 核心
# ---------------------------------------------------------------------------

def test_cross_user_access_is_403(env):
    c, store = env
    _add_user(store, 42)
    _add_user(store, 99)
    token = create_access_token(42)  # 以 42 身份登录
    r = c.get("/api/99/ping", headers={"Authorization": f"Bearer {token}"})  # 访问 99 的数据
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


# ---------------------------------------------------------------------------
# 200：本人访问放行
# ---------------------------------------------------------------------------

def test_owner_access_is_200(env):
    c, store = env
    _add_user(store, 42)
    token = create_access_token(42)
    r = c.get("/api/42/ping", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "uid": 42}
