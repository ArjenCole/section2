"""构件剪贴板（跨文件复制/粘贴/剪切）与格式刷测试。

覆盖：快照口径（合槽成员还原为独立构件）、系统剪贴板读写、原则引用
重映射、合槽组整组粘贴与嵌套拒绝、多选复制粘贴顺序、格式刷同步四项
原则与取消路径、断面图跟随合槽成员画整槽。Qt 部分离屏运行。
"""

from __future__ import annotations

import pytest

from app.core.models import base as orm
from app.services import element_clipboard, project_io
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm


@pytest.fixture()
def two_unit_project(tmp_path):
    """两个单位工程的临时工程，返回 (unit_a, unit_b)。"""
    project_io.new_project(NewProjectSpec(path=tmp_path / "剪贴板.stn", unit_names=["雨水", "污水"]))
    units = project_io.units(project_io.segments()[0].id)
    return units[0], units[1]


def _make_pipe(unit_id: int, name: str, dn: int = 600, depth: str = "3"):
    from app.viewmodels import unit_vm

    element = unit_vm.create_element(unit_id, category=1, name=name, depth=depth, amount="10")
    unit_vm.create_pipe(element.id, mat="Ⅱ级混凝土管", dn=dn, content="1")
    return element


# --------------------------------------------------------------------------- #
# 快照与插入
# --------------------------------------------------------------------------- #
@pytest.fixture()
def multi_enclosure_project(tmp_path):
    """两个围护原则的临时工程（列表顺序：围护A、围护B）。"""
    from app.core.models.models import PcpEnclosure

    project_io.new_project(
        NewProjectSpec(path=tmp_path / "多原则.stn", unit_names=["u"], enclosure_name="围护A")
    )
    unit = project_io.units(project_io.segments()[0].id)[0]
    orm.session().add(PcpEnclosure(name="围护B", order_no=1))
    project_io.commit()
    return unit


def test_group_member_copy_both_sides_dash_uses_first_principle(
    multi_enclosure_project,
) -> None:
    """两侧都是 "-"：复制后取项目围护原则列表第一条，忽略成员原有侧名。"""
    unit = multi_enclosure_project
    e1 = _make_pipe(unit.id, "管A", depth="3")
    e2 = _make_pipe(unit.id, "管B", depth="3")
    e3 = _make_pipe(unit.id, "管C", depth="3")
    group, error = unit_vm.create_trench_group([e1.id, e2.id, e3.id])
    assert group is not None and error is None
    # 等深：中间成员左右两侧都是 "-"；把侧名改成围护B，验证不会被取用
    unit_vm.update_element(e2.id, pe_left_name="围护B", pe_right_name="围护B")

    snap = unit_vm.element_copy_snapshot(e2.id)
    assert snap["pe_name"] == "围护A"
    assert snap["pe_left_name"] == "" and snap["pe_right_name"] == ""


def test_group_member_copy_single_dash_uses_other_side(multi_enclosure_project) -> None:
    """单侧是 "-"：复制后取另一侧原则（左右两种方向都覆盖）。"""
    unit = multi_enclosure_project
    deep = _make_pipe(unit.id, "深", depth="4")
    shallow = _make_pipe(unit.id, "浅", dn=800, depth="3")
    unit_vm.update_element(deep.id, pe_name="围护A")
    unit_vm.update_element(shallow.id, pe_name="围护B")
    group, _error = unit_vm.create_trench_group([deep.id, shallow.id])

    # 末成员更浅：左侧 "-"，取右侧外侧原则
    snap = unit_vm.element_copy_snapshot(shallow.id)
    assert snap["pe_name"] == "围护B"
    assert snap["pe_left_name"] == "" and snap["pe_right_name"] == ""

    # 反过来：浅构件在首、深构件在末 → 首成员右侧 "-"，取左侧
    shallow2 = _make_pipe(unit.id, "浅2", dn=1000, depth="3")
    deep2 = _make_pipe(unit.id, "深2", dn=1200, depth="4")
    unit_vm.update_element(shallow2.id, pe_name="围护B")
    unit_vm.update_element(deep2.id, pe_name="围护A")
    group2, _error = unit_vm.create_trench_group([shallow2.id, deep2.id])
    snap2 = unit_vm.element_copy_snapshot(shallow2.id)
    assert snap2["pe_name"] == "围护B"
    assert snap2["pe_left_name"] == "" and snap2["pe_right_name"] == ""


def test_group_member_copy_both_sides_active_keeps_lr(multi_enclosure_project) -> None:
    """两侧都不是 "-"：保留左右分设及详细原则、支撑勾选。"""
    unit = multi_enclosure_project
    deep = _make_pipe(unit.id, "深", depth="4")
    shallow = _make_pipe(unit.id, "浅", dn=800, depth="3")
    group, _error = unit_vm.create_trench_group([deep.id, shallow.id])
    unit_vm.update_element(
        deep.id,
        pe_left_name="围护A",
        pe_right_name="围护B",
        support_left=True,
        support_right=False,
    )

    snap = unit_vm.element_copy_snapshot(deep.id)
    assert snap["pe_name"] == "左右分设"
    assert snap["pe_left_name"] == "围护A"
    assert snap["pe_right_name"] == "围护B"
    assert snap["support_left"] is True
    assert snap["support_right"] is False


def test_dissolve_group_keeps_lr_when_both_sides_active(multi_enclosure_project) -> None:
    """解散合槽：两侧都有效的成员保持左右分设及支撑勾选。"""
    from app.core.models.models import Element, LR_PE_TEXT, TrenchGroup

    unit = multi_enclosure_project
    deep = _make_pipe(unit.id, "深", depth="4")
    shallow = _make_pipe(unit.id, "浅", dn=800, depth="3")
    group, _error = unit_vm.create_trench_group([deep.id, shallow.id])
    unit_vm.update_element(
        deep.id,
        pe_left_name="围护A",
        pe_right_name="围护B",
        support_left=True,
        support_right=False,
    )

    unit_vm.dissolve_trench_group(group.id)
    orm.session().expire_all()
    member = orm.session().get(Element, deep.id)
    assert orm.session().get(TrenchGroup, group.id) is None
    assert member.group_id is None
    assert member.pe_name == LR_PE_TEXT
    assert member.pe_left_name == "围护A"
    assert member.pe_right_name == "围护B"
    assert member.support_left is True and member.support_right is False


def test_remove_from_group_uses_member_side_state(multi_enclosure_project) -> None:
    """移出合槽：单侧 "-" 取另一侧；两侧都有效则保留左右分设。"""
    from app.core.models.models import Element, LR_PE_TEXT

    unit = multi_enclosure_project
    left = _make_pipe(unit.id, "左", depth="3")
    middle = _make_pipe(unit.id, "中", depth="4")
    right = _make_pipe(unit.id, "右", depth="3")
    unit_vm.update_element(left.id, pe_name="围护B")
    group, _error = unit_vm.create_trench_group([left.id, middle.id, right.id])

    # 首成员右侧比邻居浅 → "-"；取左侧外侧原则
    unit_vm.remove_from_group(left.id)
    orm.session().expire_all()
    m1 = orm.session().get(Element, left.id)
    assert m1.group_id is None
    assert m1.pe_name == "围护B"
    assert m1.pe_left_name == "" and m1.pe_right_name == ""

    # 中间成员比两侧都深 → 两侧都有效；保留左右分设
    unit_vm.update_element(middle.id, pe_left_name="围护A", pe_right_name="围护B")
    unit_vm.remove_from_group(middle.id)
    orm.session().expire_all()
    m2 = orm.session().get(Element, middle.id)
    assert m2.group_id is None
    assert m2.pe_name == LR_PE_TEXT
    assert m2.pe_left_name == "围护A" and m2.pe_right_name == "围护B"


def test_remove_middle_member_with_both_sides_dash_uses_first_principle(
    multi_enclosure_project,
) -> None:
    """移出合槽：等深组的中间成员两侧都是 "-"，取项目第一条围护原则。"""
    from app.core.models.models import Element

    unit = multi_enclosure_project
    e1 = _make_pipe(unit.id, "管A", depth="3")
    e2 = _make_pipe(unit.id, "管B", depth="3")
    e3 = _make_pipe(unit.id, "管C", depth="3")
    group, _error = unit_vm.create_trench_group([e1.id, e2.id, e3.id])
    unit_vm.update_element(e2.id, pe_left_name="围护B", pe_right_name="围护B")

    unit_vm.remove_from_group(e2.id)
    orm.session().expire_all()
    member = orm.session().get(Element, e2.id)
    assert member.group_id is None
    assert member.pe_name == "围护A"
    assert member.pe_left_name == "" and member.pe_right_name == ""


def test_delete_member_dissolve_uses_pre_delete_state(multi_enclosure_project) -> None:
    """删除组员导致整组解散：剩余成员按删除前的组内状态还原。"""
    from app.core.models.models import Element, TrenchGroup

    unit = multi_enclosure_project
    deep = _make_pipe(unit.id, "深", depth="4")
    shallow = _make_pipe(unit.id, "浅", dn=800, depth="3")
    unit_vm.update_element(shallow.id, pe_name="围护B")
    group, _error = unit_vm.create_trench_group([deep.id, shallow.id])

    unit_vm.delete_element(deep.id)
    orm.session().expire_all()
    assert orm.session().get(TrenchGroup, group.id) is None
    member = orm.session().get(Element, shallow.id)
    assert member.group_id is None
    # 删除前：末成员左侧 "-"、右侧外侧原则 → 取右侧
    assert member.pe_name == "围护B"
    assert member.pe_left_name == "" and member.pe_right_name == ""


def test_group_snapshot_and_insert_roundtrip(two_unit_project) -> None:
    """合槽组整组复制 → 粘贴到另一单位工程：成员、名称、数量、左右分设一致。"""
    from app.core.models.models import TrenchGroup
    from sqlalchemy import select

    from app.viewmodels.unit_vm import group_snapshot, insert_group_data

    unit_a, unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    e2 = _make_pipe(unit_a.id, "管B", dn=800)
    group, error = unit_vm.create_trench_group([e1.id, e2.id])
    assert group is not None and error is None
    data = group_snapshot(group.id)
    assert data["name"] == group.name and len(data["members"]) == 2

    pasted = insert_group_data(unit_b.id, data, None)
    assert pasted is not None
    members = sorted(pasted.members, key=lambda item: (item.order_no, item.id))
    assert [member.name for member in members] == ["管A", "管B"]
    assert all(member.pe_name == "左右分设" for member in members)
    assert all(member.amount == group.amount for member in members)
    # 原组不受影响
    groups_a = list(
        orm.session().scalars(select(TrenchGroup).where(TrenchGroup.unit_id == unit_a.id))
    )
    assert len(groups_a) == 1


def test_insert_group_rejects_single_member(two_unit_project) -> None:
    """成员不足两条的快照拒绝成组。"""
    from app.viewmodels.unit_vm import insert_group_data

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    data = {"name": "单条", "amount": "10", "members": [{"name": "管A", "amount": "10"}]}
    assert insert_group_data(unit_a.id, data, e1.id) is None


# --------------------------------------------------------------------------- #
# 系统剪贴板
# --------------------------------------------------------------------------- #
def test_clipboard_roundtrip(qapp) -> None:
    """写入系统剪贴板后按 MIME 原样读回；异类载荷返回 None。"""
    assert element_clipboard.read_items() is None  # 空剪贴板
    items = [{"type": "element", "data": {"name": "甲", "pe_name": "围护1"}}]
    assert element_clipboard.write_items(items)
    assert element_clipboard.has_payload()
    read = element_clipboard.read_items()
    assert read == items
    # 读回的是副本：就地修改不影响剪贴板
    read[0]["data"]["name"] = "改"
    assert element_clipboard.read_items()[0]["data"]["name"] == "甲"


def test_remap_clears_unknown_principles(two_unit_project) -> None:
    """目标工程没有同名原则时回退默认（pe_name=None、侧名空），保留合槽占位。"""
    from app.core.models.models import LR_PE_TEXT

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    e2 = _make_pipe(unit_a.id, "管B", dn=800)
    unit_vm.create_trench_group([e1.id, e2.id])
    items = [
        {
            "type": "element",
            "data": {
                "name": "外来",
                "pe_name": "不存在的围护",
                "pf_name": "不存在的地基",
                "pp_name": "不存在的降水",
                "pw_name": "不存在的面宽",
                "pe_left_name": "没有的左",
                "pe_right_name": "没有的右",
            },
        },
        {
            "type": "element",
            "data": {"name": "分设", "pe_name": LR_PE_TEXT, "pe_left_name": "没有的左"},
        },
    ]
    element_clipboard.remap_items(items)
    normal = items[0]["data"]
    assert normal["pe_name"] is None and normal["pf_name"] is None
    assert normal["pp_name"] is None and normal["pw_name"] is None
    assert normal["pe_left_name"] == "" and normal["pe_right_name"] == ""
    lr = items[1]["data"]
    assert lr["pe_name"] == LR_PE_TEXT  # 合槽占位不被误清
    assert lr["pe_left_name"] == ""


# --------------------------------------------------------------------------- #
# 界面：复制 / 粘贴 / 剪切 / 嵌套拒绝 / 顺序
# --------------------------------------------------------------------------- #
def _select_rows(panel, rows: list[int]) -> None:
    from PySide6.QtCore import QItemSelectionModel

    panel._element_table.clearSelection()
    for index, row in enumerate(rows):
        if index == 0:
            panel._element_table.setCurrentCell(row, 0)
        panel._element_table.selectionModel().select(
            panel._element_table.model().index(row, 0),
            QItemSelectionModel.Select | QItemSelectionModel.Rows,
        )


def _group_row(panel) -> int:
    return next(
        index
        for index, row in enumerate(panel._rows_cache)
        if hasattr(row, "member_count")
    )


def _element_row(panel, element_id: int) -> int:
    return next(
        index
        for index, row in enumerate(panel._rows_cache)
        # 父节点行与构件行都可能同 id（分属两张表），按类型排除父行
        if not hasattr(row, "member_count") and getattr(row, "id", None) == element_id
    )


def test_copy_group_paste_into_other_unit(qapp, two_unit_project) -> None:
    """选中父行复制 → 整组进剪贴板；跨单位工程粘贴成组且顺序不变。"""
    from PySide6.QtCore import Qt

    from app.core.models.models import TrenchGroup
    from sqlalchemy import select
    from app.viewmodels.unit_vm import table_rows

    unit_a, unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    e2 = _make_pipe(unit_a.id, "管B", dn=800)
    group, _error = unit_vm.create_trench_group([e1.id, e2.id])
    e3 = _make_pipe(unit_b.id, "管C")

    panel = _panel_for(qapp, unit_a)
    _select_rows(panel, [_group_row(panel)])
    panel._copy_elements()
    items = element_clipboard.read_items()
    assert [item["type"] for item in items] == ["group"]

    panel._show_unit(unit_b.id, "污水")
    qapp.processEvents()
    _select_rows(panel, [_element_row(panel, e3.id)])
    panel._paste_elements()
    qapp.processEvents()
    groups_b = list(
        orm.session().scalars(select(TrenchGroup).where(TrenchGroup.unit_id == unit_b.id))
    )
    assert len(groups_b) == 1
    members = sorted(groups_b[0].members, key=lambda item: (item.order_no, item.id))
    assert [member.name for member in members] == ["管A", "管B"]
    # 组插在锚点（管C）之后，成员顺序保持快照顺序
    names = [row.name for row in table_rows(unit_b.id)]
    assert names == ["管C", "管A+管B 合槽", "管A", "管B"]


def test_paste_elements_into_group_and_nesting_rejected(qapp, two_unit_project) -> None:
    """粘贴到组成员之后（不是组尾）；合槽组粘贴进合槽被拒（不允许嵌套）。"""
    from app.core.event_bus import bus
    from app.core.models.models import TrenchGroup
    from sqlalchemy import select

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    e2 = _make_pipe(unit_a.id, "管B", dn=800)
    group, _error = unit_vm.create_trench_group([e1.id, e2.id])
    e3 = _make_pipe(unit_a.id, "管C")

    panel = _panel_for(qapp, unit_a)
    # 复制普通构件 管C
    _select_rows(panel, [_element_row(panel, e3.id)])
    panel._copy_elements()
    # 选中组成员 管A → 作为子构件插到 管A 之后（管B 之前）
    _select_rows(panel, [_element_row(panel, e1.id)])
    panel._paste_elements()
    qapp.processEvents()
    orm.session().expire(group)
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    assert [member.name for member in members] == ["管A", "管C", "管B"]

    # 剪贴板换成整组快照 → 粘贴到成员行被拒
    from app.viewmodels.unit_vm import group_snapshot

    element_clipboard.write_items([{"type": "group", "data": group_snapshot(group.id)}])
    messages: list[str] = []
    bus().status_message.connect(lambda text, _ms: messages.append(text))
    _select_rows(panel, [_element_row(panel, e1.id)])
    panel._paste_elements()
    assert any("嵌套" in message for message in messages)
    groups = list(orm.session().scalars(select(TrenchGroup)))
    assert len(groups) == 1


def test_paste_on_group_parent_inserts_after_group_at_same_level(
    qapp, two_unit_project
) -> None:
    """选中合槽父行粘贴普通构件：落在整组之后同层级，不变成组员。"""
    from app.core.models.models import Element
    from app.viewmodels.unit_vm import table_rows

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    e2 = _make_pipe(unit_a.id, "管B", dn=800)
    group, _error = unit_vm.create_trench_group([e1.id, e2.id])
    e3 = _make_pipe(unit_a.id, "管C", dn=1000)
    source = _make_pipe(unit_a.id, "待粘贴", dn=1200)

    panel = _panel_for(qapp, unit_a)
    _select_rows(panel, [_element_row(panel, source.id)])
    panel._copy_elements()
    _select_rows(panel, [_group_row(panel)])
    panel._paste_elements()
    qapp.processEvents()

    orm.session().expire(group)
    assert len(group.members) == 2  # 没有变成合槽子条目
    names = [row.name for row in table_rows(unit_a.id)]
    assert names == ["管A+管B 合槽", "管A", "管B", "待粘贴", "管C", "待粘贴"]
    pasted = next(
        element
        for element in orm.session().query(Element).filter_by(name="待粘贴").all()
        if element.id != source.id
    )
    assert pasted.group_id is None
    assert pasted.order_no == 2  # 紧跟在整组之后


def test_paste_group_on_group_parent_inserts_sibling_group(
    qapp, two_unit_project
) -> None:
    """选中合槽父行粘贴整组合槽：作为同层级兄弟组插在其后，不嵌套。"""
    from app.core.models.models import TrenchGroup
    from sqlalchemy import select

    from app.viewmodels.unit_vm import group_snapshot, table_rows

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    e2 = _make_pipe(unit_a.id, "管B", dn=800)
    group, _error = unit_vm.create_trench_group([e1.id, e2.id])
    e3 = _make_pipe(unit_a.id, "管C", dn=1000)

    panel = _panel_for(qapp, unit_a)
    _select_rows(panel, [_group_row(panel)])
    panel._copy_elements()
    element_clipboard.write_items([{"type": "group", "data": group_snapshot(group.id)}])
    _select_rows(panel, [_group_row(panel)])
    panel._paste_elements()
    qapp.processEvents()

    groups = list(orm.session().scalars(select(TrenchGroup).where(TrenchGroup.unit_id == unit_a.id)))
    assert len(groups) == 2
    assert all(len(item.members) == 2 for item in groups)  # 没有成员被并进原组
    names = [row.name for row in table_rows(unit_a.id)]
    assert names == ["管A+管B 合槽", "管A", "管B", "管A+管B 合槽", "管A", "管B", "管C"]


def test_multi_row_copy_paste_keeps_order(qapp, two_unit_project) -> None:
    """多行复制粘贴保持复制顺序，且整体落在当前条目之后。"""
    from app.viewmodels.unit_vm import table_rows

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "甲")
    e2 = _make_pipe(unit_a.id, "乙", dn=800)
    e3 = _make_pipe(unit_a.id, "丙", dn=1000)

    panel = _panel_for(qapp, unit_a)
    _select_rows(panel, [_element_row(panel, e1.id), _element_row(panel, e3.id)])
    panel._copy_elements()
    items = element_clipboard.read_items()
    assert [item["data"]["name"] for item in items] == ["甲", "丙"]
    panel._paste_elements()
    qapp.processEvents()
    names = [row.name for row in table_rows(unit_a.id)]
    assert names == ["甲", "甲", "丙", "乙", "丙"]


def test_paste_without_selection_appends_to_end(qapp, two_unit_project) -> None:
    """没有选中条目时的兜底：粘贴到表单最后一条构件之后（末尾）。"""
    from PySide6.QtCore import QModelIndex

    from app.viewmodels.unit_vm import table_rows

    unit_a, _unit_b = two_unit_project
    _make_pipe(unit_a.id, "甲")
    _make_pipe(unit_a.id, "乙", dn=800)
    source = _make_pipe(unit_a.id, "待粘贴", dn=1000)

    panel = _panel_for(qapp, unit_a)
    _select_rows(panel, [_element_row(panel, source.id)])
    panel._copy_elements()
    panel._element_table.clearSelection()
    panel._element_table.setCurrentIndex(QModelIndex())
    assert panel._current_element_id() is None
    panel._paste_elements()
    qapp.processEvents()
    names = [row.name for row in table_rows(unit_a.id)]
    assert names == ["甲", "乙", "待粘贴", "待粘贴"]


def test_copy_group_member_with_both_sides_active_pastes_as_lr(
    qapp, multi_enclosure_project
) -> None:
    """两侧都有效的合槽成员复制到组外：粘贴结果仍是左右分设，侧名与支撑不变。"""
    from app.core.models.models import Element, LR_PE_TEXT

    unit = multi_enclosure_project
    deep = _make_pipe(unit.id, "深", depth="4")
    shallow = _make_pipe(unit.id, "浅", dn=800, depth="3")
    group, _error = unit_vm.create_trench_group([deep.id, shallow.id])
    unit_vm.update_element(
        deep.id,
        pe_left_name="围护A",
        pe_right_name="围护B",
        support_left=True,
        support_right=False,
    )
    target = _make_pipe(unit.id, "目标", dn=1000)

    panel = _panel_for(qapp, unit)
    _select_rows(panel, [_element_row(panel, deep.id)])
    panel._copy_elements()
    _select_rows(panel, [_element_row(panel, target.id)])
    panel._paste_elements()
    qapp.processEvents()

    pasted = next(
        element
        for element in orm.session().query(Element).filter_by(name="深").all()
        if element.id != deep.id
    )
    assert pasted.group_id is None
    assert pasted.pe_name == LR_PE_TEXT
    assert pasted.pe_left_name == "围护A"
    assert pasted.pe_right_name == "围护B"
    assert pasted.support_left is True and pasted.support_right is False


def test_cut_removes_and_keeps_clipboard(qapp, two_unit_project) -> None:
    """剪切 = 复制 + 删除原条目；剪贴板内容保留可反复粘贴。"""
    from app.core.models.models import Element

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    panel = _panel_for(qapp, unit_a)
    _select_rows(panel, [_element_row(panel, e1.id)])
    panel._cut_elements()
    qapp.processEvents()
    assert orm.session().get(Element, e1.id) is None
    assert element_clipboard.has_payload()


# --------------------------------------------------------------------------- #
# 格式刷
# --------------------------------------------------------------------------- #
def _panel_for(qapp, unit):
    from app.views.panels.unit_panel import UnitPanel

    panel = UnitPanel()
    panel._show_unit(unit.id, unit.name)
    qapp.processEvents()
    return panel


def test_format_painter_syncs_four_principles(qapp, tmp_path) -> None:
    """格式刷：样板取当前构件，选其他构件自动同步四项原则；生效一次后自动退出。"""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from app.core.models.models import (
        Element,
        PcpEnclosure,
        PcpFoundation,
        PcpPrecipitation,
        PcpWidth,
    )

    project_io.new_project(NewProjectSpec(path=tmp_path / "刷.stn", unit_names=["u"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    session = orm.session()
    session.add_all(
        [
            PcpEnclosure(name="围护B", order_no=1),
            PcpFoundation(name="地基B", order_no=1),
            PcpPrecipitation(name="降水B", order_no=1),
            PcpWidth(name="面宽B", order_no=1),
        ]
    )
    project_io.commit()
    src = _make_pipe(unit.id, "样板", dn=600)
    tgt = _make_pipe(unit.id, "目标", dn=800)
    unit_vm.update_element(
        src.id, pe_name="围护B", pf_name="地基B", pp_name="降水B", pw_name="面宽B"
    )

    panel = _panel_for(qapp, unit)
    _select_rows(panel, [_element_row(panel, src.id)])
    panel.set_format_painter(True)
    assert panel._format_painter_active
    assert qapp.overrideCursor() is not None  # 刷形光标已覆盖
    # 只选中样板（或回到样板）不生效：定时器未启动
    _select_rows(panel, [_element_row(panel, src.id)])
    assert not panel._format_painter_timer.isActive()

    # 选中目标 → 防抖定时器就位 → 到点一次生效并自动退出
    _select_rows(panel, [_element_row(panel, tgt.id)])
    assert panel._format_painter_timer.isActive()
    panel._flush_format_painter()
    assert not panel._format_painter_active
    assert qapp.overrideCursor() is None  # 退出后光标恢复
    target = orm.session().get(Element, tgt.id)
    assert target.pe_name == "围护B"
    assert target.pf_name == "地基B"
    assert target.pp_name == "降水B"
    assert target.pw_name == "面宽B"

    # 生效后再选中其他构件不再刷（已退出）；Esc 取消路径仍可用
    panel.set_format_painter(True)
    assert qapp.overrideCursor() is not None
    _select_rows(panel, [_element_row(panel, tgt.id)])
    released: list[bool] = []
    panel.format_painter_changed.connect(released.append)
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    panel.eventFilter(panel._element_table, event)
    assert not panel._format_painter_active
    assert not panel._format_painter_timer.isActive()
    assert qapp.overrideCursor() is None
    assert released == [False]


def test_format_painter_multi_select_one_shot(qapp, tmp_path) -> None:
    """选中多条目标：一次生效刷全部选中构件，然后自动退出（不再连续刷）。"""
    from app.core.models.models import Element, PcpEnclosure, PcpFoundation, PcpPrecipitation, PcpWidth

    project_io.new_project(NewProjectSpec(path=tmp_path / "刷多.stn", unit_names=["u"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    orm.session().add_all(
        [
            PcpEnclosure(name="围护B", order_no=1),
            PcpFoundation(name="地基B", order_no=1),
            PcpPrecipitation(name="降水B", order_no=1),
            PcpWidth(name="面宽B", order_no=1),
        ]
    )
    project_io.commit()
    src = _make_pipe(unit.id, "样板", dn=600)
    t1 = _make_pipe(unit.id, "目标1", dn=800)
    t2 = _make_pipe(unit.id, "目标2", dn=1000)
    unit_vm.update_element(
        src.id, pe_name="围护B", pf_name="地基B", pp_name="降水B", pw_name="面宽B"
    )

    panel = _panel_for(qapp, unit)
    _select_rows(panel, [_element_row(panel, src.id)])
    panel.set_format_painter(True)
    _select_rows(panel, [_element_row(panel, t1.id), _element_row(panel, t2.id)])
    assert panel._format_painter_active  # 防抖期内尚未生效
    panel._flush_format_painter()
    assert not panel._format_painter_active  # 一次生效后自动退出
    for element_id in (t1.id, t2.id):
        target = orm.session().get(Element, element_id)
        assert target.pe_name == "围护B" and target.pf_name == "地基B"
        assert target.pp_name == "降水B" and target.pw_name == "面宽B"
    # 退出后再选中别的构件不再自动刷
    _select_rows(panel, [_element_row(panel, t1.id)])
    assert not panel._format_painter_active


def test_format_painter_requires_source(qapp, tmp_path) -> None:
    """没有选中构件时开启格式刷：提示并自动弹起（信号 False）。"""
    project_io.new_project(NewProjectSpec(path=tmp_path / "空.stn", unit_names=["u"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    panel = _panel_for(qapp, unit)
    received: list[bool] = []
    panel.format_painter_changed.connect(received.append)
    panel.set_format_painter(True)
    assert not panel._format_painter_active
    assert received == [False]


# --------------------------------------------------------------------------- #
# 断面图跟随合槽成员
# --------------------------------------------------------------------------- #
def test_section_follows_group_member(qapp, two_unit_project) -> None:
    """选中合槽成员（含普通构件切换）时断面图分别画整槽 / 单管。"""
    from app.viewmodels.unit_vm import create_trench_group

    unit_a, _unit_b = two_unit_project
    e1 = _make_pipe(unit_a.id, "管A")
    e2 = _make_pipe(unit_a.id, "管B", dn=800, depth="4")
    group, _error = create_trench_group([e1.id, e2.id])
    assert group is not None
    standalone = _make_pipe(unit_a.id, "独立")

    panel = _panel_for(qapp, unit_a)
    canvas = panel._section_view._canvas
    panel._refresh_section_for(e1.id)
    assert canvas._group_id == group.id and canvas._element_id is None
    panel._refresh_section_for(standalone.id)
    assert canvas._element_id == standalone.id and canvas._group_id is None


def test_format_painter_copies_lr_format(qapp, tmp_path) -> None:
    """左右分设样板：格式刷把分设格式整体复制（占位 / 左右原则 / 支撑勾选）。"""
    from app.core.models.models import Element, LR_PE_TEXT, PcpEnclosure

    project_io.new_project(NewProjectSpec(path=tmp_path / "刷分设.stn", unit_names=["u"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    orm.session().add_all([PcpEnclosure(name="围护A", order_no=0), PcpEnclosure(name="围护B", order_no=1)])
    project_io.commit()
    src = _make_pipe(unit.id, "分设样板", dn=600)
    tgt = _make_pipe(unit.id, "目标", dn=800)
    unit_vm.update_element(
        src.id,
        pe_name=LR_PE_TEXT,
        pe_left_name="围护A",
        pe_right_name="围护B",
        support_left=True,
        support_right=False,
    )

    panel = _panel_for(qapp, unit)
    _select_rows(panel, [_element_row(panel, src.id)])
    panel.set_format_painter(True)
    _select_rows(panel, [_element_row(panel, tgt.id)])
    panel._flush_format_painter()

    target = orm.session().get(Element, tgt.id)
    assert target.pe_name == LR_PE_TEXT
    assert target.pe_left_name == "围护A"
    assert target.pe_right_name == "围护B"
    assert target.support_left is True
    assert target.support_right is False

    qapp.processEvents()  # 等刷完后的表格重载落地
    # 反向：普通单原则样板刷到分设构件 → 退出分设、清空左右原则
    single = _make_pipe(unit.id, "单原则样板", dn=1000)
    qapp.processEvents()
    unit_vm.update_element(single.id, pe_name="围护A")
    qapp.processEvents()
    _select_rows(panel, [_element_row(panel, single.id)])
    panel.set_format_painter(True)
    _select_rows(panel, [_element_row(panel, tgt.id)])
    panel._flush_format_painter()
    target = orm.session().get(Element, tgt.id)
    assert target.pe_name == "围护A"
    assert target.pe_left_name == "" and target.pe_right_name == ""
