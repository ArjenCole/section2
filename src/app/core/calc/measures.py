"""图集与原则参数的算式伴随（“表达式不做预运算”的支撑）。

计算引擎里参与算式的图集参数（外径 oD / 壁厚 t / 工作面加宽 a / 垫层厚 C1 /
基础厚 C2 / 工作面宽度 / 沟槽底宽）与原则参数（换填层厚、垫层厚、级高…）
除数值外都带一份 :class:`Dim`：

* 查表值 / 原则表值以 mm 原值进算式（mm 记法，``Dim.s=3``，``v`` 已换算成 m）；
* 详情面板覆盖时用参数行录入原文（可写算式）；
* 派生量（外径 = 管径 + 2×壁厚）把计算写全。

这样槽底宽、分层厚、弓形占位等在输出算式里都能追到管径 / 图集 / 面宽原则，
而不是一个算好的数字，见 :mod:`app.core.calc.tracer`。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.calc.tracer import Dim, mm, mm_dim, dim_sum

__all__ = [
    "AtlasDims",
    "cushion_thickness",
    "foundation_thickness",
    "groove_b_width",
    "mm_dim",
]


@dataclass(frozen=True)
class AtlasDims:
    """图集参数的算式伴随（字段与 services.atlas.AtlasParam 对齐，mm 记法）。

    ``od`` 保留 mm 原值（图集无 oD 时按 管径+2×壁厚 推出），几何链直接用、
    不再 ``/1000``；``groove_b`` 是槽底宽（面宽原则沟槽宽度表的 mm 值，
    services.atlas 已把数值换算成 m，算式按 mm 记法折叠回表值）。
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


def cushion_thickness(pf) -> Dim:
    """垫层厚（垫层 v10 起属地基原则）的算式伴随：原则垫层的表值（mm 记法）。"""
    return mm(pf.cushions[0].h if pf.cushions else 0.0).named(
        "垫层厚度", "地基原则·垫层表值"
    )


def foundation_thickness(pf) -> Dim:
    """换填总厚（旧版 mcPcpFoundation.TiA）的算式伴随：各换填层厚相加（mm 记法）。"""
    return dim_sum(
        *(mm(replacement.h).named("换填层厚", "地基原则·换填层") for replacement in pf.replacements)
    ).named("换填总厚度", "地基原则·各换填层厚之和")


def groove_b_width(value: float) -> Dim:
    """面宽原则沟槽宽度表的槽底宽（表值 mm，services.atlas 已把数值换算成 m）。

    算式按 mm 记法折叠回表值（``1.29`` → ``1290``），几何链直接用。
    """
    return mm(value * 1000.0).named("槽底宽", "面宽原则·沟槽宽度表")
