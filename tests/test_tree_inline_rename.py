"""项目结构树「选中节点再单击直接重命名」回归测试。

1.0 项目结构树用 WinForms ``TreeView.LabelEdit``：节点已选中时再点一下即
进入行内编辑，回车 / 点击别处提交，Esc 取消。section2 原先只能走右键
菜单弹对话框改名，这里锁定新增的直接重命名交互：

* 已选中节点再次单击 → 行内 QLineEdit，文字全选；
* 回车 / 点击别处 → 写库并重建树；
* Esc / 空名称 → 保持原名称；
* 工程根节点也可改名，改名即修改项目名称；展开箭头不触发编辑；F2 仍可进入编辑。
"""

import app  # noqa: F401  # ICU 预加载必须先于 PySide6

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QLineEdit, QWidget

from app.services import project_io
from app.views.panels.tree_panel import TreePanel


def _panel(qapp) -> TreePanel:
    panel = TreePanel()
    panel.resize(320, 480)
    panel.show()
    # 测试里缩短“单击 → 进入编辑”的双击判定等待，避免每个用例多等 400ms
    panel._tree._rename_delay_ms = 100
    panel.vm.load()
    qapp.processEvents()
    return panel


def _items(panel: TreePanel):
    root = panel._tree.topLevelItem(0)
    segment = root.child(0)
    unit = segment.child(0)
    return root, segment, unit


def _visible_editor(panel: TreePanel) -> QLineEdit | None:
    for child in panel._tree.findChildren(QLineEdit):
        if child.isVisible():
            return child
    return None


def _click(
    qapp,
    panel: TreePanel,
    item,
    x_offset: int = 70,
    wait_for_rename: bool = True,
) -> None:
    tree = panel._tree
    rect = tree.visualItemRect(item)
    pos = QPoint(rect.left() + x_offset, rect.center().y())
    QTest.mouseClick(
        tree.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        pos,
    )
    qapp.processEvents()
    if wait_for_rename and tree._rename_timer.isActive():
        # 单击已选中节点会延迟一个双击间隔再进编辑；测试里等它落地
        QTest.qWait(tree._rename_delay_ms + 20)
        qapp.processEvents()


def _unit_names(segment_id: int) -> list[str]:
    return [unit.name for unit in project_io.units(segment_id)]


def test_click_selected_node_enters_inline_edit_and_enter_commits(qapp, project):
    """已选中单位工程再单击：进入行内编辑（全选），回车提交并刷新树。"""
    panel = _panel(qapp)
    segment_id = panel._tree._node_of(_items(panel)[1]).id
    _root, _segment, unit = _items(panel)
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    assert panel._tree.state() == QAbstractItemView.State.EditingState
    editor = _visible_editor(panel)
    assert editor is not None
    assert editor.text() == "雨水工程"
    assert editor.selectedText() == "雨水工程"  # 进入编辑即全选，直接输入覆盖

    editor.setText("雨水工程（改）")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["雨水工程（改）"]
    assert _items(panel)[2].text(0) == "雨水工程（改）"
    assert panel.current_node is not None
    assert panel.current_node.kind == "unit"
    assert panel.current_node.name == "雨水工程（改）"
    assert panel._tree._mouse_filter_installed is False


def test_click_elsewhere_commits_inline_edit(qapp, project):
    """编辑中点击别处（工程根）→ 提交，不需要回车；选中跟随点击目标。"""
    panel = _panel(qapp)
    root, segment, unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("点击别处提交")
    _click(qapp, panel, root)  # 焦点移走 → delegate 提交
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["点击别处提交"]
    assert _items(panel)[2].text(0) == "点击别处提交"
    assert panel.current_node is not None
    assert panel.current_node.kind == "project"


def test_click_another_node_commits_and_keeps_new_selection(qapp, project):
    """编辑中点击另一个节点：提交改名，选中停在用户点的新节点。"""
    panel = _panel(qapp)
    _root, segment, _unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel.vm.add_unit(segment_id, "第二单位工程")
    qapp.processEvents()
    first, second = _items(panel)[1].child(0), _items(panel)[1].child(1)
    panel._tree.setCurrentItem(first)
    qapp.processEvents()

    _click(qapp, panel, first)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("第一单位工程（改）")
    _click(qapp, panel, second)
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["第一单位工程（改）", "第二单位工程"]
    assert panel.current_node is not None
    assert panel.current_node.name == "第二单位工程"


def test_click_outside_tree_commits_inline_edit(qapp, project):
    """编辑中点击树面板之外（即使目标不接受焦点）→ 也提交。

    标签栏 / 工具条等区域不抢焦点，只靠 delegate 的 focus-out 不会结束编辑；
    树在编辑期间挂的应用级鼠标过滤器负责先提交再让点击照常送达。
    """
    panel = _panel(qapp)
    _root, segment, unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("点外部提交")
    other = QWidget()
    other.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    other.resize(120, 40)
    other.show()
    QTest.mouseClick(
        other,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(10, 10),
    )
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["点外部提交"]
    assert _items(panel)[2].text(0) == "点外部提交"
    assert panel._tree.state() == QAbstractItemView.State.NoState

    # 外部点击不应留下“抑制下一次单击”的状态：再点该节点应能重新进入编辑
    _click(qapp, panel, _items(panel)[2])
    assert panel._tree.state() == QAbstractItemView.State.EditingState
    again = _visible_editor(panel)
    assert again is not None
    QTest.keyClick(again, Qt.Key.Key_Escape)
    qapp.processEvents()


def test_click_blank_tree_area_commits_without_reentering(qapp, project):
    """编辑中点击树空白处：提交并关闭，不因同一行仍选中而重新进入编辑。"""
    panel = _panel(qapp)
    _root, segment, unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("空白处提交")
    tree = panel._tree
    QTest.mouseClick(
        tree.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(10, tree.viewport().height() - 5),
    )
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["空白处提交"]
    assert _items(panel)[2].text(0) == "空白处提交"
    assert panel._tree.state() == QAbstractItemView.State.NoState


def test_click_same_row_while_editing_commits_without_reentering(qapp, project):
    """编辑中再点同一行：提交并退出，不会立刻重新进入编辑。"""
    panel = _panel(qapp)
    _root, segment, unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("同一行提交")
    # 点同一行编辑器左侧的图标/缩进区（编辑器不覆盖这里）
    _click(qapp, panel, unit, x_offset=5)
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["同一行提交"]
    assert _items(panel)[2].text(0) == "同一行提交"
    assert panel._tree.state() == QAbstractItemView.State.NoState


def test_inline_editor_height_fills_row(qapp, project):
    """编辑框上下撑满树行，而不是只占文字区（默认实现会上下缩进）。"""
    panel = _panel(qapp)
    # 模拟主题 QSS 的行内边距 / 装饰选中：默认编辑器几何会按文字区缩进
    panel._tree.setStyleSheet(
        "QTreeView { show-decoration-selected: 1; }"
        "QTreeView::item { padding: 5px 8px; }"
    )
    qapp.processEvents()
    _root, _segment, unit = _items(panel)
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    item_rect = panel._tree.visualItemRect(unit)
    assert item_rect.height() > editor.fontMetrics().height()  # 行高被 padding 撑大
    assert editor.height() == item_rect.height()
    assert editor.geometry().top() == item_rect.top()
    assert editor.geometry().bottom() == item_rect.bottom()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    qapp.processEvents()


def test_escape_cancels_inline_edit(qapp, project):
    """Esc 取消：库与树都保持原名称。"""
    panel = _panel(qapp)
    _root, segment, unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("不应保存")
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["雨水工程"]
    assert _items(panel)[2].text(0) == "雨水工程"
    assert panel._tree._mouse_filter_installed is False


def test_empty_name_keeps_old_name(qapp, project):
    """空名称被 ViewModel 拒绝：编辑关闭，条目仍是旧名字。"""
    panel = _panel(qapp)
    _root, segment, unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.clear()
    QTest.keyClick(editor, Qt.Key.Key_Return)
    qapp.processEvents()
    qapp.processEvents()

    assert _unit_names(segment_id) == ["雨水工程"]
    assert _items(panel)[2].text(0) == "雨水工程"


def test_first_click_on_unselected_node_only_selects(qapp, project):
    """未选中节点第一次单击只选中，不进入编辑。"""
    panel = _panel(qapp)
    _root, _segment, unit = _items(panel)
    panel._tree.clearSelection()
    panel._tree.setCurrentItem(None)
    qapp.processEvents()

    _click(qapp, panel, unit)
    assert panel._tree.currentItem() is unit
    assert panel._tree.state() == QAbstractItemView.State.NoState
    assert _visible_editor(panel) is None


def test_double_click_selected_node_does_not_enter_rename(qapp, project):
    """已选中节点双击：第一次单击安排的延迟重命名被第二次单击取消。"""
    panel = _panel(qapp)
    _root, _segment, unit = _items(panel)
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit, wait_for_rename=False)
    assert panel._tree._rename_timer.isActive()
    _click(qapp, panel, unit, wait_for_rename=False)  # 双击的第二次单击
    QTest.qWait(panel._tree._rename_delay_ms + 30)
    qapp.processEvents()

    assert panel._tree.state() == QAbstractItemView.State.NoState
    assert _visible_editor(panel) is None


def test_double_click_unselected_node_does_not_enter_rename(qapp, project):
    """未选中节点双击：第一次单击只选中，第二次单击不能触发重命名。"""
    panel = _panel(qapp)
    _root, _segment, unit = _items(panel)
    panel._tree.clearSelection()
    panel._tree.setCurrentItem(None)
    qapp.processEvents()

    _click(qapp, panel, unit, wait_for_rename=False)
    assert panel._tree.currentItem() is unit
    assert panel._tree._rename_timer.isActive() is False
    _click(qapp, panel, unit, wait_for_rename=False)
    QTest.qWait(panel._tree._rename_delay_ms + 30)
    qapp.processEvents()

    assert panel._tree.state() == QAbstractItemView.State.NoState
    assert _visible_editor(panel) is None


def test_mouse_double_click_event_cancels_pending_rename(qapp, project):
    """Qt 原生双击事件路径：第一次单击后收到 DblClick，也不能进重命名。"""
    panel = _panel(qapp)
    _root, _segment, unit = _items(panel)
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit, wait_for_rename=False)
    assert panel._tree._rename_timer.isActive()
    tree = panel._tree
    rect = tree.visualItemRect(unit)
    QTest.mouseDClick(
        tree.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(rect.left() + 70, rect.center().y()),
    )
    qapp.processEvents()
    QTest.qWait(tree._rename_delay_ms + 30)
    qapp.processEvents()

    assert panel._tree.state() == QAbstractItemView.State.NoState
    assert _visible_editor(panel) is None


def test_project_root_rename_updates_project_name(qapp, project):
    """工程根节点支持行内改名：同步修改项目名称（树与库都变）。"""
    panel = _panel(qapp)
    root, _segment, _unit = _items(panel)
    panel._tree.setCurrentItem(root)
    qapp.processEvents()

    _click(qapp, panel, root)
    assert panel._tree.state() == QAbstractItemView.State.EditingState
    editor = _visible_editor(panel)
    assert editor is not None
    assert editor.text() == "新建项目"

    editor.setText("改名后的工程")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    qapp.processEvents()
    qapp.processEvents()

    assert project_io.project_name() == "改名后的工程"
    assert _items(panel)[0].text(0) == "改名后的工程"
    assert panel.current_node is not None
    assert panel.current_node.is_project
    assert panel.current_node.name == "改名后的工程"


def test_project_root_rename_syncs_dialog_values(qapp, project):
    """根节点改名后，基本信息对话框读到的项目名称也是新名字。"""
    panel = _panel(qapp)
    root, _segment, _unit = _items(panel)
    panel._tree.setCurrentItem(root)
    qapp.processEvents()

    _click(qapp, panel, root)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("对话框同步工程")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    qapp.processEvents()
    qapp.processEvents()

    info = project_io.basic_info()
    assert info is not None
    assert info.project_name == "对话框同步工程"
    assert panel._tree.topLevelItem(0).text(0) == "对话框同步工程"


def test_click_on_expand_arrow_does_not_edit(qapp, project):
    """标段左侧展开/折叠箭头区不算文字点击，不进入编辑。"""
    panel = _panel(qapp)
    _root, segment, _unit = _items(panel)
    panel._tree.setCurrentItem(segment)
    qapp.processEvents()

    # 箭头在条目左侧 indentation 宽的区域内
    _click(qapp, panel, segment, x_offset=panel._tree.indentation() // 2)
    assert panel._tree.state() == QAbstractItemView.State.NoState
    assert _visible_editor(panel) is None


def test_f2_enters_inline_edit(qapp, project):
    """保留 1.0 的 F2 行内重命名入口。"""
    panel = _panel(qapp)
    _root, _segment, unit = _items(panel)
    panel._tree.setCurrentItem(unit)
    panel._tree.setFocus()
    qapp.processEvents()

    QTest.keyClick(panel._tree, Qt.Key.Key_F2)
    qapp.processEvents()
    assert panel._tree.state() == QAbstractItemView.State.EditingState
    editor = _visible_editor(panel)
    assert editor is not None
    assert editor.text() == "雨水工程"
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    qapp.processEvents()


def test_rebuild_while_editing_closes_editor_safely(qapp, project):
    """编辑途中外部重建树（AI / MCP / 关工程）：先收编辑器再 clear，不崩溃。"""
    panel = _panel(qapp)
    _root, segment, unit = _items(panel)
    segment_id = panel._tree._node_of(segment).id
    panel._tree.setCurrentItem(unit)
    qapp.processEvents()

    _click(qapp, panel, unit)
    editor = _visible_editor(panel)
    assert editor is not None
    editor.setText("编辑途中的名字")

    panel.vm.load()  # 模拟外部结构变化触发的重建
    qapp.processEvents()
    qapp.processEvents()

    assert panel._tree.state() == QAbstractItemView.State.NoState
    # 未提交的编辑不应写库
    assert _unit_names(segment_id) == ["雨水工程"]
    assert _items(panel)[2].text(0) == "雨水工程"
