"""1.0 管道 → 2.0 构件库模板匹配（决策 1 / §4）。

1.0 管道只有 ``Mat / Dn / Content``；迁移时以 DN 为键到构件库资产
（``element_library()``）里匹配同材质、同 DN 的模板，从模板取
oD / iD / t（与 direct 直取对归一）与 a / C1 / C2（8 组候选）。

匹配优先级（已确认）：

1. 材质完全相等 + DN 完全相等 + 构件类别相同；
2. 材质包含（同级别内的前缀 / 后缀差异）+ DN 相等 + 类别相同；
3. 管材类别（``cat`` 折算）+ DN 相等 + 类别相同；
4. 同材质 + 1.0 TrimDn 映射 DN（1400→1350、1600→1650、2700→2800、
   >2800→3000），映射后仍按 1~3 的材质 / 类别规则；
5. 同材质 + 最近 DN（等距取大）；
6. 都不命中：不写 oD/iD/t，记 warning，计算由 2.0 图集兜底。

每一级都先限同构件类别，没有同类别候选时才放宽到其他类别并注明；
级别标记（Ⅰ/Ⅱ/Ⅲ 级、K8/K9/K10、MPa）必须一致，不跨级别包含匹配。
多个模板命中时只看 DN：DN 大者优先；DN 相同按"材质完全相等 → 级别
一致 → 类别相同 → 构件库顺序"，不比较 od/t。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.pipe_category import category_of_mat, normalize_category
from app.services.element_library import ElementTemplate, PipeTemplate, element_library

#: 1.0 TrimDn 映射（非标 DN → 图集标准 DN；>2800 统一 3000）
TRIM_DN_MAP: dict[int, int] = {1400: 1350, 1600: 1650, 2700: 2800}
TRIM_DN_LARGE_THRESHOLD = 2800
TRIM_DN_LARGE_TARGET = 3000

#: 级别标记：Ⅰ/Ⅱ/Ⅲ/Ⅳ 级混凝土管、K8/K9/K10 球墨管、PN 压力等级、MPa 压力等级
_LEVEL_RE = re.compile(r"[ⅠⅡⅢⅣ]级|K\d+|PN\d+|\d+(?:\.\d+)?\s*MPa", re.IGNORECASE)


def _level_markers(mat: str) -> frozenset[str]:
    """材质文本里的级别标记集合（归一为大写、去空白）。"""
    return frozenset(
        marker.replace(" ", "").upper() for marker in _LEVEL_RE.findall(mat or "")
    )


def _material_contains(a: str, b: str) -> bool:
    """材质包含关系：互为前后缀即命中；级别标记必须一致（不跨级别）。"""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if a not in b and b not in a:
        return False
    markers_a = _level_markers(a)
    markers_b = _level_markers(b)
    # 双方都有级别标记时必须完全一致；只有一方有（旧名省略级别）按同级别接受，
    # 命中候选在报告中列出，避免静默选错
    return not markers_a or not markers_b or markers_a == markers_b


def trim_dn(dn: float) -> int:
    """1.0 TrimDn 口径：非标 DN 映射到图集标准 DN。"""
    value = int(dn)
    if value in TRIM_DN_MAP:
        return TRIM_DN_MAP[value]
    if value > TRIM_DN_LARGE_THRESHOLD:
        return TRIM_DN_LARGE_TARGET
    return value


@dataclass(frozen=True)
class PipeMatch:
    """一次成功的匹配：模板管道 + 按直取对归一后的 oD / iD / t。"""

    template: ElementTemplate
    pipe: PipeTemplate
    #: 匹配用 DN（TrimDn 映射后；原 DN 由调用方保留）
    dn: int
    #: 兜底级别说明（报告中展示）
    level: str
    #: 该级放宽到其他构件类别时 True（报告注明）
    category_relaxed: bool
    od: float
    inner_d: float
    t: float
    direct: str
    #: 模板管道的管材类别（写回 Pipe.cat；空 = 留空按 mat 折算）
    cat: str


@dataclass(frozen=True)
class _Candidate:
    order: int
    template: ElementTemplate
    pipe: PipeTemplate


def all_candidates() -> list[_Candidate]:
    """构件库全部 (模板, 管道) 对，按库顺序编号（决胜用；一次构建全程复用）。"""
    library = element_library()
    result: list[_Candidate] = []
    order = 0
    for category_name in library.categories:
        for unit in library.units_of(category_name):
            for template in unit.elements:
                for pipe in template.pipes:
                    result.append(_Candidate(order, template, pipe))
                    order += 1
    return result


def _category_of(pipe: PipeTemplate) -> str:
    return normalize_category(pipe.cat, mat=pipe.mat)


def _select(
    candidates: list[_Candidate],
    mat: str,
    dn: int,
    category: int,
) -> tuple[_Candidate | None, bool]:
    """按决胜规则选一个候选：DN 大者优先，DN 相同按
    材质完全相等 → 级别一致 → 类别相同 → 库顺序。返回 (候选, 是否放宽类别)。"""
    if not candidates:
        return None, False
    exact_mat = (mat or "").strip()
    same_category = [c for c in candidates if c.template.category == category]
    relaxed = False
    pool = same_category
    if not pool:
        pool = candidates
        relaxed = True

    def sort_key(candidate: _Candidate) -> tuple:
        mat_equal = 0 if candidate.pipe.mat.strip() == exact_mat else 1
        level_equal = (
            0
            if not exact_mat
            or not candidate.pipe.mat.strip()
            or _level_markers(exact_mat) == _level_markers(candidate.pipe.mat)
            else 1
        )
        category_equal = 0 if candidate.template.category == category else 1
        return (-candidate.pipe.dn, mat_equal, level_equal, category_equal, candidate.order)

    ordered = sorted(pool, key=sort_key)
    return (ordered[0] if ordered else None), relaxed


def _describe(candidate: _Candidate) -> str:
    return f"{candidate.template.name or candidate.template.label}（{candidate.pipe.mat} DN{candidate.pipe.dn}）"


def match_pipe_template(
    mat: str,
    dn: float,
    category: int,
    con_found: bool,
    found_angle: int,
    *,
    candidates: list[_Candidate] | None = None,
) -> tuple[PipeMatch | None, str | None, list[str]]:
    """按优先级匹配模板，返回 ``(匹配, 失败原因, 附加说明列表)``。

    ``con_found`` / ``found_angle`` 取该子构件新 PF 的管道基础参数，用于
    模板八组壁厚里取 t。失败时 ``None`` + 原因（无材质 / 无 DN / 无模板 /
    模板无壁厚在归一化结果里另给说明）。
    """
    notes: list[str] = []
    material = (mat or "").strip()
    if not material:
        return None, "旧管道没有材质文字", notes
    if dn <= 0:
        return None, "旧管道 DN 无效", notes
    pool = candidates if candidates is not None else all_candidates()
    if not pool:
        return None, "构件库为空", notes

    def level_candidates(dn_target: int) -> tuple[list[_Candidate], _Candidate | None, bool, str]:
        exact = [c for c in pool if c.pipe.mat.strip() == material and c.pipe.dn == dn_target]
        chosen, relaxed = _select(exact, material, dn_target, category)
        if chosen is not None:
            return exact, chosen, relaxed, f"材质完全相等 + DN{dn_target} + 同类别"
        contains = [
            c
            for c in pool
            if c.pipe.dn == dn_target and _material_contains(material, c.pipe.mat)
        ]
        chosen, relaxed = _select(contains, material, dn_target, category)
        if chosen is not None:
            return contains, chosen, relaxed, f"材质包含（同级别）+ DN{dn_target} + 同类别"
        cat = category_of_mat(material)
        by_cat = [
            c for c in pool if c.pipe.dn == dn_target and _category_of(c.pipe) == cat
        ]
        chosen, relaxed = _select(by_cat, material, dn_target, category)
        if chosen is not None:
            return by_cat, chosen, relaxed, f"管材类别“{cat}” + DN{dn_target} + 同类别"
        return [], None, relaxed, ""

    # 1~3 级：原 DN
    level_pool, chosen, relaxed, level_text = level_candidates(int(dn))
    if chosen is None:
        # 4 级：TrimDn 映射 DN（映射后仍按 1~3 的材质/类别规则）
        mapped = trim_dn(dn)
        if mapped != int(dn):
            level_pool, chosen, relaxed, level_text = level_candidates(mapped)
            if chosen is not None:
                level_text = f"TrimDn {int(dn):g}→{mapped}，{level_text}"
    if chosen is None:
        # 5 级：同材质 + 最近 DN（等距取大）
        same_material = [
            c for c in pool if _material_contains(material, c.pipe.mat)
        ]
        if same_material:
            nearest = min(
                (c.pipe.dn for c in same_material),
                key=lambda value: (abs(value - dn), -value),
            )
            level_pool = [c for c in same_material if c.pipe.dn == nearest]
            chosen, relaxed = _select(level_pool, material, nearest, category)
            if chosen is not None:
                level_text = f"同材质最近 DN（{int(dn):g}→{nearest}）"
    if chosen is None:
        return None, f"构件库无同材质 / 同 DN 模板（材质“{material}”，DN{dn:g}）", notes
    if relaxed:
        notes.append("同构件类别内无候选，已放宽到其他类别匹配。")
    if len(level_pool) > 1:
        listed = "、".join(_describe(item) for item in sorted(level_pool, key=lambda c: c.order)[:5])
        notes.append(f"该级命中 {len(level_pool)} 个模板，按 DN 大者优先选定：{listed}。")

    od, inner, thickness, t_note = _normalized_dimensions(
        chosen.pipe, dn, con_found, found_angle
    )
    if t_note:
        notes.append(t_note)
    match = PipeMatch(
        template=chosen.template,
        pipe=chosen.pipe,
        dn=chosen.pipe.dn,
        level=level_text,
        category_relaxed=relaxed,
        od=od,
        inner_d=inner,
        t=thickness,
        direct=chosen.pipe.direct or "",
        cat=_category_of(chosen.pipe),
    )
    return match, None, notes


def _normalized_dimensions(
    pipe: PipeTemplate, dn: float, con_found: bool, found_angle: int
) -> tuple[float, float, float, str]:
    """按模板直取对归一 (oD, iD, t)（计划 §4.3）。

    t 先按 (砼基础, 角度) 取模板八组壁厚（thickness_at 已做同组就近 →
    砼组同角度兜底）；``od_id`` 型（结构壁管）t 由 oD − iD 反算。
    取不到壁厚时 t = 0 并给说明（计算时按图集兜底）。
    """
    note = ""
    direct = pipe.direct or ""
    if direct == "od_id":
        od = float(pipe.od or dn)
        inner = float(pipe.inner_d or dn)
        return od, inner, max((od - inner) / 2.0, 0.0), note
    t = pipe.thickness_at(con_found, found_angle)
    if t is None:
        note = f"模板“{pipe.mat} DN{pipe.dn:g}”无该基础形式的壁厚，t 记 0（计算时按图集兜底）。"
        t = 0.0
    if direct == "od_t":
        od = float(pipe.od or dn)
        return od, od - 2.0 * t, t, note
    # id_t 与 ""（直取对缺失）都以 iD 为基准
    inner = float(pipe.inner_d or dn)
    return inner + 2.0 * t, inner, t, note
