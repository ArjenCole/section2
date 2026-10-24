"""撤销 / 重做测试（brackets2 同款快照式撤销栈）。

覆盖：服务层 UndoStack 的步数 / 上限 / 时间窗合并 / 内容去重语义，以及
project_io 集成（新增 / 删除 / 改名可撤销重做、恢复后文件重写、临时工程
撤销、关闭清栈）与树面板的位置选中。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.models import base as orm
from app.core.models.models import Element
from app.services import project_io, stn_format, undo as undo_stack
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm


@pytest.fixture(autouse=True)
def _clean_undo_stack():
    """每个用例前后都恢复空栈、清掉视图注入（服务是模块级单例）。"""
    undo_stack.clear()
    undo_stack.set_ui_provider(None)
    undo_stack.set_listener(None)
    yield
    undo_stack.clear()
    undo_stack.set_ui_provider(None)
    undo_stack.set_listener(None)


@pytest.fixture(autouse=True)
def _no_coalesce(monkeypatch):
    """测试里的连续操作都发生在时间窗内（时间戳甚至完全相同），关掉合并（合并语义单独测）。"""
    monkeypatch.setattr("app.services.undo._COALESCE_SECONDS", -1.0)


# --------------------------------------------------------------------------- #
# 服务层：步数 / 重做分支 / 内容去重
# --------------------------------------------------------------------------- #
def test_reset_is_baseline() -> None:
    undo_stack.reset({"v": 1})
    assert not undo_stack.can_undo()
    assert not undo_stack.can_redo()
    assert undo_stack.undo() is None
    assert undo_stack.redo() is None


def test_undo_redo_roundtrip() -> None:
    undo_stack.reset({"v": 1})
    undo_stack.record({"v": 2})
    undo_stack.record({"v": 3})
    assert undo_stack.can_undo()

    data, _ui = undo_stack.undo()
    assert data == {"v": 2}
    assert undo_stack.can_redo()

    data, _ui = undo_stack.redo()
    assert data == {"v": 3}
    assert not undo_stack.can_redo()

    data, _ui = undo_stack.undo()
    assert data == {"v": 2}


def test_new_change_clears_redo_branch() -> None:
    undo_stack.reset({"v": 1})
    undo_stack.record({"v": 2})
    undo_stack.undo()
    assert undo_stack.can_redo()
    undo_stack.record({"v": 3})
    assert not undo_stack.can_redo()
    data, _ui = undo_stack.undo()
    assert data == {"v": 1}


def test_unchanged_content_not_a_step() -> None:
    undo_stack.reset({"v": 1})
    undo_stack.record({"v": 1})  # 内容未变：不占步数
    assert not undo_stack.can_undo()


def test_saved_at_strip_keeps_dedup() -> None:
    # saved_at 是每次提交都变的 meta，不剔除会让"内容未变"判定永不成立
    undo_stack.reset({"saved_at": "t1", "v": 1})
    undo_stack.record({"saved_at": "t2", "v": 1})
    assert not undo_stack.can_undo()


def test_ui_state_carried_and_refreshed() -> None:
    undo_stack.set_ui_provider(lambda: {"sel": 5})
    undo_stack.reset({"v": 1})
    undo_stack.record({"v": 2})
    # 变更前快照的界面状态被刷新为当前所见（brackets2 同款），撤销时随快照返回
    data, ui = undo_stack.undo()
    assert data == {"v": 1}
    assert ui == {"sel": 5}
    _data, ui = undo_stack.redo()
    assert ui == {"sel": 5}


def test_ui_provider_exception_is_ignored() -> None:
    def _broken() -> dict:
        raise RuntimeError("界面状态不应阻断撤销流程")

    undo_stack.set_ui_provider(_broken)
    undo_stack.reset({"v": 1})
    undo_stack.record({"v": 2})
    _data, ui = undo_stack.undo()
    assert ui is None


def test_listener_notified_on_stack_change() -> None:
    calls: list[str] = []
    undo_stack.set_listener(lambda: calls.append("x"))
    undo_stack.reset({"v": 1})
    undo_stack.record({"v": 2})
    undo_stack.undo()
    undo_stack.clear()
    assert len(calls) == 4


# --------------------------------------------------------------------------- #
# 服务层：时间窗合并与双上限
# --------------------------------------------------------------------------- #
def test_records_within_window_merge(monkeypatch) -> None:
    clock = iter([100.0, 100.05])
    monkeypatch.setattr("app.services.undo.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("app.services.undo._COALESCE_SECONDS", 0.2)

    undo_stack.reset({"v": 0})
    undo_stack.record({"v": 1})  # t=100.00 追加
    undo_stack.record({"v": 2})  # t=100.05 窗口内 → 合并进栈顶
    data, _ui = undo_stack.undo()
    assert data == {"v": 0}  # 一步回到操作前，跳过中间态
    assert not undo_stack.can_undo()
    data, _ui = undo_stack.redo()
    assert data == {"v": 2}


def test_records_beyond_window_stay_separate(monkeypatch) -> None:
    clock = iter([100.0, 500.0])
    monkeypatch.setattr("app.services.undo.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("app.services.undo._COALESCE_SECONDS", 0.2)

    undo_stack.reset({"v": 0})
    undo_stack.record({"v": 1})
    undo_stack.record({"v": 2})  # 远超窗口 → 独立一步
    data, _ui = undo_stack.undo()
    assert data == {"v": 1}


def test_step_limit_trims_oldest(monkeypatch) -> None:
    monkeypatch.setattr("app.services.undo._MAX_UNDO_STEPS", 3)
    undo_stack.reset({"v": 0})
    for value in range(1, 6):
        undo_stack.record({"v": value})
    # 最多保留 3 步撤销：一路撤到底是最早保留的快照
    for expected in (4, 3, 2):
        data, _ui = undo_stack.undo()
        assert data == {"v": expected}
    assert not undo_stack.can_undo()


def test_byte_limit_trims_oldest(monkeypatch) -> None:
    monkeypatch.setattr("app.services.undo._MAX_BYTES", 10)  # 每个快照都不止 10 字节
    undo_stack.reset({"v": 0})
    for value in range(1, 4):
        undo_stack.record({"v": value})
    # 总字节超限：旧快照淘汰到只剩当前快照（当前快照始终保留）
    assert not undo_stack.can_undo()
    assert undo_stack.undo() is None


# --------------------------------------------------------------------------- #
# project_io 集成：修改可撤销、恢复后文件重写、路径不变
# --------------------------------------------------------------------------- #
def _unit_id() -> int:
    return project_io.units(project_io.segments()[0].id)[0].id


def _db_element_names() -> list[str]:
    return [
        element.name
        for element in orm.session().scalars(select(Element).order_by(Element.order_no, Element.id))
    ]


def _file_element_names(path) -> list[str]:
    document = stn_format.load_stn(path)
    names: list[str] = []
    for segment in document.data["segments"]:
        for unit in segment["units"]:
            names.extend(element["name"] for element in unit["elements"])
    return names


def test_add_element_undo_redo(project) -> None:
    path = project
    assert _db_element_names() == []

    unit_vm.create_element(_unit_id(), category=1, name="污水管 D600")
    assert _db_element_names() == ["污水管 D600"]
    assert undo_stack.can_undo()

    data, _ui = undo_stack.undo()
    project_io.restore_snapshot(data)
    assert _db_element_names() == []
    # 恢复后按"提交即落盘"语义重写文件，工程路径与锁不变
    assert _file_element_names(path) == []
    assert project_io.current_path() == path

    data, _ui = undo_stack.redo()
    project_io.restore_snapshot(data)
    assert _db_element_names() == ["污水管 D600"]
    assert _file_element_names(path) == ["污水管 D600"]


def test_delete_element_undo(project) -> None:
    unit = _unit_id()
    first = unit_vm.create_element(unit, category=1, name="构件一")
    unit_vm.create_element(unit, category=1, name="构件二")

    unit_vm.delete_element(first.id)
    assert _db_element_names() == ["构件二"]

    data, _ui = undo_stack.undo()
    project_io.restore_snapshot(data)
    assert _db_element_names() == ["构件一", "构件二"]


def test_rename_principle_undo(project) -> None:
    enclosure = project_io.enclosures()[0]
    unit_vm.create_element(_unit_id(), category=1, name="污水管", pe_name=enclosure.name)

    project_io.rename_enclosure(enclosure.id, "改名后的围护原则")
    assert project_io.enclosure_names() == ["改名后的围护原则"]

    data, _ui = undo_stack.undo()
    project_io.restore_snapshot(data)
    assert project_io.enclosure_names() == ["默认围护原则"]
    # 引用该原则的构件条目一并回到旧名
    element = orm.session().scalars(select(Element)).first()
    assert element.pe_name == "默认围护原则"


def test_no_change_commit_not_a_step(project) -> None:
    project_io.commit()  # 内容未变：只刷新界面状态，不占步数
    project_io.commit()
    assert not undo_stack.can_undo()


def test_transient_project_undo(tmp_path) -> None:
    project_io.new_project(NewProjectSpec(path=None, unit_names=["雨水工程"]))
    assert project_io.is_transient()
    unit_vm.create_element(_unit_id(), category=1, name="临时构件")
    assert undo_stack.can_undo()

    data, _ui = undo_stack.undo()
    project_io.restore_snapshot(data)
    assert _db_element_names() == []
    assert project_io.is_transient()  # 临时状态不因撤销改变


def test_close_project_clears_stack(project) -> None:
    unit_vm.create_element(_unit_id(), category=1, name="构件")
    assert undo_stack.can_undo()
    project_io.close_project()
    assert not undo_stack.can_undo()
    assert not undo_stack.can_redo()


# --------------------------------------------------------------------------- #
# 主窗体端到端：按钮可用态 + 树/表格联动
# --------------------------------------------------------------------------- #
def test_main_window_undo_redo_flow(qapp, project) -> None:
    from app.views.main_window import MainWindow

    window = MainWindow(str(project))
    qapp.processEvents()
    try:
        # 刚打开还不能撤销
        assert not window._act_undo.isEnabled()
        assert not window._act_redo.isEnabled()

        # 选中单位工程（联动工作台），新增一条构件
        unit_item = window._tree_panel._tree.topLevelItem(0).child(0).child(0)
        window._tree_panel._tree.setCurrentItem(unit_item)
        qapp.processEvents()
        unit_id = project_io.units(project_io.segments()[0].id)[0].id
        unit_vm.create_element(unit_id, category=1, name="污水管 D600")
        qapp.processEvents()
        table = window._unit_panel._element_table
        assert table.rowCount() == 1
        assert window._act_undo.isEnabled()
        assert not window._act_redo.isEnabled()

        # 撤销：树选中与工作台按快照恢复，构件行消失
        window._undo()
        qapp.processEvents()
        assert table.rowCount() == 0
        assert window._act_undo.isEnabled() is False
        assert window._act_redo.isEnabled()

        # 重做：构件行回来
        window._redo()
        qapp.processEvents()
        assert table.rowCount() == 1
        assert window._act_redo.isEnabled() is False
    finally:
        window.close()
        qapp.processEvents()


# --------------------------------------------------------------------------- #
# 树面板：位置选中（撤销快照跨重建稳定）
# --------------------------------------------------------------------------- #
def test_tree_panel_selection_path(qapp, project) -> None:
    from app.views.panels.tree_panel import TreePanel

    panel = TreePanel()
    panel.vm.load()
    root = panel._tree.topLevelItem(0)
    assert root is not None and root.childCount() >= 1

    segment = root.child(0)
    panel._tree.setCurrentItem(segment)
    assert panel.selection_path() == (0, None)

    if segment.childCount() >= 2:
        panel._tree.setCurrentItem(segment.child(1))
        assert panel.selection_path() == (0, 1)
        panel.select_by_path((0, 1))
        assert panel._tree._node_of(panel._tree.currentItem()).is_unit

    panel._tree.setCurrentItem(root)
    assert panel.selection_path() is None


def test_tree_panel_select_by_path_falls_back(qapp, project) -> None:
    from app.views.panels.tree_panel import TreePanel

    panel = TreePanel()
    panel.vm.load()
    root = panel._tree.topLevelItem(0)
    segment = root.child(0)

    # 单位工程序号越界回落到标段；标段序号越界不动选中
    assert panel.select_by_path((0, 99))
    assert panel._tree._node_of(panel._tree.currentItem()).is_segment
    assert not panel.select_by_path((99, None))
    assert not panel.select_by_path(None)
    assert not panel.select_by_path("bad")
