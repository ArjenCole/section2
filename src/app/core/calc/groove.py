"""沟槽土方 / 回填计算（复刻旧版 mscGroove.cal_groove）。

分层回填列表自底向上：换填（PF 换填层，倒序）→ 垫层 → 坞膀下半 → 坞膀上半 →
管顶 50cm → 覆土；每层按当前围护级别的放坡系数算梯形断面
``Trapezoid(B,H,slope) = (2B+2Hs)H/2``，同一层挖方与回填取同一面积。
多级围护按 splitHbyStep 的分级标高切换，切级时按平台宽度加宽底宽。

槽底宽 B（断面宽 + 2×(壁厚 + 工作面加宽 + 工作面)）、各层层厚与放坡系数
都以 :class:`Dim`（数值 + 算式）参与计算，算式不做预运算：B 在输出算式里
保留管径 / 图集参数 / 面宽原则的推导，层厚保留 毫米→米 换算与埋深原文，
见 :mod:`app.core.calc.tracer` 与 :mod:`app.core.calc.measures`。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.calc.measures import AtlasDims, foundation_thickness
from app.core.calc.tracer import Dim, QDict, dim, dim_sum, fmt, raw_dim, scale_sum, wrap


def mm2m(value: float) -> float:
    """毫米 → 米（旧版 mscGroove.D10E3）；算式侧由 ``Dim/1000`` 写出换算。"""
    return value / 1000.0


def trapezoid(bottom: float, height: float, slope: float) -> float:
    """梯形断面面积（旧版 mscGroove.Trapezoid）。"""
    return (bottom + bottom + height * slope * 2) * height / 2.0


def trapezoid_expr(bottom: Dim, height: Dim, slope: Dim) -> str:
    """梯形面积的代入算式：``(2×B+2×H×放坡系数)×H/2``（直壁为 ``B×H``）。

    B 与 H 都带各自来源的算式（槽底宽由管径 / 图集 / 面宽原则推出），
    算式展开写全、不做预运算；B 只在算式里出现一次，避免长算式重复。
    """
    h = wrap(height.e)
    b = wrap(bottom.e)
    if slope.v == 0:
        return f"{b}×{h}"
    return f"(2×{b}+2×{h}×{wrap(slope.e)})×{h}/2"


def widen(delta: Dim, slope: Dim) -> Dim:
    """放坡外扩量 ``2×Δ×放坡系数``（底宽随层高外扩，算式保留两个来源）。"""
    return Dim(delta.v * slope.v * 2, f"2×{wrap(delta.e)}×{wrap(slope.e)}")


def min_h(height: Dim, remaining: Dim) -> tuple[Dim, Dim]:
    """本层厚度与剩余深度（旧版 mscGroove.minH：层高 <0 表示吃掉全部剩余）。"""
    if remaining.v <= height.v or height.v < 0:
        return remaining, dim(0.0)
    return height, remaining - height


def split_h_by_step(levels: list, depth: Dim) -> list[Dim]:
    """多级围护的分级标高（自槽底向上每级的累计高，旧版 splitHbyStep）。

    ``levels`` 为做法内的围护构件级列表（order_no 升序，levels[-1] 最深）；
    ``h < 0`` 的级与其余负值级均分 ``depth - 固定高合计``（埋深算式随之进算式）。
    """
    fixed_h = dim_sum(*(dim(level.h) for level in levels if level.h >= 0))
    fixed_cnt = sum(1 for level in levels if level.h >= 0)
    result: list[Dim] = []
    height = dim(0.0)
    for level in reversed(levels):
        if level.h >= 0:
            step = dim(level.h)
        elif len(levels) > fixed_cnt:
            step = (depth - fixed_h) / (len(levels) - fixed_cnt)
        else:
            step = depth
        height = height + step
        result.insert(0, height if height.v >= 0 else dim(0.0))
    return result


@dataclass
class _Segment:
    """挖方的一个等坡段（用于把连续梯形合并成一条算式）。

    ``breaks_before`` 为 True 表示本段之前发生过平台加宽（换级），
    不能与上一段合并成一条梯形。
    """

    bottom: Dim
    height: Dim
    slope: Dim
    breaks_before: bool = False


def backfill_layers(
    pe, pf, ad: AtlasDims, size_h: Dim, depth: Dim, cushion_name: str
) -> list[tuple[str, Dim, str]]:
    """分层回填列表（旧版 cal_groove 的 Backfill），返回 (定额键, 层厚, 说明)。"""
    layers: list[tuple[str, Dim, str]] = []
    for replacement in reversed(list(pf.replacements)):
        h = dim(replacement.h) / 1000
        layers.append((f"换填|{replacement.name}|m3", h, f"换填 {replacement.name} {fmt(h.v)}m"))
    total = depth if depth.v >= 0 else dim(0.0)
    remaining = total - foundation_thickness(pf) / 1000

    height, remaining = min_h((ad.c1 + ad.c2) / 1000, remaining)
    layers.append((f"垫层|{cushion_name}|m3", height, "垫层"))
    height, remaining = min_h(size_h / 2 + (ad.t - ad.c2) / 1000, remaining)
    layers.append((f"回填|{pe.dock_l}|m3", height, "坞膀下半"))
    height, remaining = min_h(size_h / 2 + ad.t / 1000, remaining)
    layers.append((f"回填|{pe.dock_h}|m3", height, "坞膀上半"))
    height, remaining = min_h(dim(0.5), remaining)
    layers.append((f"回填|{pe.cover50}|m3", height, "管顶50cm"))
    cover = total - size_h - (foundation_thickness(pf) + ad.t * 2 + ad.c1) / 1000 - dim(0.5)
    height, remaining = min_h(cover, remaining)
    layers.append((f"回填|{pe.cover}|m3", height, "覆土"))
    return layers


def groove_width(ad: AtlasDims, size_b: Dim) -> Dim:
    """槽底宽度 m：沟槽宽度表为 0 时按 断面宽+2×(壁厚+工作面加宽+工作面) 推算。"""
    if ad.groove_b.v != 0:
        return ad.groove_b
    return size_b + scale_sum((ad.t, ad.a, ad.workwidth), 2.0) / 1000


def cal_groove(
    pe, work, pf, ad: AtlasDims, size_b: Dim, size_h: Dim, depth: Dim, out: QDict
) -> bool:
    """计算沟槽断面工程量（每延米），结果写入 ``out``。

    返回 False 表示没有产生任何土方（覆土不足 / 深度为 0）。
    """
    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    layers = backfill_layers(pe, pf, ad, size_h, depth, cushion_name)
    bottom = groove_width(ad, size_b)
    step_heights = split_h_by_step(list(work.levels), depth)
    if not step_heights:
        return False
    step = len(work.levels) - 1

    current = dim(0.0)
    dig_key = f"开挖|{pe.excvt}|m3"
    dig_segments: list[_Segment] = []
    jump_pending = False
    for key, layer, note in layers:
        target = current + layer
        clipped = False
        while True:
            step_top = step_heights[step]
            if target.v <= step_top.v:
                # 整层落在当前分级内：层厚就是该层本身（数值仍按旧版递推 float）
                delta = target - current if clipped else Dim(target.v - current.v, layer.e)
            else:
                delta = step_top - current
                clipped = True
            slope = level_slope(work.levels[step])
            out.add(
                key,
                trapezoid(bottom.v, delta.v, slope.v),
                trapezoid_expr(bottom, delta, slope),
                note,
            )
            dig_segments.append(_Segment(bottom=bottom, height=delta, slope=slope, breaks_before=jump_pending))
            jump_pending = False
            if target.v <= step_top.v:
                current = current + delta
            else:
                # 切级处 current 恰好到达分级标高：数值同旧版递推，算式直接取标高，
                # 避免 "(累计)+(标高−累计)" 这类未化简写法
                current = Dim(current.v + delta.v, step_top.e)
            bottom = bottom + widen(delta, slope)
            if current.v == step_top.v and step > 0:
                step -= 1
                if step_heights[step].v != step_heights[step + 1].v and step_heights[step + 1].v != 0:
                    bottom = bottom + dim(work.levels[step].step_width) * 2
                    jump_pending = True  # 平台加宽处断开，不与上一段合并
            if current.v - target.v >= -0.0001:
                break

    # 挖方 = 各层梯形之和；等坡且无平台的连续段合并成一条梯形算式（可读性简化）
    dig = out.add(dig_key, 0.0)
    dig.terms.clear()
    dig.value = 0.0
    index = 0
    while index < len(dig_segments):
        segment = dig_segments[index]
        total = segment.height
        index += 1
        while (
            index < len(dig_segments)
            and not dig_segments[index].breaks_before
            and dig_segments[index].slope.v == segment.slope.v
        ):
            total = total + dig_segments[index].height
            index += 1
        if total.v != 0:
            # 连续段恰好铺满全槽时层厚就是沟槽深度，算式直接用埋深算式（含垫层调整）
            height = depth if abs(total.v - depth.v) < 1e-9 else total
            dig.add_term(
                trapezoid(segment.bottom.v, total.v, segment.slope.v),
                trapezoid_expr(segment.bottom, height, segment.slope),
            )
    if not dig.terms:
        out.discard(dig_key)
    return len(out) > 0


def level_slope(level) -> Dim:
    """围护级的放坡系数：A 参数显示名以“放坡系数”开头时取其值（旧版约定），否则 0。"""
    component = level.components[0] if level.components else None
    if component is None:
        return dim(0.0)
    for param in component.params:
        if param.key != "A":
            continue
        display, _, expression = (param.value or "").partition("|")
        if not display.startswith("放坡系数"):
            return dim(0.0)
        from app.core.evaluator import evaluate_or_default

        return raw_dim(expression, evaluate_or_default(expression))
    return dim(0.0)
