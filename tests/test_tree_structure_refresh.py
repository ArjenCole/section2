"""项目结构树「外部（AI / MCP 工具）改结构后不刷新」回归测试。

用户反馈：用 AI 助手新建标段、在标段下新建单位工程并插入构件后，费用汇总表
能看到新标段 / 单位工程，左侧项目结构树却看不到新节点，必须重开工程才出现。

根因：树面板只在 ``ProjectViewModel.load()`` 时重建控件，而界面上的增删改
（``ProjectViewModel._after_change``）是自己 load 一次；AI / MCP 工具
（``app.agent.tools.tree``）直接写库后只广播 ``tree_structure_changed``，
树面板从没订阅这个信号，所以只有订阅了的费用汇总表 / 单位工程面板会刷新。

这里锁定：工具层（含 AI 走的那条路径）增删改名标段 / 单位工程后，树立即
跟上，且保持当前选中不跳；界面自身的操作仍然只重建一次。
"""

from __future__ import annotations

import pytest

from app.agent.tools import tree as tree_tools
from app.core.event_bus import bus
from app.services import project_io
from app.views.panels.tree_panel import TreePanel

from conftest import first_unit_id


@pytest.fixture()
def panel(qapp):
    """装好一个单标段 / 单单位工程工程的树面板。"""
    tree = TreePanel()
    tree.vm.load()
    qapp.processEvents()
    yield tree
    tree.close()


def _segment_names(panel: TreePanel) -> list[str]:
    root = panel._tree.topLevelItem(0)
    return [root.child(index).text(0) for index in range(root.childCount())]


def _unit_names(panel: TreePanel, segment_index: int = 0) -> list[str]:
    segment = panel._tree.topLevelItem(0).child(segment_index)
    return [segment.child(index).text(0) for index in range(segment.childCount())]


def test_agent_add_segment_shows_up_in_tree(qapp, project, panel) -> None:
    """AI 新增标段：树里立刻多出一行（原先要重开工程才看得到）。"""
    assert len(_segment_names(panel)) == 1

    result = tree_tools.tool_add_segment({"name": "AI 新增标段"})
    assert result["ok"] is True
    qapp.processEvents()

    assert _segment_names(panel) == ["新建标段", "AI 新增标段"]


def test_agent_add_unit_shows_up_in_tree(qapp, project, panel) -> None:
    """AI 在标段下新增单位工程：树里立刻挂在对应标段下。"""
    segment_id = project_io.segments()[0].id
    assert _unit_names(panel) == ["雨水工程"]

    result = tree_tools.tool_add_unit({"segment_id": segment_id, "name": "AI 新增单位工程"})
    assert result["ok"] is True
    qapp.processEvents()

    assert _unit_names(panel) == ["雨水工程", "AI 新增单位工程"]


def test_agent_rename_node_updates_tree_label(qapp, project, panel) -> None:
    """AI 重命名标段：树节点文字立刻跟着变。"""
    segment_id = project_io.segments()[0].id
    tree_tools.tool_rename_node({"kind": "segment", "id": segment_id, "name": "改名后的标段"})
    qapp.processEvents()

    assert _segment_names(panel) == ["改名后的标段"]


def test_agent_delete_node_removes_tree_node(qapp, project, panel) -> None:
    """AI 删除单位工程：树里对应行立刻消失，选中退回所属标段。"""
    unit_id = first_unit_id()
    segment_id = project_io.segments()[0].id
    # 先把选中落到将被删除的单位工程上
    panel._tree.setCurrentItem(panel._tree.topLevelItem(0).child(0).child(0))
    qapp.processEvents()
    assert panel.current_node is not None and panel.current_node.is_unit

    tree_tools.tool_delete_node({"kind": "unit", "id": unit_id})
    qapp.processEvents()

    assert _unit_names(panel) == []
    assert panel.current_node is not None
    assert panel.current_node.is_segment and panel.current_node.id == segment_id


def test_agent_build_flow_segment_unit_element_visible_in_tree(qapp, project, panel) -> None:
    """复现用户场景：新建标段 → 新单位工程 → 插构件，树与汇总表一致。"""
    from app.viewmodels import unit_vm

    segment = tree_tools.tool_add_segment({"name": "二标段"})["data"]
    unit = tree_tools.tool_add_unit(
        {"segment_id": segment["segment_id"], "name": "二标段雨水"}
    )["data"]
    unit_vm.create_element(
        unit["unit_id"],
        category=1,
        name="AI 插入的管",
        depth="3",
        amount="120",
        pipes=[("Ⅱ级混凝土管", 600, "1")],
        seed_atlas_defaults=True,
    )
    qapp.processEvents()

    assert _segment_names(panel) == ["新建标段", "二标段"]
    assert _unit_names(panel, 1) == ["二标段雨水"]
    # 单位工程里确实有构件（树只显示结构，构件在右侧表格）
    assert len(unit_vm.element_rows(unit["unit_id"])) == 1


def test_ui_change_reloads_tree_once(qapp, project, panel) -> None:
    """界面自身的新增标段仍只重建一次树（不因订阅广播而重复重建）。"""
    calls: list[object] = []
    original = panel._on_tree_loaded

    def counting(root) -> None:
        calls.append(root)
        original(root)

    panel._vm.tree_loaded.disconnect()
    panel._vm.tree_loaded.connect(counting)

    panel.vm.add_segment("界面新增标段")
    qapp.processEvents()

    assert len(calls) == 1
    assert _segment_names(panel) == ["新建标段", "界面新增标段"]


def test_tree_keeps_selection_after_external_change(qapp, project, panel) -> None:
    """外部改结构后重建树：当前选中（单位工程）不跳回工程根。"""
    unit_id = first_unit_id()
    panel._tree.setCurrentItem(panel._tree.topLevelItem(0).child(0).child(0))
    qapp.processEvents()

    tree_tools.tool_add_segment({"name": "另一个标段"})
    qapp.processEvents()

    assert panel.current_node is not None
    assert panel.current_node.is_unit and panel.current_node.id == unit_id


def test_structure_signal_also_drives_tree_without_vm_call(qapp, project, panel) -> None:
    """任何一处直接广播 tree_structure_changed（MCP 适配层）也要刷新树。"""
    from app.core.models import base as orm
    from app.core.models.models import Segment

    orm.session().add(Segment(name="MCP 标段", order_no=project_io.next_order_no(Segment)))
    project_io.commit()
    bus().tree_structure_changed.emit()
    qapp.processEvents()

    assert "MCP 标段" in _segment_names(panel)


def test_principle_change_broadcast_does_not_rebuild_tree(qapp, project, panel) -> None:
    """原则增删改名也发 tree_structure_changed：结构没变就不重建树。

    重建会 expandAll 并重新广播 node_selected（主面板 tab 跳回第一个），
    所以这条广播必须按结构指纹过滤。
    """
    rebuilds: list[object] = []
    original = panel._on_tree_loaded

    def counting(root) -> None:
        rebuilds.append(root)
        original(root)

    panel._vm.tree_loaded.disconnect()
    panel._vm.tree_loaded.connect(counting)

    bus().tree_structure_changed.emit()  # 原则增删改名时就是这么发的
    qapp.processEvents()

    assert rebuilds == []


def test_main_window_tree_and_summary_agree_after_ai_build(qapp, project) -> None:
    """主窗体集成：AI 建标段 / 单位工程 / 插构件后，树与费用汇总表一致。"""
    from app.viewmodels import unit_vm
    from app.views.main_window import MainWindow

    window = MainWindow()
    window.show()
    try:
        bus().project_opened.emit(str(project))
        window._tree_panel.vm.load()
        qapp.processEvents()
        tree = window._tree_panel._tree
        tree.setCurrentItem(tree.topLevelItem(0))  # 选中工程根：费用汇总表可见
        qapp.processEvents()

        def cost_names() -> list[str]:
            table = window._summary_panel._cost_table
            return [table.item(row, 1).text() for row in range(table.rowCount())]

        assert cost_names() == ["新建项目", "新建标段", "雨水工程"]

        segment = tree_tools.tool_add_segment({"name": "AI 标段"})["data"]
        unit = tree_tools.tool_add_unit(
            {"segment_id": segment["segment_id"], "name": "AI 单位工程"}
        )["data"]
        unit_vm.create_element(
            unit["unit_id"],
            category=1,
            name="AI 插入的管",
            depth="3",
            amount="120",
            pipes=[("Ⅱ级混凝土管", 600, "1")],
            seed_atlas_defaults=True,
        )
        qapp.processEvents()

        # 费用汇总表：新标段 / 单位工程各一行
        assert cost_names() == ["新建项目", "新建标段", "雨水工程", "AI 标段", "AI 单位工程"]
        # 项目结构树：同一批节点也必须在
        root = tree.topLevelItem(0)
        assert [root.child(index).text(0) for index in range(root.childCount())] == [
            "新建标段",
            "AI 标段",
        ]
        assert root.child(1).child(0).text(0) == "AI 单位工程"
    finally:
        window.close()
        qapp.processEvents()
