"""合槽编组计算（父节点 / 子节点模型，见 docs/lr_enclosure_and_trench_group_design.md）。

断面从左到右的区间（每个区间归属一条构件）：

    [左边坡+左工作面·父PE/PW] [构件1本体] [中间区1·子1右PW] [构件2本体] …
    [构件n本体] [右工作面+右边坡·子n右PE/PW]

实现口径（等深 / 异深统一）：

* **每个构件一套"归属区"**：本体区（宽 b_i = 基础外皮宽）、左右工作面区
  （仅最外构件，按父 / 最右子 PW 查表）、相邻中间区的各半（构件间范围
  平分）、边缘边坡区（仅最外构件，做法取父 PE / 最右子右 PE 按各自槽深
  选择，折线含分级与平台）；
* **宽度函数分段线性**：本体 / 工作面恒宽；中间区在埋深差段线性收窄
  （等效坡系数 = 所选做法按坡高 ΔH 的各级放坡系数按级高加权，桩类为 0
  即直壁隔断）；边坡为折线。构件的分层界面与全部折点构成事件集，事件
  之间的带上宽度线性 → 梯形公式 ``(w1+w2)/2*Δ`` 精确；
* **回填正量 = 该构件归属区面积按它自己的分层界面归类**（材质 / 换填取
  其右原则 PE / 自己的 PF，与"子节点只影响自身范围"的编组语义一致）；
  比其槽底更深的归属区部分（中间坡楔形）追加为覆土层；挖方 = 同带面积
  之和进开挖定额键；逐管扣减（弓形 / 包封 / 箱涵）由 foundation 现状函数
  以同 key 负项合并；
* **围护量每面 ×1**（``sides=1``）：左边坡挂构件 1、右边坡挂构件 n、
  中间坡挂深度更深一侧的构件（做法按坡高 ΔH 选择）；支撑（Z 类）按归属
  构件朝向该面的支撑勾选，深度按面深减该构件换填（同单管支撑口径）；
* **降水逐构件**（湿土排水 = 归属带宽 ×（槽深−1m）的简化断面）；特殊地基
  按归属带宽代入 width；
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
    component_support_quantities,
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
# 归属区：深度带上的分段线性宽度（绝对深度自地面向下）
# --------------------------------------------------------------------------- #
class _Zone:
    """一个归属区：``band_area(a, b)`` 为深度带 [a, b] 上的断面面积（m²/延米）。

    宽度分段线性、折点由 :meth:`kinks` 报出；带内无折点时梯形公式精确。
    """

    def band_area_dim(self, a: float, b: float) -> Dim | None:
        raise NotImplementedError

    def kinks(self) -> list[float]:
        raise NotImplementedError


class _RectZone(_Zone):
    """恒宽区（本体 / 工作面）：深度 [0, top] 内宽 ``width``。"""

    def __init__(self, width: Dim, top: float, note: str) -> None:
        self.width = width
        self.top = top
        self.note = note

    def band_area_dim(self, a: float, b: float) -> Dim | None:
        lo, hi = max(a, 0.0), min(b, self.top)
        if hi <= lo:
            return None
        return self.width * dim(hi - lo)

    def kinks(self) -> list[float]:
        return [self.top]


class _MidZone(_Zone):
    """中间区（相邻构件的间距 g，构件间范围平分各取一半）。

    宽度（深度 d）：d ≤ H_浅 → g；H_浅 < d < H_深 → g − (d−H_浅)×s̄
    （坡从浅槽底边向深侧收，桩类 s̄=0 即直壁隔断、整区挖到深底）；
    更深 → 0。
    """

    def __init__(self, g: Dim, h_shallow: float, h_deep: float, slope: float, note: str) -> None:
        self.g = g
        self.h_shallow = h_shallow
        self.h_deep = h_deep
        self.slope = slope
        self.note = note

    def _width(self, d: float) -> float:
        """深度 d 处的中间区全宽（带端点取带内侧值：h_deep 处 = g−run / 直壁 = g）。"""
        if d <= self.h_shallow:
            return self.g.v
        if d > self.h_deep:
            return 0.0
        return max(0.0, self.g.v - (d - self.h_shallow) * self.slope)

    def band_area_dim(self, a: float, b: float) -> Dim | None:
        total = dim(0.0)
        for lo, hi in _clip_bands(a, b, self.kinks()):
            band = (dim(self._width(lo)) + dim(self._width(hi))) / 2 * dim(hi - lo)
            total = total + band
        return total / 2 if total.v != 0 else None  # 半区 = 面积平分

    def kinks(self) -> list[float]:
        return [self.h_shallow, self.h_deep]


class _SlopeZone(_Zone):
    """边坡区（分级放坡 + 平台）：折线 ``points`` = (绝对深度, 边坡外扩宽)。

    平台在切级高程为同深度两点（宽度跳变，跳变本身不贡献面积）；带面积按
    折线段与带的交集逐段梯形积分。
    """

    def __init__(self, points: list[tuple[float, float]], note: str) -> None:
        self.points = sorted(points, key=lambda item: item[0])
        self.note = note

    def band_area_dim(self, a: float, b: float) -> Dim | None:
        total = dim(0.0)
        pts = self.points
        for (d1, x1), (d2, x2) in zip(pts, pts[1:]):
            lo, hi = max(a, d1), min(b, d2)
            if hi <= lo or d2 <= d1:
                continue  # 带外 / 零长段（平台跳变，无面积）
            w_lo = x1 + (x2 - x1) * (lo - d1) / (d2 - d1)
            w_hi = x1 + (x2 - x1) * (hi - d1) / (d2 - d1)
            total = total + (dim(w_lo) + dim(w_hi)) / 2 * dim(hi - lo)
        return total if total.v != 0 else None

    def kinks(self) -> list[float]:
        return [point[0] for point in self.points]


def _clip_bands(a: float, b: float, kinks: list[float]) -> list[tuple[float, float]]:
    """把带 [a, b] 按折点切成无折点子带（线性宽度 → 梯形精确）。"""
    edges = sorted({a, b, *(k for k in kinks if a < k < b)})
    return [(lo, hi) for lo, hi in zip(edges, edges[1:]) if hi > lo]


def _slope_points(work, depth: float) -> list[tuple[float, float]]:
    """边坡折线（绝对深度, 外扩宽 m）：槽底 (H, 0) 分级放坡到地面，切级处加平台。

    级划分复用 :func:`groove.split_h_by_step`（levels[-1] 最靠近槽底）；平台宽
    取切级后靠地面那一级的 step_width（与 cal_groove 同口径）。
    """
    levels = list(work.levels)
    heights = [step.v for step in split_h_by_step(levels, dim(depth))]
    points: list[tuple[float, float]] = [(depth, 0.0)]
    cum = 0.0
    run = 0.0
    for step in range(len(levels) - 1, -1, -1):
        top = heights[step]
        segment = top - cum
        if segment > 0:
            points.append((depth - cum, run))
            run += segment * level_slope(levels[step]).v
            points.append((depth - top, run))
            cum = top
        if step > 0 and top != 0 and heights[step - 1] != top:
            run += levels[step - 1].step_width
            points.append((depth - top, run))
    return points


def _mid_slope_of(work, delta_h: float) -> float:
    """中间坡等效坡系数：所选做法各级放坡系数按级高加权（桩类 = 0）。"""
    if delta_h <= 0:
        return 0.0
    levels = list(work.levels)
    heights = [step.v for step in split_h_by_step(levels, dim(delta_h))]
    total = sum(
        (heights[index] - (heights[index - 1] if index else 0.0)) * level_slope(level).v
        for index, level in enumerate(levels)
    )
    return total / delta_h


# --------------------------------------------------------------------------- #
# 构件快照与总入口
# --------------------------------------------------------------------------- #
@dataclass
class _Member:
    """合槽成员（子节点）的计算快照。"""

    element: Element
    info: ElementInput
    ad: AtlasDims
    pe_r: object  # 右侧围护原则（编组时挖填 / 基础取侧自动置"R"）
    depth: Dim  # 槽底深 H_i（埋深 + 换填 + 壁厚 + 垫层）
    base_width: Dim  # 基础外皮宽 b_i（= 单管槽底宽去掉两侧工作面）
    zones: list = field(default_factory=list)
    flat_width: Dim = field(default_factory=lambda: dim(0.0))  # 平面归属带宽（降水 / 特殊地基代入用）


def _resolve_by_name(session, model, name: str | None):
    from sqlalchemy import select

    if not name:
        return None
    found_id = session.scalar(select(model.id).where(model.name == name))
    return session.get(model, found_id) if found_id is not None else None


def _first_of(session, model):
    from sqlalchemy import select

    return session.scalar(select(model).order_by(model.order_no, model.id))


def compute_group(group: TrenchGroup) -> tuple[dict[int, QDict], dict[int, str]]:
    """计算一个合槽组：返回 (构件 id → 工程量, 构件 id → 错误说明)。

    组员按 order_no 从左到右；原则缺失 / 无做法时相关构件带错误说明、其余
    构件照算（单条失败不拖垮整组，错误字符串挂在行上展示）。父节点零工程量。
    """
    from app.core.models.models import (
        PcpEnclosure,
        PcpFoundation,
        PcpPrecipitation,
        PcpWidth,
    )

    session = orm.session()
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    results: dict[int, QDict] = {}
    errors: dict[int, str] = {}
    if len(members) < 2:
        for member in members:
            errors[member.id] = "合槽组至少需要两条构件。"
        return results, errors

    # 逐成员快照（右 PE / PF / PP / PW 各自解析，失效回退第一条）
    snapshots: list[_Member] = []
    for element in members:
        pe_r = _resolve_by_name(session, PcpEnclosure, element.pe_right_name) or _first_of(session, PcpEnclosure)
        pf = _resolve_by_name(session, PcpFoundation, element.pf_name) or _first_of(session, PcpFoundation)
        pp = _resolve_by_name(session, PcpPrecipitation, element.pp_name) or _first_of(session, PcpPrecipitation)
        pw = _resolve_by_name(session, PcpWidth, element.pw_name) or _first_of(session, PcpWidth)
        if pe_r is None or pf is None or pp is None or pw is None:
            errors[element.id] = "缺少围护 / 地基 / 降水 / 面宽原则。"
            continue
        info = build_element_input(element, pe_r, pf, pp, pw)
        if info.amount == 0:
            errors[element.id] = "数量为 0，未生成工程量。"
            continue
        at = resolve_atlas(build_atlas_query(info, pe_r, pw))
        ad = atlas_dims(info, at)
        if ad.c1.v == 0:
            ad = ad.replace(c1=cushion_dim(pe_r))
        depth = info.depth_dim + (foundation_dim(pf) + ad.t + ad.c1) / 1000
        base_width = info.size_b_dim + scale_sum((ad.t, ad.a), 2.0) / 1000
        snapshots.append(
            _Member(element=element, info=info, ad=ad, pe_r=pe_r, depth=depth, base_width=base_width)
        )
    if len(snapshots) < 2:
        for element in members:
            errors.setdefault(element.id, "合槽组存在无效成员，整组未计算。")
        return results, errors

    # 父节点原则（左边缘）；缺失回退第一条
    pe_group = _resolve_by_name(session, PcpEnclosure, group.pe_name) or _first_of(session, PcpEnclosure)
    pw_group = _resolve_by_name(session, PcpWidth, group.pw_name) or _first_of(session, PcpWidth)
    if pe_group is None or pw_group is None:
        for member in snapshots:
            errors[member.element.id] = "父节点缺少围护 / 工作面宽原则。"
        return results, errors

    n = len(snapshots)
    # 间距 g_i = 子 i 的 PW 按其管径查（mm→m）；wL = 父 PW 按构件 1 查；
    # wR = 最右子 PW 按其自身管径查
    gaps = [
        dim(workwidth_of(snapshots[i].info.pw, snapshots[i].info)) / 1000
        for i in range(n - 1)
    ]
    w_left = dim(workwidth_of(pw_group, snapshots[0].info)) / 1000
    w_right = dim(workwidth_of(snapshots[n - 1].info.pw, snapshots[n - 1].info)) / 1000

    # 左 / 右边坡做法（按各自槽深选择）
    work_left = choice_work(pe_group, snapshots[0].depth.v)
    work_right = choice_work(snapshots[n - 1].pe_r, snapshots[n - 1].depth.v)
    if work_left is None or work_right is None:
        for member in snapshots:
            errors[member.element.id] = "边缘围护原则没有任何围护分级。"
        return results, errors

    # 中间坡（埋深差）：做法按坡高 ΔH 选自左构件的右原则
    mid_works: list = []
    mid_slopes: list[float] = []
    for i in range(n - 1):
        delta = abs(snapshots[i + 1].depth.v - snapshots[i].depth.v)
        work = choice_work(snapshots[i].pe_r, delta) if delta > 0 else None
        mid_works.append(work)
        mid_slopes.append(_mid_slope_of(work, delta) if work is not None else 0.0)

    # 逐构件的归属区 + 平面归属带宽
    for i, member in enumerate(snapshots):
        member.zones.append(_RectZone(member.base_width, member.depth.v, "本体"))
        if i == 0:
            member.zones.append(_RectZone(w_left, snapshots[0].depth.v, "左工作面"))
            member.zones.append(_SlopeZone(_slope_points(work_left, snapshots[0].depth.v), "左边坡"))
        if i == n - 1:
            member.zones.append(_RectZone(w_right, snapshots[n - 1].depth.v, "右工作面"))
            member.zones.append(_SlopeZone(_slope_points(work_right, snapshots[n - 1].depth.v), "右边坡"))
        if i > 0:  # 左邻中间区的右半
            left = snapshots[i - 1]
            h_s = min(left.depth.v, member.depth.v)
            h_d = max(left.depth.v, member.depth.v)
            member.zones.append(_MidZone(gaps[i - 1], h_s, h_d, mid_slopes[i - 1], "左中间区半宽"))
        if i < n - 1:  # 右邻中间区的左半
            right = snapshots[i + 1]
            h_s = min(member.depth.v, right.depth.v)
            h_d = max(member.depth.v, right.depth.v)
            member.zones.append(_MidZone(gaps[i], h_s, h_d, mid_slopes[i], "右中间区半宽"))
        flat = member.base_width
        if i == 0:
            flat = flat + w_left
        if i == n - 1:
            flat = flat + w_right
        if i > 0:
            flat = flat + gaps[i - 1] / 2
        if i < n - 1:
            flat = flat + gaps[i] / 2
        member.flat_width = flat

    # 挖方 / 回填（带积分）
    for member in snapshots:
        out = QDict()
        if not _member_dig_fill(member, out):
            errors[member.element.id] = errors.get(member.element.id) or "覆土不足或分层无效，未生成工程量。"
        results[member.element.id] = out

    # 围护量（每面 ×1）+ 支撑
    flat_total = w_left + w_right
    for i, member in enumerate(snapshots):
        flat_total = flat_total + member.base_width
        if i < n - 1:
            flat_total = flat_total + gaps[i]
    amount_dim = snapshots[0].info.amount_dim

    strut_emitted = False

    def _emit_face(face_pe, work, face_depth: Dim, owner: _Member, note: str, support_flag: str) -> None:
        """一个面的围护量（F 类 ×1）与支撑（围檩 ×1；贯通支撑整槽一次）。"""
        nonlocal strut_emitted
        out = results.setdefault(owner.element.id, QDict())
        works_quantities(work, face_depth, amount_dim, "F", owner.ad, owner.info, out, note, sides=1, width=flat_total)
        if getattr(owner.element, support_flag):
            # 支撑深度按面深减该构件换填（同单管支撑口径），≤0 不算；
            # 贯通支撑行只在首个勾选面出一次（左 → 右 → 中间坡的顺序）
            support_depth = face_depth - foundation_dim(owner.info.pf) / 1000
            support_work = choice_work(face_pe, support_depth.v)
            if support_work is not None and support_depth.v > 0:
                levels = list(support_work.levels)
                fixed_h = _dim_sum(*(dim(level.h) for level in levels if level.h >= 0))
                fixed_cnt = sum(1 for level in levels if level.h >= 0)
                for level in levels:
                    if level.h >= 0:
                        height = dim(level.h)
                    elif len(levels) > fixed_cnt:
                        height = (support_depth - fixed_h) / (len(levels) - fixed_cnt)
                    else:
                        height = support_depth
                    component = level.components[0] if level.components else None
                    component_support_quantities(
                        component, height, flat_total, amount_dim, out,
                        note=f"{note}·支撑", emit_strut=not strut_emitted,
                    )
                strut_emitted = True

    _emit_face(pe_group, work_left, snapshots[0].depth, snapshots[0], "围护·左侧", "support_left")
    _emit_face(snapshots[n - 1].pe_r, work_right, snapshots[n - 1].depth, snapshots[n - 1], "围护·右侧", "support_right")
    for i in range(n - 1):
        work = mid_works[i]
        if work is None:
            continue
        left, right = snapshots[i], snapshots[i + 1]
        delta = abs(right.depth.v - left.depth.v)
        if delta <= 0:
            continue
        # 中间坡挂深度更深一侧的构件；支撑勾选 = 深侧构件朝向该面的勾选
        deep, support_flag = (
            (left, "support_right") if left.depth.v >= right.depth.v else (right, "support_left")
        )
        _emit_face(snapshots[i].pe_r, work, dim(delta), deep, f"围护·中间坡{i + 1}", support_flag)

    # 逐构件：降水 / 特殊地基 / 管道基础 / 管材
    for member in snapshots:
        out = results.setdefault(member.element.id, QDict())
        info = member.info
        pf = info.pf
        pe_excvt = member.pe_r  # 编组时挖填 / 基础取侧自动置"R"
        work_well = choice_work(member.pe_r, member.depth.v)
        if info.pp is not None and work_well is not None:
            # 湿土排水 = 归属带宽 ×（槽深−1m）的简化断面
            wet = member.flat_width * (member.depth - dim(1.0)) if member.depth.v > 1 else None
            precipitation.cal_precipitation(
                info.pp, pe_excvt, work_well, pf, member.ad, info, member.depth, out,
                wet_dig=wet,
            )
        special = pf.components[0] if pf.components else None
        if special is not None:
            component_quantities(
                special, member.depth, member.flat_width, info.amount_dim, "F", out, "特殊地基"
            )
        foundation.cal_found(info, pe_excvt, member.ad, out)
        if info.category == CATEGORY_ENCASED:
            foundation.encased_pipe_deduction(info, out)
        foundation.cal_pipes(info, out)
        out.scale(info.amount, expr=info.amount_dim.e)
    return results, errors


def _member_dig_fill(member: _Member, out: QDict) -> bool:
    """构件归属区的挖方 / 分层回填（带积分，结果写入 ``out``）。

    分层界面来自该构件自己的 backfill_layers（绝对深度 = H_i − 自槽底累计）；
    比其槽底更深的归属区部分（中间坡楔形）追加为覆土层。挖方按层合并 term
    （说明 = 层名），与单管路径同风格。
    """
    info = member.info
    pe = member.pe_r
    pf = info.pf
    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    layers = backfill_layers(pe, pf, member.ad, info.size_h_dim, member.depth, cushion_name)
    # 层的绝对深度带 (浅端, 深端)：层列表自槽底向上累计，第 k 层占据
    # [H−Σh, H−Σh+h]（自地面起算的深度区间）
    bands: list[tuple[str, float, float, str]] = []
    cum = 0.0
    for key, layer, note in layers:
        if layer.v <= 0:
            continue
        deep = member.depth.v - cum
        shallow = deep - layer.v
        bands.append((key, shallow, deep, note))
        cum += layer.v
    max_depth = max(
        (max(zone.kinks()) for zone in member.zones if zone.kinks()),
        default=0.0,
    )
    max_depth = max(max_depth, member.depth.v)
    # 比槽底更深的归属区（中间坡楔形）：按覆土层追加
    if max_depth > member.depth.v + 1e-9:
        bands.append((f"回填|{pe.cover}|m3", member.depth.v, max_depth, "覆土(深区)"))
    if not bands:
        return False

    dig_key = f"开挖|{pe.excvt}|m3"
    dig = out.add(dig_key, 0.0)
    dig.terms.clear()
    dig.value = 0.0
    produced = False
    for key, a, b, note in bands:
        if b <= a:
            continue
        layer_area = dim(0.0)
        for zone in member.zones:
            part = zone.band_area_dim(a, b)
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
