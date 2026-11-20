"""1.0 XML → :class:`LegacyProject` 解析。

从旧 ``stn_migration`` 迁入，增加两处改造（计划 §8）：

* :func:`parse_legacy` 返回 ``(LegacyProject, MigrationReport)``，解析阶段
  的 skipped 不再丢（可传入外部 report 直接写入）；
* ``_parse_segment`` 逐 ``mcElement`` 容错：单个元素解析失败只跳过该元素
  （记标段/单位/序号/名称/原因），不再丢整个标段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from app.core.models.models import CATEGORY_NAMES, PRECIPITATION_COLUMNS
from app.services.legacy_migration.report import MigrationReport

_CATEGORY_BY_NAME = {name: value for value, name in CATEGORY_NAMES.items()}

#: 旧版 showPEname / showPFname 在多原则模式下的占位显示名（仅旧文件里出现）
LEGACY_MULTI_PE_TEXT = "多围护原则"
LEGACY_MULTI_PF_TEXT = "多地基原则"

_PRECIP_DEFAULT_TEXT = {
    "wet_soil": "0|0|0",
    "light_well": "3.5|1.2|2",
    "jet_well": "6|2.5|2",
    "big_well": "10|10|2",
    "deep_well": "15|20|1",
}

_LEGACY_PRECIP_KEYS = {
    "wet_soil": "wetsoild",
    "light_well": "lightwell",
    "jet_well": "jetwell",
    "big_well": "bigwell",
    "deep_well": "deepwell",
}


class MigrationError(RuntimeError):
    """迁移整体失败。"""


def category_from_name(name: str) -> int:
    """旧 Category 文本 → 2.0 类别号；未知文本返回 0（空）。"""
    return _CATEGORY_BY_NAME.get(name, 0)


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
    #: 管顶以上回填高度 cm（v11 新增标签 CoverH；旧文件没有 = None，按材质反推）
    cover_h: float | None = None
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
    foundations: list[tuple[str, list[tuple[str, float]], _LegacyComponent, dict | None]] = field(default_factory=list)
    segments: list[_LegacySegment] = field(default_factory=list)
    prices: list[tuple[str, float]] = field(default_factory=list)


def parse_legacy(path: str | Path, report: MigrationReport | None = None) -> tuple[LegacyProject, MigrationReport]:
    """解析旧 .stn；返回 (工程, 报告)。整体结构不对时抛 MigrationError。

    ``report`` 传入外部报告实例时解析阶段的 skipped / 警告直接写入它
    （与后续迁移阶段共用，不再丢失）；None 时新建。
    """
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

    report = report or MigrationReport()
    report.source = str(source)
    report.schema_version = legacy.version
    for node in root.findall("mcPcpEnclosure"):
        try:
            legacy.enclosures.append(_parse_enclosure(node, legacy.version))
        except Exception as error:  # 单节点失败跳过，原因进报告
            report.skipped.append(f"围护原则“{_text(node, 'Name', '?')}”解析失败：{error}")
    for node in root.findall("mcPcpFoundation"):
        try:
            legacy.foundations.append(_parse_foundation(node))
        except Exception as error:
            report.skipped.append(f"地基原则“{_text(node, 'Name', '?')}”解析失败：{error}")
    for node in root.findall("mcSegment"):
        try:
            legacy.segments.append(_parse_segment(node, legacy.version, report))
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
    return legacy, report


def _text(node, tag: str, default: str = "") -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _optional_float(text: str) -> float | None:
    """可缺省的数值标签：空 / 非数字一律 None（由调用方按旧口径反推）。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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
        cover_h=_optional_float(_text(node, "CoverH", "")),
        groove_width=_text(node, "grooveWidth", "WorkWidth"),
    )
    cushion = node.find("Cush/msReplacement")
    if cushion is not None:
        enclosure.cushion = (_text(cushion, "Name", "中粗砂"), float(_text(cushion, "H", "200") or 200))
    for key in PRECIPITATION_COLUMNS:
        child = node.find(_LEGACY_PRECIP_KEYS[key])
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


def _parse_foundation(node) -> tuple[str, list[tuple[str, float]], _LegacyComponent, dict | None]:
    """解析地基原则节点。

    返回 ``(名称, 换填层列表, 特殊地基构件, 管道基础)``；管道基础形如
    ``{"con_found": bool, "found_angle": int, "cushion": (name, h)}``。
    旧 1.0 ``.stn`` 的地基节点不带这些字段（v10 前挂在围护原则下）时返回
    ``None``；新版 ``.spcp`` 导出会带上，供导入时还原。
    """
    name = _text(node, "Name", "新地基原则")
    replacements = [
        (_text(child, "Name", "中粗砂"), float(_text(child, "H", "200") or 200))
        for child in node.findall("msReplacement")
    ]
    foundation_component = _parse_component(node.find("Foundation/mcComponent"))
    pipe_base: dict | None = None
    if node.find("ConFound") is not None or node.find("FoundAngle") is not None or node.find("Cush") is not None:
        cushion_node = node.find("Cush/msReplacement")
        cushion = (
            _text(cushion_node, "Name", "中粗砂"),
            float(_text(cushion_node, "H", "200") or 200),
        ) if cushion_node is not None else None
        pipe_base = {
            "con_found": _text(node, "ConFound", "true").lower() != "false",
            "found_angle": int(float(_text(node, "FoundAngle", "120") or 120)),
            "cushion": cushion,
        }
    return name, replacements, foundation_component, pipe_base


def _parse_segment(node, version: str, report: MigrationReport) -> _LegacySegment:
    """解析标段；逐元素容错——坏元素只跳过自己（计划 §8.2）。"""
    segment = _LegacySegment(name=_text(node, "Name", "新建标段"))
    for unit_index, unit_node in enumerate(node.findall("mcUnit")):
        unit = _LegacyUnit(name=_text(unit_node, "Name", "新建单位工程"))
        for element_index, element_node in enumerate(unit_node.findall("mcElement")):
            try:
                unit.elements.append(_parse_element(element_node))
            except Exception as error:
                report.skipped.append(
                    f"标段“{segment.name}”单位工程“{unit.name}”（第 {unit_index + 1} 个）"
                    f"第 {element_index + 1} 条构件“{_text(element_node, 'Name', '(未命名)')}”"
                    f"解析失败，已跳过：{error}"
                )
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
