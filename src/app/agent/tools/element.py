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


# --------------------------------------------------------------------------- #
# 合槽编组（v3）：与界面同走 unit_vm 模块级函数，一条代码路径
# --------------------------------------------------------------------------- #
def tool_list_groups(arguments: dict) -> dict:
    require_open()
    from app.core.models import base as orm
    from app.core.models.models import TrenchGroup
    from sqlalchemy import select

    groups = []
    for group in orm.session().scalars(select(TrenchGroup).order_by(TrenchGroup.id)):
        members = sorted(group.members, key=lambda item: (item.order_no, item.id))
        groups.append(
            {
                "group_id": group.id,
                "name": group.name,
                "amount": group.amount,
                "unit_id": group.unit_id,
                "members": [
                    {"element_id": member.id, "name": member.name}
                    for member in members
                ],
            }
        )
    return {"ok": True, "data": {"groups": groups}}


def tool_group_elements(arguments: dict) -> dict:
    require_open()
    element_ids = arguments.get("element_ids") or []
    if not isinstance(element_ids, list) or not element_ids:
        raise ToolError("请给出 element_ids（两条及以上构件 id，从左到右按表单顺序）。")
    group, error = unit_vm.create_trench_group([int(item) for item in element_ids])
    if error is not None or group is None:
        raise ToolError(f"编组失败：{error}")
    return {
        "ok": True,
        "data": {"group_id": group.id, "name": group.name},
        "summary": f"已创建合槽组 id={group.id}：{group.name}",
    }


def tool_dissolve_group(arguments: dict) -> dict:
    require_open()
    group_id = arguments.get("group_id")
    if group_id is None:
        raise ToolError("请给出 group_id（先调 list_trench_groups 查看）。")
    unit_vm.dissolve_trench_group(int(group_id))
    return {"ok": True, "data": {"group_id": int(group_id)}}


def tool_update_group(arguments: dict) -> dict:
    require_open()
    group_id = arguments.get("group_id")
    if group_id is None:
        raise ToolError("请给出 group_id。")
    fields: dict = {}
    for key in ("name", "amount", "backfill_mode", "split_mode"):
        if arguments.get(key) is not None:
            fields[key] = str(arguments[key])
    if not fields:
        raise ToolError(
            "没有给出要修改的字段。可改：name / amount / backfill_mode"
            "（独立回填标高 / 统一回填标高）/ split_mode（起坡点分割 / 管中心分隔）；"
            "父节点不选围护 / 面宽原则。"
        )
    group = unit_vm.update_group(int(group_id), **fields)
    if group is None:
        raise ToolError(f"找不到 id={group_id} 的合槽组。")
    return {"ok": True, "data": {"group_id": group.id, "changed": fields}}


def tool_group_membership(arguments: dict) -> dict:
    """加入 / 移出合槽组（action: add / remove）。"""
    require_open()
    element_id = arguments.get("element_id")
    if element_id is None:
        raise ToolError("请给出 element_id。")
    action = str(arguments.get("action") or "add")
    if action == "add":
        group_id = arguments.get("group_id")
        if group_id is None:
            raise ToolError("加入合槽请给出 group_id（先调 list_trench_groups 查看）。")
        ok, error = unit_vm.add_to_group(int(element_id), int(group_id))
        if not ok:
            raise ToolError(f"加入失败：{error}")
        return {"ok": True, "data": {"element_id": int(element_id), "group_id": int(group_id)}}
    if action == "remove":
        unit_vm.remove_from_group(int(element_id))
        return {"ok": True, "data": {"element_id": int(element_id)}}
    raise ToolError("action 只能是 add / remove。")


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
    for key in (
        "name", "depth", "amount", "pe_name", "pf_name", "pp_name", "pw_name", "source",
        "pe_left_name", "pe_right_name",
    ):
        if arguments.get(key) is not None:
            fields[key] = str(arguments[key])
    for key in ("support_left", "support_right"):
        if arguments.get(key) is not None:
            fields[key] = bool(arguments[key])
    if arguments.get("category") is not None:
        fields["category"] = parse_category(arguments["category"])
    if not fields:
        raise ToolError(
            "没有给出要修改的字段。可改：name/category/depth/amount/pe_name/pf_name/pp_name/pw_name/source"
            "/pe_left_name/pe_right_name/support_left/support_right。"
        )
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
            "修改构件字段（名称/类别/埋深/数量/四类原则/左右分设与支撑勾选）。写操作。",
            {
                "type": "object",
                "properties": {
                    "element_id": element_id_schema,
                    "name": {"type": "string"},
                    "category": {"type": "string",
                                 "enum": [name for name in CATEGORY_NAMES.values() if name]},
                    "depth": {"type": "string"}, "amount": {"type": "string"},
                    "pe_name": {"type": "string",
                                "description": "围护原则名；填「左右分设」进入左右分设模式"},
                    "pf_name": {"type": "string"},
                    "pp_name": {"type": "string"}, "pw_name": {"type": "string"},
                    "source": {"type": "string"},
                    "pe_left_name": {"type": "string", "description": "左侧围护原则（左右分设模式）"},
                    "pe_right_name": {"type": "string", "description": "右侧围护原则（左右分设模式）"},
                    "support_left": {"type": "boolean", "description": "左侧支撑（类别为“支撑”的公式）是否计算"},
                    "support_right": {"type": "boolean", "description": "右侧支撑是否计算"},
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
    registry.register(
        Tool(
            "list_trench_groups",
            "列出全部合槽编组（父节点）及其成员顺序（从左到右）。只读。",
            {"type": "object", "properties": {}},
            tool_list_groups,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            "group_elements",
            "把多条构件编成合槽组（父节点不选围护 / 面宽原则；成员转为左右分设，"
            "表单顺序 = 沟槽从左到右）。写操作。",
            {
                "type": "object",
                "properties": {
                    "element_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "两条及以上构件 id，按从左到右顺序给出",
                    }
                },
                "required": ["element_ids"],
            },
            tool_group_elements,
        )
    )
    registry.register(
        Tool(
            "update_group",
            "修改合槽父节点属性（name / amount / backfill_mode / split_mode；"
            "amount = L_组，会强制同步全部子构件；backfill_mode = 回填分层方式"
            "（独立回填标高 / 统一回填标高），split_mode = 断面划分方式"
            "（起坡点分割 / 管中心分隔）；父节点不持有围护 / 面宽原则，埋深无效）。写操作。",
            {
                "type": "object",
                "properties": {
                    "group_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "amount": {"type": "string", "description": "合槽计算长度 L_组（可写算式）"},
                    "backfill_mode": {
                        "type": "string",
                        "enum": ["独立回填标高", "统一回填标高"],
                        "description": "回填分层方式：统一 = 每层取组内最浅层顶标高",
                    },
                    "split_mode": {
                        "type": "string",
                        "enum": ["起坡点分割", "管中心分隔"],
                        "description": "断面划分方式：管中心 = 相邻构件中心连线中点作虚拟分界",
                    },
                },
                "required": ["group_id"],
            },
            tool_update_group,
        )
    )
    registry.register(
        Tool(
            "dissolve_group",
            "解散合槽组（父节点删除、成员还原为独立构件）。写操作。",
            {"type": "object", "properties": {"group_id": {"type": "integer"}}},
            tool_dissolve_group,
        )
    )
    registry.register(
        Tool(
            "group_membership",
            "合槽组成员调整：action=add 加入组（追加为最右成员）/ action=remove 移出。写操作。",
            {
                "type": "object",
                "properties": {
                    "element_id": element_id_schema,
                    "action": {"type": "string", "enum": ["add", "remove"]},
                    "group_id": {"type": "integer"},
                },
                "required": ["element_id", "action"],
            },
            tool_group_membership,
        )
    )
