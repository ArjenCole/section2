"""MCP 适配层单测（工具列表 / 只读过滤 / headless 守卫 / 结果语义）。"""

from __future__ import annotations

from mcp.types import CallToolResult

from app.agent.tool_registry import Tool, ToolRegistry, default_registry
from app.mcp_server import adapter as adapter_module
from app.mcp_server.adapter import McpToolAdapter


def test_registry_tool_surface() -> None:
    registry = default_registry()
    assert len(registry.names()) == 69
    assert len(set(registry.names())) == 69
    read_only = registry.read_only_tools()
    assert read_only
    assert len(read_only) < 69


def test_adapter_lists_all_or_read_only() -> None:
    full = McpToolAdapter(default_registry(), allow_actions=True)
    readonly = McpToolAdapter(default_registry(), allow_actions=False)
    full_names = {tool.name for tool in full.list_tools()}
    readonly_names = {tool.name for tool in readonly.list_tools()}
    assert len(full_names) == 69
    assert readonly_names < full_names
    assert "add_element" not in readonly_names
    assert "compute_unit" in readonly_names
    tool = next(item for item in full.list_tools() if item.name == "evaluate_expression")
    assert tool.input_schema["type"] == "object"


def test_unknown_tool_is_error() -> None:
    adapter = McpToolAdapter(default_registry())
    result = adapter.execute_sync("no_such_tool", {})
    assert result.is_error
    assert "未知工具" in result.content[0].text


def test_read_tool_works_headless() -> None:
    adapter = McpToolAdapter(default_registry())
    result = adapter.execute_sync("evaluate_expression", {"expression": "1+2"})
    assert not result.is_error
    assert '"value": 3' in result.content[0].text


def test_write_tool_blocked_headless(monkeypatch) -> None:
    adapter = McpToolAdapter(default_registry(), allow_actions=True)
    # 显式模拟无界面：测试进程里可能有其它 GUI 用例留下的 QApplication
    monkeypatch.setattr(adapter_module, "_gui_available", lambda: False)
    result = adapter.execute_sync("add_segment", {"name": "x"})
    assert result.is_error
    assert "桌面界面" in result.content[0].text


def test_allow_actions_false_blocks_write_in_gui(monkeypatch) -> None:
    adapter = McpToolAdapter(default_registry(), allow_actions=False)
    monkeypatch.setattr(adapter_module, "_gui_available", lambda: True)
    result = adapter.execute_sync("add_segment", {"name": "x"})
    assert result.is_error
    assert "allow_actions=false" in result.content[0].text


def test_write_tool_cancelled_semantics(monkeypatch) -> None:
    registry = ToolRegistry()

    def executor(arguments: dict) -> dict:
        return {"ok": True}

    registry.register(
        Tool("fake_write", "假写工具", {"type": "object", "properties": {}}, executor)
    )
    adapter = McpToolAdapter(registry, allow_actions=True)
    monkeypatch.setattr(adapter_module, "_gui_available", lambda: True)
    monkeypatch.setattr(adapter_module, "ask_confirm", lambda preview: False)
    result = adapter.execute_sync("fake_write", {})
    assert isinstance(result, CallToolResult)
    assert not result.is_error
    assert '"cancelled": true' in result.content[0].text


def test_write_tool_approved_executes(monkeypatch) -> None:
    registry = ToolRegistry()
    calls: list[dict] = []

    def executor(arguments: dict) -> dict:
        calls.append(arguments)
        return {"ok": True, "data": {"done": True}}

    registry.register(
        Tool("fake_write", "假写工具", {"type": "object", "properties": {}}, executor)
    )
    adapter = McpToolAdapter(registry, allow_actions=True)
    monkeypatch.setattr(adapter_module, "_gui_available", lambda: True)
    monkeypatch.setattr(adapter_module, "ask_confirm", lambda preview: True)
    result = adapter.execute_sync("fake_write", {"a": 1})
    assert not result.is_error
    assert calls == [{"a": 1}]
