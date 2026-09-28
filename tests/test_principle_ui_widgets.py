"""原则 UI 控件回归测试（offscreen QApplication）。

覆盖：原则横条标签与单选切换、FormPE 复刻对话框的做法 Insert/Delete 规则、
坞塝回填双向映射、主表格 9 列结构与构件库插入。
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _closed_project():
    from app.services import project_io

    project_io.close_project()
    yield
    project_io.close_project()


@pytest.fixture()
def project(tmp_path):
    from app.services import project_io
    from app.services.project_io import NewProjectSpec

    path = tmp_path / "ui.stn2"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    return path


def test_principle_bar_labels_and_radio(qapp, project):
    from app.views.panels.principle_bar import PrincipleBar

    bar = PrincipleBar()
    bar.reload()
    assert bar.isVisibleTo(bar.parentWidget())
    # 标签布局 = 原则标签 + 常驻「+」按钮 + stretch
    assert bar._label_layout.count() - 2 == 1  # 默认 1 条围护原则
    bar._radio_foundation.setChecked(True)
    assert bar._label_layout.count() - 2 == 1  # 1 条地基原则
    bar.add_enclosure()
    bar._radio_enclosure.setChecked(True)
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
        # 主表格 9 列
        table = window._unit_panel._element_table
        assert table.columnCount() == 9
        # 选中单位工程后从构件库双击插入
        root = window._tree_panel._tree.topLevelItem(0)
        window._tree_panel._tree.setCurrentItem(root.child(0).child(0))
        qapp.processEvents()
        template = element_library().units_of("直埋混凝土管")[0].elements[0]
        window._insert_template(template)
        qapp.processEvents()
        assert table.rowCount() == 1
        rows = window._unit_panel._vm.element_rows_snapshot() if False else None
        from app.viewmodels.unit_vm import element_rows

        node = window._tree_panel.current_node
        row = element_rows(node.id)[0]
        assert row.pe_name and row.pf_name
        assert row.spec == "Ⅰ级混凝土管 Dn150"
    finally:
        window.close()
