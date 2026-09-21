"""算式求值封装（simpleeval 白名单，计划 §2、§4.2）。

录入框（埋深、数量、含量…）允许直接写算式，如 `2.5+0.3`。求值结果不落库：
库里存字符串原文，运行时用本模块算，避免两份数据不一致。

安全边界：只放开 + - * / ** 与括号，以及旧版 mscExp 支持的 abs/round/sqrt/power
四个函数和常量 pi；没有属性访问、下标、lambda、比较、位运算。
（simpleeval 自带的 ``1 if 1 else 2`` 这类条件表达式无副作用，未额外收紧。）
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any

from simpleeval import InvalidExpression, SimpleEval, safe_power

__all__ = ["EvalError", "evaluate", "evaluate_or_default", "format_number", "normalize"]


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

#: 白名单函数与常量，对应旧版 mscExp.ProcessFunction / ProcessSymbol
_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": lambda value, digits=2: round(value, int(digits)),
    "sqrt": math.sqrt,
    "power": safe_power,
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

_POWER_MARK = re.compile(r"\^")


def normalize(text: str) -> str:
    """全角符号转半角、`^` 视作乘方、去掉首尾空白。

    旧版用 SoftCircuits Eval，公式库里写的是 `^` 乘方、`PI()`，
    这里一并归一化成 Python 可求值的形式。
    """
    result = text.strip()
    for source, target in _SYMBOLS.items():
        result = result.replace(source, target)
    result = _POWER_MARK.sub("**", result)
    result = result.replace("PI()", "pi").replace("pi()", "pi")
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
