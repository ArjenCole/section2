"""PE × PF 新地基原则生成（决策 2 / §5）。

1.0 的 ``ConFound / FoundAngle / Cush`` 挂在围护原则 PE 上，2.0 挂在地基
原则 PF 上。迁移为**所有 (旧 PF, 旧 PE) 组合**生成一条新 PF（未使用的组合
也生成，便于按原 PE/PF 任意匹配与审计）：

* 名称 = ``旧PF名·旧PE名``（空名用默认名；重名追加 ``#2/#3``；超长截断）；
* ``con_found / found_angle / cushion`` 取对应旧 PE 的值（旧 PF 自带的
  基础参数以 PE 为准，冲突时记 warning）；
* 换填层与特殊地基构件克隆旧 PF；
* ``legacy_meta`` 记录来源（旧 PE / 旧 PF 名），便于报告与排查。

构件拆分子条目按 ``pf_map[(旧PF名, 旧PE名)]`` 引用新 PF。
"""

from __future__ import annotations

from app.services.legacy_migration.parser import LegacyProject
from app.services.legacy_migration.report import MigrationReport

#: 空名兜底（计划 §5.3）
_DEFAULT_PE_NAME = "未命名围护原则"
_DEFAULT_PF_NAME = "未命名地基原则"
#: PcpFoundation.name 列宽（截断 + 后缀用）
_NAME_LIMIT = 200


def _unique_name(base: str, used: set[str]) -> str:
    """重名追加 #2/#3；超长截断后仍保证带后缀不超列宽。"""
    name = base
    index = 1
    while name in used:
        index += 1
        suffix = f"#{index}"
        name = base[: _NAME_LIMIT - len(suffix)] + suffix
    return name


def build_pf_map(
    session,
    legacy: LegacyProject,
    library,
    report: MigrationReport,
) -> tuple[dict[tuple[str, str], str], dict[str, tuple[bool, int]]]:
    """生成全部 PE×PF 新地基原则。

    返回 ``(映射表, 新PF基础参数表)``：映射表 ``(旧PF名, 旧PE名) → 新 PF 名``；
    基础参数表 ``新PF名 → (con_found, found_angle)``（管道匹配取 t 用）。

    旧 PF 外层、旧 PE 内层（order_no = 旧 PF 序 × PE 数 + 旧 PE 序）。
    生成条数与未使用组合数写入报告。
    """
    from app.services.legacy_migration.writer import write_legacy_foundation

    pf_map: dict[tuple[str, str], str] = {}
    pf_angles: dict[str, tuple[bool, int]] = {}
    used_names: set[str] = set()
    pe_count = len(legacy.enclosures)
    order = 0
    for pf_index, (pf_name, replacements, component, pipe_base) in enumerate(legacy.foundations):
        old_pf = pf_name or _DEFAULT_PF_NAME
        for pe_index, old_pe in enumerate(legacy.enclosures):
            old_pe_name = old_pe.name or _DEFAULT_PE_NAME
            new_name = _unique_name(f"{old_pf}·{old_pe_name}", used_names)
            used_names.add(new_name)
            # 管道基础按 1.0 语义以 PE 为准；旧 PF 自带基础参数时只校验不覆盖
            if pipe_base is not None:
                old_cushion = pipe_base.get("cushion")
                differs = (
                    bool(pipe_base.get("con_found", True)) != bool(old_pe.con_found)
                    or int(pipe_base.get("found_angle", 120)) != int(old_pe.found_angle)
                    or (old_cushion is not None and tuple(old_cushion) != tuple(old_pe.cushion))
                )
                if differs:
                    report.warnings.append(
                        f"地基原则“{pf_name}”自带管道基础参数与围护原则“{old_pe_name}”不一致，"
                        "已按 1.0 语义以围护原则（PE）为准。"
                    )
            foundation = write_legacy_foundation(
                session,
                (new_name, replacements, component),
                library,
                report=report,
                order_no=order,
                pipe_base={
                    "con_found": old_pe.con_found,
                    "found_angle": old_pe.found_angle,
                    "cushion": old_pe.cushion,
                },
                legacy_meta={"legacy_pe_name": old_pe_name, "legacy_pf_name": old_pf},
            )
            order += 1
            pf_map[(pf_name, old_pe.name)] = new_name
            pf_angles[new_name] = (bool(old_pe.con_found), int(old_pe.found_angle))
            report.pf_mappings.append(
                f"{old_pf} × {old_pe_name} → {new_name}"
                f"（砼基础 {foundation.con_found and '是' or '否'} / {foundation.found_angle}° /"
                f" 垫层 {foundation.cushions[0].name if foundation.cushions else '无'}）"
            )
    report.foundations = order
    report.source_foundations = len(legacy.foundations)
    if pe_count and legacy.foundations:
        report.pf_mappings.append(
            f"生成 {pe_count}×{len(legacy.foundations)}={order} 条；"
            f"旧 PF {len(legacy.foundations)} 条全部克隆换填层与特殊地基，"
            "砼基础/角度/垫层取对应 PE 的值。"
        )
    return pf_map, pf_angles
