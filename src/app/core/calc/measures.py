"""图集与原则参数的算式伴随（“表达式不做预运算”的支撑）。

计算引擎里参与算式的图集参数（外径 oD / 壁厚 t / 工作面加宽 a / 垫层厚 C1 /
基础厚 C2 / 工作面宽度 / 沟槽底宽）与原则参数（换填层厚、垫层厚、级高…）
除数值外都带一份 :class:`Dim`：

* 查表值 / 原则表值以原始数字出现（表里按 mm 填的写成 ``值/1000`` 的换算）；
* 详情面板覆盖时用参数行录入原文（可写算式）；
* 派生量（外径 = 管径 + 2×壁厚）把计算写全。

这样槽底宽、分层厚、弓形占位等在输出算式里都能追到管径 / 图集 / 面宽原则，
而不是一个算好的数字，见 :mod:`app.core.calc.tracer`。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.calc.tracer import Dim, dim, dim_sum, fmt

__all__ = [
    "AtlasDims",
    "cushion_thickness",
    "foundation_thickness",
    "groove_b_width",
]


@dataclass(frozen=True)
class AtlasDims:
    """图集参数的算式伴随（字段与 services.atlas.AtlasParam 对齐，单位同它：mm）。

    ``od`` 保留 mm 原值（图集无 oD 时按 管径+2×壁厚 推出），用到处再 ``/1000``
    换算进算式；``groove_b`` 是槽底宽 m（面宽原则沟槽宽度表的 mm 值 /1000）。
    """

    od: Dim
    t: Dim
    a: Dim
    c1: Dim
    c2: Dim
    workwidth: Dim
    groove_b: Dim

    def replace(self, **changes: Dim) -> "AtlasDims":
        return replace(self, **changes)


def cushion_thickness(pe) -> Dim:
    """垫层厚 mm（旧版 PE.Cush.H）的算式伴随：原则垫层的表值。"""
    return dim(pe.cushions[0].h if pe.cushions else 0.0)


def foundation_thickness(pf) -> Dim:
    """换填总厚 mm（旧版 mcPcpFoundation.TiA）的算式伴随：各换填层厚相加。"""
    return dim_sum(*(dim(replacement.h) for replacement in pf.replacements))


def groove_b_width(value: float) -> Dim:
    """面宽原则沟槽宽度表的槽底宽 m：表里按 mm 填，算式写成 ``表值/1000``。"""
    return Dim(value, f"{fmt(value * 1000)}/1000")
