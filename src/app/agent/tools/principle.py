"""D 组：六类原则的读写（T36~T55）。"""

from __future__ import annotations

from app.agent.errors import ToolError
from app.agent.serializers import (
    component_dict,
    enclosure_dict,
    foundation_dict,
    precipitation_dict,
    principle_usage,
    width_dict,
)
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import call_edit, check_write_path, find_principle, require_open
from app.core.event_bus import bus
from app.services import principle_edit, project_io


_KINDS = ["enclosure", "foundation", "precipitation", "width"]


def _detail(kind: str, obj) -> dict:
    if kind == "enclosure":
        return enclosure_dict(obj)
    if kind == "foundation":
        return foundation_dict(obj)
    if kind == "precipitation":
        return precipitation_dict(obj)
    return width_dict(obj)


def _notify(renamed: bool = False) -> None:
    if renamed:
        bus().tree_structure_changed.emit()
    bus().principle_changed.emit()


def tool_list_principles(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "")
    if kind not in _KINDS:
        raise ToolError("kind 只能是 enclosure / foundation / precipitation / width。")
    loaders = {
        "enclosure": project_io.enclosures,
        "foundation": project_io.foundations,
        "precipitation": project_io.precipitations,
        "width": project_io.width_principles,
    }
    rows = [
        {
            "id": obj.id,
            "name": obj.name,
            "order_no": obj.order_no,
            "usage": principle_usage(kind, obj.name),
        }
        for obj in loaders[kind]()
    ]
    return {"ok": True, "data": {"kind": kind, "principles": rows}}


def tool_get_principle_detail(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "")
    obj = find_principle(kind, arguments.get("name"))
    return {"ok": True, "data": _detail(kind, obj)}


def tool_create_enclosure(arguments: dict) -> dict:
    require_open()
    name = str(arguments.get("name") or "新围护原则")
    enclosure = project_io.create_enclosure(name)
    if enclosure is None:
        raise ToolError("新建围护原则失败：请确认已打开工程。")
    fields = {
        key: arguments[key]
        for key in ("excvt", "found_angle", "con_found", "dock_l", "dock_h", "cover50", "cover")
        if arguments.get(key) is not None
    }
    cushions = arguments.get("cushions")
    if fields or cushions is not None:
        call_edit(principle_edit.apply_enclosure_fields, enclosure.id, fields, cushions)
    works = arguments.get("works")
    if works is not None:
        call_edit(principle_edit.apply_enclosure_works, enclosure.id, works)
    _notify(renamed=True)
    return {"ok": True, "data": enclosure_dict(enclosure)}


def tool_create_foundation(arguments: dict) -> dict:
    require_open()
    name = str(arguments.get("name") or "新地基原则")
    foundation = project_io.create_foundation(name)
    if foundation is None:
        raise ToolError("新建地基原则失败：请确认已打开工程。")
    layers = arguments.get("layers")
    component = arguments.get("component")
    if layers is not None or component is not None:
        call_edit(principle_edit.apply_foundation, foundation.id, layers, component)
    _notify(renamed=True)
    return {"ok": True, "data": foundation_dict(foundation)}


def tool_create_precipitation(arguments: dict) -> dict:
    require_open()
    name = str(arguments.get("name") or "新降水原则")
    precipitation = project_io.create_precipitation(name)
    if precipitation is None:
        raise ToolError("新建降水原则失败：请确认已打开工程。")
    wells = arguments.get("wells")
    if wells:
        call_edit(principle_edit.apply_precipitation_wells, precipitation.id, wells)
    _notify(renamed=True)
    return {"ok": True, "data": precipitation_dict(precipitation)}


def tool_create_width_principle(arguments: dict) -> dict:
    require_open()
    name = str(arguments.get("name") or "新面宽原则")
    width = project_io.create_width(name)
    if width is None:
        raise ToolError("新建面宽原则失败：请确认已打开工程。")
    mode = arguments.get("mode")
    items = arguments.get("items")
    if mode or items is not None:
        call_edit(principle_edit.apply_width_items, width.id, mode, items)
    _notify(renamed=True)
    return {"ok": True, "data": width_dict(width)}


def tool_rename_principle(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "")
    obj = find_principle(kind, arguments.get("name"))
    new_name = str(arguments.get("new_name") or "").strip()
    if not new_name:
        raise ToolError("new_name 不能为空。")
    renamers = {
        "enclosure": project_io.rename_enclosure,
        "foundation": project_io.rename_foundation,
        "precipitation": project_io.rename_precipitation,
        "width": project_io.rename_width,
    }
    if kind not in renamers:
        raise ToolError("kind 只能是 enclosure / foundation / precipitation / width。")
    renamers[kind](obj.id, new_name)
    _notify(renamed=True)
    return {"ok": True, "data": {"kind": kind, "name": new_name}}


def tool_delete_principle(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "")
    obj = find_principle(kind, arguments.get("name"))
    replacement = arguments.get("merge_target_name")
    deleters = {
        "enclosure": project_io.delete_enclosure,
        "foundation": project_io.delete_foundation,
        "precipitation": project_io.delete_precipitation,
        "width": project_io.delete_width,
    }
    if kind not in deleters:
        raise ToolError("kind 只能是 enclosure / foundation / precipitation / width。")
    error = deleters[kind](obj.id, replacement)
    if error:
        raise ToolError(error)
    _notify(renamed=True)
    return {"ok": True, "data": {"kind": kind, "deleted": obj.name,
                                 "merged_into": replacement or "（自动选择）"}}


def tool_set_enclosure_fields(arguments: dict) -> dict:
    require_open()
    enclosure = find_principle("enclosure", arguments.get("name"))
    fields = {
        key: arguments[key]
        for key in ("excvt", "found_angle", "con_found", "dock_l", "dock_h", "cover50", "cover")
        if arguments.get(key) is not None
    }
    cushions = arguments.get("cushions")
    if not fields and cushions is None:
        raise ToolError("没有给出要修改的字段。")
    call_edit(principle_edit.apply_enclosure_fields, enclosure.id, fields, cushions)
    _notify()
    return {"ok": True, "data": enclosure_dict(enclosure)}


def tool_set_enclosure_works(arguments: dict) -> dict:
    require_open()
    enclosure = find_principle("enclosure", arguments.get("name"))
    works = arguments.get("works")
    if works is None:
        raise ToolError("请提供 works 列表（整表替换）。")
    call_edit(principle_edit.apply_enclosure_works, enclosure.id, works)
    _notify()
    return {"ok": True, "data": enclosure_dict(enclosure)}


def tool_set_work_levels(arguments: dict) -> dict:
    require_open()
    work_id = arguments.get("work_id")
    if work_id in (None, ""):
        raise ToolError("请提供 work_id（见 get_principle_detail 的 works）。")
    levels = arguments.get("levels")
    if levels is None:
        raise ToolError("请提供 levels 列表（整表替换）。")
    call_edit(principle_edit.apply_work_levels, int(work_id), levels)
    _notify()
    return {"ok": True, "data": {"work_id": int(work_id), "levels": levels}}


def tool_set_replacement_layers(arguments: dict) -> dict:
    require_open()
    foundation = find_principle("foundation", arguments.get("name"))
    layers = arguments.get("layers")
    if layers is None:
        raise ToolError("请提供 layers 列表（整表替换）。")
    call_edit(principle_edit.apply_foundation, foundation.id, layers, None)
    _notify()
    return {"ok": True, "data": foundation_dict(foundation)}


def tool_set_foundation_component(arguments: dict) -> dict:
    require_open()
    foundation = find_principle("foundation", arguments.get("name"))
    component = {
        "template_name": arguments.get("template_name"),
        "params": arguments.get("params") or {},
    }
    if arguments.get("remove"):
        component = {"remove": True}
    elif not component["template_name"]:
        raise ToolError("请提供 template_name（先用 list_component_templates group=Fi 查询），或传 remove=true。")
    call_edit(principle_edit.apply_foundation, foundation.id, None, component)
    _notify()
    return {"ok": True, "data": foundation_dict(foundation)}


def tool_set_precipitation_wells(arguments: dict) -> dict:
    require_open()
    precipitation = find_principle("precipitation", arguments.get("name"))
    wells = arguments.get("wells")
    if not wells:
        raise ToolError("请提供 wells（按井型标签：湿土排水/轻型井点/喷射井点/大口径井点/深井）。")
    call_edit(principle_edit.apply_precipitation_wells, precipitation.id, wells)
    _notify()
    return {"ok": True, "data": precipitation_dict(precipitation)}


def tool_set_width_items(arguments: dict) -> dict:
    require_open()
    width = find_principle("width", arguments.get("name"))
    mode = arguments.get("mode")
    items = arguments.get("items")
    if not mode and items is None:
        raise ToolError("请提供 mode 或 items。")
    call_edit(principle_edit.apply_width_items, width.id, mode, items)
    _notify()
    return {"ok": True, "data": width_dict(width)}


def tool_reset_width_to_atlas(arguments: dict) -> dict:
    require_open()
    width = find_principle("width", arguments.get("name"))
    call_edit(principle_edit.reset_width_to_atlas, width.id)
    _notify()
    return {"ok": True, "data": width_dict(width)}


def tool_get_component_detail(arguments: dict) -> dict:
    require_open()
    component_id = arguments.get("component_id")
    if component_id in (None, ""):
        raise ToolError("请提供 component_id（见原则详情的 component/levels）。")
    from app.core.models.models import Component
    from app.core.models import base as orm

    component = orm.session().get(Component, int(component_id))
    if component is None:
        raise ToolError(f"找不到 component_id={component_id}。")
    return {"ok": True, "data": component_dict(component)}


def tool_update_component_params(arguments: dict) -> dict:
    require_open()
    component_id = arguments.get("component_id")
    if component_id in (None, ""):
        raise ToolError("请提供 component_id。")
    params = arguments.get("params")
    if not isinstance(params, dict) or not params:
        raise ToolError("请提供 params 对象：{键: {display, expression}}。")
    call_edit(principle_edit.apply_component_params, int(component_id), params)
    _notify()
    from app.core.models.models import Component
    from app.core.models import base as orm

    return {"ok": True, "data": component_dict(orm.session().get(Component, int(component_id)))}


def tool_export_principle(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "")
    obj = find_principle(kind, arguments.get("name"))
    path = str(arguments.get("path") or "").strip()
    if not path:
        raise ToolError("请提供导出路径 path（*.spcp）。")
    check_write_path(path)
    exporters = {
        "enclosure": project_io.export_enclosure_spcp,
        "foundation": project_io.export_foundation_spcp,
        "precipitation": project_io.export_precipitation_spcp,
        "width": project_io.export_width_spcp,
    }
    if kind not in exporters:
        raise ToolError("kind 只能是 enclosure / foundation / precipitation / width。")
    target = exporters[kind](obj.id, path)
    return {"ok": True, "data": {"path": str(target), "kind": kind, "name": obj.name}}


def tool_import_principle(arguments: dict) -> dict:
    require_open()
    path = str(arguments.get("path") or "").strip()
    if not path:
        raise ToolError("请提供 *.spcp 文件路径。")
    kind, name = project_io.import_spcp(path)
    _notify(renamed=True)
    return {"ok": True, "data": {"kind": kind, "name": name}}


_WORKS_SCHEMA = {
    "type": "array",
    "description": "做法表（整表替换）：[{min_depth, cpnt_cat, stop_type, levels:[{h, step_width, level_type}]}]",
    "items": {"type": "object"},
}
_LEVELS_SCHEMA = {
    "type": "array",
    "description": "[{h, step_width, level_type}]；h=-1 表示均分剩余高度",
    "items": {"type": "object"},
}
_WELLS_SCHEMA = {
    "type": "object",
    "description": "{井型: {enabled, elevation, gap, sides}}；井型=湿土排水/轻型井点/喷射井点/大口径井点/深井",
}


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "list_principles", "列出某类原则（含被引用次数）。只读。kind=enclosure/foundation/precipitation/width。",
            {"type": "object", "properties": {"kind": {"type": "string", "enum": _KINDS}},
             "required": ["kind"]},
            tool_list_principles, read_only=True,
        )
    )
    registry.register(
        Tool(
            "get_principle_detail", "读取原则完整详情（围护含做法/多级/止水；地基含换填与构件；降水含五井型；面宽含矩阵）。只读。",
            {"type": "object", "properties": {
                "kind": {"type": "string", "enum": _KINDS},
                "name": {"type": "string"}}, "required": ["kind", "name"]},
            tool_get_principle_detail, read_only=True,
        )
    )
    registry.register(
        Tool(
            "create_enclosure", "新建围护原则（可一次提交顶部字段/垫层/做法表）。写操作。",
            {"type": "object", "properties": {
                "name": {"type": "string"},
                "excvt": {"type": "string"}, "found_angle": {"type": "integer"},
                "con_found": {"type": "boolean"}, "dock_l": {"type": "string"},
                "dock_h": {"type": "string"}, "cover50": {"type": "string"},
                "cover": {"type": "string"},
                "cushions": {"type": "array", "items": {"type": "object"},
                             "description": "[{name, h}] 垫层"},
                "works": _WORKS_SCHEMA}, "required": ["name"]},
            tool_create_enclosure,
        )
    )
    registry.register(
        Tool(
            "create_foundation", "新建地基原则（换填层 + 特殊地基构件）。写操作。",
            {"type": "object", "properties": {
                "name": {"type": "string"},
                "layers": {"type": "array", "items": {"type": "object"},
                           "description": "[{name, h}] 换填层"},
                "component": {"type": "object",
                              "description": "{template_name, params:{key:{display,expression}}}"}},
             "required": ["name"]},
            tool_create_foundation,
        )
    )
    registry.register(
        Tool(
            "create_precipitation", "新建降水原则（五井型参数）。写操作。",
            {"type": "object", "properties": {"name": {"type": "string"}, "wells": _WELLS_SCHEMA},
             "required": ["name"]},
            tool_create_precipitation,
        )
    )
    registry.register(
        Tool(
            "create_width_principle", "新建面宽原则（默认播种图集宽度表；可指定取值方式与条目）。写操作。",
            {"type": "object", "properties": {
                "name": {"type": "string"},
                "mode": {"type": "string", "enum": ["WorkWidth", "B"]},
                "items": {"type": "array", "items": {"type": "object"}}},
             "required": ["name"]},
            tool_create_width_principle,
        )
    )
    registry.register(
        Tool(
            "rename_principle", "重命名原则（同步所有构件引用）。写操作。",
            {"type": "object", "properties": {
                "kind": {"type": "string", "enum": _KINDS},
                "name": {"type": "string"}, "new_name": {"type": "string"}},
             "required": ["kind", "name", "new_name"]},
            tool_rename_principle,
        )
    )
    registry.register(
        Tool(
            "delete_principle", "删除原则（引用并入 merge_target_name；最后一条拒绝删除）。写操作。",
            {"type": "object", "properties": {
                "kind": {"type": "string", "enum": _KINDS},
                "name": {"type": "string"}, "merge_target_name": {"type": "string"}},
             "required": ["kind", "name"]},
            tool_delete_principle,
        )
    )
    registry.register(
        Tool(
            "set_enclosure_fields", "修改围护原则顶部字段（土质/角度/坞塝/覆土/垫层整表）。写操作。",
            {"type": "object", "properties": {
                "name": {"type": "string"}, "excvt": {"type": "string"},
                "found_angle": {"type": "integer"}, "con_found": {"type": "boolean"},
                "dock_l": {"type": "string"}, "dock_h": {"type": "string"},
                "cover50": {"type": "string"}, "cover": {"type": "string"},
                "cushions": {"type": "array", "items": {"type": "object"}}},
             "required": ["name"]},
            tool_set_enclosure_fields,
        )
    )
    registry.register(
        Tool(
            "set_enclosure_works", "整表替换围护做法（做法表/多级围护/止水）。写操作。",
            {"type": "object", "properties": {"name": {"type": "string"}, "works": _WORKS_SCHEMA},
             "required": ["name", "works"]},
            tool_set_enclosure_works,
        )
    )
    registry.register(
        Tool(
            "set_work_levels", "整表替换某做法的分级（多级围护）。写操作。",
            {"type": "object", "properties": {"work_id": {"type": "integer"}, "levels": _LEVELS_SCHEMA},
             "required": ["work_id", "levels"]},
            tool_set_work_levels,
        )
    )
    registry.register(
        Tool(
            "set_replacement_layers", "整表替换地基原则的换填层。写操作。",
            {"type": "object", "properties": {
                "name": {"type": "string"},
                "layers": {"type": "array", "items": {"type": "object"}}},
             "required": ["name", "layers"]},
            tool_set_replacement_layers,
        )
    )
    registry.register(
        Tool(
            "set_foundation_component", "设置/删除地基原则的特殊地基构件（模板名来自 Fi 库）。写操作。",
            {"type": "object", "properties": {
                "name": {"type": "string"}, "template_name": {"type": "string"},
                "params": {"type": "object"}, "remove": {"type": "boolean"}},
             "required": ["name"]},
            tool_set_foundation_component,
        )
    )
    registry.register(
        Tool(
            "set_precipitation_wells", "设置降水原则的井型参数。写操作。",
            {"type": "object", "properties": {"name": {"type": "string"}, "wells": _WELLS_SCHEMA},
             "required": ["name", "wells"]},
            tool_set_precipitation_wells,
        )
    )
    registry.register(
        Tool(
            "set_width_items", "设置面宽原则取值方式与矩阵条目（按 pipe_type+dn 增量替换）。写操作。",
            {"type": "object", "properties": {
                "name": {"type": "string"},
                "mode": {"type": "string", "enum": ["WorkWidth", "B"]},
                "items": {"type": "array", "items": {"type": "object"},
                          "description": "[{pipe_type, dn, width}]，width 单位 mm"}},
             "required": ["name"]},
            tool_set_width_items,
        )
    )
    registry.register(
        Tool(
            "reset_width_to_atlas", "把面宽原则恢复为图集默认宽度表。写操作。",
            {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            tool_reset_width_to_atlas,
        )
    )
    registry.register(
        Tool(
            "get_component_detail", "读取构件公式详情（参数 + F/Z 公式）。只读。",
            {"type": "object", "properties": {"component_id": {"type": "integer"}},
             "required": ["component_id"]},
            tool_get_component_detail, read_only=True,
        )
    )
    registry.register(
        Tool(
            "update_component_params", "修改构件参数（只允许模板键集内的键，不增删行）。写操作。",
            {"type": "object", "properties": {
                "component_id": {"type": "integer"},
                "params": {"type": "object", "description": "{键: {display, expression}}"}},
             "required": ["component_id", "params"]},
            tool_update_component_params,
        )
    )
    registry.register(
        Tool(
            "export_principle", "导出单条原则为 *.spcp。写操作（文件）。",
            {"type": "object", "properties": {
                "kind": {"type": "string", "enum": _KINDS},
                "name": {"type": "string"}, "path": {"type": "string"}},
             "required": ["kind", "name", "path"]},
            tool_export_principle,
        )
    )
    registry.register(
        Tool(
            "import_principle", "导入 *.spcp 原则文件（重名自动加后缀）。写操作。",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            tool_import_principle,
        )
    )
