"""多原则拆分（决策 3 / 决策 4 / §6）。

1.0 的多原则引用（``PEname`` / ``PFname`` 字典：原则名 → 比例）在 2.0 已
取消。迁移按 1.0 ``mscGroove.Cal`` 的顺序（PE 外层、PF 内层）做笛卡尔积，
把原条目拆成多条单原则子构件：

* 每条数量 = 原数量 × PE 比例 × PF 比例（比例为 1 的因子省略）；
* 单组合不拆名（比例 ≠ 1 只改数量，名称保持原名）；
* 多组合名称 = ``原名·新PF名 百分比%``（新 PF 名本身是 ``旧PF·旧PE``）；
* 构筑物 / 顶管 / 牵引管的工程量不随原则比例变化（1.0 计算口径），**不拆**：
  围护取主原则（失效取第一条引用），地基取第一条引用，原始 refs 进
  ``legacy_meta``；
* 每条子构件携带 ``legacy_meta``：原构件完整 refs / 比例 + 自己分到的
  ``assigned_pe / assigned_pf / assigned_ratio`` + 旧来源；
* ``mainPEname`` 不再参与计算（决策 4），只进 ``legacy_meta`` 与来源摘要。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.models.models import CATEGORY_JACKING, CATEGORY_PULLING, CATEGORY_STRUCTURE
from app.services.legacy_migration.parser import (
    LEGACY_MULTI_PE_TEXT,
    LEGACY_MULTI_PF_TEXT,
    _LegacyElement,
)

#: 不拆的类别：构筑物 / 顶管 / 牵引管（1.0 工程量不使用多原则比例）
NO_SPLIT_CATEGORIES = (CATEGORY_STRUCTURE, CATEGORY_JACKING, CATEGORY_PULLING)

#: 来源列 / legacy_meta 的长度上限（Element.source 是 String(200)）
_SOURCE_LIMIT = 200


@dataclass
class Child:
    """拆分后的一个子条目（名称 / 数量原文 / 原则引用 / 比例）。"""

    name: str
    amount: str
    pe_name: str
    pf_name: str
    ratio: float
    legacy_meta: dict = field(default_factory=dict)


def valid_principle_refs(
    kind: str,
    element: _LegacyElement,
    known_names: set[str],
    fallback: str,
) -> tuple[list[tuple[str, float]], list[str]]:
    """收集一个构件的有效原则引用，返回 (引用列表, 警告列表)。

    旧版 PEname / PFname 字典优先；没有引用行时按 show 名退化成单原则
    （比例 1，"多围护原则/多地基原则"占位名不算原则）。引用的原则在旧
    文件中不存在 → 跳过该条并记警告；一条有效的都不剩 → 回落引用第一条
    原则（决策 11，与旧版 GetData 一致）。
    """
    label = "围护" if kind == "pe" else "地基"
    multi_text = LEGACY_MULTI_PE_TEXT if kind == "pe" else LEGACY_MULTI_PF_TEXT
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
    if not refs and fallback:
        refs = [(fallback, 1.0)]
        warnings.append(f"未指定{label}原则，已引用“{fallback}”。")
    return refs, warnings


def warn_ratios(
    display_name: str,
    category: int,
    pe_refs: list[tuple[str, float]],
    pf_refs: list[tuple[str, float]],
    report,
) -> None:
    """比例边界警告（§6.6）：单引用比例 ≠ 1、多引用合计 ≠ 1、负比例。

    构筑物 / 顶管 / 牵引管的原则不参与计算，不做提示。0 比例与合计 ≠ 1
    均按原比例计算、不归一化（决策 4），总量随比例缩放由报告注明。
    """
    if category in NO_SPLIT_CATEGORIES:
        return
    for label, refs in (("围护", pe_refs), ("地基", pf_refs)):
        for name, ratio in refs:
            if ratio < 0:
                report.warnings.append(
                    f"构件“{display_name}”的{label}原则“{name}”比例 {ratio:g} 为负数，"
                    "数量算式按原比例保留，请人工核对。"
                )
        if len(refs) == 1 and abs(refs[0][1] - 1.0) > 1e-9:
            report.warnings.append(
                f"构件“{display_name}”的{label}原则比例 {refs[0][1]:g} ≠ 1，"
                "数量已按该比例折算（决策 3）。"
            )
        elif len(refs) > 1:
            total = sum(ratio for _name, ratio in refs)
            if abs(total - 1.0) > 1e-9:
                report.warnings.append(
                    f"构件“{display_name}”{label}原则比例合计 {total:g} ≠ 1，"
                    "按原比例拆分、未归一化，条目总量将随合计缩放。"
                )


def migration_pairs(
    category: int,
    element: _LegacyElement,
    pe_refs: list[tuple[str, float]],
    pf_refs: list[tuple[str, float]],
) -> list[tuple[str, float, str, float]]:
    """把构件的原则引用展开成 (pe 名, pe 比例, pf 名, pf 比例) 组合列表。

    旧版 mscGroove.Cal 按组合逐对计算断面量后乘 (pe 比例 × pf 比例) 求和；
    2.0 取消多原则后，组合多于一个的条目按组合拆分（决策 3）。构筑物 /
    顶管 / 牵引管不拆（决策 18）：围护取主原则（失效取第一条引用，决策
    11），地基取第一条引用。引用为空（旧文件一条原则都没有）时返回空名
    组合，写出的条目两条原则引用留空。
    """
    if not pe_refs or not pf_refs:
        return [("", 1.0, "", 1.0)]
    if category in NO_SPLIT_CATEGORIES:
        pe_names = {name for name, _ratio in pe_refs}
        main = element.main_pe_name
        pe_name = main if main in pe_names else pe_refs[0][0]
        return [(pe_name, 1.0, pf_refs[0][0], 1.0)]
    return [
        (pe_name, pe_ratio, pf_name, pf_ratio)
        for pe_name, pe_ratio in pe_refs
        for pf_name, pf_ratio in pf_refs
    ]


def _amount_for(original: str, pe_ratio: float, pf_ratio: float) -> str:
    """子条目数量算式（§6.5）：原数量外包括号，比例因子为 1 的省略。

    原数量为空按 "0"；合成比例为 0 数量写 "0"（原始比例进 legacy_meta）；
    负比例保留算式（报告异常，不阻止迁移）。
    """
    text = original or "0"
    combined = pe_ratio * pf_ratio
    if combined == 0:
        return "0"
    factors = [f"{ratio:g}" for ratio in (pe_ratio, pf_ratio) if abs(ratio - 1.0) > 1e-12]
    if not factors:
        return text
    return f"({text})*{'*'.join(factors)}"


def _ratio_text(ratio: float) -> str:
    return f"{ratio * 100:g}%"


def _refs_json(refs: list[tuple[str, float]]) -> list[dict]:
    return [{"name": name, "ratio": ratio} for name, ratio in refs]


def _new_pf_name(pf_map: dict[tuple[str, str], str], pe_name: str, pf_name: str) -> str:
    """组合对应的新 PF 名；映射缺失（原则列表为空等）回退"旧PF·旧PE"拼接。"""
    return pf_map.get((pf_name, pe_name), f"{pf_name}·{pe_name}" if pf_name and pe_name else (pf_name or pe_name))


def child_name(original: str, pe_name: str, pf_name: str, ratio: float,
               pf_map: dict[tuple[str, str], str], multi: bool) -> str:
    """子条目名称（§6.4）：单组合保持原名；多组合 ``原名·新PF名 百分比%``。"""
    if not multi:
        return original
    percent = _ratio_text(ratio)
    suffix = f"{_new_pf_name(pf_map, pe_name, pf_name)} {percent}"
    if original:
        return f"{original}·{suffix}"
    return suffix


def split_children(
    element: _LegacyElement,
    pairs: list[tuple[str, float, str, float]],
    pf_map: dict[tuple[str, str], str],
    pe_refs: list[tuple[str, float]] | None = None,
    pf_refs: list[tuple[str, float]] | None = None,
) -> list[Child]:
    """把组合列表物化成子条目（§6.3~§6.5），每条带 legacy_meta。

    ``pe_refs`` / ``pf_refs`` 是原构件校验后的**完整**引用列表（构筑物 /
    顶管 / 牵引管不拆时也要全部留档，见 §6.9）；缺省从 pairs 反推。
    """
    multi = len(pairs) > 1
    full_pe_refs = pe_refs if pe_refs is not None else pe_refs_of(element, pairs)
    full_pf_refs = pf_refs if pf_refs is not None else pf_refs_of(element, pairs)
    children: list[Child] = []
    for pe_name, pe_ratio, pf_name, pf_ratio in pairs:
        ratio = pe_ratio * pf_ratio
        child = Child(
            name=child_name(element.name, pe_name, pf_name, ratio, pf_map, multi),
            amount=_amount_for(element.amount, pe_ratio, pf_ratio),
            pe_name=pe_name,
            pf_name=_new_pf_name(pf_map, pe_name, pf_name),
            ratio=ratio,
        )
        child.legacy_meta = {
            "show_pe_name": element.pe_name or "",
            "show_pf_name": element.pf_name or "",
            "main_pe_name": element.main_pe_name or "",
            "pe_refs": _refs_json(full_pe_refs),
            "pf_refs": _refs_json(full_pf_refs),
            "assigned_pe": pe_name,
            "assigned_pf": child.pf_name,
            "assigned_ratio": ratio,
            "source": (element.source or "").strip(),
            "source_version": "",
        }
        children.append(child)
    return children


def pe_refs_of(element: _LegacyElement, pairs) -> list[tuple[str, float]]:
    """原构件的完整围护引用（legacy_meta 用；拆分调用方校验后传入 pairs）。"""
    seen: dict[str, float] = {}
    for pe_name, pe_ratio, _pf, _pf_ratio in pairs:
        seen.setdefault(pe_name, pe_ratio)
    return [(name, ratio) for name, ratio in seen.items() if name]


def pf_refs_of(element: _LegacyElement, pairs) -> list[tuple[str, float]]:
    """原构件的完整地基引用（legacy_meta 用）。"""
    seen: dict[str, float] = {}
    for _pe, _pe_ratio, pf_name, pf_ratio in pairs:
        seen.setdefault(pf_name, pf_ratio)
    return [(name, ratio) for name, ratio in seen.items() if name]


def source_summary(element: _LegacyElement, pe_refs, pf_refs) -> str:
    """来源列摘要（决策 15 / §2.2）：``旧Source｜1.0迁移｜PE:…｜PF:…｜主PE:…``。

    旧 Source 原文保留在最前（完整原文同时存 legacy_meta["source"]）；
    超长截断到 200。
    """
    parts = ["1.0迁移"]
    if pe_refs:
        parts.append("PE:" + ",".join(f"{name}{_ratio_text(ratio)}" for name, ratio in pe_refs))
    if pf_refs:
        parts.append("PF:" + ",".join(f"{name}{_ratio_text(ratio)}" for name, ratio in pf_refs))
    if element.main_pe_name:
        parts.append(f"主PE:{element.main_pe_name}")
    summary = "｜".join(parts)
    old_source = (element.source or "").strip()
    if old_source:
        summary = f"{old_source}｜{summary}"
    return summary[:_SOURCE_LIMIT]
