"""MCP 服务器测试：Bearer 鉴权 + Streamable HTTP 协议闭环。

用官方 SDK 客户端连本地 uvicorn（非 GUI、只读模式），验证
initialize → list_tools → call_tool 全链路。
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from app.agent.tool_registry import default_registry
from app.mcp_server.adapter import McpToolAdapter
from app.mcp_server.server import build_http_app


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_bearer_middleware_rejects_without_token() -> None:
    adapter = McpToolAdapter(default_registry(), allow_actions=False)
    client = TestClient(build_http_app(adapter, token="secret"))
    response = client.post("/mcp", json={})
    assert response.status_code == 401
    response = client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_http_protocol_roundtrip() -> None:
    token = "test-token"
    adapter = McpToolAdapter(default_registry(), allow_actions=False)
    app = build_http_app(adapter, token=token)
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if getattr(server, "started", False):
                break
            time.sleep(0.1)
        assert server.started, "uvicorn 未能在 5 秒内启动"

        async def scenario():
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(headers=headers, timeout=10.0) as http_client:
                async with streamable_http_client(
                    f"http://127.0.0.1:{port}/mcp", http_client=http_client
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = await session.list_tools()
                        result = await session.call_tool(
                            "evaluate_expression", {"expression": "1+2"}
                        )
                        return tools, result

        tools, result = asyncio.run(scenario())
        names = {tool.name for tool in tools.tools}
        assert "evaluate_expression" in names
        # 只读模式：写工具不暴露
        assert "add_element" not in names
        assert len(names) == len(default_registry().read_only_tools())
        assert not result.is_error
        assert '"value": 3' in result.content[0].text
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_http_protocol_rejects_wrong_token() -> None:
    adapter = McpToolAdapter(default_registry(), allow_actions=False)
    app = build_http_app(adapter, token="right")
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            if getattr(server, "started", False):
                break
            time.sleep(0.1)
        assert server.started

        async def scenario():
            async with httpx.AsyncClient(
                headers={"Authorization": "Bearer wrong"}, timeout=10.0
            ) as http_client:
                async with streamable_http_client(
                    f"http://127.0.0.1:{port}/mcp", http_client=http_client
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()

        with pytest.raises(Exception):
            asyncio.run(scenario())
    finally:
        server.should_exit = True
        thread.join(timeout=5)
