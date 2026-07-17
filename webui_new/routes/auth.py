"""
鉴权路由（v1.0，design.md §3.8）。

- POST /auth/register  注册（bcrypt 哈希）→ 201 {id,email}；重复邮箱 → 409
- POST /auth/login     校验密码 → 200 {access_token, refresh_token}；失败 → 401
- POST /auth/refresh   校验 refresh token → 200 新 access_token（refresh 不轮换）
- POST /login          [deprecated] 旧 user_id 直跳转入口，保留以兼容前端/既有测试

安全要点：
- 密码常量时间校验：用户不存在时也对固定假哈希跑一次 bcrypt verify，使「邮箱不存在」
  与「密码错误」两条路径耗时一致，防响应耗时枚举有效邮箱。
- 密码与 token 原文不入日志。
- 登录/刷新响应不回 id；canonical id 由 access token 的 sub claim 承载。
- register 内幂等建表（design.md §2.3 主路径：代码内 `CREATE TABLE IF NOT EXISTS`）。
"""
import jwt
from fastapi import APIRouter

from webui_new.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from webui_new.auth.storage import (
    apply_migration,
    create_user,
    get_conn,
    get_user_by_email,
)
from webui_new.core.errors import BusinessError, ValidationError
from webui_new.schemas.requests import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

# 常量时间登录所需：用户不存在时对这个固定假哈希跑一次 bcrypt verify。
# 模块级计算一次（cost=12），之后只读；本身不是任何真实账号的密码。
_DUMMY_PASSWORD_HASH = hash_password("constant-time-dummy-do-not-use")


def create_auth_router():
    """创建 auth router：保留旧 /login（根路径）+ 新 /auth/* 鉴权入口（无 prefix）。"""
    router = APIRouter()

    @router.post("/login", deprecated=True, summary="[deprecated] 提交用户 ID 直跳转")
    async def login(data: LoginRequest):
        """[deprecated] 旧入口：收集 user_id 并跳转，无真实认证。保留以兼容前端。"""
        user_id = data.user_id.strip()
        if not user_id:
            raise ValidationError("BAD_REQUEST", "请输入用户 ID")
        return {"redirect": f"/chat/{user_id}"}

    @router.post("/auth/register", response_model=UserResponse, status_code=201)
    async def register(data: RegisterRequest):
        """注册：邮箱 + 密码 → bcrypt 哈希落库；重复邮箱 → 409。"""
        email = data.email.strip()
        if not email or not data.password:
            raise ValidationError("BAD_REQUEST", "请输入邮箱和密码")
        with get_conn() as conn:
            apply_migration(conn)  # 幂等：首次注册自动建表
            if get_user_by_email(conn, email):
                raise BusinessError("EMAIL_ALREADY_EXISTS", "该邮箱已注册", status_code=409)
            user = create_user(conn, email, hash_password(data.password))
        return UserResponse(id=user.id, email=user.email)

    @router.post("/auth/login", response_model=TokenResponse)
    async def login_jwt(data: RegisterRequest):
        """登录：校验密码 → 签发 access + refresh；任一失败 → 401（文案不区分原因）。"""
        email = data.email.strip()
        if not email or not data.password:
            raise ValidationError("BAD_REQUEST", "请输入邮箱和密码")
        with get_conn() as conn:
            user = get_user_by_email(conn, email)
        # 常量时间：用户不存在也对假哈希跑一次 verify，防邮箱枚举探针。
        stored_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
        ok = verify_password(data.password, stored_hash)
        if not user or not ok:
            raise BusinessError("UNAUTHORIZED", "邮箱或密码错误", status_code=401)
        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    @router.post("/auth/refresh", response_model=TokenResponse)
    async def refresh(data: RefreshRequest):
        """刷新：校验 refresh token(type) → 重签 access；失败 → 401。v1 不轮换 refresh。"""
        try:
            payload = decode_token(data.refresh_token)
        except jwt.PyJWTError:
            raise BusinessError("UNAUTHORIZED", "刷新令牌无效或已过期，请重新登录", status_code=401)
        if payload.get("type") != "refresh":
            raise BusinessError("UNAUTHORIZED", "刷新令牌无效或已过期，请重新登录", status_code=401)
        try:
            sub = int(payload["sub"])
        except (KeyError, ValueError, TypeError):
            raise BusinessError("UNAUTHORIZED", "刷新令牌无效或已过期，请重新登录", status_code=401)
        return TokenResponse(
            access_token=create_access_token(sub),
            refresh_token=data.refresh_token,  # v1 不轮换：回传同一 refresh
        )

    return router
