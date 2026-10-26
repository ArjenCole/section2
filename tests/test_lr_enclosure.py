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
    # ZA = 贯通支撑（无 sides）、ZB = 围檩（含 sides），display 同键合并
    assert pile.params["ZA"][1] == "ROUND(count/G,0)/count*F*width*H/1000"
    assert pile.params["ZB"][1] == "1*sides*2*F*I/1000"
    assert pile.params["ZB"][0] == pile.params["ZA"][0] == "支撑|钢支撑、钢围檩|t"


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
                "b": info.size_b + (ad.t * 2 + ad.a * 2) / 1000,
                "h": info.depth + (fd(pf).v + ad.t + ad.c1) / 1000,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    b1, b2 = g1["b"], g2["b"]
    w1, w2 = g1["ww"], g2["ww"]
    # 父节点不持有面宽原则：首 / 末构件各用自己的 PW 工作面；相邻区 = w1 + w2
    flat = b1 + b2 + 2 * w1 + 2 * w2
    # 等深断言（同管径 → 同图集参数）
    assert g1["h"].v == pytest.approx(g2["h"].v, abs=1e-9)
    depth = g1["h"].v

    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    assert dig1 + dig2 == pytest.approx(flat.v * depth * 120, rel=1e-9)
    # 挖填拆分：等深相邻面为虚拟垂直空围护，各构件 = 本体 + 自身两侧工作面
    assert dig1 == pytest.approx((b1 + 2 * w1).v * depth * 120, rel=1e-9)
    assert dig2 == pytest.approx((b2 + 2 * w2).v * depth * 120, rel=1e-9)
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
                "b": info.size_b + (ad.t * 2 + ad.a * 2) / 1000,
                "h": info.depth + (fd(pf).v + ad.t + ad.c1) / 1000,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    h1, h2 = g1["h"].v, g2["h"].v
    # 桩类内侧放坡水平投影为 0：浅侧构件 = 本体 + 自身两侧工作面；
    # 深侧构件 = 本体 + 自身右侧工作面（相邻侧竖直隔断，无工作面）
    expected_total = (
        (2 * g1["ww"] + g1["b"]) * h1
        + (g2["b"] + g2["ww"]) * h2
    )
    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    assert dig1 + dig2 == pytest.approx(expected_total.v * 120, rel=1e-9)

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
                "b": info.size_b + (ad.t * 2 + ad.a * 2) / 1000,
                "h": info.depth + (fd(pf).v + ad.t + ad.c1) / 1000,
                "ww": workwidth_of(pw, info) / 1000,
            }
        )
    g1, g2 = geometry
    h1, h2 = g1["h"].v, g2["h"].v
    delta = h2 - h1
    run = delta * 0.5
    # 首构件（e1）自身左侧原则为放坡 1:0.5 → 左边坡梯形 = h1×(h1×0.5)/2
    edge_slope = h1 * (h1 * 0.5) / 2
    # 浅侧构件 = 本体 + 两侧自身工作面；深侧构件 = 浅槽底以上的竖直条带
    # （宽 run）+ 坡楔（h1 处宽 run → h2 处宽 0）+ 本体 + 右侧工作面
    mid_area = run * h1 + run * (h2 - h1) / 2
    expected_total = (
        (2 * g1["ww"] + g1["b"]) * h1
        + edge_slope
        + mid_area
        + (g2["b"] + g2["ww"]) * h2
    )
    dig1 = _value(results[e1], "开挖|Ⅲ类土|m3")
    dig2 = _value(results[e2], "开挖|Ⅲ类土|m3")
    assert dig1 + dig2 == pytest.approx(expected_total.v * 120, rel=1e-6)


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
    # 父行四个原则单元格一律留空且没有下拉框；
    # 埋深恒 "-"（不参与计算），数量 = L_组 且可编辑
    group_row_index = next(
        row for row in range(table.rowCount())
        if (table.item(row, 0).data(_TREE_ROLE) or {}).get("has_children")
    )
    for column in (_COL_PE, _COL_PF, _COL_PP, _COL_PW):
        assert table.item(group_row_index, column).text() == ""
        assert table.cellWidget(group_row_index, column) is None
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
