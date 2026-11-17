"""构件编辑器参数表右键选钢制品（旧版 FormCpntEdit 的 CMS 右键菜单）。

1.0 在参数表上挂了 ``ContextMenuStrip``：按当前行的参数名过滤
``mscInventory.SteelProducts``，选中型号后把该型号的参数值回填到同名的行。
2.0 用 ``app/services/steel_products.py`` 承接数据、``ComponentEditDialog``
的 ``_on_param_context_menu`` 承接菜单。
"""

from __future__ import annotations

import pytest

from app.services import project_io, steel_products
from conftest import make_enclosure


# --------------------------------------------------------------------------- #
# 目录数据
# --------------------------------------------------------------------------- #
def test_catalog_kinds_and_counts() -> None:
    """五个类型、型号条数与 1.0 数据表一致。"""
    assert steel_products.kinds() == (
        "钢板桩型号",
        "支撑延米重量 kg/m",
        "钢围檩延米重量 kg/m",
        "工法桩轴数 轴",
        "型钢延米重量 kg/m",
    )
    assert len(steel_products.products_of("钢板桩型号")) == 14
    assert len(steel_products.products_of("支撑延米重量 kg/m")) == 5
    assert len(steel_products.products_of("钢围檩延米重量 kg/m")) == 9
    assert len(steel_products.products_of("工法桩轴数 轴")) == 8
    assert len(steel_products.products_of("型钢延米重量 kg/m")) == 3


def test_sheet_pile_product_values() -> None:
    """钢板桩型号：型号文字进菜单，名称列写进「钢板桩型号」，宽度 / 间隔 / 重量同填。"""
    products = {item.name: item for item in steel_products.products_of("钢板桩型号")}
    larsen = products["拉森Ⅳ"]
    assert larsen.param_values() == {
        "钢板桩型号": "拉森钢板桩",
        "单桩宽度 mm": "400",
        "桩中心间隔 mm": "400",
        "单桩延米重量 kg/m": "75",
    }
    # 槽型钢板桩与普通钢板桩的类别名不同，重量也不同
    assert products["[32c"].param_values()["单桩延米重量 kg/m"] == "48.3"
    assert products["[32c"].param_values()["钢板桩型号"] == "槽型钢板桩"
    assert products["FSP VIL"].param_values()["钢板桩型号"] == "钢板桩"


def test_mixing_pile_product_values_keep_full_area() -> None:
    """工法桩：名称列是轴数、F6 是搭接；单套截面积必须原样写回（不能被 %g 截断）。"""
    products = {item.name: item for item in steel_products.products_of("工法桩轴数 轴")}
    three_axis = products["Ø850三轴工法桩"]
    assert three_axis.param_values() == {
        "桩径 mm": "850",
        "工法桩轴数 轴": "3",
        "单套截面积 m2": "1.495346490125",
        "搭接 mm": "250",
    }
    # 表里没有搭接值的型号不写「搭接 mm」（旧版会写空串，把 A-E 公式弄坏）
    assert "搭接 mm" not in products["Ø900三轴工法桩"].param_values()


def test_weight_products_map_to_their_own_row() -> None:
    """支撑 / 钢围檩 / 型钢：型号只对应一行「延米重量」，值就是该型号的重量。"""
    support = {item.name: item for item in steel_products.products_of("支撑延米重量 kg/m")}
    assert support["Ø609×16"].param_values() == {"支撑延米重量 kg/m": "233.988"}
    purlin = {item.name: item for item in steel_products.products_of("钢围檩延米重量 kg/m")}
    assert purlin["I45a"].param_values() == {"钢围檩延米重量 kg/m": "80.4"}
    section = {item.name: item for item in steel_products.products_of("型钢延米重量 kg/m")}
    assert section["H700×300×13×24"].param_values() == {"型钢延米重量 kg/m": "179.57"}


def test_format_number() -> None:
    assert steel_products.format_number(None) == ""
    assert steel_products.format_number(250.0) == "250"
    assert steel_products.format_number(27.5) == "27.5"
    assert steel_products.format_number(1.495346490125) == "1.495346490125"


def test_unknown_kind_has_no_products() -> None:
    assert steel_products.products_of("桩长 m") == ()
    assert steel_products.kind_for_param("桩长 m") == ""
    assert steel_products.kind_for_param("支撑延米重量 kg/m") == "支撑延米重量 kg/m"


def test_pile_weight_row_shares_the_pile_menu() -> None:
    """「单桩延米重量 kg/m」行也调出钢板桩型号菜单（旧版只有型号行有菜单）。"""
    assert steel_products.kind_for_param("单桩延米重量 kg/m") == "钢板桩型号"
    assert steel_products.kind_for_param("单桩宽度 mm") == ""


# --------------------------------------------------------------------------- #
# 构件编辑器右键菜单
# --------------------------------------------------------------------------- #
class _FakeSignal:
    def __init__(self, slots: list) -> None:
        self._slots = slots

    def connect(self, slot) -> None:
        self._slots.append(slot)


class _FakeAction:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tooltip = ""
        self.enabled = True
        self._slots: list = []
        self.triggered = _FakeSignal(self._slots)

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt 命名
        self.tooltip = text

    def setEnabled(self, flag: bool) -> None:  # noqa: N802 - Qt 命名
        self.enabled = flag

    def activate(self) -> None:
        for slot in self._slots:
            slot(False)


class _FakeMenu:
    """替掉 QMenu：不真的弹菜单，把菜单项留给用例点。"""

    captured: list["_FakeMenu"] = []

    def __init__(self, parent=None) -> None:
        self.actions: list[_FakeAction] = []

    def setToolTipsVisible(self, flag: bool) -> None:  # noqa: N802 - Qt 命名
        pass

    def addAction(self, text: str) -> _FakeAction:  # noqa: N802 - Qt 命名
        action = _FakeAction(text)
        self.actions.append(action)
        return action

    def exec(self, position) -> None:  # noqa: N802 - Qt 命名
        _FakeMenu.captured.append(self)
        return None


@pytest.fixture()
def fake_menu(monkeypatch):
    from app.views.dialogs import principle_dialogs

    _FakeMenu.captured = []
    monkeypatch.setattr(principle_dialogs, "QMenu", _FakeMenu)
    return _FakeMenu


def _open_dialog(qapp, component):
    from app.views.dialogs.principle_dialogs import ComponentEditDialog

    dialog = ComponentEditDialog(component)
    dialog.show()
    qapp.processEvents()
    return dialog


def _rows_by_name(dialog) -> dict[str, int]:
    table = dialog._tables[""]
    return {dialog._param_display_name(row): row for row in range(table.rowCount())}


def _right_click(qapp, dialog, row: int) -> _FakeMenu:
    """在参数表该行上发一次右键（坐标走 viewport，与 item view 的信号一致）。"""
    from PySide6.QtCore import QPoint

    table = dialog._tables[""]
    position = QPoint(table.columnViewportPosition(0) + 5, table.rowViewportPosition(row) + 4)
    table.customContextMenuRequested.emit(position)
    qapp.processEvents()
    return _FakeMenu.captured[-1]


def _param_value(component, key: str) -> str:
    return next(param.value for param in component.params if param.key == key)


def test_param_menu_lists_products_of_the_row_kind(qapp, project, fake_menu) -> None:
    """右键「钢板桩型号」行只列钢板桩；右键「支撑延米重量」行只列钢支撑。"""
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        pile_menu = _right_click(qapp, dialog, rows["钢板桩型号"])
        assert [action.text for action in pile_menu.actions] == [
            item.name for item in steel_products.products_of("钢板桩型号")
        ]
        assert pile_menu.actions[0].tooltip.startswith("槽型钢板桩")

        support_menu = _right_click(qapp, dialog, rows["支撑延米重量 kg/m"])
        assert [action.text for action in support_menu.actions] == [
            "Ø203×10", "Ø299×10", "Ø300×8", "Ø426×12", "Ø609×16",
        ]

        purlin_menu = _right_click(qapp, dialog, rows["钢围檩延米重量 kg/m"])
        assert "I45c" in [action.text for action in purlin_menu.actions]

        # 与钢制品无关的行：给一条禁用的提示，不是空菜单
        other_menu = _right_click(qapp, dialog, rows["桩长 m"])
        assert [action.text for action in other_menu.actions] == ["该行没有可选的钢制品"]
        assert other_menu.actions[0].enabled is False

        # 「单桩延米重量」行调出同一份钢板桩型号菜单，选完照旧回填四行
        weight_menu = _right_click(qapp, dialog, rows["单桩延米重量 kg/m"])
        assert [action.text for action in weight_menu.actions] == [
            item.name for item in steel_products.products_of("钢板桩型号")
        ]
        next(a for a in weight_menu.actions if a.text == "拉森Ⅲ").activate()
        table = dialog._tables[""]
        assert table.item(rows["钢板桩型号"], 2).text() == "拉森钢板桩"
        assert table.item(rows["单桩延米重量 kg/m"], 2).text() == "62"
    finally:
        dialog.close()


def test_param_menu_fills_pile_and_support_values(qapp, project, fake_menu) -> None:
    """选钢板桩型号 → 型号 / 宽度 / 间隔 / 单桩延米重量一起填；选钢支撑 → 只填重量。"""
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        table = dialog._tables[""]

        pile_menu = _right_click(qapp, dialog, rows["钢板桩型号"])
        next(a for a in pile_menu.actions if a.text == "拉森Ⅳ").activate()
        qapp.processEvents()
        # 值列（第 2 列）按行名回填
        assert table.item(rows["钢板桩型号"], 2).text() == "拉森钢板桩"
        assert table.item(rows["单桩宽度 mm"], 2).text() == "400"
        assert table.item(rows["桩中心间隔 mm"], 2).text() == "400"
        assert table.item(rows["单桩延米重量 kg/m"], 2).text() == "75"

        support_menu = _right_click(qapp, dialog, rows["支撑延米重量 kg/m"])
        next(a for a in support_menu.actions if a.text == "Ø609×16").activate()
        assert table.item(rows["支撑延米重量 kg/m"], 2).text() == "233.988"

        purlin_menu = _right_click(qapp, dialog, rows["钢围檩延米重量 kg/m"])
        next(a for a in purlin_menu.actions if a.text == "I45a").activate()
        assert table.item(rows["钢围檩延米重量 kg/m"], 2).text() == "80.4"

        # 点确定后落进构件参数（存储格式 显示名|值）
        dialog.save()
        assert _param_value(component, "B") == "钢板桩型号|拉森钢板桩"
        assert _param_value(component, "A") == "单桩宽度 mm|400"
        assert _param_value(component, "C") == "桩中心间隔 mm|400"
        assert _param_value(component, "E") == "单桩延米重量 kg/m|75"
        assert _param_value(component, "H") == "支撑延米重量 kg/m|233.988"
        assert _param_value(component, "I") == "钢围檩延米重量 kg/m|80.4"
    finally:
        dialog.close()


def test_param_menu_mixing_pile_keeps_overlap_when_catalog_has_none(
    qapp, project, fake_menu
) -> None:
    """SMW 工法桩：选无搭接数据的型号时保留用户当前搭接值（1.0 会写成空串）。"""
    pe = make_enclosure("SMW原则", "SMW工法桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        table = dialog._tables[""]
        assert table.item(rows["搭接 mm"], 2).text() == "350"

        menu = _right_click(qapp, dialog, rows["工法桩轴数 轴"])
        assert [action.text for action in menu.actions] == [
            item.name for item in steel_products.products_of("工法桩轴数 轴")
        ]
        next(a for a in menu.actions if a.text == "Ø900三轴工法桩").activate()
        assert table.item(rows["桩径 mm"], 2).text() == "900"
        assert table.item(rows["工法桩轴数 轴"], 2).text() == "3"
        assert table.item(rows["单套截面积 m2"], 2).text() == "1.58"
        assert table.item(rows["搭接 mm"], 2).text() == "350"  # 未被清空

        # 表里有搭接值的型号才覆盖
        next(a for a in menu.actions if a.text == "Ø850三轴工法桩").activate()
        assert table.item(rows["搭接 mm"], 2).text() == "250"
        assert table.item(rows["单套截面积 m2"], 2).text() == "1.495346490125"

        dialog.save()
        assert _param_value(component, "D") == "单套截面积 m2|1.495346490125"
    finally:
        dialog.close()


def test_param_menu_skips_rows_missing_from_table(qapp, project, fake_menu) -> None:
    """参数表里没有的行不补造：只填已存在的同名行（旧版同样只回填现有行）。"""
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        # 删掉「单桩宽度 mm」行后再选型号：其余三行照填，被删的行不会凭空出现
        dialog._delete_row("", rows["单桩宽度 mm"])
        rows = _rows_by_name(dialog)
        assert "单桩宽度 mm" not in rows
        menu = _right_click(qapp, dialog, rows["钢板桩型号"])
        next(a for a in menu.actions if a.text == "拉森Ⅵ").activate()
        assert dialog._tables[""].item(rows["单桩延米重量 kg/m"], 2).text() == "121.8"
        assert "单桩宽度 mm" not in _rows_by_name(dialog)
    finally:
        dialog.close()


def test_component_editor_menu_does_not_break_formula_table(qapp, project, fake_menu) -> None:
    """右键菜单只挂参数表：公式表右键不弹钢制品菜单。"""
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        from PySide6.QtCore import QPoint, Qt

        formula = dialog._tables["Q"]
        assert formula.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu
        before = len(_FakeMenu.captured)
        formula.customContextMenuRequested.emit(QPoint(5, 5))
        qapp.processEvents()
        assert len(_FakeMenu.captured) == before
    finally:
        dialog.close()


def test_real_context_menu_event_resolves_clicked_row(qapp, project, fake_menu) -> None:
    """真实右键事件（viewport 坐标）：菜单跟着光标所在行，不是当前选中行。"""
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QApplication

    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        table = dialog._tables[""]
        rows = _rows_by_name(dialog)
        row = rows["钢围檩延米重量 kg/m"]
        table.setCurrentCell(0, 0)  # 选中行故意不是被右键的行
        rect = table.visualItemRect(table.item(row, 0))
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            rect.center(),
            table.viewport().mapToGlobal(rect.center()),
        )
        QApplication.sendEvent(table.viewport(), event)
        qapp.processEvents()
        assert [action.text for action in _FakeMenu.captured[-1].actions] == [
            item.name for item in steel_products.products_of("钢围檩延米重量 kg/m")
        ]
    finally:
        dialog.close()


def test_real_menu_actions(qapp, project) -> None:
    """真实 QMenu：菜单项文字 / 悬停提示 / 禁用态（不 exec，只构建）。"""
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        menu = dialog._build_steel_menu(dialog._steel_products_for_row(rows["钢板桩型号"]))
        actions = menu.actions()
        assert [action.text() for action in actions] == [
            item.name for item in steel_products.products_of("钢板桩型号")
        ]
        assert all(action.isEnabled() for action in actions)
        assert actions[0].toolTip() == "槽型钢板桩，单桩宽度 250 mm，单桩延米重量 27.5 kg/m"
        # 菜单项真的接到回填上（真实信号）
        next(action for action in actions if action.text() == "拉森Ⅳ").trigger()
        assert dialog._tables[""].item(rows["单桩延米重量 kg/m"], 2).text() == "75"

        empty = dialog._build_steel_menu(())
        assert [action.text() for action in empty.actions()] == ["该行没有可选的钢制品"]
        assert empty.actions()[0].isEnabled() is False
    finally:
        dialog.close()


def test_editor_still_opens_without_catalog(qapp, project, fake_menu, monkeypatch) -> None:
    """数据文件缺失时编辑器照常可用，右键只给提示。"""
    monkeypatch.setattr(steel_products, "steel_products", lambda: ())
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        menu = _right_click(qapp, dialog, rows["钢板桩型号"])
        assert [action.text for action in menu.actions] == ["该行没有可选的钢制品"]
    finally:
        dialog.close()


def test_project_commit_unaffected_by_menu(qapp, project, fake_menu) -> None:
    """填完值后整体提交不报错（参数值仍是「显示名|表达式」两段）。"""
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        menu = _right_click(qapp, dialog, rows["钢板桩型号"])
        next(a for a in menu.actions if a.text == "拉森Ⅴ").activate()
        dialog._accept()
        project_io.commit()
        enclosure = next(item for item in project_io.enclosures() if item.name == pe.name)
        stored = {
            param.key: param.value
            for param in enclosure.works_sorted()[0].levels[0].components[0].params
        }
        assert stored["B"] == "钢板桩型号|拉森钢板桩"
        assert stored["E"] == "单桩延米重量 kg/m|100"
    finally:
        dialog.close()
