"""E 组：图集与构件库查询（T56~T63，全只读）。"""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select

from app.agent.errors import ToolError
from app.agent.serializers import library_template_dict
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import parse_category, require_open
from app.core.models import base as orm
from app.core.models.models import PcpWidth


def _width_tables(name: str | None) -> tuple[dict, dict]:
    """取面宽原则的两张表（未指定名称时用第一条原则）。"""
    width = None
    session = orm.session()
    if name:
        width = session.scalar(select(PcpWidth).where(PcpWidth.name == str(name)).order_by(PcpWidth.id))
        if width is None:
            raise ToolError(f"面宽原则“{name}”不存在。")
    else:
        width = session.scalar(select(PcpWidth).order_by(PcpWidth.order_no, PcpWidth.id))
    if width is None:
        return {}, {}
    session.expire(width)
    work: dict[str, dict[int, float]] = {}
    groove: dict[str, dict[int, float]] = {}
    for item in width.items:
        target = work if item.kind == "work" else groove
        target.setdefault(item.pipe_type, {})[item.dn] = item.width
    return work, groove


def tool_resolve_atlas(arguments: dict) -> dict:
    from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas

    category = parse_category(arguments.get("category"))
    raw_pipes = arguments.get("pipes")
    if not raw_pipes:
        raise ToolError("请提供 pipes（至少一根管道）：[{mat, dn, t?}]。")
    pipes: list[PipeSpec] = []
    for raw in raw_pipes:
        if not isinstance(raw, dict):
            raise ToolError("pipes 每项必须是对象 {mat, dn, t}。")
        try:
            dn = int(raw.get("dn"))
        except (TypeError, ValueError) as error:
            raise ToolError("管径 dn 需为整数（mm）。") from error
        t = raw.get("t")
        pipes.append(
            PipeSpec(
                mat=str(raw.get("mat") or ""),
                dn=dn,
                t=float(t) if t not in (None, "") else None,
            )
        )
    require_open()
    widths, groove_bs = _width_tables(arguments.get("width_principle"))
    overrides = arguments.get("overrides") or {}
    keywords = arguments.get("keywords") if isinstance(arguments.get("keywords"), dict) else {}
    size_b = arguments.get("size_b")
    if size_b in (None, ""):
        size_b = pipes[0].dn / 1000.0
    query = AtlasQuery(
        category=category,
        pipes=pipes,
        con_found=bool(arguments.get("con_found", True)),
        found_angle=int(arguments.get("found_angle") or 120),
        groove_width=str(arguments.get("width_mode") or "WorkWidth"),
        size_b=float(size_b),
        widths=widths,
        groove_bs=groove_bs,
        a=arguments.get("a", overrides.get("a")),
        c1=arguments.get("c1", overrides.get("c1")),
        c2=arguments.get("c2", overrides.get("c2")),
    )
    result = asdict(resolve_atlas(query))
    return {
        "ok": True,
        "data": {
            **result,
            "unit": "mm（groove_b 已换算为 m）",
            "note": "a/c1/c2 为 None 时按图集行取值；显式 0 是有效覆盖。",
            "extra": keywords,
        },
    }


def tool_list_atlas_tables(arguments: dict) -> dict:
    from app.services.atlas import ATLAS_TABLES

    return {
        "ok": True,
        "data": {
            "tables": [
                {"table_index": index, "file": file_name, "sheet": sheet}
                for index, (file_name, sheet) in enumerate(ATLAS_TABLES)
            ]
        },
    }


def tool_query_atlas_table(arguments: dict) -> dict:
    from app.services.atlas import catalog

    try:
        table_index = int(arguments.get("table_index"))
    except (TypeError, ValueError) as error:
        raise ToolError("table_index 需为整数（见 list_atlas_tables）。") from error
    dn = arguments.get("dn")
    if dn in (None, ""):
        raise ToolError("请提供管径 dn（mm）。")
    dn_text = str(int(float(dn))) if str(dn).replace(".", "", 1).isdigit() else str(dn)
    angle = arguments.get("angle")
    level = arguments.get("level")
    record = catalog().find(
        table_index,
        dn_text,
        str(angle) if angle not in (None, "") else None,
        str(level) if level not in (None, "") else None,
    )
    if record is None:
        return {
            "ok": True,
            "data": {"found": False},
            "summary": f"表 {table_index} 中未找到 dn={dn_text} 的行（可去掉 angle/level 再试）。",
        }
    return {"ok": True, "data": {"found": True, "row": record}}


def tool_get_default_width_tables(arguments: dict) -> dict:
    from app.services.atlas import default_width_tables

    work, groove = default_width_tables()
    return {
        "ok": True,
        "data": {
            "work": {
                category: {str(dn): value for dn, value in sorted(values.items())}
                for category, values in work.items()
            },
            "groove_b": {
                category: {str(dn): value for dn, value in sorted(values.items())}
                for category, values in groove.items()
            },
            "unit": "mm",
        },
    }


def tool_list_library_templates(arguments: dict) -> dict:
    from app.services.element_library import search_templates

    category = arguments.get("category")
    keyword = str(arguments.get("keyword") or "")
    limit = int(arguments.get("limit") or 100)
    results = search_templates(str(category) if category else None, keyword)
    items = []
    for item in results[:limit]:
        template = item["template"]
        items.append(
            {
                "category": item["category"],
                "unit": item["unit"],
                "index": item["index"],
                "label": template.label,
                "name": template.name,
                "category_value": template.category,
                "pipes": [
                    {"mat": pipe.mat, "cat": pipe.cat, "dn": pipe.dn, "content": pipe.content}
                    for pipe in template.pipes
                ],
            }
        )
    return {
        "ok": True,
        "data": {
            "items": items,
            "total": len(results),
            "truncated": len(results) > limit,
            "hint": "用 get_library_template(category, unit, index) 取完整模板后 insert_element_from_template。",
        },
    }


def tool_get_library_template(arguments: dict) -> dict:
    from app.services.element_library import element_library

    category = str(arguments.get("category") or "").strip()
    unit = str(arguments.get("unit") or "").strip()
    try:
        index = int(arguments.get("index"))
    except (TypeError, ValueError) as error:
        raise ToolError("index 需为整数（见 list_library_templates）。") from error
    template = element_library().find(category, unit, index)
    if template is None:
        raise ToolError(
            f"找不到构件库模板（{category}/{unit}/{index}）。请先调 list_library_templates。"
        )
    return {"ok": True, "data": library_template_dict(category, unit, index, template)}


def tool_list_component_templates(arguments: dict) -> dict:
    from app.services.atlas import component_library

    group = str(arguments.get("group") or "").strip()
    if group not in ("Ei", "WSi", "Fi"):
        raise ToolError("group 只能是 Ei（围护）/ WSi（止水）/ Fi（特殊地基）。")
    keyword = str(arguments.get("keyword") or "").strip().lower()
    library = component_library()
    rows = []
    for name in library.names(group):
        template = library.template(group, name)
        if keyword and keyword not in name.lower():
            continue
        rows.append(
            {
                "name": name,
                "describe": template.describe if template else "",
                "param_keys": sorted(template.params) if template else [],
            }
        )
    return {"ok": True, "data": {"group": group, "templates": rows}}


def tool_get_component_template(arguments: dict) -> dict:
    from app.services.atlas import component_library

    group = str(arguments.get("group") or "").strip()
    name = str(arguments.get("name") or "").strip()
    if group not in ("Ei", "WSi", "Fi"):
        raise ToolError("group 只能是 Ei / WSi / Fi。")
    template = component_library().template(group, name)
    if template is None:
        raise ToolError(
            f"构件模板“{name}”不在 {group} 库。"
            f"可用：{'、'.join(component_library().names(group))}"
        )
    return {
        "ok": True,
        "data": {
            "group": group,
            "name": template.name,
            "describe": template.describe,
            "params": {
                key: {"display": display, "value": value}
                for key, (display, value) in template.params.items()
            },
        },
    }


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "resolve_atlas",
            "按构件类别/管材/管径查询图集参数（mm）：oD/t/a/C1/C2/工作面宽/沟槽底宽。只读。",
            {"type": "object", "properties": {
                "category": {"type": "string", "description": "构件类别名"},
                "pipes": {"type": "array", "items": {"type": "object"},
                          "description": "[{mat, dn, t?}]"},
                "con_found": {"type": "boolean", "default": True},
                "found_angle": {"type": "integer", "default": 120},
                "width_mode": {"type": "string", "enum": ["WorkWidth", "B"]},
                "width_principle": {"type": "string", "description": "面宽原则名（默认第一条）"},
                "size_b": {"type": "number", "description": "断面宽 m（默认首管管径/1000）"},
                "a": {"type": "number"}, "c1": {"type": "number"}, "c2": {"type": "number"}},
             "required": ["category", "pipes"]},
            tool_resolve_atlas, read_only=True,
        )
    )
    registry.register(
        Tool(
            "list_atlas_tables", "列出 10 张图集表（table_index/file/sheet）。只读。",
            {"type": "object", "properties": {}},
            tool_list_atlas_tables, read_only=True,
        )
    )
    registry.register(
        Tool(
            "query_atlas_table", "按管径/角度/级别查某张图集表的原始行。只读。",
            {"type": "object", "properties": {
                "table_index": {"type": "integer"}, "dn": {"type": "string"},
                "angle": {"type": "string"}, "level": {"type": "string"}},
             "required": ["table_index", "dn"]},
            tool_query_atlas_table, read_only=True,
        )
    )
    registry.register(
        Tool(
            "get_default_width_tables", "读取工作面宽度/沟槽宽度默认矩阵（GB 50268-2008，mm）。只读。",
            {"type": "object", "properties": {}},
            tool_get_default_width_tables, read_only=True,
        )
    )
    registry.register(
        Tool(
            "list_library_templates", "关键词检索构件库模板（返回 category/unit/index 供插入）。只读。",
            {"type": "object", "properties": {
                "category": {"type": "string", "description": "构件库类别，省略=全部"},
                "keyword": {"type": "string"}, "limit": {"type": "integer", "default": 100}},
             },
            tool_list_library_templates, read_only=True,
        )
    )
    registry.register(
        Tool(
            "get_library_template", "读取构件库模板完整字段（管材/参数）。只读。",
            {"type": "object", "properties": {
                "category": {"type": "string"}, "unit": {"type": "string"},
                "index": {"type": "integer"}},
             "required": ["category", "unit", "index"]},
            tool_get_library_template, read_only=True,
        )
    )
    registry.register(
        Tool(
            "list_component_templates", "列出构件公式库模板（Ei 围护/WSi 止水/Fi 特殊地基）。只读。",
            {"type": "object", "properties": {
                "group": {"type": "string", "enum": ["Ei", "WSi", "Fi"]},
                "keyword": {"type": "string"}}, "required": ["group"]},
            tool_list_component_templates, read_only=True,
        )
    )
    registry.register(
        Tool(
            "get_component_template", "读取构件公式库模板的参数与公式。只读。",
            {"type": "object", "properties": {
                "group": {"type": "string", "enum": ["Ei", "WSi", "Fi"]},
                "name": {"type": "string"}}, "required": ["group", "name"]},
            tool_get_component_template, read_only=True,
        )
    )
