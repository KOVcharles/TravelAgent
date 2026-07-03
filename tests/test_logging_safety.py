"""
Minimal contract tests for log redaction/truncation.

These tests lock the Phase 1 logging rule: free-form log values should not emit
obvious secrets or unbounded payloads.
"""
from utils.logging_safety import sanitize_for_log


def test_sanitize_for_log_redacts_common_secrets():
    value = "api_key=abc token: def password='ghi' Authorization: Bearer secret.jwt"

    sanitized = sanitize_for_log(value)

    assert "abc" not in sanitized
    assert "def" not in sanitized
    assert "ghi" not in sanitized
    assert "secret.jwt" not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitize_for_log_redacts_postgres_password_and_truncates():
    value = "postgresql://hommey:secret-db@localhost:5432/hommey " + "x" * 100

    sanitized = sanitize_for_log(value, limit=80)

    assert "secret-db" not in sanitized
    assert "postgresql://hommey:[REDACTED]@localhost" in sanitized
    assert sanitized.endswith("...[truncated]")
