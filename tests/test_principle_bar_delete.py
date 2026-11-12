"""原则横条「删除原则」回归测试。

用户报告：在主页面上方原则横条右键「删除原则」时报错。
"""

import pytest

#: 四类原则：kind → (建第二条的工厂、读库的函数名)
_KINDS = {
    "enclosure": "create_enclosure",
    "foundation": "create_foundation",
    "precipitation": "create_precipitation",
    "width": "create_width",
}
_LISTERS = {
    "enclosure": "enclosures",
    "foundation": "foundations",
    "precipitation": "precipitations",
    "width": "width_principles",
}


def _make_second(kind: str):
    from app.services import project_io

    created = getattr(project_io, _KINDS[kind])()
    assert created is not None
    return created


def _names(kind: str) -> list[str]:
    from app.services import project_io

    return [item.name for item in getattr(project_io, _LISTERS[kind])()]


@pytest.mark.parametrize("kind", sorted(_KINDS))
def test_delete_principle_asks_and_deletes(qapp, project, monkeypatch, kind):
    from PySide6.QtWidgets import QMessageBox

    from app.views.panels import principle_bar as bar_module
    from app.views.panels.principle_bar import PrincipleBar

    created = _make_second(kind)
    names_before = _names(kind)
    assert created.name in names_before

    asked: list[str] = []
    monkeypatch.setattr(
        bar_module.FramelessMessageBox,
        "question",
        lambda _parent, _title, text, *_args, **_kwargs: (
            asked.append(text) or QMessageBox.StandardButton.Yes
        ),
    )
    errors: list[str] = []
    monkeypatch.setattr(
        bar_module.FramelessMessageBox,
        "information",
        lambda _parent, _title, text, *_args, **_kwargs: errors.append(text),
    )

    bar = PrincipleBar()
    bar.reload()
    bar._delete_principle(kind, created.name)

    assert asked, "应当弹出删除确认框"
    assert errors == []
    assert created.name not in _names(kind)
    assert len(_names(kind)) == len(names_before) - 1


def test_delete_principle_cancelled_keeps_it(qapp, project, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.views.panels import principle_bar as bar_module
    from app.views.panels.principle_bar import _KIND_ENCLOSURE, PrincipleBar

    created = _make_second(_KIND_ENCLOSURE)
    monkeypatch.setattr(
        bar_module.FramelessMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )

    bar = PrincipleBar()
    bar.reload()
    bar._delete_principle(_KIND_ENCLOSURE, created.name)

    assert created.name in _names(_KIND_ENCLOSURE)


def test_delete_principle_from_main_window_reloads_table(qapp, project, monkeypatch):
    """主页面原则横条删除原则：确认框可弹、构件引用并入替代原则、表格不报错。"""
    from PySide6.QtWidgets import QMessageBox

    from app.core.event_bus import bus
    from app.services import project_io
    from app.services.element_library import element_library
    from app.viewmodels.unit_vm import element_rows
    from app.views.main_window import MainWindow
    from app.views.panels import principle_bar as bar_module

    victim = _make_second("enclosure")
    monkeypatch.setattr(
        bar_module.FramelessMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )

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
        node = window._tree_panel.current_node
        row = element_rows(node.id)[0]
        project_io.commit()
        from app.viewmodels import unit_vm

        unit_vm.update_element(row.id, pe_name=victim.name)
        qapp.processEvents()
        assert element_rows(node.id)[0].pe_name == victim.name

        target = project_io.merge_target_enclosure(victim.name)
        window._principle_bar._delete_principle("enclosure", victim.name)
        qapp.processEvents()

        assert victim.name not in [item.name for item in project_io.enclosures()]
        # 引用并入替代原则，主表格跟着刷新
        assert element_rows(node.id)[0].pe_name == target
        assert window._unit_panel._element_table.rowCount() == 1
    finally:
        window.close()


def test_delete_enclosure_merges_left_right_references(qapp, project):
    """左右分设 / 合槽组员按名引用左右原则：删除时一并并入替代原则（不悬空）。"""
    from app.core.models.models import LR_PE_TEXT
    from app.services import project_io
    from app.viewmodels import unit_vm

    from conftest import first_unit_id, make_element

    victim = _make_second("enclosure")
    other = _make_second("enclosure")
    element_id = make_element("分设管", pe_name=victim.name)
    unit_vm.update_element(element_id, pe_name=LR_PE_TEXT)
    unit_vm.update_element(element_id, pe_left_name=victim.name, pe_right_name=other.name)
    project_io.commit()

    target = project_io.merge_target_enclosure(victim.name)
    assert project_io.delete_enclosure(victim.id, target) is None

    row = unit_vm.element_rows(first_unit_id())[0]
    assert row.pe_name == LR_PE_TEXT  # 占位名不变
    assert row.pe_left_name == target  # 悬空引用已并入
    assert row.pe_right_name == other.name  # 另一侧不受影响


def test_rename_enclosure_follows_left_right_references(qapp, project):
    """围护原则改名时，左右分设的两列引用一起改名。"""
    from app.core.models.models import LR_PE_TEXT
    from app.services import project_io
    from app.viewmodels import unit_vm

    from conftest import first_unit_id, make_element

    victim = _make_second("enclosure")
    other = _make_second("enclosure")
    element_id = make_element("分设改名管", pe_name=victim.name)
    unit_vm.update_element(element_id, pe_name=LR_PE_TEXT)
    unit_vm.update_element(element_id, pe_left_name=victim.name, pe_right_name=other.name)
    project_io.commit()

    project_io.rename_enclosure(victim.id, "改名后的围护原则")

    row = unit_vm.element_rows(first_unit_id())[0]
    assert row.pe_left_name == "改名后的围护原则"
    assert row.pe_right_name == other.name
