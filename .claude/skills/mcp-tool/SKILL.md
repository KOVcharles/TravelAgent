---
name: mcp-tool
description: Use this skill when the user needs to interact with external tools via the Model Context Protocol (MCP). Triggers when user asks to save/read files, search external APIs, or any operation requiring MCP-connected tools. This skill routes tool calls to the MCPManager which manages connections to external MCP servers.
---

# MCP Tool (外部工具调用)

通过 MCP 协议调用外部工具。当前支持的工具由 `MCPManager` 动态发现。

## When to Use

- 用户说「保存到文件」「读取文件」「导出行程」「列出文件」等
- 用户需要任何 MCP Server 提供的工具能力

## Agent

- **MCPToolAgent** — 接收工具调用请求，路由到 MCPManager
- 入参为 **model 对象** + **mcp_manager 实例**
- **异步**：`reply()` 为 `async`，需 `await`

## 调用模式

1. IntentionAgent 识别到 MCP 工具意图 → 在 `agent_schedule` 中添加 `mcp_tool` 任务
2. Orchestrator 调度到 `MCPToolAgent`
3. MCPToolAgent 解析参数 → 调用 `mcp_manager.call_tool(server, tool, arguments)`
4. 返回结果给 Orchestrator 聚合
