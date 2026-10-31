"""沟槽土方 / 回填计算（复刻旧版 mscGroove.cal_groove）。

分层回填列表自底向上：换填（PF 换填层，倒序）→ 垫层 → 坞膀下半 → 坞膀上半 →
管顶 50cm → 覆土；每层按当前围护级别的放坡系数算梯形断面
``Trapezoid(B,H,slope) = (2B+2Hs)H/2``，同一层挖方与回填取同一面积。
多级围护按 splitHbyStep 的分级标高切换，切级时按平台宽度加宽底宽。

槽底宽 B（断面宽 + 2×(壁厚 + 工作面加宽 + 工作面)）、各层层厚与放坡系数
都以 :class:`Dim`（数值 + 算式）参与计算，算式不做预运算。**记法口径**：
几何量全程 mm 记法（``Dim.s=3``，图集 / 原则表值原样、用户 m 录入经
:func:`mm_of_m` 换算），梯形断面式为纯 mm² 算式，记录工程量时统一追加
``/10^6``（体积）、``/10^3``（面积），见 :mod:`app.core.calc.tracer`。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.calc.measures import AtlasDims, foundation_thickness
from app.core.calc.tracer import Dim, QDict, dim, dim_sum, fmt, mm, mm_of_m, raw_dim, scale_sum, wrap


def mm2m(value: float) -> float:
    """毫米 → 米（旧版 mscGroove.D10E3）；算式侧由 mm 记法统一记录（Dim.s=3）。"""
    return value / 1000.0


def trapezoid(bottom: float, height: float, slope: float) -> float:
    """梯形断面面积（旧版 mscGroove.Trapezoid）。"""
    return (bottom + bottom + height * slope * 2) * height / 2.0


def trapezoid_expr(bottom: Dim, height: Dim, slope: Dim) -> Dim:
    """梯形断面的代入算式（mm 记法）：``(2*B+2*H*放坡系数)*H/2``（直壁为 ``B*H``）。

    B 与 H 都带各自来源的算式（槽底宽由管径 / 图集 / 面宽原则推出），
    算式展开写全、不做预运算；B 只在算式里出现一次，避免长算式重复。
    返回 :class:`Dim`：``v`` 为每延米断面面积（m²），``e`` 为 mm² 记法算式
    （记法指数 = 底宽指数 + 高指数），记录工程量时统一 ``/10^6``。
    """
    h = wrap(height.e)
    b = wrap(bottom.e)
    if slope.v == 0:
        text = f"{b}*{h}"
    else:
        text = f"(2*{b}+2*{h}*{wrap(slope.e)})*{h}/2"
    return Dim(trapezoid(bottom.v, height.v, slope.v), text, (), bottom.s + height.s)


def widen(delta: Dim, slope: Dim) -> Dim:
    """放坡外扩量 ``2*Δ*放坡系数``（底宽随层高外扩，算式保留两个来源）。"""
    return Dim(
        delta.v * slope.v * 2,
        f"2*{wrap(delta.e)}*{wrap(slope.e)}",
        (),
        delta.s + slope.s,
    )


def _trapezoid_geometry(
    z0: float, height: float, bottom: float, slope_total: float
) -> tuple[float, float, float, float, float, float]:
    """梯形分项的断面范围：自槽底 [z0, z0+height]，底/顶全宽对称展开。

    ``slope_total`` 为两侧放坡系数之和（对称断面 = 2×放坡，不对称 = sL+sR）。
    返回 ``(h0, h1, l0, r0, l1, r1)``，l/r 相对本体内/槽中心（左负右正，m）。
    """
    h1 = z0 + height
    top = bottom + height * slope_total
    return (z0, h1, -bottom / 2.0, bottom / 2.0, -top / 2.0, top / 2.0)


def min_h(height: Dim, remaining: Dim) -> tuple[Dim, Dim]:
    """本层厚度与剩余深度（旧版 mscGroove.minH：层高 <0 表示吃掉全部剩余）。"""
    if remaining.v <= height.v or height.v < 0:
        return remaining, dim(0.0)
    return height, remaining - height


def split_h_by_step(levels: list, depth: Dim) -> list[Dim]:
    """多级围护的分级标高（自槽底向上每级的累计高，旧版 splitHbyStep）。

    ``levels`` 为做法内的围护构件级列表（order_no 升序，levels[-1] 最深）；
    ``h < 0`` 的级与其余负值级均分 ``depth - 固定高合计``（埋深算式随之进算式）。
    级高按 m 录入，进 mm 记法几何链经 :func:`mm_of_m` 换算。
    """
    fixed_h = dim_sum(*(mm_of_m(dim(level.h)) for level in levels if level.h >= 0))
    fixed_cnt = sum(1 for level in levels if level.h >= 0)
    result: list[Dim] = []
    height = mm(0.0)
    for level in reversed(levels):
        if level.h >= 0:
            step = mm_of_m(dim(level.h))
        elif len(levels) > fixed_cnt:
            step = (depth - fixed_h) / (len(levels) - fixed_cnt)
        else:
            step = depth
        height = height + step
        result.insert(0, height if height.v >= 0 else mm(0.0))
    return result


@dataclass
class _Segment:
    """挖方的一个等坡段（用于把连续梯形合并成一条算式）。

    ``note`` 为本段覆盖的分层说明（如 ``垫层``），合并时首尾相接成 ``垫层~坞膀上半``；
    ``breaks_before`` 为 True 表示本段之前发生过平台加宽（换级），
    不能与上一段合并成一条梯形。``z0``/``z1`` 为本段的自槽底标高范围（m），
    合并成一条挖方分项时取首段底到末段顶，供详情弹窗高亮断面范围。
    """

    bottom: Dim
    height: Dim
    slope: Dim
    note: str = ""
    breaks_before: bool = False
    z0: float = 0.0
    z1: float = 0.0


def backfill_layers(
    pp, pf, ad: AtlasDims, size_h: Dim, depth: Dim, cushion_name: str
) -> list[tuple[str, Dim, str]]:
    """分层回填列表（旧版 cal_groove 的 Backfill），返回 (定额键, 层厚, 说明)。

    换填层 / 垫层厚度取自 ``pf``（地基原则），坞膀与覆土的材质取自 ``pp``
    （挖填降水原则，v10 起挖填类型不再随左右围护分侧）。
    """
    layers: list[tuple[str, Dim, str]] = []
    for replacement in reversed(list(pf.replacements)):
        h = mm(replacement.h).named(
            "换填层厚", f"地基原则·换填 {replacement.name}"
        )
        layers.append((f"换填|{replacement.name}|m3", h, f"换填 {replacement.name} {fmt(h.v)}m"))
    total = depth if depth.v >= 0 else mm(0.0)
    remaining = total - foundation_thickness(pf)

    height, remaining = min_h(ad.c1 + ad.c2, remaining)
    height = height.named("垫层厚度", "垫层厚 C1 + 基础厚 C2")
    layers.append((f"垫层|{cushion_name}|m3", height, "垫层"))
    height, remaining = min_h(size_h / 2 + (ad.t - ad.c2), remaining)
    height = height.named("坞膀下半层厚", "断面高/2 + (壁厚−基础厚)")
    layers.append((f"回填|{pp.dock_l}|m3", height, "坞膀下半"))
    height, remaining = min_h(size_h / 2 + ad.t, remaining)
    height = height.named("坞膀上半层厚", "断面高/2 + 壁厚")
    layers.append((f"回填|{pp.dock_h}|m3", height, "坞膀上半"))
    height, remaining = min_h(mm(500), remaining)
    height = height.named("管顶50cm层厚", "管顶 50cm 范围")
    layers.append((f"回填|{pp.cover50}|m3", height, "管顶50cm"))
    cover = total - size_h - (foundation_thickness(pf) + ad.t * 2 + ad.c1) - mm(500)
    height, remaining = min_h(cover, remaining)
    height = height.named("覆土层厚", "计算深度−断面高−基础厚度−0.5")
    layers.append((f"回填|{pp.cover}|m3", height, "覆土"))
    return layers


def layer_roles(layers: list[tuple[str, Dim, str]]) -> list[tuple[str, int]]:
    """分层条目的统筹角色 ``(角色名, 自底向上的同角色序号)``。

    合槽"统一回填标高"按角色统筹：换填各层同属角色 ``换填``（按自底向上
    的出现序号区分），其余层角色 = 分层说明（垫层 / 坞膀下半 / 坞膀上半 /
    管顶50cm / 覆土）——同一角色在构件之间才被认作"同一层"参与取最浅标高，
    回填材质（定额键）差异不影响统筹。
    """
    roles: list[tuple[str, int]] = []
    counts: dict[str, int] = {}
    for key, _layer, note in layers:
        base = "换填" if key.startswith("换填|") else note
        index = counts.get(base, 0)
        counts[base] = index + 1
        roles.append((base, index))
    return roles


def groove_width(ad: AtlasDims, size_b: Dim) -> Dim:
    """槽底宽（mm 记法）：沟槽宽度表为 0 时按 断面宽+2×(壁厚+工作面加宽+工作面) 推算。

    几何链直接用本结果；围护等用户公式按 m 口径代入，用 :meth:`Dim.to_m` 派生。
    """
    if ad.groove_b.v != 0:
        return ad.groove_b.named("槽底宽", "面宽原则·沟槽宽度表")
    return (
        size_b + scale_sum((ad.t, ad.a, ad.workwidth), 2.0)
    ).named("槽底宽", "断面宽 + 2×(壁厚+工作面加宽+工作面)")


def cal_groove(
    pp, work, pf, ad: AtlasDims, size_b: Dim, size_h: Dim, depth: Dim, out: QDict
) -> bool:
    """计算沟槽断面工程量（每延米），结果写入 ``out``。

    返回 False 表示没有产生任何土方（覆土不足 / 深度为 0）。
    挖填类型（开挖土质 / 回填材质）取自 ``pp``（挖填降水原则），垫层与
    换填取自 ``pf``（地基原则）——v10 起均不再挂在围护原则下。
    """
    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    layers = backfill_layers(pp, pf, ad, size_h, depth, cushion_name)
    bottom = groove_width(ad, size_b)
    step_heights = split_h_by_step(list(work.levels), depth)
    if not step_heights:
        return False
    step = len(work.levels) - 1

    current = mm(0.0)
    dig_key = f"开挖|{pp.excvt}|m3"
    dig_segments: list[_Segment] = []
    jump_pending = False
    for key, layer, note in layers:
        target = current + layer
        clipped = False
        while True:
            step_top = step_heights[step]
            if target.v <= step_top.v:
                # 整层落在当前分级内：层厚就是该层本身（数值仍按旧版递推 float）
                delta = (
                    target - current
                    if clipped
                    else Dim(target.v - current.v, layer.e, (), layer.s)
                )
            else:
                delta = step_top - current
                clipped = True
            slope = level_slope(work.levels[step])
            area = trapezoid_expr(bottom, delta, slope)
            geometry = _trapezoid_geometry(current.v, delta.v, bottom.v, slope.v * 2)
            out.add(
                key,
                area.v,
                area,
                note,
                tags=bottom.tags + delta.tags + slope.tags,
                geometry=geometry,
            )
            dig_segments.append(
                _Segment(
                    bottom=bottom,
                    height=delta,
                    slope=slope,
                    note=note,
                    breaks_before=jump_pending,
                    z0=current.v,
                    z1=current.v + delta.v,
                )
            )
            jump_pending = False
            if target.v <= step_top.v:
                current = current + delta
            else:
                # 切级处 current 恰好到达分级标高：数值同旧版递推，算式直接取标高，
                # 避免 "(累计)+(标高−累计)" 这类未化简写法
                current = Dim(current.v + delta.v, step_top.e, (), step_top.s)
            bottom = (bottom + widen(delta, slope)).named(
                "槽底宽", "上一层底宽 + 2×层厚×放坡系数"
            )
            if current.v == step_top.v and step > 0:
                step -= 1
                if step_heights[step].v != step_heights[step + 1].v and step_heights[step + 1].v != 0:
                    bottom = (
                        bottom + mm_of_m(dim(work.levels[step].step_width)) * 2
                    ).named("槽底宽", "切级平台加宽")
                    jump_pending = True  # 平台加宽处断开，不与上一段合并
            if current.v - target.v >= -0.0001:
                break

    # 挖方 = 各层梯形之和；等坡且无平台的连续段合并成一条梯形算式（可读性简化），
    # 说明取该段覆盖的分层范围（首层~末层，只有一层时就写该层）
    dig = out.add(dig_key, 0.0)
    dig.terms.clear()
    dig.value = 0.0
    index = 0
    while index < len(dig_segments):
        segment = dig_segments[index]
        total = segment.height
        notes = [segment.note] if segment.note else []
        index += 1
        while (
            index < len(dig_segments)
            and not dig_segments[index].breaks_before
            and dig_segments[index].slope.v == segment.slope.v
        ):
            total = total + dig_segments[index].height
            if dig_segments[index].note:
                notes.append(dig_segments[index].note)
            index += 1
        if total.v != 0:
            # 连续段恰好铺满全槽时层厚就是沟槽深度，算式直接用埋深算式（含垫层调整）
            height = depth if abs(total.v - depth.v) < 1e-9 else total
            area = trapezoid_expr(segment.bottom, height, segment.slope)
            dig.add_term(
                area.v,
                area,
                _segment_note(notes),
                tags=segment.bottom.tags + height.tags + segment.slope.tags,
                geometry=_trapezoid_geometry(
                    segment.z0, total.v, segment.bottom.v, segment.slope.v * 2
                ),
            )
    if not dig.terms:
        out.discard(dig_key)
    return len(out) > 0


def _segment_note(notes: list[str]) -> str:
    """挖方段的说明：``垫层~坞膀上半``（只覆盖一层时就是该层名）。"""
    if not notes:
        return ""
    if len(notes) == 1 or notes[0] == notes[-1]:
        return notes[0]
    return f"{notes[0]}~{notes[-1]}"


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

        return raw_dim(expression, evaluate_or_default(expression)).named(
            "放坡系数", "围护原则·做法参数"
        )
    return dim(0.0)


# --------------------------------------------------------------------------- #
# 左右分设：不对称几何（两侧各自的围护做法，级标高取并集切段）
# --------------------------------------------------------------------------- #
def trapezoid_lr(bottom: float, height: float, slope_l: float, slope_r: float) -> float:
    """不对称梯形断面面积：``(2B+H*sL+H*sR)*H/2``；两侧直壁退化为 ``B*H``。"""
    if slope_l == 0 and slope_r == 0:
        return bottom * height
    return (2.0 * bottom + height * (slope_l + slope_r)) * height / 2.0


def trapezoid_lr_expr(bottom: Dim, height: Dim, slope_l: Dim, slope_r: Dim) -> Dim:
    """不对称梯形的代入算式（mm 记法）：直壁侧省略 ``H*s`` 项（与对称版同风格，不出 ``*0``）。"""
    h = wrap(height.e)
    b = wrap(bottom.e)
    if slope_l.v == 0 and slope_r.v == 0:
        text = f"{b}*{h}"
    else:
        terms = [f"2*{b}"]
        if slope_l.v != 0:
            terms.append(f"{h}*{wrap(slope_l.e)}")
        if slope_r.v != 0:
            terms.append(f"{h}*{wrap(slope_r.e)}")
        text = "(" + "+".join(terms) + f")*{h}/2"
    return Dim(
        trapezoid_lr(bottom.v, height.v, slope_l.v, slope_r.v),
        text,
        (),
        bottom.s + height.s,
    )


def widen_lr(delta: Dim, slope_l: Dim, slope_r: Dim) -> Dim:
    """不对称层间外扩 ``Δ*sL+Δ*sR``（直壁侧省略项）。"""
    if slope_l.v == 0 and slope_r.v == 0:
        return dim(0.0)
    parts: list[Dim] = []
    if slope_l.v != 0:
        parts.append(delta * slope_l)
    if slope_r.v != 0:
        parts.append(delta * slope_r)
    return dim_sum(*parts)


@dataclass
class _SideSegment:
    """不对称挖方的一个等坡段：每段左右各自的坡（合并判据 = 两坡都相等）。"""

    bottom: Dim
    height: Dim
    slope_l: Dim
    slope_r: Dim
    note: str = ""
    breaks_before: bool = False
    z0: float = 0.0
    z1: float = 0.0


def cal_groove_sided(
    pp,
    work_l,
    work_r,
    pf,
    ad: AtlasDims,
    size_b: Dim,
    size_h: Dim,
    depth: Dim,
    out: QDict,
    cushion_name: str | None = None,
) -> bool:
    """左右分设模式的沟槽断面工程量（每延米），结果写入 ``out``。

    与 :func:`cal_groove` 同构，区别在两侧各自的围护做法：级标高取**并集**切段，
    每段梯形按 ``(2B+H*sL+H*sR)*H/2``，切级时平台加宽只加发生切级的一侧。
    挖填类型取 ``pp``（挖填降水原则，v10 起不再分侧）；垫层材质与基础参数取
    ``pf``（地基原则），材质名由 ``cushion_name`` 显式传入。
    """
    if cushion_name is None:
        cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    layers = backfill_layers(pp, pf, ad, size_h, depth, cushion_name)
    bottom = groove_width(ad, size_b)
    heights_l = split_h_by_step(list(work_l.levels), depth)
    heights_r = split_h_by_step(list(work_r.levels), depth)
    if not heights_l or not heights_r:
        return False
    step_l = len(work_l.levels) - 1
    step_r = len(work_r.levels) - 1

    current = mm(0.0)
    dig_key = f"开挖|{pp.excvt}|m3"
    dig_segments: list[_SideSegment] = []
    jump_pending = False
    for key, layer, note in layers:
        target = current + layer
        clipped = False
        while True:
            top_l = heights_l[step_l]
            top_r = heights_r[step_r]
            # 并集切点：取两侧级标高中的较小者（其算式随被截的那侧进算式）
            step_top = top_l if top_l.v <= top_r.v else top_r
            if target.v <= step_top.v:
                delta = (
                    target - current
                    if clipped
                    else Dim(target.v - current.v, layer.e, (), layer.s)
                )
            else:
                delta = step_top - current
                clipped = True
            slope_l = level_slope(work_l.levels[step_l])
            slope_r = level_slope(work_r.levels[step_r])
            area = trapezoid_lr_expr(bottom, delta, slope_l, slope_r)
            geometry = _trapezoid_geometry(
                current.v, delta.v, bottom.v, slope_l.v + slope_r.v
            )
            out.add(
                key,
                area.v,
                area,
                note,
                tags=bottom.tags + delta.tags + slope_l.tags + slope_r.tags,
                geometry=geometry,
            )
            dig_segments.append(
                _SideSegment(
                    bottom=bottom,
                    height=delta,
                    slope_l=slope_l,
                    slope_r=slope_r,
                    note=note,
                    breaks_before=jump_pending,
                    z0=current.v,
                    z1=current.v + delta.v,
                )
            )
            jump_pending = False
            if target.v <= step_top.v:
                current = current + delta
            else:
                current = Dim(current.v + delta.v, step_top.e, (), step_top.s)
            bottom = (bottom + widen_lr(delta, slope_l, slope_r)).named(
                "槽底宽", "上一层底宽 + 左右放坡外扩"
            )
            if current.v == top_l.v and step_l > 0:
                step_l -= 1
                if heights_l[step_l].v != heights_l[step_l + 1].v and heights_l[step_l + 1].v != 0:
                    bottom = (
                        bottom + mm_of_m(dim(work_l.levels[step_l].step_width))
                    ).named("槽底宽", "左侧切级平台加宽")
                    jump_pending = True  # 平台加宽处断开，不与上一段合并
            if current.v == top_r.v and step_r > 0:
                step_r -= 1
                if heights_r[step_r].v != heights_r[step_r + 1].v and heights_r[step_r + 1].v != 0:
                    bottom = (
                        bottom + mm_of_m(dim(work_r.levels[step_r].step_width))
                    ).named("槽底宽", "右侧切级平台加宽")
                    jump_pending = True
            if current.v - target.v >= -0.0001:
                break

    # 挖方 = 各段不对称梯形之和；(sL,sR) 相等且无平台断点的连续段合并成一条
    dig = out.add(dig_key, 0.0)
    dig.terms.clear()
    dig.value = 0.0
    index = 0
    while index < len(dig_segments):
        segment = dig_segments[index]
        total = segment.height
        notes = [segment.note] if segment.note else []
        index += 1
        while (
            index < len(dig_segments)
            and not dig_segments[index].breaks_before
            and dig_segments[index].slope_l.v == segment.slope_l.v
            and dig_segments[index].slope_r.v == segment.slope_r.v
        ):
            total = total + dig_segments[index].height
            if dig_segments[index].note:
                notes.append(dig_segments[index].note)
            index += 1
        if total.v != 0:
            height = depth if abs(total.v - depth.v) < 1e-9 else total
            area = trapezoid_lr_expr(segment.bottom, height, segment.slope_l, segment.slope_r)
            dig.add_term(
                area.v,
                area,
                _segment_note(notes),
                tags=segment.bottom.tags + height.tags + segment.slope_l.tags + segment.slope_r.tags,
                geometry=_trapezoid_geometry(
                    segment.z0,
                    total.v,
                    segment.bottom.v,
                    segment.slope_l.v + segment.slope_r.v,
                ),
            )
    if not dig.terms:
        out.discard(dig_key)
    return len(out) > 0
