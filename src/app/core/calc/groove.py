"""沟槽土方 / 回填计算（复刻旧版 mscGroove.cal_groove，计划 §6.1）。

分层回填列表自底向上：换填（PF 换填层，倒序）→ 垫层 → 坞膀下半 → 坞膀上半 →
管顶 50cm → 覆土；每层按当前围护级别的放坡系数算梯形断面
``Trapezoid(B,H,slope) = (2B+2Hs)H/2``，同一层挖方与回填取同一面积。
多级围护按 splitHbyStep 的分级标高切换，切级时按平台宽度加宽底宽。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.calc.tracer import QDict, fmt


def mm2m(value: float) -> float:
    """毫米 → 米（旧版 mscGroove.D10E3）。"""
    return value / 1000.0


def trapezoid(bottom: float, height: float, slope: float) -> float:
    """梯形断面面积（旧版 mscGroove.Trapezoid）。"""
    return (bottom + bottom + height * slope * 2) * height / 2.0


def trapezoid_expr(bottom: float, height: float, slope: float) -> str:
    """梯形面积的数值代入算式（§6.3 示例的同款形式）。"""
    if slope == 0:
        return f"{fmt(bottom)}×{fmt(height)}"
    return f"({fmt(bottom)}+{fmt(bottom)}+2×{fmt(height)}×{fmt(slope)})×{fmt(height)}/2"


def min_h(height: float, remaining: float) -> tuple[float, float]:
    """本层厚度与剩余深度（旧版 mscGroove.minH：层高 <0 表示吃掉全部剩余）。"""
    if remaining <= height or height < 0:
        return remaining, 0.0
    return height, remaining - height


def split_h_by_step(levels: list, depth: float) -> list[float]:
    """多级围护的分级标高（自槽底向上每级的累计高，旧版 splitHbyStep）。

    ``levels`` 为做法内的围护构件级列表（order_no 升序，levels[-1] 最深）；
    ``h < 0`` 的级与其余负值级均分 ``depth - 固定高合计``。
    """
    fixed_h = sum(max(level.h, 0.0) for level in levels)
    fixed_cnt = sum(1 for level in levels if level.h >= 0)
    result: list[float] = []
    height = 0.0
    for level in reversed(levels):
        if level.h >= 0:
            step_h = level.h
        elif len(levels) > fixed_cnt:
            step_h = (depth - fixed_h) / (len(levels) - fixed_cnt)
        else:
            step_h = depth
        height += step_h
        result.insert(0, max(0.0, height))
    return result


@dataclass
class _Segment:
    """挖方的一个等坡段（用于把连续梯形合并成一条算式）。

    ``breaks_before`` 为 True 表示本段之前发生过平台加宽（换级），
    不能与上一段合并成一条梯形。
    """

    bottom: float
    height: float
    slope: float
    breaks_before: bool = False


def foundation_thickness(pf) -> float:
    """换填总厚 mm（旧版 mcPcpFoundation.TiA）。"""
    return sum(replacement.h for replacement in pf.replacements)


def backfill_layers(pe, pf, at, size_h: float, depth: float, cushion_name: str) -> list[tuple[str, float, str]]:
    """分层回填列表（旧版 cal_groove 的 Backfill），返回 (定额键, 层厚 m, 说明)。"""
    layers: list[tuple[str, float, str]] = []
    for replacement in reversed(list(pf.replacements)):
        layers.append((f"换填|{replacement.name}|m3", mm2m(replacement.h), f"换填 {replacement.name} {fmt(mm2m(replacement.h))}m"))
    depth = max(0.0, depth)
    remaining = depth - mm2m(foundation_thickness(pf))

    height, remaining = min_h(mm2m(at.c1 + at.c2), remaining)
    layers.append((f"垫层|{cushion_name}|m3", height, "垫层"))
    height, remaining = min_h(size_h / 2 + mm2m(at.t - at.c2), remaining)
    layers.append((f"回填|{pe.dock_l}|m3", height, "坞膀下半"))
    height, remaining = min_h(size_h / 2 + mm2m(at.t), remaining)
    layers.append((f"回填|{pe.dock_h}|m3", height, "坞膀上半"))
    height, remaining = min_h(0.5, remaining)
    layers.append((f"回填|{pe.cover50}|m3", height, "管顶50cm"))
    height, remaining = min_h(depth - size_h - mm2m(foundation_thickness(pf) + at.t * 2 + at.c1) - 0.5, remaining)
    layers.append((f"回填|{pe.cover}|m3", height, "覆土"))
    return layers


def groove_width(at, size_b: float) -> float:
    """槽底宽度 m：沟槽宽度表为 0 时按 断面宽+2×(壁厚+工作面+加宽) 推算。"""
    if at.groove_b != 0:
        return at.groove_b
    return size_b + mm2m(at.t * 2 + at.a * 2 + at.workwidth * 2)


def cal_groove(pe, work, pf, at, size_b: float, size_h: float, depth: float, out: QDict) -> bool:
    """计算沟槽断面工程量（每延米），结果写入 ``out``。

    返回 False 表示没有产生任何土方（覆土不足 / 深度为 0）。
    """
    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    layers = backfill_layers(pe, pf, at, size_h, depth, cushion_name)
    bottom = groove_width(at, size_b)
    step_heights = split_h_by_step(list(work.levels), depth)
    if not step_heights:
        return False
    step = len(work.levels) - 1

    current = 0.0
    dig_key = f"开挖|{pe.excvt}|m3"
    dig_segments: list[_Segment] = []
    jump_pending = False
    for key, layer_h, note in layers:
        target = current + layer_h
        while True:
            delta = min(target, step_heights[step]) - current
            slope = level_slope(work.levels[step])
            area = trapezoid(bottom, delta, slope)
            expr = trapezoid_expr(bottom, delta, slope)
            out.add(key, area, expr, note)
            dig_segments.append(_Segment(bottom=bottom, height=delta, slope=slope, breaks_before=jump_pending))
            jump_pending = False
            current += delta
            bottom += delta * slope * 2
            if current == step_heights[step] and step > 0:
                step -= 1
                if step_heights[step] != step_heights[step + 1] and step_heights[step + 1] != 0:
                    bottom += work.levels[step].step_width * 2
                    jump_pending = True  # 平台加宽处断开，不与上一段合并
            if current - target >= -0.0001:
                break

    # 挖方 = 各层梯形之和；等坡且无平台的连续段合并成一条梯形算式（§6.2 的可读性简化）
    dig = out.add(dig_key, 0.0)
    dig.terms.clear()
    dig.value = 0.0
    index = 0
    while index < len(dig_segments):
        segment = dig_segments[index]
        total_h = segment.height
        index += 1
        while (
            index < len(dig_segments)
            and not dig_segments[index].breaks_before
            and dig_segments[index].slope == segment.slope
        ):
            total_h += dig_segments[index].height
            index += 1
        if total_h != 0:
            dig.add_term(
                trapezoid(segment.bottom, total_h, segment.slope),
                trapezoid_expr(segment.bottom, total_h, segment.slope),
            )
    if not dig.terms:
        out.discard(dig_key)
    return len(out) > 0


def level_slope(level) -> float:
    """围护级的放坡系数：A 参数显示名以“放坡系数”开头时取其值，否则 0（旧版约定）。"""
    component = level.components[0] if level.components else None
    if component is None:
        return 0.0
    for param in component.params:
        if param.key == "A" and param.value.split("|")[0].startswith("放坡系数"):
            from app.core.evaluator import evaluate_or_default

            return evaluate_or_default(param.value.split("|", 1)[1] if "|" in param.value else "")
    return 0.0
