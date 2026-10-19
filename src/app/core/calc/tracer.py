"""表达式记录器。

每个工程量条目产出 ``{key, value, expression, terms}``：

* ``expression`` 是一条代入后的算式，如
  ``(2×(600/1000+(65×2+130×2+500×2)/1000)+2×2.995×1)×2.995/2``；
* **不预运算**：软件派生出来的数字（槽底宽由管径 + 图集参数 + 面宽原则推出、
  毫米→米的换算、换填总厚、弓形占位…）在算式里把计算过程写全，只有直接
  录入 / 查表的原始数据与软件常数才以单个数字出现，见 :class:`Dim`；
* 用户在埋深 / 数量 / 参数 / 含量列写的算式以原文（括号保护）出现在代入位置，
  见 :class:`Dim` 与 :func:`raw_dim`；
* 多来源的量（分层土方、多个构件公式）按项累加，算式用 +/− 连接各代入项；
* 中间步骤（:meth:`Quantity.steps`）＝逐项一行「说明 + 该步算式」（分层、扣减、
  公式类别等），由项本身派生，每步算式按顺序拼起来就是完整算式；
  供表格 tooltip / 详情弹窗查看，不进主算式。

算式求值与表达式拼接共用同一套数值：先拼出可求值的算式字符串，
再用 core.evaluator 对它求值得到结果，禁止两套算法各算各的。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

_SUPERSCRIPTS = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹"}

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

    顶层只有乘除的算式（``600/1000``、``65×2``）嵌进任何位置都不改变结合顺序
    （乘除同级、左结合：``a×b/c×d`` ≡ ``a×(b/c)×d``），纯数字与函数调用同理。
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

    默认（加 / 减 / 乘上下文）只对顶层加减（含正负号）加括号——``65×2`` 这类
    纯乘除嵌进任何位置都不会改变结合顺序；``tight=True`` 用于除数位置或变量
    代入（后面接什么运算符未知），顶层乘除也加括号。纯数字原样保留。
    """
    text = expression.strip()
    needed = needs_parens_tight(text) if tight else needs_parens(text)
    return f"({text})" if needed else text


def pair(other: "Dim | float") -> tuple[float, str]:
    """Dim 与普通数字统一成 (数值, 算式) 两件套（普通数字的算式就是它本身）。"""
    if isinstance(other, Dim):
        return other.v, other.e
    value = float(other)
    return value, fmt(value)


@dataclass
class Dim:
    """带算式的数值（埋深、层厚、宽度、图集参数、数量…）：``v`` 为数值，``e`` 为求值等价的算式。

    数值与算式同源：加减乘除都在 Dim 上进行，算式按运算逐级拼出来，
    **不做预运算**——派生量（槽底宽 = 管径/1000 + 图集与面宽参数、换填总厚、
    弓形占位…）在算式里保留全部来源，只有直接录入 / 查表的原始数据
    （管径、图集 t/a/C1/C2、面宽表值）和软件常数（0.5、π 系数）才是一个数字。
    ``e`` 是裸算式，嵌入模板前须经 :func:`wrap`。
    """

    v: float
    e: str

    def __add__(self, other: "Dim | float") -> "Dim":
        value, expr = pair(other)
        if value == 0:
            return self
        if self.v == 0:
            return Dim(value, expr)
        # 加法两侧都是同级运算，右操作数加括号只为可读；左操作数无须括号
        return Dim(self.v + value, f"{self.e}+{wrap(expr)}")

    __radd__ = __add__

    def __sub__(self, other: "Dim | float") -> "Dim":
        value, expr = pair(other)
        if value == 0:
            return self
        # 减法的右操作数是算式时必须括起来，否则 X-(A+B) 会变成 X-A+B
        return Dim(self.v - value, f"{self.e}-{wrap(expr)}")

    def __neg__(self) -> "Dim":
        return Dim(-self.v, f"-{wrap(self.e)}")

    def __mul__(self, other: "Dim | float") -> "Dim":
        value, expr = pair(other)
        return Dim(self.v * value, f"{wrap(self.e)}×{wrap(expr)}")

    __rmul__ = __mul__

    def __truediv__(self, other: "Dim | float") -> "Dim":
        value, expr = pair(other)
        if value == 1:
            return self  # ÷1 不写进算式（只可能是引擎生成的等分，用户写的算式保留原文）
        # 除数位置的算式要更严格：顶层乘除也得括起来，否则 _a/(b×c) 会变成 _a/b×c
        return Dim(self.v / value, f"{wrap(self.e)}/{wrap(expr, tight=True)}")


def dim(value: float, expr: str | None = None) -> Dim:
    """纯数值尺寸：算式就是数值本身。"""
    return Dim(float(value), expr if expr is not None else fmt(value))


def dim_sum(*parts: Dim) -> Dim:
    """逐项求和：跳过 0 项，每项保留自己的算式（``65+130``、``200+300``）。"""
    total = dim(0.0)
    for part in parts:
        total = total + part
    return total


def scale_sum(parts: Iterable[Dim], factor: float) -> Dim:
    """Σ(项 × 系数)：系数逐项写进算式并跳过 0 项，如 ``65×2+130×2+500×2``。"""
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


def prettify(expression: str) -> str:
    """把 Python 语法的算式转成可读写法：**n → 上标，* → ×。"""
    text = re.sub(r"\*\*(\d+)", lambda m: "".join(_SUPERSCRIPTS[ch] for ch in m.group(1)), expression)
    return text.replace("*", "×")


@dataclass
class Term:
    """工程量的一个代入项：expr 为未带正负号的算式，value 为带符号数值，note 为该项说明。"""

    expr: str
    value: float
    note: str = ""


@dataclass
class Quantity:
    """一个工程量条目：定额键 + 数值 + 数值代入算式 + 中间步骤。

    中间步骤由项（:class:`Term`）本身派生，见 :meth:`steps`：说明挂在项上，
    不单独存一份标签列表，因此“每步算式拼起来”与 :attr:`expression` 必然一致。
    """

    key: str
    value: float = 0.0
    terms: list[Term] = field(default_factory=list)

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

    def add_term(self, value: float, expr: str, note: str = "") -> None:
        self.value += value
        if value != 0:
            # 算式只存“数值代入”部分，正负号由 value 决定，避免出现双重负号
            self.terms.append(Term(expr=expr.lstrip("-") or "0", value=value, note=note))


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
    def add(self, key: str, value: float, expr: str = "", note: str = "") -> Quantity:
        """累加一项：``note`` 是该步的说明，挂在项上随 :meth:`Quantity.steps` 一起展示。

        数值为 0 的项不进算式，其说明也一并丢弃（步骤列表与算式严格一一对应）。
        """
        quantity = self._items.get(key)
        if quantity is None:
            quantity = Quantity(key=key)
            self._items[key] = quantity
        quantity.add_term(value, expr or fmt(value), note)
        return quantity

    def discard(self, key: str) -> None:
        """移除一个条目（挖方合并用）。"""
        self._items.pop(key, None)

    def extend(self, other: "QDict") -> None:
        """合并另一本字典（旧版 PlusDic_StrmcQ）：项连同说明一起拷贝。"""
        for quantity in other.items():
            target = self.add(quantity.key, 0.0)
            for term in quantity.terms:
                target.add_term(term.value, term.expr, term.note)

    def scale(self, coefficient: float, expr: str | None = None) -> None:
        """整体乘系数（旧版 MultDic_StrmcQ）；系数进算式，``expr`` 为系数的算式原文。

        算式变成 ``项×系数``：项只在顶层是加减时才括（乘除左结合，``a/b×c`` ≡
        ``(a/b)×c``）；系数原文同埋深一样按优先级写进算式——``50*2`` 写成
        ``×50×2``（与埋深 ``2*3`` 进算式的写法一致），只有 ``×(40-2)`` 这类
        顶层加减才补括号。除数位置由 :meth:`Dim.__truediv__` 单独保证。
        """
        if coefficient == 1.0:
            return
        suffix = f"×{wrap(expr) if expr is not None else fmt(coefficient)}"
        for quantity in self._items.values():
            quantity.value *= coefficient
            for term in quantity.terms:
                term.value *= coefficient
                term.expr = f"{wrap(term.expr)}{suffix}"

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
