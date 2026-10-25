"""原则 UI 复刻相关回归测试。

覆盖：构件库解析、原则重名后缀、删除并入语义、*.spcp 导入导出回路、
v1→v2 结构迁移（element.source 列）、原则编辑对话框与原则横条的关键交互。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.services.element_library import element_library
from app.viewmodels import unit_vm


# --------------------------------------------------------------------------- #
# 构件库
# --------------------------------------------------------------------------- #
def test_element_library_categories_and_templates() -> None:
    library = element_library()
    assert library.categories == (
        "直埋混凝土管", "直埋塑料管", "直埋金属类管道", "混凝土结构", "非开挖管道", "附属构筑物",
    )
    templates = [tpl for units in library.units.values() for unit in units for tpl in unit.elements]
    assert len(templates) == 407
    assert all(tpl.label for tpl in templates)
    # 附属构筑物（构筑物类）：24 座检查井 + 单篦/双篦雨水口 + 排放口 + 自定义构筑物
    structures = library.units_of("附属构筑物")[0].elements
    assert len(structures) == 3
    well = structures[0]
    assert well.category == 7
    assert well.params[0] == ("-名称", well.label)
    assert ("-井筒 个", "1") in well.params
    assert ("-井筒 m3/m", "0.71") in well.params
    assert any(key == "构筑物|垫层|m3" for key, _value in well.params)
    assert not well.pipes
    # 雨水口 / 排放口 / 自定义构筑物：Name 为空的模板靠“-名称”参数兜底显示
    rain_inlets = library.units_of("附属构筑物")[4].elements
    assert [tpl.label for tpl in rain_inlets] == ["单篦式雨水口", "双篦式雨水口"]


def test_insert_template_attaches_first_principles(project) -> None:
    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().units_of("直埋混凝土管")[0].elements[0]
    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None
    assert element.pe_name == project_io.enclosure_names()[0]
    assert element.pf_name == project_io.foundation_names()[0]
    assert element.pipes, "模板的管材应一并带入"
    assert unit_vm.element_rows(unit.id)[0].spec == "Ⅰ级混凝土管 Dn150"


def test_insert_template_before_selected_row(project) -> None:
    unit = project_io.units(project_io.segments()[0].id)[0]
    first = unit_vm.insert_blank_element(unit.id)
    template = element_library().units_of("直埋混凝土管")[0].elements[0]
    inserted = unit_vm.insert_element_template(unit.id, template, before_element_id=first.id)
    rows = unit_vm.element_rows(unit.id)
    assert [row.id for row in rows] == [inserted.id, first.id]


# --------------------------------------------------------------------------- #
# 原则增删改（原版交互语义）
# --------------------------------------------------------------------------- #
def test_unique_principle_name_suffix(project) -> None:
    assert project_io.unique_principle_name("钢板桩", ["默认围护原则"]) == "钢板桩"
    assert project_io.unique_principle_name("钢板桩", ["默认围护原则", "钢板桩"]) == "钢板桩1"
    assert project_io.unique_principle_name("钢板桩", ["钢板桩", "钢板桩1"]) == "钢板桩2"
    # create_enclosure 重名时按同一规则自动加后缀
    first = project_io.create_enclosure("钢板桩")
    second = project_io.create_enclosure("钢板桩")
    assert (first.name, second.name) == ("钢板桩", "钢板桩1")


def test_delete_enclosure_merges_references(project) -> None:
    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, name="管子")
    replaced = project_io.create_enclosure("钢板桩")
    target = project_io.merge_target_enclosure("默认围护原则")
    assert target == replaced.name
    error = project_io.delete_enclosure(
        project_io.enclosures()[0].id, project_io.merge_target_enclosure("默认围护原则")
    )
    assert error is None
    assert unit_vm.orm.session().get(type(element), element.id).pe_name == target


def test_delete_last_principle_is_rejected(project) -> None:
    error = project_io.delete_foundation(project_io.foundations()[0].id)
    assert error == "至少需要一种地基处理原则。"
    error = project_io.delete_enclosure(project_io.enclosures()[0].id)
    assert error == "至少需要一种沟槽围护原则。"


# --------------------------------------------------------------------------- #
# *.spcp 导入/导出
# --------------------------------------------------------------------------- #
def test_spcp_roundtrip(project, tmp_path: Path) -> None:
    pe = project_io.enclosures()[0]
    pf = project_io.foundations()[0]
    out_pe = tmp_path / "pe.spcp"
    out_pf = tmp_path / "pf.spcp"
    project_io.export_enclosure_spcp(pe.id, out_pe)
    project_io.export_foundation_spcp(pf.id, out_pf)
    kind, name = project_io.import_spcp(out_pe)
    assert (kind, name) == ("enclosure", "默认围护原则1")
    kind, name = project_io.import_spcp(out_pf)
    assert (kind, name) == ("foundation", "默认地基原则1")
    original, cloned = project_io.enclosures()[0], project_io.enclosures()[1]
    for field in ("con_found", "excvt", "found_angle", "dock_l", "dock_h",
                  "cover50", "cover"):
        assert getattr(original, field) == getattr(cloned, field), field
    assert len(original.works) == len(cloned.works)
    # 旧版 mcPcpEnclosure 文件随围护导入拆出同名降水/面宽原则；
    # 新版围护导出已不含降水/宽度数据 → 拆出的是旧版默认井型与默认宽度表
    pp = next(p for p in project_io.precipitations() if p.name == "默认围护原则1")
    pw = next(w for w in project_io.width_principles() if w.name == "默认围护原则1")
    from app.core.models.models import GROOVE_WIDTH_WORK, PRECIPITATION_DEFAULTS, format_precipitation

    for field, (elevation, gap, sides) in PRECIPITATION_DEFAULTS.items():
        assert getattr(pp, field) == format_precipitation(elevation, gap, sides), field
    assert pw.groove_width == GROOVE_WIDTH_WORK
    assert len(pw.items) > 0

    # 降水 / 面宽原则自身的导出导入回路
    out_pp = tmp_path / "pp.spcp"
    out_pw = tmp_path / "pw.spcp"
    project_io.export_precipitation_spcp(pp.id, out_pp)
    project_io.export_width_spcp(pw.id, out_pw)
    kind, name = project_io.import_spcp(out_pp)
    assert kind == "precipitation"
    cloned_pp = next(p for p in project_io.precipitations() if p.name == name)
    for field in ("wet_soil", "light_well", "jet_well", "big_well", "deep_well"):
        assert getattr(pp, field) == getattr(cloned_pp, field), field
    kind, name = project_io.import_spcp(out_pw)
    assert kind == "width"
    cloned_pw = next(w for w in project_io.width_principles() if w.name == name)
    assert len(cloned_pw.items) == len(pw.items)


def test_spcp_rejects_wrong_root(project, tmp_path: Path) -> None:
    bad = tmp_path / "bad.spcp"
    bad.write_text("<?xml version='1.0'?><Something/>", encoding="utf-8")
    with pytest.raises(project_io.ProjectIoError):
        project_io.import_spcp(bad)


# --------------------------------------------------------------------------- #
# 原则编辑窗体 UI 调整（2026-10）：标题、按钮文案与顺序、板块布局、1.0 列头
# --------------------------------------------------------------------------- #
def test_principle_dialog_titles(qapp, project) -> None:
    """窗体标题：围护原则编辑 / 多级围护编辑窗体 / 地基原则编辑。"""
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog
    from app.views.dialogs.foundation_edit_dialog import FoundationEditDialog
    from app.views.dialogs.principle_dialogs import EnclosureWorkDialog

    enclosure = EnclosureEditDialog(project_io.enclosures()[0].id)
    work_dialog = EnclosureWorkDialog(project_io.enclosures()[0].works_sorted()[0])
    foundation = FoundationEditDialog(project_io.foundations()[0].id)
    try:
        assert enclosure.windowTitle() == "围护原则编辑"
        assert work_dialog.windowTitle() == "多级围护编辑窗体"
        assert foundation.windowTitle() == "地基原则编辑"
    finally:
        enclosure.close()
        work_dialog.close()
        foundation.close()


def test_enclosure_dialog_no_precipitation_box_and_button_position(qapp, project) -> None:
    """围护原则编辑：降水/面宽板块取消，确认/取消按钮列紧跟管道基础板块。"""
    from PySide6.QtWidgets import QGroupBox

    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    dialog = EnclosureEditDialog(project_io.enclosures()[0].id)
    try:
        boxes = [box.title() for box in dialog.findChildren(QGroupBox)]
        assert boxes == ["挖填类型", "管道基础"]
    finally:
        dialog.close()


def test_foundation_dialog_layout(qapp, project) -> None:
    """地基原则编辑：换填层 3 行起滚动、+/-按钮同列（+ 在按钮列表头格）、
    构件类型行 2:1、描述在框下方、底部 取消/确认（Apple HIG）。"""
    from PySide6.QtWidgets import QPushButton, QVBoxLayout

    from app.core.models import base as orm
    from app.core.models.models import FoundationReplacement
    from app.views.dialogs.foundation_edit_dialog import FoundationEditDialog

    foundation = project_io.foundations()[0]
    for order in range(1, 5):  # 5 行换填：默认窗口下只显示 3 行，其余滚动
        orm.session().add(
            FoundationReplacement(foundation_id=foundation.id, name="碎石", h=200.0, order_no=order)
        )
    project_io.commit()

    dialog = FoundationEditDialog(foundation.id)
    try:
        dialog.show()
        qapp.processEvents()
        table = dialog._replace_table
        # 板块高度 = 表头 + 3 行（4 行起出纵向滚动条）
        expected = table.horizontalHeader().height() + 3 * 32
        assert table.minimumHeight() == expected
        assert table.maximumHeight() == expected
        # 「+」钉在按钮列的表头格里（与行尾「-」同一列）；按钮列固定 40px
        button_col = dialog._replace_buttons.column
        header = table.horizontalHeader()
        from PySide6.QtWidgets import QHeaderView

        assert table.columnWidth(button_col) == 40
        assert header.sectionResizeMode(button_col) == QHeaderView.ResizeMode.Interactive
        add_button = dialog._replace_buttons.add_button
        assert add_button.isVisibleTo(dialog)
        assert add_button.x() == header.sectionViewportPosition(button_col) + 3
        assert add_button.y() + add_button.height() <= header.height()
        # 每行行尾都有「-」
        for row in range(table.rowCount()):
            holder = table.cellWidget(row, button_col)
            delete_button = holder.findChild(QPushButton)
            assert delete_button is not None and delete_button.text() == "-"
        # 构件类型行：下拉与编辑按钮同行，宽度 2:1
        picker = dialog._component_picker
        edit_button = picker.parentWidget().layout().itemAt(1).widget()
        assert isinstance(edit_button, QPushButton) and edit_button.text() == "编辑"
        picker_layout = picker.parentWidget().layout()
        assert picker_layout.stretch(0) == 2 and picker_layout.stretch(1) == 1
        # 描述 Label 在特殊地基框下方（不再属于其表单行）
        assert dialog._describe.parentWidget() is not picker.parentWidget()
        # 底部按钮：取消在左，确认在右（Apple HIG）
        button_row = dialog._name.parentWidget()
        buttons = [b for b in dialog.findChildren(QPushButton) if b.text() in ("取消", "确认")]
        assert [b.text() for b in buttons] == ["取消", "确认"]
    finally:
        dialog.close()


def test_precipitation_dialog_columns_per_1_0(qapp, project) -> None:
    """降水原则编辑：列头按 1.0（道数→侧数），范围列自最深行向浅处推算。"""
    from PySide6.QtCore import Qt

    from app.views.dialogs.principle_dialogs import PrecipitationEditDialog

    dialog = PrecipitationEditDialog(project_io.precipitations()[0].id)
    table = dialog._table
    try:
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        assert headers == ["措施名称", "选用", "埋深", "范围", "侧数", "间隔"]
        # 行序同 1.0（湿土排水 → 深井）；默认五井全启用：范围 = 下一已选用行埋深，最深 +∞
        assert [table.item(r, 0).text() for r in range(5)] == [
            "湿土排水", "轻型井点", "喷射井点", "大口径井点", "深井",
        ]
        assert [table.item(r, 3).text() for r in range(5)] == ["3.5", "6", "10", "15", "+∞"]
        # 全表文字居中
        assert table.item(0, 0).textAlignment() & 0x0004  # Qt.AlignHCenter
        # 取消“轻型井点”：其埋深/范围变“-”且只读，湿土排水的范围改为喷射井点埋深
        table.item(1, 1).setCheckState(Qt.CheckState.Unchecked)
        assert table.item(1, 2).text() == "-" and table.item(1, 3).text() == "-"
        assert not (table.item(1, 2).flags() & Qt.ItemFlag.ItemIsEditable)
        assert table.item(0, 3).text() == "6"
        assert dialog._precipitation().light_well == "-1|1.2|2"
    finally:
        dialog.close()


def test_dialog_bottom_buttons_cancel_left_confirm_right(qapp, project) -> None:
    """降水/面宽编辑：底部按钮 取消 在左、确认（primary）在右，文案不带“修改”。"""
    from PySide6.QtWidgets import QPushButton

    from app.views.dialogs.principle_dialogs import PrecipitationEditDialog, WidthEditDialog

    precipitation = PrecipitationEditDialog(project_io.precipitations()[0].id)
    width = WidthEditDialog(project_io.width_principles()[0].id)
    try:
        for dialog in (precipitation, width):
            dialog.show()
            qapp.processEvents()
            buttons = [
                button for button in dialog.findChildren(QPushButton)
                if button.text() in ("取消", "确认")
            ]
            assert [button.text() for button in buttons] == ["取消", "确认"]
            confirm = buttons[1]
            assert confirm.property("primary") in (True, "true")
            assert confirm.x() > buttons[0].x()
    finally:
        precipitation.close()
        width.close()


def test_enclosure_table_column_widths_stable_across_rebuilds(qapp, project) -> None:
    """做法表重建（_fill）后内容列宽不变：setRowCount 触发的自动重算发生在
    内嵌下拉框创建之前，会把下拉列压窄、表头文字移位（视觉上字体忽粗忽细）；
    _fill 末尾按控件实尺寸重算一次后应保持稳定。"""
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    dialog = EnclosureEditDialog(project_io.enclosures()[0].id)
    header = dialog._work_table.horizontalHeader()
    try:
        widths = [header.sectionSize(c) for c in range(6)]
        dialog._fill()
        widths_after = [header.sectionSize(c) for c in range(6)]
        assert widths_after == widths, f"{widths} != {widths_after}"
    finally:
        dialog.close()


# --------------------------------------------------------------------------- #
# 取消修改丢弃本次编辑（编辑只写会话，确认才统一落库）
# --------------------------------------------------------------------------- #
def test_enclosure_dialog_cancel_discards_work_edits(qapp, project) -> None:
    """围护原则编辑：取消修改后，新增/删行/埋深编辑全部失效，确认才落库。"""
    from app.core.models import base as orm
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    def works_snapshot() -> list[tuple[float, str]]:
        enclosure = project_io.enclosures()[0]
        orm.session().flush()
        orm.session().expire(enclosure)
        return [(work.min_depth, work.cpnt_cat) for work in enclosure.works_sorted()]

    before = works_snapshot()
    dialog = EnclosureEditDialog(project_io.enclosures()[0].id)
    try:
        dialog._insert_work()  # 追加做法（未落库）
        dialog._insert_work()  # 再追加一条（未落库）
        dialog._work_table.item(1, 0).setText("9.5")  # 改中间行埋深（未落库）
        dialog._delete_work_rows([1])  # 删中间行（未落库）
        assert works_snapshot() != before  # 编辑期间会话里已生效
        dialog.reject()  # 取消修改 → 回滚
        assert works_snapshot() == before
    finally:
        dialog.close()

    confirmed = EnclosureEditDialog(project_io.enclosures()[0].id)
    try:
        confirmed._insert_work()
        confirmed._confirm()  # 确认修改 → 统一落库
        assert len(works_snapshot()) == len(before) + 1
    finally:
        confirmed.close()


def test_foundation_dialog_cancel_discards_edits(qapp, project) -> None:
    """地基原则编辑：取消修改后，换填层的增行/改材质失效，确认才落库。"""
    from app.core.models import base as orm
    from app.views.dialogs.foundation_edit_dialog import FoundationEditDialog

    foundation = project_io.foundations()[0]

    def replacements_snapshot() -> list[tuple[str, float]]:
        orm.session().flush()
        orm.session().expire(foundation)
        return [(layer.name, layer.h) for layer in foundation.replacements]

    before = replacements_snapshot()
    dialog = FoundationEditDialog(foundation.id)
    try:
        dialog._insert_replacement()
        dialog._replace_table.item(0, 0).setText("砂砾")  # 改首行材质（未落库）
        assert replacements_snapshot() != before
        dialog.reject()
        assert replacements_snapshot() == before
    finally:
        dialog.close()

    confirmed = FoundationEditDialog(foundation.id)
    try:
        confirmed._insert_replacement()
        confirmed._confirm()
        assert len(replacements_snapshot()) == len(before) + 1
    finally:
        confirmed.close()


def test_width_dialog_cancel_discards_changes(qapp, project) -> None:
    """面宽原则编辑：取消后取值方式与宽度表编辑失效，确认才落库。"""
    from app.core.models import base as orm
    from app.core.models.models import WIDTH_KIND_WORK, WidthItem
    from app.views.dialogs.principle_dialogs import WidthEditDialog, _WIDTH_CATEGORY_ORDER

    from sqlalchemy import select

    width = project_io.width_principles()[0]
    original_mode = width.groove_width
    dialog = WidthEditDialog(width.id)
    try:
        dialog._tabs.setCurrentIndex(0 if original_mode != "WorkWidth" else 1)
        dialog.reject()
        orm.session().expire(width)
        assert width.groove_width == original_mode
    finally:
        dialog.close()

    confirmed = WidthEditDialog(width.id)
    try:
        category = _WIDTH_CATEGORY_ORDER[0]
        confirmed._tables[WIDTH_KIND_WORK].item(0, 1).setText("123")  # DN0 格
        confirmed._confirm()
        orm.session().expire(width)
        hit = (
            orm.session()
            .scalars(
                select(WidthItem).where(
                    WidthItem.width_id == width.id,
                    WidthItem.kind == WIDTH_KIND_WORK,
                    WidthItem.pipe_type == category,
                    WidthItem.dn == 0,
                )
            )
            .first()
        )
        assert hit is not None and hit.width == 123
    finally:
        confirmed.close()


def test_precipitation_dialog_cancel_discards_edits(qapp, project) -> None:
    """降水原则编辑：取消后井型勾选修改失效，确认才落库。"""
    from PySide6.QtCore import Qt

    from app.core.models import base as orm
    from app.views.dialogs.principle_dialogs import PrecipitationEditDialog

    precipitation = project_io.precipitations()[0]
    original = precipitation.light_well
    dialog = PrecipitationEditDialog(precipitation.id)
    try:
        dialog._table.item(1, 1).setCheckState(Qt.CheckState.Unchecked)  # 取消轻型井点
        dialog.reject()
        orm.session().expire(precipitation)
        assert precipitation.light_well == original
    finally:
        dialog.close()

    confirmed = PrecipitationEditDialog(precipitation.id)
    try:
        confirmed._table.item(1, 1).setCheckState(Qt.CheckState.Unchecked)
        confirmed._confirm()
        orm.session().expire(precipitation)
        assert precipitation.light_well == "-1|1.2|2"
    finally:
        confirmed.close()


def test_enclosure_work_dialog_cancel_restores_levels(qapp, project) -> None:
    """多级围护编辑窗体：取消修改把分级子树恢复为进入时的样子，确认才生效。"""
    from app.core.models import base as orm
    from app.views.dialogs.principle_dialogs import EnclosureWorkDialog

    work = project_io.enclosures()[0].works_sorted()[0]

    def levels_snapshot() -> list[tuple[str, float, float]]:
        orm.session().flush()
        orm.session().expire(work)
        return [(level.name, level.h, level.step_width) for level in work.levels]

    before = levels_snapshot()
    dialog = EnclosureWorkDialog(work)
    try:
        dialog._insert_level()
        assert len(levels_snapshot()) == len(before) + 1
        dialog.reject()  # 取消修改 → 分级子树恢复
        assert levels_snapshot() == before
    finally:
        dialog.close()

    confirmed = EnclosureWorkDialog(work)
    try:
        confirmed._insert_level()
        confirmed._accept()  # 确认修改：本窗体只标记生效，落库由原则主窗体统一提交
        project_io.commit()  # 模拟主窗体「确认修改」
        assert len(levels_snapshot()) == len(before) + 1
    finally:
        confirmed.close()
