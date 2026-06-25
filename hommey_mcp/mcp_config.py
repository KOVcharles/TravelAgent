"""
MCP 配置模型
定义 MCP Server 的连接配置结构，支持从 dict/JSON 加载和环境变量覆盖。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import os
import logging

logger = logging.getLogger(__name__)


class MCPTransportType(str, Enum):
    """MCP 传输类型"""
    STDIO = "stdio"
    HTTP_STATEFUL = "http_stateful"
    HTTP_STATELESS = "http_stateless"


class MCPHttpTransport(str, Enum):
    """HTTP 子传输协议"""
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


@dataclass
class MCPServerConfig:
    """单个 MCP Server 的配置"""
    name: str                                    # Server 唯一名称
    transport: MCPTransportType = MCPTransportType.STDIO

    # Stdio 传输
    command: Optional[str] = None                # 可执行命令（如 "npx"）
    args: List[str] = field(default_factory=list)  # 命令参数
    env: Dict[str, str] = field(default_factory=dict)  # 环境变量
    cwd: Optional[str] = None                    # 工作目录

    # HTTP 传输
    url: Optional[str] = None                    # HTTP 端点 URL
    http_transport: MCPHttpTransport = MCPHttpTransport.SSE
    headers: Dict[str, str] = field(default_factory=dict)

    # 通用
    timeout: float = 30.0                        # 连接超时（秒）
    execution_timeout: float = 60.0              # 工具执行超时（秒）
    enabled: bool = True                         # 是否启用
    description: str = ""                        # 描述

    def validate(self) -> bool:
        """验证配置完整性"""
        if self.transport == MCPTransportType.STDIO:
            if not self.command:
                logger.error(f"MCP Server '{self.name}': stdio 传输需要 command")
                return False
        elif self.transport in (MCPTransportType.HTTP_STATEFUL, MCPTransportType.HTTP_STATELESS):
            if not self.url:
                logger.error(f"MCP Server '{self.name}': HTTP 传输需要 url")
                return False
        return True


@dataclass
class MCPConfig:
    """全局 MCP 配置"""
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)
    auto_connect: bool = True                    # 初始化时自动连接
    connect_timeout: float = 10.0                # 整体连接超时

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPConfig":
        """从字典加载配置（兼容 config.py 中的 MCP_CONFIG）"""
        servers = {}
        servers_data = data.get("servers", {})

        for name, srv in servers_data.items():
            if isinstance(srv, MCPServerConfig):
                servers[name] = srv
                continue

            # 从字典解析
            transport_raw = srv.get("transport", srv.get("type", "stdio")).lower()
            transport_map = {
                "stdio": MCPTransportType.STDIO,
                "http_stateful": MCPTransportType.HTTP_STATEFUL,
                "http_stateless": MCPTransportType.HTTP_STATELESS,
            }
            transport = transport_map.get(transport_raw, MCPTransportType.STDIO)

            http_transport_raw = srv.get("http_transport", "sse").lower()
            http_transport = MCPHttpTransport.STREAMABLE_HTTP if http_transport_raw == "streamable_http" else MCPHttpTransport.SSE

            server_config = MCPServerConfig(
                name=name,
                transport=transport,
                command=srv.get("command"),
                args=srv.get("args", srv.get("command_args", [])),
                env=srv.get("env", {}),
                cwd=srv.get("cwd"),
                url=srv.get("url"),
                http_transport=http_transport,
                headers=srv.get("headers", {}),
                timeout=srv.get("timeout", 30.0),
                execution_timeout=srv.get("execution_timeout", 60.0),
                enabled=srv.get("enabled", True),
                description=srv.get("description", ""),
            )
            servers[name] = server_config

        return cls(
            servers=servers,
            auto_connect=data.get("auto_connect", True),
            connect_timeout=data.get("connect_timeout", 10.0),
        )

    def get_enabled_servers(self) -> Dict[str, MCPServerConfig]:
        """获取所有已启用的服务器配置"""
        return {k: v for k, v in self.servers.items() if v.enabled and v.validate()}
