#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Aligo MCP Server 启动入口
将 Aligo 商旅助手的核心能力以 MCP 协议暴露，供外部 AI 应用调用。

启动方式：
    # Stdio 模式（Claude Desktop / Cursor 集成）
    python aligo_mcp/run_server.py

    # 或通过绝对路径
    python e:/PythonProject/ProjetcAgent/aligo_mcp/run_server.py

Claude Desktop 配置示例（claude_desktop_config.json）：
{
    "mcpServers": {
        "aligo": {
            "command": "python",
            "args": ["e:/PythonProject/ProjetcAgent/aligo_mcp/run_server.py"]
        }
    }
}
"""
import sys
import os

# 确保项目根目录在路径中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from aligo_mcp.aligo_mcp_server import server


def main():
    """启动 Aligo MCP Server（stdio 模式）"""
    print("🚀 Aligo MCP Server starting on stdio...", file=sys.stderr)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
