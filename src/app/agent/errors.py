"""Agent 工具层异常。

工具执行器遇到可自纠的业务错误（找不到 id、原则名不存在、参数非法…）时
抛 :class:`ToolError`，由 :class:`app.agent.tool_registry.ToolRegistry`
统一包装成 ``{"error": "..."}`` 结果——错误文案必须包含下一步指引
（例如“请先用 list_elements 查看”），让模型能自行纠正。
"""

from __future__ import annotations


class ToolError(Exception):
    """可读的业务错误（会被转成 {"error": ...} 返回给模型）。"""
