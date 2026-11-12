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
    NamedValue,
    QDict,
    Quantity,
    dim,
    dim_min,
    dim_sum,
    mm,
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
    assert wrap("65*2") == "65*2"
    assert wrap("(65+130)/1000") == "(65+130)/1000"  # 加减在括号内，顶层是除
    assert wrap("1.99+(65+130)/1000") == "(1.99+(65+130)/1000)"  # 顶层加减 → 加括号
    assert wrap("0.3-0.117") == "(0.3-0.117)"


def test_wrap_tight_also_protects_divisor_positions() -> None:
    # 除数位置：顶层乘除必须括号，否则 a/(b*c) 会变成 a/b*c
    assert wrap("65*2", tight=True) == "(65*2)"
    assert wrap("600/1000", tight=True) == "(600/1000)"
    assert wrap("2.85", tight=True) == "2.85"


def test_atomic_expressions_never_need_parentheses() -> None:
    """纯数字 / 单变量 / 函数调用是原子表达式，任何位置都不加括号。"""
    for text in ("2", "233.988", "0.5", "SIN(1.2)", "CEILING(40/1.2,1)"):
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
    width = Dim(1.99, "600/1000+(65*2+130*2+500*2)/1000")  # 顶层加减
    count = Dim(100.0, "50*2")  # 顶层乘除

    assert engine.pre_sub("1*2*height", height, width, count) == "1*2*2"
    # 顶层加减：任何位置都括起来
    assert engine.pre_sub("width*B", height, width, count) == (
        "(600/1000+(65*2+130*2+500*2)/1000)*B"
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
    assert bottom.e == "600/1000+(65*2+130*2+500*2)/1000"
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
    assert scale_sum((dim(0), dim(100), dim(500)), 2.0).e == "100*2+500*2"
    assert dim_min(dim(2.0), dim(0.5)).v == 0.5
    assert dim_min(dim(2.0), dim(0.5)).e == "0.5"


def test_dim_division_by_one_keeps_expression() -> None:
    assert (dim(2.5) / 1).e == "2.5"
    # 除数是带记法指数的 1（如 1m）时不能走 ÷1 捷径：商要降指数并保留算式，
    # 否则 500mm/1000mm 会被当成 500mm，再乘高度就错成面积（10^6 vs 10^3）。
    one_length = mm(1000)
    quotient = mm(500) / one_length
    assert quotient.v == pytest.approx(0.5)
    assert quotient.s == 0
    assert quotient.e == "500/1000"
    assert (quotient * mm(1000)).s == 3


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
    out.add("回填|中粗砂|m3", 2.0, "1*2", "坞膀下半")
    out.add("回填|中粗砂|m3", 0.5, "0.5", "管顶50cm")
    out.add("回填|中粗砂|m3", -0.3, "0.3+1*0", "坞膀扣弓形")
    quantity = out.get("回填|中粗砂|m3")

    assert quantity.expression == "1*2+0.5-(0.3+1*0)"
    assert quantity.steps() == [
        ("坞膀下半", "1*2"),
        ("管顶50cm", "+0.5"),
        ("坞膀扣弓形", "-(0.3+1*0)"),
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
    """多原则合并（extend）与 *数量 都保留每步说明与算式。"""
    first = QDict()
    first.add("开挖|Ⅲ类土|m3", 1.0, "1*(600/1000)", "垫层~坞膀上半")
    second = QDict()
    second.add("开挖|Ⅲ类土|m3", 2.0, "2*3", "第2级围护段")
    merged = QDict()
    merged.extend(first)
    merged.extend(second)
    quantity = merged.get("开挖|Ⅲ类土|m3")
    assert [note for note, _text in quantity.steps()] == ["垫层~坞膀上半", "第2级围护段"]
    merged.scale(3.0, expr="3")  # *数量 3（系数与算式原文都是 3）
    assert quantity.steps() == [
        ("垫层~坞膀上半", "1*(600/1000)*3"),
        ("第2级围护段", "+2*3*3"),
    ]
    assert quantity.value == pytest.approx(9.0)


def test_compact_terms_factor_volume_tail_into_areas() -> None:
    """多分项同带 /10^s*数量 尾：主算式合并为 (S1+S2-…)/10^s*数量，分项即面积。"""
    import re

    area1 = "(2*(600+65*2+130*2+500*2)+2*2995*1)*2995/2"
    area2 = "(2*(1500+100*2+500*2)+2*3100*1)*3100/2"
    deduction = "(130+182)*(600+65*2+130*2)"
    out = QDict()
    out.add("垫层|中粗砂|m3", evaluate(f"({area1})/10^6*100"), f"({area1})/10^6*100", "垫层")
    out.add("垫层|中粗砂|m3", evaluate(f"({area2})/10^6*100"), f"({area2})/10^6*100", "坞膀")
    out.add(
        "垫层|中粗砂|m3",
        -evaluate(f"({deduction})/10^6*100"),
        f"({deduction})/10^6*100",
        "扣管位",
    )
    view = out.get("垫层|中粗砂|m3").presentation()

    assert view.formula == "V=(S1+S2-S3)/10^6*100"
    assert [term.symbol for term in view.terms] == ["S1", "S2", "S3"]
    # 分项值 = 面积式的求值（mm²）；扣减项的面积仍为正，负号由主算式表达
    assert view.terms[2].value == pytest.approx(evaluate(deduction))
    # 主算式迭代展开后 == 完整式 == 数值
    expanded = view.main
    for _ in range(len(view.definitions) + 1):
        for item in view.definitions:
            expanded = re.sub(rf"\b{item.symbol}\b", f"({item.expression})", expanded)
    assert evaluate(expanded) == pytest.approx(evaluate(view.full), rel=1e-9)
    assert evaluate(view.full) == pytest.approx(
        evaluate(f"({area1})/10^6*100+({area2})/10^6*100-({deduction})/10^6*100")
    )


def test_compact_terms_keep_v_form_without_common_tail() -> None:
    """无公共尾（湿土排水复用式头部带加减）或尾不一致：维持 V 形态。"""
    out = QDict()
    out.add("降水|湿土排水|m3", 3.0, "(A)/10^6*100+(B)/10^6*100", "湿土排水")
    out.add("降水|湿土排水|m3", 1.0, "1", "其它")
    view = out.get("降水|湿土排水|m3").presentation()
    assert view.formula == "V=V1+V2"

    # 单分项带尾也不合并（主算式就是该式本身）
    out2 = QDict()
    out2.add("管材|混凝土管 Dn600|m", 1.0, "1", "管材含量")
    view2 = out2.get("管材|混凝土管 Dn600|m").presentation()
    assert view2.formula == "V=1"


def test_generic_intermediate_symbols_carry_nature_prefix() -> None:
    """通用中间量按性质取名 tB/tH/tS（宽度/高度/面积），不再出现 X。

    重复片段出现在层高（h）算式里 → 高度类 tH（层高算式是纯竖向链，优先级
    高于 u/v——坡段 1*h 会把高度带进宽度算式）；只在下底宽 / 上底宽算式里
    出现 → 宽度类 tB；同一性质第一个免后缀，其后从 1 开始递增。
    """
    import re

    from app.core.calc.tracer import AreaParts

    width1 = "600+65*2+130*2"
    width2 = "700+75*2+140*2"
    height = "130+182+65"
    out = QDict()
    for note, width in (("垫层", width1), ("坞膀", width2)):
        u_text = f"{width}+500"
        v_text = f"{width}+500+1*({height})"
        h_text = f"({height})"
        area_expr = f"(({u_text})+({v_text}))*({h_text})/2"
        out.add(
            "开挖|Ⅲ类土|m3",
            evaluate(f"({area_expr})/10^6*100"),
            f"({area_expr})/10^6*100",
            note,
            area=AreaParts(
                "trapezoid",
                Dim(evaluate(u_text), u_text),
                Dim(evaluate(v_text), v_text),
                Dim(evaluate(h_text), h_text),
            ),
        )
    view = out.get("开挖|Ⅲ类土|m3").presentation()
    symbols = [item.symbol for item in view.definitions]
    assert not any(symbol.startswith("X") for symbol in symbols), symbols
    widths = [symbol for symbol in symbols if symbol.startswith("tB")]
    heights = [symbol for symbol in symbols if symbol.startswith("tH")]
    # 两条宽度片段：第一个免后缀，第二个从 1 开始；高度片段只有一条
    assert sorted(widths) == ["tB", "tB1"], symbols
    assert heights == ["tH"], symbols
    # 展开定义后主算式仍与完整式同值
    expanded = view.main
    for _ in range(len(view.definitions) + 1):
        for item in view.definitions:
            expanded = re.sub(rf"\b{item.symbol}\b", f"({item.expression})", expanded)
    assert evaluate(expanded) == pytest.approx(evaluate(view.full), rel=1e-9)


def test_candidate_natures_classify_leftover_fragments() -> None:
    """游离片段（不在任何 u/v/h 算式里）按值量级兜底：面积量级 → tS，其余 → tB。

    弓形半径 Do/2 这类只出现在公式型分项（扣管位·弓形）里的横向长度归宽度类；
    达到面积量级（mm² ≥ 1e5）的重复片段才是面积类。
    """
    from app.core.calc.tracer import (
        _Candidate,
        _assign_symbols,
        _candidate_natures,
        _node_key,
        _parse_expression,
    )

    def candidate(text: str) -> _Candidate:
        node = _parse_expression(text)
        return _Candidate(
            key=_node_key(node), text=text, node=node, length=len(text), count=2, depth=0
        )

    candidates = [candidate("(600+65*2)/2"), candidate("5000*5000")]
    natures = _candidate_natures([], candidates)
    assert natures[candidates[0].key] == "width"
    assert natures[candidates[1].key] == "area"
    symbols = _assign_symbols(candidates, natures)
    assert list(symbols.values()) == ["tB", "tS"]


def test_merged_rows_carry_member_ids() -> None:
    """合并行的 quantities 记录 (构件id, Quantity)，供详情弹窗按成员定位断面。"""
    from app.views.panels.unit_panel import UnitPanel

    first = QDict()
    first.add("开挖|Ⅲ类土|m3", 10.0, "10", "垫层")
    second = QDict()
    second.add("开挖|Ⅲ类土|m3", 20.0, "20", "垫层")
    merged = UnitPanel._merge_quantities([(101, first), (202, second)])[0]
    assert [member_id for member_id, _q in merged.quantities] == [101, 202]
    assert [q.value for _mid, q in merged.quantities] == [10.0, 20.0]


def test_merged_rows_keep_per_element_steps() -> None:
    """多选构件时（定额页签合并行）：算式用 " + " 连接，步骤按构件分组列出。"""
    from app.views.panels.unit_panel import UnitPanel, _expression_detail

    first = QDict()
    first.add("开挖|Ⅲ类土|m3", 10.0, "10", "垫层~覆土")
    second = QDict()
    second.add("开挖|Ⅲ类土|m3", 20.0, "20", "垫层~覆土")
    merged = UnitPanel._merge_quantities([(None, first), (None, second)])[0]
    assert merged.value == pytest.approx(30.0)
    assert merged.expression == "10 + 20"
    assert merged.display_expression == "V1+V2"
    assert _expression_detail(merged) == (
        "V=V1+V2 ＝ 30\n\n"
        "构件1：V=10 ＝ 10\n完整式：10\n\n"
        "构件2：V=20 ＝ 20\n完整式：20"
    )


def test_expression_detail_tooltip() -> None:
    """tooltip / 弹窗正文：完整算式 + 逐步骤算式；单项带说明时只补说明。"""
    from app.views.panels.unit_panel import _expression_detail

    out = QDict()
    out.add("垫层|中粗砂|m3", 1.99, "1.99", "垫层")
    out.add("垫层|中粗砂|m3", -0.3, "0.3", "垫层扣基础占位")
    assert _expression_detail(out.get("垫层|中粗砂|m3")) == (
        "V=V1-V2 ＝ 1.69\n\n"
        "分项（按主算式中的符号相加）：\n"
        "V1（垫层）＝ 1.99 ＝ 1.99    来源：垫层\n"
        "V2（垫层扣基础占位）＝ 0.3 ＝ 0.3    来源：垫层扣基础占位\n\n"
        "完整数值算式（可复制到 Excel 复核）：\n1.99-0.3"
    )

    single = QDict()
    single.add("管道基础|混凝土|m3", 1.0, "2-1", "基础 2 − 120° 弓形占位 1")
    assert _expression_detail(single.get("管道基础|混凝土|m3")) == (
        "V=2-1 ＝ 1\n\n基础 2 − 120° 弓形占位 1\n\n"
        "完整数值算式（可复制到 Excel 复核）：\n2-1"
    )


def test_presentation_extracts_semantic_intermediates() -> None:
    """槽底宽 / 计算深度提成中间量：主算式缩短，但定义仍全是原始参数。"""
    out = QDict()
    expression = (
        "(2*(600+(65*2+130*2+500*2))"
        "+2*((2.5+0.3)*1000+(65+130))*1)"
        "*((2.5+0.3)*1000+(65+130))/2/10^6*100"
    )
    out.add(
        "开挖|Ⅲ类土|m3",
        1493.0075,
        expression,
        "垫层~覆土",
        tags=(
            NamedValue(
                "600+(65*2+130*2+500*2)",
                "槽底宽",
                "管径+图集+面宽",
            ),
            NamedValue(
                "(2.5+0.3)*1000+(65+130)",
                "计算深度",
                "埋深+壁厚+垫层",
            ),
        ),
    )
    view = out.get("开挖|Ⅲ类土|m3").presentation()

    assert view.formula == "V=(2*B+2*H*1)*H/2/10^6*100"
    labels = {item.label for item in view.definitions}
    assert {"槽底宽", "计算深度"} <= labels
    # 派生结果只出现在 value，不允许以算好的数字回填定义式。
    bottom = next(item for item in view.definitions if item.label == "槽底宽")
    assert bottom.expression == "600+(65*2+130*2+500*2)"
    assert "1.99" not in bottom.expression
    assert bottom.value == pytest.approx(1990.0)


def test_presentation_expands_back_to_full_value() -> None:
    """主算式按定义逐层展开（用定义结果仅为测试）必须等于工程量。"""
    import re

    out = QDict()
    expression = (
        "((130+182)/1000*(600/1000+(65*2+130*2)/1000)"
        "-(PI()*(600+65*2)*(600+65*2)/4*120/360"
        "-(600+65*2)*(600+65*2)/8*SIN(120*PI()/180))/1000/1000)*100"
    )
    out.add(
        "管道基础|混凝土|m3",
        evaluate(expression),
        expression,
        "基础扣弓形占位",
        tags=(
            NamedValue("(130+182)/1000", "基础厚度", "C1+C2"),
            NamedValue(
                "600/1000+(65*2+130*2)/1000",
                "基础宽度",
                "断面宽+2×(壁厚+工作面加宽)",
            ),
            NamedValue(
                "(PI()*(600+65*2)*(600+65*2)/4*120/360"
                "-(600+65*2)*(600+65*2)/8*SIN(120*PI()/180))/1000/1000",
                "弓形占位面积",
                "外径与120°基础角度",
            ),
        ),
    )
    quantity = out.get("管道基础|混凝土|m3")
    view = quantity.presentation()
    expanded = view.main
    definitions = {item.symbol: item for item in view.definitions}
    for _ in range(len(definitions) + 1):
        for symbol, item in definitions.items():
            expanded = re.sub(rf"\b{symbol}\b", f"({item.expression})", expanded)
    assert not any(re.search(rf"\b{symbol}\b", expanded) for symbol in definitions)
    assert evaluate(expanded) == pytest.approx(quantity.value, rel=1e-12)


def test_presentation_definitions_are_complete_and_not_precomputed() -> None:
    """所有主算式里的符号都有定义，且定义中没有把派生量算成单个数字。"""
    import re

    out = QDict()
    out.add(
        "开挖|Ⅲ类土|m3",
        1493.0075,
        "(2*(600/1000+(65*2+130*2+500*2)/1000)"
        "+2*(2.5+0.3+(65+130)/1000)*1)"
        "*(2.5+0.3+(65+130)/1000)/2*100",
        "垫层~覆土",
        tags=(
            NamedValue(
                "600/1000+(65*2+130*2+500*2)/1000",
                "槽底宽",
                "管径+图集+面宽",
            ),
            NamedValue(
                "2.5+0.3+(65+130)/1000",
                "计算深度",
                "埋深+壁厚+垫层",
            ),
        ),
    )
    view = out.get("开挖|Ⅲ类土|m3").presentation()
    names = {item.symbol for item in view.definitions}
    used = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", view.main))
    used -= {"V", "PI", "SIN", "CEILING", "ROUND", "ROUNDUP", "SQRT", "ABS"}
    assert used <= names, f"主算式用了未定义符号：{used - names}"
    for item in view.definitions:
        assert item.expression
        # 定义式的数值部分仍是原始数据；派生结果放在 value 列。
        if item.label == "槽底宽":
            assert "600" in item.expression and "65" in item.expression


def test_presentation_symbolizes_component_parameters() -> None:
    """构件参数 t/a/C1/C2：中间量表给出符号定义，主算式 / 定义式用符号代替数值。

    a 与 C1 数值相同（都是 130）也必须各归各的：定义式按参数集合区分，
    B（断面宽 + 2×(壁厚+工作面加宽)）里是 a，H（埋深 + 壁厚 + 垫层厚）里是 C1。
    """
    from app.core.calc.tracer import mm

    t = mm(65).as_param("t", "管道壁厚", "图集参数 t")
    a = mm(130).as_param("a", "工作面加宽", "图集参数 a")
    c1 = mm(130).as_param("C1", "垫层厚", "图集参数 C1")
    bottom = (mm(600) + scale_sum((t, a), 2.0)).named(
        "槽底宽", "断面宽 + 2×(壁厚+工作面加宽)"
    )
    height = (mm(2500) + t + c1).named("计算深度", "埋深 + 壁厚 + 垫层厚")
    area = Dim(
        (2 * bottom.v + 2 * height.v) * height.v / 2,
        f"(2*{wrap(bottom.e)}+2*{wrap(height.e)}*1)*{wrap(height.e)}/2",
        bottom.tags + height.tags,
        bottom.s + height.s,
    )
    out = QDict()
    out.add("开挖|Ⅲ类土|m3", area.v, area, "垫层~覆土", tags=area.tags)
    quantity = out.get("开挖|Ⅲ类土|m3")
    view = quantity.presentation()

    definitions = {item.symbol: item for item in view.definitions}
    assert {"t", "a", "C1"} <= definitions.keys()
    assert "C2" not in definitions  # 没用到就不进符号表
    assert definitions["t"].expression == "65"
    assert definitions["t"].value == pytest.approx(65.0)
    assert definitions["a"].expression == "130"
    assert definitions["C1"].expression == "130"
    assert definitions["B"].expression == "600+t*2+a*2"
    assert definitions["H"].expression == "2500+t+C1"
    assert view.main == "(2*B+2*H*1)*H/2/10^6"
    # 完整数值算式保持数字，供复制 Excel / 复核
    assert "t" not in view.full and "65" in view.full

    # 定义逐层展开后仍等于工程量
    import re

    expanded = view.main
    for _ in range(len(definitions) + 1):
        for symbol, item in definitions.items():
            expanded = re.sub(rf"\b{symbol}\b", f"({item.expression})", expanded)
    assert evaluate(expanded) == pytest.approx(quantity.value, rel=1e-12)


def test_presentation_assigns_equal_valued_parameters_in_order() -> None:
    """a 与 C1 数值相同时，按算式左→右的出现顺序分别对应，不写错符号。"""
    from app.core.calc.tracer import mm

    a = mm(130).as_param("a", "工作面加宽", "图集参数 a")
    c1 = mm(130).as_param("C1", "垫层厚", "图集参数 C1")
    total = a + c1  # 130+130：标签顺序 a → C1，算式出现顺序也是 a → C1
    out = QDict()
    out.add("测试|量|m", total.v, total, "a+C1", tags=total.tags)
    view = out.get("测试|量|m").presentation()

    assert view.main == "(a+C1)/10^3"
    definitions = {item.symbol: item for item in view.definitions}
    assert definitions["a"].expression == "130"
    assert definitions["C1"].expression == "130"
    assert view.full == "(130+130)/10^3"


def test_presentation_triangle_area_uses_v_h_form() -> None:
    """三角形面积行统一成 v*h/2（下底为 0，没有 u）。"""
    from app.core.calc.groove import trapezoid_expr
    from app.core.calc.tracer import mm

    height = mm(2000).named("高", "测试高")
    slope = dim(1.0).named("放坡系数", "测试坡")
    area = trapezoid_expr(mm(0.0), height, slope)
    assert area.area is not None and area.area.kind == "triangle"

    out = QDict()
    out.add("测试|三角|m2", area.v, area, "三角形", tags=area.tags)
    view = out.get("测试|三角|m2").presentation()

    assert view.main == "(v1*h1/2)/10^6"
    term = view.terms[0]
    assert [part.symbol for part in term.parts] == ["v1", "h1"]
    assert term.parts[0].expression == "2*2000*1"  # 底宽 = 2×高×放坡
    assert term.parts[1].expression == "2000"  # 高
    assert "u1" not in {part.symbol for part in term.parts}


def test_presentation_splits_overlong_definitions() -> None:
    """定义式超过单元格可显示宽度（_MAX_DEFINITION_LENGTH）时嵌套提取。

    两条深度不同的弓形扣减式（合槽扣管占位的真实形态）：弓形式 90+ 字符且
    各只出现一次，常规“确有重复才提取”不会提；长度控制把弓形式连同内部
    深度链逐轮提成新中间量，最终所有会写进单元格的式子都收进上限，
    主算式按定义展开仍与完整式同值。
    """
    import re

    from app.core.calc.tracer import _MAX_DEFINITION_LENGTH

    def bow(depth: str) -> str:
        return (
            f"450^2*ACOS((450-({depth}))/450)-(450-({depth}))"
            f"*SQRT(({depth})*(2*450-({depth})))"
        )

    shallow, deep = "200+100+50", "200+100+50+30"
    # 深弓 − 浅弓 > 0：expr 存数值代入部分（正值），符号由 value 决定；
    # 弓形式顶层是加减，作减数时要像引擎 wrap() 一样先括起来
    expression = f"(({bow(deep)})-({bow(shallow)}))/10^6*100"
    assert len(expression) > _MAX_DEFINITION_LENGTH  # 前提：完整式确实超限
    out = QDict()
    out.add("回填|中粗砂|m3", evaluate(expression), expression, "扣管位")
    view = out.get("回填|中粗砂|m3").presentation()

    assert len(view.main) <= _MAX_DEFINITION_LENGTH
    assert view.definitions, "应有中间量定义"
    for item in view.definitions:
        assert len(item.expression) <= _MAX_DEFINITION_LENGTH, item
    # 展开不变式：主算式按定义逐层展开 == 完整式 == 原式数值
    expanded = view.main
    for _ in range(len(view.definitions) + 1):
        for item in view.definitions:
            expanded = re.sub(rf"\b{item.symbol}\b", f"({item.expression})", expanded)
    assert evaluate(expanded) == pytest.approx(evaluate(view.full), rel=1e-9)
    assert evaluate(view.full) == pytest.approx(evaluate(expression), rel=1e-9)


def test_presentation_keeps_short_definitions_untouched() -> None:
    """长度控制只针对超限式：本就收进上限的展示不新增中间量。"""
    out = QDict()
    out.add("垫层|中粗砂|m3", 1.0, "(600+65*2+130*2+500*2)*0.1", "垫层")
    view = out.get("垫层|中粗砂|m3").presentation()
    assert view.main == "(600+65*2+130*2+500*2)*0.1"
    assert not any(
        item.kind == "intermediate" and not item.basic for item in view.definitions
    )


def test_expression_outline_does_not_build_presentation() -> None:
    """表格首屏摘要必须零解析：不调用 presentation，多分项按符号列说明。"""
    out = QDict()
    out.add("回填|中粗砂|m3", 1.0, "1", "垫层")
    out.add("回填|中粗砂|m3", 2.0, "2", "坞膀下半")
    out.add("回填|中粗砂|m3", -0.5, "0.5", "扣弓形")
    quantity = out.get("回填|中粗砂|m3")

    def _boom():
        raise AssertionError("expression_outline 不应生成 presentation")

    quantity.presentation = _boom  # type: ignore[method-assign]
    assert quantity.expression_outline == "垫层+坞膀下半-扣弓形"

    # 扣除项排最前时以 - 开头；同名说明同符号去重
    out2 = QDict()
    out2.add("回填|素土|m3", -1.0, "1", "扣基础占位")
    out2.add("回填|素土|m3", 2.0, "2", "夯填")
    out2.add("回填|素土|m3", 0.5, "0.5", "夯填")
    assert out2.get("回填|素土|m3").expression_outline == "-扣基础占位+夯填"

    out3 = QDict()
    out3.add("挖|土方|m3", 1.0, "1", "挖土")
    out3.add("挖|土方|m3", 1.0, "1", "挖土")
    out3.add("挖|土方|m3", -0.5, "0.5", "扣基础占位")
    out3.add("挖|土方|m3", -0.5, "0.5", "扣基础占位")
    assert out3.get("挖|土方|m3").expression_outline == "挖土-扣基础占位"


def test_expression_detail_is_generated_on_demand(qapp) -> None:
    """工程量表格首屏为空 tooltip；双击/复制时才生成主式、定义和完整算式。"""
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    from app.views.panels.unit_panel import (
        _EXPR_DETAIL_ROLE,
        _EXPR_MAIN_ROLE,
        _EXPR_QUANTITY_ROLE,
        _EXPR_READY_ROLE,
        UnitPanel,
    )

    out = QDict()
    out.add(
        "开挖|Ⅲ类土|m3",
        1493.0075,
        "(2*(600/1000+(65*2+130*2+500*2)/1000)"
        "+2*(2.5+0.3+(65+130)/1000)*1)"
        "*(2.5+0.3+(65+130)/1000)/2*100",
        "垫层~覆土",
        tags=(
            NamedValue(
                "600/1000+(65*2+130*2+500*2)/1000",
                "槽底宽",
                "管径+图集+面宽",
            ),
            NamedValue(
                "2.5+0.3+(65+130)/1000",
                "计算深度",
                "埋深+壁厚+垫层",
            ),
        ),
    )
    quantity = out.get("开挖|Ⅲ类土|m3")
    table = QTableWidget(1, 6)
    item = QTableWidgetItem(quantity.expression_outline)
    item.setData(_EXPR_QUANTITY_ROLE, quantity)
    table.setItem(0, 5, item)

    assert item.toolTip() == ""
    assert not item.data(_EXPR_READY_ROLE)
    assert UnitPanel._ensure_expression_item(None, item) is True  # type: ignore[arg-type]
    assert item.data(_EXPR_READY_ROLE)
    assert item.data(_EXPR_MAIN_ROLE) == "(2*B+2*H*1)*H/2*100"
    # 首屏摘要原样保留：悬停不刷新单元格文字、不弹 tooltip
    assert item.text() == quantity.expression_outline
    assert item.toolTip() == ""
    detail = item.data(_EXPR_DETAIL_ROLE)
    assert "中间量" in detail
    assert "完整数值算式" in detail


def test_mm_notation_construction_and_conversion() -> None:
    """mm 记法构造器：表值原样进算式（v 已换算 m），m 录入量按规则桥接。"""
    from app.core.calc.tracer import mm, mm_dim, mm_of_m

    # mm 表值：算式就是 mm 原值，数值换算成 m
    assert mm(600).e == "600"
    assert mm(600).s == 3
    assert mm(600).v == pytest.approx(0.6)

    # 用户按 mm 录入的参数原文：原文保留、数值 /1000
    assert mm_dim(dim(400)).e == "400"
    assert mm_dim(dim(400)).v == pytest.approx(0.4)

    # m 录入量 → mm 记法：纯数字折叠，录入算式保留原文 ×1000
    assert mm_of_m(dim(2.5)).e == "2500"
    assert mm_of_m(raw_dim("2.5", 2.5)).e == "2500"
    assert mm_of_m(raw_dim("2.5+0.3", 2.8)).e == "(2.5+0.3)*1000"
    assert mm_of_m(raw_dim("2.5+0.3", 2.8)).v == pytest.approx(2.8)
    # 已是 mm 记法原样返回
    already = mm(600)
    assert mm_of_m(already) is already

    # to_m：m 记法视图（公式路径），纯数字折叠回 m 值、复合式补 /1000
    assert mm(600).to_m().e == "0.6"
    assert (mm(600) + mm(130)).to_m().e == "(600+130)/1000"
    assert (mm(600) + mm(130)).to_m().v == pytest.approx(0.73)
    assert (mm(600) + mm(130)).to_m().s == 0


def test_mm_space_algebra_records_scale_suffix() -> None:
    """mm 记法代数：乘除指数相加减、加减要求同指数；记录时统一 /10^s。"""
    from app.core.calc.tracer import Dim, mm, mm_of_m, raw_dim

    bottom = mm(600) + mm(65) * 2 + mm(130) * 2
    assert bottom.s == 3
    assert bottom.e == "600+65*2+130*2"
    # 面积 = mm × mm → s=6；记录成 (mm²)/10^6，求值 = 每延米体积（m³/m）
    area = Dim(
        bottom.v * bottom.v * 2,
        f"({bottom.e})*({bottom.e})*2",
        (),
        bottom.s + bottom.s,
    )
    quantity = Quantity(key="开挖|Ⅲ类土|m3")
    quantity.add_term(area.v, area, "垫层~覆土")
    assert quantity.terms[0].expr == "(600+65*2+130*2)*(600+65*2+130*2)*2/10^6"
    assert evaluate(quantity.terms[0].expr) == pytest.approx(area.v, rel=1e-12)

    # m² 每延米（s=3）记录成 /10^3
    template = mm(100) * 2
    q2 = Quantity(key="垫层|模板|m2")
    q2.add_term(template.v, template, "垫层模板")
    assert q2.terms[0].expr == "100*2/10^3"
    assert evaluate(q2.terms[0].expr) == pytest.approx(template.v, rel=1e-12)

    # 无量纲（s=0）原样记录：管材含量、井点数
    q3 = Quantity(key="管材|混凝土管 Dn600|m")
    q3.add_term(1.0, "1", "管材含量")
    assert q3.terms[0].expr == "1"

    # 混空间加减立即报错（漏桥接 fail-fast）
    with pytest.raises(AssertionError):
        _ = bottom + raw_dim("2.5", 2.5)
    with pytest.raises(AssertionError):
        _ = raw_dim("2.5", 2.5) - bottom

    # mm_of_m 折叠规则：纯数字折叠、公式 ×1000
    assert mm_of_m(raw_dim("2.5+0.3", 2.8)).e == "(2.5+0.3)*1000"
    assert evaluate(mm_of_m(raw_dim("2.5+0.3", 2.8)).e) == pytest.approx(2800)
