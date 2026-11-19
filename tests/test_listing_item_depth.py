"""清单项目行名称：规格 / 名称后追加埋深。

详情面板「清单工程量」的项目列与工程量明细表「清单工程量」的名称列同口径：
沿用旧版写法“规格 埋深 3.2m”，埋深按求值结果格式化；导出保持原名称不变。
"""

from __future__ import annotations

from types import SimpleNamespace

from app.core.models.models import CATEGORY_STRUCTURE
from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm


def _unit_with_depth(tmp_path, depth: str = "3.2"):
    """一个单位工程、一条带埋深的附属构筑物（名称 / 规格同为“雨水检查井”）。"""
    project_io.new_project(
        NewProjectSpec(path=tmp_path / "埋深名称.stn", unit_names=["雨水工程"])
    )
    unit = project_io.units(project_io.segments()[0].id)[0]
    assert unit_vm.create_element(
        unit.id,
        category=CATEGORY_STRUCTURE,
        name="雨水检查井",
        depth=depth,
        amount="2",
        params=[("名称", "", "雨水检查井"), ("单位", "", "座")],
        quantities=[("构筑物", "垫层", "m3", "1.0")],
    ) is not None
    return unit


def _listing_project_names(table) -> list[str]:
    """表格里清单项目行（首列“清单项目”）的名称列文本。"""
    return [
        table.item(row, 2).text()
        for row in range(table.rowCount())
        if table.item(row, 0).text() == "清单项目"
    ]


def test_quantity_detail_listing_name_includes_depth(qapp, tmp_path) -> None:
    from app.views.panels.quantity_detail_panel import QuantityDetailPanel

    unit = _unit_with_depth(tmp_path)
    panel = QuantityDetailPanel()
    panel.show()
    panel.set_node(SimpleNamespace(id=unit.id, name=unit.name, kind="unit"))
    panel._segment_group.button(1).click()

    assert _listing_project_names(panel._listing_table) == ["雨水检查井 埋深 3.2m"]
    # 「导出当前表格」与页面同口径（工具栏「导出 Excel」仍保持原名称）
    assert panel._export_rows(True, True)[0][0][2] == "雨水检查井 埋深 3.2m"


def test_quantity_detail_listing_depth_expression_shows_result(qapp, tmp_path) -> None:
    from app.views.panels.quantity_detail_panel import QuantityDetailPanel

    unit = _unit_with_depth(tmp_path, depth="3+0.2")
    panel = QuantityDetailPanel()
    panel.show()
    panel.set_node(SimpleNamespace(id=unit.id, name=unit.name, kind="unit"))
    panel._segment_group.button(1).click()

    assert _listing_project_names(panel._listing_table) == ["雨水检查井 埋深 3.2m"]


def test_unit_panel_listing_project_column_includes_depth(qapp, tmp_path) -> None:
    from app.views.panels.unit_panel import UnitPanel, _select_row

    unit = _unit_with_depth(tmp_path)
    panel = UnitPanel()
    panel._show_unit(unit.id, unit.name)
    qapp.processEvents()

    table = panel._element_table
    assert table.rowCount() == 1
    _select_row(table, 0, 0)
    panel._sync_detail_to_selection()

    assert _listing_project_names(panel._quantity_tables["清单工程量"]) == [
        "雨水检查井 埋深 3.2m"
    ]


def test_toolbar_export_keeps_original_listing_name(tmp_path) -> None:
    """工具栏「导出 Excel」清单表不追加埋深（导出格式不变）。"""
    import openpyxl

    from app.services import summary

    unit = _unit_with_depth(tmp_path)
    summary.export_quantity_tables(tmp_path / "toolbar.xlsx", [unit.id])
    sheet = openpyxl.load_workbook(tmp_path / "toolbar.xlsx")["新建标段-雨水工程-清单表"]
    assert sheet.cell(row=2, column=2).value == "雨水检查井"


def test_listing_item_name_skips_empty_or_invalid_depth() -> None:
    """埋深为空 / 算式不合法时只显示名称；with_depth=False 永远不追加。"""
    from app.services.summary import listing_item_name

    row = SimpleNamespace(
        spec="DN600", name="管A", depth="", depth_value=0.0, depth_error=""
    )
    assert listing_item_name(row, with_depth=True) == "DN600"
    assert listing_item_name(row) == "DN600"

    row.depth = "2+"
    row.depth_error = "算式不合法"
    assert listing_item_name(row, with_depth=True) == "DN600"
