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
    QDict,
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


# --------------------------------------------------------------------------- #
# 中间步骤：说明挂在项上，各步算式拼接 = 完整算式
# --------------------------------------------------------------------------- #
def test_steps_carry_note_and_expr_per_term() -> None:
    out = QDict()
    out.add("回填|中粗砂|m3", 2.0, "1×2", "坞膀下半")
    out.add("回填|中粗砂|m3", 0.5, "0.5", "管顶50cm")
    out.add("回填|中粗砂|m3", -0.3, "0.3+1×0", "坞膀扣弓形")
    quantity = out.get("回填|中粗砂|m3")

    assert quantity.expression == "1×2+0.5-(0.3+1×0)"
    assert quantity.steps() == [
        ("坞膀下半", "1×2"),
        ("管顶50cm", "+0.5"),
        ("坞膀扣弓形", "-(0.3+1×0)"),
    ]
    # 不变式：各步算式按顺序拼接就是完整算式（展示层不再另拼字符串）
    assert "".join(text for _note, text in quantity.steps()) == quantity.expression


def test_steps_skip_zero_terms_with_their_note() -> None:
    """数值为 0 的项不进算式，其说明也一并丢弃，步骤与算式严格一一对应。"""
    out = QDict()
    out.add("开挖|Ⅲ类土|m3", 1.5, "1.5", "垫层~覆土")
    out.add("开挖|Ⅲ类土|m3", 0.0, "0", "空段")
    quantity = out.get("开挖|Ⅲ类土|m3")
    assert quantity.steps() == [("垫层~覆土", "1.5")]
    assert quantity.value == pytest.approx(1.5)


def test_steps_survive_merge_and_scale() -> None:
    """多原则合并（extend）与 ×数量 都保留每步说明与算式。"""
    first = QDict()
    first.add("开挖|Ⅲ类土|m3", 1.0, "1×(600/1000)", "垫层~坞膀上半")
    second = QDict()
    second.add("开挖|Ⅲ类土|m3", 2.0, "2×3", "第2级围护段")
    merged = QDict()
    merged.extend(first)
    merged.extend(second)
    quantity = merged.get("开挖|Ⅲ类土|m3")
    assert [note for note, _text in quantity.steps()] == ["垫层~坞膀上半", "第2级围护段"]
    merged.scale(3.0, expr="3")  # ×数量 3（系数与算式原文都是 3）
    assert quantity.steps() == [
        ("垫层~坞膀上半", "1×(600/1000)×3"),
        ("第2级围护段", "+2×3×3"),
    ]
    assert quantity.value == pytest.approx(9.0)


def test_merged_rows_keep_per_element_steps() -> None:
    """多选构件时（定额页签合并行）：算式用 " + " 连接，步骤按构件分组列出。"""
    from app.views.panels.unit_panel import UnitPanel, _expression_detail

    first = QDict()
    first.add("开挖|Ⅲ类土|m3", 10.0, "10", "垫层~覆土")
    second = QDict()
    second.add("开挖|Ⅲ类土|m3", 20.0, "20", "垫层~覆土")
    merged = UnitPanel._merge_quantities([first, second])[0]
    assert merged.value == pytest.approx(30.0)
    assert merged.expression == "10 + 20"
    assert _expression_detail(merged) == (
        "10 + 20\n\n中间步骤（按构件列出；同一构件内各步拼接 = 该构件的算式）：\n"
        "1. [构件1] 垫层~覆土：10\n2. [构件2] 垫层~覆土：20"
    )


def test_expression_detail_tooltip() -> None:
    """tooltip / 弹窗正文：完整算式 + 逐步骤算式；单项带说明时只补说明。"""
    from app.views.panels.unit_panel import _expression_detail

    out = QDict()
    out.add("垫层|中粗砂|m3", 1.99, "1.99", "垫层")
    out.add("垫层|中粗砂|m3", -0.3, "0.3", "垫层扣基础占位")
    assert _expression_detail(out.get("垫层|中粗砂|m3")) == (
        "1.99-0.3\n\n中间步骤（各步拼接 = 上式）：\n1. 垫层：1.99\n2. 垫层扣基础占位：-0.3"
    )

    single = QDict()
    single.add("管道基础|混凝土|m3", 1.0, "2-1", "基础 2 − 120° 弓形占位 1")
    assert _expression_detail(single.get("管道基础|混凝土|m3")) == "2-1\n\n基础 2 − 120° 弓形占位 1"
