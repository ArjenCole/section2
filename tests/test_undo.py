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


def test_patch_top_ui_after_view_settles() -> None:
    """界面落定后回填栈顶快照：重做恢复的是用户实际看到的选中。"""
    undo_stack.reset({"v": 0})
    undo_stack.record({"v": 1})
    undo_stack.record({"v": 2})  # record 时视图未刷新，栈顶 ui 还是提交前的
    undo_stack.patch_top_ui({"cell": (2, 2)})
    data, ui = undo_stack.undo()
    assert data == {"v": 1}
    assert ui is None  # 变更前快照未被 patch 触碰
    _data, ui = undo_stack.redo()
    assert ui == {"cell": (2, 2)}  # 栈顶是回填后的真实视图

    # 撤销到中间快照后回填：落在当前指向的快照上（而不是栈顶）
    undo_stack.undo()  # pos=0
    undo_stack.patch_top_ui({"cell": (1, 1)})  # 回填 S0（当前快照）
    _data, ui = undo_stack.redo()
    assert ui == {"cell": (2, 2)}  # S1 不受影响
    _data, ui = undo_stack.undo()
    assert ui == {"cell": (1, 1)}  # S0 是回填后的内容

    # 空栈时回填是空操作
    undo_stack.clear()
    undo_stack.patch_top_ui({"cell": (0, 0)})  # 不应抛异常


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


def test_undo_redo_selection_follows_snapshot(qapp, project) -> None:
    """撤销 / 重做后主表格选中行不得错乱（回归：重做后选中跳到别的构件）。

    两个病根（均已修复）：
    1. commit 时刻界面还没按新数据刷新，栈顶快照的选中行指向已删除的行，
       重做恢复时越界被跳过；现在界面落定后回填栈顶快照（patch_top_ui），
       重做恢复的是用户当时真实看到的选中；
    2. 重建后的库按位置重新编号构件 id，重载按旧 id 恢复选中会撞到别的
       构件（或回落第 0 行）；现在重建后禁用按 id 恢复（mark_ids_stale）。
    """
    from app.views.main_window import MainWindow
    from app.views.panels.unit_panel import _COL_NAME

    window = MainWindow(str(project))
    qapp.processEvents()
    try:
        unit_item = window._tree_panel._tree.topLevelItem(0).child(0).child(0)
        window._tree_panel._tree.setCurrentItem(unit_item)
        qapp.processEvents()
        unit_id = project_io.units(project_io.segments()[0].id)[0].id
        for name in ("构件A", "构件B", "构件C", "构件D"):
            unit_vm.create_element(unit_id, category=1, name=name)
        qapp.processEvents()
        table = window._unit_panel._element_table
        panel = window._unit_panel

        def _current_name() -> str | None:
            row = table.currentRow()
            return table.item(row, _COL_NAME).text() if row >= 0 else None

        def _detail_matches_selection() -> bool:
            element_id = panel._element_id_at(table.currentRow())
            return panel._current_detail_id == element_id

        def _check_invariants(expected: str) -> None:
            assert _current_name() == expected
            assert _detail_matches_selection()

        # 选中 B（第 1 行）并删除：删除行后选中收敛到第 0 行（软件既有行为），
        # 栈顶快照在界面落定后回填的正是这个位置
        table.setCurrentCell(1, _COL_NAME)
        unit_vm.delete_element(panel._element_id_at(1))
        qapp.processEvents()
        assert table.rowCount() == 3
        _check_invariants("构件A")

        # 撤销：B 恢复，选中落回操作前的位置（B）
        window._undo()
        qapp.processEvents()
        assert table.rowCount() == 4
        _check_invariants("构件B")

        # 重做（回归点）：B 再删。选中按相邻快照对比落在被删位置（现在是 C），
        # 不受视图 / 浏览影响
        window._redo()
        qapp.processEvents()
        assert table.rowCount() == 3
        _check_invariants("构件C")

        # 撤销 / 重做再走一轮，选中始终确定
        window._undo()
        qapp.processEvents()
        _check_invariants("构件B")
        window._redo()
        qapp.processEvents()
        _check_invariants("构件C")
    finally:
        window.close()
        qapp.processEvents()


def test_redo_selects_each_step_modified_element(qapp, project) -> None:
    """回归（用户报告）：连续添加 → 连续撤销 → 连续重做，每一步都只选中
    该步骤修改的那一条构件。

    此前新增操作不选中新行，快照视图停在第一行——重做时选中
    完全不动，每步重做出来的条目没有被选中。现在新增（构件库插入/
    AI 共用 create_element）广播 element_focused，面板选中新行，快照视图
    跟着每一步走。
    """
    from app.services.element_library import element_library
    from app.views.main_window import MainWindow

    window = MainWindow(str(project))
    qapp.processEvents()
    try:
        unit_item = window._tree_panel._tree.topLevelItem(0).child(0).child(0)
        window._tree_panel._tree.setCurrentItem(unit_item)
        qapp.processEvents()
        panel = window._unit_panel
        table = panel._element_table

        # 连续插入 3 条（构件库双击路径）：每一步选中新条目
        template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
        for _ in range(3):
            panel.insert_template(template)
            qapp.processEvents()
            qapp.processEvents()
        assert table.rowCount() == 3
        assert table.currentRow() == 2  # 最新一条被选中

        # 连续撤销：选中逐步回退，每一步落在上一步新增的那条上
        window._undo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 2
        assert table.currentRow() == 1
        window._undo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 1
        assert table.currentRow() == 0
        window._undo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 0
        assert table.currentRow() == -1

        # 连续重做（回归点）：每一步只选中该步重做出来的那一条
        for row in range(3):
            window._redo()
            qapp.processEvents()
            qapp.processEvents()
            assert table.rowCount() == row + 1
            assert table.currentRow() == row
    finally:
        window.close()
        qapp.processEvents()


def test_last_focus_diff_across_snapshots() -> None:
    """撤销 / 重做的焦点由相邻快照对比得出：每一步落在该步修改的条目上。"""

    def _data(names: list[str]) -> dict:
        return {
            "segments": [
                {
                    "name": "标段",
                    "units": [
                        {"name": "雨水工程", "elements": [{"name": n} for n in names]}
                    ],
                }
            ]
        }

    undo_stack.reset(_data([]))
    undo_stack.record(_data(["A"]))
    undo_stack.record(_data(["A", "B"]))
    undo_stack.record(_data(["A", "B", "C"]))

    # 撤销：目标快照相对来路少一条 → 收敛到被删位置
    undo_stack.undo()
    assert undo_stack.last_focus() == ((0, 0), 1)
    undo_stack.undo()
    assert undo_stack.last_focus() == ((0, 0), 0)
    undo_stack.undo()  # 基线：清单清空
    assert undo_stack.last_focus() == ((0, 0), None)

    # 重做：目标快照相对来路多一条 → 正是重新出现的那条
    undo_stack.redo()
    assert undo_stack.last_focus() == ((0, 0), 0)
    undo_stack.redo()
    assert undo_stack.last_focus() == ((0, 0), 1)
    undo_stack.redo()
    assert undo_stack.last_focus() == ((0, 0), 2)

    # 同长（改值步骤）：第一个差异行
    undo_stack.record(_data(["A", "B改", "C"]))
    undo_stack.undo()
    assert undo_stack.last_focus() == ((0, 0), 1)

    # 原则 / 单价类步骤（构件清单无差异）：无焦点，选中由快照视图兜底
    undo_stack.record({"segments": [], "prices": [{"key": "k", "value": 1.0}]})
    undo_stack.undo()
    assert undo_stack.last_focus() is None

    # 新提交清掉过期的焦点
    undo_stack.record(_data(["A", "B改", "C"]))
    assert undo_stack.last_focus() is None


def test_redo_after_browsing_selects_step_entry(qapp, project) -> None:
    """回归（用户报告）：重做的选中由数据对比决定，不受操作间浏览影响。

    插入 T1、T2 后浏览到第 0 行再插入 T3：下一步快照携带的视图是浏览后的
    第 0 行——重做若按视图恢复，T2 那一步会错选 T1。按数据对比，每一步
    重做只选中该步插入的那条。
    """
    from app.views.main_window import MainWindow
    from app.views.panels.unit_panel import _COL_NAME

    window = MainWindow(str(project))
    qapp.processEvents()
    try:
        unit_item = window._tree_panel._tree.topLevelItem(0).child(0).child(0)
        window._tree_panel._tree.setCurrentItem(unit_item)
        qapp.processEvents()
        panel = window._unit_panel
        table = panel._element_table
        unit_id = project_io.units(project_io.segments()[0].id)[0].id
        for name in ("T1", "T2"):
            unit_vm.create_element(unit_id, category=1, name=name)
        qapp.processEvents()
        qapp.processEvents()

        # 浏览到第 0 行（视图选中与步骤脱节），再插入 T3
        table.setCurrentCell(0, _COL_NAME)
        unit_vm.create_element(unit_id, category=1, name="T3")
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 3
        assert [table.item(r, _COL_NAME).text() for r in range(3)] == ["T1", "T2", "T3"]

        window._undo()
        qapp.processEvents()
        qapp.processEvents()
        window._undo()
        qapp.processEvents()
        qapp.processEvents()
        window._undo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 0

        # 重做两步：无论中途浏览到哪，每一步都只选中该步插入的那条
        window._redo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 1
        assert table.currentRow() == 0
        assert table.item(0, _COL_NAME).text() == "T1"
        window._redo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 2
        assert table.currentRow() == 1
        assert table.item(1, _COL_NAME).text() == "T2"
    finally:
        window.close()
        qapp.processEvents()


def test_redo_with_ctrl_key_does_not_accumulate_selection(qapp, project) -> None:
    """回归（用户报告）：Ctrl+Z / Ctrl+Y 连续撤销重做，选中不得累积。

    撤销 / 重做在按键处理过程中同步执行，Ctrl 修饰键还按着，QAbstractItemView
    的 selectionCommand 会把 setCurrentCell 推断成"追加选择"——重做的每一步都
    把新行加进选区，最终整表被持续选中（用户实测 6 条同时被选中）。恢复选中
    必须用显式 ClearAndSelect 命令，不受修饰键影响。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from app.views.main_window import MainWindow

    window = MainWindow(str(project))
    window.show()
    qapp.processEvents()
    try:
        unit_item = window._tree_panel._tree.topLevelItem(0).child(0).child(0)
        window._tree_panel._tree.setCurrentItem(unit_item)
        qapp.processEvents()
        panel = window._unit_panel
        table = panel._element_table

        def _selected_rows() -> list[int]:
            return sorted(i.row() for i in table.selectionModel().selectedRows())

        from app.services.element_library import element_library

        template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
        for _ in range(3):
            panel.insert_template(template)
            qapp.processEvents()
            qapp.processEvents()
        assert table.rowCount() == 3

        # 连续撤销（真实按键，Ctrl 修饰键在处理过程中处于按下状态）
        for _ in range(4):
            QTest.keyClick(window, Qt.Key_Z, Qt.KeyboardModifier.ControlModifier)
            qapp.processEvents()
            qapp.processEvents()
        assert table.rowCount() == 0
        assert _selected_rows() == []

        # 连续重做（回归点）：每一步只有该步重做出来的那一条被选中
        for row in range(3):
            QTest.keyClick(window, Qt.Key_Y, Qt.KeyboardModifier.ControlModifier)
            qapp.processEvents()
            qapp.processEvents()
            assert table.rowCount() == row + 1
            assert table.currentRow() == row
            assert _selected_rows() == [row]
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
