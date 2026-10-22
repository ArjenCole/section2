"""F 组：计算与表达式（T64~T66）。"""

from __future__ import annotations

from app.agent.context import resolve_element_id, resolve_unit_id
from app.agent.errors import ToolError
from app.agent.serializers import element_row_dict, qdict_dict
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import require_open
from app.core.evaluator import EvalError, evaluate
from app.core.models import base as orm
from app.core.models.models import Unit


def tool_compute_unit(arguments: dict) -> dict:
    require_open()
    unit_id = resolve_unit_id(arguments)
    from app.viewmodels.unit_vm import compute_unit

    summary, detail = compute_unit(unit_id)
    include_steps = bool(arguments.get("include_steps", False))
    include_expressions = bool(arguments.get("include_expressions", True))
    unit = orm.session().get(Unit, unit_id)
    per_element = []
    for row, qdict in detail:
        per_element.append(
            {
                "element": element_row_dict(row),
                "quantities": qdict_dict(
                    qdict,
                    include_steps=include_steps,
                    include_expressions=include_expressions,
                ),
            }
        )
    totals = qdict_dict(
        summary, include_steps=include_steps, include_expressions=include_expressions
    )
    total_value = sum(item["value"] for item in totals)
    return {
        "ok": True,
        "data": {
            "unit_id": unit_id,
            "unit_name": unit.name if unit else "",
            "totals": totals,
            "per_element": per_element,
            "quantity_count": len(totals),
            "value_sum": total_value,
        },
        "summary": f"{unit.name if unit else unit_id}：{len(totals)} 条工程量",
    }


def tool_compute_element(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    from app.core.models.models import Element
    from app.viewmodels.unit_vm import compute_unit

    element = orm.session().get(Element, element_id)
    if element is None:
        raise ToolError(f"找不到 id={element_id} 的构件。请先调 list_elements。")
    _summary, detail = compute_unit(element.unit_id)
    for row, qdict in detail:
        if row.id != element_id:
            continue
        include_steps = bool(arguments.get("include_steps", True))
        quantities = qdict_dict(qdict, include_steps=include_steps)
        return {
            "ok": True,
            "data": {
                "element_id": element_id,
                "element": element_row_dict(row),
                "quantities": quantities,
                "error": row.error,
            },
        }
    raise ToolError(
        f"构件 id={element_id} 不在单位工程计算范围内（可能刚被删除）。请刷新后重试。"
    )


def tool_evaluate_expression(arguments: dict) -> dict:
    expression = str(arguments.get("expression") or "").strip()
    if not expression:
        raise ToolError("请提供要计算的 expression。")
    try:
        value = evaluate(expression)
    except EvalError as error:
        raise ToolError(f"算式不合法：{error}") from error
    return {"ok": True, "data": {"expression": expression, "value": value}}


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "compute_unit",
            "计算单位工程全部工程量（定额键/数值/表达式/可选中间步骤）。只读。unit_id 省略时用当前选中。",
            {"type": "object", "properties": {
                "unit_id": {"type": "integer"},
                "include_expressions": {"type": "boolean", "default": True},
                "include_steps": {"type": "boolean", "default": False}},
             },
            tool_compute_unit, read_only=True,
        )
    )
    registry.register(
        Tool(
            "compute_element",
            "计算单个构件工程量（默认含中间步骤）。只读。element_id 省略时用当前选中构件。",
            {"type": "object", "properties": {
                "element_id": {"type": "integer"},
                "include_steps": {"type": "boolean", "default": True}},
             },
            tool_compute_element, read_only=True,
        )
    )
    registry.register(
        Tool(
            "evaluate_expression",
            "用软件白名单求值器计算算式（支持 +-*/^、括号、ABS/ROUND/ROUNDUP/SQRT/POWER/CEILING/SIN/COS/PI()，Excel 写法可直接用）。只读。",
            {"type": "object", "properties": {"expression": {"type": "string"}},
             "required": ["expression"]},
            tool_evaluate_expression, read_only=True,
        )
    )
