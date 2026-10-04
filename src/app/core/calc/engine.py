"""计算总入口（复刻旧版 mscGroove.Cal + mcElement.getDQ，计划 §6.1）。

一个构件条目的工程量 = 沟槽断面（挖方/换填/垫层/回填） + 降水 + 围护 + 特殊地基
+ 支撑（Z 类公式） + 管道基础（扣占土） + 管材，全部按“每延米”计算后 ×数量。

构件公式（旧版 mcComponent）求值也在这里：参数引用递归代入 →
height/width/count 代入 → core.evaluator 求值，失败按 0 处理（同旧版 mscExp）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.evaluator import evaluate, evaluate_or_default, format_number
from app.core.models.models import (
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_GALLERY,
    CATEGORY_STRUCTURE,
    MULTI_PE_TEXT,
    MULTI_PF_TEXT,
    Element,
    PcpEnclosure,
    PcpFoundation,
)
from app.services import atlas as atlas_service
from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas
from app.core.calc import foundation, groove, precipitation
from app.core.calc.tracer import QDict, fmt
from app.core.evaluator import EvalError

_CYCLE = "参数循环引用"

#: 各类别构件的默认扩展参数（旧版 mcE2/mcE3/mcE6 构造函数）
_DEFAULT_PARAMS: dict[int, dict[str, float]] = {
    CATEGORY_ENCASED: {"包封宽 m": 1.5, "包封高 m": 1.0},
    CATEGORY_BOX_CULVERT: {
        "净宽 m(含内壁厚度)": 3.5,
        "净高 m": 2.0,
        "底板厚 mm": 400,
        "顶板厚 mm": 300,
        "外壁厚 mm": 350,
        "内壁 道": 0,
        "内壁厚 mm": 250,
        "含钢量 kg/m3": 150,
    },
    CATEGORY_GALLERY: {
        "外包宽 m": 6.8,
        "外包高 m": 3.2,
        "底板厚 mm": 400,
        "顶板厚 mm": 300,
        "外壁厚 mm": 350,
        "内壁 道": 0,
        "内壁厚 mm": 250,
        "含钢量 kg/m3": 160,
    },
}

#: 附属构筑物默认参数（旧版 mcE7 构造函数；值为文本，不能并入上面的数值表）
STRUCTURE_DEFAULT_PARAMS: tuple[tuple[str, str], ...] = (
    ("-名称", "自定义构筑物"),
    ("-单位", "个"),
)


@dataclass
class ElementInput:
    """参与计算的构件快照（深度/数量已求值，参数已合并默认值）。

    ``pe_refs`` / ``pf_refs`` 为多原则引用（旧版 PEname / PFname 字典，
    (原则, 比例) 列表）；为空时退化为单原则 ``pe`` × ``pf``（比例 1）。
    沟槽断面 / 降水 / 围护 / 特殊地基按 pe×pf 组合逐对计算后乘比例求和；
    回填材质命名、支撑、管道基础用主原则 ``pe``（旧版 mainPEname）。
    """

    category: int
    name: str = ""
    depth: float = 0.0
    amount: float = 0.0
    pipes: list[PipeSpec] = field(default_factory=list)
    pipe_contents: list[float] = field(default_factory=list)
    params: dict[str, float] = field(default_factory=dict)
    #: 构件参数原文（附属构筑物的工程量键值对用，含“-名称”等非数值参数）
    raw_params: dict[str, str] = field(default_factory=dict)
    pe: PcpEnclosure | None = None
    pf: PcpFoundation | None = None
    pe_refs: list[tuple[PcpEnclosure, float]] = field(default_factory=list)
    pf_refs: list[tuple[PcpFoundation, float]] = field(default_factory=list)

    @property
    def size_b(self) -> float:
        """断面宽 m（旧版 rtSizeB）。"""
        params = self.params
        if self.category in (CATEGORY_BURIED, 4, 5):
            return (self.pipes[0].dn / 1000.0) if self.pipes else 0.0
        if self.category == CATEGORY_ENCASED:
            return params.get("包封宽 m", 1.5)
        if self.category == CATEGORY_BOX_CULVERT:
            return params.get("净宽 m(含内壁厚度)", 3.5) + params.get("外壁厚 mm", 350) * 2 / 1000.0
        if self.category == CATEGORY_GALLERY:
            return params.get("外包宽 m", 6.8)
        return 0.0

    @property
    def size_h(self) -> float:
        """断面高 m（旧版 rtSizeH）。"""
        params = self.params
        if self.category in (CATEGORY_BURIED, 4, 5):
            return (self.pipes[0].dn / 1000.0) if self.pipes else 0.0
        if self.category == CATEGORY_ENCASED:
            return params.get("包封高 m", 1.0)
        if self.category == CATEGORY_BOX_CULVERT:
            return params.get("净高 m", 2.0) + (params.get("底板厚 mm", 400) + params.get("顶板厚 mm", 300)) / 1000.0
        if self.category == CATEGORY_GALLERY:
            return params.get("外包高 m", 3.2)
        return 0.0

    def spec(self) -> str:
        """规格（旧版 Specification()，清单项目行用）。"""
        if self.category == CATEGORY_STRUCTURE:
            return self.raw_params.get("-名称", "")
        if self.category == 1:
            pipe = self.pipes[0] if self.pipes else None
            return f"{pipe.mat} Dn{format_number(pipe.dn)}" if pipe else ""
        if self.category in (2, 4, 5):
            parts: list[str] = []
            for pipe, content in zip(self.pipes, self.pipe_contents):
                if content == 0:
                    continue
                if content == 1:
                    parts.append(f"D{format_number(pipe.dn)}{pipe.mat}")
                else:
                    parts.append(f"{format_number(content)}×D{format_number(pipe.dn)}{pipe.mat}")
            tail = {2: " 包封", 4: " 顶管", 5: " 牵引管"}[self.category]
            return "+".join(parts) + tail if parts else ""
        if self.category == 3:
            return f"{format_number(self.params.get('净宽 m(含内壁厚度)', 3.5))}×{format_number(self.params.get('净高 m', 2.0))}箱涵"
        if self.category == 6:
            return f"{format_number(self.params.get('外包宽 m', 6.8))}×{format_number(self.params.get('外包高 m', 3.2))}管廊断面"
        return ""


def build_element_input(
    element: Element,
    pe: PcpEnclosure | None,
    pf: PcpFoundation | None,
    pe_refs: list[tuple[PcpEnclosure, float]] | None = None,
    pf_refs: list[tuple[PcpFoundation, float]] | None = None,
) -> ElementInput:
    """从 ORM 构件构造计算输入（深度/数量求值，扩展参数合并默认值）。

    ``pe_refs`` / ``pf_refs`` 为 (原则, 比例) 多原则引用；None 时按单原则处理。
    """
    raw_params = {param.key: param.value for param in element.params}
    params = dict(_DEFAULT_PARAMS.get(element.category, {}))
    for key, text in raw_params.items():
        try:
            params[key] = float(evaluate_or_default(text))
        except Exception:
            params[key] = 0.0
    pipes = [PipeSpec(mat=pipe.mat, dn=pipe.dn) for pipe in element.pipes]
    contents = [evaluate_or_default(pipe.content) for pipe in element.pipes]
    return ElementInput(
        category=element.category,
        name=element.name,
        depth=evaluate_or_default(element.depth),
        amount=evaluate_or_default(element.amount),
        pipes=pipes,
        pipe_contents=contents,
        params=params,
        raw_params=raw_params,
        pe=pe,
        pf=pf,
        pe_refs=[] if pe_refs is None else list(pe_refs),
        pf_refs=[] if pf_refs is None else list(pf_refs),
    )


def build_atlas_query(info: ElementInput, pe: PcpEnclosure) -> AtlasQuery:
    widths, groove_bs = _width_tables(pe)
    return AtlasQuery(
        category=info.category,
        pipes=list(info.pipes),
        con_found=bool(pe.con_found),
        found_angle=int(pe.found_angle),
        groove_width=pe.groove_width,
        size_b=info.size_b,
        widths=widths,
        groove_bs=groove_bs,
    )


def _width_tables(pe: PcpEnclosure) -> tuple[dict[str, dict[int, float]], dict[str, dict[int, float]]]:
    widths: dict[str, dict[int, float]] = {}
    groove_bs: dict[str, dict[int, float]] = {}
    for row in pe.widths:
        table = widths if row.kind == "work" else groove_bs
        table.setdefault(row.pipe_type, {})[int(row.dn)] = row.width
    if not widths:
        widths, groove_bs2 = atlas_service.default_width_tables()
        if not groove_bs:
            groove_bs = groove_bs2
    return widths, groove_bs


def choice_work(pe: PcpEnclosure, depth: float):
    """按沟槽深度选围护做法（旧版 mcPcpEnclosure.ChoiceEcls：最后一个 min_depth ≤ 深度）。

    没有做法满足时退回第一条（旧版 idx 初值 0）；做法列表为空才返回 None。
    """
    works = pe.works_sorted()
    chosen = None
    for work in works:
        if work.min_depth <= depth:
            chosen = work
    if chosen is None and works:
        return works[0]
    return chosen


# --------------------------------------------------------------------------- #
# 构件公式求值（复刻旧版 mcComponent）
# --------------------------------------------------------------------------- #
def load_params(component) -> dict[str, tuple[str, str]]:
    """component_param 行 → {key: (显示名, 表达式)}；value 为旧版 "显示名|表达式"。"""
    params: dict[str, tuple[str, str]] = {}
    for row in component.params:
        display, _, expression = row.value.rpartition("|")
        if not _:
            display, expression = row.value, ""
        params[row.key] = (display, expression)
    return params


def value_exp(params: dict[str, tuple[str, str]], key: str, _trail: tuple[str, ...] = ()) -> str:
    """公式里的参数引用递归代入（旧版 ValueExp/SubstitutingExp，含循环引用检测）。"""
    if key in _trail:
        return _CYCLE
    text = params[key][1]
    for other_key in params:
        pattern = re.compile(r"\b" + re.escape(other_key) + r"\b")
        if pattern.search(text):
            replaced = "(" + value_exp(params, other_key, _trail + (key,)) + ")"
            if _CYCLE in replaced:
                return _CYCLE
            text = pattern.sub(lambda _match, replacement=replaced: replacement, text)
    return text or "0"


def key_exp(params: dict[str, tuple[str, str]], key: str) -> str:
    """定额键显示名：把参数引用替换成参数值（旧版 KeyExp）。"""
    text = params[key][0]
    for other_key, (_, other_value) in params.items():
        text = re.sub(r"\b" + re.escape(other_key) + r"\b", other_value, text)
    return text.replace(" ", "")


def pre_sub(expression: str, height: float, width: float, count: float) -> str:
    """把 height / width / count 代入公式，返回全数字算式（供求值与展示）。"""
    text = expression
    for name, value in (("height", height), ("width", width), ("count", count)):
        text = re.sub(r"\b" + name + r"\b", fmt(value), text)
    return text


def component_quantities(component, height: float, width: float, count: float, cat: str, out: QDict, note: str = "") -> None:
    """构件公式求值（旧版 mcComponent.Q）：cat="F" 工程量公式，"Z" 支撑公式。"""
    if component is None:
        return
    params = load_params(component)
    for key in params:
        if not key.startswith(cat) or len(key) <= 1:
            continue
        substituted = value_exp(params, key)
        if substituted == _CYCLE or substituted == "":
            continue
        numeric = prettify_formula(pre_sub(substituted, height, width, count))
        value = evaluate_or_default(numeric)
        if value != 0:
            out.add(key_exp(params, key), value, numeric, note)


def prettify_formula(expression: str) -> str:
    """公式算式：ROUND→round、^→** 由 evaluator.normalize 处理，这里统一小写函数名。"""
    text = expression
    for name in ("ROUND", "SQRT", "ABS", "POWER"):
        text = re.sub(r"\b" + name + r"\b", name.lower(), text)
    return text


# --------------------------------------------------------------------------- #
# 总入口
# --------------------------------------------------------------------------- #
def cushion_thickness(pe: PcpEnclosure) -> float:
    """垫层厚 mm（旧版 PE.Cush.H）。"""
    return pe.cushions[0].h if pe.cushions else 0.0


def foundation_thickness(pf: PcpFoundation) -> float:
    """换填总厚 mm（旧版 mcPcpFoundation.TiA）。"""
    return sum(replacement.h for replacement in pf.replacements)


def compute_element(info: ElementInput) -> QDict | None:
    """计算一个构件条目的工程量；数量为 0 或原则缺失时返回 None。

    多原则（旧版 mscGroove.Cal）：沟槽断面 + 降水 + 围护(F) + 特殊地基按
    pe×pf 组合逐对计算后乘 (pe 比例 × pf 比例) 求和；支撑(Z)、管道基础、
    管材只用主原则（旧版 mainPEname）计算，不乘比例。
    """
    if info.category == CATEGORY_STRUCTURE:
        return compute_structure(info)
    main_pe = info.pe
    pf_main = info.pf
    if info.amount == 0 or main_pe is None or pf_main is None:
        return None
    pe_refs = info.pe_refs or [(main_pe, 1.0)]
    pf_refs = info.pf_refs or [(pf_main, 1.0)]

    at = resolve_atlas(build_atlas_query(info, main_pe))
    c1 = at.c1 if at.c1 != 0 else cushion_thickness(main_pe)
    at_with_c1 = replace(at, c1=c1)

    per_meter = QDict()
    for pe, pe_ratio in pe_refs:
        for pf, pf_ratio in pf_refs:
            pair = QDict()
            groove_depth = info.depth + groove.mm2m(foundation_thickness(pf) + at.t + c1)
            work = choice_work(pe, groove_depth)
            if work is None:
                return None
            if not groove.cal_groove(pe, work, pf, at_with_c1, info.size_b, info.size_h, groove_depth, pair):
                return None
            precipitation.cal_precipitation(pe, work, pf, at_with_c1, info, groove_depth, pair)
            works_quantities(work, groove_depth, info.amount, "F", at_with_c1, info, pair, "围护")
            special = pf.components[0] if pf.components else None
            if special is not None:
                component_quantities(
                    special, groove_depth, groove.groove_width(at_with_c1, info.size_b), info.amount,
                    "F", pair, "特殊地基",
                )
            pair.scale(pe_ratio * pf_ratio)
            per_meter.extend(pair)

    # 支撑（Z 类公式）：只用主原则、不考虑换填层厚度（旧版 Cal 末尾）
    support_depth = info.depth + groove.mm2m(at.t + c1)
    support_work = choice_work(main_pe, support_depth)
    if support_work is not None:
        works_quantities(support_work, support_depth, info.amount, "Z", at_with_c1, info, per_meter, "支撑")

    # 管道基础（扣弓形占土）+ 管材：主原则
    foundation.cal_found(info, main_pe, at_with_c1, per_meter)
    if info.category == CATEGORY_ENCASED:
        foundation.encased_pipe_deduction(info, per_meter)
    foundation.cal_pipes(info, per_meter)

    per_meter.scale(info.amount)
    return per_meter


def compute_structure(info: ElementInput) -> QDict | None:
    """附属构筑物（旧版 mcE7.getDQ）：不参与沟槽计算。

    * 非“-”开头的参数逐项输出为工程量（键本身即“类别|项目|单位”定额键，
      如 构筑物|垫层|m3），值可以是算式；
    * 同时存在“-井筒 个”与“-井筒 m3/m”时追加井筒方量：
      个数 × max(埋深 − 井高, 0.4) × 每米方量；
    * 全部 × 数量（个数）。
    """
    if info.amount == 0:
        return None
    out = QDict()
    for key, text in info.raw_params.items():
        if not key or key.startswith("-"):
            continue
        value = evaluate_or_default(text)
        out.add(key, value, text or fmt(value), "构筑物")
    cnt_text = info.raw_params.get("-井筒 个", "").strip()
    rate_text = info.raw_params.get("-井筒 m3/m", "").strip()
    if cnt_text and rate_text:
        count = evaluate_or_default(cnt_text)
        rate = evaluate_or_default(rate_text)
        well_h = 0.4  # 旧版 mcE7：默认最小井筒高度
        if "-井高 m" in info.raw_params:
            try:
                well_h = max(info.depth - evaluate(info.raw_params["-井高 m"]), 0.4)
            except EvalError:
                pass
        out.add(
            "构筑物|井筒|m3",
            count * well_h * rate,
            f"{fmt(count)}×{fmt(well_h)}×{fmt(rate)}",
            "井筒",
        )
    out.scale(info.amount)
    return out


def works_quantities(work, depth: float, count: float, cat: str, at, info: ElementInput, out: QDict, note: str) -> None:
    """围护做法各级构件 + 止水构件的公式量（旧版 cal_Ecpnts）。"""
    levels = list(work.levels)
    fixed_h = sum(max(level.h, 0.0) for level in levels)
    fixed_cnt = sum(1 for level in levels if level.h >= 0)
    width = groove.mm2m(info.size_b + at.t * 2 + at.a * 2 + at.workwidth * 2)
    for level in levels:
        if level.h >= 0:
            height = level.h
        elif len(levels) > fixed_cnt:
            height = (depth - fixed_h) / (len(levels) - fixed_cnt)
        else:
            height = depth
        component = level.components[0] if level.components else None
        component_quantities(component, height, width, count, cat, out, note)
    waterstop = work.waterstops[0] if work.waterstops else None
    if waterstop is not None:
        component_quantities(waterstop, depth, width, count, "F", out, "止水")


def replace(at, **changes):
    """复制图集参数并覆盖指定字段（dataclasses.replace 的轻量封装）。"""
    from dataclasses import replace as _replace

    return _replace(at, **changes)


def compute_from_orm(element: Element, session) -> QDict | None:
    """便利入口：从 ORM 构件取原则并计算（含多原则引用与附属构筑物）。"""
    pe, pf, pe_refs, pf_refs = resolve_element_principles(element, session)
    info = build_element_input(element, pe, pf, pe_refs, pf_refs)
    return compute_element(info)


def resolve_element_principles(element: Element, session):
    """按构件的多原则引用解析出 (主 pe, 主 pf, [(pe, 比例)...], [(pf, 比例)...)])。

    引用行缺失时退化为单原则（pe_name/pf_name，比例 1）；主原则取
    main_pe_name（不在引用列表里时取第一条引用）。
    """
    from sqlalchemy import select

    def _by_name(model, name: str):
        if not name:
            return None
        return session.get(model, session.scalar(select(model.id).where(model.name == name)))

    def _refs(kind: str, model, fallback: str):
        rows = element.pe_refs_sorted() if kind == "pe" else element.pf_refs_sorted()
        refs = [(row.name, row.ratio) for row in rows]
        if not refs:
            refs = [(fallback, 1.0)] if fallback else []
        resolved = [( _by_name(model, name), ratio) for name, ratio in refs]
        return [(principle, ratio) for principle, ratio in resolved if principle is not None]

    pe_refs = _refs("pe", PcpEnclosure, element.pe_name if element.pe_name != MULTI_PE_TEXT else "")
    pf_refs = _refs("pf", PcpFoundation, element.pf_name if element.pf_name != MULTI_PF_TEXT else "")
    main_pe = _by_name(PcpEnclosure, element.main_pe_name) if element.main_pe_name else None
    if main_pe is None and pe_refs:
        main_pe = pe_refs[0][0]
    main_pf = pf_refs[0][0] if pf_refs else None
    return main_pe, main_pf, pe_refs, pf_refs


def unit_of(category: int) -> str:
    return "m" if category else ""


def is_concrete_pipe(info: ElementInput) -> bool:
    """是否混凝土管道（旧版 mcE1.IsConPipe）。"""
    mat = info.pipes[0].mat if info.pipes else ""
    return ("混凝土" in mat) or ("砼" in mat)
