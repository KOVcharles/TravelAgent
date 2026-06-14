"""
Runtime settings for the Aligo multi-agent system.

Do not put real API keys in this file. Set ALIGO_API_KEY in your shell or
local .env file instead.
"""
import os

from dotenv import load_dotenv
load_dotenv()  # 加载项目根目录的 .env 文件


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


LLM_CONFIG = {
    "api_key": os.getenv("ALIGO_API_KEY", ""),
    "model_name": os.getenv("ALIGO_MODEL_NAME", "deepseek-v3"),
    "base_url": os.getenv(
        "ALIGO_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "temperature": _float_env("ALIGO_TEMPERATURE", 0.7),
    "max_tokens": _int_env("ALIGO_MAX_TOKENS", 8192),
}


SYSTEM_CONFIG = {
    "enable_llm": _bool_env("ALIGO_ENABLE_LLM", True),
    "log_level": os.getenv("ALIGO_LOG_LEVEL", "INFO"),
    "max_retries": _int_env("ALIGO_SYSTEM_MAX_RETRIES", 3),
    "timeout": _int_env("ALIGO_TIMEOUT", 60),
}


RAG_CONFIG = {
    "embedding_model": os.getenv(
        "ALIGO_EMBEDDING_MODEL",
        "data/models/bge-small-zh-v1.5",
    ),
    "documents_dir": os.getenv(
        "ALIGO_RAG_DOCUMENTS_DIR",
        "data/documents",
    ),
    "knowledge_base_path": os.getenv(
        "ALIGO_RAG_KNOWLEDGE_BASE_PATH",
        "data/rag_knowledge",
    ),
    "collection_name": os.getenv(
        "ALIGO_RAG_COLLECTION",
        "business_travel_knowledge",
    ),
    "top_k": _int_env("ALIGO_RAG_TOP_K", 3),
    "vector_top_k": _int_env("ALIGO_RAG_VECTOR_TOP_K", 10),
    "bm25_top_k": _int_env("ALIGO_RAG_BM25_TOP_K", 10),
}


SKILL_CONFIG = {
    "root": os.getenv("ALIGO_SKILLS_ROOT", ".claude/skills"),
}


RESILIENCE_CONFIG = {
    "max_retries": _int_env("ALIGO_MAX_RETRIES", 3),
    "retry_base_delay_sec": _float_env("ALIGO_RETRY_BASE_DELAY_SEC", 1.0),
    "retry_max_delay_sec": _float_env("ALIGO_RETRY_MAX_DELAY_SEC", 30.0),
    "circuit_failure_threshold": _int_env("ALIGO_CIRCUIT_FAILURE_THRESHOLD", 5),
    "circuit_recovery_timeout_sec": _float_env(
        "ALIGO_CIRCUIT_RECOVERY_TIMEOUT_SEC",
        60.0,
    ),
    "circuit_half_open_successes": _int_env("ALIGO_CIRCUIT_HALF_OPEN_SUCCESSES", 2),
    "health_check_timeout_sec": _float_env("ALIGO_HEALTH_CHECK_TIMEOUT_SEC", 10.0),
}


MEMORY_CONFIG = {
    "short_term": {
        "backend": os.getenv("ALIGO_SHORT_TERM_BACKEND", "memory").lower(),
        "max_turns": _int_env("ALIGO_SHORT_TERM_MAX_TURNS", 10),
        "redis_host": os.getenv("ALIGO_REDIS_HOST", "127.0.0.1"),
        "redis_port": _int_env("ALIGO_REDIS_PORT", 6379),
        "redis_db": _int_env("ALIGO_REDIS_DB", 0),
        "redis_password": os.getenv("ALIGO_REDIS_PASSWORD") or None,
        "redis_key_prefix": os.getenv("ALIGO_REDIS_KEY_PREFIX", "aligo:short_term"),
    },
    "long_term": {
        "backend": os.getenv("ALIGO_LONG_TERM_BACKEND", "file").lower(),
        "storage_path": os.getenv("ALIGO_MEMORY_STORAGE_PATH", "data/memory"),
        "postgres_dsn": os.getenv("ALIGO_POSTGRES_DSN", ""),
    },
}


MCP_CONFIG = {
    "auto_connect": _bool_env("ALIGO_MCP_AUTO_CONNECT", True),
    "connect_timeout": _float_env("ALIGO_MCP_CONNECT_TIMEOUT", 10.0),
    "servers": {
        "filesystem": {
            "transport": "stdio",
            "command": os.getenv("ALIGO_MCP_FILESYSTEM_COMMAND", "npx"),
            "args": ["-y", "@anthropic/mcp-server-filesystem", "."],
            "env": {},
            "timeout": _float_env("ALIGO_MCP_FILESYSTEM_TIMEOUT", 30.0),
            "execution_timeout": _float_env(
                "ALIGO_MCP_FILESYSTEM_EXECUTION_TIMEOUT",
                60.0,
            ),
            "enabled": _bool_env("ALIGO_MCP_FILESYSTEM_ENABLED", False),
            "description": (
                "Filesystem operations: read, write, list, and create project files."
            ),
        },
    },
}
