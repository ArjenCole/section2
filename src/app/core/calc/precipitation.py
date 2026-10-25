"""降水计算（复刻旧版 mscGroove.cal_precipitation）。

按沟槽深度阈值从深井到轻型井点依次判定井型；座数 = ⌈长度/井距⌉ × 侧数，
按每延米存储（÷数量），最终由引擎 ×数量 还原为总座数/根数。
无井型适用且启用湿土排水、深度 > 1m 时，取 深度-1m 断面的挖方作为湿土排水量。

座数的算式不做预运算：``CEILING(长度/井距,1)*侧数`` 写全井距与侧数（Excel 语法，
可直接复制进 Excel）；``CEILING`` 是 evaluator 白名单里为这条算式放开的取整函数。

座数的数值走 :func:`app.core.evaluator.ceil_ratio`，与算式求值同一个函数：它在
求值内部先把商收敛到 9 位小数，抹掉 ``4.2/1.4 = 3.0000000000000004`` 这类二进制
浮点噪声（否则长度正好整除时会多算一座井）。收敛**只发生在代码里**，输出算式仍
是标准写法，不带任何辅助函数。
"""

from __future__ import annotations

from app.core.evaluator import ceil_ratio
from app.core.models.models import parse_precipitation
from app.core.calc import groove
from app.core.calc.measures import AtlasDims
from app.core.calc.tracer import Dim, QDict, dim, fmt, raw_dim, wrap


def _enabled(text: str, key: str) -> tuple[bool, float, float, float]:
    elevation, gap, sides = parse_precipitation(text, key)
    return elevation >= 0, elevation, gap, sides


def cal_precipitation(
    pp,
    pe,
    work,
    pf,
    ad: AtlasDims,
    info,
    groove_depth: Dim,
    out: QDict,
    work_r=None,
    cushion_name: str | None = None,
    wet_dig=None,
) -> None:
    """降水工程量（每延米），结果写入 ``out``；井型配置取降水原则 ``pp``。

    湿土排水的沟槽断面（深度−1m）仍按围护原则 ``pe`` 的开挖/回填结构算；
    左右分设模式传 ``work_r``（右做法）时走双侧几何，垫层材质由
    ``cushion_name`` 显式传入（管道基础侧原则）。

    ``wet_dig``（合槽用）：预计算的湿土排水量（Dim，按归属带宽的简化断面），
    传入时跳过单管断面副调用直接采用。
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
            # ⌈长度/井距⌉：ceil_ratio 在求值内部收敛浮点噪声（4.2/1.4 别多算一座），
            # 但输出算式仍是标准 CEILING(…,1)，不带任何辅助函数
            wells = ceil_ratio(amount, gap) * sides
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
        if wet_dig is not None:
            # 合槽：湿土排水 = 归属带宽 ×（槽深−1m）的简化断面（合槽路径预算）
            if wet_dig.v != 0:
                out.add(
                    "降水|湿土排水|m3",
                    wet_dig.v,
                    wet_dig.e,
                    "湿土排水 = 归属带宽×(槽深−1m)（合槽简化断面）",
                )
            return
        sub = QDict()
        if work_r is None:
            groove.cal_groove(
                pe, work, pf, ad, info.size_b_dim, info.size_h_dim, groove_depth - dim(1.0), sub
            )
        else:
            groove.cal_groove_sided(
                pe, work, work_r, pf, ad, info.size_b_dim, info.size_h_dim,
                groove_depth - dim(1.0), sub, cushion_name,
            )
        dig = sub.get(f"开挖|{pe.excvt}|m3")
        if dig is not None:
            out.add(
                "降水|湿土排水|m3",
                dig.value,
                dig.expression,
                "湿土排水 = 沟槽深度−1m 断面挖方",
            )
