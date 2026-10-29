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
from app.core.calc.groove import backfill_layers, level_slope, split_h_by_step
from app.core.calc.measures import AtlasDims, cushion_thickness as cushion_dim
from app.core.calc.measures import foundation_thickness as foundation_dim
from app.core.calc.tracer import Dim, QDict, dim, dim_sum as _dim_sum, scale_sum
from app.core.models import base as orm
from app.core.models.models import CATEGORY_ENCASED, Element, TrenchGroup
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
            run = run + dim(levels[step - 1].step_width)
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
    if depth.v <= 0:
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


def _internal_side_profiles(work, depth: Dim, shallow: Dim) -> list[list[_SlopeSegment]]:
    """相邻侧（深侧）：深槽底放坡到浅槽底，以上为等宽竖直条带。

    返回的剖面覆盖 [0, depth]；桩类 / 直壁的 ``run`` 为 0，不产生宽度贡献。
    """
    delta = depth - shallow
    if delta.v <= 0:
        return []
    segments = _profile_segments(work, delta)
    if not segments:
        return []
    run = segments[-1].width_at(delta)
    if depth.v > delta.v + 1e-9:
        segments = segments + [_SlopeSegment(delta, run, dim(0.0), depth)]
    return [segments]


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


def _width_for_interval(
    profiles: list[list[_SlopeSegment]], lo: Dim, hi: Dim
) -> tuple[Dim, Dim]:
    """区间下沿 / 上沿的构件总宽（各宽度贡献之和）。"""
    low = dim(0.0)
    high = dim(0.0)
    for profile in profiles:
        segment = _segment_for_interval(profile, lo, hi)
        if segment is None:
            continue
        low = low + segment.width_at(lo)
        high = high + segment.width_at(hi)
    return low, high


def _as_dim(value: "Dim | float") -> Dim:
    """普通数字 → Dim（断面图等浮点调用方复用同一套剖面函数）。"""
    return value if isinstance(value, Dim) else dim(value)


def _internal_run(work, h_deep: "Dim | float", h_shallow: "Dim | float") -> Dim:
    """内侧放坡的水平投影（Dim）：深侧槽底放坡到浅侧槽底的总外扩宽。

    按做法逐级累加（含切级平台），桩类为 0（竖直隔断）。
    """
    deep, shallow = _as_dim(h_deep), _as_dim(h_shallow)
    delta = deep - shallow
    if delta.v <= 0 or work is None:
        return dim(0.0)
    _segments, run = _slope_profile(work, delta)
    return run


def _slope_points(work, depth: float) -> list[tuple[float, float]]:
    """断面图用边坡折线 (绝对深度, 外扩宽 m)：浮点坐标，供 section_view 绘制。"""
    segments, _run = _slope_profile(work, dim(depth))
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
    flat_width: Dim = field(default_factory=lambda: dim(0.0))  # 平面归属带宽（降水 / 特殊地基代入用）


@dataclass
class _Pair:
    """相邻两构件的几何口径（规则 4 / 5 / 7）。"""

    deep: _Member | None  # 更深一侧；None = 等深
    run: Dim  # 深侧放坡水平投影（m）；等深为 0
    work: object | None  # 深侧内侧坡做法
    left_width: Dim  # 左构件在该相邻面的归属宽（浅侧 = 工作面，深侧 = 放坡投影）
    right_width: Dim  # 右构件在该相邻面的归属宽


def _side_name(element: Element, side: str) -> str:
    """构件的左 / 右围护原则名；分设占位 ``pe_name`` 不参与几何。"""
    if side == "left":
        return element.pe_left_name or ("" if element.pe_name == "左右分设" else element.pe_name)
    return element.pe_right_name or ("" if element.pe_name == "左右分设" else element.pe_name)


def _resolve_by_name(session, model, name: str | None):
    from sqlalchemy import select

    if not name or name == "-":
        return None
    found_id = session.scalar(select(model.id).where(model.name == name))
    return session.get(model, found_id) if found_id is not None else None


def _first_of(session, model):
    from sqlalchemy import select

    return session.scalar(select(model).order_by(model.order_no, model.id))


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
    depth = info.depth_dim + (foundation_dim(pf) + ad.t + ad.c1) / 1000
    base_width = info.size_b_dim + scale_sum((ad.t, ad.a), 2.0) / 1000
    work_width = dim(workwidth_of(pw, info)) / 1000
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
                    right_width=run,
                )
            )
        else:
            pairs.append(
                _Pair(
                    deep=deep,
                    run=run,
                    work=work,
                    left_width=run,
                    right_width=right.work_width,
                )
            )

    # 逐构件的宽度剖面 + 平面归属带宽（规则 6：工作面宽用自己的 PW）
    for i, member in enumerate(snapshots):
        member.profiles = []
        base = _rect_segments(member.base_width, member.depth)
        if base:
            member.profiles.append(base)
        if i == 0:
            member.profiles += _outer_side_profiles(
                work_left, member.depth, member.work_width
            )
        else:
            pair = pairs[i - 1]
            if pair.deep is member:  # 自身更深：左侧内侧放坡
                member.profiles += _internal_side_profiles(
                    pair.work, member.depth, snapshots[i - 1].depth
                )
            else:  # 自身更浅 / 等深：左侧虚拟竖直围护
                member.profiles += _wall_profiles(member.work_width, member.depth)
        if i == n - 1:
            member.profiles += _outer_side_profiles(
                work_right, member.depth, member.work_width
            )
        else:
            pair = pairs[i]
            if pair.deep is member:  # 自身更深：右侧内侧放坡
                member.profiles += _internal_side_profiles(
                    pair.work, member.depth, snapshots[i + 1].depth
                )
            else:  # 自身更浅 / 等深：右侧虚拟竖直围护
                member.profiles += _wall_profiles(member.work_width, member.depth)
        flat = member.base_width
        if i == 0:
            flat = flat + member.work_width
        else:
            flat = flat + pairs[i - 1].left_width
        if i == n - 1:
            flat = flat + member.work_width
        else:
            flat = flat + pairs[i].right_width
        member.flat_width = flat

    # 挖方 / 回填（按标高分层、每层梯形）
    for member in snapshots:
        out = QDict()
        if not _member_dig_fill(member, out):
            errors[member.element.id] = errors.get(member.element.id) or "覆土不足或分层无效，未生成工程量。"
        results[member.element.id] = out

    # 围护量（每面 ×1）+ 支撑
    flat_total = _dim_sum(*(member.flat_width for member in snapshots))
    amount_dim = snapshots[0].info.amount_dim

    strut_emitted = False

    def _emit_face(face_work, face_depth: Dim, owner: _Member, note: str, support_flag: str) -> None:
        """一个面的围护量（类别 ``围护`` ×1）与支撑（围檩 ×1；贯通支撑整槽一次）。"""
        nonlocal strut_emitted
        out = results.setdefault(owner.element.id, QDict())
        works_quantities(
            face_work, face_depth, amount_dim, "F", owner.ad, owner.info, out, note,
            sides=1, width=flat_total, categories={"围护"},
        )
        if getattr(owner.element, support_flag):
            # 支撑行按公式类别识别（不再看 Z 键前缀）；做法与围护面同一个
            # （含换填层厚度的）档位，贯通支撑行只在首个勾选面出一次
            levels = list(face_work.levels)
            fixed_h = _dim_sum(*(dim(level.h) for level in levels if level.h >= 0))
            fixed_cnt = sum(1 for level in levels if level.h >= 0)
            for level in levels:
                if level.h >= 0:
                    height = dim(level.h)
                elif len(levels) > fixed_cnt:
                    height = (face_depth - fixed_h) / (len(levels) - fixed_cnt)
                else:
                    height = face_depth
                component = level.components[0] if level.components else None
                component_side_quantities(
                    component, height, flat_total, amount_dim, out,
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
            wet = member.flat_width * (member.depth - dim(1.0)) if member.depth.v > 1 else None
            precipitation.cal_precipitation(
                pp, work_well, pf, member.ad, info, member.depth, out,
                wet_dig=wet,
            )
        special = pf.components[0] if pf.components else None
        if special is not None:
            component_quantities(
                special, member.depth, member.flat_width, info.amount_dim, "F", out, "特殊地基"
            )
        foundation.cal_found(info, pf, pp, member.ad, out)
        if info.category == CATEGORY_ENCASED:
            foundation.encased_pipe_deduction(info, out)
        foundation.cal_pipes(info, out)
        out.scale(info.amount, expr=info.amount_dim.e)
    return results, errors


def _member_dig_fill(member: _Member, out: QDict) -> bool:
    """构件宽度剖面的挖方 / 分层回填（按标高分层、每层梯形，结果写入 ``out``）。

    标高事件集 = 回填分层界面（换填顶 / 垫层顶 / 坞膀下半顶 / 坞膀顶 /
    管顶 50cm 顶 / 覆土顶）+ 各侧放坡剖面的全部分级 / 平台折点（含相邻
    构件槽底标高）。事件之间宽度线性，单层面积用梯形 ``(w_下+w_上)/2*Δh``
    精确计算；每层按它所属的回填分层归类，挖方按层合并 term（说明 = 层名）。
    """
    info = member.info
    pp = info.pp
    pf = info.pf
    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    layers = backfill_layers(pp, pf, member.ad, info.size_h_dim, member.depth, cushion_name)
    # 层的高度带 (下界, 上界, 层厚, 说明)：自槽底向上累计，第 k 层占据
    # [Σh, Σh+h]（自构件槽底起算的高度区间）
    bands: list[tuple[str, Dim, Dim, Dim, str]] = []
    cum = dim(0.0)
    for key, layer, note in layers:
        if layer.v <= 0:
            continue
        bands.append((key, cum, cum + layer, layer, note))
        cum = cum + layer
    if not bands:
        return False
    total = cum

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
        low, high = _width_for_interval(member.profiles, lo, hi)
        # 线性宽度两端相等 = 恒宽层，退化为矩形（梯形公式的等底情形），
        # 避免把同一个宽度算式重复展开两遍
        if abs(low.v - high.v) <= 1e-12:
            area = low * height
        else:
            area = (low + high) / 2 * height
        if area.v == 0:
            continue
        produced = True
        out.add(key, area.v, area.e, note)
        dig.add_term(area.v, area.e, note)
    if not produced:
        out.discard(dig_key)
        return False
    if not dig.terms:
        out.discard(dig_key)
    return True
