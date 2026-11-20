"""工程量明细表单价列的「回车提交并选中下一行单价格」测试。

定额工程量表：单价格里按回车 = 提交写库 + 当前格落到下一行的单价列（连续
录价不用碰鼠标）；末行只提交、焦点留在原格。清单工程量表：清单项目行的单价
是派生值、不可编辑，回车跳行跳过它们，落到下一条能录价的工程量行。单价列
以外的列都不可编辑，不会出现「跳过去也录不了」的落点。Qt 部分离屏运行。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from app.core.models.models import CATEGORY_STRUCTURE
from app.services import project_io, summary
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm
from app.views.panels.quantity_detail_panel import _COL_NAME, _COL_PRICE
from app.views.widgets.table_edit_delegate import (
    ENTER_NEXT_COLUMNS_ATTR,
    ENTER_NEXT_SKIP_READONLY_ATTR,
)


@pytest.fixture()
def three_row_unit(tmp_path):
    """三个构件、每条一条定额拆分行：定额表 3 行，清单表 6 行（项目行 + 工程量行）。"""
    project_io.new_project(
        NewProjectSpec(path=tmp_path / "回车录价.stn", unit_names=["雨水工程"])
    )
    segment = project_io.segments()[0]
    unit = project_io.units(segment.id)[0]
    for index, (item, amount) in enumerate(
        (("垫层", "1.0"), ("回填", "2.0"), ("余土", "3.0")), start=1
    ):
        assert unit_vm.create_element(
            unit.id,
            category=CATEGORY_STRUCTURE,
            name=f"检查井{index}",
            depth="3.2",
            amount="1",
            params=[("名称", "", f"检查井{index}"), ("单位", "", "座")],
            quantities=[("构筑物", item, "m3", amount)],
        ) is not None
    return unit


def _panel_for(qapp, unit):
    from app.views.panels.quantity_detail_panel import QuantityDetailPanel

    panel = QuantityDetailPanel()
    panel.show()
    panel.set_node(SimpleNamespace(id=unit.id, name=unit.name, kind="unit"))
    qapp.processEvents()
    return panel


def _price_key(table, row: int) -> str:
    """该行单价条目的 key（类别|项目|单位，与写库口径一致）。"""
    return "|".join(table.item(row, column).text() for column in (1, 2, 3))


def _open_editor(table, row: int, column: int) -> QLineEdit:
    """打开 (row, column) 单元格的行内编辑器并返回编辑器控件。"""
    table.setCurrentCell(row, column)
    item = table.item(row, column)
    assert item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable
    table.editItem(item)
    editors = [
        child
        for child in table.viewport().children()
        if isinstance(child, QLineEdit) and child.isVisibleTo(table.viewport())
    ]
    assert len(editors) == 1, f"期望恰好一个行内编辑器，实际 {len(editors)} 个"
    return editors[0]


def _press_enter(editor) -> None:
    QApplication.sendEvent(
        editor,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier),
    )


# --------------------------------------------------------------------------- #
# 定额工程量表
# --------------------------------------------------------------------------- #
def test_enter_on_quota_price_commits_and_moves_to_next_row(qapp, three_row_unit) -> None:
    """定额表单价格按回车：提交写库 + 当前格移到下一行单价列。"""
    panel = _panel_for(qapp, three_row_unit)
    table = panel._quota_table
    assert table.rowCount() == 3

    key = _price_key(table, 0)
    editor = _open_editor(table, 0, _COL_PRICE)
    editor.setText("123")
    _press_enter(editor)

    assert summary.prices()[key] == 123
    assert table.item(0, _COL_PRICE).text() == "123"
    assert table.item(1, _COL_PRICE).text() == "0"  # 下一行未被改动
    assert table.currentRow() == 1
    assert table.currentColumn() == _COL_PRICE

    # 单价联动只重乘、不重建表格：事件循环转一圈后选中仍在新行
    qapp.processEvents()
    assert table.currentRow() == 1
    assert table.currentColumn() == _COL_PRICE


def test_enter_on_last_quota_row_only_commits(qapp, three_row_unit) -> None:
    """定额表末行按回车：只提交，焦点留在原格（没有下一行可去）。"""
    panel = _panel_for(qapp, three_row_unit)
    table = panel._quota_table
    last = table.rowCount() - 1

    key = _price_key(table, last)
    editor = _open_editor(table, last, _COL_PRICE)
    editor.setText("9")
    _press_enter(editor)

    assert summary.prices()[key] == 9
    assert table.currentRow() == last
    assert table.currentColumn() == _COL_PRICE


# --------------------------------------------------------------------------- #
# 清单工程量表（清单项目行单价是派生值，跳行时跳过）
# --------------------------------------------------------------------------- #
def test_enter_on_listing_quota_row_skips_listing_project_rows(
    qapp, three_row_unit
) -> None:
    """清单表工程量行按回车：跳过其下不可编辑的清单项目行，落到下一条工程量行。"""
    panel = _panel_for(qapp, three_row_unit)
    panel._segment_group.button(1).click()
    table = panel._listing_table
    # 行序：清单项目行 0、工程量行 1、清单项目行 2、工程量行 3、清单项目行 4、工程量行 5
    assert table.rowCount() == 6
    listing_price = table.item(2, _COL_PRICE)
    assert listing_price is not None
    assert not (listing_price.flags() & Qt.ItemFlag.ItemIsEditable)

    key = _price_key(table, 1)
    editor = _open_editor(table, 1, _COL_PRICE)
    editor.setText("55")
    _press_enter(editor)

    assert summary.prices()[key] == 55
    assert table.currentRow() == 3
    assert table.currentColumn() == _COL_PRICE

    qapp.processEvents()
    assert table.currentRow() == 3


def test_enter_on_last_listing_row_only_commits(qapp, three_row_unit) -> None:
    """清单表末行（最后一条工程量行）按回车：只提交，焦点留在原格。"""
    panel = _panel_for(qapp, three_row_unit)
    panel._segment_group.button(1).click()
    table = panel._listing_table
    last = table.rowCount() - 1

    key = _price_key(table, last)
    editor = _open_editor(table, last, _COL_PRICE)
    editor.setText("66")
    _press_enter(editor)

    assert summary.prices()[key] == 66
    assert table.currentRow() == last
    assert table.currentColumn() == _COL_PRICE


# --------------------------------------------------------------------------- #
# 只有单价列可编辑（回车跳行的落点）
# --------------------------------------------------------------------------- #
def test_enter_next_is_opted_in_for_price_column_only(qapp, three_row_unit) -> None:
    """两张表都挂上回车跳行，且只在单价列生效；其余列不可编辑。"""
    panel = _panel_for(qapp, three_row_unit)
    panel._segment_group.button(1).click()
    for table in (panel._quota_table, panel._listing_table):
        assert getattr(table, ENTER_NEXT_COLUMNS_ATTR, None) == (_COL_PRICE,)
        assert getattr(table, ENTER_NEXT_SKIP_READONLY_ATTR, None) is True
        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                if column == _COL_PRICE:
                    continue
                item = table.item(row, column)
                assert item is not None
                assert not (item.flags() & Qt.ItemFlag.ItemIsEditable), (
                    f"row={row} column={column}（{table.item(row, _COL_NAME).text()}）"
                )
