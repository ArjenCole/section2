"""费用汇总表树形列测试：+/- 方框画在序号列（编号左侧），点击切换收起 / 展开。

费用汇总表按项目结构展开成树：序号列兼作树形列（父行 +/- 方框、子行缩进
竖线），名称列是普通文本列。这里覆盖三件事：

* 树形元数据挂在序号列条目上（名称列不再有缩进 / 方框）；
* 序号列左侧的方框能被点中（委托装在序号列上，点击落到 toggle 回调）；
* 收起 / 展开后行数按层级增减。

注意：``SummaryPanel`` 只造页控件、页本身没有父级。测试里必须把页装进一个
宿主窗体再显示——裸着的顶层页在用例结束时随 panel 一起被 Python 回收，
Qt 的控件表会留下残影，随后 ``QApplication.allWidgets()`` 直接访问违例。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QStyleOptionViewItem, QVBoxLayout, QWidget

from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.viewmodels.project_vm import KIND_PROJECT, TreeNode
from app.views.panels.unit_panel import _TREE_ROLE, _ElementNameDelegate


@pytest.fixture()
def panel(qapp, tmp_path):
    """两个标段 × 两个单位工程的工程，返回装好工程根行的汇总页控制器。"""
    project_io.new_project(
        NewProjectSpec(
            path=tmp_path / "汇总表.stn",
            project_name="示例工程",
            segment_names=["一标段", "二标段"],
            unit_names=["雨水工程", "污水工程"],
        )
    )
    from app.views.panels.summary_panel import SummaryPanel

    summary = SummaryPanel()
    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(summary.cost_page)
    layout.addWidget(summary.price_page)
    host.resize(780, 640)
    host.show()
    summary.set_node(TreeNode(kind=KIND_PROJECT, name=project_io.project_name(), id=None))
    qapp.processEvents()
    yield summary
    host.close()


def _click_tree_box(table, row: int) -> bool:
    """在序号列该行的 +/- 方框中心模拟一次左键按下，返回委托是否吃掉事件。"""
    index = table.model().index(row, 0)
    delegate = table.itemDelegateForColumn(0)
    option = QStyleOptionViewItem()
    option.rect = table.visualRect(index)
    point = delegate._icon_rect(option.rect, index.data(_TREE_ROLE)).center()
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(point),
        QPointF(point),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    return delegate.editorEvent(event, table.model(), option, index)


def test_tree_metadata_lives_in_seq_column(panel) -> None:
    table = panel._cost_table
    # 工程根 + 2 标段 + 4 单位工程
    assert table.rowCount() == 7
    assert table.horizontalHeaderItem(0).text() == "序号"
    # 序号列是树形列：委托装在序号列，名称列是普通列
    assert isinstance(table.itemDelegateForColumn(0), _ElementNameDelegate)
    for row in range(table.rowCount()):
        assert table.item(row, 0).data(_TREE_ROLE) is not None
        assert table.item(row, 1).data(_TREE_ROLE) is None
    assert table.item(0, 0).data(_TREE_ROLE) == {
        "indent": 0,
        "has_children": True,
        "expanded": True,
    }
    # 子行按层级缩进：标段 1 级、单位工程 2 级（方框画在编号左侧）
    assert [table.item(row, 0).data(_TREE_ROLE)["indent"] for row in range(7)] == [
        0, 1, 2, 2, 1, 2, 2,
    ]
    # 名称列是普通文本列：不再缩进
    assert table.item(0, 1).text() == "示例工程"
    # 序号列按最深编号的实际字宽兜底加宽，缩进后仍不裁字
    assert table.columnWidth(0) >= 110


def test_click_box_in_seq_column_collapses_and_expands(panel) -> None:
    table = panel._cost_table
    assert table.rowCount() == 7

    # 点第一个标段（第 2 行）的 +/- 方框：两个单位工程收起
    assert _click_tree_box(table, 1) is True
    assert table.rowCount() == 5
    assert table.item(1, 0).data(_TREE_ROLE)["expanded"] is False
    assert [table.item(row, 0).text() for row in range(5)] == ["1", "1.1", "1.2", "1.2.1", "1.2.2"]

    # 再点一次：重新展开
    assert _click_tree_box(table, 1) is True
    assert table.rowCount() == 7
    assert table.item(1, 0).data(_TREE_ROLE)["expanded"] is True
