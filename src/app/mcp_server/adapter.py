"""ToolRegistry → MCP 适配层。

与 Quotor 同款执行模型：
- 同步执行器放 ``anyio.to_thread``，不阻塞 asyncio 事件循环；
- ``allow_actions=false`` 时只暴露只读工具；
- 写工具在无界面进程直接拒绝（没有确认面，避免无人值守改数据）；
- MCP 通道写操作按 ``[mcp] require_confirmation`` 决定是否弹确认卡；
- 结果语义：``{"error"}`` → isError=true；``{"cancelled"}`` → isError=false。
"""

from __future__ import annotations

import json
import threading
from typing import Any

import anyio
from mcp.types import CallToolResult, TextContent, Tool as McpTool

from app.agent import tool_registry
from app.agent.confirm_policy import (
    CHANNEL_MCP,
    ask_confirm,
    channel,
    has_confirm_handler,
    make_preview,
)
from app.agent.tool_registry import Tool, ToolRegistry


def _gui_available() -> bool:
    """是否有可弹确认卡的界面（QCoreApplication 存在且已安装确认处理器）。"""
    from PySide6.QtCore import QCoreApplication

    return QCoreApplication.instance() is not None and has_confirm_handler()


def _result_to_call_result(result: Any) -> CallToolResult:
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except Exception as error:  # noqa: BLE001
        text = json.dumps({"error": f"结果序列化失败：{error}"}, ensure_ascii=False)
    is_error = isinstance(result, dict) and bool(result.get("error"))
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        is_error=is_error,
    )


def _error_result(message: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps({"error": message}, ensure_ascii=False))],
        is_error=True,
    )


def _cancelled_result(message: str = "用户取消了操作") -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps({"cancelled": True, "message": message}, ensure_ascii=False),
            )
        ],
        is_error=False,
    )


def _preview(tool: Tool, name: str, arguments: dict) -> dict:
    details: list[str] = []
    for key, value in arguments.items():
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        details.append(f"{key} = {text}")
    return make_preview(
        action=tool.description,
        target=name,
        summary="外部 MCP 客户端请求执行写操作",
        details=details,
    )


class McpToolAdapter:
    """ToolRegistry → MCP 工具适配器。"""

    def __init__(self, registry: ToolRegistry, *, allow_actions: bool = True) -> None:
        self._registry = registry
        self._allow_actions = allow_actions
        # 全局串行：数据层是全局单会话，不允许并行执行工具
        self._lock = threading.Lock()

    @property
    def allow_actions(self) -> bool:
        return self._allow_actions

    def visible_tools(self) -> list[Tool]:
        tools = self._registry.all_tools()
        if self._allow_actions:
            return tools
        return [tool for tool in tools if tool.read_only]

    def list_tools(self) -> list[McpTool]:
        return [
            McpTool(
                name=tool.name,
                title=tool.name,
                description=tool.description,
                input_schema=tool.parameters,
            )
            for tool in self.visible_tools()
        ]

    def execute_sync(self, name: str, arguments: dict | None) -> CallToolResult:
        tool = self._registry.get(name)
        if tool is None:
            return _error_result(f"未知工具：{name}")
        if not self._allow_actions and not tool.read_only:
            return _error_result("写操作已被禁用（[mcp] allow_actions=false）")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _error_result("arguments 必须是 JSON 对象。")
        with self._lock, channel(CHANNEL_MCP):
            if not tool.read_only:
                if not _gui_available():
                    return _error_result(
                        "该工具是写操作，需要 Section2 桌面界面弹出确认卡。"
                        "请在运行中的桌面应用里启用 MCP 服务，或用 `section2-mcp --connect` "
                        "接入正在运行的应用；headless 模式只支持只读工具。"
                    )
                if not ask_confirm(_preview(tool, name, arguments)):
                    return _cancelled_result()
            result = self._registry.execute(name, arguments)
        return _result_to_call_result(result)

    async def call_tool(self, name: str, arguments: dict | None) -> CallToolResult:
        return await anyio.to_thread.run_sync(self.execute_sync, name, arguments)


def build_adapter(*, allow_actions: bool = True) -> McpToolAdapter:
    return McpToolAdapter(tool_registry.default_registry(), allow_actions=allow_actions)
