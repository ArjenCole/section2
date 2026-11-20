"""迁移写库：LegacyProject → 2.0 工作库（§3 总流程）。

* **先建原则，再建构件**：围护（含同名降水 / 面宽）先落库，PE×PF 新地基
  原则其次，子构件按名引用；
* **一条旧构件可能变成多条**：拆分在主循环内完成，保持原顺序；
* **所有无法原样保留的值都进报告**：不能静默跳过；
* 管道按 DN 到构件库匹配 oD / iD / t（决策 1），直埋构件生成 8 组候选并
  自动匹配参数行（决策 7）；
* 单价键 ``Dn → DN``（决策 12）。

迁移只负责"把 1.0 数据写成正常的 2.0 数据"，不写任何运行时特殊逻辑。
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from app.core.atlas_candidates import CANDIDATE_ANGLES, combo_key
from app.core.models import base as orm
from app.core.models.models import (
    CATEGORY_BURIED,
    CATEGORY_STRUCTURE,
    Element,
    ElementAtlasCandidate,
    ElementParam,
    ElementQuantity,
    BasicInfo,
    Pipe,
    Price,
    Segment,
    Unit,
)
from app.core.param_naming import atlas_param_rows, split_param_key
from app.services.legacy_migration.matcher import all_candidates, match_pipe_template
from app.services.legacy_migration.parser import (
    LEGACY_MULTI_PF_TEXT,
    LEGACY_MULTI_PE_TEXT,
    _LegacyElement,
    _LegacyEnclosure,
    _LegacyWork,
    _version_tuple,
    category_from_name,
    parse_legacy,
)
from app.services.legacy_migration.principles import build_pf_map
from app.services.legacy_migration.report import MigrationReport
from app.services.legacy_migration.splitter import (
    migration_pairs,
    source_summary,
    split_children,
    valid_principle_refs,
    warn_ratios,
)
from app.services.legacy_migration.structure_keys import parse_quantity_key

#: 打开旧版文件自动转译时，原文件的备份文件夹（软件数据目录下，brackets 同款）
MIGRATION_BACKUP_DIR_NAME = "migration_backup"

#: 单价键 / 管材工程量键里的旧直径标记 ``Dn<数字>``（决策 12：只改生成的键，
#: 不碰用户材料名 / 参数值 / 构件名里的 Dn）
_PRICE_DN_RE = re.compile(r"(?<=\s)Dn(?=\d)")


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #
def migrate(source: str | Path, target: str | Path) -> MigrationReport:
    """解析旧工程并写出新的 .stn；失败时删除半成品文件后抛出。"""
    target_path = Path(target)
    try:
        report = build_legacy_database(source)
        report.target = str(target_path)
        if target_path.exists():
            target_path.unlink()
        try:
            from app.services import stn_format, stn_codec

            stn_format.write_stn(target_path, stn_codec.dump_database())
        finally:
            orm.close_database()
    except Exception:
        orm.close_database()
        if target_path.exists():
            try:
                target_path.unlink()
            except OSError:
                pass
        raise
    return report


def build_legacy_database(source: str | Path) -> MigrationReport:
    """解析旧工程并写入新建的临时工作库，返回迁移报告。

    打开旧版文件自动转译（project_io.open_legacy_project）与导出迁移
    （migrate）共用：只建库不写 `.stn` 文件、转译后保持打开（工作库里的
    数据就是转译结果）。失败时抛异常，工作库由调用方负责关闭。
    """
    from app.services.atlas import component_library

    source_path = Path(source)
    report = MigrationReport(source=str(source_path))
    legacy, report = parse_legacy(source_path, report)
    library = component_library()

    orm.create_working_database()
    session = orm.session()

    session.add(
        BasicInfo(
            id=1,
            project_name=legacy.project_name or "新建项目",
            project_index=legacy.project_index,
            author=legacy.author,
            atlas_name=legacy.atlas_name or "06MS201-1",
            legacy_meta=json.dumps(
                {
                    "source_version": legacy.version,
                    "source_file": str(source_path),
                    "migrated_at": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
            ),
        )
    )

    # 围护原则（降水 / 面宽原则同名跟随，见 write_legacy_enclosure）
    for index, legacy_pe in enumerate(legacy.enclosures):
        write_legacy_enclosure(session, legacy_pe, library, report, order_no=index)
        report.enclosures += 1
        report.principle_names.append(legacy_pe.name)

    # PE × PF 新地基原则（先落库，子构件才能按名引用）
    pf_map, pf_angles = build_pf_map(session, legacy, library, report)
    for pf_name, _replacements, _component, _pipe_base in legacy.foundations:
        report.principle_names.append(pf_name)

    # 标段 / 单位工程 / 构件 / 管道
    candidates = all_candidates()
    pe_names = {enclosure.name for enclosure in legacy.enclosures}
    pf_names = {entry[0] for entry in legacy.foundations}
    first_pe = legacy.enclosures[0].name if legacy.enclosures else ""
    first_pf = legacy.foundations[0][0] if legacy.foundations else ""
    for segment_index, legacy_segment in enumerate(legacy.segments):
        segment = Segment(name=legacy_segment.name, order_no=segment_index)
        session.add(segment)
        session.flush()
        report.segments += 1
        for unit_index, legacy_unit in enumerate(legacy_segment.units):
            unit = Unit(segment_id=segment.id, name=legacy_unit.name, order_no=unit_index)
            session.add(unit)
            session.flush()
            report.units += 1
            element_order = 0
            for legacy_element in legacy_unit.elements:
                element_order = _migrate_element(
                    session, unit.id, legacy_element,
                    pf_map=pf_map, pf_angles=pf_angles,
                    pe_names=pe_names, pf_names=pf_names,
                    first_pe=first_pe, first_pf=first_pf,
                    candidates=candidates,
                    order_no=element_order, version=legacy.version, report=report,
                )

    # 单价：旧直径标记 Dn → DN（决策 12，只改生成的单价键）
    for key, value in legacy.prices:
        new_key = _PRICE_DN_RE.sub("DN", key)
        if new_key != key:
            report.price_rewrites.append(f"{key} → {new_key}")
        session.add(Price(key=new_key, value=value))
        report.prices += 1

    orm.commit()
    report.warnings = _dedupe(report.warnings)
    return report


def backup_legacy_file(path: str | Path, version: str) -> Path:
    """把旧版文件复制到软件数据目录的迁移备份文件夹，返回备份路径（brackets 同款）。

    备份文件名带旧版程序版本号与时间戳，原文件任何情况下不被修改。
    """
    from app.core.paths import ensure_app_data_dir

    source = Path(path)
    folder = ensure_app_data_dir() / MIGRATION_BACKUP_DIR_NAME
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = folder / f"{source.stem}_v{version}_{stamp}{source.suffix}"
    shutil.copy2(source, target)
    return target


# --------------------------------------------------------------------------- #
# 构件迁移
# --------------------------------------------------------------------------- #
def _migrate_element(
    session,
    unit_id: int,
    legacy_element: _LegacyElement,
    *,
    pf_map: dict,
    pf_angles: dict,
    pe_names: set[str],
    pf_names: set[str],
    first_pe: str,
    first_pf: str,
    candidates,
    order_no: int,
    version: str,
    report: MigrationReport,
) -> int:
    """迁移一条旧构件（含拆分），返回下一个可用 order_no。"""
    category = category_from_name(legacy_element.category)
    display_name = legacy_element.name or "(未命名)"
    if legacy_element.category and category == 0:
        report.warnings.append(
            f"构件“{display_name}”的类别“{legacy_element.category}”无法识别，按空类别迁移。"
        )
    pe_refs, pe_warnings = valid_principle_refs("pe", legacy_element, pe_names, first_pe)
    pf_refs, pf_warnings = valid_principle_refs("pf", legacy_element, pf_names, first_pf)
    for warning in pe_warnings + pf_warnings:
        report.warnings.append(f"构件“{display_name}”{warning}")
    warn_ratios(display_name, category, pe_refs, pf_refs, report)
    pairs = migration_pairs(category, legacy_element, pe_refs, pf_refs)
    children = split_children(legacy_element, pairs, pf_map, pe_refs, pf_refs)
    if len(children) > 1:
        report.splits += 1
        report.split_details.append(_split_detail_line(display_name, legacy_element, pairs))
    for child in children:
        child.legacy_meta["source_version"] = version
        _write_child(
            session, unit_id, legacy_element, category, child, version=version,
            pf_angles=pf_angles, candidates=candidates,
            order_no=order_no, report=report,
        )
        order_no += 1
    return order_no


def _split_detail_line(display_name: str, legacy_element: _LegacyElement,
                       pairs: list[tuple[str, float, str, float]]) -> str:
    parts = [
        f"{pe_name}×{pf_name} {pe_ratio * pf_ratio * 100:g}%"
        for pe_name, pe_ratio, pf_name, pf_ratio in pairs
    ]
    main = legacy_element.main_pe_name
    tail = f"（旧主围护原则：{main}）" if main else ""
    return f"“{display_name}”拆成 {len(pairs)} 条：{'、'.join(parts)}{tail}"


def _write_child(
    session,
    unit_id: int,
    legacy_element: _LegacyElement,
    category: int,
    child,
    *,
    version: str,
    pf_angles: dict,
    candidates,
    order_no: int,
    report: MigrationReport,
) -> None:
    """写一条子构件及其管道 / 参数 / 工程量行 / 图集候选（§4 / §6.3）。

    降水 / 面宽原则跟随围护原则同名引用（write_legacy_enclosure 为每条旧
    围护原则生成了同名降水 / 面宽原则）。
    """
    con_found, found_angle = pf_angles.get(child.pf_name, (True, 120))
    element = Element(
        unit_id=unit_id,
        category=category,
        name=child.name,
        depth=legacy_element.depth or "0",
        amount=child.amount,
        pe_name=child.pe_name,
        pf_name=child.pf_name,
        pp_name=child.pe_name,
        pw_name=child.pe_name,
        source=source_summary(legacy_element, *_element_refs(legacy_element)),
        legacy_meta=json.dumps(child.legacy_meta, ensure_ascii=False),
        order_no=order_no,
    )
    session.add(element)
    session.flush()
    report.elements += 1
    first_match = None
    for index, legacy_pipe in enumerate(legacy_element.pipes):
        match = _write_pipe(
            session, element, legacy_pipe, category,
            con_found=con_found, found_angle=found_angle,
            candidates=candidates, first=index == 0, report=report,
        )
        if index == 0:
            first_match = match
    _write_params_and_quantities(session, element, legacy_element, category, version, report)
    if category == CATEGORY_BURIED and first_match is not None:
        _seed_atlas_candidates(element, first_match)
        from app.services.atlas_match import match_atlas_candidates

        match_atlas_candidates(element, commit=False)


def _element_refs(legacy_element: _LegacyElement) -> tuple[list, list]:
    """来源摘要用的引用列表（有效引用；展示名占位“多围护原则”不算）。"""
    pe_refs = list(legacy_element.pe_refs)
    if not pe_refs and legacy_element.pe_name and legacy_element.pe_name != LEGACY_MULTI_PE_TEXT:
        pe_refs = [(legacy_element.pe_name, 1.0)]
    pf_refs = list(legacy_element.pf_refs)
    if not pf_refs and legacy_element.pf_name and legacy_element.pf_name != LEGACY_MULTI_PF_TEXT:
        pf_refs = [(legacy_element.pf_name, 1.0)]
    return pe_refs, pf_refs


def _write_pipe(
    session,
    element: Element,
    legacy_pipe,
    category: int,
    *,
    con_found: bool,
    found_angle: int,
    candidates,
    first: bool,
    report: MigrationReport,
):
    """写一根管道：按 DN 匹配构件库模板取 oD / iD / t（决策 1 / §4）。

    匹配失败不伪造直径（保持 None，2.0 计算按图集兜底），原因进报告；
    成功时返回匹配结果（首管的模板供图集候选生成复用）。
    """
    mat = legacy_pipe.mat
    dn = legacy_pipe.dn
    match, failure, notes = match_pipe_template(
        mat, dn, category, con_found, found_angle, candidates=candidates
    )
    label = f"“{element.name or '(未命名)'}”的管道 {mat or '(无材质)'} DN{dn:g}"
    if match is None:
        report.warnings.append(f"{label}未匹配到构件库模板：{failure}；oD/iD/t 留空，计算时按图集兜底。")
        element.pipes.append(
            Pipe(
                mat=mat,
                dn=int(dn),
                content=legacy_pipe.content or "1",
            )
        )
        report.pipes += 1
        return None
    for note in notes:
        report.warnings.append(f"{label}：{note}")
    element.pipes.append(
        Pipe(
            mat=mat,
            dn=int(dn),
            content=legacy_pipe.content or "1",
            od=match.od,
            inner_d=match.inner_d,
            t=match.t,
            direct=match.direct,
            cat=match.cat,
        )
    )
    report.pipes += 1
    report.pipe_matches.append(
        f"{label} → {match.level}"
        f"（oD {match.od:g} / iD {match.inner_d:g} / t {match.t:g}，"
        f"模板：{match.template.name or match.template.label}"
        + ("，首管：a/C1/C2 取此模板）" if first else "）")
    )
    return match


def _write_params_and_quantities(
    session,
    element: Element,
    legacy_element: _LegacyElement,
    category: int,
    version: str,
    report: MigrationReport,
) -> None:
    """写参数行与构筑物工程量行（决策 5 / §7）。

    构筑物按 1.0 规则判定：键以 ``-`` 开头 → 参数行；其余键都是工程量行
    （不再要求含 ``|``），键原文存 ``raw_key``，显示三列按 1.0 规则解析。
    """
    known_params = {key for key, _value in legacy_element.params}
    quantity_order = 0
    for key, value in legacy_element.params:
        if category == CATEGORY_STRUCTURE and not key.startswith("-"):
            parsed_category, item, unit, warning = parse_quantity_key(key)
            report.structure_keys.append(
                f"“{element.name or '(未命名)'}”键“{key}” → 分类“{parsed_category}”"
                f" / 项目“{item}” / 单位“{unit}”"
            )
            if warning:
                report.warnings.append(f"构件“{element.name or '(未命名)'}”{warning}")
            element.quantities.append(
                ElementQuantity(
                    category=parsed_category,
                    item=item,
                    unit=unit,
                    value=value,
                    raw_key=key,
                    order_no=quantity_order,
                )
            )
            quantity_order += 1
            continue
        param_name = key.lstrip("-") if category == CATEGORY_STRUCTURE else key
        param_name, unit = split_param_key(param_name)
        element.params.append(
            ElementParam(key=param_name, unit=unit, value=value)
        )
    if category == 3 and "含钢量 kg/m3" not in known_params and _version_tuple(version or "0") < (1, 2, 1, 1):
        element.params.append(ElementParam(key="含钢量", unit="kg/m3", value="150"))
        report.defaults.append(f"旧版 <1.2.1.1：箱涵“{element.name or '(未命名)'}”补默认含钢量 150 kg/m³。")
    # 该类别显示的图集参数行（直埋三行，包封 / 箱涵 / 管廊的工作面
    # 加宽 / 垫层厚；空 = 自动按图集 / 软件约定），与新建 / 构件库
    # 插入的条目保持一致（1.0 没有这些行）。
    # 子行一律经 relationship 集合追加（与 stn_codec 落库同款）：后续
    # match_atlas_candidates 读 element.params 选组写值，外键直插的行
    # 不在已加载的集合里，会重复出一套参数行
    existing_keys = {param.key for param in element.params}
    added = [
        (param_name, param_unit)
        for param_name, param_unit in atlas_param_rows(category)
        if param_name not in existing_keys
    ]
    for param_name, param_unit in added:
        element.params.append(
            ElementParam(
                key=param_name,
                unit=param_unit,
                value="",
            )
        )
    if added:
        names = "、".join(name for name, _unit in added)
        report.defaults.append(
            f"构件“{element.name or '(未命名)'}”按类别补图集参数行（空值 = 自动按图集）：{names}。"
        )


def _seed_atlas_candidates(element: Element, match) -> None:
    """按首根管匹配到的模板生成 8 组图集候选（决策 7 / §4.4）。

    候选值取模板 ``thickness`` / ``atlas`` 同键值，该组合无数据写 None
    （与 2.0 资产一致）；随后由调用方 ``match_atlas_candidates`` 按新 PF
    的 con_found + found_angle 自动选组写参数行。
    """
    pipe_template = match.pipe
    template = match.template
    for con_found in (True, False):
        for angle in CANDIDATE_ANGLES:
            key = combo_key(con_found, angle)
            t = pipe_template.thickness.get(key)
            atlas = template.atlas.get(key)
            a, c1, c2 = atlas if atlas else (None, None, None)
            element.atlas_candidates.append(
                ElementAtlasCandidate(
                    con_found=con_found,
                    angle=int(angle),
                    t=t,
                    a=a,
                    c1=c1,
                    c2=c2,
                    order_no=len(element.atlas_candidates),
                )
            )


# --------------------------------------------------------------------------- #
# 围护 / 地基原则写入（*.spcp 单原则导入共用）
# --------------------------------------------------------------------------- #
def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _seed_widths(session, width, table: dict[str, dict[int, float]], kind: str) -> None:
    from app.core.models.models import WidthItem

    for category_index, (category, values) in enumerate(table.items()):
        for dn_index, (dn, value) in enumerate(sorted(values.items())):
            session.add(
                WidthItem(
                    width_id=width.id,
                    pipe_type=category,
                    dn=dn,
                    width=value,
                    kind=kind,
                    order_no=category_index * 100 + dn_index,
                )
            )


def write_legacy_enclosure(session, legacy_pe: _LegacyEnclosure, library, report: MigrationReport | None = None,
                           order_no: int = 0):
    """把旧版围护原则（mcPcpEnclosure 解析结果）写入当前会话并返回。

    迁移与 *.spcp 单原则导入共用；原则本体与做法/级别/构件全套写入。
    旧版挂在围护原则下的降水参数与宽度表，v4 起拆成与围护同名的独立
    降水/面宽原则一并写入（旧 PE 名在其各自表内即原则名）；v10 起原本挂在
    围护原则下的挖填类型（开挖土质 / 回填材质）也并入该同名挖填降水原则，
    管道基础与垫层则随 :func:`write_legacy_foundation` 落到地基原则。
    """
    from app.core.models.models import (
        EnclosureLevel,
        EnclosureWork,
        PcpEnclosure,
        PcpPrecipitation,
        PcpWidth,
        PRECIPITATION_COLUMNS,
        dock_cover_h_for,
    )

    report = report or MigrationReport()
    enclosure = PcpEnclosure(name=legacy_pe.name, order_no=order_no)
    session.add(enclosure)
    session.flush()
    precipitation = PcpPrecipitation(
        name=legacy_pe.name,
        order_no=order_no,
        excvt=legacy_pe.excvt,
        dock_l=legacy_pe.dock_l,
        dock_h=legacy_pe.dock_h,
        cover50=legacy_pe.cover50,
        cover=legacy_pe.cover,
        # 旧版没有 CoverH 标签：按四个材质字段反推（至管顶标高 = 0cm，其余 50cm）
        cover_h=(
            legacy_pe.cover_h
            if legacy_pe.cover_h is not None
            else dock_cover_h_for(
                legacy_pe.dock_l, legacy_pe.dock_h, legacy_pe.cover50, legacy_pe.cover
            )
        ),
    )
    from app.services.legacy_migration.parser import _PRECIP_DEFAULT_TEXT

    for key in PRECIPITATION_COLUMNS:
        setattr(precipitation, key, legacy_pe.precipitation.get(key, _PRECIP_DEFAULT_TEXT[key]))
    session.add(precipitation)
    width = PcpWidth(name=legacy_pe.name, groove_width=legacy_pe.groove_width, order_no=order_no)
    session.add(width)
    session.flush()
    if legacy_pe.widths or legacy_pe.groove_bs:
        _seed_widths(session, width, legacy_pe.widths, "work")
        _seed_widths(session, width, legacy_pe.groove_bs, "groove_b")
    else:
        # 新版围护导出已不含宽度数据（旧版 1.0 文件必有）：按新建面宽原则的
        # 同一默认表补齐，保证原则开箱可用
        from app.services.project_io import default_width_tables

        _seed_widths(session, width, default_width_tables()[0], "work")
        _seed_widths(session, width, default_width_tables()[1], "groove_b")
        report.defaults.append(f"围护原则“{legacy_pe.name}”的宽度表为空，已按默认表补齐。")
    works = legacy_pe.works or [
        _LegacyWork(min_depth=0.0, cpnt_cat=library.names("Ei")[0] if library.names("Ei") else "放坡")
    ]
    if not legacy_pe.works:
        report.defaults.append(f"围护原则“{legacy_pe.name}”没有围护做法，已按构件库默认项补一条。")
    for work_index, legacy_work in enumerate(works):
        work = EnclosureWork(
            enclosure_id=enclosure.id,
            min_depth=legacy_work.min_depth,
            cpnt_cat=legacy_work.cpnt_cat,
            order_no=work_index,
        )
        session.add(work)
        session.flush()
        if legacy_work.levels:
            for level_index, (name, h, step_width, component) in enumerate(legacy_work.levels):
                level = EnclosureLevel(
                    work_id=work.id, name=name, h=h, step_width=step_width, order_no=level_index
                )
                session.add(level)
                session.flush()
                _write_component(session, component, library, enclosure_level_id=level.id, report=report, group="Ei")
        else:
            level = EnclosureLevel(work_id=work.id, h=-1.0, step_width=1.0, order_no=0)
            session.add(level)
            session.flush()
            _write_component(session, None, library, enclosure_level_id=level.id, report=report, group="Ei")
        _write_component(session, legacy_work.waterstop, library, enclosure_work_id=work.id,
                         report=report, group="WSi", fallback="无")
    return enclosure


def write_legacy_foundation(session, legacy_pf: tuple[str, list[tuple[str, float]], object],
                            library, report: MigrationReport | None = None,
                            order_no: int = 0, pipe_base: dict | None = None,
                            legacy_meta: dict | None = None):
    """把旧版地基原则（(名称, 换填层列表, 特殊地基构件)）写入当前会话并返回。

    ``pipe_base`` 为 v10 起自旧版围护原则迁出的管道基础数据，形如
    ``{"con_found": bool, "found_angle": int, "cushion": (name, h)}``；
    旧版地基原则本身不带这些字段，由调用方按旧 PE 值传入。
    ``legacy_meta`` 记录生成来源（旧 PE / 旧 PF 名，PE×PF 交叉生成用）。
    """
    from app.core.models.models import FoundationCushion, FoundationReplacement, PcpFoundation

    report = report or MigrationReport()
    name, replacements, component = legacy_pf
    pipe_base = pipe_base or {}
    foundation = PcpFoundation(
        name=name,
        order_no=order_no,
        con_found=bool(pipe_base.get("con_found", True)),
        found_angle=int(pipe_base.get("found_angle", 120)),
        legacy_meta=json.dumps(legacy_meta, ensure_ascii=False) if legacy_meta else "",
    )
    session.add(foundation)
    session.flush()
    cushion = pipe_base.get("cushion")
    if cushion:
        cushion_name, cushion_h = cushion
        session.add(
            FoundationCushion(foundation_id=foundation.id, name=cushion_name, h=cushion_h, order_no=0)
        )
    for replace_index, (material, thickness) in enumerate(replacements):
        session.add(
            FoundationReplacement(foundation_id=foundation.id, name=material, h=thickness,
                                  order_no=replace_index)
        )
    _write_component(session, component, library, foundation_id=foundation.id,
                     report=report, group="Fi", fallback="无")
    return foundation


def _write_component(session, legacy_component, library,
                     *, group: str, report: MigrationReport, fallback: str = "", **owner) -> None:
    """把旧版 mcComponent 写入新库；空构件用构件库默认项补齐并记入补全项。"""
    from app.core.models.models import Component, ComponentParam

    if legacy_component is None or (not legacy_component.name and not legacy_component.params):
        names = library.names(group)
        template = library.template(group, names[0]) if names else None
        component = Component(
            name=template.name if template else (fallback or ""),
            formula=template.describe if template else "",
            **owner,
        )
        if template is not None:
            for key, (display, value) in template.params.items():
                component.params.append(ComponentParam(key=key, value=f"{display}|{value}"))
        session.add(component)
        session.flush()
        report.defaults.append(f"缺失的{group}构件已按构件库默认项补齐（“{component.name}”）。")
        return
    component = Component(name=legacy_component.name, formula=legacy_component.describe, **owner)
    session.add(component)
    session.flush()
    for key, display, value in legacy_component.params:
        session.add(ComponentParam(component_id=component.id, key=key, value=f"{display}|{value}"))
    # 旧数据可能缺参数（如钢板桩只有公式没有数值参数），用构件库同名条目补齐
    template = library.template(group, legacy_component.name)
    if template is not None:
        existing = {param.key for param in component.params}
        for key, (display, value) in template.params.items():
            if key not in existing:
                component.params.append(ComponentParam(key=key, value=f"{display}|{value}"))
                report.defaults.append(
                    f"构件“{legacy_component.name}”缺少参数 {key}（{display}），已按构件库默认值补齐。"
                )
