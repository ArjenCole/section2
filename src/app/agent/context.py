"""工具执行上下文：GUI 当前选中状态（内嵌模式缺省 id 的来源）。

三层上下文注入的运行时层：

1. 事件层：EventBus.ai_context_changed 由树面板 / 主表格发出；
2. prompt 层：AiPanel 每轮把当前上下文塞进 system prompt（见
   ToolRegistry.to_rules_for_context）；
3. 运行时层：本模块保存最新快照，工具参数省略 id 时从这里解析
   （MCP 内嵌模式同样生效；headless 独立进程没有选中状态，必须显式传 id）。

工具执行器不直接 import 本模块的全局变量做判断，统一用
:func:`resolve_unit_id` / :func:`resolve_element_id`——错误文案里带
“下一步该调哪个工具”的指引。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.agent.errors import ToolError


@dataclass(frozen=True)
class AgentContext:
    """当前选中上下文（不可变快照）。"""

    unit_id: int | None = None
    unit_name: str = ""
    element_id: int | None = None
    element_name: str = ""
    #: "gui"：界面内嵌（有选中状态）；"headless"：独立进程（无选中状态）
    source: str = "gui"

    def as_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "unit_name": self.unit_name,
            "element_id": self.element_id,
            "element_name": self.element_name,
            "source": self.source,
        }


_current = AgentContext()


def current() -> AgentContext:
    """当前上下文快照。"""
    return _current


def update_context(**fields) -> AgentContext:
    """更新上下文（None 值表示清除对应选中项）。返回新快照。"""
    global _current
    _current = replace(_current, **fields)
    return _current


def reset_context() -> AgentContext:
    """工程关闭时清空选中。"""
    global _current
    _current = AgentContext()
    return _current


def resolve_unit_id(arguments: dict) -> int:
    """从参数或当前选中解析单位工程 id。"""
    value = arguments.get("unit_id")
    if value in (None, ""):
        value = _current.unit_id
    if value in (None, ""):
        raise ToolError(
            "当前未选中单位工程：请显式传 unit_id（可先调 get_project_tree 查看单位工程 id）。"
        )
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ToolError(f"unit_id 需要整数，收到：{value!r}") from error


def resolve_element_id(arguments: dict) -> int:
    """从参数或当前选中构件解析构件 id。"""
    value = arguments.get("element_id")
    if value in (None, ""):
        value = _current.element_id
    if value in (None, ""):
        raise ToolError(
            "当前未选中构件：请显式传 element_id，或先调 list_elements / get_element_detail 查看。"
        )
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ToolError(f"element_id 需要整数，收到：{value!r}") from error


def optional_unit_id(arguments: dict) -> int | None:
    """可选单位工程 id（省略且无选中时返回 None，用于“全工程”语义）."""
    value = arguments.get("unit_id")
    if value in (None, ""):
        value = _current.unit_id
    return int(value) if value not in (None, "") else None
