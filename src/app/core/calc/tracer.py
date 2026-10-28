"""表达式记录器。

每个工程量条目产出 ``{key, value, expression, terms}``：

* ``expression`` 是一条代入后的算式，加减链里公共的 ``/1000`` 已按四则运算
  规则提到括号外（见 :func:`extract_common_divisors`），如
  ``(2*(600+(65*2+130*2+500*2))/1000+2*2.995*1)*2.995/2``；
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


# --------------------------------------------------------------------------- #
# 公共 /1000 提取（输出表达式可读化）
# --------------------------------------------------------------------------- #
_OPENERS = "([{"
_CLOSERS = ")]}"
_THOUSAND = re.compile(r"1000(?:\.0*)?")


def _binary_sign_positions(text: str) -> list[int]:
    """顶层二元加减号的位置（括号内、一元正负号、科学计数 1E-5 的指数号不算）。"""
    positions: list[int] = []
    depth = 0
    for index, character in enumerate(text):
        if character in _OPENERS:
            depth += 1
        elif character in _CLOSERS:
            depth -= 1
        elif depth == 0 and character in "+-":
            previous = text[index - 1] if index else ""
            if not previous or not (previous.isalnum() or previous in _CLOSERS):
                continue  # 一元正负号
            if (
                previous in "Ee"
                and index >= 2
                and text[index - 2].isdigit()
            ):
                continue  # 1E-5 的指数符号
            positions.append(index)
    return positions


def _term_divisor(term: str) -> tuple[str, int] | None:
    """乘除链里 ``/1000`` 因子提出后的 (剩余算式, 个数)；没有可提出的因子返回 None。

    因子按顶层 ``*`` / ``/`` 切（``**`` 乘方与括号整体都属于因子内部，不算
    分隔符）；只有 ``/1000`` 形态（恰好除以常数 1000）的因子可以提出。
    """
    factors: list[str] = []
    depth = 0
    start = 0
    for index, character in enumerate(term):
        if character in _OPENERS:
            depth += 1
        elif character in _CLOSERS:
            depth -= 1
        elif depth == 0 and character in "*/":
            if character == "*" and (
                term[index + 1 : index + 2] == "*" or term[index - 1 : index] == "*"
            ):
                continue  # 乘方 ** 的两个星号都不是分隔符
            factors.append(term[start:index])
            start = index
    factors.append(term[start:])
    kept: list[str] = []
    count = 0
    for factor in factors:
        stripped = factor.strip()
        operator, body = ("", stripped)
        if stripped[:1] in "*/":
            operator, body = stripped[:1], stripped[1:].strip()
        if operator == "/" and _THOUSAND.fullmatch(body):
            count += 1
            continue
        kept.append(stripped)
    if count == 0:
        return None
    residual = "".join(kept).strip()
    return (residual, count) if residual else None


def _strip_group_parens(residual: str) -> str:
    """去掉残式外围的一层括号（仅当首括号与末括号正好配对包住整个残式）。"""
    text = residual.strip()
    if not (text.startswith("(") and text.endswith(")")):
        return text
    depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return text  # 首括号的配对不在末尾：不是整体包裹
    return text[1:-1].strip()


def _joined_residual(residual: str, operator: str) -> str:
    """残式并回括号组时的形态：按上下文去掉冗余的外层括号。

    组首与加号后的残式括号总可去（加法左结合）；减号后的残式如果剥掉
    外围括号后顶层出现加减，说明那层括号正是在保护"作为整体被减的加减组"
    （``X-(A+B)`` ≠ ``X-A+B``），必须保留。
    """
    if operator == "-":
        inner = _strip_group_parens(residual)
        if _top_operator(inner, _ADDITIVE):
            return residual if residual.startswith("(") else f"({inner})"
        return inner
    return _strip_group_parens(residual)


def _extract_chain(text: str) -> str:
    """把加减链里**连续两段以上**公共的 ``/1000`` 提取到括号外。

    只处理连续的可提取段（段序不变）；函数参数表（顶层逗号）与单段链不动。
    ``600/1000+(65*2)/1000`` → ``(600+65*2)/1000``；首段带负号的连续段
    （``X-A/1000-B/1000``）括号内符号取反 → ``X-(A+B)/1000``。
    """
    depth = 0
    for character in text:
        if character in _OPENERS:
            depth += 1
        elif character in _CLOSERS:
            depth -= 1
        elif depth == 0 and character == ",":
            return text  # 顶层逗号 = 函数参数表，不动
    positions = _binary_sign_positions(text)
    if not positions:
        return text
    terms: list[tuple[str, str]] = []
    cursor = 0
    for order, index in enumerate(positions):
        operator = "" if order == 0 else text[positions[order - 1]]
        terms.append((operator, text[cursor:index].strip()))
        cursor = index + 1
    terms.append((text[positions[-1]], text[cursor:].strip()))
    if any(not body for _operator, body in terms):
        return text

    #: (运算符, 原段, 提出后的残式或 None, 提出的个数或 -1)
    extracted: list[tuple[str, str, str | None, int]] = []
    for operator, body in terms:
        found = _term_divisor(body)
        if found is None:
            extracted.append((operator, body, None, -1))
        else:
            extracted.append((operator, body, found[0], found[1]))

    parts: list[str] = []
    index = 0
    total = len(extracted)
    while index < total:
        if extracted[index][3] < 0:
            parts.append(extracted[index][0] + extracted[index][1])
            index += 1
            continue
        run_end = index
        while run_end < total and extracted[run_end][3] >= 0:
            run_end += 1
        if run_end - index >= 2:
            # 连续可提取段按"提出的个数"再分组：个数不同（如 /1000/1000 与
            # /1000 混排）不能合进同一个括号，各自成组、单段原样保留
            sub_index = index
            while sub_index < run_end:
                count = extracted[sub_index][3]
                sub_end = sub_index
                while sub_end < run_end and extracted[sub_end][3] == count:
                    sub_end += 1
                chunk = extracted[sub_index:sub_end]
                if len(chunk) >= 2:
                    # 首段运算符留在括号外；为负时括号内各段运算符取反
                    # （-(A-B)/1000 = -A/1000+B/1000）
                    first_operator = chunk[0][0]
                    flip = first_operator == "-"
                    inner_parts: list[str] = []
                    for order in range(len(chunk)):
                        operator = "" if order == 0 else chunk[order][0]
                        if order == 0:
                            operator = ""
                        elif flip:
                            operator = "+" if operator == "-" else "-"
                        inner_parts.append(
                            operator + _joined_residual(chunk[order][2], operator)
                        )
                    inner = "".join(inner_parts)
                    parts.append(first_operator + f"({inner})" + "/1000" * count)
                else:
                    parts.append(chunk[0][0] + chunk[0][1])  # 单段原样
                sub_index = sub_end
        else:
            for order in range(index, run_end):
                parts.append(extracted[order][0] + extracted[order][1])  # 单段原样
        index = run_end
    return "".join(parts)


def extract_common_divisors(expression: str) -> str:
    """输出表达式可读化：把公共的 ``/1000`` 按四则运算规则提到括号外。

    引擎按"不预运算"原则把毫米→米换算写成 ``/1000``，同一加减链里反复出现
    （``600/1000+(65*2+130*2+500*2)/1000``）；连续两段以上公共的 ``/1000``
    提取为 ``(600+(65*2+130*2+500*2))/1000``，值不变、式更短。逐段扫描
    （顶层加减号切段、段内乘除链找 ``/1000`` 因子、括号组递归），扫描失败
    或无公共因子时原样返回。
    """
    text = (expression or "").strip()
    if "/1000" not in text:
        return text
    return _extract_chain(_rewrite_groups(text))


def _rewrite_groups(text: str) -> str:
    """递归改写各顶层括号组（组内再找更深的组与加减链）。

    组重写后顶层只剩乘除、且组不在除数 / 乘方底数位置时，外层括号可以
    去掉（``2*((600+…)/1000)`` → ``2*(600+…)/1000``，左结合下同值），
    避免改写引入冗余括号。
    """
    pieces: list[str] = []
    cursor = 0
    depth = 0
    start = -1
    for index, character in enumerate(text):
        if character in _OPENERS:
            if depth == 0:
                start = index
            depth += 1
        elif character in _CLOSERS:
            depth -= 1
            if depth < 0:
                return text
            if depth == 0 and start >= 0:
                original = text[start + 1 : index]
                content = _extract_chain(_rewrite_groups(original))
                if content == original:
                    pieces.append(text[cursor : index + 1])  # 组内没有变化：原样保留
                    cursor = index + 1
                    start = -1
                    continue
                before = text[cursor:start].rstrip()
                after = text[index + 1 : index + 3].lstrip()
                # 除数 / 乘方（前后紧邻 ^ **）位置的组括号不能去；函数调用
                # （SIN( … 的括号是语法的一部分，更不能动）
                tight = (
                    before.endswith(("/", "**", "^"))
                    or before[-1:].isalnum()
                    or before[-1:] == "_"
                    or after.startswith(("^", "**"))
                )
                if tight or not content.strip() or _top_operator(content, _ADDITIVE):
                    pieces.append(text[cursor:start] + "(" + content + ")")
                else:
                    pieces.append(text[cursor:start])
                    pieces.append(content)
                cursor = index + 1
                start = -1
    if depth != 0:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


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
        return Dim(self.v * value, f"{wrap(self.e)}*{wrap(expr)}")

    __rmul__ = __mul__

    def __truediv__(self, other: "Dim | float") -> "Dim":
        value, expr = pair(other)
        if value == 1:
            return self  # ÷1 不写进算式（只可能是引擎生成的等分，用户写的算式保留原文）
        # 除数位置的算式要更严格：顶层乘除也得括起来，否则 _a/(b*c) 会变成 _a/b*c
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
            # 算式只存“数值代入”部分，正负号由 value 决定，避免出现双重负号；
            # 存入前把公共的 /1000 提到括号外（输出可读化，值不变，见
            # :func:`extract_common_divisors`）
            self.terms.append(
                Term(
                    expr=extract_common_divisors(expr.lstrip("-") or "0"),
                    value=value,
                    note=note,
                )
            )


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
