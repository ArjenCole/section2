"""管道基础与管材计算（复刻旧版 mcE1~mcE6 的 cal_found / cal_pipes）。

* 直埋管道（mcE1）：砼基础体积扣弓形占位、模板、垫层扣减、坞膀/上半回填扣减；
* 包封埋管（mcE2）：垫层 + 包封混凝土/模板 + 回填扣减 + 管材（包封混凝土扣管位）；
* 箱涵（mcE3）/ 管廊（mcE6）：垫层、底板、箱涵壁、顶板、钢筋（含钢量）与扣减；
* 顶管（mcE4）/ 牵引管（mcE5）：只有管材。

全部为每延米量，由引擎统一 ×数量。各条量的算式都由 :class:`Dim` 拼出、
不做预运算：基础宽高、外径、弓形面积、钢筋合计等都保留 管径 / 图集参数
与构件参数原文的推导，见 :mod:`app.core.calc.tracer`。
"""

from __future__ import annotations

import math

from app.core.models.models import CATEGORY_BURIED, CATEGORY_BOX_CULVERT, CATEGORY_ENCASED, CATEGORY_GALLERY
from app.core.calc.measures import AtlasDims
from app.core.calc.tracer import Dim, QDict, dim, dim_min, fmt, scale_sum, wrap


def add_dim(out: QDict, key: str, quantity: Dim, note: str = "") -> None:
    """按 :class:`Dim` 输出一条工程量：数值取 ``v``，算式取 ``e``（不预运算）。"""
    out.add(key, quantity.v, quantity.e, note)


def _circle(diameter: float) -> float:
    """圆面积 m²（旧版 mcE1.Circle）。"""
    return math.pi * diameter * diameter / 4.0


def _bow(diameter: float, angle: float) -> float:
    """弓形面积 m²（旧版 mcE1.Bow：扇形 − 三角形）。"""
    sector = _circle(diameter) * angle / 360.0
    triangle = 0.5 * diameter * diameter / 4.0 * math.sin(angle / 180.0 * math.pi)
    return sector - triangle


def _bow_expr(diameter: Dim, angle: float) -> str:
    """弓形面积的代入算式（π 取 3.141593，重算误差 <0.001%）；外径带自己的算式。"""
    d = wrap(diameter.e)
    return (
        f"3.141593×{d}×{d}/4×{fmt(angle)}/360"
        f"-{d}×{d}/8×sin({fmt(angle)}×3.141593/180)"
    )


def _bow_dim(diameter: Dim, angle: float) -> Dim:
    """弓形占位（数值按 mcE1.Bow，算式按 π=3.141593 的代入式）。"""
    return Dim(_bow(diameter.v, angle), _bow_expr(diameter, angle))


def _outside_dn(info, ad: AtlasDims) -> Dim:
    """管道外径 m：图集有 oD 用 oD（表值），否则 内径+2×壁厚（旧版 mcE1.cal_found）。"""
    return ad.od / 1000


def cal_found(info, pe, ad: AtlasDims, out: QDict) -> None:
    """管道基础 / 包封 / 箱涵 / 管廊本体量与占土扣减（每延米）。"""
    if info.category == CATEGORY_BURIED:
        _found_pipe(info, pe, ad, out)
    elif info.category == CATEGORY_ENCASED:
        _found_encased(info, pe, ad, out)
    elif info.category == CATEGORY_BOX_CULVERT:
        _found_box(info, pe, ad, out, prefix="箱涵", wall_key="箱涵壁")
    elif info.category == CATEGORY_GALLERY:
        _found_box(info, pe, ad, out, prefix="管廊", wall_key="管廊壁")


def _found_pipe(info, pe, ad: AtlasDims, out: QDict) -> None:
    """直埋管道基础（旧版 mcE1.cal_found）。"""
    if not info.pipes:
        return
    outside = _outside_dn(info, ad)
    half_circle = _circle(outside.v) / 2.0
    angle = float(pe.found_angle)
    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    remain = info.depth_dim + (ad.t + ad.c1) / 1000

    if pe.con_found and ("混凝土" in info.pipes[0].mat or "砼" in info.pipes[0].mat):
        width = info.size_b_dim + scale_sum((ad.t, ad.a), 2.0) / 1000
        found_h = (ad.c1 + ad.c2) / 1000
        found = found_h * width
        bow = _bow_dim(outside, angle)
        add_dim(
            out,
            "管道基础|混凝土|m3",
            found - bow,
            f"基础 {fmt(found.v)} − {fmt(angle)}° 弓形占位 {fmt(bow.v)}",
        )
        add_dim(out, "管道基础|模板|m2", found_h * 2)

        deducted = dim_min(remain, found_h)
        add_dim(out, f"垫层|{cushion_name}|m3", -(deducted * width), "垫层扣基础占位")
        remain = remain - deducted
    else:
        deducted = dim_min(remain, ad.c2 / 1000) if ad.c2.v > 0 else dim(0.0)
        remain = remain - deducted
        add_dim(out, f"垫层|{cushion_name}|m3", -_bow_dim(outside, angle), "垫层扣弓形占位")

    chord_height = outside.v / 2 - outside.v / 2 * math.cos(angle / 2 / 180 * math.pi)
    remain = remain - dim_min(remain, dim(chord_height / 1000.0))

    add_dim(
        out,
        f"回填|{pe.dock_l}|m3",
        Dim(
            -(half_circle - _bow(outside.v, angle)),
            f"3.141593×{wrap(outside.e)}×{wrap(outside.e)}/8-({_bow_expr(outside, angle)})",
        ),
        "坞膀扣弓形",
    )
    add_dim(
        out,
        f"回填|{pe.dock_h}|m3",
        Dim(-half_circle, f"3.141593×{wrap(outside.e)}×{wrap(outside.e)}/8"),
        "上半回填扣半圆",
    )


def _found_encased(info, pe, ad: AtlasDims, out: QDict) -> None:
    """包封埋管（旧版 mcE2.cal_found）。"""
    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    remain = info.depth_dim + (ad.t + ad.c1) / 1000

    add_dim(out, "垫层|混凝土|m3", ad.c1 / 1000 * (info.size_b_dim + ad.a / 1000 * 2))
    add_dim(out, "垫层|模板|m2", ad.c1 / 1000 * 2)

    width = info.size_b_dim + scale_sum((ad.t, ad.a), 2.0) / 1000
    deducted = dim_min(remain, (ad.c1 + ad.c2) / 1000)
    add_dim(out, f"垫层|{cushion_name}|m3", -(deducted * width), "垫层扣基础占位")
    remain = remain - deducted

    add_dim(out, "包封|混凝土|m3", info.size_b_dim * info.size_h_dim)
    add_dim(out, "包封|模板|m2", info.size_h_dim * 2)

    used = dim_min(remain, info.size_h_dim / 2)
    add_dim(out, f"回填|{pe.dock_l}|m3", -(info.size_b_dim * used), "坞膀扣包封")
    remain = remain - used
    used = dim_min(remain, info.size_h_dim / 2)
    add_dim(out, f"回填|{pe.dock_h}|m3", -(info.size_b_dim * used), "上半扣包封")


def _found_box(info, pe, ad: AtlasDims, out: QDict, *, prefix: str, wall_key: str) -> None:
    """箱涵 / 管廊（旧版 mcE3 / mcE6.cal_found）。"""
    bt = info.param_dim("底板厚", 400) / 1000
    tt = info.param_dim("顶板厚", 300) / 1000
    ot = info.param_dim("外壁厚", 350) / 1000
    it = info.param_dim("内壁厚", 250) / 1000
    ic = info.param_dim("内壁", 0)
    steel_rate = info.param_dim("含钢量", 150) / 1000

    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    remain = info.depth_dim + (ad.t + ad.c1) / 1000

    add_dim(out, f"{prefix}|垫层|m3", ad.c1 / 1000 * (info.size_b_dim + ad.a / 1000 * 2))
    add_dim(out, f"{prefix}|垫层模板|m2", ad.c1 / 1000 * 2)

    width = info.size_b_dim + scale_sum((ad.t, ad.a), 2.0) / 1000
    deducted = dim_min(remain, (ad.c1 + ad.c2) / 1000)
    add_dim(out, f"垫层|{cushion_name}|m3", -(deducted * width), "垫层扣基础占位")
    remain = remain - deducted

    bottom = info.size_b_dim * bt
    add_dim(out, f"{prefix}|底板|m3", bottom)
    add_dim(out, f"{prefix}|底板模板|m2", bt * 2)
    wall = (info.size_h_dim - bt) * ot * 2 + (info.size_h_dim - bt - tt) * ic * it
    add_dim(out, f"{prefix}|{wall_key}|m3", wall)
    wall_form = (info.size_h_dim - bt) * 2 * 2 + (info.size_h_dim - bt - tt) * ic * 2
    add_dim(out, f"{prefix}|{wall_key}模板|m2", wall_form)
    roof = (info.size_b_dim - ot * 2) * tt
    add_dim(out, f"{prefix}|顶板|m3", roof)
    add_dim(out, f"{prefix}|顶板模板|m2", info.size_b_dim - ot * 2)

    add_dim(out, f"{prefix}|钢筋|t", steel_rate * (bottom + wall + roof), "钢筋 = 含钢量 × 混凝土合计")

    used = dim_min(remain, info.size_h_dim / 2)
    add_dim(out, f"回填|{pe.dock_l}|m3", -(info.size_b_dim * used), "坞膀扣箱涵")
    remain = remain - used
    used = dim_min(remain, info.size_h_dim / 2)
    add_dim(out, f"回填|{pe.dock_h}|m3", -(info.size_b_dim * used), "上半扣箱涵")


def cal_pipes(info, out: QDict, cat: str = "管材") -> None:
    """管材量 = Σ 含量（每延米，旧版 mcElement.cal_pipes）：含量原文进算式。"""
    for pipe, content in zip(info.pipes, info.pipe_content_dims):
        if content.v == 0:
            continue
        out.add(f"{cat}|{pipe.mat} Dn{fmt(pipe.dn)}|m", content.v, content.e)


def encased_pipe_deduction(info, out: QDict) -> None:
    """包封混凝土扣管位（旧版 mcE2.cal_pipes 的负项：按每根管查图集取壁厚）。

    每根管带详情面板的用户壁厚（PipeSpec.t，空 = 按图集自动），
    临时按直埋管道类别查该管的壁厚（同旧版构造临时 mcE1）。
    """
    from app.services.atlas import PipeSpec, resolve_atlas
    from app.core.calc.engine import build_atlas_query

    for pipe, content in zip(info.pipes, info.pipe_content_dims):
        if content.v == 0:
            continue
        query = build_atlas_query(info, info.pe, info.pw)
        query.category = 1  # 直埋管道图集
        query.pipes = [PipeSpec(mat=pipe.mat, dn=pipe.dn, t=pipe.t)]
        at = resolve_atlas(query)
        radius = (dim(pipe.dn) / 2 + dim(at.t)) / 1000
        out.add(
            "包封|混凝土|m3",
            -math.pi * radius.v * radius.v * content.v,
            # 底数带除号，**2 前必须括起来（tight），否则 (…)/1000² 会算错
            f"3.141593×{wrap(radius.e, tight=True)}**2×{wrap(content.e)}",
            f"扣 Dn{fmt(pipe.dn)} 管位",
        )
