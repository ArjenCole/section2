"""管道基础与管材计算（复刻旧版 mcE1~mcE6 的 cal_found / cal_pipes）。

* 直埋管道（mcE1）：砼基础体积扣弓形占位、模板、垫层扣减、坞膀/上半回填扣减；
* 包封埋管（mcE2）：垫层 + 包封混凝土/模板 + 回填扣减 + 管材（包封混凝土扣管位）；
* 箱涵（mcE3）/ 管廊（mcE6）：垫层、底板、箱涵壁、顶板、钢筋（含钢量）与扣减；
* 顶管（mcE4）/ 牵引管（mcE5）：只有管材。

全部为每延米量，由引擎统一 ×数量。各条量的算式都由 :class:`Dim` 拼出、
不做预运算：基础宽高、外径、弓形面积、钢筋合计等都保留 管径 / 图集参数
与构件参数原文的推导。**记法口径**：几何量全程 mm 记法（``Dim.s=3``），
面积 / 体积式记录时统一追加 ``/10^6``（体积）、``/10^3``（面积）；含钢量的
``/1000``（kg/m³ → t/m³）是系数换算，保留原样，见 :mod:`app.core.calc.tracer`。
"""

from __future__ import annotations

import math

from app.core.models.models import CATEGORY_BURIED, CATEGORY_BOX_CULVERT, CATEGORY_ENCASED, CATEGORY_GALLERY
from app.core.calc.measures import AtlasDims
from app.core.calc.tracer import Dim, QDict, dim, dim_max, dim_min, mm, mm_dim, mm_of_m, fmt, scale_sum, tag_dim, wrap


def _rect_geometry(z0: float, z1: float, half_width: float) -> tuple[float, float, float, float, float, float]:
    """矩形断面范围（梯形几何的等宽特例）：自槽底 [z0, z1]，左右缘 ±half_width。

    供详情弹窗把分项行高亮到断面图上；弓形 / 圆形扣减用它做外接矩形近似。
    """
    return (z0, z1, -half_width, half_width, -half_width, half_width)


def _rect_geometry(z0: float, z1: float, half_width: float) -> tuple[float, float, float, float, float, float]:
    """矩形断面范围（梯形几何的等宽特例）：自槽底 [z0, z1]，左右缘 ±half_width。

    供详情弹窗把分项行高亮到断面图上。
    """
    return (z0, z1, -half_width, half_width, -half_width, half_width)


def _segment_polygon(z_bottom: float, r: float, h_lo: float, h_hi: float, samples: int = 12) -> tuple:
    """圆管在自管底高度 [h_lo, h_hi] 内的弓形段多边形（本体中心相对，m）。

    弦线 + 采样弧线，供详情弹窗按真实形状（弓形 / 半圆）高亮。
    """
    def chord(h: float) -> float:
        return math.sqrt(max(h * (2.0 * r - h), 0.0))

    pts: list[tuple[float, float]] = [
        (-chord(h_lo), z_bottom + h_lo),
        (chord(h_lo), z_bottom + h_lo),
    ]
    for k in range(1, samples):
        h = h_lo + (h_hi - h_lo) * k / samples
        pts.append((chord(h), z_bottom + h))
    pts.append((chord(h_hi), z_bottom + h_hi))
    pts.append((-chord(h_hi), z_bottom + h_hi))
    for k in range(samples - 1, 0, -1):
        h = h_lo + (h_hi - h_lo) * k / samples
        pts.append((-chord(h), z_bottom + h))
    return tuple(pts)


def _circle_area_below(h: Dim, r: Dim) -> Dim:
    """圆内自管底到高度 h 的面积（Excel 语法）：
    ``R²·ACOS((R−h)/R) − (R−h)·√(h·(2R−h))``。h 须在 [0, 2R] 内（调用方截断）。
    """
    h_e, r_e = wrap(h.e), wrap(r.e)
    # 乘方统一写 Excel 的 ^（不再用 POWER 函数）；底数可能是复合式，按乘方
    # 底数位置用 tight 括号保护，避免 (600/2)^2 写成 600/2^2。
    r_sq = wrap(r.e, tight=True)
    expr = (
        f"{r_sq}^2*ACOS(({r_e}-{h_e})/({r_e}))"
        f"-({r_e}-{h_e})*SQRT({h_e}*(2*({r_e})-{h_e}))"
    )
    ratio = max(-1.0, min(1.0, (r.v - h.v) / r.v))
    value = (
        r.v * r.v * math.acos(ratio)
        - (r.v - h.v) * math.sqrt(max(h.v * (2.0 * r.v - h.v), 0.0))
    )
    return Dim(value, expr, h.tags + r.tags, h.s + r.s)


def _circle_area_between(h_lo: Dim, h_hi: Dim, r: Dim) -> Dim:
    """圆管在自管底高度 [h_lo, h_hi] 内的截面面积（两端弦之间）。"""
    return _circle_area_below(h_hi, r) - _circle_area_below(h_lo, r)


def _emit_footprint_slices(out: QDict, bands, found_h: Dim, width: Dim) -> None:
    """基础占位按实际分层标高切片：每个重叠分层一条矩形扣减（负项）。

    统一回填标高下分层界面会移动，占位必须落到几何上真正覆盖它的分层里。
    """
    for b_key, b_lo, b_hi, _layer, _b_note in bands:
        lo_dim = dim_max(b_lo, dim(0.0))
        hi_dim = dim_min(b_hi, found_h)
        if hi_dim.v - lo_dim.v <= 1e-9:
            continue
        area = (hi_dim - lo_dim) * width
        out.add(
            b_key,
            -area.v,
            area,
            "扣基础占位",
            tags=width.tags,
            geometry=_rect_geometry(lo_dim.v, hi_dim.v, width.v / 2.0),
        )


def _emit_pipe_slices(out: QDict, bands, z_bottom: Dim, outside: Dim, z_floor: Dim) -> None:
    """管位占用按实际分层标高切片：每个重叠分层一条弓形 / 半圆扣减（负项）。

    圆管自 ``z_bottom``（垫层顶）到管顶；只扣 ``z_floor``（基础顶，基础混凝土
    已扣自己范围内的管位）以上的部分；管中心必为切点，每片不超过半圆。
    """
    r = outside / 2
    z_center = z_bottom + r
    for b_key, b_lo, b_hi, _layer, _b_note in bands:
        lo_dim = dim_max(b_lo, z_bottom, z_floor)
        hi_dim = dim_min(b_hi, z_bottom + outside)
        if hi_dim.v - lo_dim.v <= 1e-9:
            continue
        if lo_dim.v < z_center.v < hi_dim.v:
            pieces = [(lo_dim, z_center), (z_center, hi_dim)]
        else:
            pieces = [(lo_dim, hi_dim)]
        for h_lo, h_hi in pieces:
            height_lo, height_hi = h_lo - z_bottom, h_hi - z_bottom
            area = _circle_area_between(height_lo, height_hi, r)
            is_half = abs(height_lo.v - r.v) < 1e-9 and abs(height_hi.v - 2.0 * r.v) < 1e-9
            out.add(
                b_key,
                -area.v,
                area,
                f"扣管位·{'半圆' if is_half else '弓形'}",
                tags=area.tags,
                geometry=_segment_polygon(z_bottom.v, r.v, height_lo.v, height_hi.v),
            )


def add_dim(out: QDict, key: str, quantity: Dim, note: str = "", geometry=None) -> None:
    """按 :class:`Dim` 输出一条工程量：数值取 ``v``，算式取 ``e``（记法指数随之记录）。

    ``quantity.tags`` 供展示层识别槽底宽 / 外径 / 弓形占位等中间量；
    ``geometry`` 为该项的断面范围（见 :func:`_rect_geometry`）。
    """
    out.add(key, quantity.v, quantity, note, tags=quantity.tags, geometry=geometry)


def _circle(diameter: float) -> float:
    """圆面积 m²（旧版 mcE1.Circle）。"""
    return math.pi * diameter * diameter / 4.0


def _bow(diameter: float, angle: float) -> float:
    """弓形面积 m²（旧版 mcE1.Bow：扇形 − 三角形）。"""
    sector = _circle(diameter) * angle / 360.0
    triangle = 0.5 * diameter * diameter / 4.0 * math.sin(angle / 180.0 * math.pi)
    return sector - triangle


def _bow_expr(diameter: Dim, angle: float) -> str:
    """弓形面积的代入算式（Excel 语法，π 写 ``PI()``）；外径带自己的算式。"""
    d = wrap(diameter.e)
    return (
        f"PI()*{d}*{d}/4*{fmt(angle)}/360"
        f"-{d}*{d}/8*SIN({fmt(angle)}*PI()/180)"
    )


def _bow_dim(diameter: Dim, angle: float) -> Dim:
    """弓形占位（数值按 mcE1.Bow，算式按 π=3.141593 的代入式；mm² 记法）。"""
    return tag_dim(
        Dim(
            _bow(diameter.v, angle),
            _bow_expr(diameter, angle),
            diameter.tags,
            diameter.s * 2,
        ),
        "弓形占位面积",
        f"外径与 {fmt(angle)}° 基础角度",
    )


def _outside_dn(info, ad: AtlasDims) -> Dim:
    """管道外径 oD（mm 记法）：构件库 / 详情面板的 oD，旧数据按 iD+2t 兜底。"""
    return tag_dim(ad.od, "管道外径（mm）", "管道外径 oD")


def cal_found(info, pf, pp, ad: AtlasDims, out: QDict, bands=None) -> None:
    """管道基础 / 包封 / 箱涵 / 管廊本体量与占土扣减（每延米）。

    ``pf``（地基原则）提供砼基础开关 / 基础角度 / 垫层，``pp``（挖填降水原则）
    提供回填材质（坞膀下半 / 上半）。``bands``（合槽路径传入）为该构件的
    回填分层带 (定额键, 下界, 上界, 层厚, 说明)：垫层占位与管位扣减按实际
    分层标高切片、扣到几何上真正覆盖它的分层（统一回填标高下分层界面会
    移动，固定键机械对应会错位）；不传时维持固定扣减项（单构件口径）。
    """
    if info.category == CATEGORY_BURIED:
        _found_pipe(info, pf, pp, ad, out, bands=bands)
    elif info.category == CATEGORY_ENCASED:
        _found_encased(info, pf, pp, ad, out)
    elif info.category == CATEGORY_BOX_CULVERT:
        _found_box(info, pf, pp, ad, out, prefix="箱涵", wall_key="箱涵壁")
    elif info.category == CATEGORY_GALLERY:
        _found_box(info, pf, pp, ad, out, prefix="管廊", wall_key="管廊壁")


def _lower_half_minus_bow_polygon(
    z_bottom: float, r: float, angle: float, samples: int = 12
) -> tuple:
    """下半圆扣除弓形（弦以下）后的区域多边形（本体中心相对，m）。

    边界：左半圆端 → 左下弧到弦左端 → 弦 → 弦右端 → 右下弧到右半圆端 →
    直径闭合。用于“坞膀扣弓形”的高亮，避免退化成外包矩形。
    """
    half = math.radians(angle) / 2.0
    chord_y = r - r * math.cos(half)
    points: list[tuple[float, float]] = [(-r, z_bottom + r)]
    # 左下弧：圆心 (0, r)，从 π 到 3π/2 - half
    for k in range(1, samples + 1):
        theta = math.pi + (math.pi / 2 - half) * k / samples
        points.append(
            (r * math.cos(theta), z_bottom + r + r * math.sin(theta))
        )
    # 弦：从左端到右端
    points.append((r * math.sin(half), z_bottom + chord_y))
    # 右下弧：从 3π/2 + half 到 2π
    for k in range(1, samples + 1):
        theta = 3 * math.pi / 2 + half + (math.pi / 2 - half) * k / samples
        points.append(
            (r * math.cos(theta), z_bottom + r + r * math.sin(theta))
        )
    return tuple(points)


def _found_pipe(info, pf, pp, ad: AtlasDims, out: QDict, bands=None) -> None:
    """直埋管道基础（旧版 mcE1.cal_found）。"""
    if not info.pipes:
        return
    outside = _outside_dn(info, ad)
    half_circle = _circle(outside.v) / 2.0
    angle = float(pf.found_angle)
    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    remain = mm_of_m(info.depth_dim) + ad.t + ad.c1

    if pf.con_found and ("混凝土" in info.pipes[0].mat or "砼" in info.pipes[0].mat):
        width = (
            info.size_b_dim + scale_sum((ad.t, ad.a), 2.0)
        ).named("基础宽度", "断面宽 + 2×(壁厚+工作面加宽)")
        found_h = ad.c1 + ad.c2
        found_h = tag_dim(found_h, "基础厚度", "垫层厚 C1 + 基础厚 C2")
        found = (found_h * width).named("基础断面面积", "基础厚度 × 基础宽度")
        bow = _bow_dim(outside, angle)
        add_dim(
            out,
            "管道基础|混凝土|m3",
            found - bow,
            f"基础 {fmt(found.v)} − {fmt(angle)}° 弓形占位 {fmt(bow.v)}",
            geometry=_rect_geometry(0.0, found_h.v, width.v / 2.0),
        )
        add_dim(out, "管道基础|模板|m2", found_h * 2,
                geometry=_rect_geometry(0.0, found_h.v, width.v / 2.0))

        if bands is None:
            deducted = dim_min(remain, found_h)
            add_dim(out, f"垫层|{cushion_name}|m3", -(deducted * width), "垫层扣基础占位",
                    geometry=_rect_geometry(0.0, deducted.v, width.v / 2.0))
            remain = remain - deducted
        else:
            # 按实际分层标高切片：占位与管位落到几何上真正覆盖它的分层
            #（统一回填标高下分层界面会移动，固定键机械对应会错位）
            _emit_footprint_slices(out, bands, found_h, width)
            _emit_pipe_slices(out, bands, ad.c1, outside, found_h)
            return  # 切片口径已完成，跳过固定坞膀扣减（砂基础分支不切片、走固定项）
    else:
        deducted = dim_min(remain, ad.c2) if ad.c2.v > 0 else mm(0.0)
        remain = remain - deducted
        # 弓形占位 = 管底弓形（管底自垫层顶起），高亮按实际圆弧段绘制
        bow = _bow_dim(outside, angle)
        chord_height = outside.v / 2 - outside.v / 2 * math.cos(
            angle / 2 / 180 * math.pi
        )
        bow_polygon = _segment_polygon(
            ad.c1.v, outside.v / 2.0, 0.0, chord_height
        )
        add_dim(out, f"垫层|{cushion_name}|m3", -bow, "垫层扣弓形",
                geometry=bow_polygon)

    chord_height = outside.v / 2 - outside.v / 2 * math.cos(angle / 2 / 180 * math.pi)
    remain = remain - dim_min(remain, mm(chord_height * 1000.0))

    # 管底自垫层顶（C1）起：坞膀扣弓形占下半管带、上半扣半圆占上半管带
    add_dim(
        out,
        f"回填|{pp.dock_l}|m3",
        Dim(
            -(half_circle - _bow(outside.v, angle)),
            f"PI()*{wrap(outside.e)}*{wrap(outside.e)}/8-({_bow_expr(outside, angle)})",
            outside.tags + bow.tags,
            outside.s * 2,
        ),
        "坞膀扣弓形",
        geometry=_lower_half_minus_bow_polygon(
            ad.c1.v, outside.v / 2.0, angle
        ),
    )
    add_dim(
        out,
        f"回填|{pp.dock_h}|m3",
        Dim(
            -half_circle,
            f"PI()*{wrap(outside.e)}*{wrap(outside.e)}/8",
            outside.tags,
            outside.s * 2,
        ),
        "上半回填扣半圆",
        geometry=_segment_polygon(
            ad.c1.v, outside.v / 2.0, outside.v / 2.0, outside.v
        ),
    )


def _found_encased(info, pf, pp, ad: AtlasDims, out: QDict) -> None:
    """包封埋管（旧版 mcE2.cal_found）。"""
    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    remain = mm_of_m(info.depth_dim) + ad.t + ad.c1
    # 包封底自垫层顶（C1）起，高 = 包封高；高亮用外接矩形
    z_bottom = ad.c1.v
    encased_rect = _rect_geometry(
        z_bottom, z_bottom + info.size_h_dim.v, info.size_b_dim.v / 2.0
    )

    cushion_half = (info.size_b_dim.v + ad.a.v * 2.0) / 2.0
    add_dim(out, "垫层|混凝土|m3", ad.c1 * (info.size_b_dim + ad.a * 2),
            geometry=_rect_geometry(0.0, ad.c1.v, cushion_half))
    add_dim(out, "垫层|模板|m2", ad.c1 * 2,
            geometry=_rect_geometry(0.0, ad.c1.v, cushion_half))

    width = (
        info.size_b_dim + scale_sum((ad.t, ad.a), 2.0)
    ).named("基础宽度", "断面宽 + 2×(壁厚+工作面加宽)")
    deducted = dim_min(remain, ad.c1 + ad.c2)
    add_dim(out, f"垫层|{cushion_name}|m3", -(deducted * width), "垫层扣基础占位",
            geometry=_rect_geometry(0.0, deducted.v, width.v / 2.0))
    remain = remain - deducted

    add_dim(out, "包封|混凝土|m3", info.size_b_dim * info.size_h_dim, "包封混凝土",
            geometry=encased_rect)
    add_dim(out, "包封|模板|m2", info.size_h_dim * 2, "包封模板", geometry=encased_rect)

    used = dim_min(remain, info.size_h_dim / 2)
    used0 = used.v
    add_dim(out, f"回填|{pp.dock_l}|m3", -(info.size_b_dim * used), "坞膀扣包封",
            geometry=_rect_geometry(z_bottom, z_bottom + used0, info.size_b_dim.v / 2.0))
    remain = remain - used
    used = dim_min(remain, info.size_h_dim / 2)
    add_dim(out, f"回填|{pp.dock_h}|m3", -(info.size_b_dim * used), "上半扣包封",
            geometry=_rect_geometry(z_bottom + used0, z_bottom + used0 + used.v,
                                    info.size_b_dim.v / 2.0))


def _found_box(info, pf, pp, ad: AtlasDims, out: QDict, *, prefix: str, wall_key: str) -> None:
    """箱涵 / 管廊（旧版 mcE3 / mcE6.cal_found）。"""
    bt = tag_dim(mm_dim(info.param_dim("底板厚", 400)), "底板厚", "构件参数·底板厚")
    tt = tag_dim(mm_dim(info.param_dim("顶板厚", 300)), "顶板厚", "构件参数·顶板厚")
    ot = tag_dim(mm_dim(info.param_dim("外壁厚", 350)), "外壁厚", "构件参数·外壁厚")
    it = tag_dim(mm_dim(info.param_dim("内壁厚", 250)), "内壁厚", "构件参数·内壁厚")
    ic = tag_dim(info.param_dim("内壁", 0), "内壁数量", "构件参数·内壁")
    steel_rate = tag_dim(
        info.param_dim("含钢量", 150) / 1000, "含钢量", "构件参数·含钢量"
    )

    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    remain = mm_of_m(info.depth_dim) + ad.t + ad.c1
    # 箱涵本体自垫层顶（C1）起：底板 / 墙 / 顶板各自的矩形范围
    z_bottom = ad.c1.v
    size_b = info.size_b_dim.v
    size_h = info.size_h_dim.v
    bt_v, tt_v, ot_v = bt.v, tt.v, ot.v

    add_dim(out, f"{prefix}|垫层|m3", ad.c1 * (info.size_b_dim + ad.a * 2),
            geometry=_rect_geometry(0.0, z_bottom, (size_b + ad.a.v * 2.0) / 2.0))
    add_dim(out, f"{prefix}|垫层模板|m2", ad.c1 * 2,
            geometry=_rect_geometry(0.0, z_bottom, (size_b + ad.a.v * 2.0) / 2.0))

    width = (
        info.size_b_dim + scale_sum((ad.t, ad.a), 2.0)
    ).named("基础宽度", "断面宽 + 2×(壁厚+工作面加宽)")
    deducted = dim_min(remain, ad.c1 + ad.c2)
    add_dim(out, f"垫层|{cushion_name}|m3", -(deducted * width), "垫层扣基础占位",
            geometry=_rect_geometry(0.0, deducted.v, width.v / 2.0))
    remain = remain - deducted

    bottom = info.size_b_dim * bt
    add_dim(out, f"{prefix}|底板|m3", bottom,
            geometry=_rect_geometry(z_bottom, z_bottom + bt_v, size_b / 2.0))
    add_dim(out, f"{prefix}|底板模板|m2", bt * 2,
            geometry=_rect_geometry(z_bottom, z_bottom + bt_v, size_b / 2.0))
    wall = (info.size_h_dim - bt) * ot * 2 + (info.size_h_dim - bt - tt) * ic * it
    add_dim(out, f"{prefix}|{wall_key}|m3", wall,
            geometry=_rect_geometry(z_bottom + bt_v, z_bottom + size_h - tt_v, size_b / 2.0))
    wall_form = (info.size_h_dim - bt) * 2 * 2 + (info.size_h_dim - bt - tt) * ic * 2
    add_dim(out, f"{prefix}|{wall_key}模板|m2", wall_form,
            geometry=_rect_geometry(z_bottom + bt_v, z_bottom + size_h - tt_v, size_b / 2.0))
    roof = (info.size_b_dim - ot * 2) * tt
    roof_rect = _rect_geometry(z_bottom + size_h - tt_v, z_bottom + size_h,
                               (size_b - ot_v * 2.0) / 2.0)
    add_dim(out, f"{prefix}|顶板|m3", roof, geometry=roof_rect)
    add_dim(out, f"{prefix}|顶板模板|m2", info.size_b_dim - ot * 2, geometry=roof_rect)

    steel_rect = _rect_geometry(z_bottom, z_bottom + size_h, size_b / 2.0)
    add_dim(out, f"{prefix}|钢筋|t", steel_rate * (bottom + wall + roof),
            "钢筋 = 含钢量 × 混凝土合计", geometry=steel_rect)

    used = dim_min(remain, info.size_h_dim / 2)
    used0 = used.v
    add_dim(out, f"回填|{pp.dock_l}|m3", -(info.size_b_dim * used), "坞膀扣箱涵",
            geometry=_rect_geometry(z_bottom, z_bottom + used0, size_b / 2.0))
    remain = remain - used
    used = dim_min(remain, info.size_h_dim / 2)
    add_dim(out, f"回填|{pp.dock_h}|m3", -(info.size_b_dim * used), "上半扣箱涵",
            geometry=_rect_geometry(z_bottom + used0, z_bottom + used0 + used.v,
                                    size_b / 2.0))


def cal_pipes(info, out: QDict, cat: str = "管材") -> None:
    """管材量 = Σ 含量（每延米，旧版 mcElement.cal_pipes）：含量原文进算式。"""
    for pipe, content in zip(info.pipes, info.pipe_content_dims):
        if content.v == 0:
            continue
        out.add(
            f"{cat}|{pipe.mat} DN{fmt(pipe.dn)}|m",
            content.v,
            content.e,
            tags=content.tags,
        )


def encased_pipe_deduction(info, out: QDict, z_bottom: float | None = None) -> None:
    """包封混凝土扣管位（旧版 mcE2.cal_pipes 的负项：按每根管取壁厚）。

    每根管带自己的管材类别与壁厚（构件库快照 / 详情面板用户值），壁厚为空时
    才临时按直埋管道图集查（同旧版构造临时 mcE1）。``z_bottom`` 为垫层顶标高
    （自槽底，m）：传入时给扣管位分项记录外接矩形几何（高亮用）。

    包封类别没有“管道壁厚”构件参数行（见 ``param_naming``），壁厚取管材行，
    因此这里按各管自己的图集值记录，不挂 ``t`` 符号。
    """
    from app.services.atlas import PipeSpec, resolve_atlas
    from app.core.calc.engine import build_atlas_query, pipe_direct_labels

    for pipe, content in zip(info.pipes, info.pipe_content_dims):
        if content.v == 0:
            continue
        query = build_atlas_query(info, info.pf, info.pw)
        query.category = 1  # 直埋管道图集
        query.pipes = [
            PipeSpec(
                mat=pipe.mat,
                dn=pipe.dn,
                t=pipe.t,
                cat=pipe.cat,
                od=pipe.od,
                inner_d=pipe.inner_d,
                direct=pipe.direct,
            )
        ]
        at = resolve_atlas(query)
        od_value = pipe.od
        if od_value is None:
            t_value = pipe.t if pipe.t is not None else at.t
            od_value = float(pipe.dn) + 2.0 * float(t_value or 0.0)
        od_dim = mm(od_value)
        if len(info.pipes) == 1:
            # 单管：外径挂 oD 符号（来源按图集直取对标注）；多管直径可能
            # 不同，保留各自数值
            source, display = pipe_direct_labels(pipe.direct or "")["oD"]
            od_dim = od_dim.as_param("oD", "管道外径", source, display=display)
        radius = od_dim / 2
        geometry = (
            _rect_geometry(z_bottom, z_bottom + radius.v * 2.0, radius.v)
            if z_bottom is not None
            else None
        )
        area = Dim(
            -math.pi * radius.v * radius.v * content.v,
            # 底数带除号，^2 前必须括起来（tight），否则 (…)/1000^2 会算错
            f"PI()*{wrap(radius.e, tight=True)}^2*{wrap(content.e)}",
            radius.tags + content.tags,
            radius.s * 2,
        )
        out.add(
            "包封|混凝土|m3",
            area.v,
            area,
            f"扣 DN{fmt(pipe.dn)} 管位",
            tags=area.tags,
            geometry=geometry,
        )
