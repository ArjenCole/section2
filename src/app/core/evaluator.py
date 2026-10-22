"""算式求值封装（simpleeval 白名单）。

录入框（埋深、数量、含量…）允许直接写算式，如 `2.5+0.3`。求值结果不落库：
库里存字符串原文，运行时用本模块算，避免两份数据不一致。

安全边界：只放开 + - * / ** 与括号，以及旧版 mscExp 支持的 abs/round/sqrt/power
四个函数和常量 pi（另加计算引擎输出算式要用的 sin/cos/ceiling/roundup）；没有
属性访问、下标、lambda、比较、位运算。
（simpleeval 自带的 ``1 if 1 else 2`` 这类条件表达式无副作用，未额外收紧。）

**输出侧是 Excel 语法**（`*` `/` `^`、`CEILING(x,1)`、`SIN(...)`、`PI()`），
用户复制进 Excel 即为可用公式；本模块的归一化与函数表保证这些写法自己也能求值，
并且 Excel 与 Python 在舍入上对齐（ROUND 逢 5 远离零，见 :func:`_excel_round`）。
"""

from __future__ import annotations

import ast
import math
import operator
import re
from decimal import ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Any

from simpleeval import InvalidExpression, SimpleEval, safe_power

__all__ = ["EvalError", "ceil_ratio", "evaluate", "evaluate_or_default", "format_number", "normalize"]


class EvalError(ValueError):
    """表达式无法求值（语法错误、除零、未知符号等）。"""


#: 白名单运算符：仅四则运算与乘方（含一元正负号）。
#: 乘方用 simpleeval 的 safe_power（限制指数大小），避免 `9**9**9` 这类输入卡死界面。
_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: safe_power,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

#: 白名单函数与常量，对应旧版 mscExp.ProcessFunction / ProcessSymbol；
#: 同时补齐 Excel 函数名（CEILING/ROUNDUP/PI），使输出的算式能被自己重算。
#: ``round``/``ceiling`` 采用 Excel 语义（见 :func:`_excel_round` / :func:`_ceiling`），
#: 与 Python 内置的银行家舍入、``math.ceil`` 的浮点行为不同，改动时注意别退回。
def _excel_round(value: Any, digits: Any = 0) -> float:
    """Excel ``ROUND``：四舍五入到 ``digits`` 位小数，逢 5 远离零（0.125 → 0.13）。

    Python 内置 ``round`` 是银行家舍入（0.125 → 0.12），复制到 Excel 会得到不同
    结果，所以这里按十进制表示做 ``ROUND_HALF_UP``，与 Excel 对齐。
    """
    places = int(digits)
    quant = Decimal(1).scaleb(-places)
    return float(Decimal(repr(float(value))).quantize(quant, rounding=ROUND_HALF_UP))


def _excel_roundup(value: Any, digits: Any = 0) -> float:
    """Excel ``ROUNDUP``：远离零向上取到 ``digits`` 位小数。"""
    places = int(digits)
    quant = Decimal(1).scaleb(-places)
    return float(Decimal(repr(float(value))).quantize(quant, rounding=ROUND_UP))


#: 取整前把商收敛到的小数位：抹掉二进制浮点噪声（4.2/1.4 = 3.0000000000000004），
#: 真实商离整数的最小距离是 1/间距 量级，远大于 1e-9，不会误伤。
_CEIL_DIGITS = 9


def ceil_ratio(value: Any, divisor: Any = 1) -> float:
    """⌈value/divisor⌉：井点座数 = ⌈长度/井距⌉。

    二进制浮点存不下 4.2、1.4 这类十进制小数，商可能落在整数**略上方**
    （``4.2/1.4 = 3.0000000000000004``），直接 ``math.ceil`` 会多进一位、多算
    一座井。这里先把商收敛到 ``_CEIL_DIGITS`` 位小数再取整。

    **收敛只发生在求值内部**：输出的算式仍然写 ``CEILING(长度/井距,1)``，
    不带任何辅助函数，用户复制进 Excel 看到的还是标准写法。
    """
    step = float(divisor) or 1.0
    return float(math.ceil(round(float(value) / step, _CEIL_DIGITS)))


def _ceiling(value: Any, significance: Any = 1) -> float:
    """Excel ``CEILING(number, significance)``：向上取到 ``significance`` 的整数倍。

    ``CEILING(x,1)`` 即 ``⌈x⌉``，是引擎输出的井点座数写法；旧写法 ``ceil(x)``
    也指向这里，保持兼容。取整前先收敛浮点噪声，见 :func:`ceil_ratio`。
    """
    step = float(significance) or 1.0
    return ceil_ratio(value, step) * step


_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": _excel_round,
    "roundup": _excel_roundup,
    "sqrt": math.sqrt,
    "power": safe_power,
    "ceil": _ceiling,
    "ceiling": _ceiling,
    "sin": math.sin,
    "cos": math.cos,
}
_NAMES: dict[str, Any] = {"pi": math.pi, "PI": math.pi}

#: 中文输入法下常见的全角符号/乘除号 → 半角
_SYMBOLS = {
    "×": "*",
    "✕": "*",
    "＊": "*",
    "÷": "/",
    "／": "/",
    "（": "(",
    "）": ")",
    "＋": "+",
    "－": "-",
    "−": "-",
    "．": ".",
    "＝": "=",
}

#: 上标数字 → 乘方（表达式记录器输出的可读写法）
_SUPERSCRIPTS = {"⁰": 0, "¹": 1, "²": 2, "³": 3, "⁴": 4, "⁵": 5, "⁶": 6, "⁷": 7, "⁸": 8, "⁹": 9}

_POWER_MARK = re.compile(r"\^")


def normalize(text: str) -> str:
    """全角符号转半角、`^`/上标视作乘方、函数名转小写、去掉首尾空白。

    旧版用 SoftCircuits Eval，公式库里写的是 `^` 乘方、`PI()`、大写 ROUND，
    这里一并归一化成 Python 可求值的形式；引擎输出的是 Excel 语法
    （`CEILING(x,1)`、`SIN(...)`、`PI()`），同一套归一化保证它也能被自己重算。
    用户从 Excel 粘进来的公式带开头 `=`，这里直接剥掉。
    """
    result = text.strip()
    for source, target in _SYMBOLS.items():
        result = result.replace(source, target)
    result = result.lstrip("=").strip()
    # Excel 的 CEILING.MATH 带点，不是合法标识符，先收敛成 CEILING
    result = re.sub(r"\bCEILING\.MATH\s*\(", "CEILING(", result, flags=re.IGNORECASE)
    result = _POWER_MARK.sub("**", result)
    for character, exponent in _SUPERSCRIPTS.items():
        result = result.replace(character, f"**{exponent}")
    result = result.replace("PI()", "pi").replace("pi()", "pi")
    # 长名在前：\b 保证 CEIL 不会咬掉 CEILING，ROUND 不会咬掉 ROUNDUP
    for name in ("CEILING", "ROUNDUP", "ROUND", "SQRT", "ABS", "POWER", "CEIL", "SIN", "COS"):
        result = re.sub(r"\b" + name + r"\b", name.lower(), result, flags=re.IGNORECASE)
    return result


def evaluate(text: str) -> float:
    """求值，失败抛 EvalError。空表达式视为 0。"""
    expression = normalize(text if text is not None else "")
    if expression == "":
        return 0.0
    evaluator = SimpleEval(operators=dict(_OPERATORS), functions=dict(_FUNCTIONS), names=dict(_NAMES))
    try:
        value = evaluator.eval(expression)
    except ZeroDivisionError as error:
        raise EvalError("除数为 0") from error
    except InvalidExpression as error:
        raise EvalError(str(error) or "算式不合法") from error
    except Exception as error:  # simpleeval 内部还会抛 SyntaxError / NameNotDefined 等
        raise EvalError(f"无法求值: {error}") from error
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvalError("算式结果不是数值")
    result = float(value)
    if math.isnan(result) or math.isinf(result):
        raise EvalError("算式结果不是有效数值")
    return result


def evaluate_or_default(text: str, default: float = 0.0) -> float:
    """求值失败时返回默认值（旧版 mscExp.Eval 失败返回 "0" 的语义）。"""
    try:
        return evaluate(text)
    except EvalError:
        return default


def format_number(value: float, digits: int = 4) -> str:
    """按旧版 mscMslns.ShowDouble 的规则格式化：四舍五入到 4 位后去掉多余的 0。"""
    text = f"{round(float(value), digits):.{digits}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"
