"""
Configuration Template for the Aligo Multi-Agent System
复制此文件为 config.py 并填入你的 API Key
"""
# LLM Configuration
LLM_CONFIG = {
    "api_key": "your-api-key-here",          # 替换为你的 API Key
    "model_name": "deepseek-v4-flash",        # 或 deepseek-v3 / 其他模型
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",  # 或 https://api.deepseek.com/v1
    "temperature": 0.7,
    "max_tokens": 8192,
}

# System Configuration
SYSTEM_CONFIG = {
    "enable_llm": True,
    "log_level": "INFO",
    "max_retries": 3,
    "timeout": 60,
}

# 嵌入模型（需下载到本地）
RAG_CONFIG = {
    "embedding_model": "data/models/bge-small-zh-v1.5",
}

RESILIENCE_CONFIG = {
    "max_retries": 3,
    "retry_base_delay_sec": 1.0,
    "retry_max_delay_sec": 30.0,
    "circuit_failure_threshold": 5,
    "circuit_recovery_timeout_sec": 60.0,
    "circuit_half_open_successes": 2,
    "health_check_timeout_sec": 10.0,
}
