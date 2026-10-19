"""表达式记录器的“不预运算”规则测试（tracer.Dim / wrap / 汇总助手）。

规则见 README 与 docs/architecture.md：

* 派生量以 Dim 参与计算，算式按运算逐级拼出来，不出现预先算好的数字；
* 只有直接录入 / 查表的原始数据与软件常数才是单个数字；
* 括号按运算优先级给，且只在语法必需处给（顶层加减进乘除上下文才加；
  除数位置、乘方底数位置更严格；原子表达式哪里都不加）；
* 数值与算式同源：Dim.e 重新求值必须等于 Dim.v。
"""

from __future__ import annotations

import pytest

from app.core.evaluator import evaluate
from app.core.calc import engine
from app.core.calc.tracer import (
    Dim,
    dim,
    dim_min,
    dim_sum,
    needs_parens,
    needs_parens_tight,
    raw_dim,
    scale_sum,
    wrap,
)


# --------------------------------------------------------------------------- #
# wrap：括号按优先级
# --------------------------------------------------------------------------- #
def test_wrap_parenthesises_only_additive_expressions() -> None:
    assert wrap("2.85") == "2.85"  # 纯数字原样
    assert wrap("600/1000") == "600/1000"  # 顶层只有乘除 → 不需括号
    assert wrap("65×2") == "65×2"
    assert wrap("(65+130)/1000") == "(65+130)/1000"  # 加减在括号内，顶层是除
    assert wrap("1.99+(65+130)/1000") == "(1.99+(65+130)/1000)"  # 顶层加减 → 加括号
    assert wrap("0.3-0.117") == "(0.3-0.117)"


def test_wrap_tight_also_protects_divisor_positions() -> None:
    # 除数位置：顶层乘除必须括号，否则 a/(b×c) 会变成 a/b×c
    assert wrap("65×2", tight=True) == "(65×2)"
    assert wrap("600/1000", tight=True) == "(600/1000)"
    assert wrap("2.85", tight=True) == "2.85"


def test_atomic_expressions_never_need_parentheses() -> None:
    """纯数字 / 单变量 / 函数调用是原子表达式，任何位置都不加括号。"""
    for text in ("2", "233.988", "0.5", "sin(1.2)", "ceil(40/1.2)"):
        assert not needs_parens(text), text
        assert not needs_parens_tight(text), text
        assert wrap(text, tight=True) == text
    for text in ("50*2", "600/1000", "1.99+(65+130)/1000", "2-1"):
        assert needs_parens_tight(text), text


# --------------------------------------------------------------------------- #
# 公式代入的括号：按占位符位置的最小需要
# --------------------------------------------------------------------------- #
def test_pre_sub_parentheses_follow_position() -> None:
    height = dim(2.0)  # 原子
    width = Dim(1.99, "600/1000+(65×2+130×2+500×2)/1000")  # 顶层加减
    count = Dim(100.0, "50*2")  # 顶层乘除

    assert engine.pre_sub("1*2*height", height, width, count) == "1*2*2"
    # 顶层加减：任何位置都括起来
    assert engine.pre_sub("width*B", height, width, count) == (
        "(600/1000+(65×2+130×2+500×2)/1000)*B"
    )
    # 顶层乘除：除数 / 乘方底数位置才括
    assert engine.pre_sub("ROUND(count/B,0)/count*A", height, width, count) == (
        "ROUND(50*2/B,0)/(50*2)*A"
    )
    assert engine.pre_sub("count^2", height, width, count) == "(50*2)^2"
    assert engine.pre_sub("A*count*A", height, width, count) == "A*50*2*A"


def test_value_exp_parentheses_follow_position() -> None:
    params = {
        "A": ("桩径 mm", "800"),
        "B": ("搭接 mm", "300"),
        "D": ("半桩径", "A/2"),
        "F": ("间距 mm", "A-B"),
        "Z": ("绕过", "height/D/135"),
    }
    assert engine.value_exp(params, "A") == "800"
    assert engine.value_exp(params, "F") == "800-300"  # 原子代入不加括号
    # 乘除式代入到除数位置要括号：height/(800/2)/135 不能写成 height/800/2/135
    assert engine.value_exp(params, "Z") == "height/(800/2)/135"


def test_value_exp_detects_cycle() -> None:
    params = {"A": ("甲", "B+1"), "B": ("乙", "A+1")}
    assert engine.value_exp(params, "A") == engine._CYCLE


# --------------------------------------------------------------------------- #
# Dim：数值与算式同源
# --------------------------------------------------------------------------- #
def test_dim_keeps_derivation_instead_of_precomputing() -> None:
    """管径 / 图集参数 / 面宽原则推出的槽底宽：算式写全，不折成一个数字。"""
    dn = dim(600)  # 管径（mm，原始数据）
    t, a, workwidth = dim(65), dim(130), dim(500)  # 图集与面宽表值（原始数据）
    bottom = dn / 1000 + scale_sum((t, a, workwidth), 2.0) / 1000
    assert bottom.v == pytest.approx(1.99)
    assert bottom.e == "600/1000+(65×2+130×2+500×2)/1000"
    assert evaluate(bottom.e) == pytest.approx(bottom.v)

    # 层厚同样保留 毫米→米 换算与埋深原文
    depth = raw_dim("2.5+0.3", 2.8) + (t + dim(130)) / 1000
    assert depth.e == "2.5+0.3+(65+130)/1000"
    assert evaluate(depth.e) == pytest.approx(depth.v)


def test_dim_arithmetic_is_value_exact() -> None:
    """每一步运算的算式求值都等于同一步的数值（禁止两套算法各算各的）。"""
    value = raw_dim("2.5+0.3", 2.8)
    for expression, number in (
        (value + dim(0.195), 2.995),
        (value - dim(0.5), 2.3),
        (dim(600) / 1000, 0.6),
        (dim(0.6) / 2 + dim(65) / 1000, 0.365),
        (dim(4.2) * dim(0.4), 1.68),
        (-dim(0.4), -0.4),
    ):
        assert evaluate(expression.e) == pytest.approx(number, rel=1e-12)
        assert expression.v == pytest.approx(number, rel=1e-12)


def test_dim_subtraction_keeps_parentheses() -> None:
    """X-(A+B) 不能丢括号写成 X-A+B。"""
    expression = dim(3.0) - (dim(1.0) + dim(1.0))
    assert expression.v == pytest.approx(1.0)
    assert expression.e == "3-(1+1)"


def test_dim_sum_and_min_skip_empty_parts() -> None:
    assert dim_sum(dim(0.0), dim(200), dim(300)).e == "200+300"
    assert scale_sum((dim(0), dim(100), dim(500)), 2.0).e == "100×2+500×2"
    assert dim_min(dim(2.0), dim(0.5)).v == 0.5
    assert dim_min(dim(2.0), dim(0.5)).e == "0.5"


def test_dim_division_by_one_keeps_expression() -> None:
    assert (dim(2.5) / 1).e == "2.5"


# --------------------------------------------------------------------------- #
# 原始数据 vs 派生数字
# --------------------------------------------------------------------------- #
def test_raw_dim_keeps_user_expression_text() -> None:
    assert raw_dim("2.5+0.3", 2.8).e == "2.5+0.3"  # 录入算式按原文
    assert raw_dim("2.5", 2.5).e == "2.5"  # 纯数字照旧
    assert raw_dim("2．5*2", 5.0).e == "2.5*2"  # 全角归一化


def test_same_number_from_different_sources_stays_distinct() -> None:
    """数值相同但来源不同不合并：图集 65mm 的换算写成 65/1000，不是算好的 0.065。"""
    assert dim(65).e == "65"  # 查表值就是单个数字
    assert (dim(65) / 1000).e == "65/1000"  # 换算写全
    assert (dim(65) / 1000).v == pytest.approx(dim(0.065).v)
    assert (dim(65) / 1000).e != dim(0.065).e
