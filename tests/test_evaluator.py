"""core.evaluator 单元测试（计划 §2：录入框支持算式、白名单运算符）。"""

from __future__ import annotations

import math

import pytest

from app.core.evaluator import EvalError, evaluate, evaluate_or_default, format_number, normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.5+0.3", 2.8),
        ("0", 0.0),
        ("", 0.0),
        ("2*(3+4)", 14.0),
        ("-(1+2)", -3.0),
        ("2^3", 8.0),
        ("2**3", 8.0),
        ("10/4", 2.5),
        ("1.2+1.2+2*2.85*0.5", 5.25),
        ("（1+2）×3", 9.0),
        ("sqrt(9)", 3.0),
        ("abs(-3.5)", 3.5),
        ("power(2,10)", 1024.0),
        ("round(3.14159,2)", 3.14),
    ],
)
def test_evaluate_ok(text: str, expected: float) -> None:
    assert evaluate(text) == pytest.approx(expected)


def test_pi_constant() -> None:
    assert evaluate("pi") == pytest.approx(math.pi)
    assert evaluate("PI()*2") == pytest.approx(math.pi * 2)


@pytest.mark.parametrize(
    "text",
    [
        "2.5+",
        "abc",
        "1/0",
        "2 & 3",  # 位运算不在白名单
        "[1,2][0]",  # 下标不允许
        "__import__('os').system('dir')",  # 属性访问不允许
        "().__class__",
        "open('x')",
    ],
)
def test_evaluate_rejects(text: str) -> None:
    with pytest.raises(EvalError):
        evaluate(text)


def test_conditional_expression_is_harmless() -> None:
    """simpleeval 自带条件表达式；无副作用，不影响安全边界。"""
    assert evaluate("1 if 1 else 2") == 1


def test_evaluate_or_default() -> None:
    assert evaluate_or_default("2+2") == 4.0
    assert evaluate_or_default("坏算式") == 0.0
    assert evaluate_or_default("坏算式", default=-1.0) == -1.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (100.0, "100"),
        (2.85, "2.85"),
        (583.1, "583.1"),
        (0.0, "0"),
        (-0.00001, "0"),
        (1 / 3, "0.3333"),
        (1234.56789, "1234.5679"),
    ],
)
def test_format_number(value: float, expected: str) -> None:
    assert format_number(value) == expected


def test_normalize_symbols() -> None:
    assert normalize(" 2 ×（3） ") == "2 *(3)"
    assert normalize("D^2") == "D**2"
