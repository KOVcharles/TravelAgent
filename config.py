"""
Configuration for the Aligo Multi-Agent System
"""
import os

# LLM Configuration
LLM_CONFIG = {
    "api_key": "sk-1adc9fd1d29041e7a7433cb46a930af8",
    "model_name": "deepseek-v3",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "temperature": 0.7,
    "max_tokens": 8192,
}

# System Configuration
SYSTEM_CONFIG = {
    "enable_llm": True,  # Set to True to use LLM (recommended), False for rule-based
    "log_level": "INFO",
    "max_retries": 3,
    "timeout": 60,  # Increased timeout for better stability
}

# RAG 知识库：嵌入模型（本地路径，无需连 HuggingFace）
RAG_CONFIG = {
    "embedding_model": "data/models/bge-small-zh-v1.5",
}

# 连接与可用性：重试、熔断、健康检查
RESILIENCE_CONFIG = {
    "max_retries": 3,              # 单次请求最大重试次数（与 SYSTEM_CONFIG 对齐）
    "retry_base_delay_sec": 1.0,   # 重试退避基数（秒）
    "retry_max_delay_sec": 30.0,   # 重试退避上限（秒）
    "circuit_failure_threshold": 5, # 连续失败多少次后熔断
    "circuit_recovery_timeout_sec": 60.0,  # 熔断后多少秒进入半开
    "circuit_half_open_successes": 2,      # 半开状态下连续成功多少次后关闭
    "health_check_timeout_sec": 10.0,      # 健康检查请求超时（秒）
}

# Memory Configuration
MEMORY_CONFIG = {
    "short_term": {
        # 本地调试默认使用 memory，无需 Redis。
        # 设置 ALIGO_SHORT_TERM_BACKEND=redis 可切换到 Redis。
        # 可选值："memory" | "redis"
        "backend": os.getenv("ALIGO_SHORT_TERM_BACKEND", "memory").lower(),
        "max_turns": 10,
        "redis_host": "127.0.0.1",
        "redis_port": 6379,
        "redis_db": 0,
        "redis_password": None,
        "redis_key_prefix": "aligo:short_term",
    },
    "long_term": {
        # 本地调试快捷开关：默认使用 file，无需 PostgreSQL。
        # 设置 ALIGO_LONG_TERM_BACKEND=postgres 可切换到 PostgreSQL。
        # 可选值："file" | "postgres" | "disabled"
        "backend": os.getenv("ALIGO_LONG_TERM_BACKEND", "file").lower(),
        "storage_path": os.getenv("ALIGO_MEMORY_STORAGE_PATH", "data/memory"),
        # PostgreSQL 模式下必填，示例:
        # postgresql://postgres:password@127.0.0.1:5432/aligo
        "postgres_dsn": os.getenv("ALIGO_POSTGRES_DSN", ""),
    },
}

# MCP (Model Context Protocol) Configuration
# 双向 MCP 集成：消费外部 MCP Server 的工具，同时暴露 Aligo 能力为 MCP Server
MCP_CONFIG = {
    # 是否在 CLI 启动时自动连接 MCP Server
    "auto_connect": True,
    # 连接超时（秒）
    "connect_timeout": 10.0,
    # MCP Server 列表
    "servers": {
        # --- 文件系统 MCP Server（官方 @anthropic/mcp-server-filesystem）---
        # 使用前需安装: npm install -g @anthropic/mcp-server-filesystem
        # 或通过 npx 自动下载运行
        "filesystem": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@anthropic/mcp-server-filesystem", "."],
            "env": {},
            "timeout": 30.0,
            "execution_timeout": 60.0,
            "enabled": os.getenv("ALIGO_MCP_FILESYSTEM_ENABLED", "false").lower() == "true",
            "description": "文件系统操作：读写文件、创建目录、列出文件等",
        },
        # --- 更多 MCP Server 示例（按需启用）---
        # "weather": {
        #     "transport": "http_stateless",
        #     "url": "http://localhost:8000/mcp",
        #     "http_transport": "streamable_http",
        #     "headers": {},
        #     "timeout": 15.0,
        #     "execution_timeout": 30.0,
        #     "enabled": False,
        #     "description": "天气查询 MCP Server",
        # },
    },
}
