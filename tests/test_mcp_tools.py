"""MCP 工具端到端测试（无界面，直接走统一 ToolRegistry）。

覆盖：工程生命周期、项目树、构件与子行、六类原则、图集/构件库、
计算（含 steps 不变式）、旧档迁移、汇总导出、上下文解析。
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.agent import context as agent_context
from app.agent.tool_registry import default_registry

REG = default_registry()
FIXTURES = Path(__file__).parent / "fixtures" / "legacy"


def _unit_id() -> int:
    result = REG.execute("get_project_tree", {})
    assert result["ok"], result
    return result["data"]["segments"][0]["units"][0]["id"]


def _add_pipe_element(unit_id: int, name: str = "雨水管") -> int:
    result = REG.execute(
        "add_element",
        {
            "unit_id": unit_id,
            "name": name,
            "category": "直埋管道",
            "depth": "2.5",
            "amount": "100",
            "pipe": {"mat": "Ⅱ级混凝土管", "dn": 600},
        },
    )
    assert result["ok"], result
    return result["data"]["element_id"]


# --------------------------------------------------------------------------- #
# 工程 / 树 / 构件
# --------------------------------------------------------------------------- #
def test_project_lifecycle(tmp_path: Path) -> None:
    target = tmp_path / "生命周期.stn2"
    result = REG.execute(
        "create_project",
        {"project_name": "生命周期", "path": str(target), "unit_names": ["雨水工程"]},
    )
    assert result["ok"], result
    assert target.exists()
    assert REG.execute("get_project_info", {})["data"]["project_name"] == "生命周期"
    assert REG.execute("save_project", {})["ok"]
    assert REG.execute("close_project", {})["ok"]
    assert REG.execute("open_project", {"path": str(target)})["ok"]
    another = tmp_path / "生命周期-副本.stn2"
    assert REG.execute("save_project_as", {"path": str(another)})["ok"]
    assert another.exists()


def test_tree_tools(project) -> None:
    result = REG.execute("add_segment", {"name": "第二标段"})
    assert result["ok"], result
    segment_id = result["data"]["segment_id"]
    result = REG.execute("add_unit", {"segment_id": segment_id, "name": "污水工程"})
    assert result["ok"], result
    unit_id = result["data"]["unit_id"]
    REG.execute("rename_node", {"kind": "unit", "id": unit_id, "name": "污水工程2"})
    REG.execute("move_node", {"kind": "unit", "id": unit_id, "target_segment_id": segment_id, "index": 0})
    tree = REG.execute("get_project_tree", {})["data"]
    assert len(tree["segments"]) == 2
    assert tree["segments"][1]["units"][0]["name"] == "污水工程2"
    deleted = REG.execute("delete_node", {"kind": "unit", "id": unit_id})
    assert deleted["ok"] and "污水工程2" in deleted["data"]["deleted"]


def test_element_lifecycle_and_parts(project) -> None:
    unit_id = _unit_id()
    element_id = _add_pipe_element(unit_id)
    listed = REG.execute("list_elements", {"unit_id": unit_id})["data"]
    assert listed["count"] == 1

    detail = REG.execute("get_element_detail", {"element_id": element_id})["data"]
    assert detail["pipes"][0]["dn"] == 600
    assert detail["principle_refs"]["pe"]
    pipe_id = detail["pipes"][0]["id"]

    # 直埋管道只允许一条管材：再加 / 删除都被拒（构筑物同理不带管材）
    refused = REG.execute("add_pipe", {"element_id": element_id, "mat": "钢管", "dn": 200})
    assert not refused.get("ok") and "只允许一条管材" in refused.get("error", "")
    refused_delete = REG.execute("delete_pipe", {"pipe_id": pipe_id})
    assert not refused_delete.get("ok") and "不能删除" in refused_delete.get("error", "")
    # 包封 / 箱涵 / 管廊仍可增删管材行
    box_id = REG.execute(
        "add_element",
        {"unit_id": unit_id, "name": "箱涵", "category": "箱涵", "depth": "3", "amount": "40"},
    )["data"]["element_id"]
    added = REG.execute("add_pipe", {"element_id": box_id, "mat": "钢管", "dn": 200})
    assert added["ok"], added
    assert REG.execute("delete_pipe", {"pipe_id": added["data"]["pipe_id"]})["ok"]
    assert REG.execute("update_pipe", {"pipe_id": pipe_id, "content": "2"})["ok"]
    assert REG.execute("add_param", {"element_id": element_id, "key": "含钢量", "unit": "kg/m3", "value": "150"})["ok"]

    detail = REG.execute("get_element_detail", {"element_id": element_id})["data"]
    custom = next(item for item in detail["params"] if item["key"] == "含钢量")
    assert REG.execute("update_param", {"param_id": custom["id"], "value": "160"})["ok"]
    assert REG.execute("delete_param", {"param_id": custom["id"]})["ok"]

    assert REG.execute("update_element", {"element_id": element_id, "depth": "3+0.5"})["ok"]
    assert REG.execute("get_element_detail", {"element_id": element_id})["data"]["depth"] == "3+0.5"

    duplicate = REG.execute("duplicate_element", {"element_id": element_id})
    assert duplicate["ok"], duplicate
    assert REG.execute("list_elements", {"unit_id": unit_id})["data"]["count"] == 3
    assert REG.execute("delete_element", {"element_id": duplicate["data"]["element_id"]})["ok"]
    assert REG.execute("delete_element", {"element_id": box_id})["ok"]
    assert REG.execute("list_elements", {"unit_id": unit_id})["data"]["count"] == 1
    assert REG.execute("move_element", {"element_id": element_id, "delta": 1})["ok"]


def test_principle_refs(project) -> None:
    unit_id = _unit_id()
    element_id = _add_pipe_element(unit_id)
    pe_names = REG.execute("list_principles", {"kind": "enclosure"})["data"]["principles"]
    first = pe_names[0]["name"]
    second = REG.execute("create_enclosure", {"name": "第二围护"})["data"]["name"]
    added = REG.execute(
        "add_principle_ref", {"element_id": element_id, "kind": "pe", "name": second, "ratio": 0.4}
    )
    assert added["ok"], added
    refs = REG.execute("list_principle_refs", {"element_id": element_id})["data"]["pe"]
    assert len(refs) == 2
    assert REG.execute("update_principle_ref", {"ref_id": refs[1]["ref_id"], "ratio": 0.6})["ok"]
    assert REG.execute("set_main_pe", {"element_id": element_id, "name": first})["ok"]
    assert REG.execute("remove_principle_ref", {"ref_id": refs[1]["ref_id"]})["ok"]


def test_current_context_resolution(project) -> None:
    unit_id = _unit_id()
    element_id = _add_pipe_element(unit_id)
    try:
        agent_context.update_context(
            unit_id=unit_id, unit_name="雨水工程", element_id=element_id, element_name="雨水管"
        )
        assert REG.execute("list_elements", {})["ok"]
        assert REG.execute("compute_element", {})["ok"]
        snapshot = REG.execute("get_current_context", {})["data"]
        assert snapshot["unit_id"] == unit_id
        assert snapshot["element_id"] == element_id
    finally:
        agent_context.reset_context()


# --------------------------------------------------------------------------- #
# 原则
# --------------------------------------------------------------------------- #
def test_enclosure_principles(project) -> None:
    detail = REG.execute(
        "get_principle_detail", {"kind": "enclosure", "name": "默认围护原则"}
    )["data"]
    level_type = detail["works"][0]["levels"][0]["level_type"]
    stop_type = detail["works"][0]["stop_type"]
    work_id = detail["works"][0]["work_id"]

    assert REG.execute(
        "set_enclosure_fields",
        {"name": "默认围护原则", "excvt": "Ⅳ类土", "cushions": [{"name": "碎石", "h": 150}]},
    )["ok"]
    works = [
        {
            "min_depth": 0,
            "cpnt_cat": level_type,
            "stop_type": stop_type,
            "levels": [{"h": -1, "step_width": 1.0, "level_type": level_type}],
        }
    ]
    result = REG.execute("set_enclosure_works", {"name": "默认围护原则", "works": works})
    assert result["ok"], result
    assert REG.execute("set_work_levels", {"work_id": work_id, "levels": [
        {"h": 2, "step_width": 0.8, "level_type": level_type},
        {"h": -1, "step_width": 1.0, "level_type": level_type},
    ]})["ok"]

    created = REG.execute(
        "create_enclosure",
        {
            "name": "多级围护测试",
            "works": [
                {
                    "min_depth": 0,
                    "cpnt_cat": "多级围护",
                    "stop_type": stop_type,
                    "levels": [
                        {"h": 2, "step_width": 0.8, "level_type": level_type},
                        {"h": -1, "step_width": 1.0, "level_type": level_type},
                    ],
                }
            ],
        },
    )
    assert created["ok"], created
    component_id = created["data"]["works"][0]["levels"][0]["component_id"]
    component = REG.execute("get_component_detail", {"component_id": component_id})["data"]
    if component["params"]:
        key = component["params"][0]["key"]
        assert REG.execute(
            "update_component_params",
            {"component_id": component_id, "params": {key: {"display": "测试", "expression": "1"}}},
        )["ok"]

    assert REG.execute(
        "rename_principle", {"kind": "enclosure", "name": "多级围护测试", "new_name": "多级围护测试2"}
    )["ok"]
    assert REG.execute(
        "delete_principle", {"kind": "enclosure", "name": "多级围护测试2"}
    )["ok"]


def test_foundation_precipitation_width(project) -> None:
    result = REG.execute(
        "create_foundation",
        {"name": "测试地基", "layers": [{"name": "碎石", "h": 200}, {"name": "中粗砂", "h": 100}]},
    )
    assert result["ok"], result
    assert len(result["data"]["replacements"]) == 2
    assert REG.execute("set_replacement_layers", {"name": "测试地基", "layers": [{"name": "碎石", "h": 300}]})["ok"]
    fi_names = REG.execute("list_component_templates", {"group": "Fi"})["data"]["templates"]
    if fi_names:
        assert REG.execute(
            "set_foundation_component", {"name": "测试地基", "template_name": fi_names[0]["name"]}
        )["ok"]

    result = REG.execute(
        "create_precipitation",
        {"name": "测试降水", "wells": {"轻型井点": {"enabled": True, "elevation": 4, "gap": 1.2, "sides": 2}}},
    )
    assert result["ok"], result
    detail = REG.execute("get_principle_detail", {"kind": "precipitation", "name": "测试降水"})["data"]
    assert detail["wells"]["轻型井点"]["elevation"] == 4
    assert REG.execute(
        "set_precipitation_wells",
        {"name": "测试降水", "wells": {"深井": {"enabled": True, "elevation": 12, "gap": 20, "sides": 1}}},
    )["ok"]

    result = REG.execute(
        "create_width_principle",
        {
            "name": "测试面宽",
            "mode": "B",
            "items": [{"pipe_type": "混凝土管-刚性接口", "dn": 600, "width": 1200}],
        },
    )
    assert result["ok"], result
    detail = REG.execute("get_principle_detail", {"kind": "width", "name": "测试面宽"})["data"]
    assert detail["mode"] == "B"
    assert detail["groove_b"]["混凝土管-刚性接口"]["600"] == 1200
    assert REG.execute("reset_width_to_atlas", {"name": "测试面宽"})["ok"]
    detail = REG.execute("get_principle_detail", {"kind": "width", "name": "测试面宽"})["data"]
    assert detail["work"]


def test_spcp_roundtrip(project, tmp_path: Path) -> None:
    path = tmp_path / "围护.spcp"
    result = REG.execute(
        "export_principle", {"kind": "enclosure", "name": "默认围护原则", "path": str(path)}
    )
    assert result["ok"], result
    assert path.exists()
    imported = REG.execute("import_principle", {"path": str(path)})
    assert imported["ok"], imported
    assert imported["data"]["kind"] == "enclosure"


# --------------------------------------------------------------------------- #
# 图集 / 构件库 / 计算
# --------------------------------------------------------------------------- #
def test_reference_tools(project) -> None:
    assert REG.execute("list_atlas_tables", {})["data"]["tables"]
    atlas = REG.execute(
        "resolve_atlas",
        {
            "category": "直埋管道",
            "pipes": [{"mat": "Ⅱ级混凝土管", "dn": 600}],
            "found_angle": 120,
        },
    )
    assert atlas["ok"], atlas
    assert atlas["data"]["t"] > 0
    assert REG.execute("query_atlas_table", {"table_index": 0, "dn": "600", "angle": "120", "level": "2"})["ok"]
    assert REG.execute("get_default_width_tables", {})["data"]["work"]

    templates = REG.execute("list_library_templates", {"limit": 5})["data"]
    assert templates["items"]
    first = templates["items"][0]
    template = REG.execute(
        "get_library_template",
        {"category": first["category"], "unit": first["unit"], "index": first["index"]},
    )
    assert template["ok"], template
    unit_id = _unit_id()
    inserted = REG.execute(
        "insert_element_from_template",
        {"unit_id": unit_id, "category": first["category"], "unit": first["unit"], "index": first["index"]},
    )
    assert inserted["ok"], inserted

    for group in ("Ei", "WSi", "Fi"):
        result = REG.execute("list_component_templates", {"group": group})
        assert result["ok"] and result["data"]["templates"], group
        name = result["data"]["templates"][0]["name"]
        assert REG.execute("get_component_template", {"group": group, "name": name})["ok"]


def test_compute_tools_and_steps_invariant(project) -> None:
    unit_id = _unit_id()
    element_id = _add_pipe_element(unit_id)
    unit_result = REG.execute(
        "compute_unit", {"unit_id": unit_id, "include_steps": True}
    )
    assert unit_result["ok"], unit_result
    assert unit_result["data"]["totals"]
    element_result = REG.execute("compute_element", {"element_id": element_id})
    assert element_result["ok"], element_result
    for quantity in element_result["data"]["quantities"]:
        if quantity.get("steps"):
            joined = "".join(step["expr"] for step in quantity["steps"])
            assert joined == quantity["expression"], quantity["key"]
    assert REG.execute("evaluate_expression", {"expression": "2×(3+4)"})["data"]["value"] == 14
    assert "error" in REG.execute("evaluate_expression", {"expression": "__import__('os')"})


# --------------------------------------------------------------------------- #
# 迁移 / 汇总 / 导出
# --------------------------------------------------------------------------- #
def test_legacy_inspect_and_migrate(tmp_path: Path) -> None:
    source = FIXTURES / "样例-基础版.stn"
    inspected = REG.execute("inspect_legacy_project", {"path": str(source)})
    assert inspected["ok"], inspected
    assert inspected["data"]["elements"] > 0
    target = tmp_path / "迁移结果.stn2"
    migrated = REG.execute(
        "migrate_legacy_project", {"source_path": str(source), "target_path": str(target)}
    )
    assert migrated["ok"], migrated
    assert target.exists()
    assert migrated["data"]["elements"] > 0


def test_summary_prices_and_excel(project, tmp_path: Path) -> None:
    unit_id = _unit_id()
    _add_pipe_element(unit_id)
    rows = REG.execute("get_unit_summary", {"unit_id": unit_id})["data"]["rows"]
    assert rows
    key = rows[0]["key"]
    assert REG.execute("set_price", {"key": key, "value": 12.5})["ok"]
    rows = REG.execute("get_unit_summary", {"unit_id": unit_id})["data"]["rows"]
    priced = next(row for row in rows if row["key"] == key)
    assert priced["price"] == 12.5
    assert priced["total"] == priced["amount"] * 12.5

    csv_path = tmp_path / "prices.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "value"])
        writer.writerow([key, "20"])
    imported = REG.execute("batch_import_prices", {"path": str(csv_path)})
    assert imported["ok"], imported
    assert imported["data"]["imported"] == 1
    rows = REG.execute("get_unit_summary", {"unit_id": unit_id})["data"]["rows"]
    assert next(row for row in rows if row["key"] == key)["price"] == 20

    excel = tmp_path / "导出.xlsx"
    exported = REG.execute("export_excel", {"path": str(excel), "kind": "定额", "unit_id": unit_id})
    assert exported["ok"], exported
    assert excel.exists()
    assert exported["data"]["rows"] > 0
