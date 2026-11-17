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
    """五个类型；型号条数 = 1.0 原表 + 补充的常用断面。"""
    assert steel_products.kinds() == (
        "钢板桩型号",
        "支撑延米重量 kg/m",
        "钢围檩延米重量 kg/m",
        "工法桩轴数 轴",
        "型钢延米重量 kg/m",
    )
    assert len(steel_products.products_of("钢板桩型号")) == 22
    assert len(steel_products.products_of("支撑延米重量 kg/m")) == 18
    assert len(steel_products.products_of("钢围檩延米重量 kg/m")) == 20
    assert len(steel_products.products_of("工法桩轴数 轴")) == 8
    assert len(steel_products.products_of("型钢延米重量 kg/m")) == 8


def test_pipe_and_welded_h_weights_follow_their_formulas() -> None:
    """钢管 / 焊接 H 型钢的重量必须能由公式复现（数据表被改错时在这里报）。

    钢管：``π(D-t)tρ/1000``（ρ=7.85），1.0 表里的 Ø203×10=47.597 等就是这条；
    焊接 H：``(2·b·tf + (h-2tf)·tw) × 0.00785``，1.0 表里的 H300×200×6×8=38.49 等。
    """
    import math

    rho = 7.85
    for product in steel_products.products_of("支撑延米重量 kg/m"):
        d, t = (float(part) for part in product.name.removeprefix("Ø").split("×"))
        expected = math.pi * (d - t) * t * rho / 1000.0
        assert product.weight == pytest.approx(expected, abs=0.001), product.name
    for kind in ("钢围檩延米重量 kg/m", "型钢延米重量 kg/m"):
        for product in steel_products.products_of(kind):
            if not product.name.startswith("H"):
                continue
            h, b, tw, tf = (float(part) for part in product.name.removeprefix("H").split("×"))
            expected = (2 * b * tf + (h - 2 * tf) * tw) * rho / 1000.0
            assert product.weight == pytest.approx(expected, abs=0.01), product.name


def test_hot_rolled_section_weights_match_gb706() -> None:
    """热轧工字钢 / 槽钢取 GB/T 706 理论重量（与 1.0 的 I45a/b/c 同一来源）。"""
    purlin = {item.name: item.weight for item in steel_products.products_of("钢围檩延米重量 kg/m")}
    assert (purlin["I40a"], purlin["I40b"], purlin["I40c"]) == (67.6, 73.8, 80.1)
    assert (purlin["I45a"], purlin["I45b"], purlin["I45c"]) == (80.4, 87.4, 94.5)
    assert (purlin["I50a"], purlin["I50b"], purlin["I50c"]) == (93.6, 101.0, 109.0)
    piles = {item.name: item.weight for item in steel_products.products_of("钢板桩型号")}
    assert (piles["[40a"], piles["[40b"], piles["[40c"]) == (58.9, 65.2, 71.5)


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
    # 补充的常用型号：FSP 系列（日标）与拉森Ⅱ
    assert products["FSP-Ⅳ"].param_values()["单桩延米重量 kg/m"] == "76.1"
    assert products["拉森Ⅱ"].param_values()["单桩延米重量 kg/m"] == "48"
    assert products["FSP-ⅤL"].param_values()["单桩宽度 mm"] == "500"


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


def test_every_mixing_pile_has_a_standard_overlap() -> None:
    """所有工法桩型号都带搭接值：Ø850/Ø900 取 250、Ø700/Ø650 取 200。

    即「桩径 − 相邻钻杆中心距」的机械模数（Ø850 中心距 600、Ø900 中心距 650、
    Ø700 中心距 500、Ø650 中心距 450），与表内 Ø850/700/650 的单套截面积反算一致。
    """
    expected = {900: "250", 850: "250", 700: "200", 650: "200"}
    for product in steel_products.products_of("工法桩轴数 轴"):
        diameter = int(product.name[1:].split("二")[0].split("三")[0])
        assert product.overlap == float(expected[diameter]), product.name
        assert product.param_values()["搭接 mm"] == expected[diameter], product.name


def test_product_without_overlap_leaves_the_row_alone() -> None:
    """表里万一没有搭接值：不写「搭接 mm」（旧版会写空串，把 A-E 公式弄坏）。"""
    product = steel_products.SteelProduct(
        name="Ø900三轴工法桩", kind=steel_products.KIND_MIXING_PILE, weight=1.58, width=900, axes=3
    )
    assert "搭接 mm" not in product.param_values()


def test_weight_products_map_to_their_own_row() -> None:
    """支撑 / 钢围檩 / 型钢：型号只对应一行「延米重量」，值就是该型号的重量。"""
    support = {item.name: item for item in steel_products.products_of("支撑延米重量 kg/m")}
    assert support["Ø609×16"].param_values() == {"支撑延米重量 kg/m": "233.988"}
    assert support["Ø800×16"].param_values() == {"支撑延米重量 kg/m": "309.354"}
    assert support["Ø1000×16"].param_values() == {"支撑延米重量 kg/m": "388.271"}
    purlin = {item.name: item for item in steel_products.products_of("钢围檩延米重量 kg/m")}
    assert purlin["I45a"].param_values() == {"钢围檩延米重量 kg/m": "80.4"}
    assert purlin["H500×300×11×18"].param_values() == {"钢围檩延米重量 kg/m": "124.85"}
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
        self._slots: list = []
        self.triggered = _FakeSignal(self._slots)

    def setToolTip(self, text: str) -> None:  # noqa: N802 - Qt 命名
        self.tooltip = text

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


def _emit_context_menu(qapp, dialog, row: int) -> None:
    """在参数表该行上发一次右键（坐标走 viewport，与 item view 的信号一致）。"""
    from PySide6.QtCore import QPoint

    table = dialog._tables[""]
    position = QPoint(table.columnViewportPosition(0) + 5, table.rowViewportPosition(row) + 4)
    table.customContextMenuRequested.emit(position)
    qapp.processEvents()


def _right_click(qapp, dialog, row: int) -> _FakeMenu:
    """右键该行并返回弹出的菜单（该行没有候选时用例会在这里失败）。"""
    _emit_context_menu(qapp, dialog, row)
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
            item.name for item in steel_products.products_of("支撑延米重量 kg/m")
        ]
        assert "Ø609×16" in [action.text for action in support_menu.actions]
        assert "Ø800×16" in [action.text for action in support_menu.actions]

        purlin_menu = _right_click(qapp, dialog, rows["钢围檩延米重量 kg/m"])
        assert "I45c" in [action.text for action in purlin_menu.actions]
        assert "H500×300×11×18" in [action.text for action in purlin_menu.actions]

        # 与钢制品无关的行：右键直接没反应（不弹空菜单，也不弹提示项）
        before = len(_FakeMenu.captured)
        for row_name in ("桩长 m", "支撑垂直向数量 道", "支撑水平向间隔 m"):
            _emit_context_menu(qapp, dialog, rows[row_name])
        assert len(_FakeMenu.captured) == before

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


def test_param_menu_mixing_pile_fills_overlap(qapp, project, fake_menu) -> None:
    """SMW 工法桩：选型号把搭接一并填上（Ø900/Ø850 → 250，Ø700/Ø650 → 200）。"""
    pe = make_enclosure("SMW原则", "SMW工法桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        table = dialog._tables[""]
        assert table.item(rows["搭接 mm"], 2).text() == "350"  # 构件库模板默认值

        menu = _right_click(qapp, dialog, rows["工法桩轴数 轴"])
        assert [action.text for action in menu.actions] == [
            item.name for item in steel_products.products_of("工法桩轴数 轴")
        ]
        next(a for a in menu.actions if a.text == "Ø900三轴工法桩").activate()
        assert table.item(rows["桩径 mm"], 2).text() == "900"
        assert table.item(rows["工法桩轴数 轴"], 2).text() == "3"
        assert table.item(rows["单套截面积 m2"], 2).text() == "1.58"
        assert table.item(rows["搭接 mm"], 2).text() == "250"

        next(a for a in menu.actions if a.text == "Ø700二轴工法桩").activate()
        assert table.item(rows["桩径 mm"], 2).text() == "700"
        assert table.item(rows["工法桩轴数 轴"], 2).text() == "2"
        assert table.item(rows["单套截面积 m2"], 2).text() == "0.7024"
        assert table.item(rows["搭接 mm"], 2).text() == "200"

        next(a for a in menu.actions if a.text == "Ø850三轴工法桩").activate()
        assert table.item(rows["搭接 mm"], 2).text() == "250"
        assert table.item(rows["单套截面积 m2"], 2).text() == "1.495346490125"

        dialog.save()
        assert _param_value(component, "D") == "单套截面积 m2|1.495346490125"
        assert _param_value(component, "E") == "搭接 mm|250"
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
        assert empty.actions() == []  # 没有候选时上层根本不弹菜单
    finally:
        dialog.close()


def test_editor_still_opens_without_catalog(qapp, project, fake_menu, monkeypatch) -> None:
    """数据文件缺失时编辑器照常可用，右键不弹菜单（不是空菜单）。"""
    monkeypatch.setattr(steel_products, "steel_products", lambda: ())
    pe = make_enclosure("钢制品原则", "钢板桩")
    component = pe.works_sorted()[0].levels[0].components[0]
    dialog = _open_dialog(qapp, component)
    try:
        rows = _rows_by_name(dialog)
        before = len(_FakeMenu.captured)
        _emit_context_menu(qapp, dialog, rows["钢板桩型号"])
        assert len(_FakeMenu.captured) == before
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
