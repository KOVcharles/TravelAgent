"""Structured logging helpers for Hommey services."""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from settings import SYSTEM_CONFIG
from utils.logging_safety import sanitize_for_log


STANDARD_LOG_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_for_log(record.getMessage()),
        }

        for key, value in record.__dict__.items():
            if key in STANDARD_LOG_RECORD_KEYS or key.startswith("_"):
                continue
            payload[key] = sanitize_for_log(value)

        if record.exc_info:
            payload["exception"] = sanitize_for_log(self.formatException(record.exc_info))

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(format_name: str | None = None, level: str | None = None) -> None:
    """Configure root logging once for CLI/WebUI entrypoints."""
    resolved_level = (level or SYSTEM_CONFIG.get("log_level") or "INFO").upper()
    resolved_format = (format_name or SYSTEM_CONFIG.get("log_format") or "text").lower()

    handler = logging.StreamHandler(sys.stdout)
    if resolved_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, resolved_level, logging.INFO))
