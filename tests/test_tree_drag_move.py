"""项目结构树「拖拽移动节点」回归测试。

用户反馈：在项目结构里拖拽节点无效，没能正确移动单项工程位置。

根因：``_ProjectTree.move_node_requested`` 声明为 ``Signal(object, int, int)``，
而标段移动的落点解析返回 ``(source, None, index)``（None = 项目根）；
PySide6 把 None 静默转换成 0（仅向 stderr 打一行转换警告），
``ProjectViewModel.move_node`` 里 ``if parent_id is not None: return False``
拿到 0 视为非法父级，标段拖拽被静默吞掉。
另外落点解析要求标段拖到其它标段行上下边缘约 2px 的窄条才算合法，
用户最自然的"拖到行上"落点是 OnItem，几乎必被拒绝。

测试策略：不跑真实鼠标拖拽（drag.exec 模态循环在离屏平台难以稳定驱动，
且 dropEvent 依赖 Qt 内部设置的 source），而是按真实链路构造待移动：
``_resolve_drop`` 落点解析 → ``_pending_move`` 记录（dropEvent 的职责）
→ ``_consume_pending_move``（startDrag 退出后的职责，含信号发射）
→ ViewModel 写库 → 树重建。覆盖从解析到落库的整条链。
"""

import app  # noqa: F401  # ICU 预加载必须先于 PySide6

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QAbstractItemView

from app.core.models import base as orm
from app.core.models.models import Segment, Unit
from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.views.panels.tree_panel import TreePanel

from sqlalchemy import select

Above = QAbstractItemView.DropIndicatorPosition.AboveItem
Below = QAbstractItemView.DropIndicatorPosition.BelowItem
OnItem = QAbstractItemView.DropIndicatorPosition.OnItem


def _two_segments_two_units():
    """建工程：标段一（甲/乙）与标段二（丙/丁），四个单位工程名称互不相同。

    NewProjectSpec 会把同一组 unit_names 建进每个标段，故先建后改名区分，
    断言里能明确区分"移动"与"复制"。
    """
    project_io.new_project(
        NewProjectSpec(
            path=None,
            project_name="拖拽测试工程",
            segment_names=["标段一", "标段二"],
            unit_names=["甲", "乙"],
        )
    )
    session = orm.session()
    second = session.scalar(select(Segment).where(Segment.name == "标段二"))
    for unit, name in zip(project_io.units(second.id), ("丙", "丁")):
        unit.name = name
    project_io.commit()


def _panel(qapp) -> TreePanel:
    panel = TreePanel()
    panel.vm.load()
    qapp.processEvents()
    return panel


def _drag_and_drop(qapp, panel, source_item, target_item, indicator):
    """复刻真实拖放链路：dropEvent 记录待移动 → startDrag 退出后消费。"""
    tree = panel._tree
    status, payload = tree._resolve_drop(tree._node_of(source_item), target_item, indicator)
    if status != "ok":
        raise AssertionError(f"落点解析失败：{payload}")
    tree._pending_move = payload
    tree._consume_pending_move()
    qapp.processEvents()


def _segment_items(panel):
    root = panel._tree.topLevelItem(0)
    return [root.child(i) for i in range(root.childCount())]


def _segment_order() -> list[str]:
    return [
        row.name
        for row in orm.session().scalars(select(Segment).order_by(Segment.order_no, Segment.id))
    ]


def _unit_order(segment_name: str) -> list[str]:
    segment = orm.session().scalar(select(Segment).where(Segment.name == segment_name))
    return [
        row.name
        for row in orm.session().scalars(
            select(Unit).where(Unit.segment_id == segment.id).order_by(Unit.order_no, Unit.id)
        )
    ]


# ---------------------------------------------------------------- 标段拖拽
def test_segment_move_onto_another_segment(qapp):
    """标段拖到另一标段行上（最自然的落点）：排在它后面。

    回归核心：此前 None→0 类型转换让 ``move_node`` 把标段移动静默吞掉，
    OnItem 落点又因边缘窄条判定被直接拒绝，拖拽后顺序纹丝不动。
    """
    _two_segments_two_units()
    panel = _panel(qapp)
    seg1, seg2 = _segment_items(panel)
    _drag_and_drop(qapp, panel, seg1, seg2, OnItem)
    assert _segment_order() == ["标段二", "标段一"]
    # 落库后树按新顺序重建
    assert _segment_items(panel)[0].text(0) == "标段二"


def test_segment_move_below_another_segment(qapp):
    """标段拖到另一标段下方边缘：同样排在它后面。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    seg1, seg2 = _segment_items(panel)
    _drag_and_drop(qapp, panel, seg1, seg2, Below)
    assert _segment_order() == ["标段二", "标段一"]


def test_segment_move_above_another_segment(qapp):
    """标段拖到另一标段上方边缘：插到它前面。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    seg1, seg2 = _segment_items(panel)
    _drag_and_drop(qapp, panel, seg2, seg1, Above)
    assert _segment_order() == ["标段二", "标段一"]


def test_segment_move_back_restores_order(qapp):
    """往返拖拽两次：顺序还原。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    seg1, seg2 = _segment_items(panel)
    _drag_and_drop(qapp, panel, seg1, seg2, OnItem)
    assert _segment_order() == ["标段二", "标段一"]
    seg_moved = _segment_items(panel)[0]
    seg_last = _segment_items(panel)[1]
    _drag_and_drop(qapp, panel, seg_moved, seg_last, OnItem)
    assert _segment_order() == ["标段一", "标段二"]


# ---------------------------------------------------------------- 单位工程拖拽
def test_unit_move_across_segments(qapp):
    """单位工程甲拖进另一标段行上：跨标段移动（原标段不再保留甲）。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    seg2 = _segment_items(panel)[1]
    unit_a = panel._tree.topLevelItem(0).child(0).child(0)  # 标段一/甲
    _drag_and_drop(qapp, panel, unit_a, seg2, OnItem)
    assert _unit_order("标段一") == ["乙"]
    assert _unit_order("标段二") == ["丙", "丁", "甲"]


def test_unit_move_to_segment_end_of_target(qapp):
    """单位工程拖进目标标段：追加到末尾。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    seg2 = _segment_items(panel)[1]
    unit_b = panel._tree.topLevelItem(0).child(0).child(1)  # 标段一/乙
    _drag_and_drop(qapp, panel, unit_b, seg2, OnItem)
    assert _unit_order("标段一") == ["甲"]
    assert _unit_order("标段二") == ["丙", "丁", "乙"]


def test_unit_reorder_within_segment(qapp):
    """单位工程在标段内拖到兄弟上方：顺序对调，不影响其它标段。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    unit_a = panel._tree.topLevelItem(0).child(0).child(0)  # 标段一/甲
    unit_b = panel._tree.topLevelItem(0).child(0).child(1)  # 标段一/乙
    _drag_and_drop(qapp, panel, unit_b, unit_a, Above)
    assert _unit_order("标段一") == ["乙", "甲"]
    assert _unit_order("标段二") == ["丙", "丁"]


# ---------------------------------------------------------------- 非法落点
def test_invalid_drop_reports_and_keeps_structure(qapp):
    """单位工程放到空白区域：结构不变并广播错误消息。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    messages = []
    panel._tree.drop_rejected.connect(messages.append)
    tree = panel._tree
    unit_a = panel._tree.topLevelItem(0).child(0).child(0)
    status, payload = tree._resolve_drop(tree._node_of(unit_a), None, OnItem)
    assert status == "invalid"
    tree.drop_rejected.emit(payload)
    assert _segment_order() == ["标段一", "标段二"]
    assert _unit_order("标段一") == ["甲", "乙"]
    assert messages and "标段" in messages[0]


def test_segment_drop_onto_unit_row_is_invalid(qapp):
    """标段放到单位工程行上：非法落点，结构不变。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    messages = []
    panel._tree.drop_rejected.connect(messages.append)
    seg2 = _segment_items(panel)[1]
    unit_a = panel._tree.topLevelItem(0).child(0).child(0)
    status, payload = panel._tree._resolve_drop(
        panel._tree._node_of(seg2), unit_a, OnItem
    )
    assert status == "invalid"
    panel._tree.drop_rejected.emit(payload)
    assert _segment_order() == ["标段一", "标段二"]
    assert messages and "标段" in messages[0]


def test_drop_on_viewport_position_resolves_invalid(qapp):
    """dropEvent 的 itemAt 在视口外返回 None：按非法落点处理（不抛异常）。"""
    _two_segments_two_units()
    panel = _panel(qapp)
    tree = panel._tree
    unit_a = panel._tree.topLevelItem(0).child(0).child(0)
    target = tree.itemAt(QPoint(8, tree.viewport().rect().bottom() + 20))
    assert target is None
    status, _payload = tree._resolve_drop(tree._node_of(unit_a), target, OnItem)
    assert status == "invalid"
