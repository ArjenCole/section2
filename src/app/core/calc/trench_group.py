"""合槽编组计算（父节点 / 子节点模型，见 docs/lr_enclosure_and_trench_group_design.md）。

断面从左到右的区间（每个区间归属一条构件）：

    [左边坡+左工作面·首构件左PE/自身PW] [构件1本体]
    [相邻区1·浅侧工作面 + 深侧放坡] [构件2本体] …
    [构件n本体] [右工作面+右边坡·末构件右PE/自身PW]

实现口径（等深 / 异深统一）：

* **父节点不持有围护 / 面宽原则**：父节点零工程量、零几何，只作合计视图；
  全部原则取子构件自己的。
* **每个构件一套"归属区"**：本体区（宽 b_i = 基础外皮宽）、工作面区
  （宽按**自己的**面宽原则 + 自身管径查表）、内侧放坡区（仅深侧构件）、
  边缘边坡区（仅首 / 末构件）。首构件左边缘取``pe_left_name``、末构件
  右边缘取``pe_right_name``，中间构件的左右侧只在与邻居的相邻区里生效。
* **相邻区**：
  - 埋深相同 → 两侧围护均为 "-"（等同 1:0、高 0 的围护），几何 =
    左构件右侧工作面 + 右构件左侧工作面；
  - 埋深不同 → 浅侧围护 "-"（自身工作面宽 + 虚拟垂直空围护），深侧围护
    由用户选择（默认库中第一条）并向浅侧槽底放坡；坡与浅槽底的交点即
    浅侧虚拟垂直围护的水平位置。相邻区宽 = 浅侧工作面宽 + 深侧放坡水平
    投影（分级 / 平台按做法逐级累加）。
* **挖填拆分**：以浅侧虚拟垂直围护为分界线——浅侧构件得工作面矩形，
  深侧构件得内侧放坡楔形 + 浅槽底以上的垂直条带（宽度 = 放坡水平投影）。
* **宽度函数分段线性**：本体 / 工作面恒宽；内侧放坡区为折线（含平台
  跳变）；边缘边坡为折线。构件的分层界面与全部折点构成事件集，事件
  之间的带上宽度线性 → 梯形公式 ``(w1+w2)/2*Δ`` 精确。
* **回填正量 = 该构件归属区面积按它自己的分层界面归类**（材质 / 换填取
  自身围护原则 PE / 自己的 PF）；比其槽底更深的归属区部分追加为覆土层；
  挖方 = 同带面积之和进开挖定额键；逐管扣减（弓形 / 包封 / 箱涵）由
  foundation 现状函数以同 key 负项合并。
* **围护量每面 ×1**（``sides=1``）：左边坡挂首构件（其左原则）、右边坡
  挂末构件（其右原则）、内侧坡挂深侧构件（其朝向该面的原则）；等深相邻
  面不出围护量。支撑行按公式类别（``支撑``）识别，按归属构件朝向该面的
  支撑勾选输出；做法档位与围护面共用同一个**含换填层厚度**的面深。
* **降水逐构件**（湿土排水 = 归属带宽 ×（槽深−1m）的简化断面）；特殊地基
  按归属带宽代入 width。
* **父节点零工程量**：全部输出挂在子构件名下，每构件量 × L_组（编组时
  校验组员数量一致）。
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
# 归属区：高度带上的分段线性宽度（自构件槽底向上累计，算式不预运算）
# --------------------------------------------------------------------------- #
class _Zone:
    """一个归属区：``area_in(lo, hi, height)`` 为高度带 [lo, hi] 上的断面面积。

    ``lo`` / ``hi`` 是自**构件槽底**向上的累计高度（Dim），``height`` 为该带厚度
    （Dim，数值等于 hi−lo）。宽度以 Dim 分段线性参与运算，放坡系数与层厚都按
    算式原文展开，不做提前运算。
    """

    top: Dim

    def area_in(self, lo: Dim, hi: Dim, height: Dim) -> Dim | None:
        raise NotImplementedError


class _RectZone(_Zone):
    """恒宽区（本体 / 工作面）：高度 [0, top] 内宽 ``width``。"""

    def __init__(self, width: Dim, top: Dim, note: str) -> None:
        self.width = width
        self.top = top
        self.note = note

    def area_in(self, lo: Dim, hi: Dim, height: Dim) -> Dim | None:
        if hi.v <= 0 or lo.v >= self.top.v:
            return None
        if hi.v > self.top.v:
            # 带超出区顶（中间坡楔形追加的覆土层）：只算区内的剩余厚度
            return self.width * (self.top - lo)
        return self.width * height


@dataclass(frozen=True)
class _SlopeSegment:
    """一段等坡线：高度 ``t1`` 处宽 ``w1``，到 ``t2`` 按 ``slope`` 线性外扩。"""

    t1: Dim
    w1: Dim
    slope: Dim
    t2: Dim

    def width_at(self, t: Dim) -> Dim:
        step = t - self.t1
        return self.w1 if step.v == 0 else self.w1 + self.slope * step


class _SlopeZone(_Zone):
    """边坡区（分级放坡 + 平台）：侧宽按等坡段积分，平台跳变不贡献面积。"""

    def __init__(self, segments: list[_SlopeSegment], top: Dim, note: str) -> None:
        self.segments = segments
        self.top = top
        self.note = note

    def area_in(self, lo: Dim, hi: Dim, height: Dim) -> Dim | None:
        total = dim(0.0)
        covered = False
        for segment in self.segments:
            part_lo = lo if lo.v > segment.t1.v else segment.t1
            part_hi = hi if hi.v < segment.t2.v else segment.t2
            if part_hi.v <= part_lo.v:
                continue  # 带外 / 零长段（平台跳变，无面积）
            # 整带落在一段内时直接取层厚算式，避免出现 hi−lo 的重复展开
            part_height = (
                height
                if part_lo.v == lo.v and part_hi.v == hi.v
                else part_hi - part_lo
            )
            total = total + (
                segment.width_at(part_lo) + segment.width_at(part_hi)
            ) / 2 * part_height
            covered = True
        return total if covered else None


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


def _internal_slope_zone(
    work, h_deep: Dim, h_shallow: Dim, note: str
) -> _SlopeZone | None:
    """内侧放坡区：深侧槽底放坡到浅槽底，以上为虚拟垂直围护（恒宽到地面）。"""
    delta = h_deep - h_shallow
    if delta.v <= 0 or work is None:
        return None
    segments, run = _slope_profile(work, delta)
    if h_shallow.v > 1e-9:
        segments.append(_SlopeSegment(t1=delta, w1=run, slope=dim(0.0), t2=h_deep))
    return _SlopeZone(segments, h_deep, note)


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
    zones: list = field(default_factory=list)
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

    # 逐构件的归属区 + 平面归属带宽（规则 6：工作面宽用自己的 PW）
    for i, member in enumerate(snapshots):
        member.zones.append(_RectZone(member.base_width, member.depth, "本体"))
        if i == 0:
            member.zones.append(_RectZone(member.work_width, member.depth, "左工作面"))
            segments, _run = _slope_profile(work_left, member.depth)
            member.zones.append(_SlopeZone(segments, member.depth, "左边坡"))
        else:
            pair = pairs[i - 1]
            if pair.deep is member:  # 自身更深：左侧内侧放坡
                zone = _internal_slope_zone(
                    pair.work, member.depth, snapshots[i - 1].depth, "左侧中间坡"
                )
                if zone is not None:
                    member.zones.append(zone)
            else:  # 自身更浅 / 等深：左侧工作面（虚拟垂直围护）
                member.zones.append(_RectZone(member.work_width, member.depth, "左工作面"))
        if i == n - 1:
            member.zones.append(_RectZone(member.work_width, member.depth, "右工作面"))
            segments, _run = _slope_profile(work_right, member.depth)
            member.zones.append(_SlopeZone(segments, member.depth, "右边坡"))
        else:
            pair = pairs[i]
            if pair.deep is member:  # 自身更深：右侧内侧放坡
                zone = _internal_slope_zone(
                    pair.work, member.depth, snapshots[i + 1].depth, "右侧中间坡"
                )
                if zone is not None:
                    member.zones.append(zone)
            else:  # 自身更浅 / 等深：右侧工作面（虚拟垂直围护）
                member.zones.append(_RectZone(member.work_width, member.depth, "右工作面"))
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

    # 挖方 / 回填（带积分）
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
    """构件归属区的挖方 / 分层回填（带积分，结果写入 ``out``）。

    分层界面来自该构件自己的 backfill_layers（自槽底累计高度，层厚算式原文
    参与面积计算）；比其槽底更深的归属区部分（中间坡楔形）追加为覆土层。
    挖方按层合并 term（说明 = 层名），与单管路径同风格。
    """
    info = member.info
    pp = info.pp
    pf = info.pf
    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    layers = backfill_layers(pp, pf, member.ad, info.size_h_dim, member.depth, cushion_name)
    # 层的高度带 (下界, 上界, 层厚)：自槽底向上累计，第 k 层占据
    # [Σh, Σh+h]（自构件槽底起算的高度区间）
    bands: list[tuple[str, Dim, Dim, Dim, str]] = []
    cum = dim(0.0)
    for key, layer, note in layers:
        if layer.v <= 0:
            continue
        bands.append((key, cum, cum + layer, layer, note))
        cum = cum + layer
    max_top = max(
        (zone.top for zone in member.zones),
        key=lambda item: item.v,
        default=member.depth,
    )
    # 比槽底更高的归属区（中间坡楔形）：按覆土层追加
    if max_top.v > member.depth.v + 1e-9:
        bands.append(
            (f"回填|{pp.cover}|m3", member.depth, max_top, max_top - member.depth, "覆土(深区)")
        )
    if not bands:
        return False

    dig_key = f"开挖|{pp.excvt}|m3"
    dig = out.add(dig_key, 0.0)
    dig.terms.clear()
    dig.value = 0.0
    produced = False
    for key, lo, hi, height, note in bands:
        if hi.v <= lo.v:
            continue
        layer_area = dim(0.0)
        for zone in member.zones:
            part = zone.area_in(lo, hi, height)
            if part is not None:
                layer_area = layer_area + part
        if layer_area.v == 0:
            continue
        produced = True
        out.add(key, layer_area.v, layer_area.e, note)
        dig.add_term(layer_area.v, layer_area.e, note)
    if not produced:
        out.discard(dig_key)
        return False
    if not dig.terms:
        out.discard(dig_key)
    return True
