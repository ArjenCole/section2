"""生成带图集快照的构件库资产（``EleInventory.json``）。

一次性离线任务。输入是旧版构件库 ``app/resources/inventory/EleInventory.stn``
（407 个模板，只有管材名称与旧参数，没有图集值）；输出是同名的 JSON 资产，
每个模板额外带上：

* 每根管的 **管材类别**（``cat``，由材质名称按 core.pipe_category 折算一次固化）
  与 **图集壁厚**（``t``）——**8 组**：采用/不采用混凝土基础 × 90/120/150/180
  （砼基础表的 t 随角度变化，例如 Dn600 Ⅱ级管砂基础 120° 是 55mm、90° 是 60mm）；
* 构件的 **工作面加宽 / 垫层厚 / 基础厚**（``a / C1 / C2``）同样 8 组。

这 8 组是详情面板"候选参数列"的数据源（一次性快照，允许用户改，不再自动变）；
运行时按当前围护原则的 砼基础开关 + 基础角度 自动选一组填进参数值列。

运行时不再读图集表：双击构件库条目时把 8 组写进候选表并自动匹配，
之后计算、断面、面宽、包封扣管位都只读条目自身（见 unit_vm.insert_element_template）。

用法（在仓库根目录）：

    .venv/Scripts/python.exe scripts/build_element_inventory.py
    .venv/Scripts/python.exe scripts/build_element_inventory.py --check   # 只校验不写

图集表若更新，重跑本脚本即可；不要手工改 JSON。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app.core.models.models import CATEGORY_NAMES, CATEGORY_STRUCTURE, category_from_name
from app.core.param_naming import split_param_key
from app.core.pipe_category import category_of_mat
from app.core.version import DEFAULT_ATLAS_NAME
from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas
from app.services.stn_migration import parse_legacy

SOURCE = ROOT / "src" / "app" / "resources" / "inventory" / "EleInventory.stn"
TARGET = SOURCE.with_suffix(".json")

#: 基础角度：围护原则 FoundAngle 的四种取值
ANGLES: tuple[int, ...] = (90, 120, 150, 180)

#: 基础形式 × 角度 = 8 组候选（采用/不采用混凝土基础 × 90/120/150/180）。
#: 注意：06MS201-1 砼管**砼基础表没有 150° 行**（砂基础有），
#: 所以“采用混凝土基础-150°”对混凝土管快照为 null，匹配时按就近角度取。
COMBOS: tuple[tuple[bool, int], ...] = tuple(
    (con_found, angle) for con_found in (True, False) for angle in ANGLES
)


def combo_key(con_found: bool, angle: int) -> str:
    """候选键：``con90``（采用砼基础 90°）… ``plain180``（不采用 180°）。"""
    return f"{'con' if con_found else 'plain'}{angle}"

#: 构件类别里要快照图集参数的（顶管 / 牵引只算管材，没有 a / C1 / C2 行）
ATLAS_CATEGORIES = (1, 2, 3, 6)


def _param_map(params: list[tuple[str, str]]) -> dict[str, tuple[float, str]]:
    """旧参数 (键, 值) → {参数名: (数值, 单位)}；求不出数的按 0。"""
    result: dict[str, tuple[float, str]] = {}
    for key, value in params:
        name, unit = split_param_key(str(key).strip())
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            number = 0.0
        result[name] = (number, unit)
    return result


def _number(params: dict[str, tuple[float, str]], name: str, default: float) -> float:
    found = params.get(name)
    return found[0] if found and found[0] else default


def _size_b(category: int, pipes, params: dict[str, tuple[float, str]]) -> float:
    """断面宽 m（同 engine.ElementInput.size_b 的取法）。"""
    if category in (1, 4, 5):
        return float(pipes[0].dn) / 1000.0 if pipes else 0.0
    if category == 2:
        return _number(params, "包封宽", 1.5)
    if category == 3:
        return _number(params, "净宽(含内壁厚度)", 3.5) + _number(params, "外壁厚", 350.0) * 2 / 1000.0
    if category == 6:
        return _number(params, "外包宽", 6.8)
    return 0.0


def _query(category: int, pipes, params, enclosure, con_found: bool, angle: int) -> AtlasQuery:
    return AtlasQuery(
        category=category,
        pipes=[PipeSpec(mat=p.mat, dn=int(p.dn), cat=category_of_mat(p.mat)) for p in pipes],
        con_found=con_found,
        found_angle=int(angle),
        groove_width=enclosure.groove_width,
        size_b=_size_b(category, pipes, params),
        widths=enclosure.widths,
        groove_bs=enclosure.groove_bs,
    )


def _pipe_row(pipe, category: int, params, enclosure) -> dict:
    """单个管道行：类别 + 八组图集壁厚（该组合查不到记 null）。"""
    thickness: dict[str, float | None] = {}
    for con_found, angle in COMBOS:
        at = resolve_atlas(_query(category, [pipe], params, enclosure, con_found, angle))
        thickness[combo_key(con_found, angle)] = at.t if at.t > 0 else None
    return {
        "mat": pipe.mat,
        "cat": category_of_mat(pipe.mat),
        "dn": int(pipe.dn),
        "content": str(pipe.content),
        "t": thickness,
    }


def build() -> dict:
    legacy = parse_legacy(SOURCE)
    enclosure = legacy.enclosures[0] if legacy.enclosures else None
    if enclosure is None:
        raise SystemExit("构件库里没有围护原则，无法快照图集值")

    categories: list[dict] = []
    stats = {"elements": 0, "pipes": 0, "no_thickness": 0, "no_atlas": 0}

    for segment in legacy.segments:
        units: list[dict] = []
        for unit in segment.units:
            elements: list[dict] = []
            for element in unit.elements:
                category = category_from_name(element.category)
                params = _param_map(element.params)
                pipes = [_pipe_row(pipe, category, params, enclosure) for pipe in element.pipes]

                atlas: dict[str, dict[str, float | None]] = {}
                if category in ATLAS_CATEGORIES:
                    for con_found, angle in COMBOS:
                        at = resolve_atlas(
                            _query(category, element.pipes, params, enclosure, con_found, angle)
                        )
                        atlas[combo_key(con_found, angle)] = {
                            "a": at.a or None,
                            "c1": at.c1 or None,
                            "c2": at.c2 or None,
                        }
                elif category and category != CATEGORY_STRUCTURE:
                    stats["no_atlas"] += 1

                elements.append(
                    {
                        "category": element.category or CATEGORY_NAMES.get(category, ""),
                        "name": element.name,
                        "depth": element.depth,
                        "amount": element.amount,
                        "source": element.source,
                        "pipes": pipes,
                        "params": [[key, value] for key, value in element.params],
                        "atlas": atlas,
                    }
                )
                stats["elements"] += 1
                stats["pipes"] += len(pipes)
                for row in pipes:
                    if all(value is None for value in row["t"].values()):
                        stats["no_thickness"] += 1
            units.append({"name": unit.name, "elements": elements})
        categories.append({"name": segment.name, "units": units})

    return {
        "version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": SOURCE.name,
        "atlas": DEFAULT_ATLAS_NAME,
        "angles": list(ANGLES),
        "combos": [combo_key(con, angle) for con, angle in COMBOS],
        "categories": categories,
        "stats": stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只统计不写文件")
    args = parser.parse_args()

    payload = build()
    stats = payload["stats"]
    print(
        f"模板 {stats['elements']} 个 / 管道行 {stats['pipes']} 行；"
        f"壁厚全空 {stats['no_thickness']} 行；无图集参数类别 {stats['no_atlas']} 个"
    )
    if args.check:
        return 0
    TARGET.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写入 {TARGET}（{TARGET.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
