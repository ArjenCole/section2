"""合槽编组计算（父节点 / 子节点模型，见 docs/lr_enclosure_and_trench_group_design.md）。

断面从左到右的区间（每个区间归属一条构件）：

    [左边坡+左工作面·首构件左PE/自身PW] [构件1本体]
    [相邻区1·浅侧工作面 + 深侧放坡] [构件2本体] …
    [构件n本体] [右工作面+右边坡·末构件右PE/自身PW]

实现口径（等深 / 异深统一）：

* **父节点不持有围护 / 面宽原则**：父节点零工程量、零几何，只作合计视图；
  全部原则取子构件自己的。
* **逐构件宽度剖面**：每个构件是一条自槽底向上的分段线性宽度函数——
  本体恒宽；外边缘 = 工作面矩形 + 分级放坡剖面；相邻侧按**虚拟竖直墙**
  拆分：更深一侧为"深槽底→浅槽底"的内侧放坡 + 浅槽底以上等宽竖直条带，
  更浅 / 等深一侧为工作面矩形（首构件左边缘取 ``pe_left_name``、末构件
  右边缘取 ``pe_right_name``）。
* **按标高分层、每层梯形**：把该构件的回填分层界面（换填顶、垫层顶、
  坞膀下半顶、坞膀顶、管顶 50cm 顶、覆土顶）、各侧放坡剖面的全部分级 /
  平台折点（含相邻构件的槽底标高）合并成标高事件集；相邻事件之间宽度
  线性，单层断面面积用梯形 ``(w_下+w_上)/2*Δh`` 精确计算。放坡系数变化
  与平台跳变都正好落在事件边界上，因此每一层都是一个梯形。
* **回填正量 = 各层梯形面积按该构件自己的分层界面归类**（材质 / 换填取
  自身围护原则 PE / 自己的 PF）；挖方 = 同层面积之和进开挖定额键；逐管
  扣减（弓形 / 包封 / 箱涵）由 foundation 现状函数以同 key 负项合并。
* **围护量每面 ×1**（``sides=1``）：左边坡挂首构件（其左原则）、右边坡
  挂末构件（其右原则）、内侧坡挂深侧构件（其朝向该面的原则）；等深相邻
  面不出围护量。支撑行按公式类别（``支撑``）识别，按归属构件朝向该面的
  支撑勾选输出；做法档位与围护面共用同一个**含换填层厚度**的面深。
* **降水逐构件**（湿土排水 = 归属带宽 ×（槽深−1m）的简化断面）；特殊地基
  按归属带宽代入 width。
* **父节点零工程量**：全部输出挂在子构件名下，每构件量 × L_组（编组时
  校验组员数量一致）。

后续扩展：相邻侧的分界可由用户选择"按优先级取高优先级构件的围护原则"，
低优先级一侧用负坡向内让出侵入部分；宽度剖面与梯形积分已按"坡度可正可负"
实现，届时只需替换 ``_internal_side_profiles`` / ``_wall_profiles`` 的选择逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.calc import foundation, precipitation
from app.core.calc.engine import (
    ElementInput,
    atlas_dims,
    build_atlas_query,
    build_element_input,
    choice_work,
    component_quantities,
    component_side_quantities,
    workwidth_of,
    works_quantities,
)
from app.core.calc.groove import backfill_layers, layer_roles, level_slope, split_h_by_step
from app.core.calc.measures import AtlasDims, cushion_thickness as cushion_dim
from app.core.calc.measures import foundation_thickness as foundation_dim
from app.core.calc.tracer import Dim, QDict, dim, dim_min, dim_sum as _dim_sum, mm, mm_of_m, scale_sum, wrap
from app.core.models import base as orm
from app.core.models.models import (
    BACKFILL_UNIFIED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
    Element,
    SPLIT_CENTER_LINE,
    SPLIT_SPACING_MID,
    TrenchGroup,
)
from app.services.atlas import resolve_atlas


# --------------------------------------------------------------------------- #
# 宽度剖面：自构件槽底向上的分段线性宽度（Dim，算式不预运算）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _SlopeSegment:
    """一段等坡线：高度 ``t1`` 处宽 ``w1``，到 ``t2`` 按 ``slope`` 线性变化。

    ``slope`` 可为负（后续共享侧"负坡向内让出侵入"选项），宽度仍按线性插值。
    """

    t1: Dim
    w1: Dim
    slope: Dim
    t2: Dim

    def width_at(self, t: Dim) -> Dim:
        step = t - self.t1
        return self.w1 if step.v == 0 else self.w1 + self.slope * step


def _slope_profile(work, height: Dim) -> tuple[list[_SlopeSegment], Dim]:
    """放坡剖面段（高度自槽底向上）与坡顶外扩宽。

    级划分复用 :func:`groove.split_h_by_step`（levels[-1] 最靠近槽底）；平台宽
    取切级后靠地面那一级的 step_width（与 cal_groove 同口径）。
    """
    levels = list(work.levels)
    heights = split_h_by_step(levels, height)
    segments: list[_SlopeSegment] = []
    cum = dim(0.0)
    run = dim(0.0)
    for step in range(len(levels) - 1, -1, -1):
        top = heights[step]
        segment = top - cum
        if segment.v > 0:
            slope = level_slope(levels[step])
            segments.append(_SlopeSegment(t1=cum, w1=run, slope=slope, t2=top))
            run = run + segment * slope
            cum = top
        if step > 0 and top.v != 0 and heights[step - 1].v != top.v:
            run = run + mm_of_m(dim(levels[step - 1].step_width))
    return segments, run


def _profile_segments(work, height: Dim) -> list[_SlopeSegment]:
    """放坡剖面段，覆盖 [0, height]（高度自构件槽底向上）。

    分级 / 平台沿用 :func:`_slope_profile`；固定级高之和与目标高度不一致时，
    超出部分截断、不足部分按最后一段坡度续到目标高度，保证每侧剖面都完整
    覆盖构件高度（分层梯形不会出现缺口或重叠）。
    """
    if height.v <= 0:
        return []
    segments, _run = _slope_profile(work, height)
    if all(segment.slope.v == 0 and segment.w1.v == 0 for segment in segments):
        return []  # 桩类 / 直壁：没有外扩宽度，不占归属宽
    result: list[_SlopeSegment] = []
    for segment in segments:
        if segment.t1.v >= height.v - 1e-9:
            break
        if segment.t2.v > height.v + 1e-9:
            result.append(_SlopeSegment(segment.t1, segment.w1, segment.slope, height))
            return result
        result.append(segment)
    if not result:
        return [_SlopeSegment(dim(0.0), dim(0.0), dim(0.0), height)]
    last = result[-1]
    if last.t2.v < height.v - 1e-9:
        result.append(
            _SlopeSegment(last.t2, last.width_at(last.t2), last.slope, height)
        )
    return result


def _rect_segments(width: Dim, depth: Dim) -> list[_SlopeSegment]:
    """恒宽区（本体 / 工作面）的剖面段。"""
    if depth.v <= 0 or width.v == 0:
        return []
    return [_SlopeSegment(dim(0.0), width, dim(0.0), depth)]


def _outer_side_profiles(work, depth: Dim, workface: Dim) -> list[list[_SlopeSegment]]:
    """合槽外边缘一侧：工作面矩形 + 分级放坡剖面（两个宽度贡献相加）。"""
    profiles: list[list[_SlopeSegment]] = []
    rect = _rect_segments(workface, depth)
    if rect:
        profiles.append(rect)
    slope = _profile_segments(work, depth)
    if slope:
        profiles.append(slope)
    return profiles


def _internal_side_profiles(
    work, depth: Dim, shallow: Dim, workface: Dim
) -> list[list[_SlopeSegment]]:
    """相邻侧（深侧）：工作面矩形 + 深槽底放坡到浅槽底 + 以上等宽竖直条带。

    返回的剖面覆盖 [0, depth]；桩类 / 直壁的 ``run`` 为 0，只剩工作面矩形。
    工作面是深侧构件在共享侧自己的施工面，坡从工作面外缘起算。
    """
    profiles: list[list[_SlopeSegment]] = []
    rect = _rect_segments(workface, depth)
    if rect:
        profiles.append(rect)
    delta = depth - shallow
    if delta.v <= 0:
        return profiles
    segments = _profile_segments(work, delta)
    if not segments:
        return profiles
    run = segments[-1].width_at(delta)
    if depth.v > delta.v + 1e-9:
        segments = segments + [_SlopeSegment(delta, run, dim(0.0), depth)]
    profiles.append(segments)
    return profiles


def _wall_profiles(workface: Dim, depth: Dim) -> list[list[_SlopeSegment]]:
    """相邻侧（浅侧 / 等深）：虚拟竖直围护，只有工作面矩形。"""
    rect = _rect_segments(workface, depth)
    return [rect] if rect else []


def _unique_dims(values: list[Dim]) -> list[Dim]:
    """按数值去重并升序（同一数值保留先出现的算式）。"""
    result: list[Dim] = []
    for value in sorted(values, key=lambda item: item.v):
        if result and abs(value.v - result[-1].v) <= 1e-9:
            continue
        result.append(value)
    return result


def _segment_for_interval(
    profile: list[_SlopeSegment], lo: Dim, hi: Dim
) -> _SlopeSegment | None:
    """找出覆盖整个 [lo, hi] 的段；跳变处上段用于上方、下段用于下方。"""
    for segment in profile:
        if segment.t1.v <= lo.v + 1e-9 and segment.t2.v >= hi.v - 1e-9:
            return segment
    return None


def _width_and_slope_for_interval(
    profiles: list[list[_SlopeSegment]], lo: Dim, hi: Dim, height: Dim
) -> tuple[Dim, Dim]:
    """区间下沿的构件总宽与各侧坡高项之和。

    返回 ``(W_下, Σ(H*s))``；线性宽度满足 ``W_上 = W_下 + Σ(s)*Δh``，因此
    梯形面积写成 ``(2*W_下 + Σ(H*s))/2*Δh``——与非合槽构件的
    ``trapezoid_lr_expr`` 同形，下底只出现一次（``2*下底``）。
    """
    low = dim(0.0)
    slope_terms = dim(0.0)
    for profile in profiles:
        segment = _segment_for_interval(profile, lo, hi)
        if segment is None:
            continue
        low = low + segment.width_at(lo)
        if segment.slope.v != 0:
            slope_terms = slope_terms + segment.slope * height
    return low, slope_terms


def _as_dim(value: "Dim | float") -> Dim:
    """普通数字 → Dim（断面图等浮点调用方复用同一套剖面函数）。"""
    return value if isinstance(value, Dim) else dim(value)


def _internal_run(work, h_deep: "Dim | float", h_shallow: "Dim | float") -> Dim:
    """内侧放坡的水平投影（Dim）：深侧槽底放坡到浅侧槽底的总外扩宽。

    按做法逐级累加（含切级平台），桩类为 0（竖直隔断）；浮点入参按 m 桥接。
    """
    deep, shallow = mm_of_m(_as_dim(h_deep)), mm_of_m(_as_dim(h_shallow))
    delta = deep - shallow
    if delta.v <= 0 or work is None:
        return mm(0.0)
    _segments, run = _slope_profile(work, delta)
    return run


def _slope_points(work, depth: float) -> list[tuple[float, float]]:
    """断面图用边坡折线 (绝对深度, 外扩宽 m)：浮点坐标，供 section_view 绘制。

    浮点深度按 m 桥接成 mm 记法进剖面函数（内部只取 ``.v`` 浮点）。
    """
    segments, _run = _slope_profile(work, mm_of_m(dim(depth)))
    points: list[tuple[float, float]] = [(depth, 0.0)]
    for segment in segments:
        points.append((depth - segment.t1.v, segment.w1.v))
        points.append(
            (
                depth - segment.t2.v,
                segment.w1.v + segment.slope.v * (segment.t2.v - segment.t1.v),
            )
        )
    return points


# --------------------------------------------------------------------------- #
# 虚拟竖线分界（管中心分隔 / 间距平分分隔）：分界自起坡点移到锚点中点
# --------------------------------------------------------------------------- #
def _spacing_anchor_half(member: "_Member") -> Dim:
    """间距平分分隔：构件共享侧「间距计算起始点」到本体中心的半宽。

    混凝土结构（包封 / 箱涵 / 管廊）取结构本体外包半宽；管道有混凝土基础的
    取基础外皮半宽；砂基础管道取管外皮半径（外径 / 2，壁厚含用户覆盖值）。
    """
    info = member.info
    if info.category in (CATEGORY_ENCASED, CATEGORY_BOX_CULVERT, CATEGORY_GALLERY):
        return info.size_b_dim / 2
    if info.pf is not None and info.pf.con_found:
        return member.base_width / 2
    return member.ad.od / 2


def _boundary_splits(
    snapshots: list["_Member"], pairs: list["_Pair"], split_mode: str
) -> list[_CenterSplit]:
    """逐相邻面计算虚拟竖线分界（管中心分隔 / 间距平分分隔）的位移与条带归属。

    分界线 = 相邻两构件分界锚点的水平中点：管中心分隔的锚点是构件本体中心
    （管道取管中心、混凝土构件取左右外包边线中点，都等于本体外皮宽的中点）；
    间距平分分隔的锚点是共享侧「间距计算起始点」（砼基础管道 = 基础共享侧
    边线、砂基础管道 = 管外皮共享侧切线、混凝土结构 = 结构本体共享侧最外侧
    边线）。相对起坡点分界的位移 ``δ = (锚点中点) − (起坡点)``，右正；分界
    移向的一侧获得条带（``gainer``），另一侧让出（``loser``）；位移为 0 的
    面不产生条带。
    """
    n = len(snapshots)
    spacing = split_mode == SPLIT_SPACING_MID
    left_anchors: list[Dim] = []  # 各构件在其右侧相邻面上的分界锚点
    right_anchors: list[Dim] = []  # 各构件在其左侧相邻面上的分界锚点
    walls: list[Dim] = []
    centers: list[Dim] = []  # 各构件本体中心的 x（自槽平底左缘起算）
    cursor = dim(0.0)
    for i, member in enumerate(snapshots):
        left_ext = snapshots[0].work_width if i == 0 else pairs[i - 1].right_width
        right_ext = member.work_width if i == n - 1 else pairs[i].left_width
        base_left = cursor + left_ext
        base_right = base_left + member.base_width
        center = base_left + member.base_width / 2
        centers.append(center)
        half = _spacing_anchor_half(member) if spacing else dim(0.0)
        right_anchors.append(center - half)
        left_anchors.append(center + half)
        if i < n - 1:
            walls.append(base_right + pairs[i].left_width)  # 起坡点分界（同断面图虚拟墙）
        cursor = base_right + right_ext

    splits: list[_CenterSplit] = []
    for i in range(n - 1):
        delta = (left_anchors[i] + right_anchors[i + 1]) / 2 - walls[i]
        if abs(delta.v) <= 1e-9:
            continue
        h_left, h_right = snapshots[i].depth.v, snapshots[i + 1].depth.v
        delta_h = (
            snapshots[i + 1].depth - snapshots[i].depth
            if h_right > h_left
            else snapshots[i].depth - snapshots[i + 1].depth
        )
        profile: tuple[_SlopeSegment, ...] = ()
        run_max = dim(0.0)
        if pairs[i].work is not None and delta_h.v > 1e-9:
            segments = _profile_segments(pairs[i].work, delta_h)
            if segments:
                profile = tuple(segments)
                run_max = segments[-1].width_at(delta_h)
        offset = delta if delta.v > 0 else -delta
        gainer, loser = (i, i + 1) if delta.v > 0 else (i + 1, i)
        splits.append(
            _CenterSplit(
                pair_index=i,
                offset=offset,
                gainer=gainer,
                loser=loser,
                shallow_depth=dim_min(snapshots[i].depth, snapshots[i + 1].depth),
                delta_h=delta_h,
                profile=profile,
                run_max=run_max,
                wall_x=walls[i].v,
                gainer_center_x=centers[gainer].v,
            )
        )
    return splits


def _center_deduction(split: _CenterSplit, member: "_Member") -> list[_SlopeSegment]:
    """管中心分隔下让条带一方（``loser``）的宽度扣减剖面（负宽并入分层积分）。

    让方更深时：坡区高度内扣 ``max(0, offset − gap)``（gap = 起坡点到内侧坡
    边缘的水平距，自深槽底的 run_max 向上减到 0），浅槽底以上扣恒定 offset；
    让方更浅 / 等深时全槽扣恒定 offset。扣减面积与获方的条带项严格相等，
    整槽挖填量守恒。
    """
    offset = split.offset
    segments: list[_SlopeSegment] = []
    own_delta = member.depth - split.shallow_depth  # 让方槽底到浅槽底的高差
    if own_delta.v > 1e-9:  # 让方更深：坡区内逐段扣楔形
        if not split.profile:
            # 桩类 / 直壁：内侧坡无外扩，坡区整段扣恒定 offset
            segments.append(_SlopeSegment(dim(0.0), -offset, dim(0.0), own_delta))
        else:
            for segment in split.profile:
                gap_lo = split.run_max - segment.width_at(segment.t1)
                gap_hi = split.run_max - segment.width_at(segment.t2)
                ded_lo = offset - gap_lo
                ded_hi = offset - gap_hi
                if ded_hi.v <= 1e-9:
                    continue  # 整段尚未切到分界线：不扣
                if ded_lo.v >= -1e-9:
                    segments.append(
                        _SlopeSegment(segment.t1, -ded_lo, -segment.slope, segment.t2)
                    )
                else:
                    # 段内切入坡面：切点以下不扣，以上按同坡扣到段顶
                    crossing = segment.t1 + (-ded_lo) / (ded_hi - ded_lo) * (
                        segment.t2 - segment.t1
                    )
                    segments.append(
                        _SlopeSegment(crossing, dim(0.0), -segment.slope, segment.t2)
                    )
    if member.depth.v > own_delta.v + 1e-9:
        segments.append(_SlopeSegment(own_delta, -offset, dim(0.0), member.depth))
    return segments


def _wedge_area(split: _CenterSplit, lo: Dim, hi: Dim) -> Dim | None:
    """坡区楔形在高度带 [lo, hi]（自深侧槽底起算）内的面积。

    楔形 = 分界线与内侧坡之间、浅槽底以下的条带（起坡点分界下原属深侧、
    管中心分隔下划给浅侧的部分），面积 = ∫ max(0, offset − gap) dh。带内
    坡面为一段等坡线时是梯形；分界线在带内切入坡面时是三角形
    ``w²/(2×放坡系数)``。返回 None 表示该带与坡区不相交或不产生楔形。
    """
    if hi.v <= 1e-9 or lo.v >= split.delta_h.v - 1e-9:
        return None
    top = hi if hi.v <= split.delta_h.v else split.delta_h
    bottom = lo if lo.v >= 0 else dim(0.0)
    if top.v - bottom.v <= 1e-9:
        return None
    if not split.profile:
        return split.offset * (top - bottom)  # 桩类 / 直壁：坡面竖直，整带都是楔形
    segment = _segment_for_interval(list(split.profile), bottom, top)
    if segment is None:
        return None
    width_lo = split.offset - (split.run_max - segment.width_at(bottom))
    width_hi = split.offset - (split.run_max - segment.width_at(top))
    height = top - bottom
    if width_hi.v <= 1e-9:
        return None  # 整带仍在坡面之外：分界未切入坡区
    if width_lo.v >= -1e-9:
        return (width_lo + width_hi) * height / 2
    return width_hi * width_hi / (2 * segment.slope)


# --------------------------------------------------------------------------- #
# 构件快照与总入口
# --------------------------------------------------------------------------- #
@dataclass
class _Member:
    """合槽成员（子节点）的计算快照。"""

    element: Element
    info: ElementInput
    ad: AtlasDims
    pe_r: object  # 自身围护原则（右 → 左 → 库首条；与几何侧原则分开）
    depth: Dim  # 槽底深 H_i（埋深 + 换填 + 壁厚 + 垫层）
    base_width: Dim  # 基础外皮宽 b_i（= 单管槽底宽去掉两侧工作面）
    work_width: Dim  # 自身面宽原则按自身管径查到的单侧工作面宽
    profiles: list[list[_SlopeSegment]] = field(default_factory=list)
    #: 左右分侧的剖面（与 ``profiles`` 同内容分侧存放）：分项几何的左右缘
    #: 按"本体半宽 + 该侧外扩"精确计算，供详情弹窗在整槽断面图上高亮
    profiles_left: list[list[_SlopeSegment]] = field(default_factory=list)
    profiles_right: list[list[_SlopeSegment]] = field(default_factory=list)
    flat_width: Dim = field(default_factory=lambda: dim(0.0))  # 平面归属带宽（降水 / 特殊地基代入用）
    #: 回填分层带 (定额键, 下界, 上界, 层厚, 说明)，高度自槽底起算；
    #: 独立 / 统一回填标高两种口径下内容不同（见 _member_bands / _unified_member_bands）
    bands: list[tuple[str, Dim, Dim, Dim, str]] = field(default_factory=list)


@dataclass(frozen=True)
class _CenterSplit:
    """虚拟竖线分界（管中心分隔 / 间距平分分隔）的一个相邻面。

    分界自深侧起坡点移到两构件分界锚点的水平中点。分界位移扫过的竖直条带
    归 ``gainer``（分界移向的一侧）：浅槽底以上是宽 ``offset`` 的矩形条带；
    让出方（``loser``）更深时，浅槽底以下的坡区内还有分界线与内侧坡之间的
    楔形一并划给获方。让出方在分层积分里扣减（:func:`_center_deduction`），
    获方把条带作为独立项加入（"分左右两侧分别计算工程量再加起来"）。
    """

    pair_index: int
    offset: Dim  # |δ|：分界线相对起坡点的水平位移（米）
    gainer: int  # 获得条带一侧的成员下标
    loser: int  # 让出条带一侧的成员下标
    shallow_depth: Dim  # 两侧较浅的槽底深（矩形条带的下缘标高）
    delta_h: Dim  # 相邻面的槽底高差（等深为 0）
    profile: tuple[_SlopeSegment, ...]  # 深侧内侧坡的放坡剖面段（覆盖 [0, delta_h]）
    run_max: Dim  # 剖面末端外扩宽（坡区楔形 gap 的基准；直壁 / 等深为 0）
    #: 起坡点分界的 x（自槽平底左缘起算，m）：条带 = [wall_x, wall_x±offset]
    wall_x: float = 0.0
    #: 获方本体中心的 x（同一原点）：条带几何换算成相对获方本体中心
    gainer_center_x: float = 0.0


@dataclass
class _Pair:
    """相邻两构件的几何口径（规则 4 / 5 / 7）。"""

    deep: _Member | None  # 更深一侧；None = 等深
    run: Dim  # 深侧放坡水平投影（m）；等深为 0
    work: object | None  # 深侧内侧坡做法
    left_width: Dim  # 左构件在该相邻面的归属宽（浅侧 = 工作面，深侧 = 工作面 + 放坡投影）
    right_width: Dim  # 右构件在该相邻面的归属宽


def _side_name(element: Element, side: str) -> str:
    """构件的左 / 右围护原则名；分设占位 ``pe_name`` 不参与几何。"""
    if side == "left":
        return element.pe_left_name or ("" if element.pe_name == "左右分设" else element.pe_name)
    return element.pe_right_name or ("" if element.pe_name == "左右分设" else element.pe_name)


def _resolve_by_name(session, model, name: str | None):
    from app.core.calc.engine import lookup_principle

    if not name or name == "-":
        return None
    return lookup_principle(session, model, name)


def _first_of(session, model):
    from app.core.calc.engine import first_principle

    return first_principle(session, model)


def _resolve_member(
    session, element: Element, *, require_amount: bool = True
) -> tuple[_Member | None, str | None]:
    """单个成员的计算快照；返回 (快照, 错误说明)。

    ``require_amount=False`` 时数量为 0 也照常生成快照：围护原则 tab 的
    左右侧可编辑状态只取决于相邻构件的槽底深度，与合槽工程量无关。
    """
    from app.core.models.models import (
        PcpEnclosure,
        PcpFoundation,
        PcpPrecipitation,
        PcpWidth,
    )

    pe_side = (
        _resolve_by_name(session, PcpEnclosure, _side_name(element, "right"))
        or _resolve_by_name(session, PcpEnclosure, _side_name(element, "left"))
        or _first_of(session, PcpEnclosure)
    )
    pf = _resolve_by_name(session, PcpFoundation, element.pf_name) or _first_of(session, PcpFoundation)
    pp = _resolve_by_name(session, PcpPrecipitation, element.pp_name) or _first_of(session, PcpPrecipitation)
    pw = _resolve_by_name(session, PcpWidth, element.pw_name) or _first_of(session, PcpWidth)
    if pe_side is None or pf is None or pp is None or pw is None:
        return None, "缺少围护 / 地基 / 降水 / 面宽原则。"
    info = build_element_input(element, pe_side, pf, pp, pw)
    if require_amount and info.amount == 0:
        return None, "数量为 0，未生成工程量。"
    # v10 起图集 / 基础参数取地基原则 pf（不再按左右围护分侧）
    material_pe = info.pe or pe_side
    at = resolve_atlas(build_atlas_query(info, pf, pw))
    ad = atlas_dims(info, at)
    if ad.c1.v == 0:
        ad = ad.replace(c1=cushion_dim(pf))
    # 成员几何一律 mm 记法（与单构件几何链同口径）；用户公式路径用 to_m 派生
    depth = mm_of_m(info.depth_dim) + foundation_dim(pf) + ad.t + ad.c1
    base_width = info.size_b_dim + scale_sum((ad.t, ad.a), 2.0)
    work_width = mm(workwidth_of(pw, info))
    return (
        _Member(
            element=element,
            info=info,
            ad=ad,
            pe_r=material_pe,
            depth=depth,
            base_width=base_width,
            work_width=work_width,
        ),
        None,
    )


def member_depths(group: TrenchGroup) -> dict[int, float]:
    """组内各构件的实际槽底深度（埋深 + 基础 + 壁厚 + 垫层）；算不出的跳过。"""
    session = orm.session()
    depths: dict[int, float] = {}
    for element in sorted(group.members, key=lambda item: (item.order_no, item.id)):
        member, _error = _resolve_member(session, element, require_amount=False)
        if member is not None:
            depths[element.id] = member.depth.v
    return depths


def group_side_plan(group: TrenchGroup) -> dict[int, tuple[bool, bool]]:
    """组内每条构件的 (左侧可编辑, 右侧可编辑)。

    * 首构件左侧 / 末构件右侧恒可编辑（合槽外边缘）；
    * 其余侧只有**比相邻构件更深**时才可编辑（深侧放坡原则）；
    * 等深 / 更浅的一侧围护强制 "-"（规则 4 / 5）。
    """
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    depths = member_depths(group)
    n = len(members)
    plan: dict[int, tuple[bool, bool]] = {}
    for index, element in enumerate(members):
        depth = depths.get(element.id)
        left_active = True
        if index > 0:
            neighbor = depths.get(members[index - 1].id)
            left_active = depth is None or neighbor is None or depth > neighbor + 1e-9
        right_active = True
        if index < n - 1:
            neighbor = depths.get(members[index + 1].id)
            right_active = depth is None or neighbor is None or depth > neighbor + 1e-9
        plan[element.id] = (left_active, right_active)
    return plan


def compute_group(group: TrenchGroup) -> tuple[dict[int, QDict], dict[int, str]]:
    """计算一个合槽组：返回 (构件 id → 工程量, 构件 id → 错误说明)。

    组员按 order_no 从左到右；父节点不参与（零工程量、无围护 / 面宽原则）。
    原则缺失 / 无做法时整组带错误说明，错误字符串挂在行上展示。
    """
    from app.core.models.models import PcpEnclosure

    session = orm.session()
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    results: dict[int, QDict] = {}
    errors: dict[int, str] = {}
    if len(members) < 2:
        for member in members:
            errors[member.id] = "合槽组至少需要两条构件。"
        return results, errors

    # 逐成员快照：原则一律取子构件自己的（父节点不持有原则）
    snapshots: list[_Member] = []
    for element in members:
        member, error = _resolve_member(session, element)
        if member is None:
            errors[element.id] = error or "无效成员。"
        else:
            snapshots.append(member)
    if len(snapshots) != len(members):
        for element in members:
            errors.setdefault(element.id, "合槽组存在无效成员，整组未计算。")
        return results, errors

    n = len(snapshots)
    # 边缘（规则 3）：左边坡 = 首构件左原则；右边坡 = 末构件右原则
    first, last = snapshots[0], snapshots[n - 1]
    pe_left = _resolve_by_name(session, PcpEnclosure, _side_name(first.element, "left")) or _first_of(
        session, PcpEnclosure
    )
    pe_right = _resolve_by_name(session, PcpEnclosure, _side_name(last.element, "right")) or _first_of(
        session, PcpEnclosure
    )
    work_left = choice_work(pe_left, first.depth.v) if pe_left is not None else None
    work_right = choice_work(pe_right, last.depth.v) if pe_right is not None else None
    if work_left is None or work_right is None:
        for member in snapshots:
            errors[member.element.id] = "边缘围护原则没有任何围护分级。"
        return results, errors

    # 相邻区（规则 4 / 5）：等深 → 两侧均为 "-"；异深 → 深侧选原则放坡
    pairs: list[_Pair] = []
    for i in range(n - 1):
        left, right = snapshots[i], snapshots[i + 1]
        h_left, h_right = left.depth.v, right.depth.v
        if abs(h_right - h_left) <= 1e-9:
            pairs.append(
                _Pair(
                    deep=None,
                    run=dim(0.0),
                    work=None,
                    left_width=left.work_width,
                    right_width=right.work_width,
                )
            )
            continue
        if h_right > h_left:  # 右深：用右构件的左侧原则
            deep, shallow = right, left
            deep_pe = _resolve_by_name(
                session, PcpEnclosure, _side_name(deep.element, "left")
            ) or _first_of(session, PcpEnclosure)
        else:  # 左深：用左构件的右侧原则
            deep, shallow = left, right
            deep_pe = _resolve_by_name(
                session, PcpEnclosure, _side_name(deep.element, "right")
            ) or _first_of(session, PcpEnclosure)
        delta = abs(h_right - h_left)
        work = choice_work(deep_pe, delta) if deep_pe is not None else None
        if work is None:
            for member in snapshots:
                errors[member.element.id] = "深侧围护原则没有任何围护分级。"
            return results, errors
        run = _internal_run(work, deep.depth, shallow.depth)
        if h_right > h_left:
            pairs.append(
                _Pair(
                    deep=deep,
                    run=run,
                    work=work,
                    left_width=left.work_width,
                    right_width=deep.work_width + run,
                )
            )
        else:
            pairs.append(
                _Pair(
                    deep=deep,
                    run=run,
                    work=work,
                    left_width=deep.work_width + run,
                    right_width=right.work_width,
                )
            )

    # 逐构件的宽度剖面 + 平面归属带宽（规则 6：工作面宽用自己的 PW）
    for i, member in enumerate(snapshots):
        member.profiles = []
        member.profiles_left = []
        member.profiles_right = []
        base = _rect_segments(member.base_width, member.depth)
        if base:
            member.profiles.append(base)
        if i == 0:
            left = _outer_side_profiles(work_left, member.depth, member.work_width)
            member.profiles += left
            member.profiles_left += left
        else:
            pair = pairs[i - 1]
            if pair.deep is member:  # 自身更深：左侧内侧放坡
                left = _internal_side_profiles(
                    pair.work, member.depth, snapshots[i - 1].depth, member.work_width
                )
            else:  # 自身更浅 / 等深：左侧虚拟竖直围护
                left = _wall_profiles(member.work_width, member.depth)
            member.profiles += left
            member.profiles_left += left
        if i == n - 1:
            right = _outer_side_profiles(work_right, member.depth, member.work_width)
            member.profiles += right
            member.profiles_right += right
        else:
            pair = pairs[i]
            if pair.deep is member:  # 自身更深：右侧内侧放坡
                right = _internal_side_profiles(
                    pair.work, member.depth, snapshots[i + 1].depth, member.work_width
                )
            else:  # 自身更浅 / 等深：右侧虚拟竖直围护
                right = _wall_profiles(member.work_width, member.depth)
            member.profiles += right
            member.profiles_right += right
        flat = member.base_width
        if i == 0:
            flat = flat + member.work_width
        else:
            flat = flat + pairs[i - 1].right_width
        if i == n - 1:
            flat = flat + member.work_width
        else:
            flat = flat + pairs[i].left_width
        member.flat_width = flat

    # 虚拟竖线分界（管中心分隔 / 间距平分分隔）：分界移到锚点中点。让出条带
    # 的一方在剖面里扣减（挖填随分层积分同步减少），平面归属带宽随分界位移调整
    splits: list[_CenterSplit] = []
    if group.split_mode in (SPLIT_CENTER_LINE, SPLIT_SPACING_MID):
        splits = _boundary_splits(snapshots, pairs, group.split_mode)
        for split in splits:
            loser = snapshots[split.loser]
            deduction = _center_deduction(split, loser)
            loser.profiles.append(deduction)
            # 分侧剖面同步扣减：分项几何的左右缘才能反映分隔
            #（否则高亮色块仍按起坡点口径显示）
            if split.loser == split.pair_index:  # 让方在 pair 左侧：扣自己的右缘
                loser.profiles_right.append(deduction)
            else:  # 让方在 pair 右侧：扣自己的左缘
                loser.profiles_left.append(deduction)
            snapshots[split.gainer].flat_width = snapshots[split.gainer].flat_width + split.offset
            loser.flat_width = loser.flat_width - split.offset

    # 回填分层带：独立回填标高 = 各构件自己的分层界面（现状口径）；
    # 统一回填标高 = 每层取组内各构件该层顶的最浅标高
    if group.backfill_mode == BACKFILL_UNIFIED:
        interfaces = _unified_interfaces(snapshots)
        for member in snapshots:
            member.bands = _unified_member_bands(member, interfaces)
    else:
        for member in snapshots:
            member.bands = _member_bands(member)

    # 挖方 / 回填（按标高分层、每层梯形）
    filled: set[int] = set()
    for member in snapshots:
        out = QDict()
        if _member_dig_fill(member, out, member.bands):
            filled.add(member.element.id)
        else:
            errors[member.element.id] = errors.get(member.element.id) or "覆土不足或分层无效，未生成工程量。"
        results[member.element.id] = out

    # 虚拟竖线分界（管中心分隔 / 间距平分分隔）：获方把分界条带作为独立项
    # 加进来（矩形条带按自己的分层带摊入；获方更浅时坡区楔形按让方=深侧的
    # 分层带摊入），挖方同步累加；说明后缀随所选方式
    for split in splits:
        gainer = snapshots[split.gainer]
        if gainer.element.id not in filled or not gainer.bands:
            continue
        loser = snapshots[split.loser]
        out = results[gainer.element.id]
        dig_key = f"开挖|{gainer.info.pp.excvt}|m3"
        suffix = f"·{group.split_mode}"
        # 条带 x 范围（相对获方本体中心，m）：起坡点分界与新分界之间的转移带
        if split.gainer == split.pair_index:  # 获方在 pair 左侧：条带在分界右侧
            x_left, x_right = split.wall_x, split.wall_x + split.offset.v
        else:  # 获方在 pair 右侧：条带在分界左侧
            x_left, x_right = split.wall_x - split.offset.v, split.wall_x
        strip_left = x_left - split.gainer_center_x
        strip_right = x_right - split.gainer_center_x
        # 矩形条带：浅槽底以上的竖直条带，按获方自己的分层带摊入
        rect_lo = gainer.depth - split.shallow_depth
        for key, lo, hi, _layer, note in gainer.bands:
            band_lo = lo if lo.v >= rect_lo.v - 1e-9 else rect_lo
            if hi.v - band_lo.v <= 1e-9:
                continue
            area = split.offset * (hi - band_lo)
            geometry = (band_lo.v, hi.v, strip_left, strip_right, strip_left, strip_right)
            out.add(key, area.v, area, f"{note}{suffix}", tags=area.tags, geometry=geometry)
            out.add(dig_key, area.v, area, f"{note}{suffix}", tags=area.tags, geometry=geometry)
        # 坡区楔形：仅当获方更浅（条带在获方槽底以下），按深侧的分层带摊入
        if gainer.depth.v < loser.depth.v - 1e-9:
            for key, lo, hi, _layer, note in loser.bands:
                area = _wedge_area(split, lo, hi)
                if area is None or area.v == 0:
                    continue
                # 楔形自深侧槽底起算，换算到获方槽底（高差 delta_h）后为负高度
                geometry = (
                    lo.v - split.delta_h.v,
                    hi.v - split.delta_h.v,
                    strip_left,
                    strip_right,
                    strip_left,
                    strip_right,
                )
                out.add(key, area.v, area, f"{note}{suffix}", tags=area.tags, geometry=geometry)
                out.add(dig_key, area.v, area, f"{note}{suffix}", tags=area.tags, geometry=geometry)

    # 围护量（每面 ×1）+ 支撑
    flat_total = _dim_sum(*(member.flat_width for member in snapshots))
    amount_dim = snapshots[0].info.amount_dim

    strut_emitted = False

    def _emit_face(face_work, face_depth: Dim, owner: _Member, note: str, support_flag: str) -> None:
        """一个面的围护量（类别 ``围护`` ×1）与支撑（围檩 ×1；贯通支撑整槽一次）。

        ``face_depth`` / ``flat_total`` 是 mm 记法的几何量，用户公式按 m 口径
        代入，经 :meth:`Dim.to_m` 派生。
        """
        nonlocal strut_emitted
        out = results.setdefault(owner.element.id, QDict())
        depth_m = face_depth.to_m()
        flat_m = flat_total.to_m()
        works_quantities(
            face_work, depth_m, amount_dim, "F", owner.ad, owner.info, out, note,
            sides=1, width=flat_m, categories={"围护"},
        )
        if getattr(owner.element, support_flag):
            # 支撑行按公式类别识别（不再看 Z 键前缀）；做法与围护面同一个
            # （含换填层厚度的）档位，贯通支撑行只在首个勾选面出一次
            levels = list(face_work.levels)
            fixed_h = _dim_sum(*(mm_of_m(dim(level.h)) for level in levels if level.h >= 0))
            fixed_cnt = sum(1 for level in levels if level.h >= 0)
            for level in levels:
                if level.h >= 0:
                    height = mm_of_m(dim(level.h))
                elif len(levels) > fixed_cnt:
                    height = (face_depth - fixed_h) / (len(levels) - fixed_cnt)
                else:
                    height = face_depth
                component = level.components[0] if level.components else None
                component_side_quantities(
                    component, height.to_m(), flat_m, amount_dim, out,
                    note=f"{note}·支撑", emit_without_sides=not strut_emitted,
                )
            strut_emitted = True

    _emit_face(work_left, first.depth, first, "围护·左侧", "support_left")
    _emit_face(work_right, last.depth, last, "围护·右侧", "support_right")
    for i, pair in enumerate(pairs):
        if pair.deep is None:
            continue  # 等深相邻面：两侧均为 "-"，不出围护量
        deep = pair.deep
        delta = snapshots[i + 1].depth - snapshots[i].depth
        if delta.v < 0:
            delta = -delta
        # 内侧坡挂深侧构件；支撑勾选 = 深侧构件朝向该面的勾选
        support_flag = "support_right" if deep is snapshots[i] else "support_left"
        _emit_face(pair.work, delta, deep, f"围护·中间坡{i + 1}", support_flag)

    # 逐构件：降水 / 特殊地基 / 管道基础 / 管材
    for member in snapshots:
        out = results.setdefault(member.element.id, QDict())
        info = member.info
        pf = info.pf
        pp = info.pp
        work_well = choice_work(member.pe_r, member.depth.v)
        if pp is not None and work_well is not None:
            # 湿土排水 = 归属带宽 ×（槽深−1m）的简化断面
            wet = member.flat_width * (member.depth - mm(1000)) if member.depth.v > 1 else None
            precipitation.cal_precipitation(
                pp, work_well, pf, member.ad, info, member.depth, out,
                wet_dig=wet,
            )
        special = pf.components[0] if pf.components else None
        if special is not None:
            component_quantities(
                special,
                member.depth.to_m(),
                member.flat_width.to_m(),
                info.amount_dim,
                "F",
                out,
                "特殊地基",
            )
        foundation.cal_found(info, pf, pp, member.ad, out)
        if info.category == CATEGORY_ENCASED:
            foundation.encased_pipe_deduction(info, out, z_bottom=member.ad.c1.v)
        foundation.cal_pipes(info, out)
        out.scale(info.amount, expr=info.amount_dim.e)
    return results, errors


def _cushion_name(pf) -> str:
    return pf.cushions[0].name if pf.cushions else "中粗砂"


def _member_layers(member: _Member) -> list[tuple[str, Dim, str]]:
    """构件自己的回填分层列表（定额键, 层厚, 说明），与单构件计算同口径。"""
    return backfill_layers(
        member.info.pp,
        member.info.pf,
        member.ad,
        member.info.size_h_dim,
        member.depth,
        _cushion_name(member.info.pf),
    )


def _member_bands(member: _Member) -> list[tuple[str, Dim, Dim, Dim, str]]:
    """构件自己的分层带 (定额键, 下界, 上界, 层厚, 说明)——独立回填标高口径。

    层的高度带自槽底向上累计：第 k 层占据 [Σh, Σh+h]。
    """
    bands: list[tuple[str, Dim, Dim, Dim, str]] = []
    cum = dim(0.0)
    for key, layer, note in _member_layers(member):
        if layer.v <= 0:
            continue
        bands.append((key, cum, cum + layer, layer, note))
        cum = cum + layer
    return bands


def _unified_interfaces(snapshots: list[_Member]) -> dict[tuple[str, int], Dim]:
    """统一回填标高：逐层角色取组内各构件层顶的最低标高（最浅）。

    层顶标高 = 槽底深 − 自底向上的累计层厚（地面以下深度，越小越浅），只有
    该层自身厚度为正的构件参与统筹，算式取贡献构件的推导；组内没有正厚度
    贡献的角色不进结果，构件重建分层带时跳过该界面、由相邻层带并入。
    """
    layers_by_member = [(member, _member_layers(member)) for member in snapshots]
    best: dict[tuple[str, int], Dim] = {}
    for member, layers in layers_by_member:
        cum = dim(0.0)
        for (base, occurrence), (_key, layer, _note) in zip(layer_roles(layers), layers):
            cum = cum + layer
            if layer.v <= 0:
                continue
            elevation = member.depth - cum
            role = (base, occurrence)
            if role not in best or elevation.v < best[role].v - 1e-9:
                best[role] = elevation
    return best


def _unified_member_bands(
    member: _Member, interfaces: dict[tuple[str, int], Dim]
) -> list[tuple[str, Dim, Dim, Dim, str]]:
    """统一回填标高下构件的分层带：界面取统筹标高，材质定额键仍是自己的。

    各层厚度 = 相邻两条统筹界面的标高差（首层自构件自己的槽底起算）；构件
    缺某层（自身厚度 0 / 无此层）时该界面跳过、标高区间并入相邻层带。最后
    一条带不足槽顶时向上补齐——与 backfill_layers"顶层吸收剩余"的口径一致。
    """
    layers = _member_layers(member)
    bands: list[tuple[str, Dim, Dim, Dim, str]] = []
    bottom = member.depth  # 首层带的下缘标高 = 自身槽底
    for (base, occurrence), (key, _layer, note) in zip(layer_roles(layers), layers):
        top = interfaces.get((base, occurrence))
        if top is None or top.v >= bottom.v - 1e-9:
            continue  # 组内没有该层的统筹界面 / 界面不高于上一条：并入相邻层带
        bands.append((key, member.depth - bottom, member.depth - top, bottom - top, note))
        bottom = top
    if bands and bands[-1][2].v < member.depth.v - 1e-9:
        key, lo, _hi, _thickness, note = bands[-1]
        bands[-1] = (key, lo, member.depth, member.depth - lo, note)
    return bands


def _side_extension(pieces: list[list[_SlopeSegment]], height: Dim) -> float:
    """该侧各剖面段在自槽底高度 ``height`` 处的外扩宽合计（不覆盖该高度的段不计）。

    ``height`` 传 mm 记法 Dim（与剖面段同空间）。
    """
    probe = height
    total = 0.0
    for profile in pieces:
        segment = _segment_for_interval(profile, probe, probe)
        if segment is not None:
            total += segment.width_at(probe).v
    return total


def _member_geometry(
    member: "_Member", lo: Dim, hi: Dim
) -> tuple[float, float, float, float, float, float]:
    """分层区间的断面范围：自槽底 [lo, hi]，左右缘 = 本体半宽 + 该侧外扩。

    左右缘相对本体中心（m，左负右正）；不对称坡区（深浅相邻）也精确。
    """
    base_half = member.base_width.v / 2.0
    return (
        lo.v,
        hi.v,
        -(base_half + _side_extension(member.profiles_left, lo)),
        base_half + _side_extension(member.profiles_right, lo),
        -(base_half + _side_extension(member.profiles_left, hi)),
        base_half + _side_extension(member.profiles_right, hi),
    )


def _member_dig_fill(
    member: _Member, out: QDict, bands: list[tuple[str, Dim, Dim, Dim, str]]
) -> bool:
    """构件宽度剖面的挖方 / 分层回填（按标高分层、每层梯形，结果写入 ``out``）。

    ``bands`` 为该构件的回填分层带（独立 / 统一回填标高口径由调用方决定）。
    标高事件集 = 回填分层界面 + 各侧放坡剖面的全部分级 / 平台折点（含相邻
    构件槽底标高）。事件之间宽度线性，单层面积用梯形 ``(w_下+w_上)/2*Δh``
    精确计算；每层按它所属的回填分层归类，挖方按层合并 term（说明 = 层名）。
    """
    info = member.info
    pp = info.pp
    if not bands:
        return False
    total = bands[-1][2]

    # 标高事件集：回填分层界面优先，其次各侧剖面的折点（分级 / 平台 / 相邻槽底）
    boundaries: list[Dim] = [dim(0.0), total]
    for _key, lo, hi, _layer, _note in bands:
        boundaries.append(lo)
        boundaries.append(hi)
    for profile in member.profiles:
        for segment in profile:
            boundaries.append(segment.t1)
            boundaries.append(segment.t2)
    edges = [
        value
        for value in _unique_dims(boundaries)
        if -1e-9 <= value.v <= total.v + 1e-9
    ]

    dig_key = f"开挖|{pp.excvt}|m3"
    dig = out.add(dig_key, 0.0)
    dig.terms.clear()
    dig.value = 0.0
    produced = False
    for lo, hi in zip(edges, edges[1:]):
        if hi.v - lo.v <= 1e-9:
            continue
        band = next(
            (
                item
                for item in bands
                if item[1].v <= lo.v + 1e-9 and hi.v <= item[2].v + 1e-9
            ),
            None,
        )
        if band is None:
            continue
        key, band_lo, band_hi, layer, note = band
        # 整层未被围护分级切开时沿用层厚算式，否则用区间差
        if abs(lo.v - band_lo.v) <= 1e-9 and abs(hi.v - band_hi.v) <= 1e-9:
            height = layer
        else:
            height = hi - lo
        low, slope_terms = _width_and_slope_for_interval(
            member.profiles, lo, hi, height
        )
        if slope_terms.v == 0:
            # 恒宽层：梯形公式的等底情形，直接 B*H
            area = low * height
        else:
            # (2*W_下 + Σ(H*s))*H/2：下底只出现一次，与非合槽构件同形
            doubled = Dim(2 * low.v, f"2*{wrap(low.e)}", (), low.s)
            inner = doubled + slope_terms
            area = Dim(
                inner.v * height.v / 2.0,
                f"({inner.e})*{wrap(height.e)}/2",
                (),
                inner.s + height.s,
            )
        if area.v == 0:
            continue
        produced = True
        geometry = _member_geometry(member, lo, hi)
        out.add(key, area.v, area, note, tags=area.tags, geometry=geometry)
        dig.add_term(area.v, area, note, tags=area.tags, geometry=geometry)
    if not produced:
        out.discard(dig_key)
        return False
    if not dig.terms:
        out.discard(dig_key)
    return True
