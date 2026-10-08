"""围护做法“围护类型”切换回归测试（旧版 FormPE ColEclsCat / mcEnclosure.setECpnt）。

复刻语义：切换做法的围护类型时清空原有分级、按构件库模板重建一级
（多级围护取库第一项）。构件库 Ei 里只有 放坡/喷锚护坡 的 A 参数是
“放坡系数 1:X”，钢板桩/横列板/钻孔灌注桩/SMW工法桩等支护类型 A 非
放坡系数 → 放坡系数按 0 处理，沟槽为直壁并走支护的 F/Z 公式出围护量。
"""

import pytest

from PySide6.QtCore import Qt


def _enclosure():
    from app.services import project_io

    return project_io.enclosures()[0]


# --------------------------------------------------------------------------- #
# 服务层：set_work_category（旧版 setECpnt）
# --------------------------------------------------------------------------- #
def test_set_work_category_rebuilds_level_from_template(project) -> None:
    from app.core.calc.groove import level_slope
    from app.core.models import base as orm
    from app.core.models.models import MULTI_LEVEL_TEXT, EnclosureWork
    from app.services import project_io

    library = project_io.component_library()
    session = orm.session()
    work = _enclosure().works_sorted()[0]

    project_io.set_work_category(session, work, library, "钢板桩")
    project_io.commit()
    work = session.get(EnclosureWork, work.id)
    assert work.cpnt_cat == "钢板桩"
    assert len(work.levels) == 1
    level = work.levels[0]
    assert level.name == "钢板桩"
    assert (level.h, level.step_width) == (-1.0, 1.0)  # 均分高度、平台宽 1
    params = {param.key: param.value for param in level.components[0].params}
    assert params["A"] == "单桩宽度 mm|400"  # 模板默认参数一并带入
    assert level_slope(level) == 0.0  # 非放坡类型 → 直壁

    project_io.set_work_category(session, work, library, MULTI_LEVEL_TEXT)
    project_io.commit()
    work = session.get(EnclosureWork, work.id)
    assert work.cpnt_cat == MULTI_LEVEL_TEXT
    # 多级围护：一级取库第一项（旧版 Ecpnti.First().Key）
    assert len(work.levels) == 1 and work.levels[0].name == "放坡"
    assert level_slope(work.levels[0]) == 1.0

    project_io.set_work_category(session, work, library, "放坡")
    project_io.commit()
    work = session.get(EnclosureWork, work.id)
    assert work.cpnt_cat == "放坡"
    assert level_slope(work.levels[0]) == 1.0


def test_sloped_vs_vertical_dig_and_enclosure_quantities(project) -> None:
    """钢板桩（直壁）与放坡（梯形）的挖方算式与围护量对比。"""
    from app.core.calc.engine import build_element_input, compute_element, resolve_element_principles
    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_BURIED
    from app.services import project_io
    from app.viewmodels import unit_vm

    session = orm.session()

    def _compute(element):
        pe, pf, pp, pw, pe_refs, pf_refs = resolve_element_principles(element, session)
        return compute_element(build_element_input(element, pe, pf, pe_refs, pf_refs, pp, pw))

    library = project_io.component_library()
    unit_id = project_io.units(project_io.segments()[0].id)[0].id
    element = unit_vm.create_element(
        unit_id, category=CATEGORY_BURIED, name="", depth="2.5", amount="10",
        pipes=[("Ⅰ级混凝土管", 600, "1")],
    )
    assert element is not None

    # 放坡（默认做法）：挖方算式含放坡项，无支护围护量
    result = _compute(element)
    assert result is not None
    dig = next(q for q in result.items() if q.key.startswith("开挖|"))
    assert "2×" in dig.expression and "+" in dig.expression  # (B+B+2×H×放坡系数)×H/2
    assert not [key for key in result.keys() if key.startswith("围护|")]

    # 切成钢板桩：挖方为直壁矩形算式，出现围护/支撑量
    project_io.set_work_category(
        session, _enclosure().works_sorted()[0], library, "钢板桩"
    )
    project_io.commit()
    result = _compute(element)
    assert result is not None
    dig = next(q for q in result.items() if q.key.startswith("开挖|"))
    assert "+" not in dig.expression  # 放坡系数 0 → B×H
    assert any(key.startswith("围护|") for key in result.keys())
    assert any(key.startswith("支撑|") for key in result.keys())


# --------------------------------------------------------------------------- #
# 原则编辑对话框（FormPE）：围护类型下拉切换
# --------------------------------------------------------------------------- #
def test_enclosure_dialog_switch_category_rebuilds(qapp, project) -> None:
    from app.core.models.models import MULTI_LEVEL_TEXT
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    dialog = EnclosureEditDialog(_enclosure().id)
    table = dialog._work_table
    try:
        work = dialog._enclosure().works_sorted()[0]
        dialog._on_work_category(work, "钢板桩")
        work = dialog._enclosure().works_sorted()[0]
        assert work.cpnt_cat == "钢板桩"
        assert work.levels[0].components[0].name == "钢板桩"
        # 围护类型下拉与描述列同步刷新（旧版 FlashdGVPERow）
        assert table.cellWidget(0, 2).currentText() == "钢板桩"
        assert table.item(0, 3).text() == "拉森钢板桩 支护"

        dialog._on_work_category(work, MULTI_LEVEL_TEXT)
        work = dialog._enclosure().works_sorted()[0]
        assert work.cpnt_cat == MULTI_LEVEL_TEXT
        assert table.item(0, 3).text() == MULTI_LEVEL_TEXT
        assert work.levels[0].name == "放坡"
    finally:
        dialog.close()


# --------------------------------------------------------------------------- #
# 做法编辑对话框（FormEcls）：分级增删、级类型切换、均分只读
# --------------------------------------------------------------------------- #
def test_enclosure_work_dialog_level_operations(qapp, project, monkeypatch) -> None:
    from app.views.dialogs.principle_dialogs import EnclosureWorkDialog

    # 全删被拦的提示框在 offscreen 下会阻塞，替换为记录调用
    shown: list[str] = []
    monkeypatch.setattr(
        "app.views.dialogs.principle_dialogs.FramelessMessageBox.information",
        lambda *_args, **_kwargs: shown.append("blocked"),
    )

    dialog = EnclosureWorkDialog(_enclosure().works_sorted()[0])
    try:
        assert dialog._level_table.rowCount() == 1
        dialog._add_level()
        assert dialog._level_table.rowCount() == 2  # 新级立即可见
        h_item = dialog._level_table.item(1, 1)
        assert h_item.text() == "均分高度"
        assert not (h_item.flags() & Qt.ItemFlag.ItemIsEditable)  # 均分级高只读

        # 新级自带模板构件（旧版 new mcEclsCpnt）：描述非空，双击可编辑
        assert dialog._level_table.item(1, 4).text() != ""
        assert dialog._levels()[1].components

        # 换级类型 → 构件按库模板重建（旧版 tmEC.Cpnt = Ecpnti[value]）
        dialog._on_level_category(dialog._levels()[0], "钢板桩")
        level = dialog._levels()[0]
        assert level.name == "钢板桩"
        assert level.components[0].name == "钢板桩"
        assert dialog._level_table.item(0, 4).text() == "拉森钢板桩 支护"

        # Insert 键插到当前行之前，order_no 重排
        dialog._level_table.setCurrentCell(1, 0)
        dialog._level_table.insert_requested.emit()
        assert dialog._level_table.rowCount() == 3
        assert [item.order_no for item in dialog._levels()] == [0, 1, 2]

        # 全删被拦（至少一级），删除部分行后 order_no 归一
        dialog._level_table.selectAll()
        dialog._delete_levels()
        assert shown == ["blocked"]
        assert dialog._level_table.rowCount() == 3
        dialog._level_table.setCurrentCell(1, 0)
        dialog._delete_levels()
        assert dialog._level_table.rowCount() == 2
        assert [item.order_no for item in dialog._levels()] == [0, 1]

        # 确定保存（order_no 归一）不再报错
        dialog._accept()
        assert dialog.saved
    finally:
        dialog.close()


def test_enclosure_work_dialog_repairs_bare_level(qapp, project) -> None:
    """历史遗留的无构件级：打开窗体时按级名补齐模板构件，描述可显示、双击可编辑。"""
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Component, EnclosureLevel
    from app.views.dialogs.principle_dialogs import EnclosureWorkDialog

    work = _enclosure().works_sorted()[0]
    session = orm.session()
    bare = EnclosureLevel(work_id=work.id, name="放坡", h=2.0, step_width=1.0, order_no=1)
    session.add(bare)
    session.flush()

    dialog = EnclosureWorkDialog(work)
    try:
        levels = session.scalars(
            select(EnclosureLevel).where(EnclosureLevel.work_id == work.id).order_by(EnclosureLevel.order_no)
        ).all()
        assert len(levels) == 2
        for level in levels:  # 旧行 + 补齐行都带模板构件
            assert level.components
            assert level.components[0].name == "放坡"
        assert dialog._level_table.item(1, 4).text() != ""  # 描述不再为空
        assert session.scalar(
            select(Component.id).where(Component.enclosure_level_id == bare.id)
        ) is not None
    finally:
        dialog.close()


# --------------------------------------------------------------------------- #
# 联动：原则窗体点击「确认修改」后 → 明细面板工程量与断面示意图刷新（编辑中不刷新）
# --------------------------------------------------------------------------- #
def test_unit_panel_refreshes_on_principle_confirm(qapp, project) -> None:
    from app.core.event_bus import bus
    from app.services import project_io
    from app.services.element_library import element_library
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog
    from app.views.main_window import MainWindow

    window = MainWindow()
    try:
        bus().project_opened.emit(str(project))
        window._tree_panel.vm.load()
        qapp.processEvents()
        root = window._tree_panel._tree.topLevelItem(0)
        window._tree_panel._tree.setCurrentItem(root.child(0).child(0))
        qapp.processEvents()
        template = element_library().units_of("直埋混凝土管")[0].elements[0]
        window._insert_template(template)
        qapp.processEvents()
        panel = window._unit_panel
        element_id = panel._current_element_id()
        assert element_id is not None
        # 模板不带埋深/数量，先补上让沟槽计算生效
        panel._vm.set_element_field(element_id, "depth", "2.5")
        panel._vm.set_element_field(element_id, "amount", "10")
        qapp.processEvents()
        digests = panel._quantity_tables["定额工程量"]

        def _category_items() -> list[str]:
            return [digests.item(row, 1).text() for row in range(digests.rowCount())]

        # 初始放坡：无围护量；断面为放坡（顶宽 > 底宽）
        assert "围护" not in _category_items()
        scene = panel._section_view._canvas._scene
        assert scene is not None and scene.top_width > scene.segments[0].bottom

        # 原则窗体编辑过程中（切围护类型即改即存）不刷新主界面
        dialog = EnclosureEditDialog(project_io.enclosures()[0].id)
        dialog._on_work_category(dialog._enclosure().works_sorted()[0], "钢板桩")
        qapp.processEvents()
        assert "围护" not in _category_items()
        scene = panel._section_view._canvas._scene
        assert scene.top_width > scene.segments[0].bottom  # 仍是放坡断面

        # 点击「确认修改」后统一刷新：出现围护量，断面变直壁
        dialog._confirm()
        qapp.processEvents()
        assert "围护" in _category_items()
        scene = panel._section_view._canvas._scene
        assert scene.top_width == pytest.approx(scene.segments[0].bottom)

        # 改名确认：tree_structure_changed 同步主表格原则下拉
        dialog = EnclosureEditDialog(project_io.enclosures()[0].id)
        dialog._name.setText("围护改名")
        dialog._confirm()
        qapp.processEvents()
        pe_combo = panel._element_table.cellWidget(0, 6)
        assert pe_combo.currentText() == "围护改名"
    finally:
        window.close()
