"""ORM / 计算结果 → 工具返回 dict 的序列化。

约定：
- 数值保留 float，格式化交给展示层；
- 算式列保留用户原文，另给 ``*_value`` 数值；
- 工程量保留 key（类别|项目|单位）并拆出 category/item/unit；
- steps 逐项 ``{note, expr}``，不得改写（各步拼接恒等于 expression）。
"""

from __future__ import annotations

import re

from sqlalchemy import func, select

from app.agent.errors import ToolError
from app.core.models import base as orm
from app.core.models.models import (
    Component,
    Element,
    PcpEnclosure,
    PcpFoundation,
    PcpPrecipitation,
    PcpWidth,
    category_name,
    parse_precipitation,
)
from app.core.models.models import PRECIPITATION_COLUMNS, PRECIPITATION_LABELS
from app.core.models.models import unit_of


# --------------------------------------------------------------------------- #
# 构件
# --------------------------------------------------------------------------- #
def element_row_dict(row) -> dict:
    """ElementRow（unit_vm）→ dict。"""
    return {
        "id": row.id,
        "name": row.name,
        "category": category_name(row.category),
        "category_value": row.category,
        "spec": row.spec,
        "depth": row.depth,
        "depth_value": row.depth_value,
        "depth_error": row.depth_error,
        "amount": row.amount,
        "amount_value": row.amount_value,
        "amount_error": row.amount_error,
        "unit": row.unit,
        "pe_name": row.pe_name,
        "pf_name": row.pf_name,
        "pp_name": row.pp_name,
        "pw_name": row.pw_name,
        "pe_left_name": getattr(row, "pe_left_name", ""),
        "pe_right_name": getattr(row, "pe_right_name", ""),
        "support_left": getattr(row, "support_left", True),
        "support_right": getattr(row, "support_right", True),
        "group_id": getattr(row, "group_id", None),
        "source": row.source,
        "order_no": row.order_no,
        "error": row.error,
    }


def _element_or_raise(element_id: int) -> Element:
    element = orm.session().get(Element, element_id) if orm.is_open() else None
    if element is None:
        raise ToolError(f"找不到 id={element_id} 的构件。请先调 list_elements 查看。")
    return element


def element_detail_dict(element_id: int) -> dict:
    """构件完整详情（含管材 / 参数 / 工程量 / 图集自动值预览）。"""
    from app.viewmodels import unit_vm

    element = _element_or_raise(element_id)
    snapshot = unit_vm.element_snapshot(element_id) or {}
    pipes = [
        {
            "id": pipe.id,
            "mat": pipe.mat,
            "cat": pipe.pipe_category,
            "dn": pipe.dn,
            "content": pipe.content,
            "t": pipe.t,
        }
        for pipe in element.pipes
    ]
    # param_rows 会过滤掉该类别不显示的图集残留行，按 id 对齐而不是 zip
    lock_by_id = {row.id: row.lock_name for row in unit_vm.param_rows(element_id)}
    params = [
        {
            "id": param.id,
            "key": param.key,
            "unit": param.unit,
            "value": param.value,
            "lock_name": bool(lock_by_id.get(param.id, False)),
        }
        for param in element.params
    ]
    # 候选参数（v9，直埋构件）：参数值锁定时 AI 用 update_atlas_candidate 改这里
    atlas_candidates = [
        {
            "candidate_id": row.id,
            "con_found": row.con_found,
            "angle": row.angle,
            "t": row.t,
            "a": row.a,
            "c1": row.c1,
            "c2": row.c2,
        }
        for row in element.atlas_candidates
    ]
    quantities = [
        {"id": quantity.id, "category": quantity.category, "item": quantity.item,
         "unit": quantity.unit, "value": quantity.value}
        for quantity in element.quantities
    ]
    try:
        auto_atlas = unit_vm.auto_atlas_params(element)
    except Exception:
        auto_atlas = {}
    try:
        auto_thickness = unit_vm.auto_pipe_thicknesses(element)
    except Exception:
        auto_thickness = {}
    return {
        "id": element.id,
        "unit_id": element.unit_id,
        "name": element.name,
        "category": category_name(element.category),
        "category_value": element.category,
        "depth": element.depth,
        "amount": element.amount,
        "unit": unit_of(element.category),
        "pe_name": element.pe_name,
        "pf_name": element.pf_name,
        "pp_name": element.pp_name,
        "pw_name": element.pw_name,
        "source": element.source,
        "order_no": element.order_no,
        "pipes": pipes,
        "params": params,
        "quantities": quantities,
        "auto": {
            "atlas_params": auto_atlas,
            "pipe_thicknesses": {
                str(pipe_id): value for pipe_id, value in auto_thickness.items()
            },
        },
        "snapshot_meta": {"snapshot_keys": sorted(snapshot)},
    }


# --------------------------------------------------------------------------- #
# 工程量
# --------------------------------------------------------------------------- #
def quantity_dict(quantity, include_steps: bool = True) -> dict:
    parts = quantity.key.split("|")
    data = {
        "key": quantity.key,
        "category": parts[0] if parts else "",
        "item": parts[1] if len(parts) > 1 else "",
        "unit": parts[2] if len(parts) > 2 else "",
        "value": quantity.value,
        "expression": quantity.expression,
    }
    if include_steps:
        data["steps"] = [
            {"note": note, "expr": expr} for note, expr in quantity.steps()
        ]
    return data


def qdict_dict(qdict, include_steps: bool = True, include_expressions: bool = True) -> list[dict]:
    from app.core.calc.tracer import sorted_items

    rows: list[dict] = []
    for quantity in sorted_items(qdict):
        row = quantity_dict(quantity, include_steps=include_steps)
        if not include_expressions:
            row.pop("expression", None)
            row.pop("steps", None)
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# 项目树
# --------------------------------------------------------------------------- #
def tree_dict() -> dict:
    from app.services import project_io

    if not project_io.is_open():
        raise ToolError("当前没有打开的工程，请先 open_project。")
    info = project_io.basic_info()
    segments: list[dict] = []
    for segment in project_io.segments():
        units: list[dict] = []
        for unit in project_io.units(segment.id):
            count = orm.session().scalar(
                select(func.count(Element.id)).where(Element.unit_id == unit.id)
            )
            units.append(
                {"id": unit.id, "name": unit.name, "order_no": unit.order_no,
                 "element_count": int(count or 0)}
            )
        segments.append(
            {"id": segment.id, "name": segment.name, "order_no": segment.order_no,
             "units": units}
        )
    return {
        "project_name": info.project_name if info else project_io.project_name(),
        "project_index": info.project_index if info else "",
        "author": info.author if info else "",
        "schema_version": orm.get_meta("schema_version", ""),
        "segments": segments,
    }


# --------------------------------------------------------------------------- #
# 原则
# --------------------------------------------------------------------------- #
def describe_component(component: Component | None) -> str:
    """构件描述（旧版 mcComponent.Discribe：描述公式代入参数并去括号）。"""
    if component is None:
        return ""
    from app.core.calc.engine import load_params

    params = load_params(component)
    if not params:
        return component.formula
    text = component.formula
    for key in params:
        text = re.sub(r"\b" + re.escape(key) + r"\b", params[key][1], text)
    if "参数循环引用" in text:
        return "参数循环引用"
    return text.replace("(", "").replace(")", "")


def component_dict(component: Component) -> dict:
    params: list[dict] = []
    f_formulas: list[dict] = []
    z_formulas: list[dict] = []
    for param in component.params:
        display, _, expression = (param.value or "").partition("|")
        entry = {"key": param.key, "display": display, "expression": expression}
        if len(param.key) == 2 and param.key.startswith("F"):
            f_formulas.append(entry)
        elif len(param.key) == 2 and param.key.startswith("Z"):
            z_formulas.append(entry)
        else:
            params.append(entry)
    return {
        "component_id": component.id,
        "name": component.name,
        "describe": describe_component(component),
        "formula": component.formula,
        "params": params,
        "f_formulas": f_formulas,
        "z_formulas": z_formulas,
        "owner": {
            "foundation_id": component.foundation_id,
            "enclosure_level_id": component.enclosure_level_id,
            "enclosure_work_id": component.enclosure_work_id,
        },
    }


def enclosure_dict(enclosure: PcpEnclosure) -> dict:
    works = []
    for work in enclosure.works_sorted():
        levels = [
            {
                "level_id": level.id,
                "h": level.h,
                "step_width": level.step_width,
                "level_type": level.name,
                "component_id": level.components[0].id if level.components else None,
                "describe": describe_component(level.components[0] if level.components else None),
            }
            for level in sorted(work.levels, key=lambda item: (item.order_no, item.id))
        ]
        waterstop = work.waterstops[0] if work.waterstops else None
        works.append(
            {
                "work_id": work.id,
                "min_depth": work.min_depth,
                "cpnt_cat": work.cpnt_cat,
                "stop_type": waterstop.name if waterstop else "无",
                "waterstop_component_id": waterstop.id if waterstop else None,
                "levels": levels,
            }
        )
    # v10 起围护原则只带围护做法（挖填类型 → 挖填降水原则、管道基础 → 地基原则）
    return {
        "name": enclosure.name,
        "works": works,
    }


def foundation_dict(foundation: PcpFoundation) -> dict:
    component = foundation.components[0] if foundation.components else None
    return {
        "name": foundation.name,
        # v10 起管道基础（砼基础开关 / 基础角度 / 垫层）并入地基原则
        "con_found": bool(foundation.con_found),
        "found_angle": int(foundation.found_angle),
        "cushions": [
            {"name": cushion.name, "h": cushion.h}
            for cushion in sorted(foundation.cushions, key=lambda item: (item.order_no, item.id))
        ],
        "replacements": [
            {"name": item.name, "h": item.h}
            for item in sorted(foundation.replacements, key=lambda row: (row.order_no, row.id))
        ],
        "component": component_dict(component) if component else None,
    }


def precipitation_dict(precipitation: PcpPrecipitation) -> dict:
    wells: dict[str, dict] = {}
    for key in PRECIPITATION_COLUMNS:
        elevation, gap, sides = parse_precipitation(getattr(precipitation, key), key)
        wells[PRECIPITATION_LABELS[key]] = {
            "key": key,
            "enabled": elevation >= 0,
            "elevation": elevation,
            "gap": gap,
            "sides": sides,
        }
    # v10 起挖填类型（开挖土质 / 回填材质）并入挖填降水原则
    return {
        "name": precipitation.name,
        "excvt": precipitation.excvt,
        "dock_l": precipitation.dock_l,
        "dock_h": precipitation.dock_h,
        "cover50": precipitation.cover50,
        "cover": precipitation.cover,
        "wells": wells,
    }


def width_dict(width: PcpWidth) -> dict:
    tables: dict[str, dict[str, dict[str, float]]] = {"work": {}, "groove_b": {}}
    for item in width.items:
        tables.setdefault(item.kind, {}).setdefault(item.pipe_type, {})[
            str(item.dn)
        ] = item.width
    return {"name": width.name, "mode": width.groove_width, **tables}


def principle_usage(kind: str, name: str) -> int:
    """原则被构件引用的次数（多原则引用行也计入）。"""
    if not orm.is_open():
        return 0
    session = orm.session()
    field = {
        "enclosure": Element.pe_name,
        "foundation": Element.pf_name,
        "precipitation": Element.pp_name,
        "width": Element.pw_name,
    }.get(kind)
    count = 0
    if field is not None:
        count = int(session.scalar(select(func.count(Element.id)).where(field == name)) or 0)
    return count


# --------------------------------------------------------------------------- #
# 构件库
# --------------------------------------------------------------------------- #
def library_template_dict(category: str, unit: str, index: int, template) -> dict:
    return {
        "category": category,
        "unit": unit,
        "index": index,
        "label": template.label,
        "name": template.name,
        "category_value": template.category,
        "category_name": category_name(template.category),
        "depth": template.depth,
        "amount": template.amount,
        "source": template.source,
        "pipes": [
            {
                "mat": pipe.mat,
                "cat": pipe.cat,
                "dn": pipe.dn,
                "content": pipe.content,
                "t": {str(angle): value for angle, value in pipe.thickness.items()},
            }
            for pipe in template.pipes
        ],
        "params": [list(param) for param in template.params],
        "atlas": {
            key: (
                {"a": row[0], "c1": row[1], "c2": row[2]}
                if row is not None
                else {"a": None, "c1": None, "c2": None}
            )
            for key, row in template.atlas.items()
        },
    }
