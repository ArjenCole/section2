"""计算总入口（复刻旧版 mscGroove.Cal + mcElement.getDQ，计划 §6.1）。

一个构件条目的工程量 = 沟槽断面（挖方/换填/垫层/回填） + 降水 + 围护 + 特殊地基
+ 支撑（Z 类公式） + 管道基础（扣占土） + 管材，全部按“每延米”计算后 ×数量。

构件公式（旧版 mcComponent）求值也在这里：参数引用递归代入 →
height/width/count 代入 → core.evaluator 求值，失败按 0 处理（同旧版 mscExp）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.evaluator import evaluate_or_default, format_number
from app.orm.models import (
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_GALLERY,
    Element,
    PcpEnclosure,
    PcpFoundation,
)
from app.services import atlas as atlas_service
from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas
from app.services.calc import foundation, groove, precipitation
from app.services.calc.tracer import QDict, fmt

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


@dataclass
class ElementInput:
    """参与计算的构件快照（深度/数量已求值，参数已合并默认值）。"""

    category: int
    name: str = ""
    depth: float = 0.0
    amount: float = 0.0
    pipes: list[PipeSpec] = field(default_factory=list)
    pipe_contents: list[float] = field(default_factory=list)
    params: dict[str, float] = field(default_factory=dict)
    pe: PcpEnclosure | None = None
    pf: PcpFoundation | None = None

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


def build_element_input(element: Element, pe: PcpEnclosure | None, pf: PcpFoundation | None) -> ElementInput:
    """从 ORM 构件构造计算输入（深度/数量求值，扩展参数合并默认值）。"""
    params = dict(_DEFAULT_PARAMS.get(element.category, {}))
    for param in element.params:
        try:
            params[param.key] = float(evaluate_or_default(param.value))
        except Exception:
            params[param.key] = 0.0
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
        pe=pe,
        pf=pf,
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
    """按沟槽深度选围护做法（旧版 mcPcpEnclosure.ChoiceEcls：最后一个 min_depth ≤ 深度）。"""
    chosen = None
    for work in pe.works_sorted():
        if work.min_depth <= depth:
            chosen = work
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
    """计算一个构件条目的工程量；数量为 0 或原则缺失时返回 None。"""
    pe = info.pe
    pf = info.pf
    if info.amount == 0 or pe is None or pf is None:
        return None

    at = resolve_atlas(build_atlas_query(info, pe))
    c1 = at.c1 if at.c1 != 0 else cushion_thickness(pe)
    at_with_c1 = replace(at, c1=c1)

    per_meter = QDict()
    groove_depth = info.depth + groove.mm2m(foundation_thickness(pf) + at.t + c1)
    work = choice_work(pe, groove_depth)
    if work is None:
        return None
    if not groove.cal_groove(pe, work, pf, at_with_c1, info.size_b, info.size_h, groove_depth, per_meter):
        return None
    precipitation.cal_precipitation(pe, work, pf, at_with_c1, info, groove_depth, per_meter)
    works_quantities(work, groove_depth, info.amount, "F", at_with_c1, info, per_meter, "围护")
    special = pf.components[0] if pf.components else None
    if special is not None:
        component_quantities(
            special, groove_depth, groove.groove_width(at_with_c1, info.size_b), info.amount,
            "F", per_meter, "特殊地基",
        )

    # 支撑（Z 类公式）：不考虑换填层厚度（旧版 Cal 末尾）
    support_depth = info.depth + groove.mm2m(at.t + c1)
    support_work = choice_work(pe, support_depth)
    if support_work is not None:
        works_quantities(support_work, support_depth, info.amount, "Z", at_with_c1, info, per_meter, "支撑")

    # 管道基础（扣弓形占土）+ 管材
    foundation.cal_found(info, pe, at_with_c1, per_meter)
    if info.category == CATEGORY_ENCASED:
        foundation.encased_pipe_deduction(info, per_meter)
    foundation.cal_pipes(info, per_meter)

    per_meter.scale(info.amount)
    return per_meter


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
    """便利入口：从 ORM 构件取原则并计算。"""
    pe = session.get(PcpEnclosure, _id_by_name(session, PcpEnclosure, element.pe_name)) if element.pe_name else None
    pf = session.get(PcpFoundation, _id_by_name(session, PcpFoundation, element.pf_name)) if element.pf_name else None
    info = build_element_input(element, pe, pf)
    return compute_element(info)


def _id_by_name(session, model, name: str) -> int | None:
    from sqlalchemy import select

    return session.scalar(select(model.id).where(model.name == name))


def unit_of(category: int) -> str:
    return "m" if category else ""


def is_concrete_pipe(info: ElementInput) -> bool:
    """是否混凝土管道（旧版 mcE1.IsConPipe）。"""
    mat = info.pipes[0].mat if info.pipes else ""
    return ("混凝土" in mat) or ("砼" in mat)
