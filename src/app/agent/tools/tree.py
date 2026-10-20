"""B 组：项目树（T08~T13）。"""

from __future__ import annotations

from app.agent.errors import ToolError
from app.agent.serializers import tree_dict
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import require_open
from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import Segment, Unit
from app.services import project_io


def _segment(segment_id: int) -> Segment:
    segment = orm.session().get(Segment, int(segment_id))
    if segment is None:
        raise ToolError(f"找不到 id={segment_id} 的标段。请先调 get_project_tree。")
    return segment


def _unit(unit_id: int) -> Unit:
    unit = orm.session().get(Unit, int(unit_id))
    if unit is None:
        raise ToolError(f"找不到 id={unit_id} 的单位工程。请先调 get_project_tree。")
    return unit


def tool_get_project_tree(arguments: dict) -> dict:
    require_open()
    return {"ok": True, "data": tree_dict()}


def tool_add_segment(arguments: dict) -> dict:
    require_open()
    name = str(arguments.get("name") or "新建标段")
    segment = Segment(name=name, order_no=project_io.next_order_no(Segment))
    orm.session().add(segment)
    project_io.commit()
    bus().tree_structure_changed.emit()
    return {"ok": True, "data": {"segment_id": segment.id, "name": segment.name}}


def tool_add_unit(arguments: dict) -> dict:
    require_open()
    segment = _segment(arguments.get("segment_id"))
    name = str(arguments.get("name") or "新建单位工程")
    unit = Unit(
        segment_id=segment.id,
        name=name,
        order_no=project_io.next_order_no(Unit, segment_id=segment.id),
    )
    orm.session().add(unit)
    project_io.commit()
    bus().tree_structure_changed.emit()
    return {"ok": True, "data": {"unit_id": unit.id, "segment_id": segment.id, "name": unit.name}}


def tool_rename_node(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "").strip()
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ToolError("名称不能为空。")
    if kind == "segment":
        target = _segment(arguments.get("id"))
    elif kind == "unit":
        target = _unit(arguments.get("id"))
    else:
        raise ToolError("kind 只能是 segment 或 unit。")
    target.name = name
    project_io.commit()
    bus().tree_structure_changed.emit()
    return {"ok": True, "data": {"kind": kind, "id": target.id, "name": name}}


def tool_delete_node(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "").strip()
    if kind == "segment":
        target = _segment(arguments.get("id"))
        unit_count = len(project_io.units(target.id))
        element_count = sum(
            len(unit.elements) for unit in project_io.units(target.id)
        )
        detail = f"标段“{target.name}”及其 {unit_count} 个单位工程、{element_count} 条构件"
    elif kind == "unit":
        target = _unit(arguments.get("id"))
        detail = f"单位工程“{target.name}”及其 {len(target.elements)} 条构件"
    else:
        raise ToolError("kind 只能是 segment 或 unit。")
    orm.session().delete(target)
    project_io.commit()
    bus().tree_structure_changed.emit()
    return {"ok": True, "data": {"deleted": detail}}


def tool_move_node(arguments: dict) -> dict:
    require_open()
    kind = str(arguments.get("kind") or "").strip()
    index = int(arguments.get("index") or 0)
    if kind == "segment":
        project_io.move_segment(int(arguments.get("id")), index)
    elif kind == "unit":
        target_segment_id = arguments.get("target_segment_id")
        if target_segment_id in (None, ""):
            unit = _unit(arguments.get("id"))
            target_segment_id = unit.segment_id
        _segment(target_segment_id)
        project_io.move_unit(int(arguments.get("id")), int(target_segment_id), index)
    else:
        raise ToolError("kind 只能是 segment 或 unit。")
    bus().tree_structure_changed.emit()
    return {"ok": True, "data": {}}


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_project_tree",
            "读取项目树（工程→标段→单位工程，含单位工程 id 与构件数量）。只读。",
            {"type": "object", "properties": {}},
            tool_get_project_tree,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            "add_segment",
            "新增标段。写操作。",
            {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            tool_add_segment,
        )
    )
    registry.register(
        Tool(
            "add_unit",
            "在标段下新增单位工程。写操作。",
            {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["segment_id", "name"],
            },
            tool_add_unit,
        )
    )
    registry.register(
        Tool(
            "rename_node",
            "重命名标段/单位工程。写操作。",
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["segment", "unit"]},
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["kind", "id", "name"],
            },
            tool_rename_node,
        )
    )
    registry.register(
        Tool(
            "delete_node",
            "删除标段/单位工程（级联删除下属构件，返回删除数量提醒）。写操作。",
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["segment", "unit"]},
                    "id": {"type": "integer"},
                },
                "required": ["kind", "id"],
            },
            tool_delete_node,
        )
    )
    registry.register(
        Tool(
            "move_node",
            "移动标段/单位工程到指定位置（unit 可跨标段）。写操作。",
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["segment", "unit"]},
                    "id": {"type": "integer"},
                    "target_segment_id": {"type": "integer", "description": "unit 用：目标标段"},
                    "index": {"type": "integer", "description": "目标位置（0 起）"},
                },
                "required": ["kind", "id", "index"],
            },
            tool_move_node,
        )
    )
