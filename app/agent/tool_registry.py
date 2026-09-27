"""工具注册表（计划 §3 agent/tool_registry.py）。

一期只有构件增删改查 4 个工具（见 tools/element_crud.TOOL_SPECS）；
扩展新工具时在 element_crud 里登记 spec 与 handler，本模块对外暴露统一入口。
"""

from __future__ import annotations

from app.agent.tools import element_crud


def openai_tools() -> list[dict]:
    """给 chat/completions 的 tools 参数（OpenAI JSON Schema）。"""
    return list(element_crud.TOOL_SPECS)


def is_write(name: str) -> bool:
    """是否写操作（执行前必须经 confirm_policy 确认）。"""
    return name in element_crud.WRITE_TOOLS


def execute(name: str, arguments: str, context) -> str:
    """执行工具并返回给模型的文本结果。"""
    return element_crud.execute(name, arguments, context)
