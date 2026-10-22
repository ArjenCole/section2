"""core.evaluator 单元测试（录入框支持算式、白名单运算符）。"""

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
        # Excel 语义：ROUND 逢 5 远离零（Python 内置 round 会给 0.12）
        ("ROUND(0.125,2)", 0.13),
        ("ROUNDUP(2.11,1)", 2.2),
        # Excel 写法可直接求值；CEILING 内部先收敛浮点噪声，4.2/1.4 不多进一位
        ("CEILING(4.2/1.4,1)", 3.0),
        ("CEILING(22.1/0.85,1)", 26.0),
        ("CEILING(7.3,0.5)", 7.5),
        ("CEILING(-2.1,1)", -2.0),
        ("3.141593*2", 6.283186),
        ("PI()*2", 2 * math.pi),
        ("=CEILING(4,1)+1", 5.0),
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
