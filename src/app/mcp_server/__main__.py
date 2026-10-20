"""MCP CLI 入口：`section2-mcp`。

用法::

    # 本地 stdio server（进程内执行；无界面时写工具被拒绝）
    section2-mcp [--read-only]

    # 本地 Streamable HTTP server
    section2-mcp --transport http [--port 8765 --token <t>] [--read-only]

    # stdio 桥：把 stdio MCP 转发到运行中桌面应用的 HTTP 端点
    section2-mcp --connect http://127.0.0.1:8765/mcp [--token <t>]

    # headless 只读：无界面打开工程，只暴露只读工具
    section2-mcp --project <path.stn2>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.agent import context
from app.agent import tool_registry
from app.mcp_server.adapter import McpToolAdapter


def _build_adapter(*, allow_actions: bool) -> McpToolAdapter:
    return McpToolAdapter(tool_registry.default_registry(), allow_actions=allow_actions)


def _open_project_headless(path: Path) -> None:
    from app.services import project_io

    if not path.exists():
        raise FileNotFoundError(f"工程文件不存在：{path}")
    project_io.open_project(path)
    context.update_context(source="headless")


async def _run_local(transport: str, args: argparse.Namespace) -> None:
    from app.mcp_server import server as mcp_server

    adapter = _build_adapter(allow_actions=not args.read_only)
    if transport == "stdio":
        await mcp_server.run_stdio(adapter)
    else:
        await mcp_server.run_http_async(
            adapter,
            host="127.0.0.1",
            port=args.port,
            token=args.token,
        )


# --------------------------------------------------------------------------- #
# stdio 桥：stdio ↔ 运行中桌面应用的 HTTP MCP
# --------------------------------------------------------------------------- #
async def _run_bridge(url: str, token: str | None) -> None:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server.lowlevel import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, TextContent

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def on_list_tools(ctx, params) -> ListToolsResult:  # noqa: ANN001, ARG001
                    result = await session.list_tools()
                    return ListToolsResult(tools=result.tools)

                async def on_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:  # noqa: ANN001, ARG001
                    result = await session.call_tool(params.name, params.arguments or {})
                    if isinstance(result, CallToolResult):
                        return result
                    text = getattr(result, "model_dump_json", lambda: str(result))()
                    return CallToolResult(
                        content=[TextContent(type="text", text=text)], is_error=False
                    )

                server = Server(
                    "section2-mcp-bridge",
                    version="2.0.0",
                    on_list_tools=on_list_tools,
                    on_call_tool=on_call_tool,
                )
                async with stdio_server() as (read_stream, write_stream):
                    await server.run(
                        read_stream,
                        write_stream,
                        server.create_initialization_options(),
                    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="section2-mcp", description="Section 2.0 MCP server")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="本地 server 传输方式（默认 stdio）",
    )
    parser.add_argument("--port", type=int, default=8765, help="HTTP 监听端口（仅回环）")
    parser.add_argument("--token", default=None, help="HTTP Bearer token")
    parser.add_argument("--read-only", action="store_true", help="只暴露只读工具")
    parser.add_argument("--connect", default=None, help="stdio 桥：转发到运行中应用的 HTTP MCP 端点")
    parser.add_argument("--project", default=None, help="headless：无界面打开 .stn2（强制只读）")
    args = parser.parse_args(argv)

    opened = False
    if args.project:
        try:
            _open_project_headless(Path(args.project))
            opened = True
        except Exception as error:  # noqa: BLE001
            print(f"[错误] 打开工程失败：{error}", file=sys.stderr)
            return 1
        args.read_only = True

    try:
        if args.connect:
            asyncio.run(_run_bridge(args.connect, args.token))
        else:
            asyncio.run(_run_local(args.transport, args))
    except KeyboardInterrupt:
        pass
    except Exception as error:  # noqa: BLE001
        print(f"[错误] MCP server 运行失败：{error}", file=sys.stderr)
        return 1
    finally:
        if opened:
            from app.services import project_io

            try:
                project_io.close_project()
            except Exception:  # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
