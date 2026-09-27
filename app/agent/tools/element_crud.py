"""一期 AI 工具（计划 §8.3）：仅构件条目增删改查 4 个。

工具函数都通过 viewmodels.unit_vm 的数据操作执行（与界面同一条代码路径），
写操作由 confirm_policy 统一弹确认；执行后 EventBus 自动刷新工程量表。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from app.core.evaluator import evaluate_or_default
from app.orm.models import CATEGORY_NAMES, CATEGORY_CHOICES, category_from_name, category_name
from app.services import project_io
from app.viewmodels import unit_vm


@dataclass
class ToolContext:
    """工具执行上下文：当前单位工程 id + 确认回调（写操作由循环层调用）。"""

    unit_id: int | None = None
    unit_name: str = ""
    confirm: Callable[[str], bool] = field(default_factory=lambda: lambda _description: True)


def _category_value(value) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        number = int(value)
        return number if number in CATEGORY_CHOICES else None
    return category_from_name(str(value)) or None


def _element_rows_text(context: ToolContext) -> str:
    rows = unit_vm.element_rows(context.unit_id)
    if not rows:
        return "（当前单位工程没有构件条目）"
    lines = []
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}. id={row.id} 名称={row.name or '（未命名）'} 类别={category_name(row.category)} "
            f"埋深={row.depth}（={row.depth_value:g}m） 数量={row.amount}（={row.amount_value:g}m） "
            f"围护={row.pe_name or '—'} 地基={row.pf_name or '—'}"
        )
    return "\n".join(lines)


def tool_list_elements(context: ToolContext, **_kwargs) -> str:
    """列出当前单位工程的构件条目。"""
    if context.unit_id is None:
        return "当前未选中单位工程，请先在项目树里选择。"
    header = f"单位工程“{context.unit_name}”的构件条目："
    return header + "\n" + _element_rows_text(context)


def tool_add_element(context: ToolContext, **kwargs) -> str:
    """新增构件条目（写操作）。"""
    if context.unit_id is None:
        return "当前未选中单位工程，无法新增。"
    name = str(kwargs.get("name") or "").strip()
    category = _category_value(kwargs.get("category"))
    depth = str(kwargs.get("depth") or "0")
    amount = str(kwargs.get("amount") or "0")
    pe_name = kwargs.get("pe_name") or None
    pf_name = kwargs.get("pf_name") or None
    enclosure_names = project_io.enclosure_names()
    foundation_names = project_io.foundation_names()
    if pe_name and pe_name not in enclosure_names:
        return f"围护原则“{pe_name}”不存在。可用：{'、'.join(enclosure_names)}"
    if pf_name and pf_name not in foundation_names:
        return f"地基原则“{pf_name}”不存在。可用：{'、'.join(foundation_names)}"

    element = unit_vm.create_element(
        context.unit_id,
        category=category if category is not None else 1,
        name=name,
        depth=depth,
        amount=amount,
        pe_name=pe_name,
        pf_name=pf_name,
    )
    if element is None:
        return "新增失败：单位工程不存在。"
    pipe = kwargs.get("pipe") or {}
    pipe_text = ""
    if isinstance(pipe, dict) and pipe.get("mat"):
        unit_vm.create_pipe(element.id, mat=str(pipe.get("mat")), dn=int(pipe.get("dn") or 600),
                            content=str(pipe.get("content") or "1"))
        pipe_text = f"，管材 {pipe.get('mat')} Dn{pipe.get('dn')}"
    return (
        f"已新增构件 id={element.id}：{name or '（未命名）'} "
        f"{category_name(element.category)}，埋深 {depth}，数量 {amount}{pipe_text}。"
    )


def tool_update_element(context: ToolContext, **kwargs) -> str:
    """修改构件条目字段（写操作）。"""
    element = _find_element(context, kwargs)
    if isinstance(element, str):
        return element
    fields: dict = {}
    mapping = {
        "name": str(kwargs.get("name")) if kwargs.get("name") is not None else None,
        "depth": str(kwargs["depth"]) if kwargs.get("depth") is not None else None,
        "amount": str(kwargs["amount"]) if kwargs.get("amount") is not None else None,
        "pe_name": kwargs.get("pe_name"),
        "pf_name": kwargs.get("pf_name"),
    }
    category = _category_value(kwargs.get("category"))
    if category is not None:
        fields["category"] = category
    for key, value in mapping.items():
        if value is not None:
            fields[key] = value
    if not fields:
        return "没有给出要修改的字段（可改：名称/类别/埋深/数量/围护原则/地基原则）。"
    enclosure_names = project_io.enclosure_names()
    foundation_names = project_io.foundation_names()
    if fields.get("pe_name") and fields["pe_name"] not in enclosure_names:
        return f"围护原则“{fields['pe_name']}”不存在。可用：{'、'.join(enclosure_names)}"
    if fields.get("pf_name") and fields["pf_name"] not in foundation_names:
        return f"地基原则“{fields['pf_name']}”不存在。可用：{'、'.join(foundation_names)}"
    updated = unit_vm.update_element(element.id, **fields)
    if updated is None:
        return "修改失败。"
    changes = "、".join(f"{key}={value}" for key, value in fields.items())
    return f"已修改构件 id={element.id}：{changes}。"


def tool_delete_element(context: ToolContext, **kwargs) -> str:
    """删除构件条目（写操作，二次确认）。"""
    element = _find_element(context, kwargs)
    if isinstance(element, str):
        return element
    unit_vm.delete_element(element.id)
    return f"已删除构件 id={element.id}（{element.name or '未命名'}）及其管材、参数。"


def _find_element(context: ToolContext, kwargs: dict):
    """按 id 或名称定位构件；找不到返回说明文本。"""
    if context.unit_id is None:
        return "当前未选中单位工程。"
    element_id = kwargs.get("element_id")
    rows = unit_vm.element_rows(context.unit_id)
    if element_id is not None:
        for row in rows:
            if row.id == int(element_id):
                return row
        return f"找不到 id={element_id} 的构件。请先用 list_elements 查看。"
    name = str(kwargs.get("name") or "").strip()
    if name:
        matches = [row for row in rows if row.name == name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return (
                f"有 {len(matches)} 条同名构件，请先用 list_elements 查看后按 element_id 操作。"
            )
        fuzzy = [row for row in rows if name in row.name]
        if len(fuzzy) == 1:
            return fuzzy[0]
        return f"找不到名称含“{name}”的构件。请先用 list_elements 查看。"
    return "请提供 element_id 或 name。"


#: 工具的 OpenAI JSON Schema（与 §8.3 一致，仅这 4 个）
TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_elements",
            "description": "列出当前单位工程的构件条目（类别/规格/埋深/数量/原则）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_element",
            "description": "新增一条构件条目（写操作，需要用户确认）",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "构件名称，如“雨水管 D600”"},
                    "category": {"type": "string", "enum": [name for name in CATEGORY_NAMES.values() if name],
                                 "description": "构件类别"},
                    "depth": {"type": "string", "description": "埋深（m），可写算式如 2.5+0.3"},
                    "amount": {"type": "string", "description": "数量/长度（m），可写算式"},
                    "pe_name": {"type": "string", "description": "沟槽围护原则名（可选，默认第一条）"},
                    "pf_name": {"type": "string", "description": "地基处理原则名（可选）"},
                    "pipe": {
                        "type": "object",
                        "description": "管道信息（可选）",
                        "properties": {
                            "mat": {"type": "string", "description": "管材"},
                            "dn": {"type": "integer", "description": "管径 mm"},
                            "content": {"type": "string", "description": "含量"},
                        },
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_element",
            "description": "修改构件条目的字段（埋深/数量/名称/类别/原则），写操作需要用户确认",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer", "description": "构件 id（list_elements 里给出）"},
                    "name": {"type": "string", "description": "按名称定位（仅当没有 id 时）"},
                    "category": {"type": "string", "enum": [name for name in CATEGORY_NAMES.values() if name]},
                    "depth": {"type": "string"},
                    "amount": {"type": "string"},
                    "pe_name": {"type": "string"},
                    "pf_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_element",
            "description": "删除一条构件条目及其管材、参数（写操作，需要用户确认）",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "integer"},
                    "name": {"type": "string"},
                },
            },
        },
    },
]

_HANDLERS = {
    "list_elements": tool_list_elements,
    "add_element": tool_add_element,
    "update_element": tool_update_element,
    "delete_element": tool_delete_element,
}

#: 写操作工具名（执行前必须经 confirm_policy 确认）
WRITE_TOOLS = {"add_element", "update_element", "delete_element"}


def execute(name: str, arguments: str, context: ToolContext) -> str:
    """执行一个工具调用；参数解析失败时返回错误说明。"""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"未知工具：{name}"
    try:
        kwargs = json.loads(arguments or "{}")
    except json.JSONDecodeError as error:
        return f"参数不是合法 JSON：{error}"
    if not isinstance(kwargs, dict):
        return "参数必须是 JSON 对象。"
    return handler(context, **kwargs)
