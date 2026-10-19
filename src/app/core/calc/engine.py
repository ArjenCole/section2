"""计算总入口（复刻旧版 mscGroove.Cal + mcElement.getDQ）。

一个构件条目的工程量 = 沟槽断面（挖方/换填/垫层/回填） + 降水 + 围护 + 特殊地基
+ 支撑（Z 类公式） + 管道基础（扣占土） + 管材，全部按“每延米”计算后 ×数量。

例外（同旧版）：附属构筑物（mcE7）只算自己的工程量行（见 compute_structure）；
顶管 / 牵引管（mcE4 / mcE5）不开槽，只有管材（见 compute_trenchless）。

构件公式（旧版 mcComponent）求值也在这里：参数引用递归代入 →
height/width/count 代入 → core.evaluator 求值，失败按 0 处理（同旧版 mscExp）。

埋深 / 数量 / 构件参数的录入原文以 :class:`Dim`（数值 + 算式）参与计算：
算式不做预运算，派生量（断面宽 = 管径/1000、图集外径 = 径+2×壁厚、
槽底宽 = 断面宽+2×(壁厚+工作面加宽+工作面)、毫米→米换算…）在输出表达式里
都写全来源，见 :mod:`app.core.calc.tracer` 与 :mod:`app.core.calc.measures`。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.evaluator import EvalError, evaluate, evaluate_or_default, format_number
from app.core.models.models import (
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_GALLERY,
    CATEGORY_JACKING,
    CATEGORY_PULLING,
    CATEGORY_STRUCTURE,
    GROOVE_WIDTH_WORK,
    MULTI_PE_TEXT,
    MULTI_PF_TEXT,
    Element,
    PcpEnclosure,
    PcpFoundation,
    PcpPrecipitation,
    PcpWidth,
)
from app.core.param_naming import (
    PARAM_A_NAME,
    PARAM_C1_NAME,
    PARAM_C2_NAME,
    is_atlas_param,
    is_atlas_param_name,
    supports_atlas_param,
)
from app.core.calc.measures import (
    AtlasDims,
    cushion_thickness as cushion_dim,
    foundation_thickness as foundation_dim,
    groove_b_width,
)
from app.services import atlas as atlas_service
from app.services.atlas import C2_ZERO_CATEGORIES, AtlasParam, AtlasQuery, PipeSpec, resolve_atlas
from app.core.calc import foundation, groove, precipitation
from app.core.calc.tracer import Dim, QDict, dim, dim_sum, fmt, raw_dim, scale_sum, wrap

_CYCLE = "参数循环引用"

#: 各类别构件的默认扩展参数（旧版 mcE2/mcE3/mcE6 构造函数；键不带单位，v5 起拆列）
_DEFAULT_PARAMS: dict[int, dict[str, float]] = {
    CATEGORY_ENCASED: {"包封宽": 1.5, "包封高": 1.0},
    CATEGORY_BOX_CULVERT: {
        "净宽(含内壁厚度)": 3.5,
        "净高": 2.0,
        "底板厚": 400,
        "顶板厚": 300,
        "外壁厚": 350,
        "内壁": 0,
        "内壁厚": 250,
        "含钢量": 150,
    },
    CATEGORY_GALLERY: {
        "外包宽": 6.8,
        "外包高": 3.2,
        "底板厚": 400,
        "顶板厚": 300,
        "外壁厚": 350,
        "内壁": 0,
        "内壁厚": 250,
        "含钢量": 160,
    },
}


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
    #: 埋深 / 数量的录入原文（可求值时以算式进输出表达式）
    depth_text: str = ""
    amount_text: str = ""
    pipes: list[PipeSpec] = field(default_factory=list)
    pipe_contents: list[float] = field(default_factory=list)
    #: 管道含量原文（可写算式）的算式伴随
    pipe_content_dims: list[Dim] = field(default_factory=list)
    params: dict[str, float] = field(default_factory=dict)
    #: 构件参数原文的算式伴随（与 ``params`` 同键；录入算式时原文进输出表达式）
    param_dims: dict[str, Dim] = field(default_factory=dict)
    #: 构件参数 (参数名, 单位) → 原文：构筑物“名称/单位”行、井筒参数等
    #: 非数值内容按原文查询（旧版“-名称”等键已拆成名称+单位两列）
    named_params: dict[tuple[str, str], str] = field(default_factory=dict)
    #: 附属构筑物工程量行 (类别, 项目, 单位, 值原文)，值可写算式
    struct_quantities: list[tuple[str, str, str, str]] = field(default_factory=list)
    pe: PcpEnclosure | None = None
    pf: PcpFoundation | None = None
    #: 降水 / 面宽原则（旧版挂在 PE 下，v4 起独立引用）
    pp: PcpPrecipitation | None = None
    pw: PcpWidth | None = None
    pe_refs: list[tuple[PcpEnclosure, float]] = field(default_factory=list)
    pf_refs: list[tuple[PcpFoundation, float]] = field(default_factory=list)

    @property
    def depth_dim(self) -> Dim:
        """埋深 m（算式为录入原文，如 ``2.5+0.3``）。"""
        return raw_dim(self.depth_text, self.depth)

    @property
    def amount_dim(self) -> Dim:
        """数量 / 长度（算式为录入原文）。"""
        return raw_dim(self.amount_text, self.amount)

    def param_dim(self, key: str, default: float) -> Dim:
        """构件参数的算式伴随：录入原文可求值时用原文，否则用数值 / 默认值。"""
        found = self.param_dims.get(key)
        return found if found is not None else dim(self.params.get(key, default))

    @property
    def size_b_dim(self) -> Dim:
        """断面宽 m 的算式伴随（直埋 = 管径/1000，箱涵 = 净宽 + 2×外壁厚/1000）。"""
        if self.category in (CATEGORY_BURIED, CATEGORY_JACKING, CATEGORY_PULLING):
            return dim(self.pipes[0].dn) / 1000 if self.pipes else dim(0.0)
        if self.category == CATEGORY_ENCASED:
            return self.param_dim("包封宽", 1.5)
        if self.category == CATEGORY_BOX_CULVERT:
            return self.param_dim("净宽(含内壁厚度)", 3.5) + self.param_dim("外壁厚", 350) * 2 / 1000
        if self.category == CATEGORY_GALLERY:
            return self.param_dim("外包宽", 6.8)
        return dim(0.0)

    @property
    def size_b(self) -> float:
        """断面宽 m（旧版 rtSizeB）。"""
        return self.size_b_dim.v

    @property
    def size_h_dim(self) -> Dim:
        """断面高 m 的算式伴随（箱涵 = 净高 + (底板厚+顶板厚)/1000）。"""
        if self.category in (CATEGORY_BURIED, CATEGORY_JACKING, CATEGORY_PULLING):
            return dim(self.pipes[0].dn) / 1000 if self.pipes else dim(0.0)
        if self.category == CATEGORY_ENCASED:
            return self.param_dim("包封高", 1.0)
        if self.category == CATEGORY_BOX_CULVERT:
            return self.param_dim("净高", 2.0) + (
                self.param_dim("底板厚", 400) + self.param_dim("顶板厚", 300)
            ) / 1000
        if self.category == CATEGORY_GALLERY:
            return self.param_dim("外包高", 3.2)
        return dim(0.0)

    @property
    def size_h(self) -> float:
        """断面高 m（旧版 rtSizeH）。"""
        return self.size_h_dim.v

    def spec(self) -> str:
        """规格（旧版 Specification()，清单项目行用）。"""
        if self.category == CATEGORY_STRUCTURE:
            return self.named_params.get(("名称", ""), "")
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
            return f"{format_number(self.params.get('净宽(含内壁厚度)', 3.5))}×{format_number(self.params.get('净高', 2.0))}箱涵"
        if self.category == 6:
            return f"{format_number(self.params.get('外包宽', 6.8))}×{format_number(self.params.get('外包高', 3.2))}管廊断面"
        return ""


def _usable_text(text: str) -> str:
    """录入原文可求值才带回算式；求值失败的格子仍按 0 计算，算式退回纯数值。"""
    try:
        evaluate(text or "")
    except EvalError:
        return ""
    return str(text or "").strip()


def build_element_input(
    element: Element,
    pe: PcpEnclosure | None,
    pf: PcpFoundation | None,
    pe_refs: list[tuple[PcpEnclosure, float]] | None = None,
    pf_refs: list[tuple[PcpFoundation, float]] | None = None,
    pp: PcpPrecipitation | None = None,
    pw: PcpWidth | None = None,
) -> ElementInput:
    """从 ORM 构件构造计算输入（深度/数量求值，扩展参数合并默认值）。

    ``pe_refs`` / ``pf_refs`` 为 (原则, 比例) 多原则引用；None 时按单原则处理。
    ``pp`` / ``pw`` 为降水 / 面宽原则（None 时不参与降水与图集宽度查询）。
    """
    named_params = {(param.key, param.unit or ""): param.value for param in element.params}
    params = dict(_DEFAULT_PARAMS.get(element.category, {}))
    #: 参数原文的算式伴随：可求值才带回原文（求值失败的格子按 0 计算）
    param_dims: dict[str, Dim] = {}
    for (key, unit), text in named_params.items():
        stripped = (text or "").strip()
        if is_atlas_param_name(key):
            # 工作面加宽 / 垫层厚 / 基础厚：只有该类别显示的图集行（名称 + mm）
            # 才是用户覆盖值——空值 = 自动按图集，显式数字 = 覆盖（直埋三行、
            # 包封 / 箱涵 / 管廊的工作面加宽与垫层厚；见 param_naming）。
            # 其余（包封 / 箱涵 / 管廊的基础厚、顶管 / 牵引管的全部三行）一律
            # 不参与计算，同名其它单位（如“工作面加宽 cm”）的行也只是普通
            # 参数行，同样不参与图集取值
            if (
                not is_atlas_param(key, unit)
                or not supports_atlas_param(element.category, key, unit)
                or not stripped
            ):
                continue
        try:
            params[key] = float(evaluate_or_default(text))
        except Exception:
            params[key] = 0.0
        param_dims[key] = raw_dim(_usable_text(text), params[key])
    pipes = [PipeSpec(mat=pipe.mat, dn=pipe.dn, t=pipe.t) for pipe in element.pipes]
    contents = [evaluate_or_default(pipe.content) for pipe in element.pipes]
    quantities = [
        (quantity.category, quantity.item, quantity.unit, quantity.value)
        for quantity in element.quantities
    ]
    return ElementInput(
        category=element.category,
        name=element.name,
        depth=evaluate_or_default(element.depth),
        amount=evaluate_or_default(element.amount),
        depth_text=_usable_text(element.depth),
        amount_text=_usable_text(element.amount),
        pipes=pipes,
        pipe_contents=contents,
        pipe_content_dims=[
            raw_dim(_usable_text(pipe.content), content)
            for pipe, content in zip(element.pipes, contents)
        ],
        params=params,
        param_dims=param_dims,
        named_params=named_params,
        struct_quantities=quantities,
        pe=pe,
        pf=pf,
        pp=pp,
        pw=pw,
        pe_refs=[] if pe_refs is None else list(pe_refs),
        pf_refs=[] if pf_refs is None else list(pf_refs),
    )


def build_atlas_query(info: ElementInput, pe: PcpEnclosure, pw: PcpWidth | None = None) -> AtlasQuery:
    """图集查询：基础/角度取围护原则，宽度表与槽宽取值方式取面宽原则。

    详情面板的参数行（工作面加宽 / 垫层厚 / 基础厚，param_naming 常量）为
    空值时不设覆盖（自动按图集），写了数字时按用户值覆盖图集行；不显示的
    行已被 :func:`build_element_input` 滤掉，这里传不传都由类别规则决定
    （见 param_naming.ATLAS_PARAM_CATEGORIES）。
    """
    widths, groove_bs = _width_tables(pw)
    params = info.params

    def _override(key: str) -> float | None:
        value = params.get(key)
        return value if value is not None else None

    return AtlasQuery(
        category=info.category,
        pipes=list(info.pipes),
        con_found=bool(pe.con_found),
        found_angle=int(pe.found_angle),
        groove_width=pw.groove_width if pw is not None else GROOVE_WIDTH_WORK,
        size_b=info.size_b,
        widths=widths,
        groove_bs=groove_bs,
        a=_override(PARAM_A_NAME),
        c1=_override(PARAM_C1_NAME),
        c2=_override(PARAM_C2_NAME),
    )


def _width_tables(pw: PcpWidth | None) -> tuple[dict[str, dict[int, float]], dict[str, dict[int, float]]]:
    widths: dict[str, dict[int, float]] = {}
    groove_bs: dict[str, dict[int, float]] = {}
    for row in pw.items if pw is not None else ():
        table = widths if row.kind == "work" else groove_bs
        table.setdefault(row.pipe_type, {})[int(row.dn)] = row.width
    if not widths:
        widths, groove_bs2 = atlas_service.default_width_tables()
        if not groove_bs:
            groove_bs = groove_bs2
    return widths, groove_bs


def atlas_dims(info: ElementInput, at: AtlasParam) -> AtlasDims:
    """图集参数的算式伴随：覆盖值取参数行原文，查表值以原始表值进算式。

    覆盖判定与 :func:`app.services.atlas._apply_overrides` 一致：工作面加宽 /
    垫层厚 / 基础厚按详情面板参数行（:func:`build_element_input` 已按类别滤过，
    键存在即覆盖），壁厚按管材行的用户值（包封 / 箱涵 / 管廊的断面宽由自身
    参数决定，不认管道壁厚）。图集无 oD 列时外径按 ``管径+2×壁厚`` 推出，
    算式里保留这个推导。
    """
    def _override(name: str) -> Dim | None:
        return info.param_dims.get(name) if name in info.params else None

    a = _override(PARAM_A_NAME) or dim(at.a)
    c1 = _override(PARAM_C1_NAME) or dim(at.c1)
    c2 = _override(PARAM_C2_NAME) or dim(at.c2)
    dn = dim(info.pipes[0].dn) if info.pipes else dim(0.0)
    wall = info.pipes[0].t if info.pipes else None
    if wall is not None and info.category not in C2_ZERO_CATEGORIES:
        t = dim(wall)
        od = dn + t * 2
    else:
        t = dim(at.t)
        od = dim(at.od) if at.od > 0 else dn + t * 2
    return AtlasDims(
        od=od,
        t=t,
        a=a,
        c1=c1,
        c2=c2,
        workwidth=dim(at.workwidth),
        groove_b=groove_b_width(at.groove_b),
    )


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


def pre_sub(expression: str, height: Dim, width: Dim, count: Dim) -> str:
    """把 height / width / count 代入公式；埋深/数量为算式时原文随代入进算式。

    代入位置在公式里（接什么运算符未知），算式按最严格方式加括号（tight）。
    """
    text = expression
    for name, value in (("height", height), ("width", width), ("count", count)):
        text = re.sub(r"\b" + name + r"\b", lambda _match, replacement=wrap(value.e, tight=True): replacement, text)
    return text


def component_quantities(component, height: Dim, width: Dim, count: Dim, cat: str, out: QDict, note: str = "") -> None:
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
    """垫层厚 mm（旧版 PE.Cush.H）；算式伴随见 measures.cushion_thickness。"""
    return cushion_dim(pe).v


def foundation_thickness(pf: PcpFoundation) -> float:
    """换填总厚 mm（旧版 mcPcpFoundation.TiA）；算式伴随见 measures.foundation_thickness。"""
    return foundation_dim(pf).v


def compute_element(info: ElementInput) -> QDict | None:
    """计算一个构件条目的工程量；数量为 0 或原则缺失时返回 None。

    顶管 / 牵引管不开槽，只有管材（见 :func:`compute_trenchless`）；
    多原则（旧版 mscGroove.Cal）：沟槽断面 + 降水 + 围护(F) + 特殊地基按
    pe×pf 组合逐对计算后乘 (pe 比例 × pf 比例) 求和；支撑(Z)、管道基础、
    管材只用主原则（旧版 mainPEname）计算，不乘比例。
    """
    if info.category == CATEGORY_STRUCTURE:
        return compute_structure(info)
    if info.category in (CATEGORY_JACKING, CATEGORY_PULLING):
        return compute_trenchless(info)
    main_pe = info.pe
    pf_main = info.pf
    if info.amount == 0 or main_pe is None or pf_main is None or info.pp is None or info.pw is None:
        return None
    pe_refs = info.pe_refs or [(main_pe, 1.0)]
    pf_refs = info.pf_refs or [(pf_main, 1.0)]
    depth_dim = info.depth_dim
    amount_dim = info.amount_dim

    at = resolve_atlas(build_atlas_query(info, main_pe, info.pw))
    ad = atlas_dims(info, at)
    if ad.c1.v == 0:
        # 垫层厚 0（砂基础无垫层）：旧版语义——垫层取围护原则的垫层表值
        ad = ad.replace(c1=cushion_dim(main_pe))

    per_meter = QDict()
    for pe, pe_ratio in pe_refs:
        for pf, pf_ratio in pf_refs:
            pair = QDict()
            groove_depth = depth_dim + (foundation_dim(pf) + ad.t + ad.c1) / 1000
            work = choice_work(pe, groove_depth.v)
            if work is None:
                return None
            if not groove.cal_groove(pe, work, pf, ad, info.size_b_dim, info.size_h_dim, groove_depth, pair):
                return None
            precipitation.cal_precipitation(info.pp, pe, work, pf, ad, info, groove_depth, pair)
            works_quantities(work, groove_depth, amount_dim, "F", ad, info, pair, "围护")
            special = pf.components[0] if pf.components else None
            if special is not None:
                component_quantities(
                    special,
                    groove_depth,
                    groove.groove_width(ad, info.size_b_dim),
                    amount_dim,
                    "F",
                    pair,
                    "特殊地基",
                )
            pair.scale(pe_ratio * pf_ratio)
            per_meter.extend(pair)

    # 支撑（Z 类公式）：只用主原则、不考虑换填层厚度（旧版 Cal 末尾）
    support_depth = depth_dim + (ad.t + ad.c1) / 1000
    support_work = choice_work(main_pe, support_depth.v)
    if support_work is not None:
        works_quantities(support_work, support_depth, amount_dim, "Z", ad, info, per_meter, "支撑")

    # 管道基础（扣弓形占土）+ 管材：主原则
    foundation.cal_found(info, main_pe, ad, per_meter)
    if info.category == CATEGORY_ENCASED:
        foundation.encased_pipe_deduction(info, per_meter)
    foundation.cal_pipes(info, per_meter)

    per_meter.scale(info.amount, expr=amount_dim.e)
    return per_meter


def compute_trenchless(info: ElementInput) -> QDict | None:
    """顶管 / 牵引管（旧版 mcE4.getDQ / mcE5.getDQ）：只算管材。

    顶管（键前缀“顶管”）与牵引管（键前缀“拖拉管”）都是非开挖施工，不开槽
    也就没有开挖 / 换填 / 垫层 / 回填 / 降水 / 围护 / 支撑 / 管道基础——1.0 的
    这两个构件只输出 ``管材含量 × 数量``，也不看围护 / 地基 / 降水 / 面宽原则。
    数量为 0 或没录入管材时返回 None（没有可输出的量）。
    """
    if info.amount == 0:
        return None
    amount_dim = info.amount_dim
    out = QDict()
    foundation.cal_pipes(info, out, "顶管" if info.category == CATEGORY_JACKING else "拖拉管")
    if not out:
        return None  # 没录入管材：没有可输出的量
    out.scale(info.amount, expr=amount_dim.e)
    return out


def compute_structure(info: ElementInput) -> QDict | None:
    """附属构筑物（旧版 mcE7.getDQ）：不参与沟槽计算。

    * 工程量行（详情面板“工程量”页，旧版“类别|项目|单位”三段参数）逐行输出，
      值可以是算式；
    * 名称 / 单位 / 井筒等为参数行，只参与规格与井筒增量计算，不单独输出；
    * 同时存在 (井筒, 个) 与 (井筒, m3/m) 参数时追加井筒方量：
      个数 × max(埋深 − 井高, 0.4) × 每米方量；
    * 全部 × 数量（个数）。
    """
    if info.amount == 0:
        return None
    amount_dim = info.amount_dim
    out = QDict()
    for category, item, unit, text in info.struct_quantities:
        key = "|".join((category, item, unit))
        if not item and not unit:
            continue
        value = evaluate_or_default(text)
        out.add(key, value, _usable_text(text) or fmt(value), "构筑物")
    cnt_text = info.named_params.get(("井筒", "个"), "").strip()
    rate_text = info.named_params.get(("井筒", "m3/m"), "").strip()
    if cnt_text and rate_text:
        count = raw_dim(cnt_text, evaluate_or_default(cnt_text))
        rate = raw_dim(rate_text, evaluate_or_default(rate_text))
        well_h = dim(0.4)  # 旧版 mcE7：默认最小井筒高度
        jh_text = info.named_params.get(("井高", "m"), "").strip()
        if jh_text:
            try:
                jh = evaluate(jh_text)
                if info.depth - jh > 0.4:
                    well_h = info.depth_dim - raw_dim(jh_text, jh)
            except EvalError:
                pass
        out.add(
            "构筑物|井筒|m3",
            count.v * well_h.v * rate.v,
            f"{wrap(count.e)}×{wrap(well_h.e)}×{wrap(rate.e)}",
            "井筒",
        )
    out.scale(info.amount, expr=amount_dim.e)
    return out


def works_quantities(work, depth: Dim, count: Dim, cat: str, ad: AtlasDims, info: ElementInput, out: QDict, note: str) -> None:
    """围护做法各级构件 + 止水构件的公式量（旧版 cal_Ecpnts）。

    代入公式的 ``width`` 与旧版一致：``(断面宽 + 2×(壁厚+工作面加宽+工作面))/1000``
    ——旧版把断面宽（m）与图集 mm 值加在一起再 /1000，算式照写以便复核。
    """
    levels = list(work.levels)
    fixed_h = dim_sum(*(dim(level.h) for level in levels if level.h >= 0))
    fixed_cnt = sum(1 for level in levels if level.h >= 0)
    width = (info.size_b_dim + scale_sum((ad.t, ad.a, ad.workwidth), 2.0)) / 1000
    for level in levels:
        if level.h >= 0:
            height = dim(level.h)
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


def resolve_element_principles(element: Element, session):
    """按构件的引用解析出 (主 pe, 主 pf, pp, pw, [(pe, 比例)...], [(pf, 比例)...])。

    引用行缺失时退化为单原则（pe_name/pf_name，比例 1）；主原则取
    main_pe_name（不在引用列表里时取第一条引用）。降水/面宽原则按名字
    解析，名字失效（如多围护原则迁出的行）时取库中第一条。
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

    def _first(model):
        return session.scalar(select(model).order_by(model.order_no, model.id))

    pe_refs = _refs("pe", PcpEnclosure, element.pe_name if element.pe_name != MULTI_PE_TEXT else "")
    pf_refs = _refs("pf", PcpFoundation, element.pf_name if element.pf_name != MULTI_PF_TEXT else "")
    main_pe = _by_name(PcpEnclosure, element.main_pe_name) if element.main_pe_name else None
    if main_pe is None and pe_refs:
        main_pe = pe_refs[0][0]
    main_pf = pf_refs[0][0] if pf_refs else None
    pp = _by_name(PcpPrecipitation, element.pp_name) or _first(PcpPrecipitation)
    pw = _by_name(PcpWidth, element.pw_name) or _first(PcpWidth)
    return main_pe, main_pf, pp, pw, pe_refs, pf_refs


def is_concrete_pipe(info: ElementInput) -> bool:
    """是否混凝土管道（旧版 mcE1.IsConPipe）。"""
    mat = info.pipes[0].mat if info.pipes else ""
    return ("混凝土" in mat) or ("砼" in mat)
