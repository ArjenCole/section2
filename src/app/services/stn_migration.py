"""旧 `.stn`(XML) → `.stn2` 一次性迁移（M6）。

定位：**单向只读迁移工具**——老工程的 `.stn` 文件任何情况下只读；
不追求 100% 还原，追求“数据不丢、能继续算”。

* 兼容 1.0.x ~ 1.2.2.x（`<1.2.1.1` 补箱涵含钢量参数；`<1.2.2.1`
  工作面宽度类别“箱涵”改“箱涵-管廊”，统一按最新语义处理）；
* 原则按名称匹配到新库，匹配不到的构件引用记入报告 warning，
  绝不静默丢数据或静默替换；
* 单个节点解析失败 → 跳过并记入报告；整体失败 → 抛出异常，由调用方
  删除半成品 `.stn2`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from app.core.models import base as orm
from app.core.models.models import (
    CATEGORY_NAMES,
    MULTI_PE_TEXT,
    MULTI_PF_TEXT,
    PRECIPITATION_COLUMNS,
    BasicInfo,
    Component,
    ComponentParam,
    Element,
    ElementParam,
    ElementPrinciple,
    EnclosureCushion,
    EnclosureLevel,
    EnclosureWork,
    PcpEnclosure,
    PcpFoundation,
    PcpPrecipitation,
    PcpWidth,
    Pipe,
    Price,
    Segment,
    Unit,
    WidthItem,
)

_CATEGORY_BY_NAME = {name: value for value, name in CATEGORY_NAMES.items()}
_LEGACY_CATEGORIES = tuple(CATEGORY_NAMES.values())

_PRECIP_DEFAULT_TEXT = {
    "wet_soil": "0|0|0",
    "light_well": "3.5|1.2|2",
    "jet_well": "6|2.5|2",
    "big_well": "10|10|2",
    "deep_well": "15|20|1",
}


@dataclass
class MigrationReport:
    """迁移报告：计数 + 警告/跳过明细（UI 必须展示，不得只写日志）。"""

    source: str = ""
    target: str = ""
    schema_version: str = ""
    segments: int = 0
    units: int = 0
    elements: int = 0
    pipes: int = 0
    enclosures: int = 0
    foundations: int = 0
    prices: int = 0
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    principle_names: list[str] = field(default_factory=list)

    def text(self) -> str:
        lines = [
            f"源文件：{self.source}",
            f"目标文件：{self.target}",
            f"旧版程序版本：{self.schema_version or '未知'}",
            f"标段 {self.segments} 个，单位工程 {self.units} 个，构件 {self.elements} 条，管道 {self.pipes} 根",
            f"围护原则 {self.enclosures} 条，地基原则 {self.foundations} 条，单价 {self.prices} 条",
            f"涉及原则：{'、'.join(self.principle_names) if self.principle_names else '（无）'}",
        ]
        if self.warnings:
            lines.append("")
            lines.append(f"警告 {len(self.warnings)} 条：")
            lines.extend(f"  · {warning}" for warning in self.warnings)
        if self.skipped:
            lines.append("")
            lines.append(f"跳过 {len(self.skipped)} 条：")
            lines.extend(f"  · {item}" for item in self.skipped)
        if not self.warnings and not self.skipped:
            lines.append("")
            lines.append("无警告，全部数据迁移成功。")
        return "\n".join(lines)


@dataclass
class _LegacyComponent:
    name: str = ""
    describe: str = ""
    params: list[tuple[str, str, str]] = field(default_factory=list)  # (key, display, value)


@dataclass
class _LegacyWork:
    min_depth: float = 0.0
    cpnt_cat: str = ""
    levels: list[tuple[str, float, float, _LegacyComponent]] = field(default_factory=list)
    waterstop: _LegacyComponent | None = None


@dataclass
class _LegacyEnclosure:
    name: str = ""
    con_found: bool = True
    excvt: str = "Ⅲ类土"
    found_angle: int = 120
    cushion: tuple[str, float] = ("中粗砂", 200.0)
    dock_l: str = "中粗砂"
    dock_h: str = "中粗砂"
    cover50: str = "中粗砂"
    cover: str = "素土"
    precipitation: dict[str, str] = field(default_factory=dict)
    groove_width: str = "WorkWidth"
    widths: dict[str, dict[int, float]] = field(default_factory=dict)
    groove_bs: dict[str, dict[int, float]] = field(default_factory=dict)
    works: list[_LegacyWork] = field(default_factory=list)


@dataclass
class _LegacyPipe:
    mat: str = ""
    dn: float = 600
    content: str = "1"


@dataclass
class _LegacyElement:
    name: str = ""
    category: str = ""
    depth: str = "0"
    amount: str = "0"
    pe_name: str = ""
    pf_name: str = ""
    main_pe_name: str = ""
    source: str = ""
    pipes: list[_LegacyPipe] = field(default_factory=list)
    params: list[tuple[str, str]] = field(default_factory=list)
    #: 多原则引用（旧版 PEname / PFname 字典：原则名 → 比例系数）
    pe_refs: list[tuple[str, float]] = field(default_factory=list)
    pf_refs: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class _LegacyUnit:
    name: str = ""
    elements: list[_LegacyElement] = field(default_factory=list)


@dataclass
class _LegacySegment:
    name: str = ""
    units: list[_LegacyUnit] = field(default_factory=list)


@dataclass
class LegacyProject:
    version: str = ""
    project_name: str = "新建项目"
    project_index: str = ""
    author: str = ""
    atlas_name: str = "06MS201-1"
    enclosures: list[_LegacyEnclosure] = field(default_factory=list)
    foundations: list[tuple[str, list[tuple[str, float]], _LegacyComponent]] = field(default_factory=list)
    segments: list[_LegacySegment] = field(default_factory=list)
    prices: list[tuple[str, float]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def parse_legacy(path: str | Path) -> LegacyProject:
    """解析旧 .stn；整体结构不对时抛 MigrationError。"""
    source = Path(path)
    if not source.exists():
        raise MigrationError(f"源文件不存在：{source}")
    try:
        tree = etree.parse(str(source))
    except etree.XMLSyntaxError as error:
        raise MigrationError(f"旧工程文件不是有效的 XML：{error}") from error
    root = tree.getroot()
    if root.tag != "Root":
        raise MigrationError("旧工程文件缺少 Root 根元素，无法识别。")

    legacy = LegacyProject()
    version_node = root.find("Assembly/Version")
    legacy.version = (version_node.text or "").strip() if version_node is not None else ""

    info = root.find("mcBasicInfo")
    if info is not None:
        legacy.project_name = _text(info, "ProjectName", "新建项目")
        legacy.project_index = _text(info, "ProjectIndex", "")
        legacy.author = _text(info, "Author", "")
        legacy.atlas_name = _text(info, "AtlasName", "06MS201-1")

    report = MigrationReport(source=str(source))
    for node in root.findall("mcPcpEnclosure"):
        try:
            legacy.enclosures.append(_parse_enclosure(node, legacy.version))
        except Exception as error:  # 单节点失败跳过
            report.skipped.append(f"围护原则“{_text(node, 'Name', '?')}”解析失败：{error}")
    for node in root.findall("mcPcpFoundation"):
        try:
            legacy.foundations.append(_parse_foundation(node))
        except Exception as error:
            report.skipped.append(f"地基原则“{_text(node, 'Name', '?')}”解析失败：{error}")
    for node in root.findall("mcSegment"):
        try:
            legacy.segments.append(_parse_segment(node))
        except Exception as error:
            report.skipped.append(f"标段“{_text(node, 'Name', '?')}”解析失败：{error}")
    for node in root.findall("Price"):
        try:
            name = _text(node, "name", "")
            value = float(_text(node, "price", "0") or 0)
            if name:
                legacy.prices.append((name, value))
        except Exception as error:
            report.skipped.append(f"单价解析失败：{error}")
    report.schema_version = legacy.version
    _report = report  # 供调用方复用（write_target 会重建报告）
    return legacy


class MigrationError(RuntimeError):
    """迁移整体失败。"""


def _text(node, tag: str, default: str = "") -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _parse_component(node) -> _LegacyComponent:
    component = _LegacyComponent()
    if node is None:
        return component
    name_node = node.find("Name")
    if name_node is not None and name_node.text:
        name, _, describe = name_node.text.partition("|")
        component.name = name.strip()
        component.describe = describe.strip()
    for child in node:
        tag = child.tag if isinstance(child.tag, str) else ""
        if tag in ("Name",) or child.text is None:
            continue
        display, _, value = child.text.partition("|")
        component.params.append((tag, display.strip(), value.strip()))
    return component


def _parse_enclosure(node, version: str) -> _LegacyEnclosure:
    enclosure = _LegacyEnclosure(
        name=_text(node, "Name", "新围护原则"),
        con_found=_text(node, "ConFound", "true").lower() != "false",
        excvt=_text(node, "Excvt", "Ⅲ类土"),
        found_angle=int(float(_text(node, "FoundAngle", "120") or 120)),
        dock_l=_text(node, "DockL", "中粗砂"),
        dock_h=_text(node, "DockH", "中粗砂"),
        cover50=_text(node, "Cover50", "中粗砂"),
        cover=_text(node, "Cover", "素土"),
        groove_width=_text(node, "grooveWidth", "WorkWidth"),
    )
    cushion = node.find("Cush/msReplacement")
    if cushion is not None:
        enclosure.cushion = (_text(cushion, "Name", "中粗砂"), float(_text(cushion, "H", "200") or 200))
    for key in PRECIPITATION_COLUMNS:
        legacy_key = {"wet_soil": "wetsoild", "light_well": "lightwell", "jet_well": "jetwell",
                      "big_well": "bigwell", "deep_well": "deepwell"}[key]
        child = node.find(legacy_key)
        enclosure.precipitation[key] = child.text.strip() if child is not None and child.text else _PRECIP_DEFAULT_TEXT[key]
    for kind, tag in (("widths", "WorkWidth"), ("groove_bs", "GrooveB")):
        container = node.find(tag)
        if container is None:
            continue
        table = getattr(enclosure, kind)
        for category_node in container:
            category = category_node.tag if isinstance(category_node.tag, str) else ""
            if version and _version_tuple(version) < (1, 2, 2, 1):
                category = {"箱涵": "箱涵-管廊"}.get(category, category)
            values: dict[int, float] = {}
            for dn_node in category_node:
                dn_text = (dn_node.tag or "").lstrip("d")
                try:
                    values[int(dn_text)] = float(dn_node.text or 0)
                except ValueError:
                    continue
            table[category] = values
    for work_node in node.findall("mcEnclosure"):
        work = _LegacyWork(
            min_depth=float(_text(work_node, "MinDepth", "0") or 0),
            cpnt_cat=_text(work_node, "eCpntCat", ""),
        )
        for level_node in work_node.findall("mcEclsCpnt"):
            work.levels.append(
                (
                    _text(level_node, "name", ""),
                    float(_text(level_node, "H", "-1") or -1),
                    float(_text(level_node, "stepWidth", "1") or 1),
                    _parse_component(level_node.find("mcComponent")),
                )
            )
        waterstop_node = work_node.find("WSCpnt/mcComponent")
        if waterstop_node is not None:
            work.waterstop = _parse_component(waterstop_node)
        enclosure.works.append(work)
    return enclosure


def _parse_foundation(node) -> tuple[str, list[tuple[str, float]], _LegacyComponent]:
    name = _text(node, "Name", "新地基原则")
    replacements = [
        (_text(child, "Name", "中粗砂"), float(_text(child, "H", "200") or 200))
        for child in node.findall("msReplacement")
    ]
    foundation_component = _parse_component(node.find("Foundation/mcComponent"))
    return name, replacements, foundation_component


def _parse_segment(node) -> _LegacySegment:
    segment = _LegacySegment(name=_text(node, "Name", "新建标段"))
    for unit_node in node.findall("mcUnit"):
        unit = _LegacyUnit(name=_text(unit_node, "Name", "新建单位工程"))
        for element_node in unit_node.findall("mcElement"):
            unit.elements.append(_parse_element(element_node))
        segment.units.append(unit)
    return segment


def _parse_element(node) -> _LegacyElement:
    element = _LegacyElement(
        name=_text(node, "Name", ""),
        category=_text(node, "Category", ""),
        depth=_text(node, "Depth", "0"),
        amount=_text(node, "Amount", "0"),
        pe_name=_text(node, "showPEname", ""),
        pf_name=_text(node, "showPFname", ""),
        main_pe_name=_text(node, "mainPEname", ""),
        source=_text(node, "Source", ""),
    )
    for pipe_node in node.findall("msPipe"):
        element.pipes.append(
            _LegacyPipe(
                mat=_text(pipe_node, "Mat", ""),
                dn=float(_text(pipe_node, "Dn", "0") or 0),
                content=_text(pipe_node, "Content", "1"),
            )
        )
    for param in node.findall("Param"):
        element.params.append((_text(param, "key", ""), _text(param, "value", "")))
    for kind, target in (("PEname", "pe"), ("PFname", "pf")):
        for ref_node in node.findall(kind):
            name = _text(ref_node, "key", "")
            if not name:
                continue
            try:
                ratio = float(_text(ref_node, "value", "1") or 1)
            except ValueError:
                ratio = 1.0
            if target == "pe":
                element.pe_refs.append((name, ratio))
            else:
                element.pf_refs.append((name, ratio))
    return element


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


# --------------------------------------------------------------------------- #
# 写入新库
# --------------------------------------------------------------------------- #
def migrate(source: str | Path, target: str | Path) -> MigrationReport:
    """解析旧工程并写入新的 .stn2；失败时删除半成品文件后抛出。"""
    target_path = Path(target)
    try:
        report = _migrate_inner(Path(source), target_path)
    except Exception:
        if target_path.exists():
            try:
                target_path.unlink()
            except OSError:
                pass
        raise
    return report


def _migrate_inner(source: Path, target: Path) -> MigrationReport:
    from app.services.atlas import component_library

    legacy = parse_legacy(source)
    library = component_library()
    report = MigrationReport(
        source=str(source), target=str(target), schema_version=legacy.version
    )

    if target.exists():
        target.unlink()
    orm.create_database(target)
    session = orm.session()

    session.add(
        BasicInfo(
            id=1,
            project_name=legacy.project_name or "新建项目",
            project_index=legacy.project_index,
            author=legacy.author,
            atlas_name=legacy.atlas_name or "06MS201-1",
        )
    )

    # 围护原则
    for index, legacy_pe in enumerate(legacy.enclosures):
        write_legacy_enclosure(session, legacy_pe, library, report, order_no=index)
        report.enclosures += 1
        report.principle_names.append(legacy_pe.name)

    # 地基原则
    for index, (name, replacements, component) in enumerate(legacy.foundations):
        write_legacy_foundation(
            session, (name, replacements, component), library, report, order_no=index
        )
        report.foundations += 1
        report.principle_names.append(name)

    # 标段 / 单位工程 / 构件 / 管道
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
            for element_index, legacy_element in enumerate(legacy_unit.elements):
                category = _CATEGORY_BY_NAME.get(legacy_element.category, 0)
                display_name = legacy_element.name or '(未命名)'
                # 多原则引用（旧版 PEname / PFname 字典）→ 引用行 + show 名
                pe_name, pe_refs, pe_warnings = _migrate_principle_refs(
                    "pe", legacy_element, _pe_names(legacy),
                    legacy.enclosures and legacy.enclosures[0].name or "",
                )
                pf_name, pf_refs, pf_warnings = _migrate_principle_refs(
                    "pf", legacy_element, _pf_names(legacy),
                    legacy.foundations and legacy.foundations[0][0] or "",
                )
                for warning in pe_warnings + pf_warnings:
                    report.warnings.append(f"构件“{display_name}”{warning}")
                main_pe_name = legacy_element.main_pe_name
                if len(pe_refs) > 1 and main_pe_name not in {name for name, _ratio in pe_refs}:
                    main_pe_name = pe_refs[0][0]
                # 降水/面宽引用随围护名拆出（v4 独立原则）；多围护等对不上号的
                # 落到第一条原则（旧版随各 PE 计算，独立后取默认一条）
                enclosure_names = {item.name for item in legacy.enclosures}
                default_pppw = legacy.enclosures[0].name if legacy.enclosures else ""
                element = Element(
                    unit_id=unit.id,
                    category=category,
                    name=legacy_element.name,
                    depth=legacy_element.depth or "0",
                    amount=legacy_element.amount or "0",
                    pe_name=pe_name,
                    pf_name=pf_name,
                    pp_name=pe_name if pe_name in enclosure_names else default_pppw,
                    pw_name=pe_name if pe_name in enclosure_names else default_pppw,
                    main_pe_name=main_pe_name,
                    source=legacy_element.source or "",
                    order_no=element_index,
                )
                session.add(element)
                session.flush()
                for order, (ref_name, ratio) in enumerate(pe_refs):
                    session.add(
                        ElementPrinciple(
                            element_id=element.id, kind="pe", name=ref_name,
                            ratio=ratio, order_no=order,
                        )
                    )
                for order, (ref_name, ratio) in enumerate(pf_refs):
                    session.add(
                        ElementPrinciple(
                            element_id=element.id, kind="pf", name=ref_name,
                            ratio=ratio, order_no=order,
                        )
                    )
                report.elements += 1
                for pipe_index, legacy_pipe in enumerate(legacy_element.pipes):
                    session.add(
                        Pipe(
                            element_id=element.id,
                            mat=legacy_pipe.mat,
                            dn=int(legacy_pipe.dn),
                            content=legacy_pipe.content or "1",
                        )
                    )
                    report.pipes += 1
                known_params = {key for key, _value in legacy_element.params}
                for key, value in legacy_element.params:
                    session.add(ElementParam(element_id=element.id, key=key, value=value))
                if category == 3 and "含钢量 kg/m3" not in known_params and _version_tuple(legacy.version or "0") < (1, 2, 1, 1):
                    session.add(ElementParam(element_id=element.id, key="含钢量 kg/m3", value="150"))
                    report.warnings.append(
                        f"旧版 <1.2.1.1：箱涵“{legacy_element.name or '(未命名)'}”补默认含钢量 150 kg/m³。"
                    )

    for key, value in legacy.prices:
        session.add(Price(key=key, value=value))
        report.prices += 1

    orm.commit()
    orm.close_database()
    report.warnings.extend(_dedupe(report.warnings))
    return report


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _pe_names(legacy: LegacyProject) -> set[str]:
    return {enclosure.name for enclosure in legacy.enclosures}


def _pf_names(legacy: LegacyProject) -> set[str]:
    return {name for name, _replacements, _component in legacy.foundations}


def _migrate_principle_refs(
    kind: str,
    element: _LegacyElement,
    known_names: set[str],
    fallback: str,
) -> tuple[str, list[tuple[str, float]], list[str]]:
    """迁移一个构件的原则引用，返回 (show 名, 有效引用列表, 警告列表)。

    多原则引用（旧版 PEname 字典）优先；没有引用行时按 show 名退化成
    单原则（比例 1）。引用的原则在旧文件中不存在 → 跳过该条并记警告；
    一条有效的都不剩 → 回落引用第一条原则（与旧版 GetData 一致）。
    """
    multi_text = MULTI_PE_TEXT if kind == "pe" else MULTI_PF_TEXT
    label = "围护" if kind == "pe" else "地基"
    warnings: list[str] = []
    raw_refs = element.pe_refs if kind == "pe" else element.pf_refs
    show = element.pe_name if kind == "pe" else element.pf_name
    if not raw_refs and show and show != multi_text:
        raw_refs = [(show, 1.0)]
    refs: list[tuple[str, float]] = []
    for name, ratio in raw_refs:
        if name in known_names:
            refs.append((name, ratio))
        else:
            warnings.append(f"引用的{label}原则“{name}”在旧文件中不存在，已跳过。")
    if not refs:
        if fallback:
            refs = [(fallback, 1.0)]
            warnings.append(f"未指定{label}原则，已引用“{fallback}”。")
        else:
            return "", [], warnings
    if len(refs) > 1:
        return multi_text, refs, warnings
    return refs[0][0], refs, warnings


def _seed_widths(session, width: PcpWidth, table: dict[str, dict[int, float]], kind: str) -> None:
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
                           order_no: int = 0) -> PcpEnclosure:
    """把旧版围护原则（mcPcpEnclosure 解析结果）写入当前会话并返回。

    迁移与 *.spcp 单原则导入共用；原则本体、垫层、做法/级别/构件全套写入。
    旧版挂在围护原则下的降水参数与宽度表，v4 起拆成与围护同名的独立
    降水/面宽原则一并写入（旧 PE 名在其各自表内即原则名）。
    """
    from app.core.models.models import PRECIPITATION_COLUMNS

    report = report or MigrationReport()
    enclosure = PcpEnclosure(
        name=legacy_pe.name,
        con_found=legacy_pe.con_found,
        excvt=legacy_pe.excvt,
        found_angle=legacy_pe.found_angle,
        dock_l=legacy_pe.dock_l,
        dock_h=legacy_pe.dock_h,
        cover50=legacy_pe.cover50,
        cover=legacy_pe.cover,
        order_no=order_no,
    )
    enclosure.cushions.append(
        EnclosureCushion(name=legacy_pe.cushion[0], h=legacy_pe.cushion[1], order_no=0)
    )
    session.add(enclosure)
    session.flush()
    precipitation = PcpPrecipitation(name=legacy_pe.name, order_no=order_no)
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
    works = legacy_pe.works or [
        _LegacyWork(min_depth=0.0, cpnt_cat=library.names("Ei")[0] if library.names("Ei") else "放坡")
    ]
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


def write_legacy_foundation(session, legacy_pf: tuple[str, list[tuple[str, float]], _LegacyComponent],
                            library, report: MigrationReport | None = None,
                            order_no: int = 0) -> PcpFoundation:
    """把旧版地基原则（(名称, 换填层列表, 特殊地基构件)）写入当前会话并返回。"""
    from app.core.models.models import FoundationReplacement

    report = report or MigrationReport()
    name, replacements, component = legacy_pf
    foundation = PcpFoundation(name=name, order_no=order_no)
    session.add(foundation)
    session.flush()
    for replace_index, (material, thickness) in enumerate(replacements):
        session.add(
            FoundationReplacement(foundation_id=foundation.id, name=material, h=thickness,
                                  order_no=replace_index)
        )
    _write_component(session, component, library, foundation_id=foundation.id,
                     report=report, group="Fi", fallback="无")
    return foundation


def _write_component(session, legacy_component: _LegacyComponent | None, library,
                     *, group: str, report: MigrationReport, fallback: str = "", **owner) -> None:
    """把旧版 mcComponent 写入新库；空构件用构件库默认项补齐并记警告。"""
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
                report.warnings.append(
                    f"构件“{legacy_component.name}”缺少参数 {key}（{display}），已按构件库默认值补齐。"
                )
