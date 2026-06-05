"""
MCP (Model Context Protocol) 集成模块
提供双向 MCP 能力：
- 消费者侧：通过 MCPManager 连接外部 MCP Server，消费其工具
- 生产者侧：通过 AligoMCPServer 将 Aligo 能力暴露为 MCP Server
"""
from .mcp_config import MCPConfig, MCPServerConfig
from .mcp_manager import MCPManager

__all__ = [
    "MCPConfig",
    "MCPServerConfig",
    "MCPManager",
]
