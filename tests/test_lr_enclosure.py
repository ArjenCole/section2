"""左右分设与合槽编组（v3）的计算与操作测试。

金样例口径（docs/lr_enclosure_and_trench_group_design.md）：

* 分设对称退化：左右同原则时，挖方 / 回填 / 围护 / 支撑 数值与普通单原则
  构件一致（不对称几何与 sides=1 的每面调用在两侧同形时收敛回对称路径）；
* 左坡右桩手算：挖方 = (2B+H*sL)*H/2（B/H 由图集与宽度表的**原始值**独立
  组合，不用被测逻辑算结果）；桩量 = ⌈L/桩距⌉×桩长×单重（×1 单面）；
* 合槽等深守恒：两侧直壁时 Σ成员挖方 = 平底宽 × H × L（精确矩形），
  平底宽 = Σ本体 + 2×（各构件自身工作面宽）；
* 合槽异深：浅侧构件自身工作面 + 深侧放坡（坡到浅槽底），深侧构件另得
  浅槽底以上的竖直条带；中间坡围护量挂深侧；挖填拆分以浅侧虚拟垂直围护
  为界；
* 父节点零工程量、不持有围护 / 面宽原则；降水逐构件挂各自名下。
"""

import math

import pytest

from app.core.evaluator import evaluate


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


def _compute(element_id: int):
    from app.core.calc.engine import (
        build_element_input,
        compute_element,
        resolve_element_principles,
    )
    from app.core.models import base as orm
    from app.core.models.models import Element

    session = orm.session()
    element = session.get(Element, element_id)
    pe, pf, pp, pw = resolve_element_principles(element, session)
    info = build_element_input(element, pe, pf, pp, pw)
    result = compute_element(info)
    assert result is not None
    return result


def _value(result, key: str) -> float:
    quantity = result.get(key)
    assert quantity is not None, f"缺少定额行 {key}（现有：{result.keys()}）"
    return quantity.value


def _make_lr(element_id: int, left: str, right: str):
    from app.core.models.models import LR_PE_TEXT
    from app.viewmodels import unit_vm

    unit_vm.update_element(element_id, pe_name=LR_PE_TEXT)
    unit_vm.update_element(element_id, pe_left_name=left, pe_right_name=right)
    return element_id


# --------------------------------------------------------------------------- #
# 库模板 sides 代入
# --------------------------------------------------------------------------- #
def test_library_templates_use_sides_variable() -> None:
    """库模板的两侧因子已变量化，支撑拆成 贯通行 + 围檩行（同定额键）。"""
    from app.services.atlas import component_library

    lib = component_library()
    pile = lib.template("Ei", "钢板桩")
    assert pile.params["FA"][1].endswith("*sides")
    assert lib.template("Ei", "横列板").params["FA"][1] == "1*sides*height"
    # FB = 贯通支撑（无 sides）、FC = 围檩（含 sides），display 同键合并
    assert pile.params["FB"][1] == "ROUND(count/G,0)/count*F*width*H/1000"
    assert pile.params["FC"][1] == "1*sides*2*F*I/1000"
    assert pile.params["FC"][0] == pile.params["FB"][0] == "支撑|钢支撑、钢围檩|t"


def test_normal_element_formula_output_matches_legacy(project) -> None:
    """普通单原则构件：新模板 sides=2 代入后输出算式与旧版 *2 逐字节一致。"""
    from app.core.models import base as orm
    from app.core.models.models import EnclosureWork
    from app.services import project_io

    session = orm.session()
    pe = project_io.enclosures()[0]
    project_io.set_work_category(
        session, pe.works_sorted()[0], project_io.component_library(), "钢板桩"
    )
    project_io.commit()

    element_id = _element("普通钢板桩", pe_name=pe.name)
    result = _compute(element_id)
    assert "*2" in result.get("围护|拉森钢板桩|t").expression
    assert "sides" not in result.get("围护|拉森钢板桩|t").expression


# --------------------------------------------------------------------------- #
# 左右分设计算
# --------------------------------------------------------------------------- #
def test_lr_symmetric_matches_single(project) -> None:
    """左右同原则 = 对称退化：各定额行数值与普通单原则构件一致。"""
    pe = _make_enclosure("对称测试原则", "钢板桩")
    single = _compute(_element("普通", pe_name=pe.name))
    lr = _compute(_make_lr(_element("分设", pe_name=pe.name), pe.name, pe.name))
    assert set(single.keys()) == set(lr.keys())
    for key in single.keys():
        assert single.get(key).value == pytest.approx(lr.get(key).value, rel=1e-9), key


def test_lr_slope_left_pile_right_hand_calc(project) -> None:
    """左放坡 1:0.5、右钢板桩：不对称梯形 + 单面桩量手算对拍。"""
    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        choice_work,
        resolve_element_principles,
    )
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.services.atlas import resolve_atlas

    slope_pe = _make_enclosure("左坡1:0.5", "放坡", slope=0.5)
    pile_pe = _make_enclosure("右桩", "钢板桩")

    element_id = _make_lr(_element("左坡右桩", pe_name=slope_pe.name), slope_pe.name, pile_pe.name)
    result = _compute(element_id)

    # 原始输入（图集 / 宽度表值）独立组合出手算基准
    session = orm.session()
    element = session.get(Element, element_id)
    _pe, pf, pp, pw = resolve_element_principles(element, session)
    info = build_element_input(element, slope_pe, pf, pp, pw)  # 挖填取 pp、基础取 pf
    at = resolve_atlas(build_atlas_query(info, pf, pw))
    bottom = info.size_b + (at.t * 2 + at.a * 2 + at.workwidth * 2) / 1000
    depth = info.depth + (at.t + at.c1) / 1000  # 无换填

    # 挖方 = (2B + H*0.5)*H/2（右侧直壁项省略）；分层求和与整槽一条等价
    dig = _value(result, f"开挖|{pp.excvt}|m3")
    assert dig == pytest.approx((2 * bottom + depth * 0.5) * depth / 2 * info.amount, rel=1e-9)
    # 右侧直壁：算式里只有左坡项（(H)*0.5 形式，不出现右坡项）
    assert "*0.5)" in result.get(f"开挖|{pp.excvt}|m3").expression

    # 桩量 = ⌈L/桩距⌉×桩长×单重（×1 单面；桩距 400、桩长 12、单重 75）
    pile = _value(result, "围护|拉森钢板桩|t")
    expected = math.floor(120 / 0.4 + 0.5) / 120 * 12 * 75 / 1000 * 1 * 120
    assert pile == pytest.approx(expected, rel=1e-9)


def test_lr_support_flags(project) -> None:
    """支撑勾选语义：右单勾 = 贯通支撑 + 单侧围檩；两侧勾 = 单原则总量。"""
    from app.viewmodels import unit_vm

    pile_pe = _make_enclosure("支撑勾选原则", "钢板桩")
    single = _compute(_element("单原则基准", pe_name=pile_pe.name))
    single_support = _value(single, "支撑|钢支撑、钢围檩|t")  # = 贯通支撑 S + 两侧围檩 2W

    element_id = _make_lr(_element("支撑测试", pe_name=pile_pe.name), pile_pe.name, pile_pe.name)
    unit_vm.update_element(element_id, support_left=False, support_right=True)
    right_only = _compute(element_id)
    ro = _value(right_only, "支撑|钢支撑、钢围檩|t")  # = S + W

    unit_vm.update_element(element_id, support_left=True)
    both = _compute(element_id)
    bo = _value(both, "支撑|钢支撑、钢围檩|t")

    # 单侧围檩（W）手算：1×1侧×2×2道×38.49kg/m（每延米）×L
    wale = 1 * 1 * 2 * 2 * 38.49 / 1000 * 120
    strut = single_support - 2 * wale
    assert ro == pytest.approx(strut + wale, rel=1e-9)  # 贯通支撑整槽一次 + 右侧围檩
    assert bo == pytest.approx(single_support, rel=1e-9)  # 两侧勾 = 单原则总量
    # 两侧都不勾 → 没有支撑量
    unit_vm.update_element(element_id, support_left=False, support_right=False)
    none_checked = _compute(element_id)
    assert none_checked.get("支撑|钢支撑、钢围檩|t") is None


def test_lr_excvt_and_foundation_from_pp_and_pf(project) -> None:
    """v10：挖填类型归挖填降水原则、管道基础归地基原则，不再随左右围护分侧。

    构件引用哪条挖填降水 / 地基原则，回填材质与图集基础参数（垫层 / 角度）
    就跟着走；改左右围护不影响这两项（故不再有「取侧」概念）。
    """
    from app.services import project_io
    from app.services.principle_edit import apply_foundation, apply_precipitation_excavation
    from app.viewmodels import unit_vm

    left_pe = _make_enclosure("左侧原则", "放坡", slope=0.5)
    right_pe = _make_enclosure("右侧原则", "放坡", slope=0.75)

    # 新建挖填降水 / 地基原则，材质 / 垫层 / 角度全部与默认区分开
    pp = project_io.create_precipitation("明细挖填原则")
    apply_precipitation_excavation(
        pp.id,
        {"dock_l": "右侧砂", "dock_h": "右侧砂", "cover50": "右侧管顶砂", "cover": "右侧覆土"},
    )
    pf = project_io.create_foundation("明细地基原则")
    apply_foundation(
        pf.id,
        fields={"found_angle": 180},
        cushions=[{"name": "右侧垫层", "h": 300.0}],
    )
    assert pp is not None and pf is not None

    element_id = _make_lr(_element("取侧测试", pe_name=left_pe.name), left_pe.name, right_pe.name)
    before = _compute(element_id)
    assert before.get("回填|右侧砂|m3") is None  # 仍引用默认挖填降水原则

    # 改引用到新原则 → 回填材质、垫层名、图集基础参数跟着走（与左右围护无关）
    unit_vm.update_element(element_id, pp_name=pp.name, pf_name=pf.name)
    after = _compute(element_id)
    assert after.get("回填|右侧砂|m3") is not None
    assert after.get("回填|右侧管顶砂|m3") is not None
    assert after.get("回填|右侧覆土|m3") is not None
    assert after.get("垫层|右侧垫层|m3") is not None
    # 左右坡不同 → 挖方数值 ≠ 对称（两侧都 0.5 的对称基准）
    symmetric = _compute(_make_lr(_element("对称基准", pe_name=left_pe.name), left_pe.name, left_pe.name))
    assert _value(after, f"开挖|{pp.excvt}|m3") != pytest.approx(
        _value(symmetric, f"开挖|{pp.excvt}|m3")
    )


# --------------------------------------------------------------------------- #
# 合槽编组：计算
# --------------------------------------------------------------------------- #
def _group_fixture(project, depth2="3", dn2=600, member1_pe=None):
    """建双管合槽（同管径等参数便于精确对拍），返回 (group, 成员 element 列表)。"""
    from app.viewmodels import unit_vm

    pile_pe = _make_enclosure("合槽桩原则", "钢板桩")
    member1_pe = member1_pe or pile_pe
    e1 = _element("合槽左管", dn=600, depth="3", amount="120", pe_name=member1_pe.name)
    e2 = _element("合槽右管", dn=dn2, depth=depth2, amount="120", pe_name=pile_pe.name)
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    return group, [e1, e2]


def _group_results(group):
    from app.core.models import base as orm
    from app.core.calc.trench_group import compute_group

    group = orm.session().get(type(group), group.id)
    return compute_group(group)


def test_group_equal_depth_flat_dig(project) -> None:
    """等深 + 全直壁（两侧相邻面强制 "-"）：Σ成员挖方 = 平底宽×H×L。

    平底 = 首构件工作面 + 本体 + （右构件自身工作面 + 左构件工作面）+ 本体
    + 末构件工作面；各构件挖方 = （本体 + 2×自身工作面）× H × L。
    """
    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        workwidth_of,
    )
    from app.core.calc.measures import foundation_thickness as fd
    from app.core.models import base as orm
    from app.core.models.models import (
        Element,
        PcpEnclosure,
        PcpFoundation,
        PcpWidth,
    )
    from app.services.atlas import resolve_atlas
    from sqlalchemy import select

    group, (e1, e2) = _group_fixture(project)
    results, errors = _group_results(group)
    assert not errors, errors

    session = orm.session()
    geometry = []
    for element_id in (e1, e2):
        element = session.get(Element, element_id)
        pw = session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
        pe = session.scalars(
            select(PcpEnclosure).where(PcpEnclosure.name == element.pe_right_name)
        ).first()
        pf = session.scalars(
            select(PcpFoundation).where(PcpFoundation.name == element.pf_name)
        ).first()
        info = build_element_input(element, pe, pf, pw=pw)
        ad = atlas_dims(info, resolve_atlas(build_atlas_query(info, pf, pw)))
        geometry.append(
            {
                "b": info.size_b + ad.t.v * 2 + ad.a.v * 2,
                "h": info.depth + fd(pf).v / 1000 + ad.t.v + ad.c1.v,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    b1, b2 = g1["b"], g2["b"]
    w1, w2 = g1["ww"], g2["ww"]
    # 父节点不持有面宽原则：首 / 末构件各用自己的 PW 工作面；相邻区 = w1 + w2
    flat = b1 + b2 + 2 * w1 + 2 * w2
    # 等深断言（同管径 → 同图集参数）
    assert g1["h"] == pytest.approx(g2["h"], abs=1e-9)
    depth = g1["h"]

    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    assert dig1 + dig2 == pytest.approx(flat * depth * 120, rel=1e-9)
    # 挖填拆分：等深相邻面为虚拟垂直空围护，各构件 = 本体 + 自身两侧工作面
    assert dig1 == pytest.approx((b1 + 2 * w1) * depth * 120, rel=1e-9)
    assert dig2 == pytest.approx((b2 + 2 * w2) * depth * 120, rel=1e-9)
    # 分项几何：等深平槽各分层段左右缘 = ±(本体半宽 + 自身工作面)，合深覆盖全槽
    dig_terms = results[e1].get("开挖|Ⅲ类土|m3").terms
    assert dig_terms[0].geometry[0] == 0.0
    assert dig_terms[-1].geometry[1] == pytest.approx(depth)
    half_span = b1 / 2 + w1
    for term in dig_terms:
        _h0, _h1, l0, r0, l1, r1 = term.geometry
        assert (l0, r0) == (pytest.approx(-half_span), pytest.approx(half_span))
        assert (l1, r1) == (pytest.approx(-half_span), pytest.approx(half_span))
    # 父节点零工程量：输出只挂在成员名下
    assert set(results) == {e1, e2}


def test_group_precipitation_per_member(project) -> None:
    """降水逐构件：两成员各有一条湿土排水（默认井型阈值不适用时）。"""
    group, (e1, e2) = _group_fixture(project)
    results, errors = _group_results(group)
    assert not errors, errors
    assert results[e1].get("降水|湿土排水|m3") is not None
    assert results[e2].get("降水|湿土排水|m3") is not None


def test_group_different_depth_mid_slope(project) -> None:
    """异深中间坡：浅侧自身工作面 + 深侧竖直隔断（桩）；中间坡围护量挂深侧。"""
    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        workwidth_of,
    )
    from app.core.calc.measures import foundation_thickness as fd
    from app.core.models import base as orm
    from app.core.models.models import Element, PcpEnclosure, PcpFoundation, PcpWidth
    from app.services.atlas import resolve_atlas
    from sqlalchemy import select
    from app.viewmodels import unit_vm

    pile_pe = _make_enclosure("合槽桩原则2", "钢板桩")
    group, (e1, e2) = _group_fixture(project, depth2="4", member1_pe=pile_pe)
    # 深侧（e2）相邻侧原则由用户选择：显式改为钢板桩（竖直隔断）
    e2_right = orm.session().get(Element, e2).pe_right_name
    unit_vm.update_element(e2, pe_left_name=e2_right)
    results, errors = _group_results(group)
    assert not errors, errors

    session = orm.session()
    geometry = []
    for element_id in (e1, e2):
        element = session.get(Element, element_id)
        pw = session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
        pe = session.scalars(select(PcpEnclosure).where(PcpEnclosure.name == element.pe_right_name)).first()
        pf = session.scalars(select(PcpFoundation).where(PcpFoundation.name == element.pf_name)).first()
        info = build_element_input(element, pe, pf, pw=pw)
        at = resolve_atlas(build_atlas_query(info, pf, pw))
        ad = atlas_dims(info, at)
        geometry.append(
            {
                "b": info.size_b + ad.t.v * 2 + ad.a.v * 2,
                "h": info.depth + fd(pf).v / 1000 + ad.t.v + ad.c1.v,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    h1, h2 = g1["h"], g2["h"]
    # 桩类内侧放坡水平投影为 0：两侧构件各得本体 + 两侧自身工作面
    # （深侧共享侧现在也有自己的工作面，坡从工作面外缘起算）
    expected_total = (
        (2 * g1["ww"] + g1["b"]) * h1
        + (2 * g2["ww"] + g2["b"]) * h2
    )
    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    assert dig1 + dig2 == pytest.approx(expected_total * 120, rel=1e-9)

    # 中间坡围护量挂深侧（e2 深 4m）：e2 名下的桩量含隔断面，比 e1（只有左边坡面）多
    pile1 = _value(results[e1], "围护|拉森钢板桩|t")
    pile2 = _value(results[e2], "围护|拉森钢板桩|t")
    per_face = math.floor(120 / 0.4 + 0.5) / 120 * 12 * 75 / 1000 * 1 * 120
    assert pile1 == pytest.approx(per_face, rel=1e-9)  # 左边坡一面
    assert pile2 == pytest.approx(per_face * 2, rel=1e-9)  # 中间坡 + 右边坡


def test_group_mid_slope_pile_run_encroaches(project) -> None:
    """深侧放坡 1:0.5：坡到浅槽底后竖直向上，浅槽底以上条带归深侧构件。"""
    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        workwidth_of,
    )
    from app.core.calc.measures import foundation_thickness as fd
    from app.core.models import base as orm
    from app.core.models.models import Element, PcpEnclosure, PcpFoundation, PcpWidth
    from app.services.atlas import resolve_atlas
    from sqlalchemy import select

    slope_pe = _make_enclosure("中间放坡原则", "放坡", slope=0.5)
    pile_pe = _make_enclosure("合槽桩原则3", "钢板桩")
    from app.viewmodels import unit_vm

    e1 = _element("浅管", dn=600, depth="3", amount="120", pe_name=slope_pe.name)
    e2 = _element("深管", dn=600, depth="4", amount="120", pe_name=pile_pe.name)
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    # 深侧（e2）相邻侧（左）由用户选择：放坡 1:0.5（默认是库中第一条）
    unit_vm.update_element(e2, pe_left_name=slope_pe.name)
    results, errors = _group_results(group)
    assert not errors, errors

    session = orm.session()
    geometry = []
    for element_id in (e1, e2):
        element = session.get(Element, element_id)
        pw = session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
        pe = session.scalars(select(PcpEnclosure).where(PcpEnclosure.name == element.pe_right_name)).first()
        pf = session.scalars(select(PcpFoundation).where(PcpFoundation.name == element.pf_name)).first()
        info = build_element_input(element, pe, pf, pw=pw)
        at = resolve_atlas(build_atlas_query(info, pf, pw))
        ad = atlas_dims(info, at)
        geometry.append(
            {
                "b": info.size_b + ad.t.v * 2 + ad.a.v * 2,
                "h": info.depth + fd(pf).v / 1000 + ad.t.v + ad.c1.v,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    h1, h2 = g1["h"], g2["h"]
    delta = h2 - h1
    run = delta * 0.5
    # 首构件（e1）自身左侧原则为放坡 1:0.5 → 左边坡梯形 = h1×(h1×0.5)/2
    edge_slope = h1 * (h1 * 0.5) / 2
    # 浅侧构件 = 本体 + 两侧自身工作面；深侧构件 = 浅槽底以上的竖直条带
    # （宽 run）+ 坡楔（h1 处宽 run → h2 处宽 0）+ 本体 + 两侧自身工作面
    # （共享侧工作面在坡脚，坡从工作面外缘起算）
    mid_area = run * h1 + run * (h2 - h1) / 2
    expected_total = (
        (2 * g1["ww"] + g1["b"]) * h1
        + edge_slope
        + mid_area
        + (2 * g2["ww"] + g2["b"]) * h2
    )
    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    assert dig1 + dig2 == pytest.approx(expected_total * 120, rel=1e-6)


def test_group_layered_trapezoid_multilevel_slope() -> None:
    """多级放坡按标高分层：换级处坡度切换、平台跳变不贡献面积，每层一个梯形。"""
    from types import SimpleNamespace

    from app.core.calc.tracer import dim, mm_of_m
    from app.core.calc.trench_group import (
        _internal_side_profiles,
        _rect_segments,
        _unique_dims,
        _width_and_slope_for_interval,
    )

    def level(slope: float, step_width: float):
        param = SimpleNamespace(key="A", value=f"放坡系数 1:X|{slope}")
        component = SimpleNamespace(params=[param])
        return SimpleNamespace(h=-1.0, step_width=step_width, components=[component])

    # 深级 1:0.3 / 平台 1.0；浅级 1:0.5 / 平台 0.8；ΔH = 1.0
    work = SimpleNamespace(levels=[level(0.5, 0.8), level(0.3, 1.0)])
    # 剖面函数走 mm 记法几何链（与生产一致），m 浮点经 mm_of_m 桥接
    depth, shallow = mm_of_m(dim(4.0)), mm_of_m(dim(3.0))
    profile = _internal_side_profiles(work, depth, shallow, mm_of_m(dim(0.0)))[0]

    # 0→0.5：0.3；换级平台 0.8；0.5→1.0：0.5；1.0→4.0：竖直 1.2
    assert [round(seg.t1.v, 6) for seg in profile] == [0.0, 0.5, 1.0]
    assert [round(seg.t2.v, 6) for seg in profile] == [0.5, 1.0, 4.0]
    assert [round(seg.slope.v, 6) for seg in profile] == [0.3, 0.5, 0.0]
    assert profile[1].w1.v == pytest.approx(0.5 * 0.3 + 0.8, rel=1e-9)
    assert profile[2].w1.v == pytest.approx(0.5 * 0.3 + 0.8 + 0.5 * 0.5, rel=1e-9)

    # 本体 1.0 + 内侧坡；在回填分层与围护折点上切分，逐层梯形求和
    profiles = [_rect_segments(mm_of_m(dim(1.0)), depth)] + _internal_side_profiles(
        work, depth, shallow, mm_of_m(dim(0.0))
    )
    boundaries = [mm_of_m(dim(value)) for value in (0.0, 0.5, 1.0, 2.0, 3.0, 4.0)]
    for item in profiles:
        for segment in item:
            boundaries += [segment.t1, segment.t2]
    edges = _unique_dims(boundaries)
    areas = []
    for lo, hi in zip(edges, edges[1:]):
        height = hi - lo
        low, slope_terms = _width_and_slope_for_interval(
            profiles, lo, hi, height
        )
        if slope_terms.v == 0:
            areas.append((low * height).v)
        else:
            areas.append((2 * low.v + slope_terms.v) * height.v / 2.0)

    # 0→0.5：(1+1.15)/2*0.5；0.5→1：(1.95+2.2)/2*0.5；其余三层恒宽 2.2
    assert areas == pytest.approx([0.5375, 1.0375, 2.2, 2.2, 2.2], rel=1e-9)
    assert sum(areas) == pytest.approx(8.175, rel=1e-9)


# --------------------------------------------------------------------------- #
# 合槽整槽口径：回填分层方式 / 断面划分方式（父节点下拉）
# --------------------------------------------------------------------------- #
def _group_snapshots(group):
    """组员快照（按从左到右），供分层 / 几何对拍。"""
    from app.core.calc.trench_group import _resolve_member
    from app.core.models import base as orm

    session = orm.session()
    return [
        _resolve_member(session, element)[0]
        for element in sorted(group.members, key=lambda item: (item.order_no, item.id))
    ]


def _unified_interface_oracle(snapshots):
    """手算统筹界面：逐层角色取组内各构件层顶的最低标高（地面以下深度）。"""
    from app.core.calc.groove import layer_roles
    from app.core.calc.trench_group import _member_layers

    best: dict[tuple[str, int], float] = {}
    for member in snapshots:
        cum = 0.0
        layers = _member_layers(member)
        for (base, occurrence), (_key, layer, _note) in zip(layer_roles(layers), layers):
            cum += layer.v
            if layer.v <= 0:
                continue
            role = (base, occurrence)
            elevation = member.depth.v - cum
            if role not in best or elevation < best[role] - 1e-9:
                best[role] = elevation
    return best


def test_group_unified_backfill_elevation(project) -> None:
    """统一回填标高：每层界面取组内最浅层顶标高，材质仍按各构件自己的原则。

    * 每个构件的层带顶标高 == 组内该层最浅标高（手算统筹界面逐带对拍）；
    * 层带自构件自己的槽底起算并补齐到槽顶（总高 = 自身槽深）；
    * 宽度剖面未变：每个构件的挖方与独立回填标高口径完全一致（守恒）。
    """
    from app.core.calc.groove import layer_roles
    from app.core.calc.trench_group import (
        _member_layers,
        _unified_interfaces,
        _unified_member_bands,
    )
    from app.core.models import base as orm
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group_fixture(project, depth2="4", dn2=800)
    unit_vm.update_group(group.id, backfill_mode="统一回填标高")
    group = orm.session().get(type(group), group.id)
    snapshots = _group_snapshots(group)
    expected = _unified_interface_oracle(snapshots)
    interfaces = _unified_interfaces(snapshots)
    assert set(interfaces) == set(expected)
    for member in snapshots:
        bands = _unified_member_bands(member, interfaces)
        assert bands, "统一口径下层带不应为空"
        # 手算期望带序：按构件自己的分层自底向上，凡有统筹界面且界面低于
        # 上一条者成带（与 _unified_member_bands 同一重建规则，逐带对拍）
        expected_bands: list[tuple[str, float]] = []
        bottom = member.depth.v
        for (base, occurrence), (key, layer, _note) in zip(
            layer_roles(_member_layers(member)), _member_layers(member)
        ):
            if (base, occurrence) not in expected:
                continue
            top = expected[(base, occurrence)]
            if top >= bottom - 1e-9:
                continue
            expected_bands.append((key, member.depth.v - top))
            bottom = top
        assert [(band[0], round(band[2].v, 9)) for band in bands] == [
            (key, round(top, 9)) for key, top in expected_bands
        ]
        for _key, lo, hi, thickness, _note in bands:
            assert thickness.v == pytest.approx(hi.v - lo.v, rel=1e-9)
            assert lo.v >= -1e-9 and hi.v <= member.depth.v + 1e-9
        # 顶层补齐到槽顶
        assert bands[-1][2].v == pytest.approx(member.depth.v, rel=1e-9)

    # 守恒：剖面未变，两种回填口径下每个构件的挖方一致
    results_unified, errors = _group_results(group)
    assert not errors, errors
    unit_vm.update_group(group.id, backfill_mode="独立回填标高")
    results_independent, errors = _group_results(group)
    assert not errors, errors
    for element_id in (e1, e2):
        key = "开挖|Ⅲ类土|m3"
        assert results_unified[element_id].get(key) is not None
        assert results_unified[element_id].get(key).value == pytest.approx(
            results_independent[element_id].get(key).value, rel=1e-9
        )


def test_group_unified_backfill_roundtrip(tmp_path, project) -> None:
    """回填分层 / 断面划分方式随工程保存重开（旧文件缺省 = 现状口径）。"""
    from app.core.models import base as orm
    from app.core.models.models import TrenchGroup
    from app.viewmodels import unit_vm

    group, (_e1, _e2) = _group_fixture(project)
    unit_vm.update_group(group.id, backfill_mode="统一回填标高", split_mode="管中心分隔")
    project_io_close_and_open(project)
    reopened = list(orm.session().scalars(sa_select(TrenchGroup)))
    assert len(reopened) == 1
    assert reopened[0].backfill_mode == "统一回填标高"
    assert reopened[0].split_mode == "管中心分隔"

    # 旧文件（无这两个字段）读入 = 现状口径缺省；早期措辞「起坡点分割」归一化
    from app.services import project_io, stn_format

    project_io.close_project()
    document = stn_format.load_stn(project)
    for unit_data in document.data["segments"][0]["units"]:
        for group_data in unit_data.get("groups") or []:
            group_data.pop("backfill_mode", None)
            group_data["split_mode"] = "起坡点分割"  # 早期措辞
    stn_format.write_stn(project, document.data)
    project_io.open_project(project)
    reopened = list(orm.session().scalars(sa_select(TrenchGroup)))
    assert reopened[0].backfill_mode == "独立回填标高"
    assert reopened[0].split_mode == "起坡点分隔"


def project_io_close_and_open(path):
    from app.services import project_io

    project_io.close_project()
    project_io.open_project(path)
    return path


def sa_select(model):
    from sqlalchemy import select

    return select(model)


def test_group_center_split_conserves_and_transfers(project) -> None:
    """管中心分隔：分界移到中心连线中点，条带归分界移向的一侧，整槽守恒。

    右深左浅（深侧内坡 1:0.5）：分界必右移（中点比起坡点更靠深侧中心）……
    实际手算 δ = (b−a)/2 > 0（a = 浅管中心→起坡点，b = 起坡点→深管中心含
    放坡投影），浅管获条带 = 矩形 |δ|×浅槽深 + 坡区楔形 |δ|²/(2×0.5)，深管
    等量让出；总挖方与起坡点口径严格一致。
    """
    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        workwidth_of,
    )
    from app.core.calc.measures import foundation_thickness as fd
    from app.core.models.models import Element
    from app.services.atlas import resolve_atlas
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("中心放坡原则", "放坡", slope=0.5)
    pile_pe = _make_enclosure("中心桩原则", "钢板桩")
    e1 = _element("中心浅管", dn=600, depth="3", amount="120", pe_name=slope_pe.name)
    e2 = _element("中心深管", dn=600, depth="4", amount="120", pe_name=pile_pe.name)
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    unit_vm.update_element(e2, pe_left_name=slope_pe.name)

    results, errors = _group_results(group)
    assert not errors, errors
    dig_shallow = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig_deep = _value(results[e2], "开挖|Ⅲ类土|m3")
    total = dig_shallow + dig_deep

    # 平面几何（首构件基左缘为 0）：起坡点分界 = 浅管工作面外缘
    from app.core.models import base as orm
    from sqlalchemy import select

    session = orm.session()
    geometry = []
    for element_id in (e1, e2):
        element = session.get(Element, element_id)
        from app.core.models.models import (
            PcpEnclosure,
            PcpFoundation,
            PcpPrecipitation,
            PcpWidth,
        )

        pw = session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
        pe = session.scalars(select(PcpEnclosure).where(PcpEnclosure.name == element.pe_right_name)).first()
        pf = session.scalars(select(PcpFoundation).where(PcpFoundation.name == element.pf_name)).first()
        pp = session.scalars(select(PcpPrecipitation).where(PcpPrecipitation.name == element.pp_name)).first()
        info = build_element_input(element, pe, pf, pp=pp, pw=pw)
        at = resolve_atlas(build_atlas_query(info, pf, pw))
        ad = atlas_dims(info, at)
        geometry.append(
            {
                "b": info.size_b + ad.t.v * 2 + ad.a.v * 2,
                "h": info.depth + fd(pf).v / 1000 + ad.t.v + ad.c1.v,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    run = (g2["h"] - g1["h"]) * 0.5
    wall = g1["ww"] + g1["b"] + g1["ww"]  # 浅管右工作面外缘 = 起坡点分界（坡顶）
    base_left_2 = wall + run + g2["ww"]  # 坡脚 + 深管工作面
    c1 = g1["ww"] + g1["b"] / 2
    c2 = base_left_2 + g2["b"] / 2
    delta = (c1 + c2) / 2 - wall
    assert delta > 1e-9  # 分界右移：浅管获条带（b 含放坡投影 > a）
    offset = abs(delta)
    rect = offset * g1["h"]
    wedge = offset * offset / (2 * 0.5) if offset <= run else 0.0

    unit_vm.update_group(group.id, split_mode="管中心分隔")
    results_center, errors = _group_results(group)
    assert not errors, errors
    dig_shallow_center = _value(results_center[e1], "开挖|Ⅲ类土|m3")
    dig_deep_center = _value(results_center[e2], "开挖|Ⅲ类土|m3")
    # 整槽守恒 + 手算条带（随 L_组 = 120 缩放）
    assert dig_shallow_center + dig_deep_center == pytest.approx(total, rel=1e-9)
    assert dig_shallow_center == pytest.approx(dig_shallow + (rect + wedge) * 120, rel=1e-9)
    assert dig_deep_center == pytest.approx(dig_deep - (rect + wedge) * 120, rel=1e-9)
    # 条带以独立项进入获方挖方（"分左右两侧分别计算再加起来"）
    terms = results_center[e1].get("开挖|Ⅲ类土|m3").terms
    transferred = [t for t in terms if "管中心分隔" in t.note]
    assert transferred, "获方挖方应包含管中心分隔条带项"
    assert sum(t.value for t in transferred) == pytest.approx((rect + wedge) * 120, rel=1e-9)


def test_group_center_split_wedge_to_shallow_cushion(project) -> None:
    """深-浅-深、管中心分隔：坡区楔形计入中间(浅)构件的垫层（左右两个三角形）。

    分层模型：坡区楔形划归获方最底层定额键，几何为三角形（自浅槽底负高度、
    顶点在下）；深构件的垫层不再包含楔形；整槽挖方与起坡点口径守恒。
    """
    from app.core.calc.trench_group import compute_group
    from app.viewmodels import unit_vm

    e1 = _element("楔形左深", dn=600, depth="4", amount="100")
    e2 = _element("楔形中浅", dn=600, depth="3", amount="100")
    e3 = _element("楔形右深", dn=600, depth="4", amount="100")
    group, error = unit_vm.create_trench_group([e1, e2, e3])
    assert group is not None and error is None

    results_slope, errors = compute_group(group)  # 默认起坡点分隔
    assert not any(errors.values()), errors
    total_slope = sum(
        q.value for r in results_slope.values() for q in r.items() if q.key == "开挖|Ⅲ类土|m3"
    )

    unit_vm.update_group(group.id, split_mode="管中心分隔")
    results, errors = compute_group(group)
    assert not any(errors.values()), errors
    total_center = sum(
        q.value for r in results.values() for q in r.items() if q.key == "开挖|Ⅲ类土|m3"
    )
    assert total_center == pytest.approx(total_slope, rel=1e-9)  # 整槽守恒

    # 中间(浅)构件垫层：左右两个楔形三角形（自浅槽底负高度、顶点在下）
    cushion = results[e2].get("垫层|中粗砂|m3")
    wedges = [
        t
        for t in cushion.terms
        if "管中心分隔" in t.note and t.geometry and t.geometry[0] < 0
    ]
    assert len(wedges) == 2, "中间构件垫层应有左右两个楔形三角形"
    left, right = sorted(wedges, key=lambda t: t.geometry[2])
    assert left.geometry[3] < 0 < right.geometry[2]  # 左块在中心左侧、右块在右侧
    for w in wedges:
        g = w.geometry
        assert g[1] == 0.0 and g[0] < 0.0  # 垫层下方（自浅槽底负高度）
        assert (g[3] - g[2]) <= (g[5] - g[4]) + 1e-9  # 底边不宽于顶边（顶点在下）
    # 深构件垫层不再包含楔形
    for eid in (e1, e3):
        deep_cushion = results[eid].get("垫层|中粗砂|m3")
        assert not any("管中心分隔" in t.note for t in deep_cushion.terms)


def test_group_center_split_gainer_deep_no_wedge(project) -> None:
    """深左浅右、分界右移（获方 = 深侧）：只有矩形条带、无坡区楔形，整槽守恒。

    让方更浅时分界条带只有浅槽底以上的矩形（坡区在让方槽底以下无挖方），
    获方（深侧）按 梯形 + 条带 追加，浅侧等量让出。
    """
    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        workwidth_of,
    )
    from app.core.calc.measures import foundation_thickness as fd
    from app.core.models.models import Element
    from app.services.atlas import resolve_atlas
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("深左内坡原则", "放坡", slope=0.5)
    e1 = _element("深左管", dn=600, depth="3.5", amount="100")
    e2 = _element("浅右管", dn=1500, depth="3", amount="100")
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    # 深侧（左管）共享侧内坡 1:0.5，向浅槽底放坡
    unit_vm.update_element(e1, pe_right_name=slope_pe.name)

    results, errors = _group_results(group)
    assert not errors, errors
    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    total = dig1 + dig2

    from app.core.models import base as orm
    from sqlalchemy import select

    session = orm.session()
    geometry = []
    for element_id in (e1, e2):
        element = session.get(Element, element_id)
        from app.core.models.models import (
            PcpEnclosure,
            PcpFoundation,
            PcpPrecipitation,
            PcpWidth,
        )

        pw = session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
        pe = session.scalars(
            select(PcpEnclosure).where(PcpEnclosure.name == element.pe_right_name)
        ).first()
        pf = session.scalars(select(PcpFoundation).where(PcpFoundation.name == element.pf_name)).first()
        pp = session.scalars(select(PcpPrecipitation).where(PcpPrecipitation.name == element.pp_name)).first()
        info = build_element_input(element, pe, pf, pp=pp, pw=pw)
        at = resolve_atlas(build_atlas_query(info, pf, pw))
        ad = atlas_dims(info, at)
        geometry.append(
            {
                "b": info.size_b + ad.t.v * 2 + ad.a.v * 2,
                "h": info.depth + fd(pf).v / 1000 + ad.t.v + ad.c1.v,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    assert g1["h"] > g2["h"] + 1e-9  # 左深右浅（含壁厚差后仍成立）
    run = (g1["h"] - g2["h"]) * 0.5
    # 起坡点分界 = 左管基右 + 自身工作面 + 内坡投影（坡顶，浅槽底标高）
    wall = g1["ww"] + g1["b"] + g1["ww"] + run
    c1 = g1["ww"] + g1["b"] / 2
    c2 = wall + g2["ww"] + g2["b"] / 2
    delta = (c1 + c2) / 2 - wall
    assert delta > 1e-9  # 分界右移：深管（左）获条带
    rect = delta * min(g1["h"], g2["h"])

    unit_vm.update_group(group.id, split_mode="管中心分隔")
    results_center, errors = _group_results(group)
    assert not errors, errors
    dig1c = _value(results_center[e1], "开挖|Ⅲ类土|m3")
    dig2c = _value(results_center[e2], "开挖|Ⅲ类土|m3")
    assert dig1c + dig2c == pytest.approx(total, rel=1e-9)
    assert dig1c == pytest.approx(dig1 + rect * 100, rel=1e-9)
    assert dig2c == pytest.approx(dig2 - rect * 100, rel=1e-9)


def test_group_spacing_mid_split_concrete_foundations(project) -> None:
    """间距平分分隔：分界取相邻构件「间距计算起始点」（砼基础共享侧边线）的中点。

    两根砼基础管（默认地基原则），右管 dn1000 壁厚更大槽深更深、共享侧内坡
    1:0.5：起始点 = 各自基础外皮的共享侧边线，分界中点相对起坡点的位移
    δ = (run + w_R − w_L)/2 > 0 → 分界右移、浅管（左）获条带；让方更深 →
    矩形条带 + 坡区楔形，整槽守恒。
    """
    from app.core.calc.engine import (
        atlas_dims,
        build_atlas_query,
        build_element_input,
        workwidth_of,
    )
    from app.core.calc.measures import foundation_thickness as fd
    from app.core.models.models import Element
    from app.services.atlas import resolve_atlas
    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("间距内坡原则", "放坡", slope=0.5)
    pile_pe = _make_enclosure("间距桩原则", "钢板桩")
    e1 = _element("间距左管", dn=600, depth="3", amount="120", pe_name=pile_pe.name)
    e2 = _element("间距右管", dn=1000, depth="3", amount="120", pe_name=pile_pe.name)
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    # 右深侧共享侧内坡 1:0.5（确定性放坡投影）
    unit_vm.update_element(e2, pe_left_name=slope_pe.name)

    results, errors = _group_results(group)
    assert not errors, errors
    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    total = dig1 + dig2

    from app.core.models import base as orm
    from sqlalchemy import select

    session = orm.session()
    geometry = []
    for element_id in (e1, e2):
        element = session.get(Element, element_id)
        from app.core.models.models import (
            PcpEnclosure,
            PcpFoundation,
            PcpPrecipitation,
            PcpWidth,
        )

        pw = session.scalars(select(PcpWidth).where(PcpWidth.name == element.pw_name)).first()
        pe = session.scalars(
            select(PcpEnclosure).where(PcpEnclosure.name == element.pe_right_name)
        ).first()
        pf = session.scalars(select(PcpFoundation).where(PcpFoundation.name == element.pf_name)).first()
        assert pf.con_found  # 默认地基原则 = 混凝土基础
        pp = session.scalars(select(PcpPrecipitation).where(PcpPrecipitation.name == element.pp_name)).first()
        info = build_element_input(element, pe, pf, pp=pp, pw=pw)
        at = resolve_atlas(build_atlas_query(info, pf, pw))
        ad = atlas_dims(info, at)
        geometry.append(
            {
                "b": info.size_b + ad.t.v * 2 + ad.a.v * 2,
                "h": info.depth + fd(pf).v / 1000 + ad.t.v + ad.c1.v,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    assert g2["h"] > g1["h"] + 1e-9  # dn1000 壁厚更大 → 右管更深
    d_h = g2["h"] - g1["h"]
    run = d_h * 0.5
    # 起坡点分界 = 浅管工作面外缘（坡顶）；间距起始点 = 两管基础外皮的共享侧
    # 边线：左 = 浅管基础右边缘，右 = 右管基础左边缘（坡脚 + 投影 + 工作面处）
    wall = g1["ww"] + g1["b"] + g1["ww"]
    base_left_2 = wall + run + g2["ww"]
    anchor_left = g1["ww"] + g1["b"]
    anchor_right = base_left_2
    delta = (anchor_left + anchor_right) / 2 - wall
    assert delta > 1e-9  # δ = (run + w_R − w_L)/2 > 0：分界右移，浅管（左）获条带
    offset = delta
    rect = offset * g1["h"]
    # 获方更浅、让方更深 → 坡区楔形：width(h) = offset − (run − 0.5h)
    if offset < run:
        wedge = offset * offset / (2 * 0.5)  # 分界在带内切入坡面：三角形
    else:
        wedge = (offset - run) * d_h + 0.25 * d_h * d_h

    unit_vm.update_group(group.id, split_mode="间距平分分隔")
    results_mid, errors = _group_results(group)
    assert not errors, errors
    dig1m = _value(results_mid[e1], "开挖|Ⅲ类土|m3")
    dig2m = _value(results_mid[e2], "开挖|Ⅲ类土|m3")
    assert dig1m + dig2m == pytest.approx(total, rel=1e-9)
    assert dig1m == pytest.approx(dig1 + (rect + wedge) * 120, rel=1e-9)
    assert dig2m == pytest.approx(dig2 - (rect + wedge) * 120, rel=1e-9)
    terms = results_mid[e1].get("开挖|Ⅲ类土|m3").terms
    transferred = [t for t in terms if "间距平分分隔" in t.note]
    assert transferred
    assert sum(t.value for t in transferred) == pytest.approx((rect + wedge) * 120, rel=1e-9)


# --------------------------------------------------------------------------- #
# 合槽编组：操作与校验
# --------------------------------------------------------------------------- #
def test_group_validation_rules(project) -> None:
    from app.viewmodels import unit_vm

    # 数量可以不一致：编组后统一取父节点（首成员）的数量
    e1 = _element("甲", amount="120")
    e2 = _element("乙", amount="100")
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    assert group.amount == "120"

    from app.viewmodels.unit_vm import create_element

    e3 = _element("丙", amount="120")
    jacking = create_element(
        _first_unit_id(), category=4, name="顶管", amount="120",
        pipes=[("钢管", 800, "1")],
    )
    _group, error = unit_vm.create_trench_group([e3, jacking.id])
    assert error is not None and "不开槽" in error

    _group, error = unit_vm.create_trench_group([e3])
    assert error is not None and "至少" in error


def test_group_amount_owned_by_parent(project) -> None:
    """子构件数量强制 = 父节点数量；父节点埋深显示 "-" 且不参与计算。"""
    from app.core.models import base as orm
    from app.core.models.models import Element, TrenchGroup
    from app.viewmodels import unit_vm

    e1 = _element("数量甲", amount="120")
    e2 = _element("数量乙", amount="100")
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    session = orm.session()
    assert session.get(TrenchGroup, group.id).amount == "120"
    assert session.get(Element, e1).amount == "120"
    assert session.get(Element, e2).amount == "120"  # 由父节点强制统一

    # 改父节点数量 → 全部子构件同步
    unit_vm.update_group(group.id, amount="150")
    session.expire_all()
    assert session.get(Element, e1).amount == "150"
    assert session.get(Element, e2).amount == "150"

    # 改子构件数量 → 强制回父节点值（不生效）
    unit_vm.update_element(e1, amount="99")
    session.expire_all()
    assert session.get(Element, e1).amount == "150"
    assert session.get(TrenchGroup, group.id).amount == "150"

    # 父行显示：数量 = L_组，埋深恒 "-"
    from app.viewmodels.unit_vm import GroupRow

    parent_row = next(
        row for row in unit_vm.table_rows(session.get(Element, e1).unit_id)
        if isinstance(row, GroupRow)
    )
    assert parent_row.amount == "150"
    assert parent_row.depth == "-"
    assert parent_row.depth_value == 0.0


def test_group_dissolve_reverts_members(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import LR_PE_TEXT, TrenchGroup, Element
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group_fixture(project)
    # 编组后：成员是分设模式、连续排列
    session = orm.session()
    m1 = session.get(Element, e1)
    m2 = session.get(Element, e2)
    assert m1.pe_name == LR_PE_TEXT and m1.pe_left_name and m1.pe_right_name
    assert abs(m1.order_no - m2.order_no) == 1

    unit_vm.dissolve_trench_group(group.id)
    session = orm.session()
    assert session.get(TrenchGroup, group.id) is None
    m1 = session.get(Element, e1)
    assert m1.group_id is None
    assert m1.pe_name != LR_PE_TEXT  # 还原为普通单原则
    assert m1.pe_left_name == ""


def test_group_parent_has_no_principles_and_children_forced_lr(project) -> None:
    """规则 1 / 2：父节点不选围护 / 面宽原则；子节点强制左右分设。"""
    from app.core.models import base as orm
    from app.core.models.models import Element, LR_PE_TEXT, TrenchGroup
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group_fixture(project)
    session = orm.session()
    parent = session.get(TrenchGroup, group.id)
    assert parent.pe_name == "" and parent.pw_name == ""
    # update_group 只接受 name，PE / PW 写入被忽略
    unit_vm.update_group(group.id, pe_name="合槽桩原则", pw_name="默认面宽原则")
    session.expire_all()
    parent = session.get(TrenchGroup, group.id)
    assert parent.pe_name == "" and parent.pw_name == ""

    # 子节点强制左右分设：pe_name 改回具体原则不生效
    assert session.get(Element, e1).pe_name == LR_PE_TEXT
    unit_vm.update_element(e1, pe_name="合槽桩原则")
    session.expire_all()
    assert session.get(Element, e1).pe_name == LR_PE_TEXT


def test_group_side_plan_equal_and_unequal(project) -> None:
    """规则 4 / 5：等深相邻侧强制 "-"；异深只有更深一侧可编辑。"""
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.services import project_io
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group_fixture(project)
    plan = unit_vm.group_side_plan(group.id)
    # 等深：外边缘可选，中间相邻面两侧都强制 "-"
    assert plan[e1] == (True, False)
    assert plan[e2] == (False, True)

    # 编组时内部侧默认 = 当前围护原则列表第一条（规则 5）
    first = project_io.enclosure_names()[0]
    session = orm.session()
    assert session.get(Element, e1).pe_right_name == first
    assert session.get(Element, e2).pe_left_name == first

    # 右管更深：其左侧可编辑，左管右侧仍强制 "-"
    unit_vm.update_element(e2, depth="4")
    plan = unit_vm.group_side_plan(group.id)
    assert plan[e1] == (True, False)
    assert plan[e2] == (True, True)

    # 右管更浅：深浅翻转，只有左管右侧可编辑
    unit_vm.update_element(e2, depth="2")
    plan = unit_vm.group_side_plan(group.id)
    assert plan[e1] == (True, True)
    assert plan[e2] == (False, True)


def test_delete_group_removes_all_members(project) -> None:
    """删除合槽父节点 = 连同全部子节点一并删除。"""
    from app.core.models import base as orm
    from app.core.models.models import Element, TrenchGroup
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group_fixture(project)
    unit_vm.delete_trench_group(group.id)
    session = orm.session()
    assert session.get(TrenchGroup, group.id) is None
    assert session.get(Element, e1) is None
    assert session.get(Element, e2) is None


def test_group_member_reorder_and_remove(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.viewmodels import unit_vm

    group, (e1, e2) = _group_fixture(project)
    session = orm.session()
    assert session.get(Element, e1).order_no < session.get(Element, e2).order_no
    unit_vm.move_element(e2, -1)  # 组内右移成员上移 = 左移
    session.expire_all()
    assert session.get(Element, e2).order_no < session.get(Element, e1).order_no

    unit_vm.remove_from_group(e1)  # 只剩一条 → 整组自动解散
    session.expire_all()
    assert session.get(Element, e2).group_id is None


# --------------------------------------------------------------------------- #
# stn 编解码往返（分设 + 编组）
# --------------------------------------------------------------------------- #
def test_stn_roundtrip_lr_and_group(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import LR_PE_TEXT, TrenchGroup, Element
    from app.services import project_io, stn_codec

    slope_pe = _make_enclosure("往返左原则", "放坡", slope=0.5)
    pile_pe = _make_enclosure("往返右原则", "钢板桩")
    lr = _make_lr(_element("分设往返", pe_name=slope_pe.name), slope_pe.name, pile_pe.name)
    from app.viewmodels import unit_vm

    unit_vm.update_element(lr, support_left=False)
    g1 = _element("组员1", amount="120")
    g2 = _element("组员2", amount="120")
    group, _error = unit_vm.create_trench_group([g1, g2])

    data = stn_codec.dump_database()
    # dump 里有新字段与编组
    element_data = next(item for item in data["segments"][0]["units"][0]["elements"] if item["name"] == "分设往返")
    assert element_data["pe_name"] == LR_PE_TEXT
    assert element_data["pe_left_name"] == slope_pe.name
    assert element_data["pe_right_name"] == pile_pe.name
    assert element_data["support_left"] is False
    assert data["segments"][0]["units"][0]["groups"]

    # 重开工程后字段零漂移
    path = project_io.current_path()
    project_io.close_project()
    project_io.open_project(path)
    session = orm.session()
    restored = next(
        element for element in session.query(Element).all() if element.name == "分设往返"
    )
    assert restored.pe_name == LR_PE_TEXT
    assert restored.pe_left_name == slope_pe.name
    assert restored.pe_right_name == pile_pe.name
    assert restored.support_left is False
    groups = list(session.query(TrenchGroup).all())
    assert len(groups) == 1
    assert len(groups[0].members) == 2


# --------------------------------------------------------------------------- #
# UI / 断面图冒烟（离屏）
# --------------------------------------------------------------------------- #
def test_section_scene_builds_for_lr_and_group(project, qapp) -> None:
    """分设构件与合槽的断面场景构建不报错（离屏渲染一帧）。"""
    from PySide6.QtGui import QImage

    from app.views.panels.section_view import SectionPanel, _build_group_scene, _build_scene

    slope_pe = _make_enclosure("断面左原则", "放坡", slope=0.5)
    pile_pe = _make_enclosure("断面右原则", "钢板桩")
    lr = _make_lr(_element("断面分设", pe_name=slope_pe.name), slope_pe.name, pile_pe.name)
    scene, hint = _build_scene(lr, 400, 300)
    assert scene is not None, hint

    e1 = _element("断面组1", amount="120")
    e2 = _element("断面组2", amount="120")
    from app.viewmodels import unit_vm

    group, _error = unit_vm.create_trench_group([e1, e2])
    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None and scene.outline, hint

    # 画一帧（paintEvent 全路径）
    panel = SectionPanel()
    panel.resize(400, 300)
    panel.set_element(lr)
    image = QImage(400, 300, QImage.Format.Format_RGB32)
    panel.render(image)
    panel.set_group(group.id)
    panel.render(image)


@pytest.mark.parametrize(
    "category", [3, 6]  # 箱涵 / 管廊
)
def test_group_section_draws_box_structures_and_virtual_wall(
    project, qapp, category
) -> None:
    """箱涵 / 管廊合槽：结构剖面与虚拟竖直墙都要画出来（等深 / 异深）。"""
    from app.views.panels.section_view import _build_group_scene
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    shallow = unit_vm.create_element(
        unit_id, category=category, name="箱涵浅", depth="3", amount="40",
        seed_atlas_defaults=True,
    )
    deep = unit_vm.create_element(
        unit_id, category=category, name="箱涵深", depth="4", amount="40",
        seed_atlas_defaults=True,
    )
    group, error = unit_vm.create_trench_group([shallow.id, deep.id])
    assert group is not None and error is None
    scene, hint = _build_group_scene(group.id, 400, 300)
    assert scene is not None and scene.outline, hint
    # 结构剖面（外框 + 基础 + 内腔）必须画出来，不能只剩基坑线
    assert scene.shapes, "箱涵 / 管廊的结构剖面没有画出来"
    assert len(scene.dashed_lines) == 1  # 异深虚拟墙

    # 等深相邻：结构剖面同样要画，公共边也要有虚拟竖直线
    same1 = unit_vm.create_element(
        unit_id, category=category, name="箱涵等深1", depth="3", amount="40",
        seed_atlas_defaults=True,
    )
    same2 = unit_vm.create_element(
        unit_id, category=category, name="箱涵等深2", depth="3", amount="40",
        seed_atlas_defaults=True,
    )
    group2, error2 = unit_vm.create_trench_group([same1.id, same2.id])
    assert group2 is not None and error2 is None
    scene2, hint2 = _build_group_scene(group2.id, 400, 300)
    assert scene2 is not None and scene2.outline, hint2
    assert scene2.shapes
    assert len(scene2.dashed_lines) == 1  # 等深公共边


def test_unit_panel_group_rows_and_lr_tab(project, qapp) -> None:
    """主表格树形行 / 父行编辑 / 分设 tab 的装填冒烟。"""
    from app.views.panels.unit_panel import UnitPanel

    from app.viewmodels import unit_vm

    slope_pe = _make_enclosure("面板左原则", "放坡", slope=0.5)
    pile_pe = _make_enclosure("面板右原则", "钢板桩")
    lr = _make_lr(_element("面板分设", pe_name=slope_pe.name), slope_pe.name, pile_pe.name)
    e1 = _element("面板组1", amount="120")
    e2 = _element("面板组2", amount="120")

    panel = UnitPanel()
    panel.resize(1400, 800)
    from app.viewmodels.project_vm import TreeNode

    from app.core.models.models import Unit
    from app.core.models import base as orm
    from sqlalchemy import select

    unit = orm.session().scalar(select(Unit))
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))

    # 分设构件选中 → 「围护原则」tab 装填 4 行（v10：挖填/基础已归各自原则；
    # 离屏未 show，用内容断言）
    panel._show_single_detail(lr)
    assert panel._lr_table.rowCount() == 4
    assert not panel._lr_placeholder.isVisible()

    # 编组 → 表格出现父行（树形元数据 has_children）+ 两行缩进子行（indent=1）
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    panel.refresh()
    table = panel._element_table
    from app.views.panels.unit_panel import (
        _COL_AMOUNT,
        _COL_DEPTH,
        _COL_PE,
        _COL_PF,
        _COL_PP,
        _COL_PW,
        _TREE_ROLE,
        _select_row,
    )

    metas = [table.item(row, 0).data(_TREE_ROLE) for row in range(table.rowCount())]
    assert any(meta and meta["has_children"] for meta in metas)
    assert sum(1 for meta in metas if meta and meta["indent"] == 1) == 2
    # 父行围护 / 地基两格留空且没有下拉框；挖填降水 / 面宽两格是整槽口径
    # 下拉（回填分层方式 / 断面划分方式，默认现状口径）；
    # 埋深恒 "-"（不参与计算），数量 = L_组 且可编辑
    group_row_index = next(
        row for row in range(table.rowCount())
        if (table.item(row, 0).data(_TREE_ROLE) or {}).get("has_children")
    )
    for column in (_COL_PE, _COL_PF):
        assert table.item(group_row_index, column).text() == ""
        assert table.cellWidget(group_row_index, column) is None
    from app.core.models import base as orm
    from app.core.models.models import BACKFILL_MODES, SPLIT_MODES, TrenchGroup
    from PySide6.QtWidgets import QComboBox

    fill_combo = table.cellWidget(group_row_index, _COL_PP)
    assert isinstance(fill_combo, QComboBox)
    assert [fill_combo.itemText(i) for i in range(fill_combo.count())] == list(BACKFILL_MODES)
    assert fill_combo.currentText() == "独立回填标高"
    split_combo = table.cellWidget(group_row_index, _COL_PW)
    assert isinstance(split_combo, QComboBox)
    assert [split_combo.itemText(i) for i in range(split_combo.count())] == list(SPLIT_MODES)
    assert split_combo.currentText() == "起坡点分隔"
    # 切换下拉即写父节点（整槽口径选项）
    fill_combo.setCurrentText("统一回填标高")
    split_combo.setCurrentText("管中心分隔")
    parent = orm.session().get(TrenchGroup, group.id)
    assert parent.backfill_mode == "统一回填标高"
    assert parent.split_mode == "管中心分隔"
    assert table.item(group_row_index, _COL_DEPTH).text() == "-"
    assert table.item(group_row_index, _COL_AMOUNT).text() == "120"
    from PySide6.QtCore import Qt

    assert table.item(group_row_index, _COL_AMOUNT).flags() & Qt.ItemFlag.ItemIsEditable
    # 子行强制「左右分设」（只读文本，无下拉框）；数量只读（由父节点控制）
    member_row_index = next(
        row for row in range(table.rowCount())
        if (table.item(row, 0).data(_TREE_ROLE) or {}).get("indent") == 1
    )
    assert table.item(member_row_index, _COL_PE).text() == "左右分设"
    assert table.cellWidget(member_row_index, _COL_PE) is None
    assert table.item(member_row_index, _COL_AMOUNT).text() == "120"
    assert not (
        table.item(member_row_index, _COL_AMOUNT).flags() & Qt.ItemFlag.ItemIsEditable
    )

    # 选中首构件：等深相邻侧（右侧）强制 "-"，对应的支撑勾选也禁用
    _select_row(table, member_row_index, 0)
    panel._sync_detail_to_selection()
    assert panel._lr_table.rowCount() == 4
    right_combo = panel._lr_table.cellWidget(1, 0)
    assert not right_combo.isEnabled() and right_combo.currentText() == "-"
    assert not panel._lr_table.cellWidget(3, 0).isEnabled()  # 右侧支撑

    # 父行选中 → 组成员合计工程量与合槽断面
    _select_row(table, group_row_index, 0)
    panel._sync_detail_to_selection()
    assert panel._group_member_ids
    # 断面面板 + 工程量表都有内容（合槽断面 outline 模式）
    assert panel._section_view._canvas._group_id == group.id

    # 点击 +/- 收起 → 两条成员行隐藏；再点展开 → 恢复显示
    panel._on_group_toggle_requested(group_row_index)
    assert sum(1 for row in range(table.rowCount()) if table.isRowHidden(row)) == 2
    assert (table.item(group_row_index, 0).data(_TREE_ROLE))["expanded"] is False
    panel._on_group_toggle_requested(group_row_index)
    assert not any(table.isRowHidden(row) for row in range(table.rowCount()))

    # 真实鼠标点击 +/- 方框区域：委托 editorEvent 收到左键按下 → 收起成员行
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    item_rect = table.visualItemRect(table.item(group_row_index, 0))
    QTest.mouseClick(
        table.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(item_rect.x() + 13, item_rect.center().y()),
    )
    assert sum(1 for row in range(table.rowCount()) if table.isRowHidden(row)) == 2

    # 多选占位（分设 tab 内容切回占位说明）
    panel._show_multi_detail()
    assert panel._lr_table.rowCount() == 0


def test_lr_tab_combos_follow_principle_changes(project, qapp) -> None:
    """原则增删改名后，「围护原则」tab 的左右下拉按新原则表重建。

    回归：_on_tree_structure_changed 原先只 refresh() 主表格；重新选中同一构件时
    _sync_detail_to_selection 因 id 相同跳过 _show_single_detail，LR 下拉停在旧
    名单——新增的原则选不到，界面只剩「默认围护原则」一条。
    """
    from sqlalchemy import select

    from app.core.event_bus import bus
    from app.core.models import base as orm
    from app.core.models.models import LR_PE_TEXT, Unit
    from app.services import project_io
    from app.viewmodels.project_vm import TreeNode
    from app.views.panels.unit_panel import UnitPanel

    left_pe = _make_enclosure("刷新左原则", "放坡", slope=0.5)
    right_pe = _make_enclosure("刷新右原则", "钢板桩")
    lr = _make_lr(_element("刷新分设", pe_name=left_pe.name), left_pe.name, right_pe.name)

    panel = UnitPanel()
    unit = orm.session().scalar(select(Unit))
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))
    panel._show_single_detail(lr)

    def combo_texts(row: int) -> list[str]:
        combo = panel._lr_table.cellWidget(row, 0)
        return [combo.itemText(index) for index in range(combo.count())]

    assert left_pe.name in combo_texts(0) and right_pe.name in combo_texts(1)

    # 用户点原则横条「+」新增原则 → 广播 tree_structure_changed
    created = project_io.create_enclosure("新增围护原则")
    bus().tree_structure_changed.emit()

    for row in (0, 1):
        texts = combo_texts(row)
        assert created.name in texts, texts
        assert LR_PE_TEXT not in texts  # 占位项不进左右下拉
    # 下拉重建后仍保持原选中值（未被静默改成第一条）
    assert panel._lr_table.cellWidget(0, 0).currentText() == left_pe.name
    assert panel._lr_table.cellWidget(1, 0).currentText() == right_pe.name


def _edit_group_parent_amount(panel, group_id: int, text: str) -> None:
    """真实编辑（Enter 提交）合槽父行数量：打开内嵌编辑器 → 输入 → 回车。

    不能用 item.setText 代替：Enter 走的是编辑器 commitData，整表重载由
    unit_changed 触发 QTimer 延后执行，必须让事件循环跑起来。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit

    from app.views.panels.unit_panel import _COL_AMOUNT

    table = panel._element_table
    row = next(index for index in range(table.rowCount()) if panel._group_id_at(index) == group_id)
    table.setCurrentCell(row, _COL_AMOUNT)
    table.editItem(table.item(row, _COL_AMOUNT))
    QApplication.processEvents()
    editor = table.findChild(QLineEdit)
    editor.setText(text)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()
    QTest.qWait(30)
    QApplication.processEvents()


def _show_group_panel(elements: list[int]) -> tuple:
    """建面板并编组，返回 (panel, group, unit)。"""
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Unit
    from app.viewmodels import unit_vm
    from app.viewmodels.project_vm import TreeNode
    from app.views.panels.unit_panel import UnitPanel

    unit = orm.session().scalar(select(Unit))
    panel = UnitPanel()
    panel._on_node_selected(TreeNode(kind="unit", id=unit.id, name=unit.name))
    group, error = unit_vm.create_trench_group(elements)
    assert group is not None and error is None
    panel.refresh()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()
    return panel, group, unit


def test_group_parent_amount_edit_keeps_group_detail(project, qapp) -> None:
    """改合槽父节点数量后仍选中父行：成员合计工程量与整槽断面不被清空。

    回归：父行不是构件（``_current_element_id`` 恒 None），整表重载原先会
    回落到第 0 行，随后的空态清理又把明细清掉。
    """
    from app.views.panels.unit_panel import _select_row

    _element("父行前构件")  # 让合槽父行不在第 0 行
    e1 = _element("父行组员1")
    e2 = _element("父行组员2")
    panel, group, _unit = _show_group_panel([e1, e2])

    table = panel._element_table
    group_row = next(
        row for row in range(table.rowCount()) if panel._group_id_at(row) == group.id
    )
    _select_row(table, group_row, 0)
    panel._sync_detail_to_selection()
    _edit_group_parent_amount(panel, group.id, "150")

    assert table.currentRow() == group_row
    assert panel._group_member_ids == [e1, e2]
    assert panel._section_view._canvas._group_id == group.id
    assert panel._pipe_table.item(0, 0).text() == "*多种管材"
    assert panel._quantity_tables["定额工程量"].rowCount() > 0
    listing = panel._quantity_tables["清单工程量"]
    assert listing.rowCount() > 0
    # 数量已按父节点新值重算（而不是停留在编辑前的 120）
    assert any(
        listing.item(row, 4) is not None and listing.item(row, 4).text() == "150"
        for row in range(listing.rowCount())
    )


def test_group_parent_amount_edit_first_row_not_stale(project, qapp) -> None:
    """父行位于第 0 行时，改数量后不能被上一个构件的过期明细覆盖。

    回归：明细目标停留在末条子构件时改父节点数量，重载先清空再补发
    过期 detail_loaded，整个下方面板会刷成末条子构件的内容、定额/清单清空。
    """
    from app.views.panels.unit_panel import _select_row

    e1 = _element("首行组员1")
    e2 = _element("首行组员2")
    panel, group, _unit = _show_group_panel([e1, e2])

    table = panel._element_table
    group_row = next(
        row for row in range(table.rowCount()) if panel._group_id_at(row) == group.id
    )
    assert group_row == 0
    # 先选末条子构件（明细目标停在它），再选父行编辑
    last_child_row = next(
        row for row in range(table.rowCount()) if panel._element_id_at(row) == e2
    )
    _select_row(table, last_child_row, 0)
    panel._sync_detail_to_selection()
    _select_row(table, group_row, 0)
    panel._sync_detail_to_selection()
    _edit_group_parent_amount(panel, group.id, "150")

    assert table.currentRow() == group_row
    assert panel._current_element_id() is None
    assert panel._multi_detail is True
    assert panel._group_member_ids == [e1, e2]
    assert panel._section_view._canvas._group_id == group.id
    assert panel._pipe_table.item(0, 0).text() == "*多种管材"
    assert panel._quantity_tables["定额工程量"].rowCount() > 0
    listing = panel._quantity_tables["清单工程量"]
    assert listing.rowCount() > 0
    # 数量已按父节点新值重算（而不是停留在编辑前的 120）
    assert any(
        listing.item(row, 4) is not None and listing.item(row, 4).text() == "150"
        for row in range(listing.rowCount())
    )
