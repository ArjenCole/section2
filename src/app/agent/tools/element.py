"""C 组核心：构件条目（T14~T18 + T74 的构件侧）。"""

from __future__ import annotations

from app.agent.context import resolve_element_id, resolve_unit_id
from app.agent.errors import ToolError
from app.agent.serializers import element_detail_dict, element_row_dict
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import parse_category, require_open, validate_principle_names
from app.core.models.models import CATEGORY_NAMES, category_name
from app.viewmodels import unit_vm


def _pipes(arguments: dict):
    pipes = arguments.get("pipes")
    if pipes is None and arguments.get("pipe"):
        pipes = [arguments["pipe"]]
    result = []
    for pipe in pipes or []:
        if not isinstance(pipe, dict):
            raise ToolError("pipes 每一项必须是对象 {mat, cat, dn, content, t}。")
        mat = str(pipe.get("mat") or "Ⅱ级混凝土管")
        cat = str(pipe.get("cat") or "")
        try:
            dn = int(pipe.get("dn") or 600)
        except (TypeError, ValueError) as error:
            raise ToolError("管径 dn 需为整数（mm）。") from error
        content = str(pipe.get("content") if pipe.get("content") is not None else "1")
        t_value = pipe.get("t")
        t = None
        if t_value not in (None, ""):
            try:
                t = float(t_value)
            except (TypeError, ValueError) as error:
                raise ToolError("管道壁厚 t 需为数字（mm），留空=自动按图集。") from error
        result.append((mat, cat, dn, content, t))
    return result or None


def _params(arguments: dict):
    result = []
    for param in arguments.get("params") or []:
        if not isinstance(param, dict):
            raise ToolError("params 每一项必须是对象 {key, unit, value}。")
        result.append(
            (
                str(param.get("key") or ""),
                str(param.get("unit") or ""),
                str(param.get("value") if param.get("value") is not None else ""),
            )
        )
    return result or None


def _quantities(arguments: dict):
    result = []
    for quantity in arguments.get("quantities") or []:
        if not isinstance(quantity, dict):
            raise ToolError("quantities 每一项必须是对象 {category, item, unit, value}。")
        result.append(
            (
                str(quantity.get("category") or "构筑物"),
                str(quantity.get("item") or ""),
                str(quantity.get("unit") or ""),
                str(quantity.get("value") if quantity.get("value") is not None else "0"),
            )
        )
    return result or None


def tool_list_elements(arguments: dict) -> dict:
    require_open()
    unit_id = resolve_unit_id(arguments)
    rows = [element_row_dict(row) for row in unit_vm.element_rows(unit_id)]
    return {"ok": True, "data": {"unit_id": unit_id, "elements": rows, "count": len(rows)}}


def tool_get_element_detail(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    return {"ok": True, "data": element_detail_dict(element_id)}


def tool_add_element(arguments: dict) -> dict:
    require_open()
    unit_id = resolve_unit_id(arguments)
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ToolError("构件名称不能为空。")
    category = parse_category(arguments.get("category"), default=1)
    pe_name = arguments.get("pe_name")
    pf_name = arguments.get("pf_name")
    pp_name = arguments.get("pp_name")
    pw_name = arguments.get("pw_name")
    validate_principle_names(pe_name, pf_name, pp_name, pw_name)
    element = unit_vm.create_element(
        unit_id,
        category=category,
        name=name,
        depth=str(arguments.get("depth") if arguments.get("depth") is not None else "0"),
        amount=str(arguments.get("amount") if arguments.get("amount") is not None else "0"),
        pe_name=pe_name,
        pf_name=pf_name,
        pp_name=pp_name,
        pw_name=pw_name,
        source=str(arguments.get("source") or ""),
        pipes=_pipes(arguments),
        params=_params(arguments),
        quantities=_quantities(arguments),
        # v8 起默认补图集快照（计算侧不再查图集），AI 不必显式传
        seed_atlas_defaults=bool(arguments.get("seed_atlas_defaults", True)),
    )
    if element is None:
        raise ToolError("新增失败：单位工程不存在。请先调 get_project_tree 查看 unit_id。")
    return {
        "ok": True,
        "data": {"element_id": element.id, "name": element.name,
                 "category": category_name(element.category)},
        "summary": f"已新增构件 id={element.id}：{element.name}（{category_name(element.category)}）",
    }


def tool_update_element(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    fields: dict = {}
    for key in ("name", "depth", "amount", "pe_name", "pf_name", "pp_name", "pw_name", "source"):
        if arguments.get(key) is not None:
            fields[key] = str(arguments[key])
    if arguments.get("category") is not None:
        fields["category"] = parse_category(arguments["category"])
    if not fields:
        raise ToolError("没有给出要修改的字段。可改：name/category/depth/amount/pe_name/pf_name/pp_name/pw_name/source。")
    validate_principle_names(
        fields.get("pe_name"), fields.get("pf_name"), fields.get("pp_name"), fields.get("pw_name")
    )
    updated = unit_vm.update_element(element_id, **fields)
    if updated is None:
        raise ToolError(f"找不到 id={element_id} 的构件。请先调 list_elements。")
    return {"ok": True, "data": {"element_id": element_id, "changed": fields}}


def tool_delete_element(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    element = unit_vm._element(element_id)
    if element is None:
        raise ToolError(f"找不到 id={element_id} 的构件。请先调 list_elements。")
    name = element.name
    unit_vm.delete_element(element_id)
    return {"ok": True, "data": {"element_id": element_id}, "summary": f"已删除构件 {name}"}


def tool_move_element(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    delta = int(arguments.get("delta") or 0)
    if delta not in (-1, 1):
        raise ToolError("delta 只能是 -1（上移）或 1（下移）。")
    unit_vm.move_element(element_id, delta)
    return {"ok": True, "data": {"element_id": element_id, "delta": delta}}


def tool_duplicate_element(arguments: dict) -> dict:
    require_open()
    element_id = resolve_element_id(arguments)
    data = unit_vm.element_snapshot(element_id)
    if data is None:
        raise ToolError(f"找不到 id={element_id} 的构件。")
    target_unit_id = arguments.get("target_unit_id") or unit_vm._element(element_id).unit_id
    element = unit_vm.insert_element_data(int(target_unit_id), data)
    if element is None:
        raise ToolError("复制失败：目标单位工程不存在。")
    return {"ok": True, "data": {"element_id": element.id, "source_element_id": element_id}}


def tool_insert_element_from_template(arguments: dict) -> dict:
    require_open()
    unit_id = resolve_unit_id(arguments)
    category = str(arguments.get("category") or "").strip()
    unit_name = str(arguments.get("unit") or "").strip()
    try:
        index = int(arguments.get("index"))
    except (TypeError, ValueError) as error:
        raise ToolError("index 需为整数（见 list_library_templates 返回）。") from error
    from app.services.element_library import element_library

    template = element_library().find(category, unit_name, index)
    if template is None:
        raise ToolError(
            f"找不到构件库模板（category={category}，unit={unit_name}，index={index}）。"
            "请先用 list_library_templates 检索。"
        )
    before = arguments.get("before_element_id")
    element = unit_vm.insert_element_template(
        unit_id, template, int(before) if before not in (None, "") else None
    )
    if element is None:
        raise ToolError("插入失败：单位工程不存在。")
    return {
        "ok": True,
        "data": {"element_id": element.id, "label": template.label,
                 "category": category_name(element.category)},
        "summary": f"已从构件库插入：{template.label}",
    }


def register(registry: ToolRegistry) -> None:
    element_id_schema = {"type": "integer", "description": "构件 id；省略时用当前选中构件"}
    registry.register(
        Tool(
            "list_elements",
            "列出单位工程的构件条目（类别/规格/埋深/数量/四类原则）。只读。unit_id 省略时用当前选中。",
            {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "integer", "description": "单位工程 id；省略时用当前选中"},
                    "verbose": {"type": "boolean", "default": False},
                },
            },
            tool_list_elements,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            "get_element_detail",
            "读取构件完整详情（管材/参数/工程量/图集自动值预览）。只读。",
            {"type": "object", "properties": {"element_id": element_id_schema}},
            tool_get_element_detail,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            "add_element",
            "新增构件条目（可带管材/参数/工程量）。写操作。",
            {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "integer", "description": "单位工程 id；省略时用当前选中"},
                    "name": {"type": "string"},
                    "category": {"type": "string",
                                 "enum": [name for name in CATEGORY_NAMES.values() if name]},
                    "depth": {"type": "string", "description": "埋深 m，可写算式"},
                    "amount": {"type": "string", "description": "数量/长度 m，可写算式"},
                    "pe_name": {"type": "string"}, "pf_name": {"type": "string"},
                    "pp_name": {"type": "string"}, "pw_name": {"type": "string"},
                    "source": {"type": "string"},
                    "pipe": {"type": "object", "description": "单根管材 {mat, dn, t, content}"},
                    "pipes": {"type": "array", "items": {"type": "object"},
                              "description": "多根管材 [{mat,cat,dn,content,t}]，cat 为管材类别（混凝土管-刚性接口/混凝土管-柔性接口/金属类管道/化学建材管道），不传=按 mat 折算"},
                    "params": {"type": "array", "items": {"type": "object"},
                               "description": "[{key,unit,value}]"},
                    "quantities": {"type": "array", "items": {"type": "object"},
                                   "description": "构筑物工程量行 [{category,item,unit,value}]"},
                    "seed_atlas_defaults": {"type": "boolean", "default": True},
                },
                "required": ["name"],
            },
            tool_add_element,
        )
    )
    registry.register(
        Tool(
            "update_element",
            "修改构件字段（名称/类别/埋深/数量/四类原则）。写操作。",
            {
                "type": "object",
                "properties": {
                    "element_id": element_id_schema,
                    "name": {"type": "string"},
                    "category": {"type": "string",
                                 "enum": [name for name in CATEGORY_NAMES.values() if name]},
                    "depth": {"type": "string"}, "amount": {"type": "string"},
                    "pe_name": {"type": "string"}, "pf_name": {"type": "string"},
                    "pp_name": {"type": "string"}, "pw_name": {"type": "string"},
                    "source": {"type": "string"},
                },
            },
            tool_update_element,
        )
    )
    registry.register(
        Tool(
            "delete_element",
            "删除构件条目及其管材/参数/工程量/引用。写操作。",
            {"type": "object", "properties": {"element_id": element_id_schema}},
            tool_delete_element,
        )
    )
    registry.register(
        Tool(
            "move_element",
            "上移/下移构件条目（delta=-1/+1）。写操作。",
            {
                "type": "object",
                "properties": {"element_id": element_id_schema,
                               "delta": {"type": "integer", "enum": [-1, 1]}},
                "required": ["delta"],
            },
            tool_move_element,
        )
    )
    registry.register(
        Tool(
            "duplicate_element",
            "复制构件（含管材/参数/工程量）到同单位工程末尾或指定单位工程。写操作。",
            {
                "type": "object",
                "properties": {"element_id": element_id_schema,
                               "target_unit_id": {"type": "integer"}},
            },
            tool_duplicate_element,
        )
    )
    registry.register(
        Tool(
            "insert_element_from_template",
            "从构件库插入模板（先用 list_library_templates 查 category/unit/index）。写操作。",
            {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "integer"},
                    "category": {"type": "string", "description": "构件库类别（如 直埋管道）"},
                    "unit": {"type": "string", "description": "构件库单元名"},
                    "index": {"type": "integer", "description": "模板在单元中的下标"},
                    "before_element_id": {"type": "integer", "description": "插入到该构件之前"},
                },
                "required": ["category", "unit", "index"],
            },
            tool_insert_element_from_template,
        )
    )
