"""表达式记录器。

每个工程量条目产出 ``{key, value, expression, terms}``：

* ``expression`` 是一条代入后的完整算式。**记法口径**：几何尺寸全程以 mm 进
  算式（图集 / 原则表值原样、用户按 m 录入的埋深等换算成 mm），每延米的面积 /
  体积式是纯 mm² 算式，记录时按记法指数统一追加换算 ``/10^6``（体积）、
  ``/10^3``（面积），末尾再乘数量（m 原文），如
  ``(2*(600+65*2+130*2+500*2)+2*(2500+300+65+130)*1)*(2500+300+65+130)/2/10^6*100``；
  用户公式（原则 / 库模板按 m 口径编写）与管材含量、井点数等无量纲式仍为
  m / 无量纲记法，不做换算。记法指数见 :class:`Dim` 的 ``s`` 字段；
* **不预运算**：软件派生出来的数字（槽底宽由管径 + 图集参数 + 面宽原则推出、
  埋深的 mm 换算、换填总厚、弓形占位…）在算式里把计算过程写全，只有直接
  录入 / 查表的原始数据与软件常数才以单个数字出现，见 :class:`Dim`；
* 用户在埋深 / 数量 / 参数 / 含量列写的算式以原文（括号保护）出现在代入位置；
  按 m 录入的纯数字折叠成 mm 整数（单位换算），录入算式保留原文并显式
  ``*1000``（不预计算），见 :func:`mm_of_m`；
* 多来源的量（分层土方、多个构件公式）按项累加，算式用 +/− 连接各代入项；
* 中间步骤（:meth:`Quantity.steps`）＝逐项一行「说明 + 该步算式」（分层、扣减、
  公式类别等），由项本身派生，每步算式按顺序拼起来就是完整算式；
  供详情弹窗查看，不进主算式。
* **展示层**（:meth:`Quantity.presentation`）把长算式拆成“主算式 + 中间量定义”：
  槽底宽、计算深度、外径、弓形面积等重复片段各定义一次，主算式只引用符号；
  定义式仍由原始数字组成，派生结果只放在“计算结果”列，不代回公式。
  ``expression`` 完整算式始终保留，供复制 Excel 与逐项复核。

算式求值与表达式拼接共用同一套数值：先拼出可求值的算式字符串，
再用 core.evaluator 对它求值得到结果，禁止两套算法各算各的。
"""

from __future__ import annotations

import ast
import copy
import re
from dataclasses import dataclass, field
from typing import Iterable

#: 输出算式里的函数名（Excel 写法，展示时统一转大写）
_EXCEL_FUNCTIONS = ("CEILING", "ROUNDUP", "ROUND", "SQRT", "ABS", "POWER", "CEIL", "SIN", "COS")

#: 纯数字（含负号与小数）——这类算式嵌入模板时无需加括号
_NUMERIC = re.compile(r"-?\d+(?:\.\d+)?")

_ADDITIVE = frozenset("+-−")
_MULTIPLICATIVE = frozenset("×*/÷")


def _top_operator(text: str, operators: frozenset[str]) -> bool:
    """括号外是否出现指定运算符（按运算优先级决定要不要加括号用）。"""
    depth = 0
    for character in text:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif depth == 0 and character in operators:
            return True
    return False


def fmt(value: float, digits: int = 4) -> str:
    """数值代入用的数字格式：四舍五入后去尾零（100 → "100"，2.85 → "2.85"）。"""
    text = f"{round(float(value), digits):.{digits}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def needs_parens(expression: str) -> bool:
    """算式作为加减项 / 乘除因子嵌入时是否需要括号：顶层出现加减（含正负号）才需要。

    顶层只有乘除的算式（``600/1000``、``65*2``）嵌进任何位置都不改变结合顺序
    （乘除同级、左结合：``a*b/c*d`` ≡ ``a*(b/c)*d``），纯数字与函数调用同理。
    """
    text = expression.strip()
    if _NUMERIC.fullmatch(text):
        return False
    return _top_operator(text, _ADDITIVE)


def needs_parens_tight(expression: str) -> bool:
    """算式作为除数 / 乘方底数等任意位置嵌入时是否需要括号：顶层有运算符就需要。

    纯数字、单变量、函数调用是“原子”表达式（``2``、``sin(1.2)``），
    放在哪儿都不用括号。
    """
    text = expression.strip()
    if _NUMERIC.fullmatch(text):
        return False
    return _top_operator(text, _ADDITIVE) or _top_operator(text, _MULTIPLICATIVE)


def wrap(expression: str, tight: bool = False) -> str:
    """算式嵌入模板前的保护：按运算优先级决定是否加括号。

    默认（加 / 减 / 乘上下文）只对顶层加减（含正负号）加括号——``65*2`` 这类
    纯乘除嵌进任何位置都不会改变结合顺序；``tight=True`` 用于除数位置或变量
    代入（后面接什么运算符未知），顶层乘除也加括号。纯数字原样保留。
    """
    text = expression.strip()
    needed = needs_parens_tight(text) if tight else needs_parens(text)
    return f"({text})" if needed else text


@dataclass(frozen=True)
class NamedValue:
    """算式片段与它的人类可读含义（只用于展示层，不参与求值）。

    ``expr`` 必须与 :class:`Dim` 当时的 ``e`` 完全一致；展示层按语法树比对，
    命中后把该片段提成中间量。数字本身仍由原始 ``e`` 提供，绝不用 ``value``
    反代回公式，因此不会把派生量预先算成一个数字。
    """

    expr: str
    label: str
    source: str = ""


def _merge_tags(*groups: Iterable[NamedValue]) -> tuple[NamedValue, ...]:
    """合并算式来源标记（同一段算式只保留第一次出现的说明）。"""
    merged: list[NamedValue] = []
    seen: set[str] = set()
    for group in groups:
        for tag in group:
            if not tag.expr or not tag.label or tag.expr in seen:
                continue
            seen.add(tag.expr)
            merged.append(tag)
    return tuple(merged)


def pair(other: "Dim | float") -> tuple[float, str, tuple[NamedValue, ...]]:
    """Dim 与普通数字统一成 (数值, 算式, 来源标记) 三件套。"""
    if isinstance(other, Dim):
        return other.v, other.e, other.tags
    value = float(other)
    return value, fmt(value), ()


@dataclass
class Dim:
    """带算式的数值（埋深、层厚、宽度、图集参数、数量…）：``v`` 为数值，``e`` 为求值等价的算式。

    数值与算式同源：加减乘除都在 Dim 上进行，算式按运算逐级拼出来，
    **不做预运算**——派生量（槽底宽 = 管径 + 图集与面宽参数、换填总厚、
    弓形占位…）在算式里保留全部来源，只有直接录入 / 查表的原始数据
    （管径、图集 t/a/C1/C2、面宽表值）和软件常数（0.5、π 系数）才是一个数字。
    ``e`` 是裸算式，嵌入模板前须经 :func:`wrap`。

    ``tags`` 记录参与运算的语义量（槽底宽、计算深度…），只供展示层把长算式拆成
    “主算式 + 中间量定义”；它不改变 ``v`` / ``e``，也不影响计算与完整算式。

    ``s`` 是**记法指数**：``e`` 求值 = ``v × 10^s``。``v`` 恒为 m（SI）或无量纲；
    ``s=0`` 为 m 记法（用户公式、数量、含量等），``s=3`` 为 mm 记法（几何尺寸
    全程 mm 进算式，见 :func:`mm`）。乘除时指数相加减，加减要求两侧同指数
    （不同记法空间的量必须先经 :func:`mm_of_m` / :meth:`to_m` 桥接，漏桥接
    直接报错，不静默出错值）；工程量记录时按 ``s`` 统一追加 ``/10^s``
    （见 :meth:`Quantity.add_term`）。
    """

    v: float
    e: str
    tags: tuple[NamedValue, ...] = ()
    #: 记法指数：0 = m 记法，3 = mm 记法（e 求值 = v × 10^s）
    s: int = 0

    def named(self, label: str, source: str = "") -> "Dim":
        """给当前量补一个展示名称（返回新 Dim，不改原对象）。"""
        return Dim(
            self.v,
            self.e,
            _merge_tags(self.tags, (NamedValue(self.e, label, source),)),
            self.s,
        )

    def to_m(self) -> "Dim":
        """mm 记法 → m 记法视图（``v`` 不变）：纯数字折叠回 m 值，算式补 ``/1000``。

        用户公式（原则 / 库模板）按 m 口径编写、变量按 m 代入；几何链是 mm
        记法，喂给公式前用本方法桥接：``600`` → ``0.6``、``(600+65*2)/1`` 形态的
        复合式 → ``(600+65*2)/1000``。
        """
        if self.s == 0:
            return self
        if _NUMERIC.fullmatch(self.e.strip()):
            return Dim(self.v, fmt(self.v), self.tags, 0)
        return Dim(self.v, f"({self.e})/1000", self.tags, 0)

    @staticmethod
    def _space_of(other: "Dim | float") -> int:
        """操作数的记法指数（普通数字按 m / 无量纲记法处理）。"""
        return other.s if isinstance(other, Dim) else 0

    def __add__(self, other: "Dim | float") -> "Dim":
        value, expr, tags = pair(other)
        if value == 0:
            return self
        if self.v == 0:
            return Dim(value, expr, _merge_tags(self.tags, tags), self._space_of(other))
        # 加法左结合：右操作数无论顶层是不是加减都不需要括号
        # （A+(B-C) ≡ A+B-C），扁平连接式更短
        self._assert_same_space(other, expr)
        return Dim(
            self.v + value,
            f"{self.e}+{expr}",
            _merge_tags(self.tags, tags),
            self.s,
        )

    __radd__ = __add__

    def __sub__(self, other: "Dim | float") -> "Dim":
        value, expr, tags = pair(other)
        if value == 0:
            return self
        self._assert_same_space(other, expr)
        # 减法的右操作数是算式时必须括起来，否则 X-(A+B) 会变成 X-A+B
        return Dim(
            self.v - value,
            f"{self.e}-{wrap(expr)}",
            _merge_tags(self.tags, tags),
            self.s,
        )

    def _assert_same_space(self, other: "Dim | float", expr: str) -> None:
        """加减两侧记法指数必须一致（mm 链里混入 m 记法量 = 漏桥接，立即报错）。"""
        other_s = self._space_of(other)
        if other_s != self.s:
            raise AssertionError(
                f"记法指数不一致：{self.e!r}(10^{self.s}) 与 {expr!r}(10^{other_s}) "
                "不能直接加减，请用 mm()/mm_of_m()/to_m() 桥接"
            )

    def __neg__(self) -> "Dim":
        return Dim(-self.v, f"-{wrap(self.e)}", self.tags, self.s)

    def __mul__(self, other: "Dim | float") -> "Dim":
        value, expr, tags = pair(other)
        return Dim(
            self.v * value,
            f"{wrap(self.e)}*{wrap(expr)}",
            _merge_tags(self.tags, tags),
            self.s + self._space_of(other),
        )

    __rmul__ = __mul__

    def __truediv__(self, other: "Dim | float") -> "Dim":
        value, expr, tags = pair(other)
        if value == 1:
            return self  # ÷1 不写进算式（只可能是引擎生成的等分，用户写的算式保留原文）
        # 除数位置的算式要更严格：顶层乘除也得括起来，否则 _a/(b*c) 会变成 _a/b*c
        return Dim(
            self.v / value,
            f"{wrap(self.e)}/{wrap(expr, tight=True)}",
            _merge_tags(self.tags, tags),
            self.s - self._space_of(other),
        )


def dim(
    value: float, expr: str | None = None, tags: Iterable[NamedValue] = ()
) -> Dim:
    """纯数值尺寸：算式就是数值本身。"""
    return Dim(float(value), expr if expr is not None else fmt(value), tuple(tags))


def tag_dim(value: Dim, label: str, source: str = "") -> Dim:
    """给已有 Dim 补展示名称，保留其数值、算式和已有来源标记。"""
    return value.named(label, source)


def dim_sum(*parts: Dim) -> Dim:
    """逐项求和：跳过 0 项，每项保留自己的算式（``65+130``、``200+300``）。"""
    total = dim(0.0)
    for part in parts:
        total = total + part
    return total


def scale_sum(parts: Iterable[Dim], factor: float) -> Dim:
    """Σ(项 × 系数)：系数逐项写进算式并跳过 0 项，如 ``65*2+130*2+500*2``。"""
    total = dim(0.0)
    for part in parts:
        if part.v != 0:
            total = total + part * factor
    return total


def dim_min(first: Dim, second: Dim) -> Dim:
    """取较小者（算式取被选中那一项：min 的结果就是它）。"""
    return first if first.v <= second.v else second


def raw_dim(raw: str, value: float) -> Dim:
    """用户录入原文 → 尺寸：纯数字按数值展示，算式原文（归一化后半角）进算式。"""
    from app.core.evaluator import normalize

    text = normalize(str(raw or ""))
    if not text or _NUMERIC.fullmatch(text):
        return dim(value)
    return Dim(value, text)


def mm(value: float, expr: str | None = None, tags: Iterable[NamedValue] = ()) -> Dim:
    """毫米尺寸 → mm 记法：``v`` 仍为 m（毫米值 /1000），算式就是毫米原值。

    几何计算的统一口径：图集表值、原则表值等按 mm 录入的数据用本构造器，
    参与运算的算式保持 mm 整数、不再手写 ``/1000``；记录工程量时由
    :meth:`Quantity.add_term` 按记法指数统一追加 ``/10^6``（体积）或 ``/10^3``
    （面积）。
    """
    return Dim(
        float(value) / 1000.0,
        expr if expr is not None else fmt(value),
        tuple(tags),
        3,
    )


def mm_text(raw: str, value_mm: float) -> Dim:
    """用户按 mm 录入的原文 → mm 记法尺寸（原文可求值时原文进算式，否则数值）。"""
    from app.core.evaluator import normalize

    text = normalize(str(raw or ""))
    if not text or _NUMERIC.fullmatch(text):
        return mm(value_mm)
    return Dim(value_mm / 1000.0, text, (), 3)


def mm_dim(d: Dim) -> Dim:
    """mm 值的 Dim（用户按 mm 录入的参数原文）→ mm 记法：原文进算式、数值 /1000。

    与 :func:`mm_of_m` 的区别：这里的 ``d.v`` 本身是毫米数（构件参数“底板厚 400”
    的 400 是 mm），换算发生在数值上、录入原文原样保留；:func:`mm_of_m` 的
    ``d.v`` 是米数，换算发生在算式上（×1000）。
    """
    if d.s != 0:
        return d
    return Dim(d.v / 1000.0, d.e, d.tags, 3)


def mm_of_m(d: Dim) -> Dim:
    """m 记法长度量 → mm 记法：纯数字折叠成 mm 整数，录入算式保留原文 ×1000。

    用户按 m 录入的埋深等量进几何算式时走这里：纯数字 ``2.5`` 是单位换算，
    直接折叠为 ``2500``；录入算式 ``2.5+0.3`` 保留原文写成 ``(2.5+0.3)*1000``
    （不预计算，用户能在式里核对自己的输入）。已是 mm 记法（``s=3``）的原样返回。
    """
    if d.s != 0:
        return d
    if _NUMERIC.fullmatch(d.e.strip()):
        return Dim(d.v, fmt(d.v * 1000), d.tags, 3)
    return Dim(d.v, f"({d.e})*1000", d.tags, 3)


def prettify(expression: str) -> str:
    """把算式整理成 Excel 可粘贴的写法。

    * 乘除统一 ``*`` ``/``（旧串里的 ``×`` ``÷`` 一并转掉）；
    * 乘方 ``**n`` 写成 Excel 的 ``^n``（不再转上标）；
    * 函数名转大写（``sin`` → ``SIN``、``ceil`` → ``CEILING``）；
    * 常量写成 ``PI()``。

    输出的算式直接复制进 Excel 即为可用公式，所以这里只做“可读化”以外的
    Excel 语法收敛，不改动括号（括号由 :func:`wrap` 按运算优先级决定）。
    """
    text = expression.replace("×", "*").replace("÷", "/")
    text = text.replace("**", "^")
    text = re.sub(r"(?<![A-Za-z])pi(?![A-Za-z(])", "PI()", text)
    for name in _EXCEL_FUNCTIONS:
        text = re.sub(r"(?<![A-Za-z])" + name + r"(?=\s*\()", name, text, flags=re.IGNORECASE)
    return text


# --------------------------------------------------------------------------- #
# 展示层：主算式 + 中间量定义（完整数值算式保持原样）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExpressionDefinition:
    """展示层的一条中间量定义。

    ``expression`` 仍是一条包含原始数字的代入式；``value`` 只用于“计算结果”
    列展示，**不会代回**主算式或其它定义式。
    """

    symbol: str
    label: str
    expression: str
    value: float
    source: str = ""
    kind: str = "intermediate"  # intermediate | subtotal


@dataclass(frozen=True)
class CompactTerm:
    """展示层的一个工程量分项（对应原来的一个带符号 Term）。

    ``value`` 的量纲随形态：合并形态（主算式 ``(S1+S2-…)/10^s*数量``）下
    各分项为断面面积（mm²，即面积式的求值），否则为该项自身的数值。
    ``geometry`` 透传自 :class:`Term`（详情弹窗把分项行高亮到断面图上）。
    """

    symbol: str
    note: str
    expression: str
    value: float
    geometry: tuple[float, float, float, float, float, float] | None = None


@dataclass(frozen=True)
class ExpressionPresentation:
    """一条工程量的展示结构：主算式、定义表、分项式与完整算式。"""

    formula: str
    main: str
    definitions: tuple[ExpressionDefinition, ...]
    terms: tuple[CompactTerm, ...]
    full: str


@dataclass
class _Candidate:
    """语法树里可提成变量的算式片段。"""

    key: str
    text: str
    node: ast.AST
    length: int
    count: int
    depth: int
    label: str = ""
    source: str = ""


_PREFERRED_SYMBOLS = {
    "槽底宽": "B",
    "计算深度": "H",
    "管道外径": "D",
    "管道外径（m）": "D",
    # mm 记法后外径恒为 mm，沿用 D（旧口径按 m 记法时曾用 Dmm 区分）
    "管道外径（mm）": "D",
    "基础宽度": "b",
    "基础厚度": "h",
    "基础断面面积": "S",
    "弓形占位面积": "A",
    "放坡系数": "m",
    "数量": "L",
    "长度": "L",
    "埋深": "h0",
    "垫层厚度": "h_c",
    "底板厚": "t_b",
    "顶板厚": "t_t",
    "外壁厚": "t_w",
    "内壁厚": "t_i",
    "含钢量": "rho",
    "井距": "s",
    "管材含量": "q",
}


def _excel_expression(text: str) -> str:
    """展示层语法树输出 → Excel 写法（乘方 ``^``、去空格）。"""
    return ast.unparse(text).replace(" ", "").replace("**", "^")  # type: ignore[arg-type]


def _parse_expression(expression: str) -> ast.AST | None:
    """解析引擎输出的 Excel 算式；失败返回 None（展示层退回完整算式）。"""
    text = (expression or "").strip().lstrip("=")
    if not text:
        return None
    text = (
        text.replace("×", "*")
        .replace("✕", "*")
        .replace("÷", "/")
        .replace("−", "-")
    )
    # Excel 的 ^ 与 Python 的 ** 同义；现有输出没有以负数为底的乘方，
    # 直接替换不会改变算式结构。
    text = text.replace("^", "**")
    try:
        return ast.parse(text, mode="eval").body
    except (SyntaxError, ValueError):
        return None


def _node_key(node: ast.AST) -> str:
    return ast.dump(node, annotate_fields=False, include_attributes=False)


def _node_value(node: ast.AST) -> float | None:
    """只对“可直接求值”的原式求值（中间量结果列展示用，不参与公式拼接）。"""
    try:
        from app.core.evaluator import evaluate

        return float(evaluate(_excel_expression(node)))
    except Exception:
        return None


class _PowerFold(ast.NodeTransformer):
    """把 ``X*X`` 写成 ``X^2``（纯符号恒等变形，不做任何数值预运算）。"""

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        node = self.generic_visit(node)
        if (
            isinstance(node.op, ast.Mult)
            and _node_key(node.left) == _node_key(node.right)
            and not isinstance(node.left, ast.Constant)
        ):
            return ast.BinOp(left=node.left, op=ast.Pow(), right=ast.Constant(2))
        return node


def _safe_simplify(node: ast.AST) -> ast.AST:
    """仅做不改变数值来源的展示化简（去冗余括号、X*X→X^2）。"""
    return ast.fix_missing_locations(_PowerFold().visit(node))


def _format_definition(expression: str) -> str:
    """中间量定义式的展示格式：按最小括号形式输出。"""
    node = _parse_expression(expression)
    if node is None:
        return prettify(expression)
    return _excel_expression(_safe_simplify(node))


def _collect_tag_keys(tags: Iterable[NamedValue]) -> dict[str, NamedValue]:
    """把来源标记的算式转成语法树 canonical key。"""
    result: dict[str, NamedValue] = {}
    for tag in tags:
        node = _parse_expression(tag.expr)
        if node is not None:
            result.setdefault(_node_key(node), tag)
    return result


def _candidate_key(node: ast.AST, root_keys: set[str]) -> bool:
    """节点是否可能是“可复用中间量”（数字 / 单变量 / 整个分项根节点都排除）。"""
    if isinstance(node, (ast.Constant, ast.Name)):
        return False
    text = _excel_expression(node)
    if _node_key(node) in root_keys:
        return False
    return len(text) >= 5


def _walk_nodes(node: ast.AST, depth: int = 0):
    yield node, depth
    for child in ast.iter_child_nodes(node):
        yield from _walk_nodes(child, depth + 1)


def _assign_symbols(candidates: list[_Candidate]) -> dict[str, str]:
    """给候选片段分配短符号：语义量优先用 B/H/D 等，其余用 X1、X2…。"""
    used: set[str] = set()
    symbols: dict[str, str] = {}
    for candidate in candidates:
        base = _PREFERRED_SYMBOLS.get(candidate.label, "X")
        symbol = base
        index = 2
        while symbol in used:
            symbol = f"{base}{index}"
            index += 1
        used.add(symbol)
        symbols[candidate.key] = symbol
    return symbols


class _ReplaceNodes(ast.NodeTransformer):
    """按 canonical key 替换为变量名；``stop`` 用于定义式自身不再替换。"""

    def __init__(self, symbols: dict[str, str], stop: str = "") -> None:
        self.symbols = symbols
        self.stop = stop

    def visit(self, node: ast.AST) -> ast.AST:
        key = _node_key(node)
        if key != self.stop and key in self.symbols:
            return ast.Name(id=self.symbols[key], ctx=ast.Load())
        return super().visit(node)


def _select_candidates(
    roots: list[ast.AST],
    tag_map: dict[str, NamedValue],
    notes: list[str],
) -> list[_Candidate]:
    """从所有分项语法树中选可提取片段（语义量 → 确有重复的片段）。"""
    root_keys = {_node_key(root) for root in roots}
    aggregated: dict[str, _Candidate] = {}
    for root, note in zip(roots, notes):
        for node, depth in _walk_nodes(root):
            key = _node_key(node)
            if not _candidate_key(node, root_keys):
                continue
            text = _excel_expression(node)
            existing = aggregated.get(key)
            if existing is None:
                tag = tag_map.get(key)
                aggregated[key] = _Candidate(
                    key=key,
                    text=text,
                    node=node,
                    length=len(text),
                    count=1,
                    depth=depth,
                    label=tag.label if tag else "",
                    source=(tag.source if tag and tag.source else note),
                )
            else:
                existing.count += 1
                if not existing.source and note:
                    existing.source = note

    values = list(aggregated.values())
    semantic = [item for item in values if item.label]
    repeated = [
        item
        for item in values
        if not item.label and item.count >= 2 and item.length >= 10
    ]
    semantic.sort(key=lambda item: (item.length, item.count), reverse=True)
    repeated.sort(key=lambda item: item.length * (item.count - 1), reverse=True)

    selected: list[_Candidate] = []
    seen: set[str] = set()

    def take(group: list[_Candidate], limit: int | None) -> None:
        added = 0
        for candidate in group:
            if limit is not None and added >= limit:
                return
            if candidate.key in seen:
                continue
            seen.add(candidate.key)
            selected.append(candidate)
            added += 1

    # 语义量（槽底宽 / 计算深度等 tag 命中）不设上限：多段求和的量每一段都有
    # 自己的语义量，只有全提成 B/B1…、H/H1… 每个分项行才是短式；
    # 通用重复片段仍限 8 个，避免符号表失控。
    take(semantic, None)
    # 通用片段只在“确有重复”时提取；不再把只出现一次的超长片段提成变量
    # （那只会让主算式变成 X1*100，反而多一次跳转）。同时避开语义量的内部，
    # 避免出现“计算深度 = 2.5+0.3+X”这类套娃定义。
    semantic_texts = [item.text for item in selected]
    repeated = [
        item
        for item in repeated
        if not any(item.text in text or text in item.text for text in semantic_texts)
    ]
    # 通用片段之间也不套娃：X2 = X4*…、X3 = X2/1000 这种链条并不比原式好读。
    filtered: list[_Candidate] = []
    for item in repeated:
        if any(item.text in other.text or other.text in item.text for other in filtered):
            continue
        filtered.append(item)
    take(filtered, 8)
    return selected


def _split_volume_tail(expr: str) -> tuple[str, int, str] | None:
    """识别 ``(面积式)/10^s*数量尾`` 形态：返回 (面积式, s, 尾)；不命中返回 None。

    ``/10^s`` 必须在表达式乘除链的顶层（头部不含顶层加减）——湿土排水复用式
    ``(A)/10^6*100+(B)/10^6*100`` 这类逐项拼接不命中；``s`` 为正整数，
    尾部为空（数量 1 不参与缩放）或 ``*`` 开头的系数串。
    """
    depth = 0
    best: tuple[int, int] | None = None
    for index, character in enumerate(expr):
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif depth == 0 and expr.startswith("/10^", index):
            end = index + 4
            while end < len(expr) and expr[end].isdigit():
                end += 1
            best = (index, end)
    if best is None:
        return None
    start, end = best
    exponent = int(expr[start + 4 : end])
    if exponent <= 0:
        return None
    rest = expr[end:]
    if rest and not rest.startswith("*"):
        return None
    head = expr[:start]
    if not head or _top_operator(head, _ADDITIVE):
        return None
    return head, exponent, rest


def _next_subtotal_symbol(symbols: dict[str, str], index: int) -> str:
    """分项符号 S1、S2…：跳过中间量已占用的号（S 与基础断面面积的 S 错开）。"""
    candidate = f"S{index}"
    while candidate in symbols.values():
        index += 1
        candidate = f"S{index}"
    return candidate


def _compact_terms(
    terms: list["Term"],
) -> tuple[str, list[CompactTerm], list[ExpressionDefinition]]:
    """把一条工程量的各分项压缩成主算式、分项式和中间量定义。

    多分项且每项都带同一换算尾 ``(面积式)/10^s*数量`` 时进入合并形态：
    分项即断面面积（符号 S1、S2…，值为面积式的求值 mm²），主算式为
    ``(S1+S2-…)/10^s*数量``；否则维持 V 形态（分项 = 带换算尾的完整项）。
    """
    tails = [_split_volume_tail(term.expr) for term in terms]
    factored = (
        len(terms) > 1
        and all(item is not None for item in tails)
        and len({(item[1], item[2]) for item in tails}) == 1
    )
    parsed: list[ast.AST] = []
    notes: list[str] = []
    tags: list[NamedValue] = []
    if factored:
        parsed = [_parse_expression(item[0]) for item in tails]
        if any(node is None for node in parsed):
            factored = False  # 面积式解析失败：退回完整式形态
    if not factored:
        for term in terms:
            node = _parse_expression(term.raw_expr or term.expr)
            if node is None:
                return "", [], []
            parsed.append(node)
    for term in terms:
        notes.append(term.note)
        tags.extend(term.tags)

    selected = _select_candidates(parsed, _collect_tag_keys(tags), notes)
    symbols = _assign_symbols(selected)

    compact_terms: list[CompactTerm] = []
    for index, (term, root) in enumerate(zip(terms, parsed), start=1):
        if factored:
            # 面积值必须在符号替换前求值：_ReplaceNodes 会原地改写 root 的子树
            area_value = _node_value(root)
        transformed = _ReplaceNodes(symbols).visit(root)
        expression = _excel_expression(_safe_simplify(transformed))
        if factored:
            # 合并形态：分项即断面面积（值为面积式的求值，mm²）
            symbol = _next_subtotal_symbol(symbols, index)
            value = area_value
        else:
            symbol = f"V{index}"
            value = term.value
        compact_terms.append(
            CompactTerm(
                symbol=symbol,
                note=term.note,
                expression=expression,
                value=value if value is not None else term.value,
                geometry=term.geometry,
            )
        )

    definitions: list[ExpressionDefinition] = []
    # 深层定义先输出，父级定义可以引用已定义的子式（排序只为阅读，不参与计算）。
    for candidate in sorted(selected, key=lambda item: item.depth, reverse=True):
        value = _node_value(candidate.node)  # 必须在替换子式前求值
        transformed = _ReplaceNodes(symbols, stop=candidate.key).visit(
            copy.deepcopy(candidate.node)
        )
        expression = _format_definition(_excel_expression(_safe_simplify(transformed)))
        definitions.append(
            ExpressionDefinition(
                symbol=symbols[candidate.key],
                label=candidate.label
                or (f"{candidate.source}中间量" if candidate.source else "中间量"),
                expression=expression,
                value=value if value is not None else 0.0,
                source=candidate.source or "本步原始参数",
            )
        )

    if len(compact_terms) > 1:
        parts: list[str] = []
        for index, (term, compact) in enumerate(zip(terms, compact_terms)):
            # 正负号取原始项的带符号数值：合并形态下 compact.value 是正的面积，
            # 扣减项的 - 号只能来自 term.value
            sign = "-" if term.value < 0 else ("+" if index else "")
            parts.append(sign + compact.symbol)
            definitions.append(
                ExpressionDefinition(
                    symbol=compact.symbol,
                    label=compact.note or f"分项 {index + 1}",
                    expression=compact.expression,
                    # 减项在定义表按绝对值展示，正负号由主算式里的 +/− 表达；
                    # 否则会出现“0.3 = -0.3”这种自相矛盾的行。合并形态的分项
                    # 值本就是面积式的求值（正数），直接沿用。
                    value=abs(term.value) if not factored else compact.value,
                    source=compact.note or "分项计算",
                    kind="subtotal",
                )
            )
        main = "".join(parts)
        if factored:
            _, exponent, rest = tails[0]
            main = f"({main})/10^{exponent}{rest}"
    else:
        main = compact_terms[0].expression if compact_terms else "0"

    definitions = _order_definitions(definitions)
    definitions = _prune_definitions(main, definitions)
    return main, compact_terms, definitions


_TOKEN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def _order_definitions(
    definitions: list[ExpressionDefinition],
) -> list[ExpressionDefinition]:
    """按依赖顺序排列定义：被引用的中间量排在引用它的定义之前。"""
    remaining = list(definitions)
    symbols = {item.symbol for item in remaining}
    emitted: set[str] = set()
    ordered: list[ExpressionDefinition] = []
    while remaining:
        for item in remaining:
            dependencies = set(_TOKEN.findall(item.expression)) & symbols
            if dependencies <= emitted:
                ordered.append(item)
                emitted.add(item.symbol)
                remaining.remove(item)
                break
        else:  # 理论上不会成环（语法树自下而上），兜底原序输出
            ordered.extend(remaining)
            break
    return ordered


def _prune_definitions(
    main: str, definitions: list[ExpressionDefinition]
) -> list[ExpressionDefinition]:
    """只保留主算式或其它定义真正引用到的中间量（避免出现一堆没用上的 B4）。"""
    by_symbol = {item.symbol: item for item in definitions}
    used = set(_TOKEN.findall(main)) & by_symbol.keys()
    changed = True
    while changed:
        changed = False
        for symbol in list(used):
            definition = by_symbol.get(symbol)
            if definition is None:
                continue
            for token in set(_TOKEN.findall(definition.expression)) & by_symbol.keys():
                if token not in used:
                    used.add(token)
                    changed = True
    return [item for item in definitions if item.symbol in used]


@dataclass
class Term:
    """工程量的一个代入项：expr 为未带正负号的算式，value 为带符号数值，note 为该项说明。

    ``expr`` 已按记法指数带换算尾（mm 记法的项为 ``(mm 式)/10^s`` 形态），
    求值 = 该项数值。``raw_expr`` 与 ``expr`` 同值（历史字段，保留供展示层
    与旧数据兼容）。

    ``geometry`` 是该项对应的梯形断面范围
    ``(h0, h1, l0, r0, l1, r1)``（单位 m）：深度自槽底向上（h0 深h1 浅），
    l/r 为区间底/顶的左右缘 x（相对本体中心，左负右正）。只有几何分项
    （挖方 / 回填梯形）记录，公式 / 系数类项为 None；供详情弹窗把分项行
    高亮到断面图上，不参与任何计算。
    """

    expr: str
    value: float
    note: str = ""
    tags: tuple[NamedValue, ...] = ()
    raw_expr: str = ""
    geometry: tuple[float, float, float, float, float, float] | None = None


@dataclass
class Quantity:
    """一个工程量条目：定额键 + 数值 + 数值代入算式 + 中间步骤。

    中间步骤由项（:class:`Term`）本身派生，见 :meth:`steps`：说明挂在项上，
    不单独存一份标签列表，因此“每步算式拼起来”与 :attr:`expression` 必然一致。
    展示层另有 :meth:`presentation`：把长算式拆成“主算式 + 中间量定义”，
    但 :attr:`expression` 始终保留完整数值算式，供复制 Excel 和逐项复核。
    """

    key: str
    value: float = 0.0
    terms: list[Term] = field(default_factory=list)
    _presentation_cache: ExpressionPresentation | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def steps(self) -> list[tuple[str, str]]:
        """中间步骤：``[(说明, 带符号的该项算式)]``，按相加顺序排列（可能为空）。

        ``"".join(算式 for _说明, 算式 in steps())`` 恒等于 :attr:`expression`
        ——两者出自同一份项列表，展示层不再拼字符串。
        """
        steps: list[tuple[str, str]] = []
        for index, term in enumerate(self.terms):
            expr = term.expr
            negative = term.value < 0
            if negative and needs_parens(expr):
                expr = f"({expr})"
            if index == 0:
                text = f"-{expr}" if negative else expr
            else:
                text = f"-{expr}" if negative else f"+{expr}"
            steps.append((term.note, prettify(text)))
        return steps

    @property
    def expression(self) -> str:
        """整条算式：各代入项按符号连接（与 :meth:`steps` 同源）。"""
        parts = [text for _note, text in self.steps()]
        return "".join(parts) if parts else "0"

    def presentation(self) -> ExpressionPresentation:
        """展示结构：主算式 + 中间量定义 + 分项式；失败时退回完整算式。"""
        if self._presentation_cache is not None:
            return self._presentation_cache
        main = ""
        compact_terms: list[CompactTerm] = []
        definitions: list[ExpressionDefinition] = []
        if self.terms:
            main, compact_terms, definitions = _compact_terms(self.terms)
        if not main:
            main = self.expression
        formula = f"V={main}"
        self._presentation_cache = ExpressionPresentation(
            formula=formula,
            main=main,
            definitions=tuple(definitions),
            terms=tuple(compact_terms),
            full=self.expression,
        )
        return self._presentation_cache

    @property
    def display_expression(self) -> str:
        """主算式（会触发展示层解析，供导出/接口等确实需要时使用）。"""
        return self.presentation().main

    @property
    def expression_outline(self) -> str:
        """表格首屏用的轻量摘要：**不解析表达式**，双击时再生成完整说明。

        单分项且式不长时直接显示原式；多分项不加“X 个分项”前缀，按各项说明
        与正负号直接连接——正项用 +、扣除项用 -（如“垫层-基础占位”），
        让用户一眼知道这条量由哪些部分组成，同时避免每次刷新表格都解析所有算式。
        """
        if not self.terms:
            return "0"
        if len(self.terms) == 1:
            text = self.terms[0].expr
            if len(text) <= 100:
                return text
            return f"{self.terms[0].note or '本项'}（双击查看计算过程）"
        notes: list[str] = []
        seen: set[tuple[bool, str]] = set()
        for term in self.terms:
            note = term.note
            if not note:
                continue
            negative = term.value < 0
            # 同名说明同符号只列一次（合槽/多构件合并时同一项会重复出现）
            if (negative, note) in seen:
                continue
            seen.add((negative, note))
            if not notes and not negative:
                notes.append(note)
            else:
                notes.append(f"{'-' if negative else '+'}{note}")
        if notes:
            return "".join(notes)
        return f"{len(self.terms)} 个分项（双击查看计算过程）"

    def compact_steps(self) -> list[tuple[str, str]]:
        """展示用分项步骤：``[(说明, “V1=主式”)]``；单分项直接给主式。"""
        view = self.presentation()
        if len(view.terms) <= 1:
            return [(view.terms[0].note if view.terms else "", view.main)]
        return [
            (term.note, f"{term.symbol}={term.expression}") for term in view.terms
        ]

    def add_term(
        self,
        value: float,
        expr: "str | Dim | None" = None,
        note: str = "",
        tags: Iterable[NamedValue] = (),
        geometry: tuple[float, float, float, float, float, float] | None = None,
    ) -> None:
        """累加一个代入项；``expr`` 传 :class:`Dim` 时按其记法指数追加 ``/10^s`` 换算尾。

        mm 记法（s=3）的每延米面积 / 体积式存成 ``(mm 式)/10^6``（体积）或
        ``/10^3``（面积），求值即该项数值（m 制）；m / 无量纲记法（s=0：用户
        公式、管材含量、井点数）原样存入。算式只存“数值代入”部分，正负号由
        value 决定，避免出现双重负号。``geometry`` 记录该项的梯形断面范围
        （详情弹窗高亮用，见 :class:`Term`）。
        """
        self.value += value
        if value != 0:
            if expr is None:
                text, space = fmt(value), 0
            elif isinstance(expr, Dim):
                text, space = expr.e, expr.s
            else:
                text, space = expr, 0
            text = (text or "0").lstrip("-") or "0"
            if space:
                text = f"{wrap(text)}/10^{space}"
            self.terms.append(
                Term(
                    expr=text,
                    value=value,
                    note=note,
                    tags=tuple(tags),
                    raw_expr=text,
                    geometry=geometry,
                )
            )
            self._presentation_cache = None


class QDict:
    """工程量字典（对应旧版 Dictionary<string, mcQ>），带算式记录。"""

    def __init__(self) -> None:
        self._items: dict[str, Quantity] = {}

    # ---------------------------------------------------------------- 容器
    def keys(self) -> list[str]:
        return list(self._items)

    def get(self, key: str) -> Quantity | None:
        return self._items.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def items(self) -> list[Quantity]:
        return list(self._items.values())

    def values(self) -> list[float]:
        return [item.value for item in self._items.values()]

    # ---------------------------------------------------------------- 累加
    def add(
        self,
        key: str,
        value: float,
        expr: "str | Dim | None" = None,
        note: str = "",
        tags: Iterable[NamedValue] = (),
        geometry: tuple[float, float, float, float, float, float] | None = None,
    ) -> Quantity:
        """累加一项：``note`` 是该步的说明，挂在项上随 :meth:`Quantity.steps` 一起展示。

        ``expr`` 可传算式原文（m / 无量纲记法，如用户公式结果）或 :class:`Dim`
        （几何量：mm 记法随 Dim.s 记录，自动追加 ``/10^s`` 换算尾）。
        ``geometry`` 记录该项的梯形断面范围（详情弹窗高亮用）。
        数值为 0 的项不进算式，其说明也一并丢弃（步骤列表与算式严格一一对应）。
        ``tags`` 只供展示层识别“槽底宽 / 计算深度”等中间量。
        """
        quantity = self._items.get(key)
        if quantity is None:
            quantity = Quantity(key=key)
            self._items[key] = quantity
        quantity.add_term(value, expr, note, tags, geometry)
        return quantity

    def discard(self, key: str) -> None:
        """移除一个条目（挖方合并用）。"""
        self._items.pop(key, None)

    def extend(self, other: "QDict") -> None:
        """合并另一本字典（旧版 PlusDic_StrmcQ）：项连同说明一起拷贝。"""
        for quantity in other.items():
            target = self.add(quantity.key, 0.0)
            for term in quantity.terms:
                target.add_term(
                    term.value, term.expr, term.note, term.tags, term.geometry
                )
                target.terms[-1].raw_expr = term.raw_expr or term.expr

    def scale(self, coefficient: float, expr: str | None = None) -> None:
        """整体乘系数（旧版 MultDic_StrmcQ）；系数进算式，``expr`` 为系数的算式原文。

        算式变成 ``项*系数``：项只在顶层是加减时才括（乘除左结合，``a/b*c`` ≡
        ``(a/b)*c``）；系数原文同埋深一样按优先级写进算式——``50*2`` 写成
        ``*50*2``（与埋深 ``2*3`` 进算式的写法一致），只有 ``*(40-2)`` 这类
        顶层加减才补括号。除数位置由 :meth:`Dim.__truediv__` 单独保证。
        """
        if coefficient == 1.0:
            return
        suffix = f"*{wrap(expr) if expr is not None else fmt(coefficient)}"
        for quantity in self._items.values():
            quantity.value *= coefficient
            for term in quantity.terms:
                term.value *= coefficient
                term.expr = f"{wrap(term.expr)}{suffix}"
                term.raw_expr = f"{wrap(term.raw_expr or term.expr)}{suffix}"
            quantity._presentation_cache = None

    # ---------------------------------------------------------------- 汇总
    def total(self) -> float:
        return sum(self._items.values())


#: 定额键的类别排序（旧版 mscGroove.order）
_CATEGORY_ORDER: dict[str, int] = {
    "开挖": 1,
    "换填": 10,
    "垫层": 20,
    "回填": 21,
    "围护": 30,
    "支撑": 31,
    "降水": 32,
    "包封": 39,
    "管道基础": 40,
    "管材": 41,
    "顶管": 42,
    "拖拉管": 43,
    "箱涵": 44,
    "管廊": 45,
}


def order_key(key: str) -> int:
    """定额键排序权重：按类别（旧版 mscGroove.OrderDQ），未知名排最后。"""
    category = key.split("|")[0] if key else ""
    return _CATEGORY_ORDER.get(category, 10000)


def sorted_items(source: QDict) -> list[Quantity]:
    return sorted(source.items(), key=lambda quantity: (order_key(quantity.key), quantity.key))
