"""I 组：领域约定与当前上下文（T73~T74）。"""

from __future__ import annotations

from app.agent import context
from app.agent.conventions import (
    CATEGORY_ENUM,
    CONVENTIONS_TEXT,
    DOCK_CHOICES,
    EXCVT_CHOICES,
    PRECIPITATION_WELLS,
    PRINCIPLE_KINDS,
    WIDTH_PIPE_TYPES,
)
from app.agent.tool_registry import Tool, ToolRegistry


def tool_get_conventions(arguments: dict) -> dict:
    return {
        "ok": True,
        "data": {
            "text": CONVENTIONS_TEXT,
            "categories": CATEGORY_ENUM,
            "principle_kinds": PRINCIPLE_KINDS,
            "excvt_choices": list(EXCVT_CHOICES),
            "dock_choices": list(DOCK_CHOICES),
            "precipitation_wells": list(PRECIPITATION_WELLS),
            "width_pipe_types": list(WIDTH_PIPE_TYPES),
        },
    }


def tool_get_current_context(arguments: dict) -> dict:
    snapshot = context.current()
    data = snapshot.as_dict()
    if snapshot.source == "headless":
        data["hint"] = "当前为无界面进程，没有界面选中状态；请显式传 unit_id / element_id。"
    elif snapshot.unit_id is None:
        data["hint"] = "界面当前没有选中单位工程；请先 get_project_tree 后显式传 id。"
    return {"ok": True, "data": data}


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_conventions",
            "读取领域约定（类别枚举/原则类型/土质/井型/表达式规则）。AI 冷启动时先取一次。只读。",
            {"type": "object", "properties": {}},
            tool_get_conventions, read_only=True,
        )
    )
    registry.register(
        Tool(
            "get_current_context",
            "读取界面当前选中的单位工程/构件（内嵌模式）。无界面进程返回空并提示显式传 id。只读。",
            {"type": "object", "properties": {}},
            tool_get_current_context, read_only=True,
        )
    )
