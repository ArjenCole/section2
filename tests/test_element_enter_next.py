"""主表格埋深 / 数量列的「回车提交并跳下一行」测试。

编辑埋深 / 数量单元格时按回车：提交当前单元格并把当前格移到下一可见行
同一列（跳过收起的合槽成员行），整表重载（unit_changed 延后刷新）落地后
选中仍落在新行；名称列与其余表格保持 Qt 默认行为（提交后留在原格），
带修饰键的回车（Ctrl+Enter）同样走默认行为。Qt 部分离屏运行。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from app.core.models import base as orm
from app.core.models.models import Element
from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.views.panels.unit_panel import _COL_AMOUNT, _COL_DEPTH, _COL_NAME
from app.viewmodels import unit_vm
from app.views.widgets.table_edit_delegate import ENTER_NEXT_COLUMNS_ATTR

from conftest import make_element as _element


@pytest.fixture()
def three_elements(tmp_path):
    """三个构件的单位工程，返回 (unit, [e1, e2, e3] 构件 id)。"""
    project_io.new_project(NewProjectSpec(path=tmp_path / "回车.stn", unit_names=["雨水工程"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    ids = [_element(f"管{i}", depth="3", amount="10") for i in "ABC"]
    return unit, ids


@pytest.fixture()
def four_elements_with_group(tmp_path):
    """四个构件（后三个成组）的单位工程，返回 (unit, [e1..e4], group)。"""
    project_io.new_project(NewProjectSpec(path=tmp_path / "合槽.stn", unit_names=["雨水工程"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    ids = [_element(f"管{i}", depth="3", amount="10") for i in "ABCD"]
    group, error = unit_vm.create_trench_group([ids[1], ids[2]])
    assert group is not None and error is None
    return unit, ids, group


def _panel_for(qapp, unit):
    from app.views.panels.unit_panel import UnitPanel

    panel = UnitPanel()
    panel._show_unit(unit.id, unit.name)
    qapp.processEvents()
    return panel


def _open_editor(table, row: int, column: int) -> QLineEdit:
    """打开 (row, column) 单元格的行内编辑器并返回编辑器控件。"""
    table.setCurrentCell(row, column)
    item = table.item(row, column)
    assert item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable
    table.editItem(item)
    # 离屏用例不 show()：isVisible 恒 False，用 isVisibleTo 判断编辑器本体
    editors = [
        child
        for child in table.viewport().children()
        if isinstance(child, QLineEdit) and child.isVisibleTo(table.viewport())
    ]
    assert len(editors) == 1, f"期望恰好一个行内编辑器，实际 {len(editors)} 个"
    return editors[0]


def _press_enter(editor, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
    QApplication.sendEvent(
        editor,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, modifiers),
    )


def test_enter_on_depth_commits_and_moves_to_next_row(qapp, three_elements) -> None:
    """埋深列按回车：提交写库 + 焦点移到下一行同列，重载后仍落在新行。"""
    unit, (e1, e2, _e3) = three_elements
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    editor = _open_editor(table, 0, _COL_DEPTH)
    editor.setText("4")
    _press_enter(editor)

    # 提交即写库；焦点已移到下一行同一列
    assert orm.session().get(Element, e1).depth == "4"
    assert table.currentRow() == 1
    assert table.currentColumn() == _COL_DEPTH

    # unit_changed 触发的整表重载（QTimer 延后）落地后，选中仍在新行同列
    qapp.processEvents()
    assert table.currentRow() == 1
    assert table.currentColumn() == _COL_DEPTH
    assert table.item(0, _COL_DEPTH).text() == "4"  # 重载按新数据装填
    assert table.item(1, _COL_DEPTH).text() == "3"  # 下一行未被改动


def test_enter_on_amount_accepts_expression_and_moves_down(qapp, three_elements) -> None:
    """数量列按回车：算式原样保存，焦点移到下一行同列。"""
    unit, (e1, _e2, _e3) = three_elements
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    editor = _open_editor(table, 0, _COL_AMOUNT)
    editor.setText("5+5")
    _press_enter(editor)

    assert orm.session().get(Element, e1).amount == "5+5"
    assert table.currentRow() == 1
    assert table.currentColumn() == _COL_AMOUNT
    qapp.processEvents()
    assert table.currentRow() == 1


def test_enter_on_last_row_only_commits(qapp, three_elements) -> None:
    """末行的埋深按回车：只提交，焦点留在原格（没有下一行可去）。"""
    unit, (_e1, _e2, e3) = three_elements
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    last = table.rowCount() - 1
    assert last == 2  # 三条构件
    editor = _open_editor(table, last, _COL_DEPTH)
    editor.setText("7")
    _press_enter(editor)

    assert orm.session().get(Element, e3).depth == "7"
    assert table.currentRow() == last
    assert table.currentColumn() == _COL_DEPTH
    qapp.processEvents()
    assert table.currentRow() == last


def test_enter_lands_on_group_parent_row(qapp, four_elements_with_group) -> None:
    """合槽父行可见时按回车：下一行就是父行（只选中，父行埋深不可编辑）。"""
    unit, (e1, _e2, _e3, _e4), _group = four_elements_with_group
    panel = _panel_for(qapp, unit)
    table = panel._element_table
    # 行序：管A、组父行、管B、管C、管D
    assert table.rowCount() == 5

    editor = _open_editor(table, 0, _COL_DEPTH)
    editor.setText("2")
    _press_enter(editor)

    assert orm.session().get(Element, e1).depth == "2"
    assert table.currentRow() == 1
    assert table.currentColumn() == _COL_DEPTH


def test_enter_skips_hidden_members_after_group_parent_amount(qapp, four_elements_with_group) -> None:
    """收起组后在父行数量（L_组）按回车：提交并跳过隐藏成员行，落到组后第一条可见构件。"""
    unit, (_e1, e2, e3, e4), group = four_elements_with_group
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    group_row = next(
        index for index, row in enumerate(panel._rows_cache) if hasattr(row, "member_count")
    )
    panel._on_group_toggle_requested(group_row)  # 收起：成员行隐藏
    assert table.isRowHidden(2) and table.isRowHidden(3)

    editor = _open_editor(table, 1, _COL_AMOUNT)
    editor.setText("99")
    _press_enter(editor)

    assert orm.session().get(Element, e2).amount == "99"  # 父行数量同步全部成员
    assert orm.session().get(Element, e3).amount == "99"
    assert table.currentRow() == 4
    assert table.currentColumn() == _COL_AMOUNT
    qapp.processEvents()
    assert table.currentRow() == 4


def test_enter_on_name_column_keeps_default_behavior(qapp, three_elements) -> None:
    """名称列不在回车跳行列内：按回车只提交，焦点留在原格。"""
    unit, (e1, _e2, _e3) = three_elements
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    editor = _open_editor(table, 0, _COL_NAME)
    editor.setText("管改")
    _press_enter(editor)
    # Qt 6.10+ 默认回车提交经 _q_commitDataAndCloseEditor 排队执行
    qapp.processEvents()

    assert orm.session().get(Element, e1).name == "管改"
    assert table.currentRow() == 0
    assert table.currentColumn() == _COL_NAME
    qapp.processEvents()
    assert table.currentRow() == 0


def test_enter_with_ctrl_modifier_keeps_default_behavior(qapp, three_elements) -> None:
    """Ctrl+Enter 不触发跳行：提交后焦点留在原格（与 Qt 默认一致）。"""
    unit, (e1, _e2, _e3) = three_elements
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    editor = _open_editor(table, 0, _COL_DEPTH)
    editor.setText("5")
    _press_enter(editor, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()  # 默认提交排队执行

    assert orm.session().get(Element, e1).depth == "5"
    assert table.currentRow() == 0
    assert table.currentColumn() == _COL_DEPTH


def test_only_main_table_opted_in(qapp, three_elements) -> None:
    """回车跳行是主表格专属配置：明细面板各表未挂该属性，保持默认行为。"""
    unit, (_e1, _e2, _e3) = three_elements
    panel = _panel_for(qapp, unit)
    assert getattr(panel._element_table, ENTER_NEXT_COLUMNS_ATTR, None) == (_COL_DEPTH, _COL_AMOUNT)
    for table in panel._detail_tables():
        assert getattr(table, ENTER_NEXT_COLUMNS_ATTR, None) is None
