"""计算总入口（复刻旧版 mscGroove.Cal + mcElement.getDQ）。

一个构件条目的工程量 = 沟槽断面（挖方/换填/垫层/回填） + 降水 + 围护/支撑公式
+ 特殊地基 + 管道基础（扣占土） + 管材，全部按“每延米”计算后 ×数量。

构件公式统一以 F 开头（FA~FZ）：围护、支撑只是公式显示名的类别
（``围护|…`` / ``支撑|…``），计算时一次全部代入，不再按键前缀区分。

例外（同旧版）：附属构筑物（mcE7）只算自己的工程量行（见 compute_structure）；
顶管 / 牵引管（mcE4 / mcE5）不开槽，只有管材（见 compute_trenchless）。

构件公式（旧版 mcComponent）求值也在这里：参数引用递归代入 →
height/width/count 代入 → core.evaluator 求值，失败按 0 处理（同旧版 mscExp）。

埋深 / 数量 / 构件参数的录入原文以 :class:`Dim`（数值 + 算式）参与计算：
算式不做预运算，派生量（断面宽 = 管径、图集外径 = 径+2×壁厚、槽底宽 =
断面宽+2×(壁厚+工作面加宽+工作面)、埋深的 mm 换算…）在输出表达式里
都写全来源。**记法口径**：几何链全程 mm 记算式（:func:`mm` 家族，``Dim.s=3``），
每延米面积/体积式记录时统一追加 ``/10^6``（体积）、``/10^3``（面积）；用户公式
（原则 / 库模板按 m 口径编写）的代入量用 :meth:`Dim.to_m` 派生 m 记法视图，
公式行仍输出 m 制算式，见 :mod:`app.core.calc.tracer` 与 :mod:`app.core.calc.measures`。
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
    LR_PE_TEXT,
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
from app.core.calc.tracer import (
    Dim,
    QDict,
    dim,
    dim_sum,
    fmt,
    mm,
    mm_dim,
    mm_of_m,
    needs_parens,
    needs_parens_tight,
    raw_dim,
    wrap,
)

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

    沟槽断面 / 降水 / 围护 / 特殊地基按构件引用的单条 ``pe`` × ``pf`` 计算；
    回填材质命名、支撑、管道基础同样用 ``pe``（1.0 多原则条目迁移时已按
    比例拆成独立条目，见 services/stn_migration）。
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
    #: 左右分设（v3）：左右两条围护原则；None = 普通单原则模式。
    #: 图集查询与包封扣管位等内部消费者读 ``pf``（v10 起管道基础属地基原则）
    pe_left: PcpEnclosure | None = None
    pe_right: PcpEnclosure | None = None
    support_left: bool = True
    support_right: bool = True

    @property
    def depth_dim(self) -> Dim:
        """埋深 m（算式为录入原文，如 ``2.5+0.3``）。"""
        return raw_dim(self.depth_text, self.depth).named("埋深", "构件埋深")

    @property
    def amount_dim(self) -> Dim:
        """数量 / 长度（算式为录入原文）。"""
        return raw_dim(self.amount_text, self.amount).named("数量", "构件数量")

    def param_dim(self, key: str, default: float) -> Dim:
        """构件参数的算式伴随：录入原文可求值时用原文，否则用数值 / 默认值。"""
        found = self.param_dims.get(key)
        return (found if found is not None else dim(self.params.get(key, default))).named(
            key, "构件参数"
        )

    @property
    def size_b_dim(self) -> Dim:
        """断面宽的 mm 记法算式伴随（直埋 = 管径，箱涵 = 净宽 + 2×外壁厚）。

        几何链（槽底宽、梯形断面）直接用本属性；围护等用户公式按 m 口径
        代入，用 :meth:`Dim.to_m` 派生 m 记法视图。
        """
        if self.category in (CATEGORY_BURIED, CATEGORY_JACKING, CATEGORY_PULLING):
            return (
                mm(self.pipes[0].dn).named("断面宽", "管径")
                if self.pipes
                else mm(0.0)
            )
        if self.category == CATEGORY_ENCASED:
            return mm_of_m(self.param_dim("包封宽", 1.5)).named(
                "断面宽", "构件参数·包封宽"
            )
        if self.category == CATEGORY_BOX_CULVERT:
            return (
                mm_of_m(self.param_dim("净宽(含内壁厚度)", 3.5))
                + mm_dim(self.param_dim("外壁厚", 350)) * 2
            ).named("断面宽", "净宽 + 2×外壁厚")
        if self.category == CATEGORY_GALLERY:
            return mm_of_m(self.param_dim("外包宽", 6.8)).named(
                "断面宽", "构件参数·外包宽"
            )
        return mm(0.0)

    @property
    def size_b(self) -> float:
        """断面宽 m（旧版 rtSizeB）。"""
        return self.size_b_dim.v

    @property
    def size_h_dim(self) -> Dim:
        """断面高的 mm 记法算式伴随（箱涵 = 净高 + 底板厚 + 顶板厚）。"""
        if self.category in (CATEGORY_BURIED, CATEGORY_JACKING, CATEGORY_PULLING):
            return (
                mm(self.pipes[0].dn).named("断面高", "管径")
                if self.pipes
                else mm(0.0)
            )
        if self.category == CATEGORY_ENCASED:
            return mm_of_m(self.param_dim("包封高", 1.0)).named(
                "断面高", "构件参数·包封高"
            )
        if self.category == CATEGORY_BOX_CULVERT:
            return (
                mm_of_m(self.param_dim("净高", 2.0))
                + mm_dim(self.param_dim("底板厚", 400))
                + mm_dim(self.param_dim("顶板厚", 300))
            ).named("断面高", "净高 + 底板厚 + 顶板厚")
        if self.category == CATEGORY_GALLERY:
            return mm_of_m(self.param_dim("外包高", 3.2)).named(
                "断面高", "构件参数·外包高"
            )
        return mm(0.0)

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


def _resolve_lr_enclosures(element: Element) -> tuple[PcpEnclosure | None, PcpEnclosure | None]:
    """左右分设构件的 (左 PE, 右 PE)：按名解析，引用失效回退库中第一条。"""
    from app.core.models import base as orm

    if not orm.is_open():
        return None, None
    session = orm.session()

    def _by_name(name: str | None):
        return lookup_principle(session, PcpEnclosure, name)

    def _first():
        return first_principle(session, PcpEnclosure)

    pe_left = _by_name(element.pe_left_name) or _first()
    pe_right = _by_name(element.pe_right_name) or _first()
    return pe_left, pe_right


def build_element_input(
    element: Element,
    pe: PcpEnclosure | None,
    pf: PcpFoundation | None,
    pp: PcpPrecipitation | None = None,
    pw: PcpWidth | None = None,
) -> ElementInput:
    """从 ORM 构件构造计算输入（深度/数量求值，扩展参数合并默认值）。

    ``pp`` / ``pw`` 为挖填降水 / 面宽原则（None 时不参与降水与图集宽度查询）。

    构件为左右分设模式（``pe_name == LR_PE_TEXT``）时自动解析左右两条围护
    原则（引用失效回退库中第一条，与界面一致）；``pe`` 即左侧原则（v10 起
    管道基础已迁到 ``pf``，不再需要按侧选取）。
    """
    named_params = {(param.key, param.unit or ""): param.value for param in element.params}
    params = dict(_DEFAULT_PARAMS.get(element.category, {}))
    pe_left = pe_right = None
    support_left = support_right = True
    if element.pe_name == LR_PE_TEXT:
        pe_left, pe_right = _resolve_lr_enclosures(element)
        support_left = bool(element.support_left)
        support_right = bool(element.support_right)
        # 主 pe（围护做法取左侧；管道基础 v10 起由 pf 提供）
        pe = pe_left
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
    pipes = [
        PipeSpec(mat=pipe.mat, dn=pipe.dn, t=pipe.t, cat=pipe.pipe_category)
        for pipe in element.pipes
    ]
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
            raw_dim(_usable_text(pipe.content), content).named(
                "管材含量", f"{pipe.mat} Dn{pipe.dn} 含量"
            )
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
        pe_left=pe_left,
        pe_right=pe_right,
        support_left=support_left,
        support_right=support_right,
    )


def build_atlas_query(info: ElementInput, pf: PcpFoundation, pw: PcpWidth | None = None) -> AtlasQuery:
    """图集查询：基础/角度取地基原则（v10 起），宽度表与槽宽取值方式取面宽原则。

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
        con_found=bool(pf.con_found),
        found_angle=int(pf.found_angle),
        groove_width=pw.groove_width if pw is not None else GROOVE_WIDTH_WORK,
        size_b=info.size_b,
        widths=widths,
        groove_bs=groove_bs,
        a=_override(PARAM_A_NAME),
        c1=_override(PARAM_C1_NAME),
        c2=_override(PARAM_C2_NAME),
    )


def _width_tables(pw: PcpWidth | None) -> tuple[dict[str, dict[int, float]], dict[str, dict[int, float]]]:
    """面宽原则 → 两张查找表；同一 session 内缓存，避免每次查图集都遍历 ORM 行。"""
    from sqlalchemy.orm import object_session

    session = object_session(pw) if pw is not None else None
    cache = session.info.setdefault("section2_width_tables", {}) if session is not None else {}
    cache_key = (pw.id if pw is not None else None,)
    if cache_key in cache:
        return cache[cache_key]

    widths: dict[str, dict[int, float]] = {}
    groove_bs: dict[str, dict[int, float]] = {}
    for row in pw.items if pw is not None else ():
        table = widths if row.kind == "work" else groove_bs
        table.setdefault(row.pipe_type, {})[int(row.dn)] = row.width
    if not widths:
        widths, groove_bs2 = atlas_service.default_width_tables()
        if not groove_bs:
            groove_bs = groove_bs2
    if session is not None:
        cache[cache_key] = (widths, groove_bs)
    return widths, groove_bs


def lookup_principle(session, model, name: str | None):
    """按名字取原则（同 session 内缓存）。

    原则改名 / 删除 / 新建后由 :func:`clear_calculation_caches` 清空。
    点击构件时同一原则常被计算、图集候选、断面图重复查询，缓存后只查一次。
    """
    if not name:
        return None
    from sqlalchemy import select

    cache = session.info.setdefault("section2_calc_lookup", {})
    key = (model.__name__, str(name))
    if key not in cache:
        found_id = session.scalar(select(model.id).where(model.name == name))
        cache[key] = session.get(model, found_id) if found_id is not None else None
    return cache[key]


def first_principle(session, model):
    """取库中第一条原则（同 session 内缓存）。"""
    from sqlalchemy import select

    cache = session.info.setdefault("section2_calc_lookup", {})
    key = (model.__name__, "")
    if key not in cache:
        cache[key] = session.scalar(select(model).order_by(model.order_no, model.id))
    return cache[key]


def clear_calculation_caches(session=None) -> None:
    """清空名称查找与面宽表缓存（原则/面宽数据变更或工程切换时调用）。"""
    target = session
    if target is None:
        try:
            from app.core.models import base as orm

            target = orm.session() if orm.is_open() else None
        except Exception:
            target = None
    if target is not None:
        target.info.pop("section2_calc_lookup", None)
        target.info.pop("section2_width_tables", None)


def workwidth_of(pw: PcpWidth | None, info: ElementInput) -> float:
    """按面宽原则 pw 的工作面宽度表查 info 首根管的工作面宽度（mm）。

    合槽编组用它取边缘工作面（wL 按父节点 PW + 构件 1 查、wR 按最右子节点
    PW + 其自身管径查）；查表语义与图集宽度查询同一条（百位取整、越界钳到
    0~3000，行由构件类别 + 管材类别决定）。
    """
    from app.core.pipe_category import width_dn_for, width_row_for

    widths, _groove_bs = _width_tables(pw)
    pipe = info.pipes[0] if info.pipes else None
    row = width_row_for(info.category, pipe.resolved_category() if pipe else "")
    dn = width_dn_for(info.category, pipe.dn if pipe else 0)
    key = max(0, min(3000, int(round(float(dn) / 100.0) * 100)))
    return widths.get(row, {}).get(key, 0.0)


def atlas_dims(info: ElementInput, at: AtlasParam) -> AtlasDims:
    """图集参数的算式伴随（mm 记法）：覆盖值取参数行原文，查表值以原始表值进算式。

    覆盖判定与 :func:`app.services.atlas._apply_overrides` 一致：工作面加宽 /
    垫层厚 / 基础厚按详情面板参数行（:func:`build_element_input` 已按类别滤过，
    键存在即覆盖），壁厚按管材行的用户值（包封 / 箱涵 / 管廊的断面宽由自身
    参数决定，不认管道壁厚）。图集无 oD 列时外径按 ``管径+2×壁厚`` 推出，
    算式里保留这个推导。所有 Dim 为 mm 记法（``v`` 已换算成 m）。
    """
    def _override(name: str) -> Dim | None:
        found = info.param_dims.get(name) if name in info.params else None
        # 用户覆盖值按 mm 录入：原文进算式、数值换到 m（mm 记法）
        return None if found is None else mm_dim(found)

    a = _override(PARAM_A_NAME) or mm(at.a).named("工作面加宽", "图集参数 a")
    c1 = _override(PARAM_C1_NAME) or mm(at.c1).named("垫层厚", "图集参数 C1")
    c2 = _override(PARAM_C2_NAME) or mm(at.c2).named("基础厚", "图集参数 C2")
    dn = (
        mm(info.pipes[0].dn).named("管径", "构件管材·管径")
        if info.pipes
        else mm(0.0)
    )
    wall = info.pipes[0].t if info.pipes else None
    if wall is not None and info.category not in C2_ZERO_CATEGORIES:
        t = mm(wall).named("管道壁厚", "管材参数·壁厚")
        od = (dn + t * 2).named("管道外径（mm）", "管径 + 2×壁厚")
    else:
        t = mm(at.t).named("管道壁厚", "图集参数 t")
        od = (
            mm(at.od).named("管道外径（mm）", "图集参数 oD")
            if at.od > 0
            else (dn + t * 2).named("管道外径（mm）", "管径 + 2×壁厚")
        )
    return AtlasDims(
        od=od,
        t=t,
        a=a,
        c1=c1,
        c2=c2,
        workwidth=mm(at.workwidth).named("工作面宽", "面宽原则·工作面宽度表"),
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


def _embed(formula: str, start: int, end: int, expression: str) -> str:
    """把公式里 [start, end) 处的变量名替换成代入算式，括号按位置的最小需要给。

    公式是用户可编辑的文本，代入位置接什么运算符由公式决定（:func:`pre_sub`
    与 :func:`value_exp` 共用）。规则：

    * 原子表达式（数字、单变量、函数调用，如 ``2`` / ``233.988``）哪里都不用括号；
    * 顶层是加减的算式一律括起来（它在乘除 / 减号 / 逗号等任何上下文里都可能
       需要括号，逐处判断不划算，保守处理不会算错）；
    * 顶层只有乘除的算式（``50*2``）只在“除数位置”（前面是 ``/``）或“乘方底数
       位置”（前后紧邻 ``^`` / ``**``）才括——乘除同级左结合，
       ``a*50*2/b`` ≡ ``a*(50*2)/b``；
    * 其余位置（前面是 ``(`` ``,`` ``+`` ``-`` ``*`` 或开头）不加括号。
    """
    if needs_parens(expression):
        return f"({expression})"
    if not needs_parens_tight(expression):
        return expression
    before = formula[:start].rstrip()
    after = formula[end:].lstrip()
    if before.endswith(("/", "÷", "^", "**")) or after.startswith(("^", "**")):
        return f"({expression})"
    return expression


def _substitute(formula: str, name: str, expression: str) -> str:
    """把公式里出现的变量名 ``name`` 全部换成 ``expression``（按位置补括号）。"""
    pattern = re.compile(r"\b" + re.escape(name) + r"\b")
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer(formula):
        parts.append(formula[cursor:match.start()])
        parts.append(_embed(formula, match.start(), match.end(), expression))
        cursor = match.end()
    parts.append(formula[cursor:])
    return "".join(parts)


def value_exp(params: dict[str, tuple[str, str]], key: str, _trail: tuple[str, ...] = ()) -> str:
    """公式里的参数引用递归代入（旧版 ValueExp/SubstitutingExp，含循环引用检测）。

    代入的算式按占位符位置的需要加括号（见 :func:`_embed`）：``2`` / ``233.988``
    这类原子表达式不再套括号，``600/2`` 只有在除数 / 乘方位置才括起来。
    """
    if key in _trail:
        return _CYCLE
    text = params[key][1]
    for other_key in params:
        if not re.search(r"\b" + re.escape(other_key) + r"\b", text):
            continue
        replaced = value_exp(params, other_key, _trail + (key,))
        if _CYCLE in replaced:
            return _CYCLE
        text = _substitute(text, other_key, replaced)
    return text or "0"


def key_exp(params: dict[str, tuple[str, str]], key: str) -> str:
    """定额键显示名：把参数引用替换成参数值（旧版 KeyExp）。"""
    text = params[key][0]
    for other_key, (_, other_value) in params.items():
        text = re.sub(r"\b" + re.escape(other_key) + r"\b", other_value, text)
    return text.replace(" ", "")


def pre_sub(expression: str, height: Dim, width: Dim, count: Dim, sides: int = 2) -> str:
    """把 height / width / count / sides 代入公式；埋深/数量为算式时原文随代入进算式。

    括号按占位符在公式里的位置给（见 :func:`_embed`），与参数引用的代入同一套规则。
    ``sides`` 是围护公式的"侧数"代入变量（v3）：普通构件恒 2（库模板的
    ``*2`` 已改写成 ``*sides``，代入后输出与旧版逐字节一致）；左右分设与
    合槽的每个面代入 1。公式里没写 ``sides`` 时零影响。
    """
    text = expression
    for name, value in (("height", height), ("width", width), ("count", count), ("sides", dim(sides))):
        text = _substitute(text, name, value.e)
    return text


def _display_category(display: str) -> str:
    """公式行的显示名类别（``围护|喷射砼|m3`` → ``围护``）。"""
    return (display or "").split("|", 1)[0].strip()


def component_quantities(
    component,
    height: Dim,
    width: Dim,
    count: Dim,
    cat: str,
    out: QDict,
    note: str = "",
    sides: int = 2,
    categories: set[str] | frozenset[str] | None = None,
) -> None:
    """构件公式求值（旧版 mcComponent.Q）：cat 目前只有 "F"（公式统一 F 开头）。

    ``categories`` 按公式显示名的类别（竖线前一段，如"围护"/"支撑"）筛选；
    None = 全部代入（普通单原则路径：匹配到做法后一次算出该做法下所有公式，
    不再区分围护与支撑）。
    """
    if component is None:
        return
    params = load_params(component)
    for key in params:
        if not key.startswith(cat) or len(key) <= 1:
            continue
        display = params[key][0]
        if categories is not None and _display_category(display) not in categories:
            continue
        substituted = value_exp(params, key)
        if substituted == _CYCLE or substituted == "":
            continue
        numeric = prettify_formula(pre_sub(substituted, height, width, count, sides))
        value = evaluate_or_default(numeric)
        if value != 0:
            out.add(
                key_exp(params, key),
                value,
                numeric,
                note,
                tags=height.tags + width.tags + count.tags,
            )


def component_side_quantities(
    component,
    height: Dim,
    width: Dim,
    count: Dim,
    out: QDict,
    note: str = "",
    category: str = "支撑",
    emit_without_sides: bool = True,
) -> None:
    """按公式类别筛选的单侧量（支撑）：公式含 ``sides`` 的按调用侧 ×1（围檩），
    不含 ``sides`` 的是整槽量（贯通支撑 / 支撑模板），只在
    ``emit_without_sides=True`` 的调用（首个勾选面）输出一次。

    行归属只看显示名类别（``支撑|…``），不再依赖 Z 键前缀。
    """
    if component is None:
        return
    params = load_params(component)
    for key in params:
        if not key.startswith("F") or len(key) <= 1:
            continue
        if _display_category(params[key][0]) != category:
            continue
        substituted = value_exp(params, key)
        if substituted == _CYCLE or substituted == "":
            continue
        has_sides = re.search(r"\bsides\b", substituted) is not None
        if not has_sides and not emit_without_sides:
            continue  # 贯通支撑行：整槽只出一次
        numeric = prettify_formula(pre_sub(substituted, height, width, count, 1))
        value = evaluate_or_default(numeric)
        if value != 0:
            out.add(
                key_exp(params, key),
                value,
                numeric,
                note,
                tags=height.tags + width.tags + count.tags,
            )


def support_quantities_sided(
    works,
    depth: Dim,
    count: Dim,
    ad: AtlasDims,
    info: ElementInput,
    out: QDict,
    width: Dim | None = None,
    note: str = "",
    emit_strut: bool = True,
) -> None:
    """左右分设 / 合槽的支撑输出：``works`` = [(做法, 勾选了支撑)]。

    支撑行按公式类别（``支撑|…``）识别：围檩行每个勾选面各出一次（×1）；
    贯通支撑行只在第一个勾选面出一次（左优先，勾选顺序即列表顺序）。
    级高划分同 works_quantities。
    """
    if width is None:
        width = groove.groove_width(ad, info.size_b_dim).to_m()
    strut_emitted = not emit_strut
    for work, checked in works:
        if not checked or work is None:
            continue
        levels = list(work.levels)
        fixed_h = dim_sum(*(dim(level.h) for level in levels if level.h >= 0))
        fixed_cnt = sum(1 for level in levels if level.h >= 0)
        for level in levels:
            if level.h >= 0:
                height = dim(level.h)
            elif len(levels) > fixed_cnt:
                height = (depth - fixed_h) / (len(levels) - fixed_cnt)
            else:
                height = depth
            component = level.components[0] if level.components else None
            component_side_quantities(
                component, height, width, count, out,
                note=note, emit_without_sides=not strut_emitted,
            )
            strut_emitted = True  # 首个勾选面之后不再出贯通支撑行


def prettify_formula(expression: str) -> str:
    """公式算式：函数名转 Excel 大写写法（``ROUND``/``SQRT``…），``**`` 转 ``^``。

    ``^`` 仍由 evaluator.normalize 在求值时转回 ``**``，所以这里只负责输出好看、
    贴进 Excel 能用。
    """
    text = expression.replace("**", "^")
    for name in ("CEILING", "ROUNDUP", "ROUND", "SQRT", "ABS", "POWER", "CEIL", "SIN", "COS"):
        text = re.sub(r"(?<![A-Za-z])" + name + r"(?=\s*\()", name, text, flags=re.IGNORECASE)
    return text


# --------------------------------------------------------------------------- #
# 总入口
# --------------------------------------------------------------------------- #
def cushion_thickness(pf: PcpFoundation) -> float:
    """垫层厚 mm（垫层 v10 起属地基原则）；算式伴随见 measures.cushion_thickness。

    mm 记法后 :func:`measures.cushion_thickness` 的 ``.v`` 是 m，这里换回 mm
    （图集参数替换 / 断面图等消费方都按 mm 取值）。
    """
    return cushion_dim(pf).v * 1000.0


def foundation_thickness(pf: PcpFoundation) -> float:
    """换填总厚 mm（旧版 mcPcpFoundation.TiA）；算式伴随见 measures.foundation_thickness。"""
    return foundation_dim(pf).v * 1000.0


def compute_element(info: ElementInput) -> QDict | None:
    """计算一个构件条目的工程量；数量为 0 或原则缺失时返回 None。

    顶管 / 牵引管不开槽，只有管材（见 :func:`compute_trenchless`）；
    沟槽断面 + 降水 + 围护/支撑公式(F) + 特殊地基按构件引用的单条 pe × pf
    计算（旧版多原则的按比例组合在迁移时已拆成独立条目）；围护做法用 pe，
    管道基础 / 图集查询 / 垫层用 pf，挖填类型与降水用 pp（v10 归属）。

    做法档位统一按**含换填层厚度**的 ``groove_depth`` 匹配；匹配到做法后
    一次代入该做法下的全部公式（围护与支撑不再分开取深度 / 选做法）。
    """
    if info.category == CATEGORY_STRUCTURE:
        return compute_structure(info)
    if info.category in (CATEGORY_JACKING, CATEGORY_PULLING):
        return compute_trenchless(info)
    if info.pe_left is not None or info.pe_right is not None:
        return compute_element_lr(info)
    pe = info.pe
    pf = info.pf
    if info.amount == 0 or pe is None or pf is None or info.pp is None or info.pw is None:
        return None
    depth_dim = info.depth_dim
    amount_dim = info.amount_dim

    at = resolve_atlas(build_atlas_query(info, pf, info.pw))
    ad = atlas_dims(info, at)
    if ad.c1.v == 0:
        # 垫层厚 0（砂基础无垫层）：旧版语义——垫层取地基原则的垫层表值
        ad = ad.replace(c1=cushion_dim(pf))

    per_meter = QDict()
    # mm 记法的 (换填总厚+壁厚+垫层厚)，几何链与公式路径共用
    mm_extra = foundation_dim(pf) + ad.t + ad.c1
    groove_depth = (
        mm_of_m(depth_dim).named("埋深", "构件埋深") + mm_extra
    ).named("计算深度", "埋深 + 换填总厚 + 壁厚 + 垫层厚")
    # 用户公式（围护 / 特殊地基）按 m 口径代入：埋深原文保留、换算部分 /1000
    groove_depth_m = (depth_dim + mm_extra.to_m()).named(
        "计算深度", "埋深 + (换填总厚+壁厚+垫层厚)/1000"
    )
    work = choice_work(pe, groove_depth.v)
    if work is None:
        return None
    if not groove.cal_groove(info.pp, work, pf, ad, info.size_b_dim, info.size_h_dim, groove_depth, per_meter):
        return None
    precipitation.cal_precipitation(info.pp, work, pf, ad, info, groove_depth, per_meter)
    works_quantities(work, groove_depth_m, amount_dim, "F", ad, info, per_meter, "围护")
    special = pf.components[0] if pf.components else None
    if special is not None:
        component_quantities(
            special,
            groove_depth_m,
            groove.groove_width(ad, info.size_b_dim).to_m(),
            amount_dim,
            "F",
            per_meter,
            "特殊地基",
        )

    # 管道基础（扣弓形占土）+ 管材
    foundation.cal_found(info, pf, info.pp, ad, per_meter)
    if info.category == CATEGORY_ENCASED:
        foundation.encased_pipe_deduction(info, per_meter)
    foundation.cal_pipes(info, per_meter)

    per_meter.scale(info.amount, expr=amount_dim.e)
    return per_meter


def compute_element_lr(info: ElementInput) -> QDict | None:
    """左右分设构件的计算（v3）：两侧各自的围护做法 + 单面公式（sides=1）。

    * 挖填类型（开挖土质 / 回填材质）与降水取 ``pp``（挖填降水原则，v10 起
      不再随左右围护不一致而分侧）；管道基础（砼基础 / 角度 / 垫层，决定图集
      查询）取 ``pf``（地基原则）；
    * 断面几何走 :func:`groove.cal_groove_sided`（两侧级标高并集切段）；
    * 做法档位统一按含换填层厚度的 ``groove_depth`` 匹配；围护行（类别
      ``围护``）每侧各调一次 ×1；支撑行按公式类别（``支撑``）识别，按左右
      支撑勾选输出（围檩每侧一次、贯通支撑整槽一次，见
      :func:`support_quantities_sided`）；
    * 降水的湿土排水副调用也走双侧几何；特殊地基 / 管道基础 / 管材同单原则路径。
    """
    pe_l, pe_r = info.pe_left, info.pe_right
    pf = info.pf
    pp = info.pp
    if pe_l is None or pe_r is None or pf is None or pp is None or info.pw is None:
        return None
    if info.amount == 0:
        return None
    depth_dim = info.depth_dim
    amount_dim = info.amount_dim

    at = resolve_atlas(build_atlas_query(info, pf, info.pw))
    ad = atlas_dims(info, at)
    if ad.c1.v == 0:
        # 垫层厚 0（砂基础无垫层）：取地基原则的垫层表值
        ad = ad.replace(c1=cushion_dim(pf))

    per_meter = QDict()
    mm_extra = foundation_dim(pf) + ad.t + ad.c1
    groove_depth = (
        mm_of_m(depth_dim).named("埋深", "构件埋深") + mm_extra
    ).named("计算深度", "埋深 + 换填总厚 + 壁厚 + 垫层厚")
    groove_depth_m = (depth_dim + mm_extra.to_m()).named(
        "计算深度", "埋深 + (换填总厚+壁厚+垫层厚)/1000"
    )
    work_l = choice_work(pe_l, groove_depth.v)
    work_r = choice_work(pe_r, groove_depth.v)
    if work_l is None or work_r is None:
        return None
    cushion_name = pf.cushions[0].name if pf.cushions else "中粗砂"
    if not groove.cal_groove_sided(
        pp, work_l, work_r, pf, ad, info.size_b_dim, info.size_h_dim,
        groove_depth, per_meter, cushion_name,
    ):
        return None
    # 围护行：每侧 ×1（库公式 *sides 代入 1；放坡模板无公式天然不出量）
    works_quantities(
        work_l, groove_depth_m, amount_dim, "F", ad, info, per_meter,
        "围护·左侧", sides=1, categories={"围护"},
        width=groove.groove_width(ad, info.size_b_dim).to_m(),
    )
    works_quantities(
        work_r, groove_depth_m, amount_dim, "F", ad, info, per_meter,
        "围护·右侧", sides=1, categories={"围护"},
        width=groove.groove_width(ad, info.size_b_dim).to_m(),
    )
    # 支撑行按公式类别识别（不再看 Z 键前缀）：围檩每侧 ×1、贯通支撑整槽一次
    support_quantities_sided(
        [(work_l, info.support_left), (work_r, info.support_right)],
        groove_depth_m, amount_dim, ad, info, per_meter, note="支撑",
    )
    # 降水（湿土排水的断面副调用也走双侧几何，垫层材质取地基原则）
    precipitation.cal_precipitation(
        pp, work_l, pf, ad, info, groove_depth, per_meter,
        work_r=work_r, cushion_name=cushion_name,
    )
    # 特殊地基：按整槽宽（同单原则路径）
    special = pf.components[0] if pf.components else None
    if special is not None:
        component_quantities(
            special,
            groove_depth_m,
            groove.groove_width(ad, info.size_b_dim).to_m(),
            amount_dim,
            "F",
            per_meter,
            "特殊地基",
        )
    # 管道基础（扣弓形占土，公共参数取地基原则）+ 管材
    foundation.cal_found(info, pf, pp, ad, per_meter)
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
        count = raw_dim(cnt_text, evaluate_or_default(cnt_text)).named(
            "井筒个数", "构件参数·井筒（个）"
        )
        rate = raw_dim(rate_text, evaluate_or_default(rate_text)).named(
            "井筒每米方量", "构件参数·井筒（m3/m）"
        )
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
            f"{wrap(count.e)}*{wrap(well_h.e)}*{wrap(rate.e)}",
            "井筒",
            tags=count.tags + well_h.tags + rate.tags,
        )
    out.scale(info.amount, expr=amount_dim.e)
    return out


def works_quantities(
    work,
    depth: Dim,
    count: Dim,
    cat: str,
    ad: AtlasDims,
    info: ElementInput,
    out: QDict,
    note: str,
    sides: int = 2,
    width: Dim | None = None,
    categories: set[str] | frozenset[str] | None = None,
) -> None:
    """围护做法各级构件 + 止水构件的公式量（旧版 cal_Ecpnts）。

    代入公式的 ``width`` 是槽底宽，与挖方 / 特殊地基同一条
    :func:`app.core.calc.groove.groove_width`（面宽原则用沟槽宽度表时取表值）；
    ``width`` 显式传入时按传入值（合槽用平底宽 B_平底）。

    ``sides`` 是围护公式的侧数代入（v3，见 :func:`pre_sub`）：普通构件 2，
    左右分设 / 合槽的每个面 1。

    ``categories`` 按公式显示名类别筛选（左右分设 / 合槽的围护面传
    ``{"围护"}``，避免支撑行被每侧重复计入）；普通路径 None = 全部公式。

    与旧版的偏差（修正旧版缺陷）：旧版 cal_Ecpnts 写的是
    ``D10E3(SizeB + t*2 + a*2 + workwidth*2)``，把米制的断面宽混进毫米的和里
    整体除 1000，断面宽被抹掉（cal_groove / cal_Fcpnts 用的是
    ``SizeB + D10E3(…)``，三处只有这里漏了）；结果引用 width 的公式偏小——
    直埋管少算约一个管径，箱涵 / 管廊能少到只有应有槽底宽的 1/4~1/3，
    属有意偏差。
    """
    levels = list(work.levels)
    fixed_h = dim_sum(*(dim(level.h) for level in levels if level.h >= 0))
    fixed_cnt = sum(1 for level in levels if level.h >= 0)
    if width is None:
        width = groove.groove_width(ad, info.size_b_dim).to_m()
    for level in levels:
        if level.h >= 0:
            height = dim(level.h)
        elif len(levels) > fixed_cnt:
            height = (depth - fixed_h) / (len(levels) - fixed_cnt)
        else:
            height = depth
        component = level.components[0] if level.components else None
        component_quantities(
            component, height, width, count, cat, out, note, sides, categories=categories
        )
    waterstop = work.waterstops[0] if work.waterstops else None
    if waterstop is not None:
        component_quantities(waterstop, depth, width, count, "F", out, "止水", sides)


def replace(at, **changes):
    """复制图集参数并覆盖指定字段（dataclasses.replace 的轻量封装）。"""
    from dataclasses import replace as _replace

    return _replace(at, **changes)


def resolve_element_principles(element: Element, session):
    """按构件的引用解析出 (pe, pf, pp, pw)。

    引用名失效（原则被删、旧文件迁出的行）时取库中第一条，与界面回退一致。
    """
    def _by_name(model, name: str):
        return lookup_principle(session, model, name)

    def _first(model):
        return first_principle(session, model)

    pe = _by_name(PcpEnclosure, element.pe_name)
    if pe is None and element.pe_name == LR_PE_TEXT:
        # 左右分设：pe 解析为左侧原则（v10 起管道基础属地基原则，不再按侧取；
        # 围护做法消费者读左侧），左右两侧完整解析见 _resolve_lr_enclosures
        pe_left, _pe_right = _resolve_lr_enclosures(element)
        pe = pe_left
    pf = _by_name(PcpFoundation, element.pf_name)
    pp = _by_name(PcpPrecipitation, element.pp_name) or _first(PcpPrecipitation)
    pw = _by_name(PcpWidth, element.pw_name) or _first(PcpWidth)
    return pe, pf, pp, pw


def is_concrete_pipe(info: ElementInput) -> bool:
    """是否混凝土管道（旧版 mcE1.IsConPipe）。

    v8 起读管道行的管材类别（混凝土管-刚性 / 柔性接口），不再按材质名称判断。
    """
    from app.core.pipe_category import is_concrete

    pipe = info.pipes[0] if info.pipes else None
    return is_concrete(pipe.cat if pipe else "", mat=pipe.mat if pipe else "")
