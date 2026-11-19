"""主表格埋深 / 数量列：平时显示算式求值结果，双击编辑算式原文。

两列都允许直接写算式（如 ``2.5+0.3``）。条目的 DisplayRole 必须保持算式
原文——行内编辑器读的就是它；绘制时由 ``_FocusCellDelegate`` 用
``_EXPRESSION_DISPLAY_ROLE`` 把显示文本换成求值结果，于是「退出编辑状态
（平时）」看到结果，「双击编辑」看到并可修改算式。纯数字不替换显示文本，
避免按 format_number 舍掉用户录入的精度；无效算式照原文显示并给警示色。
视图菜单「埋深/数量显示算式」勾选后（config ``ui.depth_amount_display``
= ``formula``）非编辑态改画算式原文，编辑路径不受影响。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QStyleOptionViewItem

from app.core.config import get_config, update_config
from app.core.models import base as orm
from app.core.models.models import Element
from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm
from app.views.panels.unit_panel import (
    _COL_AMOUNT,
    _COL_DEPTH,
    _EXPRESSION_DISPLAY_ROLE,
    UnitPanel,
)

from conftest import make_element as _element


@pytest.fixture()
def unit_with_amounts(tmp_path):
    """四条构件：算式 / 纯小数 / 负纯小数 / 无效算式；返回 (unit, 构件 id 列表)。"""
    project_io.new_project(NewProjectSpec(path=tmp_path / "数量算式.stn", unit_names=["雨水工程"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    ids = [
        _element("管A", amount="2.5+0.3"),
        _element("管B", amount="0.00005"),
        _element("管C", amount="2+"),
        _element("管D", amount="-0.00005"),
    ]
    return unit, ids


def _panel_for(qapp, unit) -> UnitPanel:
    panel = UnitPanel()
    panel._show_unit(unit.id, unit.name)
    qapp.processEvents()
    return panel


def _paint_text(table, row: int, column: int) -> str:
    """取委托绘制该格时实际使用的文本（不经屏幕像素）。"""
    option = QStyleOptionViewItem()
    table.itemDelegate().initStyleOption(option, table.model().index(row, column))
    return option.text


def _open_editor(table, row: int, column: int) -> QLineEdit:
    """打开 (row, column) 的行内编辑器并返回编辑器控件（与双击同一条路径）。"""
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


def test_amount_paints_result_but_keeps_expression(qapp, unit_with_amounts) -> None:
    """平时画求值结果；条目原文与 tooltip 仍保留算式。"""
    unit, _ids = unit_with_amounts
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    item = table.item(0, _COL_AMOUNT)
    assert item.text() == "2.5+0.3"  # DisplayRole = 算式原文（编辑器读它）
    assert _paint_text(table, 0, _COL_AMOUNT) == "2.8"  # 平时显示的是结果
    assert item.toolTip() == "2.5+0.3 = 2.8"


def test_double_click_editor_shows_expression_and_commit_shows_result(
    qapp, unit_with_amounts
) -> None:
    """双击编辑器里是算式原文；确认退出后平时状态显示新结果，库里存原文。"""
    unit, (e1, _e2, _e3, _e4) = unit_with_amounts
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    editor = _open_editor(table, 0, _COL_AMOUNT)
    assert editor.text() == "2.5+0.3"  # 双击看到的是可编辑的算式，不是结果

    editor.setText("1.5*2")
    _press_enter(editor)
    assert orm.session().get(Element, e1).amount == "1.5*2"  # 库里仍是算式原文

    qapp.processEvents()  # unit_changed 延后的局部刷新落地
    item = table.item(0, _COL_AMOUNT)
    assert item.text() == "1.5*2"
    assert _paint_text(table, 0, _COL_AMOUNT) == "3"


def test_depth_paints_result_and_editor_shows_expression(qapp, tmp_path) -> None:
    """埋深列与数量列同口径：平时显示结果，双击编辑器里是算式原文。"""
    project_io.new_project(NewProjectSpec(path=tmp_path / "埋深算式.stn", unit_names=["雨水工程"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    element_id = _element("管A", depth="2.5+0.5", amount="10")

    panel = _panel_for(qapp, unit)
    table = panel._element_table
    item = table.item(0, _COL_DEPTH)
    assert item.text() == "2.5+0.5"
    assert _paint_text(table, 0, _COL_DEPTH) == "3"
    assert item.toolTip() == "2.5+0.5 = 3"

    editor = _open_editor(table, 0, _COL_DEPTH)
    assert editor.text() == "2.5+0.5"
    editor.setText("4.2/1.4")
    _press_enter(editor)
    assert orm.session().get(Element, element_id).depth == "4.2/1.4"  # 库里存原文

    qapp.processEvents()
    assert table.item(0, _COL_DEPTH).text() == "4.2/1.4"
    assert _paint_text(table, 0, _COL_DEPTH) == "3"


def test_plain_number_keeps_original_precision(qapp, unit_with_amounts) -> None:
    """纯数字不换成 format_number 结果，保留用户录入的精度。"""
    unit, _ids = unit_with_amounts
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    assert table.item(1, _COL_AMOUNT).text() == "0.00005"
    assert _paint_text(table, 1, _COL_AMOUNT) == "0.00005"
    assert not table.item(1, _COL_AMOUNT).data(_EXPRESSION_DISPLAY_ROLE)

    # 带负号的纯小数同样按原文显示（format_number 会舍成 0）
    assert table.item(3, _COL_AMOUNT).text() == "-0.00005"
    assert _paint_text(table, 3, _COL_AMOUNT) == "-0.00005"
    assert not table.item(3, _COL_AMOUNT).data(_EXPRESSION_DISPLAY_ROLE)


def test_invalid_expression_shows_raw_text_with_warning(qapp, unit_with_amounts) -> None:
    """无效算式照原文显示（不静默按 0），tooltip 给原因。"""
    unit, _ids = unit_with_amounts
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    item = table.item(2, _COL_AMOUNT)
    assert _paint_text(table, 2, _COL_AMOUNT) == "2+"
    assert item.toolTip().startswith("算式错误：")
    assert not item.data(_EXPRESSION_DISPLAY_ROLE)


def test_editing_to_plain_number_clears_result_override(qapp, unit_with_amounts) -> None:
    """算式改成纯数字后，显示覆盖被清掉，按新原文显示。"""
    unit, _ids = unit_with_amounts
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    editor = _open_editor(table, 0, _COL_AMOUNT)
    editor.setText("5")
    _press_enter(editor)
    qapp.processEvents()

    item = table.item(0, _COL_AMOUNT)
    assert item.text() == "5"
    assert not item.data(_EXPRESSION_DISPLAY_ROLE)
    assert _paint_text(table, 0, _COL_AMOUNT) == "5"


def test_group_parent_amount_also_shows_result(qapp, tmp_path) -> None:
    """合槽父行（L_组）与强制同步的子构件行同样显示结果。"""
    project_io.new_project(NewProjectSpec(path=tmp_path / "合槽数量.stn", unit_names=["雨水工程"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    ids = [_element(f"管{i}", amount="10") for i in "AB"]
    group, error = unit_vm.create_trench_group(ids)
    assert group is not None and error is None
    unit_vm.update_group(group.id, amount="100+20")

    panel = _panel_for(qapp, unit)
    table = panel._element_table
    group_row = next(
        index for index, row in enumerate(panel._rows_cache) if hasattr(row, "member_count")
    )

    for row in (group_row, group_row + 1):  # 父行 + 成员行
        item = table.item(row, _COL_AMOUNT)
        assert item.text() == "100+20"
        assert _paint_text(table, row, _COL_AMOUNT) == "120"


# --------------------------------------------------------------------------- #
# 视图菜单「埋深/数量显示算式」：非编辑态显示口径切换（config ui.depth_amount_display）
# --------------------------------------------------------------------------- #
@pytest.fixture()
def set_display_mode():
    """返回切换显示口径的回调；用例结束后恢复默认「显示计算结果」口径。"""

    def _set(mode: str) -> None:
        update_config({"ui": {"depth_amount_display": mode}})

    try:
        yield _set
    finally:
        update_config({"ui": {"depth_amount_display": "result"}})


@pytest.fixture()
def formula_window(qapp, set_display_mode):
    """口径已切成「显示算式」时挂出的主窗体（用于锁定勾选项初始态）。"""
    set_display_mode("formula")
    from app.views.main_window import MainWindow

    window = MainWindow()
    try:
        yield window
    finally:
        window.close()


def test_formula_mode_paints_expression(qapp, unit_with_amounts, set_display_mode) -> None:
    """勾选「显示算式」：非编辑态画算式原文；双击编辑器里仍是算式。"""
    set_display_mode("formula")
    unit, _ids = unit_with_amounts
    panel = _panel_for(qapp, unit)
    table = panel._element_table

    assert _paint_text(table, 0, _COL_AMOUNT) == "2.5+0.3"  # 非编辑态显示算式原文
    assert _paint_text(table, 1, _COL_AMOUNT) == "0.00005"  # 纯数字口径不变
    assert not table.item(0, _COL_AMOUNT).data(_EXPRESSION_DISPLAY_ROLE)

    editor = _open_editor(table, 0, _COL_AMOUNT)
    assert editor.text() == "2.5+0.3"  # 编辑路径不受开关影响


def test_formula_mode_toggle_refreshes_loaded_rows(
    qapp, unit_with_amounts, set_display_mode
) -> None:
    """表已按结果口径装好后再切换：刷新方法即时改画，无需重开工程。"""
    unit, _ids = unit_with_amounts
    panel = _panel_for(qapp, unit)
    table = panel._element_table
    assert _paint_text(table, 0, _COL_AMOUNT) == "2.8"

    set_display_mode("formula")
    panel.refresh_depth_amount_display()
    assert _paint_text(table, 0, _COL_AMOUNT) == "2.5+0.3"

    set_display_mode("result")
    panel.refresh_depth_amount_display()
    assert _paint_text(table, 0, _COL_AMOUNT) == "2.8"


def test_formula_mode_group_parent_amount(qapp, tmp_path, set_display_mode) -> None:
    """合槽父行数量随口径切换；父行埋深格（恒 "-"）不被重算成警示色。"""
    set_display_mode("formula")
    project_io.new_project(NewProjectSpec(path=tmp_path / "合槽算式.stn", unit_names=["雨水工程"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    ids = [_element(f"管{i}", amount="10") for i in "AB"]
    group, error = unit_vm.create_trench_group(ids)
    assert group is not None and error is None
    unit_vm.update_group(group.id, amount="100+20")

    panel = _panel_for(qapp, unit)
    table = panel._element_table
    group_row = next(
        index for index, row in enumerate(panel._rows_cache) if hasattr(row, "member_count")
    )
    assert _paint_text(table, group_row, _COL_AMOUNT) == "100+20"
    assert _paint_text(table, group_row, _COL_DEPTH) == "-"

    set_display_mode("result")
    panel.refresh_depth_amount_display()
    assert _paint_text(table, group_row, _COL_AMOUNT) == "120"
    assert _paint_text(table, group_row, _COL_DEPTH) == "-"


def test_view_menu_toggle_persists(qapp, set_display_mode) -> None:
    """视图菜单勾选项：初始勾选态取自配置，切换即写回配置（跨次启动生效）。"""
    from app.views.main_window import MainWindow

    window = MainWindow()
    try:
        menubar = window._title_bar.menu_bar
        view_menu = next(
            menu_action.menu()
            for menu_action in menubar.actions()
            if menu_action.menu() is not None and menu_action.menu().title().startswith("视图")
        )
        action = window._act_formula_display
        assert action in view_menu.actions()
        assert action.isCheckable()
        assert not action.isChecked()  # 默认显示计算结果

        action.setChecked(True)
        assert get_config().depth_amount_display == "formula"
        action.setChecked(False)
        assert get_config().depth_amount_display == "result"
    finally:
        window.close()


def test_view_menu_action_initial_state_from_config(qapp, formula_window) -> None:
    """配置已是算式口径时启动：勾选项初始即为勾选。"""
    assert formula_window._act_formula_display.isChecked()
