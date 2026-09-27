"""构件库（元素模板库）：直接复用旧版 EleInventory.stn。

旧版主窗体左下角构件库 = mscInventory.Elei（bin\\Debug\\Inventory\\EleInventory.stn），
与工程 .stn 同为 XML 格式，用 stn_migration.parse_legacy 解析后转成轻量模板，
供左栏构件库树展示、双击插入单位工程主表格。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.paths import resources_dir
from app.orm.models import CATEGORY_NAMES
from app.services.stn_migration import LegacyProject, parse_legacy

_CATEGORY_BY_NAME = {name: value for value, name in CATEGORY_NAMES.items()}


@dataclass(frozen=True)
class ElementTemplate:
    """一个可插入的元素模板（旧版 mcElement 深拷贝的对应物）。"""

    category: int
    name: str
    depth: str
    amount: str
    source: str
    #: (材质, 管径mm, 含量) 列表
    pipes: tuple[tuple[str, int, str], ...]
    params: tuple[tuple[str, str], ...]
    #: 树节点文本：名称为空时用规格（原版 femE.Specification() 回退）
    label: str


@dataclass(frozen=True)
class LibraryUnit:
    """类别下的单元（旧版 mcSegment.Unit，树的第一层）。"""

    name: str
    elements: tuple[ElementTemplate, ...]


@dataclass(frozen=True)
class ElementLibrary:
    categories: tuple[str, ...]
    units: dict[str, tuple[LibraryUnit, ...]]

    def units_of(self, category: str) -> tuple[LibraryUnit, ...]:
        return self.units.get(category, ())

    def find(self, category: str, unit: str, index: int) -> ElementTemplate | None:
        """按树节点定位模板（原版 TVEleIvt_NodeMouseDoubleClick 的 e.Node.Index）。"""
        units = self.units_of(category)
        for lib_unit in units:
            if lib_unit.name == unit and 0 <= index < len(lib_unit.elements):
                return lib_unit.elements[index]
        return None


def ele_inventory_path() -> Path:
    return resources_dir() / "inventory" / "EleInventory.stn"


@lru_cache(maxsize=1)
def element_library() -> ElementLibrary:
    legacy: LegacyProject = parse_legacy(ele_inventory_path())
    categories: list[str] = []
    units: dict[str, tuple[LibraryUnit, ...]] = {}
    for segment in legacy.segments:
        categories.append(segment.name)
        lib_units = tuple(
            LibraryUnit(
                name=unit.name,
                elements=tuple(_template(element) for element in unit.elements),
            )
            for unit in segment.units
        )
        units[segment.name] = lib_units
    return ElementLibrary(categories=tuple(categories), units=units)


def _template(element) -> ElementTemplate:
    category = _CATEGORY_BY_NAME.get(element.category, 1)
    pipes = tuple(
        (pipe.mat, int(pipe.dn), str(pipe.content)) for pipe in element.pipes
    )
    params = tuple(element.params)
    name = element.name.strip()
    label = name or _specification(category, pipes, dict(params))
    if not label and pipes:
        # 个别旧版模板 Category 为空（如非开挖管道两例），按首根管材兜底显示
        label = f"{pipes[0][0]} Dn{pipes[0][1]}"
    return ElementTemplate(
        category=category,
        name=name,
        depth=(element.depth or "").strip() or "0",
        amount=(element.amount or "").strip() or "0",
        source=(element.source or "").strip(),
        pipes=pipes,
        params=params,
        label=label,
    )


def _float_or(params: dict[str, str], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _specification(
    category: int,
    pipes: tuple[tuple[str, int, str], ...],
    params: dict[str, str],
) -> str:
    """模板规格文本（旧版 mcE1~mcE6 Specification() 的只读复刻，参数算不出时不强求）。"""
    if category == 1:
        if pipes:
            mat, dn, _ = pipes[0]
            return f"{mat} Dn{dn}"
        return ""
    if category in (2, 4, 5):
        parts = []
        for mat, dn, content in pipes:
            try:
                count = float(content)
            except ValueError:
                count = 1.0
            if count == 0:
                continue
            if count == 1:
                parts.append(f"D{dn}{mat}")
            else:
                parts.append(f"{count:g}×D{dn}{mat}")
        tail = {2: " 包封", 4: " 顶管", 5: " 牵引管"}.get(category, "")
        return "+".join(parts) + tail if parts else ""
    if category == 3:
        width = _float_or(params, "净宽 m(含内壁厚度)", 0.0)
        height = _float_or(params, "净高 m", 0.0)
        return f"{width:g}×{height:g}箱涵" if width and height else ""
    if category == 6:
        width = _float_or(params, "外包宽 m", 0.0)
        height = _float_or(params, "外包高 m", 0.0)
        return f"{width:g}×{height:g}管廊断面" if width and height else ""
    return ""
