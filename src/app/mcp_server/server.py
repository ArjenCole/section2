"""MCP Server 组装与传输（mcp SDK 2.x lowlevel Server）。"""

from __future__ import annotations

from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult

from app.core.version import APP_VERSION
from app.mcp_server.adapter import McpToolAdapter
from app.mcp_server.auth import BearerAuthMiddleware

_SERVER_NAME = "section2-mcp"


def build_mcp_server(adapter: McpToolAdapter) -> Server:
    async def on_list_tools(ctx, params) -> ListToolsResult:  # noqa: ANN001, ARG001
        return ListToolsResult(tools=adapter.list_tools())

    async def on_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:  # noqa: ANN001, ARG001
        return await adapter.call_tool(params.name, params.arguments or {})

    return Server(
        _SERVER_NAME,
        version=APP_VERSION,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def build_http_app(adapter: McpToolAdapter, token: str | None = None, path: str = "/mcp") -> Any:
    """构建 Streamable HTTP 的 ASGI 应用（仅回环 + Bearer 鉴权）。"""
    server = build_mcp_server(adapter)
    app = server.streamable_http_app(streamable_http_path=path, host="127.0.0.1")
    if token:
        app = BearerAuthMiddleware(app, token)
    return app


async def run_stdio(adapter: McpToolAdapter) -> None:
    server = build_mcp_server(adapter)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def run_http_async(
    adapter: McpToolAdapter,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
    path: str = "/mcp",
) -> None:
    import uvicorn

    app = build_http_app(adapter, token=token, path=path)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
