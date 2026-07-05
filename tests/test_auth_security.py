"""
鉴权安全原语单元测试（design.md §9.2，纯单元，无 DB）。

`security.py` 每次签发/校验都读取 `AUTH_CONFIG`（不缓存），故通过 monkeypatch
就地修改 `security.AUTH_CONFIG`（与 `settings.AUTH_CONFIG` 同一 dict 对象）注入
测试用 secret / 过期值，无需真实环境变量。
"""
import jwt
import pytest

from settings import AUTH_CONFIG as SETTINGS_AUTH_CONFIG
from webui_new.auth import security
from webui_new.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from webui_new.core.errors import ConfigError

# security.AUTH_CONFIG 与 settings.AUTH_CONFIG 是同一 dict 对象——断言一次以防回归。
assert security.AUTH_CONFIG is SETTINGS_AUTH_CONFIG

_TEST_SECRET = "test-secret-not-for-production-0123456789"


@pytest.fixture
def secret(monkeypatch):
    """为正向用例注入确定性 secret（不依赖 .env 的真实 HOMMEY_JWT_SECRET）。"""
    monkeypatch.setitem(security.AUTH_CONFIG, "jwt_secret", _TEST_SECRET)
    return _TEST_SECRET


# ---------------------------------------------------------------------------
# 密码哈希（bcrypt）
# ---------------------------------------------------------------------------

def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"  # 不存明文
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_verify_password_constant_output():
    # 错误密码 / 畸形 hash 都返回 False，不抛错（便于常量时间上层逻辑）。
    assert verify_password("anything", "not-a-valid-bcrypt-hash") is False


def test_hashed_password_is_bcrypt_format():
    hashed = hash_password("supersecret-123")

    # bcrypt 输出以 $2 前缀开头；明文绝不应出现。
    assert hashed.startswith("$2")
    assert "supersecret-123" not in hashed


# ---------------------------------------------------------------------------
# JWT 签发
# ---------------------------------------------------------------------------

def test_create_access_token_has_correct_claims(secret):
    token = create_access_token(42)

    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["iat"] is not None
    # iat 与 exp 来自同一 now，差值 == 配置的 30 分钟（秒级精确）。
    assert payload["exp"] - payload["iat"] == 30 * 60


def test_create_refresh_token_type_is_refresh(secret):
    token = create_refresh_token(7)

    payload = decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["sub"] == "7"
    # 7 天（秒级精确）。
    assert payload["exp"] - payload["iat"] == 7 * 24 * 60 * 60


def test_decode_token_verifies(secret):
    token = create_access_token(99)

    payload = decode_token(token)
    assert payload["sub"] == "99"
    assert payload["type"] == "access"


def test_decode_token_rejects_tampered(secret):
    token = create_access_token(1)

    # 篡改签名末尾字符 → 验签失败。
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(jwt.PyJWTError):
        decode_token(tampered)


def test_decode_token_rejects_expired(secret, monkeypatch):
    # 让 access token 的 delta 为负 → exp 已过。
    monkeypatch.setitem(security.AUTH_CONFIG, "access_expire_minutes", -1)
    token = create_access_token(1)

    with pytest.raises(jwt.PyJWTError):
        decode_token(token)


def test_access_and_refresh_types_are_not_interchangeable(secret):
    access = create_access_token(1)
    refresh = create_refresh_token(1)

    assert decode_token(access)["type"] == "access"
    assert decode_token(refresh)["type"] == "refresh"
    assert decode_token(access)["type"] != decode_token(refresh)["type"]


# ---------------------------------------------------------------------------
# secret 缺失守护（PRD §3.3 / §6 安全红线）
# ---------------------------------------------------------------------------

def test_secret_missing_raises_on_sign(monkeypatch):
    monkeypatch.setitem(security.AUTH_CONFIG, "jwt_secret", None)

    with pytest.raises(ConfigError):
        create_access_token(1)


def test_secret_missing_raises_on_verify(monkeypatch):
    # 先用一个已知 secret 签出合法 token，再清空 secret 校验——校验前必抛 ConfigError。
    monkeypatch.setitem(security.AUTH_CONFIG, "jwt_secret", _TEST_SECRET)
    token = create_refresh_token(1)
    monkeypatch.setitem(security.AUTH_CONFIG, "jwt_secret", "")

    with pytest.raises(ConfigError):
        decode_token(token)
