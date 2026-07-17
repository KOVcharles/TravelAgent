"""
Logging safety helpers.

Use these helpers when logging exception text, model/tool payloads, or other
free-form values that may contain secrets or become very long. They keep Phase 1
simple: redact common sensitive fields and cap log value length.
"""
from __future__ import annotations

import re
from typing import Any

from utils.memory_safety import redact_sensitive_text

KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|passwd|pwd)(['\"]?\s*[:=]\s*['\"]?)[^,'\"\s}]+"
)
BEARER_TOKEN_RE = re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+")
POSTGRES_DSN_RE = re.compile(r"(?i)(postgres(?:ql)?://[^:\s]+:)[^@\s]+(@)")


def sanitize_for_log(value: Any, limit: int = 500) -> str:
    """Return a redacted, length-limited string safe enough for plain-text logs."""
    text = str(value)
    text = KEY_VALUE_SECRET_RE.sub(r"\1\2[REDACTED]", text)
    text = BEARER_TOKEN_RE.sub(r"\1[REDACTED]", text)
    text = POSTGRES_DSN_RE.sub(r"\1[REDACTED]\2", text)
    text = redact_sensitive_text(text)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"
