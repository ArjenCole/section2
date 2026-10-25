"""C 组扩展：管材 / 构件参数 / 工程量行（T22~T35）。"""

from __future__ import annotations

from app.agent.context import resolve_element_id
from app.agent.errors import ToolError
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import require_open
from app.viewmodels import unit_vm


# --------------------------------------------------------------------------- #
# 管材
# --------------------------------------------------------------------------- #
def tool_add_pipe(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    message = unit_vm.pipe_add_error(unit_vm._element(element_id))
    if message:
        raise ToolError(message)
    try:
        dn = int(arguments.get("dn") or 600)
    except (TypeError, ValueError) as error:
        raise ToolError("管径 dn 需为整数（mm）。") from error
    t_value = arguments.get("t")
    t = None
    if t_value not in (None, ""):
        try:
            t = float(t_value)
        except (TypeError, ValueError) as error:
            raise ToolError("壁厚 t 需为数字（mm），留空=自动按图集。") from error
    pipe = unit_vm.create_pipe(
        element_id,
        mat=str(arguments.get("mat") or "Ⅱ级混凝土管"),
        dn=dn,
        content=str(arguments.get("content") if arguments.get("content") is not None else "1"),
        t=t,
        cat=str(arguments.get("cat") or ""),
    )
    if pipe is None:
        raise ToolError(f"找不到 id={element_id} 的构件。")
    return {"ok": True, "data": {"pipe_id": pipe.id, "cat": pipe.pipe_category}}


def tool_update_pipe(arguments: dict) -> dict:
    require_open()
    pipe_id = arguments.get("pipe_id")
    if pipe_id in (None, ""):
        raise ToolError("请提供 pipe_id（见 get_element_detail 的 pipes）。")
    fields = {
        key: arguments[key] for key in ("mat", "cat", "dn", "content", "t") if arguments.get(key) is not None
    }
    if not fields:
        raise ToolError("没有给出要修改的字段（mat/cat/dn/content/t）。")
    pipe = unit_vm.update_pipe(int(pipe_id), **fields)
    if pipe is None:
        raise ToolError(f"找不到 pipe_id={pipe_id}。请先调 get_element_detail。")
    return {"ok": True, "data": {"pipe_id": pipe.id, "cat": pipe.pipe_category}}


def tool_delete_pipe(arguments: dict) -> dict:
    require_open()
    pipe_id = arguments.get("pipe_id")
    if pipe_id in (None, ""):
        raise ToolError("请提供 pipe_id。")
    pipe = unit_vm._pipe(int(pipe_id))
    if pipe is None:
        raise ToolError(f"找不到 pipe_id={pipe_id}。请先调 get_element_detail。")
    message = unit_vm.pipe_delete_error(pipe.element)
    if message:
        raise ToolError(message)
    unit_vm.delete_pipe(int(pipe_id))
    return {"ok": True, "data": {"pipe_id": int(pipe_id)}}


# --------------------------------------------------------------------------- #
# 构件参数
# --------------------------------------------------------------------------- #
def tool_add_param(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    key = str(arguments.get("key") or "").strip()
    if not key:
        raise ToolError("参数名 key 不能为空。")
    param = unit_vm.create_param(
        element_id,
        key=key,
        unit=str(arguments.get("unit") or ""),
        value=str(arguments.get("value") if arguments.get("value") is not None else ""),
    )
    if param is None:
        raise ToolError("该类别构件不显示这个图集参数行（见 param_naming 规则），或构件不存在。")
    return {"ok": True, "data": {"param_id": param.id}}


def tool_update_param(arguments: dict) -> dict:
    require_open()
    param_id = arguments.get("param_id")
    if param_id in (None, ""):
        raise ToolError("请提供 param_id（见 get_element_detail 的 params）。")
    fields = {key: arguments[key] for key in ("key", "unit", "value") if arguments.get(key) is not None}
    if not fields:
        raise ToolError("没有给出要修改的字段（key/unit/value）。")
    param = unit_vm.update_param(int(param_id), **fields)
    if param is None:
        raise ToolError("修改失败：参数行不存在，或该类别不允许该图集参数行。")
    return {"ok": True, "data": {"param_id": param.id}}


def tool_delete_param(arguments: dict) -> dict:
    require_open()
    param_id = arguments.get("param_id")
    if param_id in (None, ""):
        raise ToolError("请提供 param_id。")
    message = unit_vm.delete_param(int(param_id))
    if message:
        raise ToolError(message)
    return {"ok": True, "data": {"param_id": int(param_id)}}


# --------------------------------------------------------------------------- #
# 构筑物工程量行
# --------------------------------------------------------------------------- #
def tool_add_quantity(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    quantity = unit_vm.create_quantity(
        element_id,
        category=str(arguments.get("category") or "构筑物"),
        item=str(arguments.get("item") or ""),
        unit=str(arguments.get("unit") or ""),
        value=str(arguments.get("value") if arguments.get("value") is not None else "0"),
    )
    if quantity is None:
        raise ToolError(f"找不到 id={element_id} 的构件。")
    return {"ok": True, "data": {"quantity_id": quantity.id}}


def tool_update_quantity(arguments: dict) -> dict:
    require_open()
    quantity_id = arguments.get("quantity_id")
    if quantity_id in (None, ""):
        raise ToolError("请提供 quantity_id。")
    fields = {
        key: arguments[key]
        for key in ("category", "item", "unit", "value")
        if arguments.get(key) is not None
    }
    if not fields:
        raise ToolError("没有给出要修改的字段（category/item/unit/value）。")
    quantity = unit_vm.update_quantity(int(quantity_id), **fields)
    if quantity is None:
        raise ToolError(f"找不到 quantity_id={quantity_id}。")
    return {"ok": True, "data": {"quantity_id": quantity.id}}


def tool_delete_quantity(arguments: dict) -> dict:
    require_open()
    quantity_id = arguments.get("quantity_id")
    if quantity_id in (None, ""):
        raise ToolError("请提供 quantity_id。")
    unit_vm.delete_quantity(int(quantity_id))
    return {"ok": True, "data": {"quantity_id": int(quantity_id)}}


def register(registry: ToolRegistry) -> None:
    from app.core.pipe_category import PIPE_CATEGORIES

    element_id_schema = {"type": "integer", "description": "构件 id；省略时用当前选中构件"}
    cat_schema = {
        "type": "string",
        "enum": list(PIPE_CATEGORIES),
        "description": "管材类别（计算唯一依据：面宽表行 / 图集分流 / 断面图砼判断）；不传=按 mat 折算",
    }
    registry.register(
        Tool(
            "add_pipe",
            "为构件新增一根管材（t 留空=自动按图集）。"
            "直埋/顶管/牵引管只允许一条管材（已有则拒绝），构筑物不带管材。写操作。",
            {"type": "object", "properties": {
                "element_id": element_id_schema, "mat": {"type": "string"},
                "cat": cat_schema,
                "dn": {"type": "integer"}, "content": {"type": "string"},
                "t": {"type": "number", "description": "壁厚 mm；不传=自动按图集"}},
             "required": ["element_id"]},
            tool_add_pipe,
        )
    )
    registry.register(
        Tool(
            "update_pipe", "修改管材行（mat/cat/dn/content/t）。写操作。",
            {"type": "object", "properties": {
                "pipe_id": {"type": "integer"}, "mat": {"type": "string"},
                "cat": cat_schema,
                "dn": {"type": "integer"}, "content": {"type": "string"},
                "t": {"type": ["number", "null"]}},
             "required": ["pipe_id"]},
            tool_update_pipe,
        )
    )
    registry.register(
        Tool(
            "delete_pipe", "删除管材行（直埋/顶管/牵引管的管材行不可删）。写操作。",
            {"type": "object", "properties": {"pipe_id": {"type": "integer"}},
             "required": ["pipe_id"]},
            tool_delete_pipe,
        )
    )
    registry.register(
        Tool(
            "add_param", "新增构件参数行（图集参数行受类别限制）。写操作。",
            {"type": "object", "properties": {
                "element_id": element_id_schema, "key": {"type": "string"},
                "unit": {"type": "string"}, "value": {"type": "string"}},
             "required": ["element_id", "key"]},
            tool_add_param,
        )
    )
    registry.register(
        Tool(
            "update_param", "修改参数行（key/unit/value）。写操作。",
            {"type": "object", "properties": {
                "param_id": {"type": "integer"}, "key": {"type": "string"},
                "unit": {"type": "string"}, "value": {"type": "string"}},
             "required": ["param_id"]},
            tool_update_param,
        )
    )
    registry.register(
        Tool(
            "delete_param", "删除参数行（图集行/构筑物名称单位行锁定）。写操作。",
            {"type": "object", "properties": {"param_id": {"type": "integer"}},
             "required": ["param_id"]},
            tool_delete_param,
        )
    )
    registry.register(
        Tool(
            "add_quantity", "为构筑物新增工程量行（值可写算式）。写操作。",
            {"type": "object", "properties": {
                "element_id": element_id_schema, "category": {"type": "string"},
                "item": {"type": "string"}, "unit": {"type": "string"},
                "value": {"type": "string"}}},
            tool_add_quantity,
        )
    )
    registry.register(
        Tool(
            "update_quantity", "修改构筑物工程量行。写操作。",
            {"type": "object", "properties": {
                "quantity_id": {"type": "integer"}, "category": {"type": "string"},
                "item": {"type": "string"}, "unit": {"type": "string"},
                "value": {"type": "string"}},
             "required": ["quantity_id"]},
            tool_update_quantity,
        )
    )
    registry.register(
        Tool(
            "delete_quantity", "删除构筑物工程量行。写操作。",
            {"type": "object", "properties": {"quantity_id": {"type": "integer"}},
             "required": ["quantity_id"]},
            tool_delete_quantity,
        )
    )
    registry.register(
        Tool(
            "add_quantity", "为构筑物新增工程量行（值可写算式）。写操作。",
            {"type": "object", "properties": {
                "element_id": element_id_schema, "category": {"type": "string"},
                "item": {"type": "string"}, "unit": {"type": "string"},
                "value": {"type": "string"}}},
            tool_add_quantity,
        )
    )
    registry.register(
        Tool(
            "update_quantity", "修改构筑物工程量行。写操作。",
            {"type": "object", "properties": {
                "quantity_id": {"type": "integer"}, "category": {"type": "string"},
                "item": {"type": "string"}, "unit": {"type": "string"},
                "value": {"type": "string"}},
             "required": ["quantity_id"]},
            tool_update_quantity,
        )
    )
    registry.register(
        Tool(
            "delete_quantity", "删除构筑物工程量行。写操作。",
            {"type": "object", "properties": {"quantity_id": {"type": "integer"}},
             "required": ["quantity_id"]},
            tool_delete_quantity,
        )
    )
