"""项目结构树「删除节点」回归测试。

用户反馈：在左侧项目结构里删除标段 / 单位工程时报错。

根因：`ProjectViewModel.delete()` 里用了 `orm.session()`，但 `project_vm.py`
只导入了 `Segment` / `Unit`、没导入 `app.core.models.base as orm`，删除必抛
`NameError: name 'orm' is not defined`（原则节点走 `project_io.delete_*`，
所以只有标段 / 单位工程会炸）。

这里锁定：级联删除干净（构件 / 管道 / 合槽组 / 参数随单位工程一起消失）、
删除后选中父节点、取消不删、主窗体删掉当前单位工程后主面板切回汇总表。
"""

import pytest

from app.core.models import base as orm
from app.core.models.models import Element, Pipe, TrenchGroup, Unit
from app.viewmodels import unit_vm
from app.views.panels.tree_panel import TreePanel

from conftest import first_unit_id, make_element


@pytest.fixture()
def confirm_yes(monkeypatch):
    """删除确认框直接点「是」（tree_panel 在函数内导入消息框，只能打在类上）。"""
    from PySide6.QtWidgets import QMessageBox

    from app.views.widgets.frameless_dialog import FramelessMessageBox

    monkeypatch.setattr(
        FramelessMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )


@pytest.fixture()
def confirm_no(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from app.views.widgets.frameless_dialog import FramelessMessageBox

    monkeypatch.setattr(
        FramelessMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
    )


def _panel_with_tree(qapp) -> TreePanel:
    panel = TreePanel()
    panel.vm.load()
    qapp.processEvents()
    return panel


def _select(panel: TreePanel, item) -> None:
    panel._tree.setCurrentItem(item)


def _unit_item(panel: TreePanel, unit_index: int = 0):
    return panel._tree.topLevelItem(0).child(0).child(unit_index)


def test_delete_unit_removes_all_data_and_selects_segment(qapp, project, confirm_yes):
    """删除单位工程：构件 / 管道 / 合槽组一并级联删除，选中回到所属标段。"""
    from sqlalchemy import select

    unit_id = first_unit_id()
    first = make_element("直埋管1")
    second = make_element("直埋管2")
    group, error = unit_vm.create_trench_group([first, second])
    assert error is None and group is not None
    group_id = group.id
    assert orm.session().scalars(select(Pipe)).all()

    panel = _panel_with_tree(qapp)
    segment_id = panel._tree._node_of(panel._tree.topLevelItem(0).child(0)).id
    _select(panel, _unit_item(panel))
    panel._delete()
    qapp.processEvents()

    # 库：单位工程与下属数据全部消失
    assert orm.session().get(Unit, unit_id) is None
    assert orm.session().scalars(select(Element)).all() == []
    assert orm.session().scalars(select(Pipe)).all() == []
    assert orm.session().get(TrenchGroup, group_id) is None
    # 树：该标段下已无单位工程
    root = panel._tree.topLevelItem(0)
    assert root.child(0).childCount() == 0
    # 选中回到父节点（标段），不是跳回工程根
    assert panel.current_node is not None
    assert panel.current_node.kind == "segment"
    assert panel.current_node.id == segment_id


def test_delete_segment_removes_units_and_selects_project(qapp, project, confirm_yes):
    """删除标段：其下单位工程与构件一并消失，选中回到工程根。"""
    from sqlalchemy import select

    from app.services import project_io

    unit_id = first_unit_id()
    make_element("标段内管")

    panel = _panel_with_tree(qapp)
    segment_id = panel._tree._node_of(panel._tree.topLevelItem(0).child(0)).id
    panel.vm.add_unit(segment_id, "第二单位工程")
    qapp.processEvents()
    assert len(project_io.units(segment_id)) == 2

    _select(panel, panel._tree.topLevelItem(0).child(0))
    panel._delete()
    qapp.processEvents()

    assert orm.session().get(Unit, unit_id) is None
    assert orm.session().scalars(select(Element)).all() == []
    assert project_io.segments() == []
    assert panel._tree.topLevelItem(0).childCount() == 0
    assert panel.current_node is not None and panel.current_node.kind == "project"


def test_delete_unit_cancelled_keeps_everything(qapp, project, confirm_no):
    """确认框点「否」：不删数据、树不变。"""
    unit_id = first_unit_id()
    make_element("不该被删的管")

    panel = _panel_with_tree(qapp)
    _select(panel, _unit_item(panel))
    panel._delete()
    qapp.processEvents()

    assert orm.session().get(Unit, unit_id) is not None
    assert panel._tree.topLevelItem(0).child(0).childCount() == 1
    assert panel.current_node is not None and panel.current_node.kind == "unit"


def test_delete_unit_is_undoable(qapp, project, confirm_yes, monkeypatch):
    """删除单位工程走 project_io.commit()，应能撤销恢复（含下属构件）。"""
    from sqlalchemy import select

    from app.services import project_io, undo as undo_stack

    # 关掉时间窗合并（与 test_undo 同款）：否则“建构件 + 删单位工程”两次
    # commit 发生在同一秒内会被并成一步，撤销一次就回到建构件之前
    monkeypatch.setattr("app.services.undo._COALESCE_SECONDS", -1.0)
    unit_id = first_unit_id()
    make_element("可撤销的管")
    panel = _panel_with_tree(qapp)
    _select(panel, _unit_item(panel))
    assert undo_stack.can_undo()  # 建构件已经产生撤销步骤

    panel._delete()
    qapp.processEvents()
    assert orm.session().get(Unit, unit_id) is None
    assert undo_stack.can_undo()

    data, _ui = undo_stack.undo()
    assert data is not None
    project_io.restore_snapshot(data)
    assert orm.session().get(Unit, unit_id) is not None
    assert [element.name for element in orm.session().scalars(select(Element))] == ["可撤销的管"]
    undo_stack.clear()


def test_delete_from_main_window_switches_to_summary(qapp, project, confirm_yes):
    """主窗体里删掉当前选中的单位工程：不报错，主面板切回汇总表 tab。"""
    from app.core.event_bus import bus
    from app.services.element_library import element_library
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
        assert window._unit_panel._element_table.rowCount() == 1

        window._tree_panel._delete()
        qapp.processEvents()

        assert window._tree_panel._tree.topLevelItem(0).child(0).childCount() == 0
        # 非子节点（标段）：费用汇总表 / 综合单价汇总表
        bar = window._main_tabs.tabBar()
        assert bar.isTabVisible(3) and bar.isTabVisible(4)
        assert not bar.isTabVisible(1) and not bar.isTabVisible(2)
        assert window._main_tabs.currentIndex() == 3
    finally:
        window.close()
