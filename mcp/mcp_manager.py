"""
MCP 客户端管理器
管理多个 MCP Server 连接的生命周期：初始化、工具发现、调用、健康检查、LIFO 关闭。
与 CircuitBreaker 集成，在 MCP Server 连续失败时自动熔断。
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from agentscope.mcp import (
    StdIOStatefulClient,
    HttpStatefulClient,
    HttpStatelessClient,
    MCPClientBase,
    MCPToolFunction,
)

from .mcp_config import MCPServerConfig, MCPTransportType, MCPHttpTransport

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInfo:
    """MCP 工具元数据（用于意图识别和调度）"""
    server_name: str
    tool_name: str
    description: str
    json_schema: Dict[str, Any]


class MCPManager:
    """
    MCP 客户端管理器

    职责：
    1. 根据配置创建和管理多个 MCP Client 实例
    2. 自动连接、工具发现与缓存
    3. LIFO 顺序关闭（AgentScope 要求）
    4. 与 CircuitBreaker 集成
    5. 提供统一工具调用接口
    """

    def __init__(
        self,
        servers_config: Dict[str, MCPServerConfig],
        auto_connect: bool = True,
        connect_timeout: float = 10.0,
        circuit_breaker=None,
    ):
        """
        Args:
            servers_config: MCP Server 配置字典 {name: MCPServerConfig}
            auto_connect: 是否初始化时自动连接所有 Server
            connect_timeout: 连接超时
            circuit_breaker: 熔断器实例（可选）
        """
        self._configs: Dict[str, MCPServerConfig] = servers_config
        self._auto_connect = auto_connect
        self._connect_timeout = connect_timeout
        self.circuit_breaker = circuit_breaker

        # 客户端实例 {server_name: MCPClientBase}
        self._clients: Dict[str, MCPClientBase] = {}

        # 工具缓存 {server_name: {tool_name: MCPToolFunction}}
        self._tools: Dict[str, Dict[str, MCPToolFunction]] = {}

        # 工具元数据缓存 {server_name: [MCPToolInfo]}
        self._tool_infos: Dict[str, List[MCPToolInfo]] = {}

        # 连接顺序栈（用于 LIFO 关闭）
        self._connect_order: List[str] = []

        # 状态
        self._initialized = False
        self._closed = False

    # ─── 初始化与连接 ───────────────────────────────────────

    async def initialize(self) -> Dict[str, bool]:
        """
        初始化所有已启用的 MCP Server 连接。

        Returns:
            {server_name: is_connected}
        """
        if self._initialized:
            logger.warning("MCPManager already initialized")
            return {}

        results = {}
        for name, config in self._configs.items():
            if not config.enabled:
                logger.info(f"MCP Server '{name}' is disabled, skipping")
                continue

            if not config.validate():
                results[name] = False
                continue

            try:
                client = self._create_client(config)
                self._clients[name] = client

                if self._auto_connect:
                    connected = await self._safe_connect(name, client)
                    results[name] = connected
                    if connected:
                        await self._discover_tools(name, client)
                else:
                    results[name] = False

            except Exception as e:
                logger.error(f"Failed to initialize MCP Server '{name}': {e}")
                results[name] = False

        self._initialized = True
        self._log_status(results)
        return results

    async def connect_server(self, name: str) -> bool:
        """手动连接指定 Server"""
        if name not in self._clients:
            logger.error(f"MCP Server '{name}' not found")
            return False

        client = self._clients[name]
        connected = await self._safe_connect(name, client)
        if connected:
            await self._discover_tools(name, client)
        return connected

    async def _safe_connect(self, name: str, client: MCPClientBase) -> bool:
        """安全连接（带超时和错误处理）"""
        try:
            await asyncio.wait_for(
                client.connect(),
                timeout=self._connect_timeout,
            )
            self._connect_order.append(name)
            logger.info(f"✓ Connected to MCP Server '{name}'")
            return True
        except asyncio.TimeoutError:
            logger.error(f"Connection to MCP Server '{name}' timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to MCP Server '{name}': {e}")
            return False

    # ─── 客户端工厂 ─────────────────────────────────────────

    def _create_client(self, config: MCPServerConfig) -> MCPClientBase:
        """根据配置创建对应的 MCP Client 实例"""
        transport = config.transport

        if transport == MCPTransportType.STDIO:
            return StdIOStatefulClient(
                name=config.name,
                command=config.command,
                args=config.args,
                env=config.env or None,
                cwd=config.cwd,
            )

        elif transport == MCPTransportType.HTTP_STATEFUL:
            return HttpStatefulClient(
                name=config.name,
                transport=config.http_transport.value,
                url=config.url,
                headers=config.headers or None,
                timeout=config.timeout,
            )

        elif transport == MCPTransportType.HTTP_STATELESS:
            return HttpStatelessClient(
                name=config.name,
                transport=config.http_transport.value,
                url=config.url,
                headers=config.headers or None,
                timeout=config.timeout,
            )

        else:
            raise ValueError(f"Unsupported transport type: {transport}")

    # ─── 工具发现与缓存 ─────────────────────────────────────

    async def _discover_tools(self, server_name: str, client: MCPClientBase) -> List[MCPToolInfo]:
        """发现并缓存 Server 提供的工具"""
        try:
            raw_tools = await client.list_tools()
        except Exception as e:
            logger.error(f"Failed to list tools for '{server_name}': {e}")
            return []

        tool_infos = []
        tool_funcs = {}

        for tool in raw_tools:
            # 构建 json_schema（OpenAI function 格式）
            json_schema = {
                "type": "function",
                "function": {
                    "name": f"{server_name}__{tool.name}",
                    "description": getattr(tool, 'description', '') or '',
                    "parameters": getattr(tool, 'inputSchema', {}) or {},
                },
            }

            info = MCPToolInfo(
                server_name=server_name,
                tool_name=tool.name,
                description=getattr(tool, 'description', '') or '',
                json_schema=json_schema,
            )
            tool_infos.append(info)

            # 获取可调用函数（延迟到实际调用时也可，但预获取可提前发现问题）
            try:
                func = await client.get_callable_function(
                    tool.name,
                    wrap_tool_result=True,
                )
                tool_funcs[tool.name] = func
            except Exception as e:
                logger.warning(f"Failed to get callable for tool '{tool.name}': {e}")

        self._tool_infos[server_name] = tool_infos
        self._tools[server_name] = tool_funcs

        logger.info(f"Discovered {len(tool_infos)} tools from '{server_name}': "
                    f"{[t.tool_name for t in tool_infos]}")
        return tool_infos

    # ─── 工具调用接口 ───────────────────────────────────────

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        execution_timeout: Optional[float] = None,
    ) -> Any:
        """
        调用指定 MCP Server 的工具。

        Args:
            server_name: MCP Server 名称
            tool_name: 工具名称
            arguments: 工具参数
            execution_timeout: 执行超时（秒），None 则使用 Server 配置

        Returns:
            工具执行结果
        """
        # 熔断检查
        if self.circuit_breaker:
            from utils.circuit_breaker import CircuitOpenError
            try:
                self.circuit_breaker.raise_if_open()
            except CircuitOpenError:
                logger.warning(f"Circuit breaker open, rejecting MCP call to '{server_name}.{tool_name}'")
                raise

        # 获取工具函数
        tool_func = await self._get_tool_func(server_name, tool_name)
        if tool_func is None:
            raise ValueError(f"Tool '{tool_name}' not found on server '{server_name}'")

        # 执行超时
        timeout = execution_timeout or self._configs.get(server_name, MCPServerConfig(name="")).execution_timeout

        try:
            if timeout:
                result = await asyncio.wait_for(
                    tool_func(**arguments),
                    timeout=timeout,
                )
            else:
                result = await tool_func(**arguments)

            # 记录成功
            if self.circuit_breaker:
                self.circuit_breaker.record_success()

            return result

        except asyncio.TimeoutError:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise TimeoutError(f"MCP tool '{server_name}.{tool_name}' timed out after {timeout}s")

        except Exception as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.error(f"MCP tool '{server_name}.{tool_name}' failed: {e}")
            raise

    async def _get_tool_func(self, server_name: str, tool_name: str) -> Optional[MCPToolFunction]:
        """获取或懒加载工具函数"""
        # 检查缓存
        if server_name in self._tools and tool_name in self._tools[server_name]:
            return self._tools[server_name][tool_name]

        # 确保已连接
        if server_name not in self._clients:
            logger.error(f"MCP Server '{server_name}' not initialized")
            return None

        client = self._clients[server_name]

        # 尝试获取工具
        try:
            func = await client.get_callable_function(tool_name, wrap_tool_result=True)
            if server_name not in self._tools:
                self._tools[server_name] = {}
            self._tools[server_name][tool_name] = func
            return func
        except Exception as e:
            logger.error(f"Failed to get tool '{tool_name}' from '{server_name}': {e}")
            return None

    # ─── 查询接口 ───────────────────────────────────────────

    def get_all_tool_infos(self) -> List[MCPToolInfo]:
        """获取所有已发现工具的元数据（用于意图识别 Prompt 注入）"""
        all_infos = []
        for infos in self._tool_infos.values():
            all_infos.extend(infos)
        return all_infos

    def get_server_tool_infos(self, server_name: str) -> List[MCPToolInfo]:
        """获取指定 Server 的工具元数据"""
        return self._tool_infos.get(server_name, [])

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI function schema（用于 LLM function calling）"""
        schemas = []
        for infos in self._tool_infos.values():
            for info in infos:
                schemas.append(info.json_schema)
        return schemas

    def is_connected(self, server_name: str) -> bool:
        """检查指定 Server 是否已连接"""
        return server_name in self._connect_order

    def list_servers(self) -> List[str]:
        """列出所有已注册的 Server 名称"""
        return list(self._configs.keys())

    def list_connected_servers(self) -> List[str]:
        """列出所有已连接的 Server 名称"""
        return list(self._connect_order)

    # ─── 关闭与清理 ─────────────────────────────────────────

    async def close_all(self) -> None:
        """
        关闭所有 MCP Client 连接（LIFO 顺序，AgentScope 要求）。
        应在程序退出时调用。
        """
        if self._closed:
            return

        logger.info("Closing all MCP connections (LIFO order)...")
        errors = []

        # LIFO 顺序关闭
        for server_name in reversed(self._connect_order):
            client = self._clients.get(server_name)
            if client is None:
                continue
            try:
                await client.close(ignore_errors=True)
                logger.info(f"✓ Closed MCP Server '{server_name}'")
            except Exception as e:
                logger.error(f"Failed to close MCP Server '{server_name}': {e}")
                errors.append((server_name, str(e)))

        self._clients.clear()
        self._tools.clear()
        self._tool_infos.clear()
        self._connect_order.clear()
        self._closed = True

        if errors:
            logger.warning(f"MCP close errors: {errors}")

    async def close_server(self, server_name: str) -> None:
        """关闭指定 Server 连接"""
        client = self._clients.get(server_name)
        if client is None:
            return
        try:
            await client.close(ignore_errors=True)
            if server_name in self._connect_order:
                self._connect_order.remove(server_name)
            logger.info(f"✓ Closed MCP Server '{server_name}'")
        except Exception as e:
            logger.error(f"Failed to close MCP Server '{server_name}': {e}")

    # ─── 状态与日志 ─────────────────────────────────────────

    def _log_status(self, results: Dict[str, bool]) -> None:
        """打印连接状态摘要"""
        connected = [k for k, v in results.items() if v]
        failed = [k for k, v in results.items() if not v]
        if connected:
            logger.info(f"MCP connected: {', '.join(connected)}")
        if failed:
            logger.warning(f"MCP failed: {', '.join(failed)}")

    def get_status(self) -> Dict[str, Any]:
        """获取 MCP 系统状态"""
        return {
            "initialized": self._initialized,
            "total_servers": len(self._configs),
            "connected_servers": len(self._connect_order),
            "connected_names": list(self._connect_order),
            "total_tools": sum(len(t) for t in self._tool_infos.values()),
            "tools_by_server": {
                name: [t.tool_name for t in infos]
                for name, infos in self._tool_infos.items()
            },
            "circuit_breaker": str(self.circuit_breaker._state) if self.circuit_breaker else "disabled",
        }
