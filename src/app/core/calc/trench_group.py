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
  坞膀下半顶、坞膀顶、管顶以上顶、覆土顶）、各侧放坡剖面的全部分级 /
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
from app.core.calc.tracer import (
    AreaParts,
    Dim,
    QDict,
    dim,
    dim_min,
    dim_sum as _dim_sum,
    mm,
    mm_of_m,
    mm_text,
    scale_sum,
    wrap,
)
from app.core.evaluator import EvalError, evaluate
from app.core.models import base as orm
from app.core.models.models import (
    BACKFILL_UNIFIED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
    Element,
    PcpEnclosure,
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
    work,
    depth: Dim,
    shallow: Dim,
    workface: Dim,
    wall_width: Dim | None = None,
) -> list[list[_SlopeSegment]]:
    """相邻侧（深侧）的宽度剖面。

    浅槽底（``shallow``）以下：工作面矩形 + 深槽底放坡到浅槽底，按**单沟槽**
    完整计算（起坡点分隔时这部分全部归深侧构件）。
    浅槽底以上：到虚拟分割线为止的等宽条带。``wall_width`` 为深侧基础边到
    虚拟墙的距离（起坡点分隔且浅构件侵入时小于 ``工作面 + 坡顶外扩``）；
    ``None`` = 按完整宽度 ``工作面 + 坡顶外扩``（管中心 / 间距平分分隔由
    ``_boundary_splits`` 再按分割线调整）。
    """
    profiles: list[list[_SlopeSegment]] = []
    delta = depth - shallow  # 深槽底到浅槽底的高度差
    # 浅槽底以下：工作面 + 放坡（单沟槽完整断面）
    low = _rect_segments(workface, delta) if delta.v > 0 else []
    if low:
        profiles.append(low)
    segments: list[_SlopeSegment] = []
    if delta.v > 0:
        segments = _profile_segments(work, delta)
        if segments:
            profiles.append(segments)
    if depth.v <= delta.v + 1e-9:
        return profiles
    # 浅槽底以上：到虚拟墙（或完整坡顶外扩）
    if wall_width is None:
        run = segments[-1].width_at(delta) if segments else dim(0.0)
        above = workface + run
    else:
        above = wall_width if wall_width.v > 0 else dim(0.0)
    profiles.append([_SlopeSegment(delta, above, dim(0.0), depth)])
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

    恒宽段（本体 / 工作面 / 条带）先累加、坡段后累加：下底宽读作
    「本体+两侧工作面+坡外扩」，且「本体+两侧工作面」在各分层的下底宽里
    连续出现，展示层才能把它整体提成槽底宽中间量（坡项夹在两个工作面
    之间时会截断公共片段）。
    """
    constant: list[_SlopeSegment] = []
    sloped: list[_SlopeSegment] = []
    for profile in profiles:
        segment = _segment_for_interval(profile, lo, hi)
        if segment is None:
            continue
        (constant if segment.slope.v == 0 else sloped).append(segment)
    low = dim(0.0)
    slope_terms = dim(0.0)
    for segment in constant:
        low = low + segment.width_at(lo)
    for segment in sloped:
        low = low + segment.width_at(lo)
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
    # 混凝土基础只对混凝土管生效（与 foundation._found_pipe 同判据）；其余管
    # 取管外皮半径（垂直切线），即「构件外边线」
    if (
        info.pf is not None
        and info.pf.con_found
        and info.pipes
        and ("混凝土" in info.pipes[0].mat or "砼" in info.pipes[0].mat)
    ):
        return member.base_width / 2
    return member.ad.od / 2


def member_outer_radius(member: "_Member") -> Dim:
    """构件外边线半径（mm）：与「间距计算起始点」同口径。

    砼基础管道取基础外皮半宽、砂基础管道取管外皮半径、混凝土结构（包封 /
    箱涵 / 管廊）取结构本体外包半宽。合槽「与相邻构件中心距离」的下限校验
    用它：填写的距离不得小于两构件外边线半径之和。
    """
    return _spacing_anchor_half(member)


def _member_label(member: "_Member") -> str:
    """构件显示名：名称 + 规格；没有名称时只显示规格。"""
    name = (member.element.name or "").strip()
    try:
        spec = (member.info.spec() or "").strip()
    except Exception:  # 原则缺失等异常时退回名称
        spec = ""
    if name:
        return f"{name} {spec}".strip()
    return spec or "相邻构件"


def resolve_shared_widths(
    *,
    left_base,
    right_base,
    left_work,
    right_work,
    run,
    left_deep: bool,
    equal: bool,
    distance,
):
    """相邻面两侧的共享侧宽度（距离非空时按中心距离覆盖浅侧工作面）。

    输入 / 输出可为 :class:`Dim`（mm 记法，计算用）或 float（m，断面图用），
    两种调用方共用同一套分支，避免几何与算式各写一遍：

    * 未填距离：等深 = 两侧各自工作面；异深 = 浅侧工作面 + 深侧（工作面 + 放坡）；
    * 填了距离：间距 = 距离 − 两侧基础半宽；**未填距离一侧**仍按工作面 / 放坡，
      填了距离的一侧取剩余宽度（该侧匹配的工作面宽失效）。等深时按规则填在
      左侧构件的右侧，即左宽取剩余、右宽仍按右构件工作面。

    返回 ``(左宽, 右宽)``。剩余宽度**允许为负**：中心距离只受两构件外边线
    半径之和限制，浅构件可以侵入深构件的放坡范围之上（负宽度在剖面里按 0
    处理，构件位置仍按中心距离摆放）。
    """
    if equal:
        base_left, base_right = left_work, right_work
        fixed = right_work
    elif left_deep:
        base_left, base_right = left_work + run, right_work
        fixed = left_work + run
    else:
        base_left, base_right = left_work, right_work + run
        fixed = right_work + run
    if distance is None:
        return base_left, base_right
    gap = distance - left_base / 2.0 - right_base / 2.0
    if equal or not left_deep:
        # 距离填在左侧构件（等深 / 右深）：左宽取剩余，右宽保持对侧工作面
        return gap - fixed, fixed
    return fixed, gap - fixed


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
        left_ext = (
            snapshots[0].work_width_left if i == 0 else pairs[i - 1].right_width
        )
        right_ext = (
            member.work_width_right if i == n - 1 else pairs[i].left_width
        )
        base_left = cursor + left_ext
        base_right = base_left + member.half_left + member.half_right
        center = base_left + member.half_left
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


def _wedge_pieces(
    split: _CenterSplit,
) -> list[tuple[Dim, tuple[float, float, float, float, float, float]]]:
    """坡区楔形按放坡段拆分的分项：每段一个三角形 / 梯形 / 矩形，几何精确。

    楔形 = 分界线与内侧坡之间、浅槽底以下的条带（起坡点分界下原属深侧、
    管中心分隔下划给浅侧的部分），宽度 W(t) = max(0, offset − gap)，gap =
    run_max − width_at(t) 自深槽底的 run_max 向上减到 0。按放坡段逐段积分
    （与 :func:`_center_deduction` 的逐段扣减一一对应，整槽挖填守恒）：段内
    宽度线性，整段在楔形内是梯形 ``(u+v)*h/2``；分界线在段内切入坡面时
    裁剪成三角形 ``底*(底/放坡系数)/2``（底 = 段顶楔宽，高 = 底/放坡系数）；
    桩类 / 直壁坡面竖直，整段是矩形。每段面积 Dim 带 :class:`AreaParts`
    （展示层据此把 S 行统一成 底×高÷2 的分项公式），并随返回值给出分项
    几何（自获方槽底起算为负高度，悬停高亮用）。
    """
    offset = split.offset
    if offset.v <= 1e-9 or split.delta_h.v <= 1e-9:
        return []
    if not split.profile:  # 桩类 / 直壁：坡面竖直，整段都是矩形楔形
        area = offset * split.delta_h
        area = Dim(
            area.v,
            area.e,
            area.tags,
            area.s,
            AreaParts("rectangle", offset, None, split.delta_h),
        )
        return [
            (
                area,
                _wedge_piece_geometry(split, dim(0.0), split.delta_h, offset, offset),
            )
        ]
    pieces: list[tuple[Dim, tuple[float, float, float, float, float, float]]] = []
    for segment in split.profile:
        width_lo = offset - (split.run_max - segment.width_at(segment.t1))
        width_hi = offset - (split.run_max - segment.width_at(segment.t2))
        if width_hi.v <= 1e-9:
            continue  # 整段仍在坡面之外：分界未切入坡区
        if width_lo.v >= -1e-9:
            height = segment.t2 - segment.t1
            area = (width_lo + width_hi) * height / 2
            area = Dim(
                area.v,
                area.e,
                area.tags,
                area.s,
                AreaParts("trapezoid", width_lo, width_hi, height),
            )
            lower, upper = segment.t1, segment.t2
            w_lower = width_lo
        else:
            # 段内切入坡面：切点以下不产生楔形，自切点按同坡收到段顶
            height = width_hi / segment.slope
            area = width_hi * height / 2
            area = Dim(
                area.v,
                area.e,
                area.tags,
                area.s,
                AreaParts("triangle", None, width_hi, height),
            )
            lower, upper = segment.t2 - height, segment.t2  # 自切点（楔宽 0）起算
            w_lower = dim(0.0)
        if area.v == 0:
            continue
        pieces.append(
            (area, _wedge_piece_geometry(split, lower, upper, w_lower, width_hi))
        )
    return pieces


def _wedge_piece_geometry(
    split: _CenterSplit,
    t_a: Dim,
    t_b: Dim,
    w_a: Dim,
    w_b: Dim,
) -> tuple[float, float, float, float, float, float]:
    """楔形分项 [t_a, t_b]（自深侧槽底起算，两端楔宽 w_a / w_b）的断面范围。

    自获方槽底坐标为负高度；楔形在浅槽底水平面处最宽（= offset），向深处
    随放坡剖面收窄，内缘 = 分界线内移 gap = offset − 楔宽。x 相对获方本体
    中心，左负右正；单段放坡时整楔即原「外接梯形」口径。
    """
    delta = split.delta_h.v
    wall = split.wall_x - split.gainer_center_x
    offset = split.offset.v
    gap_a = offset - w_a.v
    gap_b = offset - w_b.v
    if split.gainer == split.pair_index:  # 获方在 pair 左侧：楔形在分界右侧
        return (
            t_a.v - delta,
            t_b.v - delta,
            wall + gap_a,
            wall + offset,
            wall + gap_b,
            wall + offset,
        )
    return (
        t_a.v - delta,
        t_b.v - delta,
        wall - offset,
        wall - gap_a,
        wall - offset,
        wall - gap_b,
    )


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
    #: 左 / 右侧实际生效的单侧工作面宽：默认等于 ``work_width``；某一侧填写了
    #: 与相邻构件的中心距离时，该侧改为按距离推导出的剩余宽度（匹配值失效）
    work_width_left: Dim = field(default_factory=lambda: dim(0.0))
    work_width_right: Dim = field(default_factory=lambda: dim(0.0))
    #: 左 / 右基础边界到本体中心的距离（默认 = base_width / 2）。浅构件侵入深侧
    #: 放坡时，侵入侧边界收到「构件外边线半径」（砼基础边线 / 管外皮切线），
    #: 即该侧的工作面加宽 a 不再计入本体基础
    half_left: Dim = field(default_factory=lambda: dim(0.0))
    half_right: Dim = field(default_factory=lambda: dim(0.0))
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
    #: 本相邻面填写的构件中心距离（mm 记法）；None = 两侧都按工作面宽
    distance: Dim | None = None


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
    work_width = mm(workwidth_of(pw, info)).as_param(
        "b1", "工作面宽度", "面宽原则·工作面宽度表"
    )
    return (
        _Member(
            element=element,
            info=info,
            ad=ad,
            pe_r=material_pe,
            depth=depth,
            base_width=base_width,
            work_width=work_width,
            work_width_left=work_width,
            work_width_right=work_width,
            half_left=base_width / 2.0,
            half_right=base_width / 2.0,
        ),
        None,
    )


def _body_width(member: "_Member") -> Dim:
    """本体全宽：左右半宽对称（默认 / 砼基础外皮半径）时直接用全宽算式。

    基础参数本来就是全宽（断面宽+2×(壁厚+工作面加宽)），对称时不必拆成
    两个半宽再相加——那会让下底宽显示成 ``(…)/2+(…)/2``，还截断展示层的
    公共片段提取。浅构件侵入被替换成外边线半径（管外皮 oD/2）等不对称
    场景仍按左右半宽拼。
    """
    if member.half_left.e == member.half_right.e:
        return member.base_width
    return member.half_left + member.half_right


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


def _center_distance_dim(element: Element, side: str) -> Dim | None:
    """构件某侧的构件中心距离（mm 记法）；空 / 算式不合法 / 非正数返回 None。"""
    text = (
        element.center_distance_right if side == "right" else element.center_distance_left
    ) or ""
    text = text.strip()
    if not text:
        return None
    try:
        value = evaluate(text)
    except EvalError:
        return None
    if value <= 0:
        return None
    return mm_text(text, value).named("构件中心距离", "工作面宽·与相邻构件中心距离")


def _pair_distance(left: "_Member", right: "_Member") -> tuple[Dim | None, str]:
    """相邻面的中心距离与填写侧。

    只有更浅一侧可填（等深时按规则 5 填在左侧构件的右侧）：右深 / 等深读
    左构件的 ``center_distance_right``，左深读右构件的 ``center_distance_left``；
    另一侧即使有残留值也不生效。返回的填写侧 ``"left"`` 表示填在左构件右侧，
    ``"right"`` 表示填在右构件左侧。
    """
    if right.depth.v >= left.depth.v - 1e-9:
        return _center_distance_dim(left.element, "right"), "left"
    return _center_distance_dim(right.element, "left"), "right"


def _pair_deep_geometry(session, left: "_Member", right: "_Member"):
    """相邻面的深侧构件 / 做法 / 放坡水平投影。

    返回 ``(深侧构件, 做法, run, 是否等深, 左是否更深, 错误说明)``；等深时
    深侧构件与做法为 None、run 为 0。
    """
    h_left, h_right = left.depth.v, right.depth.v
    equal = abs(h_right - h_left) <= 1e-9
    left_deep = h_left > h_right + 1e-9
    if equal:
        return None, None, dim(0.0), True, False, None
    if left_deep:
        deep, shallow = left, right
        deep_pe = _resolve_by_name(
            session, PcpEnclosure, _side_name(deep.element, "right")
        ) or _first_of(session, PcpEnclosure)
    else:
        deep, shallow = right, left
        deep_pe = _resolve_by_name(
            session, PcpEnclosure, _side_name(deep.element, "left")
        ) or _first_of(session, PcpEnclosure)
    delta = abs(h_right - h_left)
    work = choice_work(deep_pe, delta) if deep_pe is not None else None
    if work is None:
        return deep, None, dim(0.0), False, left_deep, "深侧围护原则没有任何围护分级。"
    run = _internal_run(work, deep.depth, shallow.depth)
    return deep, work, run, False, left_deep, None


def group_distance_plan(group: TrenchGroup) -> dict[int, tuple[bool, bool]]:
    """组内每条构件的 (与左侧构件中心距离可编辑, 与右侧构件中心距离可编辑)。

    * 首构件左侧 / 末构件右侧是合槽外边缘，没有相邻构件，恒不可编辑；
    * 共享面只有**更浅一侧**可填（等深时按规则 5 填在左侧构件的右侧）；
      更深 / 等深一侧不可填，由面宽原则匹配的工作面宽控制。
    """
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    depths = member_depths(group)
    n = len(members)
    plan: dict[int, tuple[bool, bool]] = {}
    for index, element in enumerate(members):
        depth = depths.get(element.id)
        left_active = False
        right_active = False
        if depth is not None:
            if index > 0:
                neighbor = depths.get(members[index - 1].id)
                left_active = neighbor is not None and depth < neighbor - 1e-9
            if index < n - 1:
                neighbor = depths.get(members[index + 1].id)
                # 等深时距离填在左侧构件（规则 5），因此 <=
                right_active = neighbor is not None and depth <= neighbor + 1e-9
        plan[element.id] = (left_active, right_active)
    return plan


def group_distance_limits(
    group: TrenchGroup, element_id: int, side: str
) -> tuple[float, str] | None:
    """某构件某侧的中心距离限制（mm）。

    返回 ``(两构件外边线半径之和, 相邻构件显示名)``；相邻构件显示名 = 名称 +
    主表格上的规格（没有名称时只显示规格）。不在组内 / 该侧没有相邻构件 /
    该侧不是可填侧 / 几何无法解析时返回 None。

    只校验**外边线半径之和**：浅构件允许侵入深构件的放坡范围之上，不再要求
    距离容纳对侧工作面 / 放坡。
    """
    session = orm.session()
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    index = next((i for i, item in enumerate(members) if item.id == element_id), None)
    if index is None:
        return None
    if side == "left":
        if index == 0:
            return None
        left_element, right_element = members[index - 1], members[index]
    elif side == "right":
        if index == len(members) - 1:
            return None
        left_element, right_element = members[index], members[index + 1]
    else:
        return None
    left, _left_error = _resolve_member(session, left_element, require_amount=False)
    right, _right_error = _resolve_member(session, right_element, require_amount=False)
    if left is None or right is None:
        return None
    # 校验的侧必须是该相邻面的可填侧：左构件的右侧（等深 / 右深）或右构件的左侧（左深）
    filled_on_left = right.depth.v >= left.depth.v - 1e-9
    if side == "right":
        if left_element.id != element_id or not filled_on_left:
            return None
    else:
        if right_element.id != element_id or filled_on_left:
            return None
    radius_sum = (member_outer_radius(left).v + member_outer_radius(right).v) * 1000.0
    neighbor = right if side == "right" else left
    return radius_sum, _member_label(neighbor)


def compute_group(group: TrenchGroup) -> tuple[dict[int, QDict], dict[int, str]]:
    """计算一个合槽组：返回 (构件 id → 工程量, 构件 id → 错误说明)。

    组员按 order_no 从左到右；父节点不参与（零工程量、无围护 / 面宽原则）。
    原则缺失 / 无做法时整组带错误说明，错误字符串挂在行上展示。
    """
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

    if group.backfill_mode == BACKFILL_UNIFIED and snapshots[0].info.pp is not None:
        # 统一回填标高：全部组员的挖填原则统一为第一条组员的（数据同步的
        # 计算侧兜底：历史数据组员原则不一致时也按统一口径计算）
        for member in snapshots[1:]:
            member.info.pp = snapshots[0].info.pp

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

    # 相邻区（规则 4 / 5）：等深 → 两侧均为 "-"；异深 → 深侧选原则放坡。
    # 填了「与相邻构件中心距离」的共享面：浅侧匹配的工作面宽失效，按距离摆放
    # 构件位置（间距 = 距离 − 两侧基础半宽；未填侧仍按工作面 / 放坡）。
    pairs: list[_Pair] = []
    for i in range(n - 1):
        left, right = snapshots[i], snapshots[i + 1]
        deep, work, run, equal, left_deep, pair_error = _pair_deep_geometry(
            session, left, right
        )
        if pair_error is not None:
            for member in snapshots:
                errors[member.element.id] = pair_error
            return results, errors
        distance, filled_side = _pair_distance(left, right)
        left_width, right_width = resolve_shared_widths(
            left_base=left.base_width,
            right_base=right.base_width,
            left_work=left.work_width,
            right_work=right.work_width,
            run=run,
            left_deep=left_deep,
            equal=equal,
            distance=distance,
        )
        if distance is not None:
            # 唯一的下限：两构件外边线半径之和。浅构件允许侵入深侧放坡范围
            # 之上，浅侧剩余宽度为负时剖面按 0 处理，构件位置仍按中心距离。
            radius_sum = (
                member_outer_radius(left).v + member_outer_radius(right).v
            ) * 1000.0
            if distance.v * 1000.0 < radius_sum - 1e-6:
                message = (
                    f"构件「{_member_label(left)}」与「{_member_label(right)}」的"
                    f"中心距离小于两构件外边线半径之和（{radius_sum:g} mm）。"
                )
                for member in snapshots:
                    errors[member.element.id] = message
                return results, errors
            # 填了距离的一侧：匹配的工作面宽失效。剩余宽度为负 = 浅构件侵入
            # 深侧放坡：浅侧该面边界收到「构件外边线半径」（砼基础边线 / 管外皮
            # 切线），工作面宽按 0；深侧共享侧宽度 = 距离 − 浅侧半径 − 深侧基础半宽
            if filled_side == "left":
                if left_width.v < -1e-9:
                    left.half_right = member_outer_radius(left)
                    left_width = dim(0.0)
                    right_width = distance - left.half_right - right.half_left
                    left.work_width_right = dim(0.0)
                else:
                    left.work_width_right = left_width
            else:
                if right_width.v < -1e-9:
                    right.half_left = member_outer_radius(right)
                    right_width = dim(0.0)
                    left_width = distance - right.half_left - left.half_right
                    right.work_width_left = dim(0.0)
                else:
                    right.work_width_left = right_width
        pairs.append(
            _Pair(
                deep=deep,
                run=run,
                work=work,
                left_width=left_width,
                right_width=right_width,
                distance=distance,
            )
        )

    # 逐构件的宽度剖面 + 平面归属带宽（规则 6：工作面宽用自己的 PW）
    for i, member in enumerate(snapshots):
        member.profiles = []
        member.profiles_left = []
        member.profiles_right = []
        base = _rect_segments(_body_width(member), member.depth)
        if base:
            member.profiles.append(base)
        if i == 0:
            left = _outer_side_profiles(work_left, member.depth, member.work_width_left)
            member.profiles += left
            member.profiles_left += left
        else:
            pair = pairs[i - 1]
            if pair.deep is member:  # 自身更深：左侧内侧放坡
                # 浅槽底以上先按虚拟墙（侵入时墙在坡顶以内）截断成「并集」，
                # 管中心 / 间距平分分隔再由 _boundary_splits 把线移到分界处
                left = _internal_side_profiles(
                    pair.work,
                    member.depth,
                    snapshots[i - 1].depth,
                    member.work_width_left,
                    pair.right_width,
                )
            else:  # 自身更浅 / 等深：左侧虚拟竖直围护
                left = _wall_profiles(member.work_width_left, member.depth)
            member.profiles += left
            member.profiles_left += left
        if i == n - 1:
            right = _outer_side_profiles(work_right, member.depth, member.work_width_right)
            member.profiles += right
            member.profiles_right += right
        else:
            pair = pairs[i]
            if pair.deep is member:  # 自身更深：右侧内侧放坡
                right = _internal_side_profiles(
                    pair.work,
                    member.depth,
                    snapshots[i + 1].depth,
                    member.work_width_right,
                    pair.left_width,
                )
            else:  # 自身更浅 / 等深：右侧虚拟竖直围护
                right = _wall_profiles(member.work_width_right, member.depth)
            member.profiles += right
            member.profiles_right += right
        flat = _body_width(member)
        if i == 0:
            flat = flat + member.work_width_left
        else:
            flat = flat + pairs[i - 1].right_width
        if i == n - 1:
            flat = flat + member.work_width_right
        else:
            flat = flat + pairs[i].left_width
        # 浅构件侵入深侧放坡时共享侧剩余宽度可能为负：归属带宽按 0 兜底，
        # 避免降水 / 特殊地基出现负宽度
        member.flat_width = flat if flat.v > 0 else dim(0.0)

    # 虚拟竖线分界（管中心分隔 / 间距平分分隔）：分界移到锚点中点。让出条带
    # 的一方在剖面里扣减（挖填随分层积分同步减少），获方把条带作为恒宽段
    # 并入分侧剖面——分层梯形自动含条带（每层一整个梯形，不再单独出条带项，
    # 也就不按起坡点分左中右三列），平面归属带宽随分界位移调整
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
            gainer = snapshots[split.gainer]
            # 条带 = [条带下缘(浅槽底), 构件槽底] 的恒宽段，并入获方共享侧剖面
            strip = [
                _SlopeSegment(
                    gainer.depth - split.shallow_depth, split.offset, dim(0.0), gainer.depth
                )
            ]
            gainer.profiles.append(strip)
            if split.gainer == split.pair_index:  # 获方在 pair 左侧：条带并自己的右缘
                gainer.profiles_right.append(strip)
            else:  # 获方在 pair 右侧：条带并自己的左缘
                gainer.profiles_left.append(strip)
            gainer.flat_width = gainer.flat_width + split.offset
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
        try:
            produced = _member_dig_fill(member, out, member.bands)
        except AssertionError as error:
            # 记法链被污染（如面积量纲混进标高链）只影响该成员的分层积分，
            # 断言全文（两侧算式与记法指数）转逐构件错误展示，其余成员照常
            errors[member.element.id] = f"分层几何记法异常，未生成工程量（{error}）。"
            continue
        if produced:
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
        # 坡区楔形：获方更浅时，浅槽底以下的坡区楔形划给获方——计入获方自己
        # 最底层的定额键（垫层），每个分界按放坡段拆分项（每段三角形/梯形/
        # 矩形，面积行统一成 底×高÷2；几何自获方槽底起算为负，悬停高亮用）
        if gainer.depth.v < loser.depth.v - 1e-9:
            bottom_key, *_rest, bottom_note = gainer.bands[0]
            for area, geometry in _wedge_pieces(split):
                out.add(
                    bottom_key,
                    area.v,
                    area,
                    f"{bottom_note}{suffix}",
                    tags=area.tags,
                    geometry=geometry,
                )
                out.add(
                    dig_key,
                    area.v,
                    area,
                    f"{bottom_note}{suffix}",
                    tags=area.tags,
                    geometry=geometry,
                )

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
        foundation.cal_found(info, pf, pp, member.ad, out, bands=member.bands)
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
    """统一回填标高：逐层角色取组内统筹界面标高。

    * 坞膀各层顶：取**最低标高（最浅）**的那条——最高的分割线（现状口径）；
    * 垫层顶：取**最高标高（最深）**的那条——最低的分割线，垫层材料只到
      最深的垫层顶为止，深构件的垫层带不再向上膨胀进回填区；
    层顶标高 = 槽底深 − 自底向上的累计层厚（地面以下深度），只有该层自身
    厚度为正的构件参与统筹，算式取贡献构件的推导；组内没有正厚度贡献的
    角色不进结果，构件重建分层带时跳过该界面、由相邻层带并入。
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
            deeper = base == "垫层"  # 垫层顶取最深（最低的分割线），其余取最浅
            take = (
                role not in best
                or (deeper and elevation.v > best[role].v + 1e-9)
                or (not deeper and elevation.v < best[role].v - 1e-9)
            )
            if take:
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
    for (base, occurrence), (key, layer, note) in zip(layer_roles(layers), layers):
        top = interfaces.get((base, occurrence))
        if top is None:
            continue
        if base == "垫层" and layer.v > 1e-9:
            # 垫层顶分割线取组内最深垫层顶：比自身垫层顶更深时，构件自己的
            # 垫层带仍按自身厚度保留（分界线以下的区域由条带/楔形分项体现）
            top = dim_min(top, bottom - layer)
        if top.v >= bottom.v - 1e-9:
            continue  # 界面不高于上一条：并入相邻层带
        bands.append((key, member.depth - bottom, member.depth - top, bottom - top, note))
        bottom = top
    if bands and bands[-1][2].v < member.depth.v - 1e-9:
        key, lo, _hi, _thickness, note = bands[-1]
        bands[-1] = (key, lo, member.depth, member.depth - lo, note)
    return bands


def _side_extension_interval(
    pieces: list[list[_SlopeSegment]], lo: Dim, hi: Dim
) -> tuple[float, float]:
    """该侧各剖面段在区间 [lo, hi] 内的外扩宽（在 lo / hi 处取值）。

    必须按**区间**找覆盖段，不能按端点找：侵入时浅槽底处「工作面 + 放坡」
    段与「浅槽底以上竖直条带」段在端点相接，按端点会同时命中两段、把两段
    宽度相加；按区间只会命中真正覆盖该分层的那一段。
    """
    lo_total = 0.0
    hi_total = 0.0
    for profile in pieces:
        segment = _segment_for_interval(profile, lo, hi)
        if segment is not None:
            lo_total += segment.width_at(lo).v
            hi_total += segment.width_at(hi).v
    return lo_total, hi_total


def _member_geometry(
    member: "_Member", lo: Dim, hi: Dim
) -> tuple[float, float, float, float, float, float]:
    """分层区间的断面范围：自槽底 [lo, hi]，左右缘 = 本体半宽 + 该侧外扩。

    左右缘相对本体中心（m，左负右正）；不对称坡区（深浅相邻）也精确。
    """
    left_lo, left_hi = _side_extension_interval(member.profiles_left, lo, hi)
    right_lo, right_hi = _side_extension_interval(member.profiles_right, lo, hi)
    return (
        lo.v,
        hi.v,
        -(member.half_left.v + left_lo),
        member.half_right.v + right_lo,
        -(member.half_left.v + left_hi),
        member.half_right.v + right_hi,
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
            # 恒宽层：矩形面积 = 宽 × 高
            rect = low * height
            area = Dim(
                rect.v,
                rect.e,
                rect.tags,
                rect.s,
                AreaParts("rectangle", low, None, height),
            )
        else:
            # (2*W_下 + Σ(H*s))*H/2：下底只出现一次，与非合槽构件同形
            doubled = Dim(2 * low.v, f"2*{wrap(low.e)}", low.tags, low.s)
            inner = doubled + slope_terms
            parts = (
                AreaParts("triangle", None, low + slope_terms, height)
                if low.v == 0
                else AreaParts("trapezoid", low, low + slope_terms, height)
            )
            area = Dim(
                inner.v * height.v / 2.0,
                f"({inner.e})*{wrap(height.e)}/2",
                inner.tags + height.tags,
                inner.s + height.s,
                parts,
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
