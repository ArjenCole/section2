"""表达式记录器。

每个工程量条目产出 ``{key, value, expression, details}``：

* ``expression`` 是一条数值代入的算式，如
  ``(1.2+1.2+2×2.85×0.5)×2.85/2×100 = 583.1``；
* 多来源的量（分层土方、多个构件公式）按项累加，算式用 +/− 连接各代入项；
* ``details`` 保留中间步骤（分层明细、公式名等），供表格 tooltip / 详情弹窗查看，
  不进主算式。

算式求值与表达式拼接共用同一套数值：先拼出“全数字”的算式字符串，
再用 core.evaluator 对它求值得到结果，禁止两套算法各算各的。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SUPERSCRIPTS = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹"}


def fmt(value: float, digits: int = 4) -> str:
    """数值代入用的数字格式：四舍五入后去尾零（100 → "100"，2.85 → "2.85"）。"""
    text = f"{round(float(value), digits):.{digits}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


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

    def scale(self, coefficient: float) -> None:
        """整体乘系数（旧版 MultDic_StrmcQ）；系数进算式。"""
        if coefficient == 1.0:
            return
        suffix = f"×{fmt(coefficient)}"
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
