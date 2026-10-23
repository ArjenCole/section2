"""构件库（元素模板库）：读取带图集快照的 ``EleInventory.json``。

旧版主窗体左下角构件库 = mscInventory.Elei（``bin\\Debug\\Inventory\\EleInventory.stn``），
与工程 .stn 同为 XML，只有管材名称与旧参数。新版把它离线快照成 JSON 资产
（见 ``scripts/build_element_inventory.py``）：每个模板带上

* 每根管的 **管材类别**（``cat``）与 **图集壁厚**（90 / 120 / 180 三套）；
* 构件的 **工作面加宽 / 垫层厚 / 基础厚**（三套角度）。

运行时不再查图集表：插入时按当前围护原则的基础角度取一套写进条目，
之后计算、断面、面宽、包封扣管位都只读条目自身。

没有 JSON 时退回解析旧 .stn（此时没有快照，插入按现场查图集补值）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.models.models import CATEGORY_NAMES
from app.core.paths import resources_dir
from app.core.pipe_category import PIPE_CATEGORIES, category_of_mat, normalize_category
from app.services.stn_migration import LegacyProject, parse_legacy

_CATEGORY_BY_NAME = {name: value for value, name in CATEGORY_NAMES.items()}

#: 基础角度全集（资产里的快照键）
ATLAS_ANGLES: tuple[int, ...] = (90, 120, 150, 180)


@dataclass(frozen=True)
class PipeTemplate:
    """模板里的一根管：管材类别 + 材质 + 管径 + 含量 + 八组图集壁厚。"""

    mat: str
    cat: str
    dn: int
    content: str
    #: {"con90": 19.0, "plain120": None, …} 八组（砼/非砼 × 4 角度）；
    #: 图集查不到的组合为 None
    thickness: dict[str, float | None] = field(default_factory=dict)

    def thickness_at(self, con_found: bool, angle: int) -> float | None:
        """按 (基础形式, 角度) 取壁厚，缺该组合时按就近角度取。"""
        return nearest_value(self.thickness, con_found, angle)


@dataclass(frozen=True)
class ElementTemplate:
    """一个可插入的元素模板（旧版 mcElement 深拷贝的对应物 + 图集快照）。"""

    category: int
    name: str
    depth: str
    amount: str
    source: str
    pipes: tuple[PipeTemplate, ...]
    params: tuple[tuple[str, str], ...]
    #: 树节点文本：名称为空时用规格（原版 femE.Specification() 回退）
    label: str
    #: {"con90": (a, C1, C2) | None, …} 八组（砼/非砼 × 4 角度），mm；
    #: 无图集参数的类别（顶管 / 牵引 / 构筑物）为空
    atlas: dict[str, tuple[float, float, float] | None] = field(default_factory=dict)

    def atlas_at(self, con_found: bool, angle: int) -> tuple[float, float, float] | None:
        """按 (基础形式, 角度) 取快照，缺该组合时按就近角度取。"""
        return nearest_value(self.atlas, con_found, angle)


def nearest_value(table: dict[str, object], con_found: bool, angle: int):
    """按 (con_found, 角度就近) 取候选值；表为空或组全缺时返回 None。"""
    if not table:
        return None
    from app.core.atlas_candidates import CANDIDATE_ANGLES, combo_key

    wanted = combo_key(con_found, angle)
    if wanted in table:
        return table[wanted]
    # 就近角度（等距取小的），仍限于同一基础形式
    prefix = "con" if con_found else "plain"
    candidates = [
        key
        for key in table
        if key.startswith(prefix) and any(key == f"{prefix}{a}" for a in CANDIDATE_ANGLES)
    ]
    if not candidates:
        return None
    best = min(
        candidates,
        key=lambda key: (
            abs(int(key.removeprefix(prefix)) - int(angle)),
            int(key.removeprefix(prefix)),
        ),
    )
    return table[best]


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


def inventory_path() -> Path:
    """带图集快照的构件库资产（运行期只读这个）。"""
    return resources_dir() / "inventory" / "EleInventory.json"


def ele_inventory_path() -> Path:
    """旧版 .stn（只在没有 JSON 资产时兜底，另作资产生成脚本的输入）。"""
    return resources_dir() / "inventory" / "EleInventory.stn"


@lru_cache(maxsize=1)
def element_library() -> ElementLibrary:
    path = inventory_path()
    if path.exists():
        return _from_asset(path)
    return _from_legacy(parse_legacy(ele_inventory_path()))


def reload_library() -> None:
    """清缓存（资产重新生成后调用）。"""
    element_library.cache_clear()


def search_templates(category: str | None = None, keyword: str = "") -> list[dict]:
    """关键词检索构件库模板（AI 工具用；index 寻址对模型不友好）。

    返回 ``[{category, unit, index, template}]``；category 为空时搜索全部类别，
    keyword 匹配模板 label / name / 规格文本（大小写不敏感）。
    """
    library = element_library()
    categories = [category] if category else list(library.categories)
    needle = (keyword or "").strip().lower()
    results: list[dict] = []
    for category_name in categories:
        if category_name not in library.units:
            continue
        for unit in library.units_of(category_name):
            for index, template in enumerate(unit.elements):
                haystack = " ".join(
                    [template.label, template.name, template.source]
                    + [f"{pipe.mat} {pipe.cat}" for pipe in template.pipes]
                ).lower()
                if needle and needle not in haystack:
                    continue
                results.append(
                    {
                        "category": category_name,
                        "unit": unit.name,
                        "index": index,
                        "template": template,
                    }
                )
    return results


# --------------------------------------------------------------------------- #
# 资产读取
# --------------------------------------------------------------------------- #
def _from_asset(path: Path) -> ElementLibrary:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"构件库资产无法读取：{path}（{error}）") from error

    categories: list[str] = []
    units: dict[str, tuple[LibraryUnit, ...]] = {}
    for segment in payload.get("categories", []):
        name = str(segment.get("name") or "")
        categories.append(name)
        units[name] = tuple(
            LibraryUnit(
                name=str(unit.get("name") or ""),
                elements=tuple(_template_from_asset(element) for element in unit.get("elements", [])),
            )
            for unit in segment.get("units", [])
        )
    return ElementLibrary(categories=tuple(categories), units=units)


def _template_from_asset(element: dict) -> ElementTemplate:
    category = _CATEGORY_BY_NAME.get(str(element.get("category") or ""), 1)
    pipes = tuple(
        PipeTemplate(
            mat=str(pipe.get("mat") or ""),
            cat=normalize_category(str(pipe.get("cat") or ""), mat=str(pipe.get("mat") or "")),
            dn=int(pipe.get("dn") or 0),
            content=str(pipe.get("content") or "1"),
            thickness={
                str(key): (float(value) if value is not None else None)
                for key, value in (pipe.get("t") or {}).items()
            },
        )
        for pipe in element.get("pipes", [])
    )
    params = tuple(
        (str(key), str(value)) for key, value in (element.get("params") or [])
    )
    atlas = {}
    for key, row in (element.get("atlas") or {}).items():
        if row is None or all(row.get(f) is None for f in ("a", "c1", "c2")):
            atlas[str(key)] = None  # 图集该组合没有数据（如砼基础 150°）
        else:
            atlas[str(key)] = tuple(
                float(row[f]) if row.get(f) is not None else None
                for f in ("a", "c1", "c2")
            )
    name = str(element.get("name") or "").strip()
    param_dict = dict(params)
    label = name or _specification(category, [(p.mat, p.dn, p.content) for p in pipes], param_dict)
    if not label and pipes:
        # 个别旧版模板 Category 为空（如非开挖管道两例），按首根管材兜底显示
        label = f"{pipes[0].mat} Dn{pipes[0].dn}"
    if not label:
        # 构件库个别构筑物模板 Name 为空（单篦/双篦雨水口等），按“-名称”参数兜底
        label = param_dict.get("-名称", "")
    return ElementTemplate(
        category=category,
        name=name,
        depth=str(element.get("depth") or "").strip() or "0",
        amount=str(element.get("amount") or "").strip() or "0",
        source=str(element.get("source") or "").strip(),
        pipes=pipes,
        params=params,
        label=label,
        atlas=atlas,
    )


# --------------------------------------------------------------------------- #
# 旧 .stn 兜底（没有 JSON 资产时）
# --------------------------------------------------------------------------- #
def _from_legacy(legacy: LegacyProject) -> ElementLibrary:
    categories: list[str] = []
    units: dict[str, tuple[LibraryUnit, ...]] = {}
    for segment in legacy.segments:
        categories.append(segment.name)
        units[segment.name] = tuple(
            LibraryUnit(
                name=unit.name,
                elements=tuple(_template(element) for element in unit.elements),
            )
            for unit in segment.units
        )
    return ElementLibrary(categories=tuple(categories), units=units)


def _template(element) -> ElementTemplate:
    category = _CATEGORY_BY_NAME.get(element.category, 1)
    pipes = tuple(
        PipeTemplate(
            mat=pipe.mat,
            cat=category_of_mat(pipe.mat),
            dn=int(pipe.dn),
            content=str(pipe.content),
        )
        for pipe in element.pipes
    )
    params = tuple(element.params)
    name = element.name.strip()
    param_dict = dict(params)
    label = name or _specification(category, [(p.mat, p.dn, p.content) for p in pipes], param_dict)
    if not label and pipes:
        label = f"{pipes[0].mat} Dn{pipes[0].dn}"
    if not label:
        label = param_dict.get("-名称", "")
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


__all__ = [
    "ATLAS_ANGLES",
    "ElementLibrary",
    "ElementTemplate",
    "LibraryUnit",
    "PIPE_CATEGORIES",
    "PipeTemplate",
    "ele_inventory_path",
    "element_library",
    "inventory_path",
    "reload_library",
    "search_templates",
]
