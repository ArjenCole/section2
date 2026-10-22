"""降水计算（复刻旧版 mscGroove.cal_precipitation）。

按沟槽深度阈值从深井到轻型井点依次判定井型；座数 = ⌈长度/井距⌉ × 侧数，
按每延米存储（÷数量），最终由引擎 ×数量 还原为总座数/根数。
无井型适用且启用湿土排水、深度 > 1m 时，取 深度-1m 断面的挖方作为湿土排水量。

座数的算式不做预运算：``CEILING(长度/井距,1)*侧数`` 写全井距与侧数（Excel 语法，
可直接复制进 Excel）；``CEILING`` 是 evaluator 白名单里为这条算式放开的取整函数。
"""

from __future__ import annotations

import math

from app.core.models.models import parse_precipitation
from app.core.calc import groove
from app.core.calc.measures import AtlasDims
from app.core.calc.tracer import Dim, QDict, dim, fmt, raw_dim, wrap


def _enabled(text: str, key: str) -> tuple[bool, float, float, float]:
    elevation, gap, sides = parse_precipitation(text, key)
    return elevation >= 0, elevation, gap, sides


def cal_precipitation(pp, pe, work, pf, ad: AtlasDims, info, groove_depth: Dim, out: QDict) -> None:
    """降水工程量（每延米），结果写入 ``out``；井型配置取降水原则 ``pp``。

    湿土排水的沟槽断面（深度−1m）仍按围护原则 ``pe`` 的开挖/回填结构算。
    """
    amount = info.amount or 1.0
    amount_dim = raw_dim(info.amount_text, amount)
    for key, name, unit in (
        ("deep_well", "深井", "座"),
        ("big_well", "大口径井点", "座"),
        ("jet_well", "喷射井点", "根"),
        ("light_well", "轻型井点", "根"),
    ):
        enabled, elevation, gap, sides = _enabled(getattr(pp, key), key)
        if enabled and groove_depth.v > elevation and gap > 0:
            wells = math.ceil(amount / gap) * sides
            # 座数按每延米存储（÷数量）：数量在除数位置，算式必须加括号（tight），
            # 数量为算式时 /(40*2) 不能写成 /40*2
            length = wrap(amount_dim.e, tight=True)
            out.add(
                f"降水|{name}|{unit}",
                wells / amount,
                f"CEILING({length}/{fmt(gap)},1)*{fmt(sides)}/{length}",
                f"深度 {fmt(groove_depth.v)}m > {fmt(elevation)}m，采用{name}；"
                f"井距 {fmt(gap)}m × {fmt(sides)} 侧",
            )
            return

    enabled, _elevation, _gap, _sides = _enabled(pp.wet_soil, "wet_soil")
    if enabled and groove_depth.v > 1:
        sub = QDict()
        groove.cal_groove(
            pe, work, pf, ad, info.size_b_dim, info.size_h_dim, groove_depth - dim(1.0), sub
        )
        dig = sub.get(f"开挖|{pe.excvt}|m3")
        if dig is not None:
            out.add(
                "降水|湿土排水|m3",
                dig.value,
                dig.expression,
                "湿土排水 = 沟槽深度−1m 断面挖方",
            )
