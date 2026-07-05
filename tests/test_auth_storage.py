"""
鉴权用户存储层测试（design.md §9.2）。

沿用 `tests/test_long_term_memory_postgres.py` 的 RecordingConnection 风格假连接：
注入记录 execute 调用、可配置 fetchone 返回的假 cursor，无需真实 PG（storage.py
惰性导入 psycopg，使模块本身在无 psycopg 环境下也可导入）。
"""
from webui_new.auth.storage import (
    User,
    apply_migration,
    create_user,
    get_user_by_email,
    get_user_by_id,
)

_PLAINTEXT = "supersecret-123"


class _FakeCursor:
    def __init__(self, fetchone_value=None):
        self.calls = []  # [(sql, params), ...]
        self._fetchone_value = fetchone_value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchone(self):
        return self._fetchone_value


class _FakeConnection:
    """单 cursor 假连接：每个 storage 函数各自 `with conn.cursor()`，单语句足够。"""

    def __init__(self, fetchone_value=None):
        self.cursor_obj = _FakeCursor(fetchone_value)

    def cursor(self):
        return self.cursor_obj

    @property
    def executed(self):
        return self.cursor_obj.calls


def _row(**overrides):
    base = {
        "id": 7,
        "email": "alice@example.com",
        "password_hash": "BCRYPT_HASH_VALUE",  # 假哈希；明文密码从不落库
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# apply_migration（幂等建表）
# ---------------------------------------------------------------------------

def test_apply_migration_uses_create_table_if_not_exists():
    conn = _FakeConnection()

    apply_migration(conn)

    assert len(conn.executed) == 1
    sql = conn.executed[0][0]
    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert "users" in sql
    # 关键列都在。
    for column in ("id", "email", "password_hash", "created_at"):
        assert column in sql


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------

def test_create_user_inserts_hashed_password_and_returns_user():
    conn = _FakeConnection(fetchone_value=_row(id=42, email="bob@example.com"))

    user = create_user(conn, "bob@example.com", "BCRYPT_HASH_VALUE")

    assert isinstance(user, User)
    assert user.id == 42
    assert user.email == "bob@example.com"

    sql, params = conn.executed[0]
    assert "INSERT INTO users" in sql
    assert "RETURNING" in sql
    # 参数只含 email 与 hash，绝不含明文密码。
    assert params == ("bob@example.com", "BCRYPT_HASH_VALUE")
    assert _PLAINTEXT not in params


def test_create_user_returning_includes_password_hash_column():
    """RETURNING 子句须带回 password_hash，使 create_user 返回完整可登录的 User。"""
    conn = _FakeConnection(fetchone_value=_row(id=42, email="bob@example.com"))

    user = create_user(conn, "bob@example.com", "BCRYPT_HASH_VALUE")

    sql, _ = conn.executed[0]
    assert "password_hash" in sql
    assert user.password_hash == "BCRYPT_HASH_VALUE"


# ---------------------------------------------------------------------------
# get_user_by_email
# ---------------------------------------------------------------------------

def test_get_user_by_email_returns_user_when_present():
    conn = _FakeConnection(fetchone_value=_row(email="alice@example.com"))

    user = get_user_by_email(conn, "alice@example.com")

    assert isinstance(user, User)
    assert user.email == "alice@example.com"
    sql, params = conn.executed[0]
    assert "WHERE email" in sql
    assert params == ("alice@example.com",)


def test_get_user_by_email_exposes_password_hash_not_plaintext():
    """登录契约核心（回应 Reviewer 严重项）：email 查询必须带回 password_hash，
    否则 `POST /auth/login` 无法做 bcrypt 校验。同时明文密码绝不出现。"""
    conn = _FakeConnection(fetchone_value=_row(email="alice@example.com"))

    user = get_user_by_email(conn, "alice@example.com")

    # SELECT 列表必须含 password_hash——这是上一轮漏掉的契约。
    sql, params = conn.executed[0]
    assert "SELECT" in sql
    assert "password_hash" in sql

    # 返回的 User 必须携带存储的哈希，供 route 层 verify_password 使用。
    assert user is not None
    assert user.password_hash == "BCRYPT_HASH_VALUE"
    # 明文密码在任何地方都不应出现（params 仅含查询 email）。
    assert _PLAINTEXT not in params
    assert _PLAINTEXT != user.password_hash


def test_get_user_by_email_returns_none_when_absent():
    conn = _FakeConnection(fetchone_value=None)

    user = get_user_by_email(conn, "nobody@example.com")

    assert user is None
    assert conn.executed[0][1] == ("nobody@example.com",)


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------

def test_get_user_by_id_returns_user_when_present():
    conn = _FakeConnection(fetchone_value=_row(id=42))

    user = get_user_by_id(conn, 42)

    assert isinstance(user, User)
    assert user.id == 42
    sql, params = conn.executed[0]
    assert "WHERE id" in sql
    assert params == (42,)


def test_get_user_by_id_returns_none_when_absent():
    conn = _FakeConnection(fetchone_value=None)

    user = get_user_by_id(conn, 999)

    assert user is None
    assert conn.executed[0][1] == (999,)
