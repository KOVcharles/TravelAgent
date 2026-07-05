"""
鉴权安全原语：bcrypt 密码哈希 + JWT 签发/校验（access / refresh）。

安全红线（PRD §3.2 / §3.3 / §6）：
- 密码用 passlib bcrypt（cost=12）哈希；明文密码不入库、不入日志、不进异常 message。
- JWT claims 含 `sub`(= DB id)、`exp`、`iat`、`type∈{"access","refresh"}`。
- `HOMMEY_JWT_SECRET` 缺失（None/空）时，签发与校验**前**均抛 `ConfigError`，
  绝不使用硬编码默认值（`_require_secret`）。

可测试性：`AUTH_CONFIG` 每次 `_encode` / `decode_token` 调用时读取（不缓存到模块级
变量），便于测试用 monkeypatch 注入 secret / 过期值，无需真实环境变量。
"""
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from settings import AUTH_CONFIG
from webui_new.core.errors import ConfigError

# bcrypt cost ≥ 12（PRD §6）；passlib 通过 bcrypt__rounds 设定。
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

_ACCESS_ALGORITHM_FALLBACK = "HS256"


def hash_password(plain: str) -> str:
    """bcrypt 哈希明文密码。"""
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """常量时间校验密码；失败返回 False，不抛错（避免时序侧信道与上层异常处理耦合）。"""
    try:
        return _pwd_ctx.verify(plain, hashed)
    except (ValueError, TypeError):
        return False


def _require_secret() -> str:
    """读取 `AUTH_CONFIG['jwt_secret']`；缺失（None/空）抛 `ConfigError`，绝不硬编码默认。"""
    secret = AUTH_CONFIG.get("jwt_secret")
    if not secret:
        raise ConfigError(
            "JWT_SECRET_MISSING",
            "系统鉴权未配置（缺少 HOMMEY_JWT_SECRET），请联系管理员",
        )
    return secret


def _algorithm() -> str:
    return AUTH_CONFIG.get("jwt_algorithm") or _ACCESS_ALGORITHM_FALLBACK


def _encode(sub: int | str, token_type: str, delta: timedelta) -> str:
    """构造并签发 JWT。secret 缺失由 `_require_secret` 守护。"""
    secret = _require_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub),  # canonical user_id = DB id（与 route/deps 同源）
        "iat": now,
        "exp": now + delta,
        "type": token_type,
    }
    return jwt.encode(payload, secret, algorithm=_algorithm())


def create_access_token(sub: int | str) -> str:
    """签发 access token，默认 30 分钟。"""
    return _encode(
        sub,
        "access",
        timedelta(minutes=AUTH_CONFIG.get("access_expire_minutes", 30)),
    )


def create_refresh_token(sub: int | str) -> str:
    """签发 refresh token，默认 7 天。"""
    return _encode(
        sub,
        "refresh",
        timedelta(days=AUTH_CONFIG.get("refresh_expire_days", 7)),
    )


def decode_token(token: str) -> dict:
    """校验并解码 JWT；签名/过期/格式错误抛 `jwt.PyJWTError`，由 deps 层捕获转 401。

    同样先走 `_require_secret()`，满足「校验前 secret 缺失必抛错」——此时抛的是
    `ConfigError`（500），而非 PyJWTError（→401），与 §7 错误码映射一致。
    """
    secret = _require_secret()
    return jwt.decode(token, secret, algorithms=[_algorithm()])
