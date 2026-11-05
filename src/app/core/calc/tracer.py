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
from dataclasses import dataclass, field, replace
from typing import Iterable

#: 输出算式里的函数名（Excel 写法，展示时统一转大写）
_EXCEL_FUNCTIONS = ("CEILING", "ROUNDUP", "ROUND", "SQRT", "ABS", "CEIL", "SIN", "COS", "ACOS")

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
class ParamRef:
    """固定符号（构件参数 / 图集参数 / 工作面宽度）的符号定义（只用于展示层）。

    ``symbol`` 是展示层用的符号（``t`` / ``a`` / ``C1`` / ``C2`` / ``D`` / ``Do`` /
    ``b1``），``expr`` 是它的数值代入式（查表值或用户录入原文），``value`` 是
    代入式的值。参数在算式里仍以原始数值参与计算；展示层把对应数值替换成符号，
    并在中间量定义表里补一行 ``symbol = expr``，见 :meth:`Dim.as_param`。

    ``basic`` 为 True 的符号（t/a/C1/C2/D/Do）统一放进计算表达式窗体的
    “基本参数”页；``b1``（工作面宽度）等按面积行归入各自的页。
    """

    symbol: str
    expr: str
    value: float
    label: str
    source: str = ""
    basic: bool = True
    #: 定义表里显示的代入式（默认同 ``expr``）；如 Do 显示成 ``D+t*2``
    display: str = ""


@dataclass(frozen=True)
class NamedValue:
    """算式片段与它的人类可读含义（只用于展示层，不参与求值）。

    ``expr`` 必须与 :class:`Dim` 当时的 ``e`` 完全一致；展示层按语法树比对，
    命中后把该片段提成中间量。数字本身仍由原始 ``e`` 提供，绝不用 ``value``
    反代回公式，因此不会把派生量预先算成一个数字。

    ``params`` 记录该片段里用到的构件参数符号（t/a/C1/C2）：由 :meth:`Dim.named`
    从 ``Dim.tags`` 汇总，供展示层在定义式里把参数值替换成符号。
    """

    expr: str
    label: str
    source: str = ""
    params: tuple[ParamRef, ...] = ()
    #: 参数符号标签（t/a/C1/C2）：只用于定义符号，不参与中间量提取
    param_tag: bool = False
    #: 语义角色（bottom_width / layer_width / layer_height / total_height）：
    #: 展示层据此分配 B、B1…、H、H1… 固定符号，而不是按候选顺序编号
    role: str = ""
    #: 角色序号（从下往上 1、2、3…）
    order: int = 0


def _merge_params(*groups: Iterable[ParamRef]) -> tuple[ParamRef, ...]:
    """合并参数符号定义（同一符号只保留第一次出现的定义）。"""
    merged: list[ParamRef] = []
    seen: set[str] = set()
    for group in groups:
        for ref in group:
            if not ref.symbol or ref.symbol in seen:
                continue
            seen.add(ref.symbol)
            merged.append(ref)
    return tuple(merged)


def _merge_tags(*groups: Iterable[NamedValue]) -> tuple[NamedValue, ...]:
    """合并算式来源标记（同一段算式 + 同一含义只保留一条，参数定义取并集）。"""
    merged: dict[tuple[str, str], NamedValue] = {}
    order: list[tuple[str, str]] = []
    for group in groups:
        for tag in group:
            if not tag.expr or not tag.label:
                continue
            key = (tag.expr, tag.label)
            existing = merged.get(key)
            if existing is None:
                merged[key] = tag
                order.append(key)
            else:
                merged[key] = NamedValue(
                    existing.expr,
                    existing.label,
                    existing.source,
                    _merge_params(existing.params, tag.params),
                    existing.param_tag or tag.param_tag,
                    tag.role or existing.role,
                    tag.order or existing.order,
                )
    return tuple(merged[key] for key in order)


def pair(other: "Dim | float") -> tuple[float, str, tuple[NamedValue, ...]]:
    """Dim 与普通数字统一成 (数值, 算式, 来源标记) 三件套。"""
    if isinstance(other, Dim):
        return other.v, other.e, other.tags
    value = float(other)
    return value, fmt(value), ()


@dataclass(frozen=True)
class AreaParts:
    """面积行的几何分解（只用于展示层）。

    梯形面积统一显示成 ``(u+v)*h/2``，三角形显示成 ``v*h/2``，矩形显示成
    ``u*h``：``u`` 为下底宽 / 矩形宽、``v`` 为上底宽、``h`` 为高。``v`` 为
    None 表示矩形 / 三角形没有上底（三角形用 ``v`` 作底宽，``u`` 为 None）。
    """

    kind: str  # "trapezoid" | "triangle" | "rectangle"
    u: "Dim | None"
    v: "Dim | None"
    h: "Dim"


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
    #: 面积行的几何分解（梯形 / 三角形）：只有面积 Dim 才有，供展示层
    #: 统一成 ``(u+v)*h/2`` / ``v*h/2``
    area: AreaParts | None = None

    def named(
        self, label: str, source: str = "", role: str = "", order: int = 0
    ) -> "Dim":
        """给当前量补一个展示名称（返回新 Dim，不改原对象）。

        同时把已有 tags 里的参数符号（t/a/C1/C2）汇总到新标签上，展示层据此
        知道这个片段内部用到了哪些构件参数。``role`` / ``order`` 用于固定符号
        （B、B1…、H、H1…）：见 :func:`_assign_symbols`。
        """
        params = _merge_params(*(tag.params for tag in self.tags))
        return Dim(
            self.v,
            self.e,
            _merge_tags(
                self.tags,
                (NamedValue(self.e, label, source, params, False, role, order),),
            ),
            self.s,
            self.area,
        )

    def as_param(
        self,
        symbol: str,
        label: str,
        source: str = "",
        basic: bool = True,
        display: str = "",
    ) -> "Dim":
        """把图集 / 构件参数挂上展示符号（t / a / C1 / C2 / D / Do / b1）。

        返回新 Dim，算式与数值不变；只是多一条带 :class:`ParamRef` 的标签，
        展示层据此在中间量定义表里补 ``symbol = expr``，并把算式里的数值替换
        成符号。``value`` 按算式记法换算（``v × 10^s``），与 ``expr`` 求值一致。
        ``basic=True`` 的符号进“基本参数”页，其余按面积行分页；``display``
        用于定义表的代入式（如 Do 显示成 ``D+t*2``），``expr`` 仍是数值式。
        """
        ref = ParamRef(
            symbol, self.e, self.v * (10 ** self.s), label, source, basic, display
        )
        return Dim(
            self.v,
            self.e,
            _merge_tags(
                self.tags,
                (NamedValue(self.e, label, source, (ref,), param_tag=True),),
            ),
            self.s,
            self.area,
        )

    def is_param(self) -> bool:
        """本量是否就是构件参数本身（参数标签的算式与当前算式一致）。"""
        return any(tag.param_tag and tag.expr == self.e for tag in self.tags)

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
        # 加法左结合：普通算式右操作数无论顶层是不是加减都不需要括号
        # （A+(B-C) ≡ A+B-C），扁平连接式更短。构件参数的录入算式例外：
        # C2 写成 "180+2" 时保留成独立语法树节点，展示层才能整段替换成 C2。
        self._assert_same_space(other, expr)
        if isinstance(other, Dim) and other.is_param() and needs_parens(expr):
            expr = f"({expr})"
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


def dim_min(*parts: Dim) -> Dim:
    """取较小者（算式取被选中那一项：min 的结果就是它）。"""
    result = parts[0]
    for part in parts[1:]:
        result = result if result.v <= part.v else part
    return result


def dim_max(*parts: Dim) -> Dim:
    """取较大者（算式取被选中那一项：max 的结果就是它）。"""
    result = parts[0]
    for part in parts[1:]:
        result = result if result.v >= part.v else part
    return result


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

    ``basic`` 为 True 的定义（t/a/C1/C2/D/Do）统一放进计算表达式窗体的
    “基本参数”页；``kind="area_part"`` 是面积行的 u/v/h 分解。
    """

    symbol: str
    label: str
    expression: str
    value: float
    source: str = ""
    kind: str = "intermediate"  # intermediate | subtotal | parameter | area_part
    basic: bool = False
    #: 层底宽 / 分层高角色（Bx / Hx）：始终保留，跨 tab 统一
    role: str = ""
    #: 悬停该行时在断面图上描出的线（场景坐标，m）：横线 / 竖线
    geometry: tuple[tuple[float, float], ...] | None = None


@dataclass(frozen=True)
class CompactTerm:
    """展示层的一个工程量分项（对应原来的一个带符号 Term）。

    ``value`` 的量纲随形态：合并形态（主算式 ``(S1+S2-…)/10^s*数量``）下
    各分项为断面面积（mm²，即面积式的求值），否则为该项自身的数值。
    ``geometry`` 透传自 :class:`Term`（详情弹窗把分项行高亮到断面图上）。
    ``parts`` 是面积行的 u/v/h 分解（梯形 / 三角形），归入该分项自己的
    中间符号页。
    """

    symbol: str
    note: str
    expression: str
    value: float
    geometry: tuple[float, ...] | tuple[tuple[float, float], ...] | None = None
    parts: tuple[ExpressionDefinition, ...] = ()


@dataclass(frozen=True)
class ExpressionGroup:
    """计算表达式窗体的一页：一个面积行（S1 / S2…）及其用到的中间符号。

    ``definitions`` 不含基本参数（t/a/C1/C2/D/Do，统一在“基本参数”页）。
    """

    symbol: str
    note: str
    expression: str
    value: float
    definitions: tuple[ExpressionDefinition, ...] = ()


@dataclass(frozen=True)
class ExpressionPresentation:
    """一条工程量的展示结构：主算式、定义表、分项式与完整算式。"""

    formula: str
    main: str
    definitions: tuple[ExpressionDefinition, ...]
    terms: tuple[CompactTerm, ...]
    full: str
    #: 基本参数页（t/a/C1/C2/D/Do）
    basic_definitions: tuple[ExpressionDefinition, ...] = ()
    #: 每个面积行一页的中间符号
    groups: tuple[ExpressionGroup, ...] = ()


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
    role: str = ""
    order: int = 0


_PREFERRED_SYMBOLS = {
    "槽底宽": "B",
    "层底宽": "B",
    "计算深度": "H",
    "基础宽度": "b",
    "基础厚度": "h",
    "基础断面面积": "S",
    "弓形占位面积": "A",
    "放坡系数": "m",
    "数量": "L",
    "长度": "L",
    "埋深": "h0",
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
    """把来源标记的算式转成语法树 canonical key。

    同一个节点既有参数标签又有语义标签时优先语义标签（参数标签只用于符号定义）。
    """
    result: dict[str, NamedValue] = {}
    for tag in tags:
        node = _parse_expression(tag.expr)
        if node is not None:
            key = _node_key(node)
            existing = result.get(key)
            if existing is None or (existing.param_tag and not tag.param_tag):
                result[key] = tag
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


def _role_symbol(role: str, order: int) -> str:
    """语义角色 → 固定符号：整个槽底宽 B、层底宽 B1/B2…、总高 H、分层高 H1/H2…。"""
    if role == "bottom_width":
        return "B"
    if role == "layer_width":
        return f"B{order}"
    if role == "layer_height":
        return f"H{order}"
    if role == "total_height":
        return "H"
    return ""


def _assign_symbols(candidates: list[_Candidate]) -> dict[str, str]:
    """给候选片段分配短符号：语义量优先用 B/H/D 等，其余用 X1、X2…。

    带 ``role`` 的候选按固定规则编号：整个槽底宽 B、层底宽 B1/B2…（按加宽
    顺序）、总高 H、分层高 H1/H2…（按从下往上的层号）。
    """
    used: set[str] = set()
    symbols: dict[str, str] = {}
    for candidate in candidates:
        base = _role_symbol(candidate.role, candidate.order) or _PREFERRED_SYMBOLS.get(
            candidate.label, "X"
        )
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


class _ReplaceParams(ast.NodeTransformer):
    """把构件参数（t/a/C1/C2）的数值节点替换成对应符号。

    ``keys`` 的值可以是符号，也可以是“同一数值对应的多个参数符号”列表：语法树
    分不清两个 100 哪个是 a、哪个是 C1 时，按出现顺序依次对应（表达式拼接与
    标签合并都按左→右进行，顺序一致）。
    """

    def __init__(self, keys: dict[str, str | list[str]]) -> None:
        self.keys = keys

    def visit(self, node: ast.AST) -> ast.AST:
        symbol = self.keys.get(_node_key(node))
        if isinstance(symbol, list):
            if not symbol:  # 出现次数比参数多：多出来的保留数字
                return super().visit(node)
            symbol = symbol.pop(0)
        if symbol is not None:
            return ast.Name(id=symbol, ctx=ast.Load())
        return super().visit(node)


#: 参数符号的展示顺序（与构件参数行一致：壁厚 / 工作面加宽 / 垫层厚 / 基础厚）
_PARAM_ORDER = {"t": 0, "a": 1, "C1": 2, "C2": 3}


def _collect_param_refs(tags: Iterable[NamedValue]) -> list[ParamRef]:
    """从来源标记里汇总构件参数符号定义（保持标签出现顺序，同一符号取第一次）。"""
    refs: dict[str, ParamRef] = {}
    for tag in tags:
        for ref in tag.params:
            refs.setdefault(ref.symbol, ref)
    return list(refs.values())


def _node_keys_within(node: ast.AST, skip_keys: set[str]) -> set[str]:
    """节点内出现过的 canonical key；``skip_keys`` 的子树（已提成符号）不进入。"""
    keys: set[str] = set()

    def walk(current: ast.AST) -> None:
        key = _node_key(current)
        if key in skip_keys:
            return
        keys.add(key)
        for child in ast.iter_child_nodes(current):
            walk(child)

    walk(node)
    return keys


def _candidate_params(tag_map: dict[str, NamedValue], keys: Iterable[str]) -> set[str]:
    """这些候选片段内部用到的固定符号（已随片段提成符号，不在本式里展开）。"""
    params: set[str] = set()
    for key in keys:
        tag = tag_map.get(key)
        if tag is not None:
            params.update(ref.symbol for ref in tag.params)
    return params


def _param_key_map(
    refs: Iterable[ParamRef],
    node: ast.AST,
    skip_keys: set[str],
    nested_params: set[str] | frozenset[str] = frozenset(),
) -> dict[str, str | list[str]]:
    """当前算式里“参数数值节点 → 符号”的映射。

    只保留确实出现在节点里的参数。两个参数数值相同（如 a 与 C1 都是 130）时
    同一个语法树节点对应多个符号，交给 :class:`_ReplaceParams` 按出现顺序分配。

    ``nested_params`` 是已提成符号的子片段里的参数：若同一数值既有“候选片段
    内”的参数、又有候选外的参数（如槽底宽里的 a 与垫层厚里的 C1 同为 100），
    候选外的才是当前算式里剩下的那个，候选内的不参与本式替换。
    """
    present = _node_keys_within(node, skip_keys)
    refs = list(refs)
    # 按数值分组；同值里只要有候选外的参数，就只保留候选外的那几路
    by_value: dict[float, list[ParamRef]] = {}
    for ref in refs:
        by_value.setdefault(round(ref.value, 9), []).append(ref)
    keep: set[str] = set()
    for group in by_value.values():
        outside = [ref for ref in group if ref.symbol not in nested_params]
        chosen = outside if len(group) > 1 and outside else group
        keep.update(ref.symbol for ref in chosen)

    mapping: dict[str, str | list[str]] = {}
    for ref in refs:
        if ref.symbol not in keep:
            continue
        parsed = _parse_expression(ref.expr)
        if parsed is None:
            continue
        key = _node_key(parsed)
        if key not in present:
            continue
        existing = mapping.get(key)
        if existing is None:
            mapping[key] = ref.symbol
        elif isinstance(existing, str):
            if existing != ref.symbol:
                mapping[key] = [existing, ref.symbol]
        elif ref.symbol not in existing:
            existing.append(ref.symbol)
    return mapping


def _render_dim_expression(
    dim: Dim,
    symbols: dict[str, str],
    selected_keys: set[str],
    tag_map: dict[str, NamedValue],
) -> tuple[str, float]:
    """把 Dim 的算式按当前符号 / 固定符号替换后输出（展示用），并返回原式值。"""
    node = _parse_expression(dim.e)
    if node is None:
        return dim.e, dim.v * (10 ** dim.s)
    value = _node_value(node)
    refs = _collect_param_refs(dim.tags)
    candidates = selected_keys & _node_keys_within(node, set())
    param_keys = _param_key_map(
        refs, node, selected_keys, _candidate_params(tag_map, candidates)
    )
    transformed = _ReplaceNodes(symbols).visit(copy.deepcopy(node))
    transformed = _ReplaceParams(param_keys).visit(transformed)
    text = _format_definition(_excel_expression(_safe_simplify(transformed)))
    return text, value if value is not None else dim.v * (10 ** dim.s)


def _select_candidates(
    roots: list[ast.AST],
    tag_map: dict[str, NamedValue],
    notes: list[str],
    exclude_keys: set[str] | frozenset[str] = frozenset(),
) -> list[_Candidate]:
    """从所有分项语法树中选可提取片段（语义量 → 确有重复的片段）。

    ``exclude_keys`` 是构件参数自身的数值节点：参数走符号定义，不再提成 X1。
    """
    root_keys = {_node_key(root) for root in roots}
    aggregated: dict[str, _Candidate] = {}
    for root, note in zip(roots, notes):
        for node, depth in _walk_nodes(root):
            key = _node_key(node)
            if key in exclude_keys or not _candidate_key(node, root_keys):
                continue
            tag = tag_map.get(key)
            if tag is not None and tag.param_tag:
                continue
            text = _excel_expression(node)
            existing = aggregated.get(key)
            if existing is None:
                aggregated[key] = _Candidate(
                    key=key,
                    text=text,
                    node=node,
                    length=len(text),
                    count=1,
                    depth=depth,
                    label=tag.label if tag else "",
                    source=(tag.source if tag and tag.source else note),
                    role=tag.role if tag else "",
                    order=tag.order if tag else 0,
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

    tag_map = _collect_tag_keys(tags)
    param_refs = _collect_param_refs(tags)
    # 固定符号（t/a/C1/C2/D/Do/b1）自身的数值节点不提成 X1
    param_expr_keys: set[str] = set()
    for ref in param_refs:
        parsed_ref = _parse_expression(ref.expr)
        if parsed_ref is not None:
            param_expr_keys.add(_node_key(parsed_ref))
    selected = _select_candidates(parsed, tag_map, notes, param_expr_keys)
    symbols = _assign_symbols(selected)
    selected_keys = set(symbols)

    # 面积行的“顶宽”不一定作为独立子式出现在面积式里（(2B+2Hs)*H/2），
    # 但它带着 B1/B2… 角色：补一条定义，展示层才能在 u/v/h 里引用它。
    extra_definitions: list[ExpressionDefinition] = []
    part_symbols: dict[int, str] = {}
    part_values: dict[int, float] = {}
    used_symbols = set(symbols.values())
    for term in terms:
        area = term.area
        if area is None:
            continue
        for part in (area.u, area.v, area.h):
            if part is None:
                continue
            role_tag = next(
                (tag for tag in part.tags if tag.role and tag.expr == part.e), None
            )
            if role_tag is None:
                continue
            parsed_part = _parse_expression(part.e)
            if parsed_part is None:
                continue
            key = _node_key(parsed_part)
            if key in symbols:
                continue
            base = _role_symbol(role_tag.role, role_tag.order)
            if not base:
                continue
            symbol = base
            suffix = 2
            while symbol in used_symbols:
                symbol = f"{base}{suffix}"
                suffix += 1
            text, value = _render_dim_expression(part, symbols, selected_keys, tag_map)
            extra_definitions.append(
                ExpressionDefinition(
                    symbol=symbol,
                    label=role_tag.label,
                    expression=text,
                    value=value,
                    source=role_tag.source or "分层",
                    kind="intermediate",
                    role=role_tag.role,
                )
            )
            part_symbols[id(part)] = symbol
            part_values[id(part)] = value
            # 纯数字（如管顶 50cm 的 500）不进全局符号表，避免把同值的其它
            # 参数（工作面宽度 b1=500）也替换掉；面积行按对象身份直接引用。
            if not _NUMERIC.fullmatch(part.e.strip()):
                symbols[key] = symbol
            used_symbols.add(symbol)

    def _part_expression(part: Dim) -> tuple[str, float]:
        """面积分解量的展示式：角色符号优先，否则按当前符号表渲染。"""
        symbol = part_symbols.get(id(part))
        if symbol is not None:
            return symbol, part_values[id(part)]
        return _render_dim_expression(part, symbols, selected_keys, tag_map)

    symbol_geometry: dict[str, tuple[tuple[float, float], ...]] = {}

    def _part_symbol(part: Dim) -> str:
        """面积分解量对应的层底宽 / 层高符号（B、B1…、H1…）。"""
        node = _parse_expression(part.e)
        if node is None:
            return ""
        return symbols.get(_node_key(node)) or part_symbols.get(id(part), "")

    compact_terms: list[CompactTerm] = []
    area_definitions: list[ExpressionDefinition] = []
    for index, (term, root) in enumerate(zip(terms, parsed), start=1):
        if factored:
            # 面积值必须在符号替换前求值：_ReplaceNodes 会原地改写 root 的子树
            area_value = _node_value(root)
            symbol = _next_subtotal_symbol(symbols, index)
            value = area_value if area_value is not None else term.value
        else:
            symbol = f"V{index}"
            value = term.value
        # 参数替换映射也要在候选替换前算：候选子树里的参数已归到各自的定义里。
        # 用该分项自己的标签顺序，数值相同的参数才能按算式左→右的出现顺序对上。
        term_refs = _collect_param_refs(term.tags)
        # 本式里实际出现的候选片段（含嵌套的）才把参数算作“已提成符号”
        root_candidates = selected_keys & _node_keys_within(root, set())
        param_keys = _param_key_map(
            term_refs, root, selected_keys, _candidate_params(tag_map, root_candidates)
        )
        transformed = _ReplaceNodes(symbols).visit(root)
        transformed = _ReplaceParams(param_keys).visit(transformed)
        expression = _excel_expression(_safe_simplify(transformed))

        # 面积行统一显示：梯形 (u+v)*h/2、三角形 v*h/2、矩形 u*h
        parts: list[ExpressionDefinition] = []
        area = term.area
        if area is not None and area.kind in ("trapezoid", "triangle", "rectangle"):
            source = f"{symbol}·{term.note or '面积行'}"
            area_geometry = term.geometry
            bottom_line = top_line = height_line = None
            if (
                area_geometry
                and len(area_geometry) == 6
                and isinstance(area_geometry[0], (int, float))
            ):
                h0, h1, l0, r0, l1, r1 = area_geometry
                bottom_line = ((l0, h0), (r0, h0))
                top_line = ((l1, h1), (r1, h1))
                # 高度 / 厚度：层底右端点向上到层顶
                height_line = ((r0, h0), (r0, h1))

            def _remember(part: Dim, geometry) -> None:
                """把该分解量对应的层底宽 / 层高符号与边线关联。"""
                sym = _part_symbol(part)
                if sym and geometry is not None:
                    symbol_geometry.setdefault(sym, geometry)

            if area.kind == "rectangle" and area.u is not None:
                _remember(area.u, bottom_line)
                _remember(area.h, height_line)
                u_text, u_value = _part_expression(area.u)
                h_text, h_value = _part_expression(area.h)
                parts = [
                    ExpressionDefinition(
                        f"u{index}", "宽", u_text, u_value, source, "area_part",
                        geometry=bottom_line,
                    ),
                    ExpressionDefinition(
                        f"h{index}", "高", h_text, h_value, source, "area_part",
                        geometry=height_line,
                    ),
                ]
                expression = f"u{index}*h{index}"
            elif area.kind == "trapezoid" and area.u is not None and area.v is not None:
                _remember(area.u, bottom_line)
                _remember(area.v, top_line)
                _remember(area.h, height_line)
                u_text, u_value = _part_expression(area.u)
                v_text, v_value = _part_expression(area.v)
                h_text, h_value = _part_expression(area.h)
                parts = [
                    ExpressionDefinition(
                        f"u{index}", "下底宽", u_text, u_value, source, "area_part",
                        geometry=bottom_line,
                    ),
                    ExpressionDefinition(
                        f"v{index}", "上底宽", v_text, v_value, source, "area_part",
                        geometry=top_line,
                    ),
                    ExpressionDefinition(
                        f"h{index}", "高", h_text, h_value, source, "area_part",
                        geometry=height_line,
                    ),
                ]
                expression = f"(u{index}+v{index})*h{index}/2"
            else:
                _remember(area.v, top_line)
                _remember(area.h, height_line)
                v_text, v_value = _part_expression(area.v)
                h_text, h_value = _part_expression(area.h)
                parts = [
                    ExpressionDefinition(
                        f"v{index}", "底宽", v_text, v_value, source, "area_part",
                        geometry=top_line,
                    ),
                    ExpressionDefinition(
                        f"h{index}", "高", h_text, h_value, source, "area_part",
                        geometry=height_line,
                    ),
                ]
                expression = f"v{index}*h{index}/2"
            # 单分项（V 形态）的换算尾 /10^s*数量 仍要保留；合并形态由主算式带尾
            if not factored:
                tail = _split_volume_tail(term.expr)
                if tail is not None:
                    _, exponent, rest = tail
                    expression = f"({expression})/10^{exponent}{rest}"
            area_definitions.extend(parts)

        compact_terms.append(
            CompactTerm(
                symbol=symbol,
                note=term.note,
                expression=expression,
                value=value,
                geometry=term.geometry,
                parts=tuple(parts),
            )
        )

    definitions: list[ExpressionDefinition] = []
    # 构件参数（t/a/C1/C2）先给定义：主算式 / 定义式里的数值被替换成符号，
    # 结果列只用于核对，不代回公式。
    for ref in sorted(param_refs, key=lambda item: _PARAM_ORDER.get(item.symbol, 99)):
        definitions.append(
            ExpressionDefinition(
                symbol=ref.symbol,
                label=ref.label,
                expression=_format_definition(ref.display or ref.expr),
                value=ref.value,
                source=ref.source or "构件参数",
                kind="parameter",
                basic=ref.basic,
            )
        )
    # 深层定义先输出，父级定义可以引用已定义的子式（排序只为阅读，不参与计算）。
    for candidate in sorted(selected, key=lambda item: item.depth, reverse=True):
        value = _node_value(candidate.node)  # 必须在替换子式前求值
        tag = tag_map.get(candidate.key)
        # 语义量标签带着“该片段用到哪些构件参数”；通用片段退回全部参数，
        # 由 _param_key_map 按实际出现的数值节点过滤。
        candidate_refs = tag.params if tag is not None and tag.params else param_refs
        # 只把确实嵌套在本定义式里的候选片段算作“已提成符号”（别的分项的
        # 候选片段不影响本式，否则同值参数会被误判成都在候选内）
        nested_keys = (
            selected_keys & _node_keys_within(candidate.node, set())
        ) - {candidate.key}
        param_keys = _param_key_map(
            candidate_refs,
            candidate.node,
            selected_keys - {candidate.key},
            _candidate_params(tag_map, nested_keys),
        )
        transformed = _ReplaceNodes(symbols, stop=candidate.key).visit(
            copy.deepcopy(candidate.node)
        )
        transformed = _ReplaceParams(param_keys).visit(transformed)
        expression = _format_definition(_excel_expression(_safe_simplify(transformed)))
        definitions.append(
            ExpressionDefinition(
                symbol=symbols[candidate.key],
                label=candidate.label
                or (f"{candidate.source}中间量" if candidate.source else "中间量"),
                expression=expression,
                value=value if value is not None else 0.0,
                source=candidate.source or "本步原始参数",
                role=candidate.role,
            )
        )

    # 面积行的 u/v/h 分解（梯形 / 三角形）也是中间符号
    definitions.extend(area_definitions)
    definitions.extend(extra_definitions)

    # 基础宽度 b / 工作面宽度 b1 / 槽底宽 B 归“基本参数”页
    definitions = [
        replace(item, basic=True)
        if item.label in ("基础宽度", "工作面宽度", "槽底宽")
        else item
        for item in definitions
    ]
    # u1/v1/h1 如果只代入一个符号，直接写该符号的计算式（不在这里再套一层符号）
    by_symbol = {item.symbol: item for item in definitions}
    definitions = [
        replace(
            item, expression=_expand_single_symbol(item.expression, by_symbol)
        )
        if item.kind == "area_part"
        else item
        for item in definitions
    ]

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

    # 层底宽 / 层高符号（B、B1…、H1…）挂上悬停描边线
    if symbol_geometry:
        definitions = [
            replace(
                item,
                geometry=symbol_geometry.get(item.symbol, item.geometry),
            )
            if item.symbol in symbol_geometry
            else item
            for item in definitions
        ]

    # 基本参数页里的宽度 / 厚度也给出对应边线：b、b1、a 为横线，C1、C2 为竖线
    basic_values = {
        item.symbol: item.value
        for item in definitions
        if item.symbol in ("B", "b", "b1", "a", "C1", "C2", "Do")
    }
    b_mm = basic_values.get("b")
    if not b_mm:
        b_mm = basic_values.get("B", 0.0) - 2 * basic_values.get("b1", 0.0)
    b_half = b_mm / 2000.0
    b1 = basic_values.get("b1", 0.0) / 1000.0
    c1 = basic_values.get("C1", 0.0) / 1000.0
    c2 = basic_values.get("C2", 0.0) / 1000.0
    do_mm = basic_values.get("Do") or (
        basic_values.get("D", 0.0) + 2 * basic_values.get("t", 0.0)
    )
    do_half = do_mm / 2000.0
    basic_geometry: dict[str, tuple[tuple[float, float], ...]] = {}
    if b_half > 0:
        basic_geometry["b"] = ((-b_half, 0.0), (b_half, 0.0))
        if b1 > 0:
            basic_geometry["B"] = (
                (-(b_half + b1), 0.0),
                (b_half + b1, 0.0),
            )
        if c1 > 0:
            basic_geometry["C1"] = ((b_half, 0.0), (b_half, c1))
        if c2 > 0:
            basic_geometry["C2"] = ((b_half, c1), (b_half, c1 + c2))
        if b1 > 0:
            basic_geometry["b1"] = ((b_half, 0.0), (b_half + b1, 0.0))
        if do_half > 0 and b_half > do_half:
            basic_geometry["a"] = ((do_half, 0.0), (b_half, 0.0))
    if basic_geometry:
        definitions = [
            replace(item, geometry=basic_geometry.get(item.symbol, item.geometry))
            if item.symbol in basic_geometry
            else item
            for item in definitions
        ]

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
    """只保留主算式或其它定义真正引用到的中间量（避免出现一堆没用上的 B4）。

    “基本参数”（t/a/C1/C2/D/Do/b/b1/B）始终保留：它们单独占一页，即使
    u/v/h 展开后不再直接引用也要能查到。
    """
    by_symbol = {item.symbol: item for item in definitions}
    used = set(_TOKEN.findall(main)) & by_symbol.keys()
    used |= {item.symbol for item in definitions if item.basic or item.role}
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


def _expand_single_symbol(
    expression: str,
    by_symbol: dict[str, ExpressionDefinition],
    seen: frozenset[str] = frozenset(),
) -> str:
    """u/v/h 的代入式只有一个符号时，展开成该符号的计算式（递归到多符号为止）。"""
    text = (expression or "").strip()
    if not _TOKEN.fullmatch(text) or text in seen:
        return text
    definition = by_symbol.get(text)
    if definition is None:
        return text
    return _expand_single_symbol(definition.expression, by_symbol, seen | {text})


def _group_definitions(
    compact_terms: list[CompactTerm],
    definitions: list[ExpressionDefinition],
) -> tuple[tuple[ExpressionDefinition, ...], tuple[ExpressionGroup, ...]]:
    """按面积行分组：基本参数一页，每个分项一页（不含基本参数）。

    每页包含该分项算式（含 u/v/h 分解）递归引用到的全部非基本符号；基本参数
    （t/a/C1/C2/D/Do）只出现在“基本参数”页，不在各面积页重复。
    """
    basic = tuple(item for item in definitions if item.basic)
    by_symbol = {item.symbol: item for item in definitions if not item.basic}
    groups: list[ExpressionGroup] = []
    for term in compact_terms:
        roots = set(_TOKEN.findall(term.expression))
        for part in term.parts:
            roots.update(_TOKEN.findall(part.expression))
        used: set[str] = set()
        frontier = list(roots)
        while frontier:
            symbol = frontier.pop()
            if symbol in used:
                continue
            item = by_symbol.get(symbol)
            if item is None:
                continue
            used.add(symbol)
            frontier.extend(_TOKEN.findall(item.expression))
        part_symbols = {part.symbol for part in term.parts}
        # u/v/h 用展开后的定义（单符号已换成计算式），其余依赖按全局定义顺序
        part_definitions = tuple(
            by_symbol.get(part.symbol, part) for part in term.parts
        )
        groups.append(
            ExpressionGroup(
                symbol=term.symbol,
                note=term.note,
                expression=term.expression,
                value=term.value,
                definitions=part_definitions
                + tuple(
                    item
                    for item in definitions
                    if item.symbol in used
                    and not item.basic
                    and item.symbol not in part_symbols
                ),
            )
        )
    return basic, tuple(groups)


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
    #: 断面范围：6 元组梯形 (h0, h1, l0, r0, l1, r1)，或点列多边形
    #: ((x, y), …)（弓形 / 半圆等弧边形状，弦线 + 采样弧线）
    geometry: tuple[float, ...] | tuple[tuple[float, float], ...] | None = None
    #: 面积行的几何分解（梯形 / 三角形 / 矩形）：供计算表达式窗体统一显示
    area: AreaParts | None = None


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
        basic_definitions: tuple[ExpressionDefinition, ...] = ()
        groups: tuple[ExpressionGroup, ...] = ()
        if compact_terms:
            basic_definitions, groups = _group_definitions(compact_terms, definitions)
        self._presentation_cache = ExpressionPresentation(
            formula=formula,
            main=main,
            definitions=tuple(definitions),
            terms=tuple(compact_terms),
            full=self.expression,
            basic_definitions=basic_definitions,
            groups=groups,
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
        geometry: tuple[float, ...] | tuple[tuple[float, float], ...] | None = None,
        area: AreaParts | None = None,
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
                    area=expr.area if isinstance(expr, Dim) else area,
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
        geometry: tuple[float, ...] | tuple[tuple[float, float], ...] | None = None,
        area: AreaParts | None = None,
    ) -> Quantity:
        """累加一项：``note`` 是该步的说明，挂在项上随 :meth:`Quantity.steps` 一起展示。

        ``expr`` 可传算式原文（m / 无量纲记法，如用户公式结果）或 :class:`Dim`
        （几何量：mm 记法随 Dim.s 记录，自动追加 ``/10^s`` 换算尾）。
        ``geometry`` 记录该项的梯形断面范围（详情弹窗高亮用）。
        数值为 0 的项不进算式，其说明也一并丢弃（步骤列表与算式严格一一对应）。
        ``tags`` 只供展示层识别“槽底宽 / 计算深度”等中间量；``area`` 在复用
        字符串算式（如湿土排水）时透传面积行的 u/v/h 分解。
        """
        quantity = self._items.get(key)
        if quantity is None:
            quantity = Quantity(key=key)
            self._items[key] = quantity
        quantity.add_term(value, expr, note, tags, geometry, area)
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
                target.terms[-1].area = term.area

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
