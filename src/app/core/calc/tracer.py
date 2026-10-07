"""表达式记录器。

每个工程量条目产出 ``{key, value, expression, details}``：

* ``expression`` 是一条代入后的算式，如
  ``(1.2+1.2+2×2.85×0.5)×2.85/2×100 = 583.1``；
* 用户在埋深 / 数量列写的算式以原文（括号保护）出现在代入位置，
  见 :class:`Dim`；
* 多来源的量（分层土方、多个构件公式）按项累加，算式用 +/− 连接各代入项；
* ``details`` 保留中间步骤（分层明细、公式名等），供表格 tooltip / 详情弹窗查看，
  不进主算式。

算式求值与表达式拼接共用同一套数值：先拼出可求值的算式字符串，
再用 core.evaluator 对它求值得到结果，禁止两套算法各算各的。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SUPERSCRIPTS = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹"}

#: 纯数字（含负号与小数）——这类算式嵌入模板时无需加括号
_NUMERIC = re.compile(r"-?\d+(?:\.\d+)?")


def fmt(value: float, digits: int = 4) -> str:
    """数值代入用的数字格式：四舍五入后去尾零（100 → "100"，2.85 → "2.85"）。"""
    text = f"{round(float(value), digits):.{digits}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def wrap(expression: str) -> str:
    """算式嵌入模板前的保护：非纯数字加括号，保证运算优先级不变。"""
    text = expression.strip()
    return text if _NUMERIC.fullmatch(text) else f"({text})"


@dataclass
class Dim:
    """带算式的尺寸量（埋深、层厚、数量）：``v`` 为数值，``e`` 为求值等价的算式。

    数值与算式同源：加减除都在 Dim 上进行——纯数字之间运算折叠成单个数字
    （写法与旧版全数字算式一致），含算式的运算把原文括号后拼进算式，
    保证 ``e`` 重算永远等于 ``v``。``e`` 是裸算式，嵌入模板前须经 :func:`wrap`。
    """

    v: float
    e: str

    def __add__(self, other: "Dim") -> Dim:
        if self.v == 0:
            return other
        if other.v == 0:
            return self
        value = self.v + other.v
        if _NUMERIC.fullmatch(self.e) and _NUMERIC.fullmatch(other.e):
            return Dim(value, fmt(value))
        # 加法两侧都是同级运算，右操作数加括号只为可读；左操作数无须括号
        return Dim(value, f"{self.e}+{wrap(other.e)}")

    def __sub__(self, other: "Dim") -> "Dim":
        if other.v == 0:
            return self
        value = self.v - other.v
        if _NUMERIC.fullmatch(self.e) and _NUMERIC.fullmatch(other.e):
            return Dim(value, fmt(value))
        # 减法的右操作数是算式时必须括起来，否则 X-(A+B) 会变成 X-A+B
        return Dim(value, f"{self.e}-{wrap(other.e)}")

    def __truediv__(self, divisor: float) -> "Dim":
        if divisor == 1:
            return self
        return Dim(self.v / divisor, f"{wrap(self.e)}/{fmt(divisor)}")


def dim(value: float, expr: str | None = None) -> Dim:
    """纯数值尺寸：算式就是数值本身。"""
    return Dim(float(value), expr if expr is not None else fmt(value))


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
    """工程量的一个代入项：expr 为未带正负号的算式，value 为带符号数值。"""

    expr: str
    value: float
    note: str = ""


@dataclass
class Quantity:
    """一个工程量条目：定额键 + 数值 + 数值代入算式 + 中间步骤。"""

    key: str
    value: float = 0.0
    terms: list[Term] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    @property
    def expression(self) -> str:
        parts: list[str] = []
        for index, term in enumerate(self.terms):
            expr = term.expr
            negative = term.value < 0
            if negative and re.search(r"[+×/^-]", expr):
                expr = f"({expr})"
            if index == 0:
                parts.append(f"-{expr}" if negative else expr)
            else:
                parts.append(f"-{expr}" if negative else f"+{expr}")
        return prettify("".join(parts)) if parts else "0"

    def add_term(self, value: float, expr: str) -> None:
        self.value += value
        if value != 0:
            # 算式只存“数值代入”部分，正负号由 value 决定，避免出现双重负号
            self.terms.append(Term(expr=expr.lstrip("-") or "0", value=value))


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
        quantity = self._items.get(key)
        if quantity is None:
            quantity = Quantity(key=key)
            self._items[key] = quantity
        quantity.add_term(value, expr or fmt(value))
        if note:
            quantity.details.append(note)
        return quantity

    def discard(self, key: str) -> None:
        """移除一个条目（挖方合并用）。"""
        self._items.pop(key, None)

    def extend(self, other: "QDict") -> None:
        """合并另一本字典（旧版 PlusDic_StrmcQ）。"""
        for quantity in other.items():
            target = self.add(quantity.key, 0.0)
            for term in quantity.terms:
                target.add_term(term.value, term.expr)
            target.details.extend(quantity.details)

    def scale(self, coefficient: float, expr: str | None = None) -> None:
        """整体乘系数（旧版 MultDic_StrmcQ）；系数进算式，``expr`` 为系数的算式原文。"""
        if coefficient == 1.0:
            return
        suffix = f"×{wrap(expr) if expr is not None else fmt(coefficient)}"
        for quantity in self._items.values():
            quantity.value *= coefficient
            for term in quantity.terms:
                term.value *= coefficient
                term.expr = f"({term.expr})" if re.search(r"[+−-]", term.expr) else term.expr
                term.expr += suffix

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
