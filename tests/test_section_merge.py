"""断面分项合并：同一工程量的上下相邻断面合成一条大梯形 / 矩形 / 弓形。

合槽的分层积分会在每个回填分层界面与放坡折点处切段；列式时若同一工程量
的上下相邻段并集仍是单一形状（同坡梯形 / 矩形 / 弓形 / 半圆 / 整圆），
应合并成一条，避免算式里堆一串重复的宽高表达式。
"""

import math

import pytest

from app.core.evaluator import evaluate
from conftest import make_element, make_enclosure


def _group_with_slope(project, *, depth1: str = "3", depth2: str = "3"):
    """双管合槽：两侧外边缘都挂放坡原则（同坡、等深时整槽是一条大梯形）。"""
    from app.viewmodels import unit_vm

    pe = make_enclosure("合并放坡原则", "放坡", slope=0.5)
    e1 = make_element("合并左管", depth=depth1, amount="100", pe_name=pe.name)
    e2 = make_element("合并右管", depth=depth2, amount="100", pe_name=pe.name)
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    return group, [e1, e2]


def _group_results(group):
    from app.core.calc.trench_group import compute_group
    from app.core.models import base as orm

    group = orm.session().get(type(group), group.id)
    return compute_group(group)


def _dig_key(quantities) -> str:
    return next(key for key in quantities.keys() if key.startswith("开挖|"))


# --------------------------------------------------------------------------- #
# 合槽分层积分：挖方 / 回填 / 管位扣减
# --------------------------------------------------------------------------- #
def test_group_merges_constant_slope_dig_into_one_term(project) -> None:
    """等深同坡：整槽挖方是一条大梯形，不再按回填分层切成 6 条。"""
    group, (e1, e2) = _group_with_slope(project)
    results, errors = _group_results(group)
    assert not errors, errors

    for element_id in (e1, e2):
        dig = results[element_id].get(_dig_key(results[element_id]))
        assert dig is not None
        assert len(dig.terms) == 1, [term.note for term in dig.terms]
        term = dig.terms[0]
        # 说明覆盖整槽分层范围，几何自槽底到槽顶
        assert "~" in term.note
        assert term.geometry[0] == pytest.approx(0.0)
        assert term.geometry[1] > 0.0
        assert evaluate(dig.expression) == pytest.approx(dig.value, rel=1e-9)


def test_group_merges_constant_width_dig_into_one_rectangle(project) -> None:
    """等深直壁：整槽挖方是一条矩形，面积行按 u*h 列式。"""
    from app.viewmodels import unit_vm

    pile = make_enclosure("合并直壁原则", "钢板桩")
    e1 = make_element("直壁左管", depth="3", amount="100", pe_name=pile.name)
    e2 = make_element("直壁右管", depth="3", amount="100", pe_name=pile.name)
    group, error = unit_vm.create_trench_group([e1, e2])
    assert group is not None and error is None
    results, errors = _group_results(group)
    assert not errors, errors

    dig = results[e1].get(_dig_key(results[e1]))
    assert dig is not None
    assert len(dig.terms) == 1, [term.note for term in dig.terms]
    term = dig.terms[0]
    assert term.area is not None and term.area.kind == "rectangle"
    assert "~" in term.note
    assert evaluate(dig.expression) == pytest.approx(dig.value, rel=1e-9)


def test_group_merges_same_material_backfill_layers(project) -> None:
    """同材质回填层合并成一条梯形；不同材质（覆土）仍单独一段。"""
    group, (e1, _e2) = _group_with_slope(project)
    results, errors = _group_results(group)
    assert not errors, errors

    sand = results[e1].get("回填|中粗砂|m3")
    assert sand is not None
    positive = [term for term in sand.terms if term.value > 0]
    assert len(positive) == 1, [term.note for term in positive]
    assert "坞膀下半" in positive[0].note
    assert "管顶以上" in positive[0].note
    assert evaluate(positive[0].expr) == pytest.approx(positive[0].value, rel=1e-9)

    cover = results[e1].get("回填|素土|m3")
    assert cover is not None
    assert len(cover.terms) == 1
    assert cover.terms[0].note == "覆土"


def test_group_merges_pipe_occupancy_into_one_slice(project) -> None:
    """同材质层覆盖整段管位：弓形 / 半圆切片合并成一条完整管位扣减。"""
    group, (e1, _e2) = _group_with_slope(project)
    results, errors = _group_results(group)
    assert not errors, errors

    sand = results[e1].get("回填|中粗砂|m3")
    assert sand is not None
    slices = [term for term in sand.terms if "扣管位" in term.note]
    assert len(slices) == 1, [term.note for term in slices]
    term = slices[0]
    assert term.note in ("扣管位·弓形", "扣管位·半圆", "扣管位·圆形")
    # 弧线多边形几何，不是外包矩形
    assert term.geometry and not (
        len(term.geometry) == 6 and isinstance(term.geometry[0], (int, float))
    )
    assert evaluate(term.expr) == pytest.approx(abs(term.value), rel=1e-9)


def test_group_keeps_terms_separate_across_slope_breakpoint(project) -> None:
    """深侧共享面在浅槽底由放坡转竖直：并集不是单一梯形，必须保持分段。"""
    group, (e1, e2) = _group_with_slope(project, depth1="4", depth2="3")
    results, errors = _group_results(group)
    assert not errors, errors

    deep_dig = results[e1].get(_dig_key(results[e1]))
    assert deep_dig is not None
    assert len(deep_dig.terms) == 2, [term.note for term in deep_dig.terms]
    first, second = deep_dig.terms
    assert first.geometry[1] == pytest.approx(second.geometry[0])
    assert first.geometry[0] == pytest.approx(0.0)
    assert second.geometry[1] > first.geometry[1] > 0.0

    # 浅侧剖面保持线性，仍是一条大梯形
    shallow_dig = results[e2].get(_dig_key(results[e2]))
    assert shallow_dig is not None
    assert len(shallow_dig.terms) == 1


# --------------------------------------------------------------------------- #
# 基础占位 / 管位切片：直接测切片合并
# --------------------------------------------------------------------------- #
def test_footprint_slices_merge_same_key_rectangles() -> None:
    from app.core.calc.foundation import _emit_footprint_slices
    from app.core.calc.tracer import QDict, mm

    out = QDict()
    bands = [
        ("回填|砂|m3", mm(0), mm(100), mm(100), "下层"),
        ("回填|砂|m3", mm(100), mm(200), mm(100), "上层"),
    ]
    _emit_footprint_slices(out, bands, mm(200), mm(1000))
    quantity = out.get("回填|砂|m3")
    assert quantity is not None
    assert len(quantity.terms) == 1
    term = quantity.terms[0]
    assert term.note == "扣基础占位"
    assert term.geometry == (0.0, pytest.approx(0.2), -0.5, 0.5, -0.5, 0.5)
    assert term.value == pytest.approx(-0.2)


def test_footprint_slices_keep_different_keys_separate() -> None:
    from app.core.calc.foundation import _emit_footprint_slices
    from app.core.calc.tracer import QDict, mm

    out = QDict()
    bands = [
        ("回填|砂|m3", mm(0), mm(100), mm(100), "下层"),
        ("回填|土|m3", mm(100), mm(200), mm(100), "上层"),
    ]
    _emit_footprint_slices(out, bands, mm(200), mm(1000))
    assert len(out.get("回填|砂|m3").terms) == 1
    assert len(out.get("回填|土|m3").terms) == 1


def test_pipe_slices_merge_same_key_into_full_circle() -> None:
    from app.core.calc.foundation import _emit_pipe_slices
    from app.core.calc.tracer import QDict, mm

    out = QDict()
    bands = [
        ("回填|砂|m3", mm(0), mm(100), mm(100), "下半"),
        ("回填|砂|m3", mm(100), mm(200), mm(100), "上半"),
    ]
    _emit_pipe_slices(out, bands, z_bottom=mm(0), outside=mm(200), z_floor=mm(0))
    quantity = out.get("回填|砂|m3")
    assert quantity is not None
    assert len(quantity.terms) == 1
    term = quantity.terms[0]
    assert term.note == "扣管位·圆形"
    assert term.expr.startswith("PI()*")
    assert term.value == pytest.approx(-math.pi * 0.1 ** 2)
    assert evaluate(term.expr) == pytest.approx(abs(term.value), rel=1e-12)


def test_pipe_slices_keep_different_keys_as_half_circles() -> None:
    from app.core.calc.foundation import _emit_pipe_slices
    from app.core.calc.tracer import QDict, mm

    out = QDict()
    bands = [
        ("回填|砂|m3", mm(0), mm(100), mm(100), "下半"),
        ("回填|土|m3", mm(100), mm(200), mm(100), "上半"),
    ]
    _emit_pipe_slices(out, bands, z_bottom=mm(0), outside=mm(200), z_floor=mm(0))
    lower = out.get("回填|砂|m3").terms[0]
    upper = out.get("回填|土|m3").terms[0]
    assert lower.note == "扣管位·半圆"
    assert upper.note == "扣管位·半圆"
    assert lower.expr.startswith("PI()*") and "/2" in lower.expr
    assert upper.expr.startswith("PI()*") and "/2" in upper.expr
    assert lower.value == pytest.approx(-math.pi * 0.1 ** 2 / 2)
    assert upper.value == pytest.approx(-math.pi * 0.1 ** 2 / 2)


def test_pipe_slices_merge_segment_across_center() -> None:
    from app.core.calc.foundation import _emit_pipe_slices
    from app.core.calc.tracer import QDict, mm

    out = QDict()
    bands = [("回填|砂|m3", mm(50), mm(150), mm(100), "跨中心")]
    _emit_pipe_slices(out, bands, z_bottom=mm(0), outside=mm(200), z_floor=mm(0))
    quantity = out.get("回填|砂|m3")
    assert quantity is not None
    assert len(quantity.terms) == 1
    term = quantity.terms[0]
    assert term.note == "扣管位·弓形"
    assert term.value < 0
    assert evaluate(term.expr) == pytest.approx(abs(term.value), rel=1e-12)
