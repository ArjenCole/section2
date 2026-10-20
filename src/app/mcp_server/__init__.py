"""MCP 服务（GUI 内嵌 + 独立 CLI）。

- adapter：ToolRegistry → MCP 工具（唯一适配层，不复制业务逻辑）
- server：mcp SDK 2.x lowlevel Server + Streamable HTTP
- auth：Bearer token（仅回环地址）
- controller：GUI 进程内启停
- __main__：CLI 四模式（stdio / http / --connect 桥 / --project headless）
"""

from __future__ import annotations

from app.mcp_server.adapter import McpToolAdapter
from app.mcp_server.controller import McpServerController
from app.mcp_server.server import build_http_app, build_mcp_server

__all__ = ["McpToolAdapter", "McpServerController", "build_http_app", "build_mcp_server"]
