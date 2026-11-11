"""合槽子构件「工作面宽」tab 与「与相邻构件中心距离」（v3.2）。

规则（用户口径）：

* 中心距离只有**共享面更浅一侧**可填；等深时填在左侧构件的右侧；
* 填了距离的一侧，该侧面宽原则匹配的工作面宽失效，按距离摆放构件；
  未填距离的一侧仍按面宽原则；
* 距离小于两构件外边线半径之和时报错；只校验半径和，浅构件允许侵入
  深构件的放坡范围之上（剩余宽度为负时剖面按 0 处理）。
"""

import pytest


# --------------------------------------------------------------------------- #
# 搭建助手
# --------------------------------------------------------------------------- #
def _first_unit_id():
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Unit

    return orm.session().scalar(select(Unit.id))


def _make_enclosure(name: str, category: str, slope: float | None = None):
    """按库模板建一条围护原则（单一做法）；slope 非空时把放坡系数设为该值。"""
    from app.core.models import base as orm
    from app.core.models.models import PcpEnclosure
    from app.services import project_io

    session = orm.session()
    pe = PcpEnclosure(name=name, order_no=90 + len(project_io.enclosures()))
    session.add(pe)
    session.flush()
    project_io.new_enclosure_work(
        session, pe, project_io.component_library(), order_no=0, level_name=category
    )
    if slope is not None:
        for param in pe.works_sorted()[0].levels[0].components[0].params:
            if param.key == "A":
                param.value = f"放坡系数 1:X|{slope}"
    project_io.commit()
    return pe


def _element(name: str, *, dn=600, depth="3", amount="120", pe_name=None):
    from app.viewmodels import unit_vm

    element = unit_vm.create_element(
        _first_unit_id(),
        category=1,
        name=name,
        depth=depth,
        amount=amount,
        pipes=[("Ⅱ级混凝土管", dn, "1")],
        pe_name=pe_name,
        seed_atlas_defaults=True,
    )
    assert element is not None
    return element.id


def _group(depths, *, amount="120", dn=600, prefix="构件"):
    """建 n 条等管径构件并编组，返回 (group, [element_id...])。"""
    from app.viewmodels import unit_vm

    elements = [
        _element(f"{prefix}{index + 1}", dn=dn, depth=str(depth), amount=amount)
        for index, depth in enumerate(depths)
    ]
    group, error = unit_vm.create_trench_group(elements)
    assert group is not None and error is None
    return group, elements


def _member_facts(element_id: int) -> dict:
    """构件几何快照（mm / m）：基础宽、工作面宽、槽深、外边线半径。"""
    from app.core.calc.trench_group import _resolve_member, member_outer_radius
    from app.core.models import base as orm
    from app.core.models.models import Element

    session = orm.session()
    element = session.get(Element, element_id)
    member, error = _resolve_member(session, element, require_amount=False)
    assert member is not None, error
    return {
        "base": member.base_width.v * 1000.0,
        "work": member.work_width.v * 1000.0,
        "depth": member.depth.v,
        "radius": member_outer_radius(member).v * 1000.0,
    }


def _group_results(group):
    from app.core.calc.trench_group import compute_group
    from app.core.models import base as orm

    group = orm.session().get(type(group), group.id)
    return compute_group(group)


def _value(result, key: str) -> float:
    quantity = result.get(key)
    assert quantity is not None, f"缺少定额行 {key}（现有：{result.keys()}）"
    return quantity.value


def _dig(element_id: int, results) -> float:
    return _value(results[element_id], "开挖|Ⅲ类土|m3")


# --------------------------------------------------------------------------- #
# 可填侧（规则 3 / 5）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("depths", "expected"),
    [
        # 3、2、4：只有中间的更浅构件两侧可填
        (["3", "2", "4"], [(False, False), (True, True), (False, False)]),
        # 3、4、2：左右两条构件各自靠中间侧可填
        (["3", "4", "2"], [(False, True), (False, False), (True, False)]),
        # 2、3、4：左侧两条构件各自与右侧构件距离可填
        (["2", "3", "4"], [(False, True), (False, True), (False, False)]),
        # 等深：填在左侧构件的右侧（规则 5）
        (["3", "3"], [(False, True), (False, False)]),
    ],
)
def test_distance_plan_follows_shallower_side(project, depths, expected) -> None:
    from app.core.calc.trench_group import group_distance_limits
    from app.viewmodels import unit_vm

    group, elements = _group(depths)
    plan = unit_vm.group_distance_plan(group.id)
    assert [plan[element_id] for element_id in elements] == expected
    # 可填侧能拿到限制；不可填侧拿不到（界面据此禁用输入）
    for element_id, (left_active, right_active) in zip(elements, expected):
        assert (group_distance_limits(group, element_id, "left") is not None) == left_active
        assert (group_distance_limits(group, element_id, "right") is not None) == right_active


def test_distance_plan_cleared_when_order_changes(project) -> None:
    """组内换序后旧的「指向某邻居」的距离清空，避免错位。"""
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group(["3", "3"])
    unit_vm.update_element(e1, center_distance_right="2000")
    orm.session().expire_all()
    assert orm.session().get(Element, e1).center_distance_right == "2000"

    unit_vm.move_element(e2, -1)  # 组内上移 = 左移，e1/e2 换位
    orm.session().expire_all()
    assert orm.session().get(Element, e1).center_distance_right == ""
    assert orm.session().get(Element, e2).center_distance_left == ""


# --------------------------------------------------------------------------- #
# 校验（规则 6）
# --------------------------------------------------------------------------- #
def test_validation_radius_uses_concrete_foundation_width(project) -> None:
    """点 1：砼基础构件的外边线半径 = 混凝土基础半宽（基础外皮），不是管外皮。"""
    element = _element("砼基础管", dn=600, depth="3")
    facts = _member_facts(element)
    assert facts["radius"] == pytest.approx(facts["base"] / 2, abs=1e-6)


def test_validation_radius_uses_pipe_outer_for_sand_foundation(project) -> None:
    """无砼基础：外边线半径 = 管道外皮半径（垂直切线），小于基础半宽。"""
    from app.services import project_io

    sand = project_io.create_foundation("砂基础原则")
    assert sand is not None
    sand.con_found = False
    project_io.commit()
    element = _element("砂基础管", dn=600, depth="3")
    from app.viewmodels import unit_vm

    unit_vm.update_element(element, pf_name=sand.name)
    facts = _member_facts(element)
    assert facts["radius"] == pytest.approx(360.0, abs=1e-6)  # (600 + 2×60)/2
    assert facts["radius"] < facts["base"] / 2 - 100  # 基础还含工作面加宽 a


def test_sand_foundation_intrusion_uses_pipe_outer_tangent(project) -> None:
    """点 2：无砼基础时，浅构件侵入侧边界收到管外皮切线（基础半宽 − a）。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.core.models import base as orm
    from app.services import project_io
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    sand = project_io.create_foundation("砂基础原则2")
    assert sand is not None
    sand.con_found = False
    project_io.commit()
    slope_pe = _make_enclosure("砂基础侵入放坡", "放坡", slope=0.5)
    pile_pe = _make_enclosure("砂基础侵入桩", "钢板桩")
    group, (e1, e2) = _group(["3", "4"])
    unit_vm.update_element(e1, pf_name=sand.name, pe_left_name=pile_pe.name)
    unit_vm.update_element(e2, pf_name=sand.name, pe_left_name=slope_pe.name)
    orm.session().expire_all()
    facts1, facts2 = _member_facts(e1), _member_facts(e2)
    r_sum, _neighbor = group_distance_limits(group, e1, "right")
    # 取两侧基础半宽之和 + 100mm：浅侧对称剩余宽度仍为负（侵入），但深侧基础
    # 边界在浅侧外边线右侧 100mm，避免基础本身重叠
    distance = facts1["base"] / 2 + facts2["base"] / 2 + 100
    assert distance > r_sum
    unit_vm.update_element(e1, center_distance_right=str(distance))
    results, errors = _group_results(group)
    assert not errors, errors
    # 浅侧共享侧边界 = 管外皮半径（不是基础半宽）；外侧仍保留自身工作面
    assert _dig(e1, results) == pytest.approx(
        (facts1["base"] / 2 + facts1["radius"] + facts1["work"])
        / 1000.0
        * facts1["depth"]
        * 120.0,
        rel=1e-9,
    )
    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None, hint
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    assert centers[e2] - centers[e1] == pytest.approx(distance / 1000.0, abs=1e-9)
    # 起坡点虚拟墙在浅构件的管外皮切线处
    wall = centers[e1] + facts1["radius"] / 1000.0
    assert scene.dashed_lines[0][0] == pytest.approx(wall, abs=1e-9)
    # 浅构件沟槽底边线画到该墙为止（管外皮切线，而不是基础边线）
    h_max = max(depth for _eid, _center, depth in scene.member_spans)
    y_shallow = h_max - facts1["depth"]
    assert any(
        abs(x - wall) <= 1e-9 and abs(y - y_shallow) <= 1e-9
        for x, y in scene.outline
    ), (wall, y_shallow, scene.outline)


def test_distance_validation_only_radius_sum(project) -> None:
    """只校验两构件外边线半径之和；相邻构件显示名 = 名称 + 规格。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group(["3", "3"])
    facts1, facts2 = _member_facts(e1), _member_facts(e2)
    radius_sum = facts1["radius"] + facts2["radius"]
    limits = group_distance_limits(group, e1, "right")
    assert limits is not None
    r_sum, neighbor = limits
    assert r_sum == pytest.approx(radius_sum, abs=1e-6)
    assert neighbor == "构件2 Ⅱ级混凝土管 DN600"

    assert unit_vm.distance_validation_error(e1, "right", "") is None
    error = unit_vm.distance_validation_error(e1, "right", str(r_sum - 1))
    assert error is not None and "半径之和" in error
    assert "构件2 Ⅱ级混凝土管 DN600" in error
    # 只校验半径和：略大于半径和即通过（不再要求容纳对侧工作面 / 放坡）
    assert unit_vm.distance_validation_error(e1, "right", str(r_sum + 1)) is None
    # 非可填侧（等深时右构件的左侧）拒绝
    error = unit_vm.distance_validation_error(e2, "left", str(r_sum + 1))
    assert error is not None and "可填" in error
    # 非法算式
    assert "数字" in (unit_vm.distance_validation_error(e1, "right", "abc") or "")

    # 没有构件名称时，括号里只显示规格
    unit_vm.update_element(e2, name="")
    _r_sum, label = group_distance_limits(group, e1, "right")
    assert label == "Ⅱ级混凝土管 DN600"


def test_distance_below_radius_sum_blocks_group_calc(project) -> None:
    """只有小于外边线半径之和才整组报错；略大于半径和允许（侵入放坡）。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group(["3", "3"])
    r_sum, _neighbor = group_distance_limits(group, e1, "right")

    unit_vm.update_element(e1, center_distance_right=str(r_sum - 1))
    results, errors = _group_results(group)
    assert results == {}
    assert errors and "半径之和" in next(iter(errors.values()))

    # 略大于半径和：不再报错（即使容纳不下对侧工作面 / 放坡）
    unit_vm.update_element(e1, center_distance_right=str(r_sum + 1))
    results, errors = _group_results(group)
    assert not errors, errors


# --------------------------------------------------------------------------- #
# 几何：填了距离的一侧按距离摆放，未填侧仍按工作面宽
# --------------------------------------------------------------------------- #
def test_distance_can_intrude_into_deep_slope(project) -> None:
    """距离略大于半径和：浅构件侵入深侧放坡范围，浅侧工作面按 0 处理，
    构件位置仍严格按填写的中心距离摆放。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.core.models import base as orm
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("侵入放坡原则", "放坡", slope=0.5)
    pile_pe = _make_enclosure("侵入桩原则", "钢板桩")
    group, (e1, e2) = _group(["3", "4"])
    # 浅构件左侧（合槽外边缘）用桩，便于精确断言；深侧用放坡
    unit_vm.update_element(e1, pe_left_name=pile_pe.name)
    unit_vm.update_element(e2, pe_left_name=slope_pe.name)
    orm.session().expire_all()
    facts1, facts2 = _member_facts(e1), _member_facts(e2)
    r_sum, _neighbor = group_distance_limits(group, e1, "right")
    # 半径和 + 1mm：容不下深侧工作面 + 放坡 → 浅侧剩余宽度为负（侵入）
    distance = r_sum + 1
    assert unit_vm.distance_validation_error(e1, "right", str(distance)) is None
    unit_vm.update_element(e1, center_distance_right=str(distance))
    results, errors = _group_results(group)
    assert not errors, errors
    # 浅侧共享侧按 0 处理：挖方 =（本体 + 外侧工作面）× 槽深 × 长度
    assert _dig(e1, results) == pytest.approx(
        (facts1["base"] + facts1["work"]) / 1000.0 * facts1["depth"] * 120.0, rel=1e-9
    )
    assert _dig(e2, results) > 0
    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None, hint
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    assert centers[e2] - centers[e1] == pytest.approx(distance / 1000.0, abs=1e-9)


def test_distance_can_intrude_into_deep_slope_left_deep(project) -> None:
    """左深（对称情形）：距离填在右（浅）构件的左侧，同样允许侵入放坡。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.core.models import base as orm
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("侵入放坡原则2", "放坡", slope=0.5)
    pile_pe = _make_enclosure("侵入桩原则2", "钢板桩")
    group, (e1, e2) = _group(["4", "3"])
    # 深侧（e1）右侧用放坡；浅侧（e2）右侧（合槽外边缘）用桩
    unit_vm.update_element(e1, pe_right_name=slope_pe.name)
    unit_vm.update_element(e2, pe_right_name=pile_pe.name)
    orm.session().expire_all()
    facts2 = _member_facts(e2)
    r_sum, _neighbor = group_distance_limits(group, e2, "left")
    distance = r_sum + 1
    assert unit_vm.distance_validation_error(e2, "left", str(distance)) is None
    unit_vm.update_element(e2, center_distance_left=str(distance))
    results, errors = _group_results(group)
    assert not errors, errors
    assert _dig(e2, results) == pytest.approx(
        (facts2["base"] + facts2["work"]) / 1000.0 * facts2["depth"] * 120.0, rel=1e-9
    )
    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None, hint
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    assert centers[e2] - centers[e1] == pytest.approx(distance / 1000.0, abs=1e-9)


def test_equal_depth_distance_extends_only_shallow_side(project) -> None:
    """等深：距离填在左构件右侧 → 左构件右侧工作面失效、按距离取剩余；
    右构件左侧仍按自身面宽原则，挖方只增在左构件。"""
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group(["3", "3"])
    facts1, facts2 = _member_facts(e1), _member_facts(e2)
    default_center = (
        facts1["base"] / 2 + facts1["work"] + facts2["work"] + facts2["base"] / 2
    )
    before, errors = _group_results(group)
    assert not errors
    dig1_before, dig2_before = _dig(e1, before), _dig(e2, before)

    distance = default_center + 500
    unit_vm.update_element(e1, center_distance_right=str(distance))
    after, errors = _group_results(group)
    assert not errors, errors
    height, length = facts1["depth"], 120.0
    assert _dig(e1, after) - dig1_before == pytest.approx(0.5 * height * length, rel=1e-9)
    assert _dig(e2, after) == pytest.approx(dig2_before, rel=1e-9)

    # 断面图按同一口径摆放：两构件本体中心距 = 填写的中心距离
    from app.views.panels.section_view import _build_group_scene

    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None, hint
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    assert centers[e2] - centers[e1] == pytest.approx(distance / 1000.0, abs=1e-9)


def test_unequal_depth_distance_keeps_deep_side_work_width(project) -> None:
    """右深：距离填在左（浅）构件右侧；深侧工作面 + 放坡不变，挖方只增浅侧。"""
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.viewmodels import unit_vm

    pile = _make_enclosure("距离桩原则", "钢板桩")
    group, (e1, e2) = _group(["3", "4"])
    # 深侧（e2）左侧改为桩：run = 0，便于精确对拍
    unit_vm.update_element(e2, pe_left_name=pile.name)
    orm.session().expire_all()
    facts1, facts2 = _member_facts(e1), _member_facts(e2)
    default_center = (
        facts1["base"] / 2 + facts1["work"] + facts2["work"] + facts2["base"] / 2
    )
    before, errors = _group_results(group)
    assert not errors
    dig1_before, dig2_before = _dig(e1, before), _dig(e2, before)

    distance = default_center + 500
    unit_vm.update_element(e1, center_distance_right=str(distance))
    after, errors = _group_results(group)
    assert not errors, errors
    assert _dig(e1, after) - dig1_before == pytest.approx(
        0.5 * facts1["depth"] * 120.0, rel=1e-9
    )
    assert _dig(e2, after) == pytest.approx(dig2_before, rel=1e-9)


def test_intrusion_quantity_split_below_and_above_shallow_bottom(project) -> None:
    """点 1：起坡点分隔下，深侧构件浅槽底以下按单沟槽完整计算，以上按虚拟墙
    （侵入时墙在坡顶以内）截断；浅侧构件只算自身基础 + 外侧工作面。"""
    from app.core.models import base as orm
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("侵入分层放坡", "放坡", slope=0.5)
    pile_pe = _make_enclosure("侵入分层桩", "钢板桩")
    group, (e1, e2) = _group(["3", "4"])
    # 浅侧左侧、深侧右侧都用桩（外侧只剩工作面），深侧左侧用放坡
    unit_vm.update_element(e1, pe_left_name=pile_pe.name)
    unit_vm.update_element(e2, pe_left_name=slope_pe.name, pe_right_name=pile_pe.name)
    orm.session().expire_all()
    shallow, deep = _member_facts(e1), _member_facts(e2)
    # 中心距 = 两侧基础半宽 + 100mm：浅侧对称剩余为负（侵入），深侧虚拟墙
    # 在深侧基础边外 100mm
    gap = 0.1
    distance = shallow["base"] / 2 + deep["base"] / 2 + 100
    unit_vm.update_element(e1, center_distance_right=str(distance))
    results, errors = _group_results(group)
    assert not errors, errors

    h_s, h_d = shallow["depth"], deep["depth"]
    delta = h_d - h_s
    run = delta * 0.5  # 单级放坡 1:0.5
    bs, bd = shallow["base"] / 1000.0, deep["base"] / 1000.0
    ws, wd = shallow["work"] / 1000.0, deep["work"] / 1000.0
    # 浅侧：本体 + 外侧工作面（侵入侧工作面 0）
    shallow_area = (bs + ws) * h_s
    # 深侧：浅槽底以下 = 本体 + 两侧工作面 + 放坡（单沟槽完整）；
    # 浅槽底以上 = 本体 + 外侧工作面 + 到虚拟墙的 gap
    deep_area = (
        (bd + 2 * wd) * delta
        + run * delta / 2.0
        + (bd + wd + gap) * h_s
    )
    assert _dig(e1, results) == pytest.approx(shallow_area * 120.0, rel=1e-9)
    assert _dig(e2, results) == pytest.approx(deep_area * 120.0, rel=1e-9)


def test_intrusion_term_geometry_matches_wall(project) -> None:
    """点 4：分项高亮几何与点 1 一致——深侧浅槽底以上截到虚拟墙，浅侧到外半径。"""
    from app.core.models import base as orm
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("侵入高亮放坡", "放坡", slope=0.5)
    pile_pe = _make_enclosure("侵入高亮桩", "钢板桩")
    group, (e1, e2) = _group(["3", "4"])
    unit_vm.update_element(e1, pe_left_name=pile_pe.name)
    unit_vm.update_element(e2, pe_left_name=slope_pe.name, pe_right_name=pile_pe.name)
    orm.session().expire_all()
    shallow, deep = _member_facts(e1), _member_facts(e2)
    gap = 0.1
    distance = shallow["base"] / 2 + deep["base"] / 2 + 100
    unit_vm.update_element(e1, center_distance_right=str(distance))
    results, errors = _group_results(group)
    assert not errors, errors
    bs, bd = shallow["base"] / 1000.0, deep["base"] / 1000.0
    delta = deep["depth"] - shallow["depth"]
    wall_from_deep_center = -(bd / 2 + gap)
    wall_from_shallow_center = bs / 2

    above_terms = 0
    for term in results[e2].get("开挖|Ⅲ类土|m3").terms:
        lo, _hi, l0, _r0, l1, _r1 = term.geometry
        if lo >= delta - 1e-9:
            above_terms += 1
            assert l0 == pytest.approx(wall_from_deep_center, abs=1e-9)
            assert l1 == pytest.approx(wall_from_deep_center, abs=1e-9)
    assert above_terms > 0
    for term in results[e1].get("开挖|Ⅲ类土|m3").terms:
        _lo, _hi, _l0, r0, _l1, r1 = term.geometry
        assert r0 == pytest.approx(wall_from_shallow_center, abs=1e-9)
        assert r1 == pytest.approx(wall_from_shallow_center, abs=1e-9)


def test_distance_with_sloped_deep_side(project) -> None:
    """深侧是放坡（run > 0）：默认中心距含放坡投影，填距离后浅侧取剩余、深侧不变。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.core.models import base as orm
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("距离放坡原则", "放坡", slope=0.5)
    group, (e1, e2) = _group(["3", "4"])
    unit_vm.update_element(e2, pe_left_name=slope_pe.name)
    orm.session().expire_all()
    facts1, facts2 = _member_facts(e1), _member_facts(e2)
    r_sum, _neighbor = group_distance_limits(group, e1, "right")
    # 默认中心距（未填距离）直接从断面场景取：两侧基础半宽 + 浅侧工作面 +
    # 深侧（工作面 + 放坡）
    scene0, hint0 = _build_group_scene(group.id, 400, 300)
    assert scene0 is not None, hint0
    centers0 = {element_id: center for element_id, center, _depth in scene0.member_spans}
    default_center = (centers0[e2] - centers0[e1]) * 1000.0
    assert default_center > r_sum

    before, errors = _group_results(group)
    assert not errors
    dig1_before, dig2_before = _dig(e1, before), _dig(e2, before)
    unit_vm.update_element(e1, center_distance_right=str(default_center + 300))
    after, errors = _group_results(group)
    assert not errors, errors
    assert _dig(e1, after) - dig1_before == pytest.approx(
        0.3 * facts1["depth"] * 120.0, rel=1e-9
    )
    assert _dig(e2, after) == pytest.approx(dig2_before, rel=1e-9)

    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None, hint
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    assert centers[e2] - centers[e1] == pytest.approx(
        (default_center + 300) / 1000.0, abs=1e-9
    )


def test_three_members_both_distances_on_middle(project) -> None:
    """三条构件（3、2、4）：中间构件左右两侧距离都可填，两侧各自按距离取剩余。"""
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.viewmodels import unit_vm

    pile = _make_enclosure("距离桩原则3", "钢板桩")
    group, (e1, e2, e3) = _group(["3", "2", "4"])
    # 两个相邻面的深侧都改桩（run = 0），便于精确对拍
    unit_vm.update_element(e1, pe_right_name=pile.name)
    unit_vm.update_element(e3, pe_left_name=pile.name)
    orm.session().expire_all()
    facts1, facts2, facts3 = (
        _member_facts(e1),
        _member_facts(e2),
        _member_facts(e3),
    )
    default_left = (
        facts1["base"] / 2 + facts1["work"] + facts2["work"] + facts2["base"] / 2
    )
    default_right = (
        facts2["base"] / 2 + facts2["work"] + facts3["work"] + facts3["base"] / 2
    )
    before, errors = _group_results(group)
    assert not errors
    dig2_before = _dig(e2, before)

    unit_vm.update_element(
        e2,
        center_distance_left=str(default_left + 300),
        center_distance_right=str(default_right + 400),
    )
    after, errors = _group_results(group)
    assert not errors, errors
    assert _dig(e2, after) - dig2_before == pytest.approx(
        0.7 * facts2["depth"] * 120.0, rel=1e-9
    )

    from app.views.panels.section_view import _build_group_scene

    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None, hint
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    assert centers[e2] - centers[e1] == pytest.approx((default_left + 300) / 1000.0, abs=1e-9)
    assert centers[e3] - centers[e2] == pytest.approx((default_right + 400) / 1000.0, abs=1e-9)


def test_distance_cleared_when_member_leaves_group(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.viewmodels import unit_vm

    group, (e1, e2, e3) = _group(["3", "3", "3"])
    unit_vm.update_element(e1, center_distance_right="2000")
    unit_vm.remove_from_group(e2)  # 剩两条，相邻关系变了
    orm.session().expire_all()
    assert orm.session().get(Element, e1).center_distance_right == ""
    assert orm.session().get(Element, e3).center_distance_left == ""


def test_unequal_depth_distance_on_right_member_left_side(project) -> None:
    """左深：距离填在右（浅）构件的左侧，深侧工作面 + 放坡不变。"""
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.viewmodels import unit_vm

    pile = _make_enclosure("距离桩原则2", "钢板桩")
    group, (e1, e2) = _group(["4", "3"])
    # 深侧（e1）右侧改为桩：run = 0
    unit_vm.update_element(e1, pe_right_name=pile.name)
    orm.session().expire_all()
    facts1, facts2 = _member_facts(e1), _member_facts(e2)
    default_center = (
        facts1["base"] / 2 + facts1["work"] + facts2["work"] + facts2["base"] / 2
    )
    before, errors = _group_results(group)
    assert not errors
    dig1_before, dig2_before = _dig(e1, before), _dig(e2, before)

    distance = default_center + 500
    unit_vm.update_element(e2, center_distance_left=str(distance))
    after, errors = _group_results(group)
    assert not errors, errors
    # 右（浅）构件的左侧取剩余宽度 → 其挖方增加；深侧不变
    assert _dig(e2, after) - dig2_before == pytest.approx(
        0.5 * facts2["depth"] * 120.0, rel=1e-9
    )
    assert _dig(e1, after) == pytest.approx(dig1_before, rel=1e-9)


# --------------------------------------------------------------------------- #
# 编解码 / 界面
# --------------------------------------------------------------------------- #
def test_distance_with_box_structures(project, qapp) -> None:
    """箱涵合槽：外边线半径取结构本体半宽（不含 a=100 工作加宽），距离照常生效。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    shallow = unit_vm.create_element(
        unit_id, category=3, name="距离箱涵1", depth="3", amount="40",
        seed_atlas_defaults=True,
    )
    deep = unit_vm.create_element(
        unit_id, category=3, name="距离箱涵2", depth="3", amount="40",
        seed_atlas_defaults=True,
    )
    group, error = unit_vm.create_trench_group([shallow.id, deep.id])
    assert group is not None and error is None
    facts1, facts2 = _member_facts(shallow.id), _member_facts(deep.id)
    assert facts1["radius"] < facts1["base"] / 2  # 外边线不含工作加宽
    limits = group_distance_limits(group, shallow.id, "right")
    assert limits is not None
    _r_sum, _neighbor = limits
    default_center = (
        facts1["base"] / 2 + facts1["work"] + facts2["work"] + facts2["base"] / 2
    )
    unit_vm.update_element(shallow.id, center_distance_right=str(default_center + 300))
    results, errors = _group_results(group)
    assert not errors, errors
    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None and scene.shapes, hint
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    assert centers[deep.id] - centers[shallow.id] == pytest.approx(
        (default_center + 300) / 1000.0, abs=1e-9
    )


def test_intrusion_with_center_split_modes(project) -> None:
    """侵入放坡 + 管中心 / 间距平分分隔：不报错、不产出负工程量。"""
    from app.core.calc.trench_group import group_distance_limits
    from app.core.models import base as orm
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    for split_mode in ("管中心分隔", "间距平分分隔"):
        slope_pe = _make_enclosure(f"侵入放坡{split_mode}", "放坡", slope=0.5)
        pile_pe = _make_enclosure(f"侵入桩{split_mode}", "钢板桩")
        group, (e1, e2) = _group(["3", "4"], prefix=f"{split_mode}侵入")
        unit_vm.update_element(e1, pe_left_name=pile_pe.name)
        unit_vm.update_element(e2, pe_left_name=slope_pe.name)
        unit_vm.update_group(group.id, split_mode=split_mode)
        orm.session().expire_all()
        r_sum, _neighbor = group_distance_limits(group, e1, "right")
        unit_vm.update_element(e1, center_distance_right=str(r_sum + 1))
        results, errors = _group_results(group)
        assert not errors, errors
        for element_id, quantities in results.items():
            for quantity in quantities.items():
                assert quantity.value >= -1e-6, (
                    split_mode,
                    element_id,
                    quantity.key,
                    quantity.value,
                )
        scene, hint = _build_group_scene(group.id, 400, 300)
        assert scene is not None, hint


def test_expression_dialog_highlight_matches_wall(project, qapp) -> None:
    """点 4：表达式窗体高亮块与工程量同口径——深侧浅槽底以上高亮到虚拟墙。"""
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from app.core.models import base as orm
    from app.views.dialogs.expression_detail_dialog import ExpressionDetailDialog
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("高亮放坡", "放坡", slope=0.5)
    pile_pe = _make_enclosure("高亮桩", "钢板桩")
    group, (e1, e2) = _group(["3", "4"])
    unit_vm.update_element(e1, pe_left_name=pile_pe.name)
    unit_vm.update_element(e2, pe_left_name=slope_pe.name, pe_right_name=pile_pe.name)
    orm.session().expire_all()
    shallow, deep = _member_facts(e1), _member_facts(e2)
    distance = shallow["base"] / 2 + deep["base"] / 2 + 100
    unit_vm.update_element(e1, center_distance_right=str(distance))
    results, errors = _group_results(group)
    assert not errors, errors
    delta = deep["depth"] - shallow["depth"]
    dig = results[e2].get("开挖|Ⅲ类土|m3")
    above = next(term for term in dig.terms if term.geometry[0] >= delta - 1e-9)

    dialog = ExpressionDetailDialog(None, dig, ("group", group.id, e2))
    dialog.show()
    QApplication.processEvents()
    QTest.qWait(100)
    QApplication.processEvents()
    scene = dialog._scene
    assert scene is not None
    polygon = dialog._highlight_polygon(above.geometry, e2)
    assert polygon
    wall = scene.dashed_lines[0][0]
    assert min(x for x, _y in polygon) == pytest.approx(wall, abs=1e-9)
    dialog.close()


def test_expression_dialog_layout_does_not_cover_formula(project, qapp) -> None:
    """点 5：窗口较矮时断面画布不能压住主算式文字（画布高度可伸缩）。"""
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from app.views.dialogs.expression_detail_dialog import ExpressionDetailDialog

    group, (e1, e2) = _group(["3", "3"])
    results, errors = _group_results(group)
    assert not errors, errors
    quantity = results[e1].get("开挖|Ⅲ类土|m3")
    dialog = ExpressionDetailDialog(None, quantity, ("group", group.id, e1))
    dialog.show()
    QApplication.processEvents()
    QTest.qWait(100)
    QApplication.processEvents()
    canvas_bottom = dialog._canvas.mapTo(
        dialog, dialog._canvas.rect().bottomLeft()
    ).y()
    formula_top = dialog._formula_label.mapTo(
        dialog, dialog._formula_label.rect().topLeft()
    ).y()
    assert canvas_bottom <= formula_top, (canvas_bottom, formula_top)
    assert dialog._formula_label.isVisible()
    dialog.close()


def test_middle_component_has_two_virtual_walls_and_bottom_within(project) -> None:
    """点 3：三条构件中间浅构件侵入两侧放坡；中间构件左右各一条虚拟墙，
    最左 / 最右各一条；沟槽底边线画到墙内（含中间构件的左右墙点）。"""
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    group, (e1, e2, e3) = _group(["4", "2", "4"])
    facts = [_member_facts(e1), _member_facts(e2), _member_facts(e3)]
    # 中间构件到左右邻的中心距 = 两侧基础半宽 + 100mm（浅侧对称剩余为负 → 侵入）
    left_distance = facts[0]["base"] / 2 + facts[1]["base"] / 2 + 100
    right_distance = facts[1]["base"] / 2 + facts[2]["base"] / 2 + 100
    unit_vm.update_element(
        e2,
        center_distance_left=str(left_distance),
        center_distance_right=str(right_distance),
    )
    results, errors = _group_results(group)
    assert not errors, errors
    scene, hint = _build_group_scene(group.id, 500, 400)
    assert scene is not None, hint
    assert len(scene.dashed_lines) == 2  # 中间构件左右各 1 条；最左 / 最右各 1 条
    centers = {element_id: center for element_id, center, _depth in scene.member_spans}
    half = facts[1]["base"] / 2000.0  # mm → m 的基础半宽（砼基础外边线）
    walls = sorted(line[0] for line in scene.dashed_lines)
    assert walls[0] == pytest.approx(centers[e2] - half, abs=1e-9)
    assert walls[1] == pytest.approx(centers[e2] + half, abs=1e-9)
    # 中间构件槽底的左右墙点都在沟槽底轮廓上（底边线画全到墙内）
    h_max = max(depth for _eid, _center, depth in scene.member_spans)
    y_middle = h_max - facts[1]["depth"]
    for wall in walls:
        assert any(
            abs(x - wall) <= 1e-9 and abs(y - y_middle) <= 1e-9
            for x, y in scene.outline
        ), (wall, y_middle, scene.outline)
    # 点 3：侵入浅构件在自己的槽底标高有一条完整分层线，贯穿左右两条虚拟墙
    bottom_lines = [
        line
        for line in scene.layer_lines
        if abs(line[1] - y_middle) <= 1e-9 and abs(line[3] - y_middle) <= 1e-9
    ]
    assert bottom_lines, scene.layer_lines
    line = bottom_lines[-1]
    assert min(line[0], line[2]) == pytest.approx(walls[0], abs=1e-9)
    assert max(line[0], line[2]) == pytest.approx(walls[1], abs=1e-9)


def test_intrusion_split_modes_use_virtual_line_and_conserve(project) -> None:
    """点 2：管中心 / 间距平分分隔以虚拟线为界分别计量，总量与起坡点分隔一致。"""
    from app.core.models import base as orm
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("分界计量放坡", "放坡", slope=0.5)
    pile_pe = _make_enclosure("分界计量桩", "钢板桩")
    group, (e1, e2) = _group(["3", "4"])
    unit_vm.update_element(e1, pe_left_name=pile_pe.name)
    unit_vm.update_element(e2, pe_left_name=slope_pe.name, pe_right_name=pile_pe.name)
    orm.session().expire_all()
    shallow, deep = _member_facts(e1), _member_facts(e2)
    distance = shallow["base"] / 2 + deep["base"] / 2 + 100
    unit_vm.update_element(e1, center_distance_right=str(distance))
    base_results, errors = _group_results(group)
    assert not errors, errors
    base_total = _dig(e1, base_results) + _dig(e2, base_results)

    for split_mode in ("管中心分隔", "间距平分分隔"):
        unit_vm.update_group(group.id, split_mode=split_mode)
        results, errors = _group_results(group)
        assert not errors, errors
        total = _dig(e1, results) + _dig(e2, results)
        assert total == pytest.approx(base_total, rel=1e-9)
        scene, hint = _build_group_scene(group.id, 500, 400)
        assert scene is not None, hint
        centers = {
            element_id: center for element_id, center, _depth in scene.member_spans
        }
        if split_mode == "管中心分隔":
            expected_wall = (centers[e1] + centers[e2]) / 2.0
        else:
            expected_wall = (
                centers[e1]
                + shallow["base"] / 2000.0
                + centers[e2]
                - deep["base"] / 2000.0
            ) / 2.0
        assert scene.dashed_lines[0][0] == pytest.approx(expected_wall, abs=1e-9)
    unit_vm.update_group(group.id, split_mode="起坡点分隔")


def test_distance_with_center_split_mode(project) -> None:
    """中心距离与「管中心分隔 / 间距平分分隔」叠加：分界锚点按新的构件位置算。"""
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    for split_mode in ("管中心分隔", "间距平分分隔"):
        group, (e1, e2) = _group(["3", "3"], prefix=f"{split_mode}构件")
        unit_vm.update_group(group.id, split_mode=split_mode)
        facts1, facts2 = _member_facts(e1), _member_facts(e2)
        default_center = (
            facts1["base"] / 2 + facts1["work"] + facts2["work"] + facts2["base"] / 2
        )
        unit_vm.update_element(e1, center_distance_right=str(default_center + 500))
        results, errors = _group_results(group)
        assert not errors, errors
        scene, hint = _build_group_scene(group.id, 400, 300)
        assert scene is not None, hint
        centers = {element_id: center for element_id, center, _depth in scene.member_spans}
        assert centers[e2] - centers[e1] == pytest.approx(
            (default_center + 500) / 1000.0, abs=1e-9
        )


def test_distance_stn_roundtrip(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.services import project_io, stn_codec
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group(["3", "3"])
    unit_vm.update_element(e1, center_distance_right="1000+500")
    results, errors = _group_results(group)
    assert not errors, errors  # 算式距离参与计算

    data = stn_codec.dump_database()
    element_data = next(
        item
        for item in data["segments"][0]["units"][0]["elements"]
        if item["name"] == "构件1"
    )
    assert element_data["center_distance_right"] == "1000+500"
    assert "center_distance_left" not in element_data

    path = project_io.current_path()
    project_io.close_project()
    project_io.open_project(path)
    session = orm.session()
    restored = next(element for element in session.query(Element).all() if element.name == "构件1")
    assert restored.center_distance_right == "1000+500"
    assert restored.center_distance_left == ""


def test_group_snapshot_preserves_distance_but_single_copy_clears(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group(["3", "3"])
    unit_vm.update_element(e1, center_distance_right="2000")
    # 整组复制：成员顺序 / 邻居不变，中心距离保留
    snapshot = unit_vm.group_snapshot(group.id)
    assert snapshot is not None
    assert snapshot["members"][0]["center_distance_right"] == "2000"
    new_group = unit_vm.insert_group_data(_first_unit_id(), snapshot)
    assert new_group is not None
    new_members = sorted(new_group.members, key=lambda item: (item.order_no, item.id))
    assert new_members[0].center_distance_right == "2000"

    # 单条复制到组外：共享面不存在，中心距离清空
    single = unit_vm.element_copy_snapshot(e1)
    assert single is not None
    assert single["center_distance_right"] == ""


def test_distance_editor_commit_via_enter(project, qapp) -> None:
    """输入框按 Enter 提交：editingFinished 接线正常，合法值写库并重载。"""
    from sqlalchemy import select

    from app.core.calc.trench_group import group_distance_limits
    from app.core.models import base as orm
    from app.core.models.models import Element, Unit
    from app.viewmodels.project_vm import TreeNode
    from app.views.panels.unit_panel import UnitPanel, _select_row
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    group, (e1, e2) = _group(["3", "3"])
    panel = UnitPanel()
    panel.resize(1400, 800)
    unit = orm.session().scalar(select(Unit))
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))
    panel.refresh()
    table = panel._element_table
    row = next(index for index in range(table.rowCount()) if panel._element_id_at(index) == e1)
    _select_row(table, row, 0)
    panel._sync_detail_to_selection()
    editor = panel._distance_table.cellWidget(3, 0)
    assert editor is not None and editor.isEnabled()
    r_sum, _neighbor = group_distance_limits(group, e1, "right")
    editor.setText(str(r_sum + 200))
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()
    QTest.qWait(30)
    QApplication.processEvents()
    orm.session().expire_all()
    assert orm.session().get(Element, e1).center_distance_right == str(r_sum + 200)


def test_distance_tab_ui_and_validation(project, qapp, monkeypatch) -> None:
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element, Unit
    from app.viewmodels.project_vm import TreeNode
    from app.viewmodels import unit_vm
    from app.views.panels import unit_panel as unit_panel_module
    from app.views.panels.unit_panel import UnitPanel, _select_row

    group, (e1, e2) = _group(["3", "3"])
    panel = UnitPanel()
    panel.resize(1400, 800)
    unit = orm.session().scalar(select(Unit))
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))
    panel.refresh()
    table = panel._element_table
    row1 = next(row for row in range(table.rowCount()) if panel._element_id_at(row) == e1)
    _select_row(table, row1, 0)
    panel._sync_detail_to_selection()

    # 页签在「围护原则」右边
    assert panel._detail_tabs.tabText(3) == "围护原则"
    assert panel._detail_tabs.tabText(4) == "工作面宽"
    assert panel._distance_table.rowCount() == 4
    assert [
        panel._distance_table.verticalHeaderItem(row).text() for row in range(4)
    ] == [
        "左侧工作面宽(mm)",
        "右侧工作面宽(mm)",
        "与左侧构件中心距离(mm)",
        "与右侧构件中心距离(mm)",
    ]
    # 等深：左构件左侧是外边缘（不可填），右侧共享面可填
    from PySide6.QtWidgets import QLineEdit

    left_editor = panel._distance_table.cellWidget(2, 0)
    right_editor = panel._distance_table.cellWidget(3, 0)
    # 不可填的一侧统一显示成只含 "-" 的禁用文本框（9961e9d 由禁用下拉框改来）
    assert isinstance(left_editor, QLineEdit)
    assert not left_editor.isEnabled() and left_editor.text() == "-"
    assert right_editor.isEnabled() and isinstance(right_editor, QLineEdit)
    assert panel._distance_table.item(0, 0).text() not in ("", "-")

    # 合法距离：写库
    from app.core.calc.trench_group import group_distance_limits

    limits = group_distance_limits(group, e1, "right")
    r_sum, _neighbor = limits
    right_editor.setText(str(r_sum + 100))
    panel._on_distance_edited(e1, "right", right_editor)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest

    QApplication.processEvents()
    QTest.qWait(30)
    QApplication.processEvents()
    orm.session().expire_all()
    assert orm.session().get(Element, e1).center_distance_right == str(r_sum + 100)
    # 填了距离的一侧：工作面宽行标注已失效（重新装填后的表格）
    assert panel._distance_table.item(1, 0).text().endswith("（已失效）")

    # 小于半径和：弹窗提示且不写库（还原原值）
    warnings: list[tuple] = []
    monkeypatch.setattr(
        unit_panel_module.FramelessMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: warnings.append(args)),
    )
    QApplication.processEvents()
    row1 = next(row for row in range(table.rowCount()) if panel._element_id_at(row) == e1)
    _select_row(table, row1, 0)
    panel._sync_detail_to_selection()
    editor = panel._distance_table.cellWidget(3, 0)
    assert editor.isEnabled()
    current = orm.session().get(Element, e1).center_distance_right
    editor.setText(str(r_sum - 1))
    panel._on_distance_edited(e1, "right", editor)
    assert warnings and "半径之和" in warnings[0][2]
    orm.session().expire_all()
    assert orm.session().get(Element, e1).center_distance_right == current
    assert editor.text() == current

    # 埋深改变后重载：更浅侧翻到右构件，其左侧可填
    unit_vm.update_element(e1, depth="4")
    panel.refresh()
    QApplication.processEvents()
    row2 = next(row for row in range(table.rowCount()) if panel._element_id_at(row) == e2)
    _select_row(table, row2, 0)
    panel._sync_detail_to_selection()
    assert panel._distance_table.cellWidget(2, 0).isEnabled()
    assert not panel._distance_table.cellWidget(3, 0).isEnabled()

    # 非合槽子构件：表格收起、显示占位说明
    standalone = _element("组外构件", depth="3", amount="120")
    panel.refresh()
    QApplication.processEvents()
    row = next(row for row in range(table.rowCount()) if panel._element_id_at(row) == standalone)
    _select_row(table, row, 0)
    panel._sync_detail_to_selection()
    assert panel._distance_table.rowCount() == 0
    assert panel._distance_table.isHidden()
    assert not panel._distance_placeholder.isHidden()


def test_distance_tab_cell_widgets_follow_rows(project, qapp) -> None:
    """合槽编组后反复重填：单元格控件必须留在各自行，不能残留叠在第 0 行。

    实测（插构件 → 选中两行编组合槽 → 选子构件）：模型重置会把 setCellWidget
    的控件从 persistent 表里摘掉，旧控件留在视口里继续显示；重填的控件又可能
    按重置前的旧行位置摆放——表现为「与左侧构件中心距离」的禁用下拉框画到了
    「左侧工作面宽」那一行。
    """
    from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Unit
    from app.services.element_library import element_library
    from app.viewmodels.project_vm import TreeNode
    from app.views.panels.unit_panel import UnitPanel, _select_row

    panel = UnitPanel()
    panel.resize(1400, 800)
    unit = orm.session().scalar(select(Unit))
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))
    panel.refresh()
    panel.show()
    try:
        template = element_library().units_of("直埋混凝土管")[0].elements[0]
        panel.insert_template(template)
        panel.insert_template(template)
        for _ in range(3):
            qapp.processEvents()

        table = panel._element_table
        _select_row(table, 0, 0)
        table.selectionModel().select(
            table.model().index(1, 0),
            table.selectionModel().SelectionFlag.Select
            | table.selectionModel().SelectionFlag.Rows,
        )
        panel.create_group_from_selection()
        for _ in range(3):
            qapp.processEvents()
        panel._detail_tabs.setCurrentIndex(4)
        for _ in range(3):
            qapp.processEvents()

        distance_table = panel._distance_table
        member_rows = [
            row
            for row in range(table.rowCount())
            if panel._element_id_at(row) is not None
        ]
        assert member_rows, "编组后应有合槽子构件行"
        for member_row in member_rows:
            _select_row(table, member_row, 0)
            panel._sync_detail_to_selection()
            for _ in range(3):
                qapp.processEvents()
            for row in range(distance_table.rowCount()):
                widget = distance_table.cellWidget(row, 0)
                if widget is None:
                    continue
                cell = distance_table.visualRect(distance_table.model().index(row, 0))
                assert widget.geometry() == cell, f"第 {row} 行控件没在单元格里"
            # 视口里不能有可见的残留控件（旧控件会叠在第 0 行上）
            cells = {
                distance_table.cellWidget(row, 0)
                for row in range(distance_table.rowCount())
            }
            stray = [
                child
                for child in distance_table.viewport().children()
                if isinstance(child, (QComboBox, QLineEdit, QCheckBox))
                and child not in cells
                and child.isVisible()
            ]
            assert not stray, f"单元格里有 {len(stray)} 个残留控件"
    finally:
        panel.close()


def test_fit_cell_widgets_repairs_misplaced_widget(project, qapp) -> None:
    """``fit_cell_widgets()`` 能把按旧行位置摆放的单元格控件铺回自己的单元格。

    实测 ``setRowCount`` 之后行列位置还是旧的，``setCellWidget`` 会把控件放在
    第 0 行（32px 行里控件跑到别的行）；重填后调用一次就能纠正。
    """
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Unit
    from app.viewmodels.project_vm import TreeNode
    from app.views.panels.unit_panel import UnitPanel, _select_row

    _, (e1, _e2) = _group(["3", "3"])
    panel = UnitPanel()
    panel.resize(1400, 800)
    unit = orm.session().scalar(select(Unit))
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))
    panel.refresh()
    table = panel._element_table
    row = next(row for row in range(table.rowCount()) if panel._element_id_at(row) == e1)
    _select_row(table, row, 0)
    panel._sync_detail_to_selection()
    panel.show()
    try:
        for _ in range(3):
            qapp.processEvents()
        distance_table = panel._distance_table
        editor = distance_table.cellWidget(2, 0)
        assert editor is not None
        # 模拟 setCellWidget 按重置前的旧行位置摆放（落在第 0 行）
        editor.setGeometry(0, 0, 199, 31)
        distance_table.fit_cell_widgets()
        cell = distance_table.visualRect(distance_table.model().index(2, 0))
        assert editor.geometry() == cell
    finally:
        panel.close()


def test_distance_editor_fills_cell(project, qapp) -> None:
    """「工作面宽」页的中心距离控件必须铺满单元格，文字才不会被裁。

    QSS 给 ``QTableWidget::item`` 的 padding（5px 8px）会让 setCellWidget 放进去
    的控件只占「单元格内容区」：32px 的行里只剩 21px 高；再叠加 QLineEdit 自身
    的 6px 纵向内边距 + 1px 边框，文字区只剩 7px（字体需要 17px）——表现为文本框
    没撑满单元格、输入的文字上下被裁掉。不可填的一侧是只含 "-" 的禁用文本框。
    """
    from PySide6.QtWidgets import QStyle, QStyleOptionFrame
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Unit
    from app.resources.qss.theme import ThemeManager, build_stylesheet
    from app.viewmodels.project_vm import TreeNode
    from app.views.panels.unit_panel import UnitPanel, _select_row

    _, (e1, _e2) = _group(["3", "3"])
    panel = UnitPanel()
    panel.resize(1400, 800)
    unit = orm.session().scalar(select(Unit))
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))
    panel.refresh()
    table = panel._element_table
    row = next(row for row in range(table.rowCount()) if panel._element_id_at(row) == e1)
    _select_row(table, row, 0)
    panel._sync_detail_to_selection()
    panel._detail_tabs.setCurrentIndex(4)

    # 测试环境没有全局主题：把真实主题 QSS 套到本页表格上，复现单元格内边距
    distance_table = panel._distance_table
    distance_table.setStyleSheet(build_stylesheet(ThemeManager.instance().current()))
    panel.show()
    try:
        for _ in range(3):
            qapp.processEvents()
        for row_index in (2, 3):
            editor = distance_table.cellWidget(row_index, 0)
            assert editor is not None
            cell = distance_table.visualRect(distance_table.model().index(row_index, 0))
            assert editor.geometry() == cell, "单元格控件没有铺满单元格"
            option = QStyleOptionFrame()
            editor.initStyleOption(option)
            band = editor.style().subElementRect(
                QStyle.SubElement.SE_LineEditContents, option, editor
            )
            assert band.height() >= editor.fontMetrics().height(), (
                f"文字区只有 {band.height()}px，字体需要 {editor.fontMetrics().height()}px"
            )
    finally:
        panel.close()
