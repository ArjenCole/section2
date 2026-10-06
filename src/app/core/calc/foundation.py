"""管道基础与管材计算（复刻旧版 mcE1~mcE6 的 cal_found / cal_pipes）。

* 直埋管道（mcE1）：砼基础体积扣弓形占位、模板、垫层扣减、坞膀/上半回填扣减；
* 包封埋管（mcE2）：垫层 + 包封混凝土/模板 + 回填扣减 + 管材（包封混凝土扣管位）；
* 箱涵（mcE3）/ 管廊（mcE6）：垫层、底板、箱涵壁、顶板、钢筋（含钢量）与扣减；
* 顶管（mcE4）/ 牵引管（mcE5）：只有管材。

全部为每延米量，由引擎统一 ×数量。
"""

from __future__ import annotations

import math

from app.core.models.models import CATEGORY_BURIED, CATEGORY_BOX_CULVERT, CATEGORY_ENCASED, CATEGORY_GALLERY
from app.core.calc.tracer import QDict, fmt


def _circle(diameter: float) -> float:
    """圆面积 m²（旧版 mcE1.Circle）。"""
    return math.pi * diameter * diameter / 4.0


def _bow(diameter: float, angle: float) -> float:
    """弓形面积 m²（旧版 mcE1.Bow：扇形 − 三角形）。"""
    sector = _circle(diameter) * angle / 360.0
    triangle = 0.5 * diameter * diameter / 4.0 * math.sin(angle / 180.0 * math.pi)
    return sector - triangle


def _bow_expr(diameter: float, angle: float) -> str:
    """弓形面积的数值代入算式（π 取 3.141593，重算误差 <0.001%）。"""
    return (
        f"3.141593×{fmt(diameter)}×{fmt(diameter)}/4×{fmt(angle)}/360"
        f"-{fmt(diameter)}×{fmt(diameter)}/8×sin({fmt(angle)}×3.141593/180)"
    )


def _outside_dn(info, at) -> float:
    """管道外径 m：图集有 oD 用 oD，否则 内径+2×壁厚（旧版 mcE1.cal_found）。"""
    od = at.od if at.od > 0 else (info.pipes[0].dn + at.t * 2 if info.pipes else 0.0)
    return od / 1000.0


def cal_found(info, pe, at, out: QDict) -> None:
    """管道基础 / 包封 / 箱涵 / 管廊本体量与占土扣减（每延米）。"""
    if info.category == CATEGORY_BURIED:
        _found_pipe(info, pe, at, out)
    elif info.category == CATEGORY_ENCASED:
        _found_encased(info, pe, at, out)
    elif info.category == CATEGORY_BOX_CULVERT:
        _found_box(info, pe, at, out, prefix="箱涵", wall_key="箱涵壁")
    elif info.category == CATEGORY_GALLERY:
        _found_box(info, pe, at, out, prefix="管廊", wall_key="管廊壁")


def _found_pipe(info, pe, at, out: QDict) -> None:
    """直埋管道基础（旧版 mcE1.cal_found）。"""
    if not info.pipes:
        return
    outside = _outside_dn(info, at)
    half_circle = _circle(outside) / 2.0
    angle = float(pe.found_angle)
    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    remain = info.depth + (at.t + at.c1) / 1000.0

    if pe.con_found and ("混凝土" in info.pipes[0].mat or "砼" in info.pipes[0].mat):
        width = info.size_b + (at.t * 2 + at.a * 2) / 1000.0
        found_h = (at.c1 + at.c2) / 1000.0
        found = found_h * width
        bow = _bow(outside, angle)
        out.add(
            "管道基础|混凝土|m3",
            found - bow,
            f"({fmt(at.c1)}+{fmt(at.c2)})/1000×({fmt(info.size_b)}+({fmt(at.t)}×2+{fmt(at.a)}×2)/1000)"
            f"-({_bow_expr(outside, angle)})",
            f"基础 {fmt(found)} − {fmt(angle)}° 弓形占位 {fmt(bow)}",
        )
        out.add("管道基础|模板|m2", found_h * 2, f"({fmt(at.c1)}+{fmt(at.c2)})×2/1000")

        deducted = min(remain, found_h)
        out.add(
            f"垫层|{cushion_name}|m3",
            -deducted * width,
            f"-({fmt(at.c1)}+{fmt(at.c2)})/1000×({fmt(info.size_b)}+({fmt(at.t)}×2+{fmt(at.a)}×2)/1000)",
            "垫层扣基础占位",
        )
        remain -= deducted
    else:
        deducted = min(remain, at.c2 / 1000.0) if at.c2 > 0 else 0.0
        remain -= deducted
        bow = _bow(outside, angle)
        out.add(
            f"垫层|{cushion_name}|m3",
            -bow,
            f"-{_bow_expr(outside, angle)}",
            "垫层扣弓形占位",
        )

    chord_height = outside / 2 - outside / 2 * math.cos(angle / 2 / 180 * math.pi)
    remain -= min(remain, chord_height / 1000.0)

    bow = _bow(outside, angle)
    out.add(
        f"回填|{pe.dock_l}|m3",
        -(half_circle - bow),
        f"3.141593×{fmt(outside)}×{fmt(outside)}/8-({_bow_expr(outside, angle)})",
        "坞膀扣弓形",
    )
    out.add(
        f"回填|{pe.dock_h}|m3",
        -half_circle,
        f"-3.141593×{fmt(outside)}×{fmt(outside)}/8",
        "上半回填扣半圆",
    )


def _found_encased(info, pe, at, out: QDict) -> None:
    """包封埋管（旧版 mcE2.cal_found）。"""
    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    remain = info.depth + (at.t + at.c1) / 1000.0

    found = at.c1 / 1000.0 * (info.size_b + at.a / 1000.0 * 2)
    out.add("垫层|混凝土|m3", found, f"{fmt(at.c1)}/1000×({fmt(info.size_b)}+{fmt(at.a)}/1000×2)")
    out.add("垫层|模板|m2", at.c1 / 1000.0 * 2, f"{fmt(at.c1)}/1000×2")

    width = info.size_b + (at.t * 2 + at.a * 2) / 1000.0
    deducted = min(remain, (at.c1 + at.c2) / 1000.0)
    out.add(
        f"垫层|{cushion_name}|m3",
        -deducted * width,
        f"-({fmt(at.c1)}+{fmt(at.c2)})/1000×({fmt(info.size_b)}+({fmt(at.t)}×2+{fmt(at.a)}×2)/1000)",
        "垫层扣基础占位",
    )
    remain -= deducted

    out.add("包封|混凝土|m3", info.size_b * info.size_h, f"{fmt(info.size_b)}×{fmt(info.size_h)}")
    out.add("包封|模板|m2", info.size_h * 2, f"{fmt(info.size_h)}×2")

    used = min(remain, info.size_h / 2.0)
    out.add(f"回填|{pe.dock_l}|m3", -info.size_b * used, f"-{fmt(info.size_b)}×{fmt(used)}", "坞膀扣包封")
    remain -= used
    used = min(remain, info.size_h / 2.0)
    out.add(f"回填|{pe.dock_h}|m3", -info.size_b * used, f"-{fmt(info.size_b)}×{fmt(used)}", "上半扣包封")


def _found_box(info, pe, at, out: QDict, *, prefix: str, wall_key: str) -> None:
    """箱涵 / 管廊（旧版 mcE3 / mcE6.cal_found）。"""
    params = info.params
    bt = params.get("底板厚 mm", 400) / 1000.0
    tt = params.get("顶板厚 mm", 300) / 1000.0
    ot = params.get("外壁厚 mm", 350) / 1000.0
    it = params.get("内壁厚 mm", 250) / 1000.0
    ic = params.get("内壁 道", 0)
    steel_rate = params.get("含钢量 kg/m3", 150) / 1000.0

    cushion_name = pe.cushions[0].name if pe.cushions else "中粗砂"
    remain = info.depth + (at.t + at.c1) / 1000.0

    found = at.c1 / 1000.0 * (info.size_b + at.a / 1000.0 * 2)
    out.add(f"{prefix}|垫层|m3", found, f"{fmt(at.c1)}/1000×({fmt(info.size_b)}+{fmt(at.a)}/1000×2)")
    out.add(f"{prefix}|垫层模板|m2", at.c1 / 1000.0 * 2, f"{fmt(at.c1)}/1000×2")

    width = info.size_b + (at.t * 2 + at.a * 2) / 1000.0
    deducted = min(remain, (at.c1 + at.c2) / 1000.0)
    out.add(
        f"垫层|{cushion_name}|m3",
        -deducted * width,
        f"-({fmt(at.c1)}+{fmt(at.c2)})/1000×({fmt(info.size_b)}+({fmt(at.t)}×2+{fmt(at.a)}×2)/1000)",
        "垫层扣基础占位",
    )
    remain -= deducted

    out.add(f"{prefix}|底板|m3", info.size_b * bt, f"{fmt(info.size_b)}×{fmt(bt)}")
    out.add(f"{prefix}|底板模板|m2", bt * 2, f"{fmt(bt)}×2")
    wall = (info.size_h - bt) * ot * 2 + (info.size_h - bt - tt) * ic * it
    out.add(
        f"{prefix}|{wall_key}|m3",
        wall,
        f"({fmt(info.size_h)}-{fmt(bt)})×{fmt(ot)}×2+({fmt(info.size_h)}-{fmt(bt)}-{fmt(tt)})×{fmt(ic)}×{fmt(it)}",
    )
    wall_form = (info.size_h - bt) * 2 * 2 + (info.size_h - bt - tt) * ic * 2
    out.add(
        f"{prefix}|{wall_key}模板|m2",
        wall_form,
        f"({fmt(info.size_h)}-{fmt(bt)})×2×2+({fmt(info.size_h)}-{fmt(bt)}-{fmt(tt)})×{fmt(ic)}×2",
    )
    roof = (info.size_b - ot * 2) * tt
    out.add(f"{prefix}|顶板|m3", roof, f"({fmt(info.size_b)}-{fmt(ot)}×2)×{fmt(tt)}")
    out.add(f"{prefix}|顶板模板|m2", info.size_b - ot * 2, f"{fmt(info.size_b)}-{fmt(ot)}×2")

    bottom_q = out.get(f"{prefix}|底板|m3")
    wall_q = out.get(f"{prefix}|{wall_key}|m3")
    roof_q = out.get(f"{prefix}|顶板|m3")
    concrete = (bottom_q.value if bottom_q else 0) + (wall_q.value if wall_q else 0) + (roof_q.value if roof_q else 0)
    out.add(
        f"{prefix}|钢筋|t",
        steel_rate * concrete,
        f"{fmt(params.get('含钢量 kg/m3', 150))}/1000×({fmt(concrete)})",
        "钢筋 = 含钢量 × 混凝土合计",
    )

    used = min(remain, info.size_h / 2.0)
    out.add(f"回填|{pe.dock_l}|m3", -info.size_b * used, f"-{fmt(info.size_b)}×{fmt(used)}", "坞膀扣箱涵")
    remain -= used
    used = min(remain, info.size_h / 2.0)
    out.add(f"回填|{pe.dock_h}|m3", -info.size_b * used, f"-{fmt(info.size_b)}×{fmt(used)}", "上半扣箱涵")


def cal_pipes(info, out: QDict, cat: str = "管材") -> None:
    """管材量 = Σ 含量（每延米，旧版 mcElement.cal_pipes）。"""
    for pipe, content in zip(info.pipes, info.pipe_contents):
        if content == 0:
            continue
        out.add(
            f"{cat}|{pipe.mat} Dn{fmt(pipe.dn)}|m",
            content,
            fmt(content),
        )


def encased_pipe_deduction(info, out: QDict) -> None:
    """包封混凝土扣管位（旧版 mcE2.cal_pipes 的负项：按每根管查图集取壁厚）。"""
    from app.services.atlas import PipeSpec, resolve_atlas
    from app.core.calc.engine import build_atlas_query

    for pipe, content in zip(info.pipes, info.pipe_contents):
        if content == 0:
            continue
        query = build_atlas_query(info, info.pe)
        query.category = 1  # 临时按直埋管道查该管的壁厚（同旧版构造临时 mcE1）
        query.pipes = [PipeSpec(mat=pipe.mat, dn=pipe.dn)]
        at = resolve_atlas(query)
        radius = (pipe.dn / 2.0 + at.t) / 1000.0
        out.add(
            "包封|混凝土|m3",
            -math.pi * radius * radius * content,
            f"3.141593×(({fmt(pipe.dn)}/2+{fmt(at.t)})/1000)**2×{fmt(content)}",
            f"扣 Dn{fmt(pipe.dn)} 管位",
        )
