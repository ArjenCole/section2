"""合槽计算的记法指数一致性回归（2026-11-06 16:40 日志报错）。

日志堆栈：合槽 + 包封构件计算工程量时，_member_dig_fill 的
``height = hi - lo`` 抛 AssertionError（10^6 面积量纲混进 10^3 标高链）。
本文件两层防线：

* 场景矩阵（包封 / 箱涵 × 分隔方式 × 回填方式 × 放坡 / 直壁）探针扫描
  bands / profiles 的记法指数，锁住「合槽几何链全 mm」的不变量；
* 人为注入面积量纲分层带，验证污染只转成逐构件错误说明、不再炸整个
  计算面板。
"""

import pytest


@pytest.fixture()
def project(tmp_path):
    from app.services import project_io
    from app.services.project_io import NewProjectSpec

    project_io.new_project(
        NewProjectSpec(
            path=tmp_path / "fuzz.stn",
            project_name="fuzz",
            segment_names=["标段一"],
            unit_names=["雨水工程"],
            enclosure_name="放坡原则",
            foundation_name="地基原则",
        )
    )
    from app.services import project_io as pio

    unit = pio.units(pio.segments()[0].id)[0]
    yield unit
    pio.close_project()


def _make(project, name, *, category=1, depth="3", dn=600, mat="Ⅱ级混凝土管", params=None, distance_right="", distance_left=""):
    from app.core.models import base as orm
    from app.core.models.models import ElementParam
    from app.viewmodels import unit_vm

    element = unit_vm.create_element(
        project.id,
        category=category,
        name=name,
        depth=depth,
        amount="50",
        pipes=[(mat, dn, "1")] if category in (1, 2, 4, 5) else None,
        seed_atlas_defaults=True,
    )
    assert element is not None
    session = orm.session()
    for key, value in (params or {}).items():
        for param in element.params:
            if param.key == key:
                param.value = value
                break
        else:
            element.params.append(ElementParam(key=key, unit="", value=value))
    if distance_right:
        element.center_distance_right = distance_right
    if distance_left:
        element.center_distance_left = distance_left
    orm.session().flush()
    return element.id


def _scan_and_compute(group):
    from app.core.models import base as orm
    from app.core.calc import trench_group

    group = orm.session().get(type(group), group.id)

    problems: list[str] = []
    original = trench_group._member_dig_fill

    def probe(member, out, bands):
        def bad(value):
            # 零值 s=0 无害：加减的 0 快捷分支不做记法断言
            return value.s != 3 and not (value.s == 0 and value.v == 0)

        for key, lo, hi, layer, _note in bands:
            for label, value in (("lo", lo), ("hi", hi), ("layer", layer)):
                if bad(value):
                    problems.append(f"band {key} {label}: s={value.s} e={value.e!r}")
        for pi, profile in enumerate(member.profiles):
            for si, seg in enumerate(profile):
                for label in ("t1", "w1", "t2"):
                    value = getattr(seg, label)
                    if bad(value):
                        problems.append(
                            f"profile p{pi}#{si} {label}: s={value.s} e={value.e!r}"
                        )
                if seg.slope.s != 0:
                    problems.append(f"profile p{pi}#{si} slope: s={seg.slope.s} e={seg.slope.e!r}")
        return original(member, out, bands)

    trench_group._member_dig_fill = probe
    try:
        results, errors = trench_group.compute_group(group)
    finally:
        trench_group._member_dig_fill = original
    return results, errors, problems


def _make_pile_principle(name: str, category: str, slope: float | None = None):
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


def _apply_pe(element_id, pe_name):
    from app.viewmodels import unit_vm

    unit_vm.update_element(element_id, pe_name=pe_name)


SCENARIOS = [
    # (成员构造参数列表, split_mode, backfill_mode)
    # 包封浅 + 管道深，距离填浅侧
    (
        [
            dict(category=2, depth="2.1", dn=800, distance_right="2100"),
            dict(category=1, depth="3.1", dn=600),
        ],
        "管中心分隔",
        "统一回填标高",
    ),
    # 包封深 + 管道浅（浅侧侵入放坡）
    (
        [
            dict(category=1, depth="2.0", dn=600, distance_right="1500"),
            dict(category=2, depth="3.5", dn=1000),
        ],
        "管中心分隔",
        "独立回填标高",
    ),
    # 包封夹中间，两侧深
    (
        [
            dict(category=1, depth="3.0", dn=600),
            dict(category=2, depth="2.0", dn=800),
            dict(category=1, depth="3.0", dn=600),
        ],
        "间距平分分隔",
        "统一回填标高",
    ),
    # 箱涵 + 包封
    (
        [
            dict(category=3, depth="4.0", params={"净宽(含内壁厚度)": "3000", "净高": "2000"}),
            dict(category=2, depth="2.5", dn=800, distance_left="2500"),
        ],
        "间距平分分隔",
        "独立回填标高",
    ),
    # 包封 + 包封，等深 + 距离（规则 5：填左侧构件右侧）
    (
        [
            dict(category=2, depth="2.5", dn=800, params={"包封宽": "200+27*2+80*2"}, distance_right="1200"),
            dict(category=2, depth="2.5", dn=600, params={"包封宽": "0.5"}),
        ],
        "管中心分隔",
        "统一回填标高",
    ),
    # 三根深浅交替（还原日志断面的深浅模式）
    (
        [
            dict(category=1, depth="1.1", dn=200),
            dict(category=2, depth="2.1", dn=1000, distance_right="2100"),
            dict(category=1, depth="3.1", dn=1000),
        ],
        "管中心分隔",
        "独立回填标高",
    ),
    (
        [
            dict(category=1, depth="1.1", dn=200),
            dict(category=2, depth="2.1", dn=1000, distance_right="2100"),
            dict(category=1, depth="3.1", dn=1000),
        ],
        "间距平分分隔",
        "统一回填标高",
    ),
    # 包封宽为算式 + 覆土自定义 + 距离
    (
        [
            dict(category=2, depth="2.1", dn=1000, params={"包封宽": "1500", "包封高": "1.2"}, distance_right="3000+100"),
            dict(category=1, depth="3.1", dn=1320),
        ],
        "管中心分隔",
        "统一回填标高",
    ),
]


PILE_SCENARIOS = [
    # 直壁（钢板桩）+ 管中心分隔 + 浅侧获条带：触发 _wedge_pieces 直壁分支
    # （offset * delta_h，即日志报错算式的形状）
    (
        [
            dict(category=2, depth="2.1", dn=800),
            dict(category=1, depth="3.1", dn=600),
        ],
        "管中心分隔",
        "独立回填标高",
    ),
    # 直壁 + 浅侧在左（获方=右侧深构件不产生楔形）与浅侧在右两种布局
    (
        [
            dict(category=1, depth="3.1", dn=600),
            dict(category=2, depth="2.1", dn=800),
        ],
        "管中心分隔",
        "统一回填标高",
    ),
    # 直壁 + 间距平分分隔 + 包封
    (
        [
            dict(category=2, depth="2.1", dn=800),
            dict(category=1, depth="3.1", dn=1000),
            dict(category=2, depth="2.1", dn=600),
        ],
        "间距平分分隔",
        "独立回填标高",
    ),
]


@pytest.mark.parametrize(
    "members,split_mode,backfill_mode,principle",
    [(*case, "default") for case in SCENARIOS]
    + [(*case, "pile") for case in PILE_SCENARIOS],
)
def test_no_space_leak(project, members, split_mode, backfill_mode, principle):
    from app.core.models import base as orm
    from app.core.models.models import TrenchGroup
    from app.viewmodels import unit_vm

    ids = [_make(project, f"构件{i}", **spec) for i, spec in enumerate(members)]
    if principle == "pile":
        pile = _make_pile_principle("fuzz桩原则", "钢板桩")
        for element_id in ids:
            _apply_pe(element_id, pile.name)
    group, error = unit_vm.create_trench_group(ids)
    assert group is not None, error
    session = orm.session()
    row = session.get(TrenchGroup, group.id)
    row.split_mode = split_mode
    row.backfill_mode = backfill_mode
    orm.session().flush()

    _results, errors, problems = _scan_and_compute(row)
    assert not problems, "记法指数泄漏：\n" + "\n".join(problems)
    for member_id, message in errors.items():
        assert not message, f"split={split_mode}: {message}"


def test_polluted_band_becomes_member_error(project):
    """面积量纲混进分层带：只转逐构件错误说明，不再抛未捕获断言。

    回归 2026-11-06 的崩溃：_member_dig_fill 里 ``height = hi - lo`` 对
    10^6 与 10^3 的操作数直接断言，整组计算中断、面板刷新失败。污染带
    内部放一个围护分级折点（深侧内坡的坡顶 = 相邻浅槽底高差），确保走到
    区间差分支 ``height = hi - lo``。
    """
    from app.core.calc import trench_group
    from app.core.calc.tracer import Dim

    e_shallow = _make(project, "管一", category=1, depth="2.1", dn=600)
    e_deep = _make(project, "管二", category=1, depth="3.1", dn=600)
    from app.viewmodels import unit_vm

    group, error = unit_vm.create_trench_group([e_shallow, e_deep])
    assert group is not None, error
    from app.core.models import base as orm
    from app.core.models.models import TrenchGroup

    row = orm.session().get(TrenchGroup, group.id)

    original = trench_group._member_bands

    def polluted_bands(member):
        bands = original(member)
        if member.element.id != e_deep:
            return bands
        # 深侧构件内坡折点在 3.1-2.1 = 1.0m 处：找到覆盖它的层带，把上界
        # 换成面积量纲（10^6）的 Dim，模拟记法链污染
        for index, (key, lo, hi, layer, note) in enumerate(bands):
            if lo.v < 1.0 <= hi.v:
                area = Dim(1.05, f"({lo.e})*({hi.e})", lo.tags, 6)
                bands[index] = (key, lo, area, layer, note)
                break
        else:
            raise AssertionError("测试数据没有覆盖 1.0m 折点的层带")
        return bands

    trench_group._member_bands = polluted_bands
    try:
        results, errors = trench_group.compute_group(orm.session().get(type(row), row.id))
    finally:
        trench_group._member_bands = original

    assert "记法异常" in errors[e_deep], errors
    assert not errors.get(e_shallow), errors
    # 其余成员照常出量
    assert results.get(e_shallow)
