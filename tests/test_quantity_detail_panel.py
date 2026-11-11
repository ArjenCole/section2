"""工程量明细表页测试：表头右侧的复制 / 导出 / 展开收起按钮。

覆盖：动作按钮随分段切换显隐、复制到剪贴板的分隔规则、清单表收起后只剩
清单项目行（合价仍按被收起的分项合计）、导出「当前表格」在展开 / 收起两种
状态下的列结构与表达式取值，以及收起状态不影响工具栏「导出 Excel」。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import openpyxl

from app.core.models.models import CATEGORY_STRUCTURE
from app.services import project_io, summary
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm

_PAGE_HEADERS = ["编号", "类别", "名称", "单位", "数量", "单价", "合价"]


def _unit_with_two_elements(tmp_path: Path):
    """一个单位工程、两条附属构筑物构件（各带一条定额拆分行）。"""
    project_io.new_project(
        NewProjectSpec(path=tmp_path / "明细表.stn", unit_names=["雨水工程"])
    )
    segment = project_io.segments()[0]
    unit = project_io.units(segment.id)[0]
    for name, amount in (("雨水检查井", "2"), ("污水检查井", "3")):
        assert unit_vm.create_element(
            unit.id,
            category=CATEGORY_STRUCTURE,
            name=name,
            depth="3.2",
            amount=amount,
            params=[("名称", "", name), ("单位", "", "座")],
            quantities=[("构筑物", "垫层", "m3", "1.0")],
        ) is not None
    return unit


def _make_panel(unit, qapp):
    from app.views.panels.quantity_detail_panel import QuantityDetailPanel

    panel = QuantityDetailPanel()
    panel.show()
    panel.set_node(SimpleNamespace(id=unit.id, name=unit.name, kind="unit"))
    return panel


def _totals(table) -> list[str]:
    return [table.item(row, 6).text() for row in range(table.rowCount())]


# --------------------------------------------------------------------------- #
# 按钮显隐
# --------------------------------------------------------------------------- #
def test_toggle_button_only_on_listing_tab(qapp, tmp_path) -> None:
    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    assert panel._btn_copy.isEnabled() and panel._btn_export.isEnabled()
    # 定额工程量没有分组层级：不显示展开 / 收起按钮
    assert not panel._btn_toggle.isVisible()
    panel._segment_group.button(1).click()
    assert panel._btn_toggle.isVisible()
    assert panel._btn_toggle.text() == "收起表格"  # 默认展开态
    panel._segment_group.button(0).click()
    assert not panel._btn_toggle.isVisible()


# --------------------------------------------------------------------------- #
# 复制当前表格
# --------------------------------------------------------------------------- #
def test_copy_current_table_to_clipboard(qapp, tmp_path) -> None:
    from PySide6.QtGui import QGuiApplication

    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    panel._copy_current_table()
    lines = QGuiApplication.clipboard().text().splitlines()
    assert lines[0].split("\t") == _PAGE_HEADERS
    assert len(lines) == panel._quota_table.rowCount() + 1  # 表头 + 定额行
    # 切到清单表后复制的是清单表内容（清单项目行 + 其下工程量行）
    panel._segment_group.button(1).click()
    panel._copy_current_table()
    lines = QGuiApplication.clipboard().text().splitlines()
    assert len(lines) == panel._listing_table.rowCount() + 1
    assert lines[1].split("\t")[0] == "清单项目"


# --------------------------------------------------------------------------- #
# 展开 / 收起
# --------------------------------------------------------------------------- #
def test_collapse_keeps_listing_rows_and_totals(qapp, tmp_path) -> None:
    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    panel._segment_group.button(1).click()
    expanded_rows = panel._listing_table.rowCount()
    assert expanded_rows == 4  # 2 个清单项目行 + 2 条工程量行
    expanded_totals = _totals(panel._listing_table)

    panel._btn_toggle.click()
    assert panel._btn_toggle.text() == "展开表格"
    assert panel._listing_table.rowCount() == 2  # 只剩清单项目行
    # 合价仍按被收起的分项合计（收起只改显示，不改数值）
    assert _totals(panel._listing_table) == [expanded_totals[0], expanded_totals[2]]

    panel._btn_toggle.click()
    assert panel._btn_toggle.text() == "收起表格"
    assert panel._listing_table.rowCount() == expanded_rows


# --------------------------------------------------------------------------- #
# 导出当前表格
# --------------------------------------------------------------------------- #
def test_export_rows_expanded_has_expression_columns(qapp, tmp_path) -> None:
    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    rows = panel._export_rows(True, False)
    assert len(rows) == 4
    assert all(len(values) == 9 for values, _flag in rows)
    listing_values = rows[0][0]
    assert listing_values[0] == "清单项目"
    assert listing_values[7] == "2" and listing_values[8] == "2"  # 数量原文
    quota_values = rows[1][0]
    assert quota_values[0] == ""
    assert quota_values[4] == 2.0  # 垫层 1.0 × 数量 2，写 float
    assert quota_values[7] and quota_values[8]  # 表达式 / 算式都有内容


def test_export_rows_collapsed_is_listing_only(qapp, tmp_path) -> None:
    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    panel._segment_group.button(1).click()
    panel._btn_toggle.click()
    rows = panel._export_rows(True, True)
    assert len(rows) == 2
    # 收起态没有工程量行，也就不带表达式 / 算式两列
    assert all(len(values) == 7 for values, _flag in rows)
    assert all(flag for _values, flag in rows)


def test_export_detail_table_file(qapp, tmp_path) -> None:
    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    path = tmp_path / "当前表格.xlsx"
    result = summary.export_detail_table(
        path, panel._export_rows(False, False), with_expression=True, sheet_title="定额工程量"
    )
    assert result["rows"] == panel._quota_table.rowCount()

    workbook = openpyxl.load_workbook(path)
    assert workbook.sheetnames == ["定额工程量"]  # 只有一张 sheet
    sheet = workbook["定额工程量"]
    assert [cell.value for cell in sheet[1]] == [
        *_PAGE_HEADERS,
        "表达式",
        "算式",
    ]
    for row in sheet.iter_rows(min_row=2):
        # 数量 / 单价 / 合价写数字（Excel 里可直接再计算），不是格式化后的文本
        assert isinstance(row[4].value, (int, float))
        assert isinstance(row[5].value, (int, float))
        assert isinstance(row[6].value, (int, float))
        assert row[7].value


def test_collapsed_export_file_has_no_expression_columns(qapp, tmp_path) -> None:
    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    panel._segment_group.button(1).click()
    panel._btn_toggle.click()
    path = tmp_path / "清单收起.xlsx"
    summary.export_detail_table(
        path, panel._export_rows(True, True), with_expression=False, sheet_title="清单工程量"
    )
    sheet = openpyxl.load_workbook(path)["清单工程量"]
    assert [cell.value for cell in sheet[1]] == _PAGE_HEADERS
    assert sheet.max_row == 3  # 表头 + 2 个清单项目行
    assert sheet.cell(row=2, column=1).value == "清单项目"


def test_export_current_table_writes_file(qapp, tmp_path, monkeypatch) -> None:
    """点「导出当前表格」：单 sheet 写到所选路径，展开态带表达式 / 算式两列。"""
    from PySide6.QtWidgets import QFileDialog

    from app.views.widgets.frameless_dialog import FramelessMessageBox

    panel = _make_panel(_unit_with_two_elements(tmp_path), qapp)
    target = tmp_path / "当前表格导出.xlsx"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(target), "")),
    )
    monkeypatch.setattr(
        FramelessMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: FramelessMessageBox.No),
    )
    panel._segment_group.button(1).click()
    panel._export_current_table()
    assert target.exists()

    sheet = openpyxl.load_workbook(target)["清单工程量"]
    assert [cell.value for cell in sheet[1]][-2:] == ["表达式", "算式"]
    assert sheet.max_row == 1 + panel._listing_table.rowCount()


def test_collapse_does_not_affect_toolbar_export(qapp, tmp_path) -> None:
    """收起只是页面显示状态：工具栏「导出 Excel」照旧带表达式 / 算式列。"""
    unit = _unit_with_two_elements(tmp_path)
    panel = _make_panel(unit, qapp)
    panel._segment_group.button(1).click()
    panel._btn_toggle.click()

    summary.export_quantity_tables(tmp_path / "toolbar.xlsx", [unit.id])
    sheet = openpyxl.load_workbook(tmp_path / "toolbar.xlsx")["清单工程量"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[-2:] == ["表达式", "算式"]
    assert sheet.max_row == 1 + 4  # 表头 + 清单项目行 + 工程量行，未受收起影响
