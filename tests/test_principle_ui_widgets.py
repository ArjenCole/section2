"""原则 UI 控件回归测试（offscreen QApplication）。

覆盖：原则横条标签与单选切换、FormPE 复刻对话框的做法 Insert/Delete 规则、
坞塝回填双向映射、主表格 11 列结构与构件库插入（插到当前选中行的下一行）、
类型列只读与简称显示。
"""



def test_principle_bar_labels_and_radio(qapp, project):
    from app.views.panels.principle_bar import (
        _KIND_ENCLOSURE,
        _KIND_FOUNDATION,
        _KIND_PRECIPITATION,
        _KIND_WIDTH,
        PrincipleBar,
    )

    bar = PrincipleBar()
    bar.reload()
    assert bar.isVisibleTo(bar.parentWidget())
    # 标签布局 = 原则标签 + 常驻「+」按钮 + stretch
    assert bar._label_layout.count() - 2 == 1  # 默认 1 条围护原则
    bar._radios[_KIND_FOUNDATION].setChecked(True)
    assert bar._label_layout.count() - 2 == 1  # 1 条地基原则
    bar._radios[_KIND_PRECIPITATION].setChecked(True)
    assert bar._label_layout.count() - 2 == 1  # 1 条降水原则
    bar._radios[_KIND_WIDTH].setChecked(True)
    assert bar._label_layout.count() - 2 == 1  # 1 条面宽原则
    bar.add_enclosure()
    bar._radios[_KIND_ENCLOSURE].setChecked(True)
    assert bar._label_layout.count() - 2 == 2
    bar.add_precipitation()
    bar._radios[_KIND_PRECIPITATION].setChecked(True)
    assert bar._label_layout.count() - 2 == 2
    bar.add_width()
    bar._radios[_KIND_WIDTH].setChecked(True)
    assert bar._label_layout.count() - 2 == 2


def test_enclosure_dialog_insert_rules(qapp, project, monkeypatch):
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    dialog = EnclosureEditDialog(project_io_enclosure_id())
    dialog._insert_work()  # 追加：0 + 3.5
    dialog._insert_work()  # 追加：3.5 + 3.5
    dialog._insert_work(0)  # 插到最前：原第一行 = 原第二行 / 2
    works = dialog._enclosure().works_sorted()
    assert [work.min_depth for work in works] == [0.0, 1.75, 3.5, 7.0]
    # Delete 全选 → 提示“至少需要一种围护做法。”，且不删除
    shown: list[str] = []
    monkeypatch.setattr(
        "app.views.dialogs.enclosure_edit_dialog.FramelessMessageBox.information",
        lambda *_args, **_kwargs: shown.append("blocked"),
    )
    dialog._work_table.selectAll()
    dialog._delete_selected_works()
    assert shown == ["blocked"]
    assert [work.min_depth for work in dialog._enclosure().works_sorted()] == [0.0, 1.75, 3.5, 7.0]
    # 删除部分行（前两行）→ 剩余首行埋深归 0
    dialog._work_table.setCurrentCell(0, 0)
    from PySide6.QtCore import QItemSelectionModel

    model = dialog._work_table.selectionModel()
    model.select(dialog._work_table.model().index(0, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    model.select(dialog._work_table.model().index(1, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    dialog._delete_selected_works()
    assert [work.min_depth for work in dialog._enclosure().works_sorted()] == [0.0, 7.0]
    dialog.close()


def project_io_enclosure_id():
    from app.services import project_io

    return project_io.enclosures()[0].id


def test_enclosure_dialog_dock_mapping_roundtrip(qapp, project):
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    dialog = EnclosureEditDialog(project_io_enclosure_id())
    dialog._dock_material.setText("中粗砂")
    dialog._cover.setText("素土")
    dialog._dock_mode.setCurrentText("至管中心标高")
    dialog._confirm()
    enclosure = dialog._enclosure()
    assert (enclosure.dock_h, enclosure.cover50, enclosure.cover) == ("素土", "素土", "素土")
    reopened = EnclosureEditDialog(enclosure.id)
    assert reopened._dock_mode.currentText() == "至管中心标高"
    reopened.close()


def test_main_window_replica_layout(qapp, project):
    from app.core.event_bus import bus
    from app.services.element_library import element_library
    from app.views.main_window import MainWindow

    window = MainWindow()
    try:
        bus().project_opened.emit(str(project))
        window._tree_panel.vm.load()
        qapp.processEvents()
        # 原则横条可见，选中单位工程后工作区直达单位工程面板（无页签）
        assert window._principle_bar.isVisibleTo(window._principle_bar.parentWidget())
        # 主表格 11 列（含降水原则 / 工作面宽原则两列）
        table = window._unit_panel._element_table
        assert table.columnCount() == 11
        # 选中单位工程后从构件库双击插入
        root = window._tree_panel._tree.topLevelItem(0)
        window._tree_panel._tree.setCurrentItem(root.child(0).child(0))
        qapp.processEvents()
        template = element_library().units_of("直埋混凝土管")[0].elements[0]
        window._insert_template(template)
        qapp.processEvents()
        assert table.rowCount() == 1

        from app.viewmodels.unit_vm import element_rows

        node = window._tree_panel.current_node
        row = element_rows(node.id)[0]
        assert row.pe_name and row.pf_name
        assert row.spec == "Ⅰ级混凝土管 Dn150"
    finally:
        window.close()


def test_insert_template_after_selected_row(qapp, project):
    """构件库双击：新条目插到当前选中行的下一行并自动选中；选中末行则追加到末尾。"""
    from app.core.event_bus import bus
    from app.services import project_io
    from app.services.element_library import element_library
    from app.viewmodels import unit_vm
    from app.views.main_window import MainWindow

    unit = project_io.units(project_io.segments()[0].id)[0]
    first = unit_vm.insert_blank_element(unit.id)
    second = unit_vm.insert_blank_element(unit.id)
    template = element_library().units_of("直埋混凝土管")[0].elements[0]

    window = MainWindow()
    try:
        bus().project_opened.emit(str(project))
        window._tree_panel.vm.load()
        qapp.processEvents()
        root = window._tree_panel._tree.topLevelItem(0)
        window._tree_panel._tree.setCurrentItem(root.child(0).child(0))
        qapp.processEvents()
        panel = window._unit_panel
        assert panel._element_table.rowCount() == 2

        # 选中第一行 → 模板插到它后面、第二行之前，且新条目成为当前选中行
        panel._element_table.setCurrentCell(0, 0)
        panel.insert_template(template)
        qapp.processEvents()
        rows = unit_vm.element_rows(unit.id)
        assert len(rows) == 3
        assert [rows[0].id, rows[2].id] == [first.id, second.id]
        inserted = rows[1].id
        assert inserted not in (first.id, second.id)
        assert panel._current_element_id() == inserted

        # 选中末行 → “下一行”不存在，追加到末尾并选中
        panel._element_table.setCurrentCell(panel._element_table.rowCount() - 1, 0)
        panel.insert_template(template)
        qapp.processEvents()
        rows = unit_vm.element_rows(unit.id)
        assert len(rows) == 4
        assert [rows[0].id, rows[2].id] == [first.id, second.id]
        assert rows[-1].id not in (first.id, second.id, inserted)
        assert panel._current_element_id() == rows[-1].id
    finally:
        window.close()


def test_category_abbreviations():
    """类型列简称映射（仅显示层）：直埋→直，包封/箱涵/管廊→箱，顶管/牵引管→顶，构筑物→井。"""
    from app.core.models.models import (
        CATEGORY_BOX_CULVERT,
        CATEGORY_BURIED,
        CATEGORY_ENCASED,
        CATEGORY_GALLERY,
        CATEGORY_JACKING,
        CATEGORY_NONE,
        CATEGORY_PULLING,
        CATEGORY_STRUCTURE,
    )
    from app.views.panels.unit_panel import _category_abbr

    assert _category_abbr(CATEGORY_BURIED) == "直"
    assert _category_abbr(CATEGORY_ENCASED) == "箱"
    assert _category_abbr(CATEGORY_BOX_CULVERT) == "箱"
    assert _category_abbr(CATEGORY_GALLERY) == "箱"
    assert _category_abbr(CATEGORY_JACKING) == "顶"
    assert _category_abbr(CATEGORY_PULLING) == "顶"
    assert _category_abbr(CATEGORY_STRUCTURE) == "井"
    # 简称表之外的类别回退完整名（空类别显示空）
    assert _category_abbr(CATEGORY_NONE) == ""


def test_param_table_columns_and_no_unit_placeholder(qapp, project):
    """构件参数表：单位列居中且加宽（参数名列相应变窄）；构筑物名称 / 单位行的单位列
    显示 “-”；直埋管道显示三行图集参数与候选列（参数值由候选自动匹配、锁定）。"""
    from PySide6.QtCore import Qt

    from app.core.models.models import CATEGORY_STRUCTURE
    from app.services import project_io
    from app.viewmodels import unit_vm
    from app.views.panels.unit_panel import (
        _NO_UNIT_TEXT,
        _PARAM_NAME_WIDTH,
        _PARAM_UNIT_WIDTH,
        UnitPanel,
    )

    unit = project_io.units(project_io.segments()[0].id)[0]
    structure = unit_vm.create_element(unit.id, category=CATEGORY_STRUCTURE, name="检查井")
    buried = unit_vm.create_element(unit.id, category=1, name="排管")
    unit_vm.create_pipe(buried.id, mat="Ⅱ级混凝土管", dn=600, content="1")

    panel = UnitPanel()
    try:
        panel._show_unit(unit.id)
        qapp.processEvents()
        table = panel._param_table
        assert table.horizontalHeaderItem(1).text() == "单位"
        # 单位列 = 原 56 × 1.5，参数名列 = 原 150 × 0.6
        assert _PARAM_UNIT_WIDTH == 84 and _PARAM_NAME_WIDTH == 90
        assert table.columnWidth(0) == _PARAM_NAME_WIDTH
        assert table.columnWidth(1) == _PARAM_UNIT_WIDTH

        # 构筑物（第一行）：名称 / 单位两行的单位列由空值改为 “-”，居中只读
        panel._element_table.setCurrentCell(0, 0)
        qapp.processEvents()
        assert [table.item(row, 0).text() for row in range(table.rowCount())] == ["名称", "单位"]
        for row in (0, 1):
            cell = table.item(row, 1)
            assert cell.text() == _NO_UNIT_TEXT
            assert cell.textAlignment() == Qt.AlignmentFlag.AlignCenter
            assert not cell.flags() & Qt.ItemFlag.ItemIsEditable
        # 库里仍然是空单位（“-” 只是显示）
        assert [(param.key, param.unit) for param in unit_vm.param_rows(structure.id)] == [
            ("名称", ""),
            ("单位", ""),
        ]

        # 排管（直埋）：三行图集参数，单位列居中；有候选后参数值由候选自动匹配
        panel._element_table.setCurrentCell(1, 0)
        qapp.processEvents()
        assert [table.item(row, 0).text() for row in range(table.rowCount())] == [
            "工作面加宽",
            "垫层厚",
            "基础厚",
        ]
        # Dn600 Ⅱ级混凝土管 120° 砼基础：a=130、C1=130、C2=182（候选自动匹配写入）
        assert [table.item(row, 2).text() for row in range(table.rowCount())] == ["130", "130", "182"]
        for row in range(table.rowCount()):
            assert table.item(row, 1).text() == "mm"
            assert table.item(row, 1).textAlignment() == Qt.AlignmentFlag.AlignCenter
            # 参数名 / 单位锁定；有候选 → 参数值也锁定（改候选列才有效）
            assert not table.item(row, 0).flags() & Qt.ItemFlag.ItemIsEditable
            assert not table.item(row, 2).flags() & Qt.ItemFlag.ItemIsEditable
        # 直埋 + 有候选 → 参数值右侧追加候选参数列
        assert table.columnCount() > 3
    finally:
        panel.close()


def test_candidate_column_highlight_follows_match(qapp, project):
    """构件参数面板：当前匹配到的候选列被标出来；换基础角度后标注跟着换列。"""
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import PcpEnclosure
    from app.services import project_io
    from app.services.principle_edit import apply_enclosure_fields
    from app.viewmodels import unit_vm
    from app.viewmodels.unit_vm import selected_candidate_combo
    from app.views.panels.unit_panel import (
        _MATCH_BG_ROLE,
        _MATCH_BG_SAME,
        UnitPanel,
    )

    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, category=1, name="排管")
    assert element is not None
    unit_vm.create_pipe(element.id, mat="Ⅱ级混凝土管", dn=600, content="1")

    panel = UnitPanel()
    try:
        panel._show_unit(unit.id)
        qapp.processEvents()
        panel._element_table.setCurrentCell(0, 0)
        qapp.processEvents()
        table = panel._param_table

        def highlighted() -> list[int]:
            return [
                column
                for column in range(3, table.columnCount())
                if table.item(0, column) is not None
                and table.item(0, column).data(_MATCH_BG_ROLE)
            ]

        keys = [column.key for column in panel._candidate_columns]
        key, _level = selected_candidate_combo(element.id)
        assert key is not None and key in keys, "直埋混凝土管应显示候选列且已匹配到一组"

        selected = 3 + keys.index(key)
        assert highlighted() == [selected], "只有当前匹配的那一列被标底色"
        for row in range(3):
            cell = table.item(row, selected)
            assert cell is not None
            assert cell.data(_MATCH_BG_ROLE) == _MATCH_BG_SAME
            assert "当前选中" in cell.toolTip()

        # 换围护原则的基础角度 → 匹配换组，高亮列跟着走
        pe = orm.session().scalar(
            select(PcpEnclosure).where(
                PcpEnclosure.name == (element.main_pe_name or element.pe_name)
            )
        )
        assert pe is not None
        new_angle = 180 if int(pe.found_angle) != 180 else 90
        apply_enclosure_fields(pe.id, {"found_angle": new_angle})
        qapp.processEvents()
        qapp.processEvents()

        new_key, _new_level = selected_candidate_combo(element.id)
        new_keys = [column.key for column in panel._candidate_columns]
        assert new_key != key and new_key in new_keys
        assert highlighted() == [3 + new_keys.index(new_key)]
    finally:
        panel.close()


def test_blank_candidate_cell_can_be_filled_by_hand(qapp, project):
    """图集没有的组合（砼基础 150°）在面板上是空格，但可手填——填了就建候选行。"""
    from PySide6.QtCore import Qt

    from app.services import project_io
    from app.services.element_library import element_library
    from app.viewmodels import unit_vm
    from app.views.panels.unit_panel import _CANDIDATE_NEW_ROLE, UnitPanel

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None

    panel = UnitPanel()
    try:
        panel._show_unit(unit.id)
        qapp.processEvents()
        panel._element_table.setCurrentCell(0, 0)
        qapp.processEvents()
        table = panel._param_table
        keys = [column.key for column in panel._candidate_columns]
        assert "con150" in keys

        column = 3 + keys.index("con150")
        cell = table.item(2, column)  # 第三行 = 基础厚
        assert cell is not None and cell.text() == ""
        assert cell.flags() & Qt.ItemFlag.ItemIsEditable
        assert cell.data(_CANDIDATE_NEW_ROLE) == (element.id, "con150", "c2")

        cell.setText("300")
        qapp.processEvents()
        qapp.processEvents()
        rows = [
            candidate
            for candidate in unit_vm._element(element.id).atlas_candidates
            if candidate.con_found and int(candidate.angle) == 150
        ]
        assert len(rows) == 1 and rows[0].c2 == 300
    finally:
        panel.close()


def test_match_bg_paints_even_with_transparent_item_qss(qapp):
    """候选格底色必须由绘制代理自绘。

    回归：全局 QSS 的 ``QTableWidget::item { background-color: transparent }``
    会让 QStyleSheetStyle 接管单元格背景、忽略 Qt.BackgroundRole，导致
    ``item.setBackground()`` 静默无效（用户反馈"看不到颜色"）。
    """
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    from app.views.panels.unit_panel import (
        _MATCH_BG_ROLE,
        _MATCH_BG_SAME,
        _FocusCellDelegate,
        _candidate_selected_bg,
    )

    table = QTableWidget(1, 2)
    table.setItemDelegate(_FocusCellDelegate(table))
    table.setStyleSheet("QTableWidget::item { background-color: transparent; }")
    marked = QTableWidgetItem("120")
    marked.setData(_MATCH_BG_ROLE, _MATCH_BG_SAME)
    table.setItem(0, 1, marked)
    table.setItem(0, 0, QTableWidgetItem(""))
    table.resize(200, 60)
    table.show()
    try:
        qapp.processEvents()
        image = table.viewport().grab().toImage()
        marked_px = image.pixelColor(table.visualRect(table.model().index(0, 1)).center())
        plain_px = image.pixelColor(table.visualRect(table.model().index(0, 0)).center())
        assert marked_px.name() == _candidate_selected_bg().name()
        assert marked_px.name() != plain_px.name()
    finally:
        table.close()


def test_category_column_readonly(qapp, project):
    """主表格“类型”列不再内嵌下拉框：只读文本单元格，显示类别简称、tooltip 完整名。"""
    from PySide6.QtCore import Qt

    from app.core.event_bus import bus
    from app.core.models.models import category_name
    from app.services.element_library import element_library
    from app.views.main_window import MainWindow
    from app.views.panels.unit_panel import _COL_CATEGORY, _category_abbr

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

        table = window._unit_panel._element_table
        # 类型列不再有内嵌下拉框，单元格本身只读
        assert table.cellWidget(0, _COL_CATEGORY) is None
        cell = table.item(0, _COL_CATEGORY)
        assert cell is not None
        assert not cell.flags() & Qt.ItemFlag.ItemIsEditable
        from app.viewmodels.unit_vm import element_rows

        row = element_rows(window._tree_panel.current_node.id)[0]
        assert cell.text() == _category_abbr(row.category) == "直"
        assert cell.toolTip() == category_name(row.category) == "直埋管道"
    finally:
        window.close()
