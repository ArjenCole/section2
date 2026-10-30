"""单位工程面板视图模型。

中部下半区：构件录入表（埋深 / 数量支持算式）+ 选中构件的明细（管材、构件参数）。
埋深、数量在库里存字符串原文，展示时用 core.evaluator 求值，失败不写 0 而是标出错误。

构件/管道/参数的数据操作写成模块级函数（create_element / update_element / …）：
界面用它们，M8 的 AI 工具也用它们，保持一条代码路径。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.evaluator import EvalError, evaluate, format_number
from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import (
    BACKFILL_INDEPENDENT,
    BACKFILL_MODES,
    CATEGORY_BURIED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
    CATEGORY_JACKING,
    CATEGORY_PULLING,
    CATEGORY_STRUCTURE,
    LR_PE_TEXT,
    SPLIT_MODES,
    SPLIT_SLOPE_POINT,
    Element,
    ElementParam,
    ElementQuantity,
    Pipe,
    TrenchGroup,
    unit_of,
)
from app.core.param_naming import (
    DEFAULT_PARAM_UNITS,
    PARAM_A_NAME,
    PARAM_C1_NAME,
    PARAM_C2_NAME,
    PARAM_T_NAME,
    STRUCTURE_NAME_PARAM,
    STRUCTURE_UNIT_PARAM,
    atlas_param_rows,
    is_atlas_param,
    split_param_key,
    supports_atlas_param,
)
from app.services import project_io

_ELEMENT_FIELDS = {
    "category",
    "name",
    "depth",
    "amount",
    "pe_name",
    "pf_name",
    "pp_name",
    "pw_name",
    "source",
    "order_no",
    "pe_left_name",
    "pe_right_name",
    "support_left",
    "support_right",
}
_PIPE_FIELDS = {"mat", "cat", "dn", "content", "t"}
_PARAM_FIELDS = {"key", "unit", "value"}
_QUANTITY_FIELDS = {"category", "item", "unit", "value"}

#: 不显示图集参数行的类别上新增 / 改名成图集参数时的提示（见 param_naming）
_ATLAS_PARAM_LOCKED_HINT = (
    "该类别构件不显示该图集参数行（直埋显示工作面加宽 / 垫层厚 / 基础厚；"
    "包封 / 箱涵 / 管廊的基础厚恒为 0，只显示工作面加宽 / 垫层厚；"
    "顶管 / 牵引管只算管材，三行都不显示）。"
)


# --------------------------------------------------------------------------- #
# 展示用行
# --------------------------------------------------------------------------- #
@dataclass
class ElementRow:
    id: int
    category: int
    name: str
    depth: str
    amount: str
    pe_name: str
    pf_name: str
    pp_name: str
    pw_name: str
    order_no: int
    unit: str
    depth_value: float
    amount_value: float
    depth_error: str = ""
    amount_error: str = ""
    #: 计算失败说明（M4 计算引擎回填，空表示正常）
    error: str = ""
    #: 规格（旧版 Specification()，清单项目行用）
    spec: str = ""
    #: 来源（旧版主表格“来源”列，构件库插入时记录模板出处）
    source: str = ""
    #: 左右分设（v3）：左右围护原则 / 支撑勾选
    pe_left_name: str = ""
    pe_right_name: str = ""
    support_left: bool = True
    support_right: bool = True
    #: 合槽编组（v3）：所属组的 id；None = 独立构件
    group_id: int | None = None
    #: 组内位置（从左到右 0 起）；独立构件恒 0
    group_index: int = 0


@dataclass
class GroupRow:
    """合槽父节点行（主表格显示用）。

    父节点零工程量：不参与计算，仅作下属子构件工程量的合计分组视图。
    父节点也不持有围护 / 面宽原则（``pe_name`` / ``pw_name`` 恒空，界面
    显示 "-"）：左 / 右边坡与各构件工作面宽全部由子构件自己的原则决定。
    **埋深恒显示 "-"、不参与任何计算**；**数量 L_组 由父节点唯一持有**
    （子构件 ``Element.amount`` 强制等于父节点 ``TrenchGroup.amount``）。
    显示位置 = 首个成员的位置（成员强制连续，见 :func:`create_trench_group`）。
    """

    id: int
    name: str
    pe_name: str  # 恒空（父节点不选围护原则）
    pw_name: str  # 恒空（父节点不选工作面宽原则）
    order_no: int
    member_count: int
    #: 回填分层方式（主表格挖填降水列的下拉）：独立回填标高 / 统一回填标高
    backfill_mode: str = BACKFILL_INDEPENDENT
    #: 断面划分方式（主表格面宽列的下拉）：起坡点分割 / 管中心分隔
    split_mode: str = SPLIT_SLOPE_POINT
    #: 供主表格统一装填的显示属性（与 ElementRow 同名同型）
    category: int = 0
    depth: str = ""
    amount: str = ""
    pf_name: str = ""
    pp_name: str = ""
    source: str = "合槽编组"
    spec: str = ""
    unit: str = "m"
    depth_value: float = 0.0
    amount_value: float = 0.0
    depth_error: str = ""
    amount_error: str = ""
    error: str = ""


@dataclass
class PipeRow:
    id: int
    mat: str
    dn: int
    content: str
    #: 管道壁厚 mm 用户值；None = 自动按图集（界面灰色显示默认值）
    t: float | None = None
    #: 管材类别（宽度表行名，见 core.pipe_category）：计算唯一依据
    cat: str = ""


@dataclass
class ParamRow:
    id: int
    key: str
    unit: str
    value: str
    #: 参数名/单位锁定（图集行、构筑物的名称/单位行），只允许改值
    lock_name: bool = False
    #: 候选参数列（v9，直埋构件）：{combo_key: (候选行 id, 该参数对应的值)}；
    #: 空字典 = 该构件不显示候选列
    candidates: dict[str, tuple[int, float | None]] = field(default_factory=dict)


@dataclass
class QuantityRow:
    """附属构筑物工程量行（详情面板“工程量”页，可增删）。"""

    id: int
    category: str
    item: str
    unit: str
    value: str


def _evaluate_field(text: str) -> tuple[float, str]:
    """返回 (值, 错误信息)；错误信息非空表示该格算式不合法。"""
    try:
        return evaluate(text), ""
    except EvalError as error:
        return 0.0, str(error)


def element_rows(unit_id: int) -> list[ElementRow]:
    """读取某单位工程的构件列表（含算式求值结果，不含合槽父节点行）。"""
    if not project_io.is_open():
        return []
    rows: list[ElementRow] = []
    for element in _elements_of(unit_id):
        row = _element_row(element)
        row.spec = _element_spec(element)
        rows.append(row)
    return rows


def table_rows(unit_id: int) -> list:
    """主表格显示序列：构件行 + 合槽父节点行（插在首成员位置、成员缩进）。

    组员按 order_no 强制连续（编组 / 加组 / 移动时维护）；父行出现在该组
    第一个成员之前。返回 ``ElementRow | GroupRow`` 混合列表，面板按
    ``isinstance(row, GroupRow)`` 分支装填。
    """
    elements = element_rows(unit_id)
    by_group: dict[int, list[ElementRow]] = {}
    for row in elements:
        if row.group_id is not None:
            by_group.setdefault(row.group_id, []).append(row)
    rows: list = []
    emitted: set[int] = set()
    for row in elements:
        if row.group_id is not None and row.group_id not in emitted:
            emitted.add(row.group_id)
            rows.append(_group_row(row.group_id, by_group[row.group_id]))
        if row.group_id is not None:
            row.group_index = next(
                (
                    index
                    for index, member in enumerate(by_group[row.group_id])
                    if member.id == row.id
                ),
                0,
            )
        rows.append(row)
    return rows


def _group_row(group_id: int, members: list[ElementRow]) -> GroupRow:
    """父节点行：名称 + 数量（L_组）；埋深与原则不参与（显示 "-"）。"""
    group = orm.session().get(TrenchGroup, group_id)
    if group is None:  # pragma: no cover - 删除竞态下短暂出现
        return GroupRow(
            id=group_id,
            name="合槽组",
            pe_name="",
            pw_name="",
            order_no=0,
            member_count=len(members),
            depth="-",
        )
    amount = _group_amount(group) or (members[0].amount if members else "")
    amount_value, amount_error = _evaluate_field(amount or "0")
    return GroupRow(
        id=group.id,
        name=group.name,
        pe_name="",
        pw_name="",
        order_no=group.order_no,
        member_count=len(members),
        backfill_mode=group.backfill_mode if group.backfill_mode in BACKFILL_MODES else BACKFILL_INDEPENDENT,
        split_mode=group.split_mode if group.split_mode in SPLIT_MODES else SPLIT_SLOPE_POINT,
        depth="-",
        amount=amount,
        amount_value=amount_value,
        amount_error=amount_error,
        spec=f"{len(members)} 条构件合槽",
    )


def _group_amount(group: TrenchGroup | None) -> str:
    """组数量（L_组）：父节点存值；旧数据为空时回退首成员数量。"""
    if group is None:
        return ""
    if group.amount:
        return group.amount
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    return (members[0].amount or "") if members else ""


def _element_spec(element: Element) -> str:
    """规格文本（旧版 Specification()）；不依赖原则，算不出就留空。"""
    try:
        from app.core.calc.engine import build_element_input

        return build_element_input(element, None, None).spec()
    except Exception:
        return ""


def pipe_rows(element_id: int) -> list[PipeRow]:
    element = _element(element_id)
    if element is None:
        return []
    return [
        PipeRow(
            id=pipe.id,
            mat=pipe.mat,
            cat=pipe.pipe_category,
            dn=pipe.dn,
            content=pipe.content,
            t=pipe.t,
        )
        for pipe in element.pipes
    ]


def param_rows(element_id: int) -> list[ParamRow]:
    element = _element(element_id)
    if element is None:
        return []
    from app.core.atlas_candidates import combo_key

    #: 参数名 → 候选行字段（t / a / C1 / C2）
    field_by_param = {
        PARAM_T_NAME: "t",
        PARAM_A_NAME: "a",
        PARAM_C1_NAME: "c1",
        PARAM_C2_NAME: "c2",
    }
    rows = []
    for param in element.params:
        if element.category == CATEGORY_STRUCTURE:
            lock_name = (param.key, param.unit) == (STRUCTURE_NAME_PARAM, "") or (
                param.key, param.unit
            ) == (STRUCTURE_UNIT_PARAM, "")
        elif is_atlas_param(param.key, param.unit):
            if not supports_atlas_param(element.category, param.key, param.unit):
                continue  # 该类别不显示这一行（旧库残留行也不显示，不参与计算）
            lock_name = True
        else:
            lock_name = False
        candidates: dict[str, tuple[int, float | None]] = {}
        candidate_field = field_by_param.get(param.key)
        if element.category == CATEGORY_BURIED and candidate_field:
            for row in element.atlas_candidates:
                candidates[combo_key(row.con_found, row.angle)] = (
                    row.id,
                    getattr(row, candidate_field),
                )
        rows.append(
            ParamRow(
                id=param.id,
                key=param.key,
                unit=param.unit,
                value=param.value,
                lock_name=lock_name,
                candidates=candidates,
            )
        )
    # 直埋的图集参数行按 param_naming.ATLAS_PARAM_NAMES 的顺序显示（管道壁厚在最前），
    # 老工程迁移出来的行顺序不定，这里统一一次；其它类别与普通参数保持原有次序
    if element.category == CATEGORY_BURIED:
        from app.core.param_naming import ATLAS_PARAM_NAMES

        order = {name: index for index, (name, _unit) in enumerate(ATLAS_PARAM_NAMES)}
        rows.sort(key=lambda row: (0, order[row.key]) if row.key in order else (1, 0))
    return rows


def selected_candidate_combo(element_id: int) -> tuple[str | None, str | None]:
    """当前匹配到的候选组合 ``(组合键, 层级)``——详情面板高亮当前列用。

    ``(None, None)`` = 四级都没命中（参数行为空，计算按图集走）。只读查询，
    不补候选行、不写库。
    """
    element = _element(element_id)
    if element is None:
        return None, None
    from app.services.atlas_match import selected_combo

    return selected_combo(element)


def quantity_rows(element_id: int) -> list[QuantityRow]:
    """附属构筑物的工程量行（详情面板“工程量”页只对构筑物启用）。"""
    element = _element(element_id)
    if element is None or element.category != CATEGORY_STRUCTURE:
        return []
    return [
        QuantityRow(
            id=quantity.id,
            category=quantity.category,
            item=quantity.item,
            unit=quantity.unit,
            value=quantity.value,
        )
        for quantity in element.quantities
    ]


def compute_unit(unit_id: int):
    """计算整个单位工程（M4）。

    返回 ``(定额汇总 QDict, [(构件行, 该构件的 QDict)])``；构件计算失败
    （数量为 0 / 原则缺失 / 覆土不足）时其 QDict 为空字典并在行上带错误说明。
    合槽编组的成员由 :func:`app.core.calc.trench_group.compute_group` 统一
    计算（整组一次、逐构件归属），父节点不出现在明细里（零工程量）。
    """
    from app.core.calc.engine import (
        build_element_input,
        compute_element,
        resolve_element_principles,
    )
    from app.core.calc.tracer import QDict
    from app.core.calc.trench_group import compute_group

    summary = QDict()
    detail: list[tuple[ElementRow, QDict]] = []
    if not project_io.is_open():
        return summary, detail
    session = orm.session()
    group_cache: dict[int, tuple[dict[int, QDict], dict[int, str]]] = {}
    for element in _elements_of(unit_id):
        row = _element_row(element)
        if element.group_id is not None:
            # 编组成员：整组只算一次（首成员触发），逐构件挂量
            cached = group_cache.get(element.group_id)
            if cached is None:
                group = session.get(TrenchGroup, element.group_id)
                cached = compute_group(group) if group is not None else ({}, {})
                group_cache[element.group_id] = cached
            results, errors = cached
            row.spec = _element_spec(element)
            result = results.get(element.id, QDict())
            row.error = errors.get(element.id, "")
            detail.append((row, result))
            summary.extend(result)
            continue
        pe, pf, pp, pw = resolve_element_principles(element, session)
        info = build_element_input(element, pe, pf, pp, pw)
        row.spec = info.spec()
        try:
            result = compute_element(info) or QDict()
            if element.category == CATEGORY_STRUCTURE and not result:
                row.error = "数量为 0，未生成工程量。"
            elif element.category in (CATEGORY_JACKING, CATEGORY_PULLING) and not result:
                # 顶管 / 牵引管只有管材：数量为 0，或没录入管材
                row.error = (
                    "数量为 0，未生成工程量。"
                    if row.amount_value == 0
                    else "未录入管材，顶管 / 牵引管只计算管材。"
                )
            else:
                row.error = "" if result else "覆土不足或缺少可用的围护/地基原则"
        except Exception as error:  # 单条失败不拖垮整表
            result = QDict()
            row.error = str(error)
        detail.append((row, result))
        summary.extend(result)
    return summary, detail


def _element_row(element: Element) -> ElementRow:
    depth_value, depth_error = _evaluate_field(element.depth)
    amount_value, amount_error = _evaluate_field(element.amount)
    unit = unit_of(element.category)
    if element.category == CATEGORY_STRUCTURE:
        # 旧版 mcElement.Unit getter：参数里的“单位”行覆盖默认单位（座/个/套…）
        for param in element.params:
            if (param.key, param.unit) == (STRUCTURE_UNIT_PARAM, "") and param.value.strip():
                unit = param.value.strip()
                break
    return ElementRow(
        id=element.id,
        category=element.category,
        name=element.name,
        depth=element.depth,
        amount=element.amount,
        pe_name=element.pe_name,
        pf_name=element.pf_name,
        pp_name=element.pp_name,
        pw_name=element.pw_name,
        order_no=element.order_no,
        unit=unit,
        depth_value=depth_value,
        amount_value=amount_value,
        depth_error=depth_error,
        amount_error=amount_error,
        source=element.source,
        pe_left_name=element.pe_left_name or "",
        pe_right_name=element.pe_right_name or "",
        support_left=bool(element.support_left),
        support_right=bool(element.support_right),
        group_id=element.group_id,
    )


# --------------------------------------------------------------------------- #
# 数据操作（界面与 AI 工具共用）
# --------------------------------------------------------------------------- #
#: 附属构筑物默认参数：名称 / 单位行（锁定参数名、单位列留空，值列影响主表格）
_STRUCTURE_DEFAULT_PARAMS = (
    (STRUCTURE_NAME_PARAM, "", "自定义构筑物"),
    (STRUCTURE_UNIT_PARAM, "", "个"),
)


def _structure_default_quantity() -> ElementQuantity:
    """附属构筑物默认工程量行：构筑物 / 自定义构筑物 / 个 / 1。"""
    return ElementQuantity(category="构筑物", item="自定义构筑物", unit="个", value="1", order_no=0)


def _append_atlas_rows(element: Element) -> None:
    """补该类别显示的图集参数行（空 = 自动按图集 / 软件约定）。

    直埋管道补工作面加宽 / 垫层厚 / 基础厚三行；包封埋管 / 箱涵 / 管廊补
    工作面加宽 / 垫层厚（基础厚恒为 0，不显示）；顶管 / 牵引管只算管材，
    一行不补（1.0 也没有）。见 param_naming.ATLAS_PARAM_CATEGORIES。
    """
    existing = {(param.key, param.unit) for param in element.params}
    for name, unit in atlas_param_rows(element.category):
        if (name, unit) not in existing:
            element.params.append(ElementParam(key=name, unit=unit, value=""))


def _reconcile_atlas_rows(element: Element) -> None:
    """类别切换后按新类别增删图集参数行（不显示的行删掉，缺的行补空值）。

    直埋 ↔ 包封 / 箱涵 / 管廊：切到基础厚恒为 0 的类别时删掉基础厚行，切回
    直埋时补回空值行（空 = 自动按图集）；切到顶管 / 牵引管时三行全删。
    """
    allowed = set(atlas_param_rows(element.category))
    for param in list(element.params):
        if is_atlas_param(param.key, param.unit) and (param.key, param.unit) not in allowed:
            element.params.remove(param)  # delete-orphan 级联删除
    _append_atlas_rows(element)


def _expire_element(element: Element) -> None:
    """让已完成 commit 的构件整体失效，下次读取按最新数据。

    共享会话 expire_on_commit=False：管材/参数/工程量行以独立对象入会话
    （element.pipes.append 的方式），commit 后父构件的子集合仍是旧数据，
    明细面板 / 工程量重算会漏示新增行——这里手动 expire 弥补。
    """
    try:
        orm.session().expire(element)
    except Exception:
        pass


def auto_atlas_params(element: Element) -> dict[str, float]:
    """该类别显示的图集参数行的自动值（空参数行灰字显示用）。

    按构件当前原则查图集：直埋管道为图集行的 a / C1 / C2；包封 / 箱涵 /
    管廊为软件约定值（t=0、a=100、C1=100、C2 恒为 0）里的工作面加宽 /
    垫层厚；垫层厚为 0 时按围护原则垫层回填（同引擎）。不显示的类别
    （顶管 / 牵引管等）返回空。
    """
    from app.core.calc.engine import (
        build_atlas_query,
        build_element_input,
        cushion_thickness,
        resolve_element_principles,
    )
    from app.services.atlas import resolve_atlas

    if not atlas_param_rows(element.category):
        return {}
    pe, pf, _pp, pw = resolve_element_principles(element, orm.session())
    if pe is None or pf is None:
        return {}
    info = build_element_input(element, pe, pf)
    at = resolve_atlas(build_atlas_query(info, pf, pw))
    values = {
        PARAM_A_NAME: at.a,
        PARAM_C1_NAME: at.c1 if at.c1 != 0 else cushion_thickness(pf),
        PARAM_C2_NAME: at.c2,
    }
    # 管道壁厚只在图集查得到时给灰字（0 = 该组合无数据，不显示"0"）
    if at.t:
        values[PARAM_T_NAME] = at.t
    allowed = {name for name, _unit in atlas_param_rows(element.category)}
    return {name: value for name, value in values.items() if name in allowed}


def auto_pipe_thicknesses(element: Element) -> dict[int, float]:
    """每根管道的图集自动壁厚（mm，供界面空值行灰字显示）。

    同引擎语义：直埋 / 顶管 / 牵引按各自图集类别查；包封管道按临时
    直埋类别查（同扣管位逻辑）；箱涵 / 管廊不带管道表壁厚按 0。
    """
    from app.core.calc.engine import build_atlas_query, build_element_input, resolve_element_principles
    from app.core.pipe_category import CONCRETE_PIPE_CATEGORIES
    from app.services.atlas import PipeSpec, resolve_atlas

    if element.category in (CATEGORY_BOX_CULVERT, CATEGORY_GALLERY):
        return {pipe.id: 0.0 for pipe in element.pipes}
    pe, pf, _pp, pw = resolve_element_principles(element, orm.session())
    if pe is None or pf is None:
        return {}
    info = build_element_input(element, pe, pf)
    result: dict[int, float] = {}
    for pipe in element.pipes:
        probe = build_atlas_query(info, pf, pw)
        # 壁厚留空才显示图集值，所以这里刻意不传 t（传了就会走快照短路返回它本身）
        probe.pipes = [PipeSpec(mat=pipe.mat, dn=pipe.dn, cat=pipe.pipe_category)]
        if element.category == CATEGORY_ENCASED:
            probe.category = CATEGORY_BURIED  # 同引擎包封扣管位的临时直埋查询
        thickness = resolve_atlas(probe).t
        if not thickness and pipe.pipe_category in CONCRETE_PIPE_CATEGORIES:
            # 砂基础表没有小管径行（页8~14 从 D=400/600 起）→ 退回砼基础表
            # 同角度的壁厚：壁厚是管子属性，不该因为选了砂基础就变 0
            probe.con_found = True
            thickness = resolve_atlas(probe).t
        result[pipe.id] = thickness
    return result


def _seed_atlas_defaults(element: Element) -> None:
    """补图集值（v10）。

    * 直埋构件：补 8 组候选（候选缺失时现场查图集一次）并按当前围护原则
      自动匹配写参数行（壁厚也走这条线：参数行 → 首根管 t）；
    * 包封埋管 / 箱涵 / 管廊：预填软件约定值（a=100、C1=100），参数值仍
      由用户自由编辑；这些类别没有候选列，壁厚仍写在管材行上；
    * 顶管 / 牵引管：只算管材，壁厚按图集写管材行。
    """
    if element.category == CATEGORY_BURIED:
        from app.services.atlas_match import match_atlas_candidates

        # 直埋的壁厚由 match 从候选组写回首根管，这里不再单独补
        match_atlas_candidates(element, commit=False)
        return
    existing = {(param.key, param.unit) for param in element.params}
    for name, value in auto_atlas_params(element).items():
        if value and (name, "mm") not in existing:
            element.params.append(
                ElementParam(key=name, unit="mm", value=format_number(float(value)))
            )
    for pipe_id, t in auto_pipe_thicknesses(element).items():
        target = next((row for row in element.pipes if row.id == pipe_id), None)
        # t 为 0 = 图集没有这一行（如砂基础的小管径），不能当成真实壁厚写进管材行
        if target is not None and target.t is None and t:
            target.t = t


def _pipe_fields(data) -> tuple[str, str, int, str, float | None]:
    """管道输入归一化 → (材质, 管材类别, 管径, 含量, 壁厚)。

    接受三种写法，兼容旧调用与 AI 工具：
    ``(mat, cat, dn, content, t)`` / ``(mat, dn, content, t)`` / ``(mat, dn, content)``；
    没有类别时按材质折算（``core.pipe_category``），没有壁厚记 None（= 按图集）。
    """
    from app.core.pipe_category import normalize_category

    if len(data) >= 5:
        mat, cat, dn, content, t = data[0], data[1], data[2], data[3], data[4]
    elif len(data) == 4:
        mat, dn, content, t = data
        cat = ""
    else:
        mat, dn, content = data
        cat, t = "", None
    text = "" if t is None else str(t).strip()
    return (
        str(mat),
        normalize_category(str(cat or ""), mat=str(mat)),
        int(dn),
        str(content),
        float(text) if text else None,
    )


def _convert_legacy_params(
    category: int,
    legacy_params: list[tuple[str, str]],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str, str]]]:
    """旧 (key, value) 参数 → 新 (key, unit, value) 参数 + 工程量行。

    旧版“类别|项目|单位”三段键变成构筑物工程量行；“-”前缀的构筑物键去前缀；
    其余按 :func:`app.core.param_naming.split_param_key` 拆名称与单位。
    """
    params: list[tuple[str, str, str]] = []
    quantities: list[tuple[str, str, str, str]] = []
    for key, value in legacy_params:
        key = str(key).strip()
        value = str(value).strip()
        if "|" in key:
            category_name, item, unit = key.split("|", 2)
            quantities.append((category_name, item, unit, value))
            continue
        name = key.lstrip("-") if category == CATEGORY_STRUCTURE else key
        name, unit = split_param_key(name)
        params.append((name, unit, value))
    return params, quantities


def create_element(
    unit_id: int,
    category: int = CATEGORY_BURIED,
    name: str = "",
    depth: str = "0",
    amount: str = "0",
    pe_name: str | None = None,
    pf_name: str | None = None,
    pp_name: str | None = None,
    pw_name: str | None = None,
    source: str = "",
    pipes: list[tuple] | None = None,
    params: list[tuple[str, str, str]] | None = None,
    quantities: list[tuple[str, str, str, str]] | None = None,
    order_no: int | None = None,
    seed_atlas_defaults: bool = False,
    atlas_candidates: list[tuple] | None = None,
    pe_left_name: str = "",
    pe_right_name: str = "",
    support_left: bool = True,
    support_right: bool = True,
) -> Element | None:
    """新增构件条目；未指定原则时取库中第一条（旧版 mcElement.GetData 的做法）。

    包封埋管 / 箱涵 / 管廊按旧版构造函数补默认扩展参数（包封宽、净宽、含钢量…），
    各构件再按类别补图集参数行（直埋的工作面加宽 / 垫层厚 / 基础厚，包封 /
    箱涵 / 管廊的工作面加宽 / 垫层厚；空 = 自动按图集，见 param_naming）；
    构筑物（附属构筑物）补名称 / 单位参数与默认工程量行且不带管材。
    ``atlas_candidates`` 为图集候选快照 (con_found, angle, a, C1, C2) 列表
    （构件库插入传资产里的 8 组）；``seed_atlas_defaults=True`` 时直埋构件
    自动匹配候选（候选缺失则现场查图集补），包封 / 箱涵 / 管廊预填软件约定值。
    ``params`` 为 (参数名, 单位, 值) 列表；``quantities`` 为
    (类别, 项目, 单位, 值) 列表；``pipes`` 为 (材质, 类别, 管径, 含量[, 壁厚]) 列表。
    """
    if not project_io.is_open() or not _unit_exists(unit_id):
        return None
    session = orm.session()
    enclosure_names = project_io.enclosure_names()
    foundation_names = project_io.foundation_names()
    precipitation_names = project_io.precipitation_names()
    width_names = project_io.width_names()
    category = int(category)
    element = Element(
        unit_id=unit_id,
        category=category,
        name=name,
        depth=str(depth),
        amount=str(amount),
        pe_name=pe_name if pe_name is not None else (enclosure_names[0] if enclosure_names else ""),
        pf_name=pf_name if pf_name is not None else (foundation_names[0] if foundation_names else ""),
        pp_name=pp_name if pp_name is not None else (precipitation_names[0] if precipitation_names else ""),
        pw_name=pw_name if pw_name is not None else (width_names[0] if width_names else ""),
        source=source,
        pe_left_name=pe_left_name or "",
        pe_right_name=pe_right_name or "",
        support_left=bool(support_left),
        support_right=bool(support_right),
        order_no=order_no
        if order_no is not None
        else project_io.next_order_no(Element, unit_id=unit_id),
    )
    from app.core.calc.engine import _DEFAULT_PARAMS

    if pipes and category != CATEGORY_STRUCTURE:
        if category in SINGLE_PIPE_CATEGORIES and len(pipes) > 1:
            # 直埋 / 非开挖只允许一条管材：多根输入取首根（面宽 / 候选也只认首根）
            pipes = pipes[:1]
        for pipe_data in pipes:
            mat, cat, dn, content, t = _pipe_fields(pipe_data)
            element.pipes.append(
                Pipe(mat=mat, cat=cat, dn=int(dn), content=str(content), t=t)
            )
    if params:
        for key, unit, value in params:
            element.params.append(ElementParam(key=key, unit=unit, value=str(value)))
    elif category == CATEGORY_STRUCTURE:
        for key, unit, value in _STRUCTURE_DEFAULT_PARAMS:
            element.params.append(ElementParam(key=key, unit=unit, value=value))
    else:
        for key, value in _DEFAULT_PARAMS.get(category, {}).items():
            element.params.append(
                ElementParam(key=key, unit=DEFAULT_PARAM_UNITS.get(key, ""), value=format_number(value))
            )
        _append_atlas_rows(element)
    if quantities:
        for order, (quantity_category, item, unit, value) in enumerate(quantities):
            element.quantities.append(
                ElementQuantity(
                    category=quantity_category,
                    item=item,
                    unit=unit,
                    value=str(value),
                    order_no=order,
                )
            )
    elif category == CATEGORY_STRUCTURE:
        element.quantities.append(_structure_default_quantity())
    session.add(element)
    session.flush()
    if atlas_candidates and category == CATEGORY_BURIED:
        from app.core.models.models import ElementAtlasCandidate

        for order, candidate in enumerate(atlas_candidates):
            con_found, angle, *fields = candidate
            # 兼容 5 元组 (con, angle, a, c1, c2) 与 6 元组 (con, angle, t, a, c1, c2)
            if len(fields) == 3:
                t, a, c1, c2 = None, *fields
            else:
                t, a, c1, c2 = fields
            element.atlas_candidates.append(
                ElementAtlasCandidate(
                    con_found=con_found,
                    angle=int(angle),
                    t=t,
                    a=a,
                    c1=c1,
                    c2=c2,
                    order_no=order,
                )
            )
    if seed_atlas_defaults and category != CATEGORY_STRUCTURE:
        _seed_atlas_defaults(element)
    project_io.commit()
    bus().unit_changed.emit(unit_id)
    # 新条目获得焦点：面板选中新行（构件库双击插入、AI 新增共用此行为），
    # 撤销/重做恢复的选中也随之落在每一步新增的条目上
    bus().element_focused.emit(unit_id, element.id)
    return element


def element_snapshot(element_id: int) -> dict | None:
    """构件条目完整快照（复制/剪切/粘贴用，含管材、参数、工程量）。"""
    element = _element(element_id)
    if element is None:
        return None
    return {
        "category": element.category,
        "name": element.name,
        "depth": element.depth,
        "amount": element.amount,
        "pe_name": element.pe_name,
        "pf_name": element.pf_name,
        "pp_name": element.pp_name,
        "pw_name": element.pw_name,
        "source": element.source,
        "pe_left_name": element.pe_left_name or "",
        "pe_right_name": element.pe_right_name or "",
        "support_left": bool(element.support_left),
        "support_right": bool(element.support_right),
        "pipes": [
            (pipe.mat, pipe.pipe_category, pipe.dn, pipe.content, pipe.t)
            for pipe in element.pipes
        ],
        "params": [(param.key, param.unit, param.value) for param in element.params],
        "quantities": [
            (quantity.category, quantity.item, quantity.unit, quantity.value)
            for quantity in element.quantities
        ],
    }


def insert_element_data(
    unit_id: int,
    data: dict,
    before_element_id: int | None = None,
) -> Element | None:
    """把构件数据（模板/剪贴板快照）插入主表格。

    ``before_element_id`` 指定插入到哪一行之前，None 时追加末尾；
    未指定原则时自动挂第一条围护/地基原则（原版构件库双击的做法）。
    """
    if not project_io.is_open() or not _unit_exists(unit_id):
        return None
    order_no = None
    if before_element_id is not None:
        anchor = _element(before_element_id)
        if anchor is not None and anchor.unit_id == unit_id:
            order_no = anchor.order_no
            # 后续行整体后移，给新行腾位（原版 mList.Insert 的等价操作）
            for item in _elements_of(unit_id):
                if item.order_no >= order_no:
                    item.order_no += 1
    return create_element(
        unit_id,
        category=data.get("category", CATEGORY_BURIED),
        name=data.get("name", ""),
        depth=data.get("depth", "0"),
        amount=data.get("amount", "0"),
        pe_name=data.get("pe_name"),
        pf_name=data.get("pf_name"),
        pp_name=data.get("pp_name"),
        pw_name=data.get("pw_name"),
        source=data.get("source", ""),
        pipes=list(data.get("pipes") or []) or None,
        params=list(data.get("params") or []) or None,
        quantities=list(data.get("quantities") or []) or None,
        order_no=order_no,
        seed_atlas_defaults=bool(data.get("seed_atlas_defaults", False)),
        atlas_candidates=list(data.get("atlas_candidates") or []) or None,
        pe_left_name=str(data.get("pe_left_name") or ""),
        pe_right_name=str(data.get("pe_right_name") or ""),
        support_left=bool(data.get("support_left", True)),
        support_right=bool(data.get("support_right", True)),
    )


def _standalone_pe_fields(
    element: Element, plan: dict[int, tuple[bool, bool]]
) -> tuple[str, str, str]:
    """合槽成员还原为组外构件时的 (pe_name, 左原则, 右原则)。

    "-" 是 ``group_side_plan`` 按相邻构件深度算出的不可编辑侧，不看编组
    前的历史选择：两侧都 "-" 取项目围护原则列表第一条；单侧 "-" 取另一
    侧；两侧都不是 "-" 保持左右分设及两侧原值。
    """
    left_active, right_active = plan.get(element.id, (True, True))
    left_name = element.pe_left_name or ""
    right_name = element.pe_right_name or ""
    if not left_active and not right_active:
        names = project_io.enclosure_names()
        return (names[0] if names else ""), "", ""
    if not left_active or not right_active:
        restore = right_name if not left_active else left_name
        if not restore or restore == LR_PE_TEXT:
            names = project_io.enclosure_names()
            restore = names[0] if names else ""
        return restore, "", ""
    return LR_PE_TEXT, left_name, right_name


def element_copy_snapshot(element_id: int) -> dict | None:
    """复制用快照：合槽成员按「在组内的实际围护状态」还原为组外构件。

    "-" 是按相邻构件深度实时算出的不可编辑侧（见 ``group_side_plan``），
    不看成员编组前的历史选择：

    * 两侧都是 "-"：复制后取项目围护原则列表第一条（最左原则）；
    * 单侧是 "-"：复制后取另一侧的原则；
    * 两侧都不是 "-"：保持左右分设，左侧 / 右侧原则与两个支撑勾选
      原样保留。
    """
    data = element_snapshot(element_id)
    if data is None:
        return None
    element = _element(element_id)
    if element is not None and element.group_id is not None:
        plan = group_side_plan(element.group_id)
        pe_name, left_name, right_name = _standalone_pe_fields(element, plan)
        data["pe_name"] = pe_name
        data["pe_left_name"] = left_name
        data["pe_right_name"] = right_name
    return data


def group_snapshot(group_id: int) -> dict | None:
    """合槽组整体快照：父节点名称 / 数量 + 成员完整快照（复制/剪切用）。"""
    group = orm.session().get(TrenchGroup, group_id) if project_io.is_open() else None
    if group is None:
        return None
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    member_data = [data for data in (element_snapshot(member.id) for member in members) if data is not None]
    return {
        "name": group.name,
        "amount": group.amount or _group_amount(group),
        "members": member_data,
    }


def insert_group_data(
    unit_id: int,
    data: dict,
    before_element_id: int | None = None,
) -> TrenchGroup | None:
    """把合槽组快照整组插入主表格（粘贴合槽用），成员保持快照里的左右分设。

    成员逐条插在 ``before_element_id`` 之前（锚点不变，插入顺序即快照顺序），
    随后建父节点并把成员挂进组里。快照成员不足两条时拒绝（合槽至少两条）。
    """
    if not project_io.is_open() or not _unit_exists(unit_id):
        return None
    members_data = [member for member in (data.get("members") or []) if isinstance(member, dict)]
    if len(members_data) < 2:
        return None
    session = orm.session()
    new_ids: list[int] = []
    for member_data in members_data:
        element = insert_element_data(unit_id, member_data, before_element_id)
        if element is not None:
            new_ids.append(element.id)
    if len(new_ids) < 2:
        return None
    group = TrenchGroup(
        unit_id=unit_id,
        name=str(data.get("name") or "合槽组"),
        amount=str(data.get("amount") or ""),
        pe_name="",
        pw_name="",
        order_no=0,
    )
    session.add(group)
    session.flush()
    members = [session.get(Element, element_id) for element_id in new_ids]
    members = [member for member in members if member is not None]
    if not group.amount:
        group.amount = members[0].amount or ""
    for member in members:
        member.group_id = group.id
        member.amount = group.amount
    project_io.commit()
    bus().unit_changed.emit(unit_id)
    return group


def element_id_after_element(element_id: int) -> int | None:
    """按库内 order_no 返回该构件之后的下一条构件 id（末尾为 None）。"""
    element = _element(element_id)
    if element is None:
        return None
    ordered = _elements_of(element.unit_id)
    index = next((i for i, item in enumerate(ordered) if item.id == element_id), None)
    if index is None or index + 1 >= len(ordered):
        return None
    return ordered[index + 1].id


def element_id_after_group(group_id: int) -> int | None:
    """合槽组最后一条成员之后的下一条构件 id（按库内 order_no 查，组在末尾为 None）。

    与界面 ``_element_id_after_group`` 的差别：直接读库，不依赖主表格的
    行缓存——粘贴合槽后表格还没重载，缓存里没有新成员。
    """
    group = orm.session().get(TrenchGroup, group_id) if project_io.is_open() else None
    if group is None or not group.members:
        return None
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    return element_id_after_element(members[-1].id)


def _first_foundation_pair() -> tuple[bool, int]:
    """项目第一条地基原则的 (砼基础开关, 基础角度)；库为空时 (True, 120)。

    构件库插入时构件还没建，先按它取每根管的图集壁厚快照；插入完成后
    :func:`match_atlas_candidates` 会按构件自己的地基原则重新选组。
    """
    from sqlalchemy import select

    from app.core.models.models import PcpFoundation

    pf = orm.session().scalars(
        select(PcpFoundation).order_by(PcpFoundation.order_no, PcpFoundation.id)
    ).first()
    return (bool(pf.con_found), int(pf.found_angle)) if pf is not None else (True, 120)


def insert_element_template(unit_id: int, template, before_element_id: int | None = None) -> Element | None:
    """把构件库模板插入主表格（原版 FormMdi 构件库双击 + FormUnit.Insert）。

    模板参数仍是旧版单键格式，先拆成 (参数名, 单位) + 工程量行。图集值不再
    现场查表：资产里的 8 组快照（砼/非砼 × 90/120/150/180）整组写进候选表
    （含管道壁厚 t），参数值由自动匹配写进参数行；之后换围护原则 / 改类别
    都自动重匹配，候选本身不再自动变。

    旧 .stn 兜底读到的模板没有快照（``template.atlas`` 为空），才退回现场查图集。
    """
    params, quantities = _convert_legacy_params(template.category, list(template.params))
    legacy_quantities = quantities if template.category == CATEGORY_STRUCTURE else []
    con_found, angle = _first_foundation_pair()
    pipes = [
        [pipe.mat, pipe.cat, pipe.dn, pipe.content, pipe.thickness_at(con_found, angle)]
        for pipe in template.pipes
    ]
    # 管道壁厚也进候选：取首根管的 8 组壁厚快照（图集里同一管径各角度壁厚相同，
    # 仍逐组存，便于用户按角度改）
    head_thickness = template.pipes[0].thickness if template.pipes else {}
    candidates = []
    for key, row in template.atlas.items():
        if row is None:
            continue  # 图集该组合没有数据（如砼基础 150°），不留空候选行
        con_found = key.startswith("con")
        angle = int(key[len("con") if con_found else len("plain"):])
        thickness = head_thickness.get(key)
        candidates.append((con_found, angle, thickness, row[0], row[1], row[2]))
    return insert_element_data(
        unit_id,
        {
            "category": template.category,
            "name": template.name,
            "depth": template.depth,
            "amount": template.amount,
            "source": template.source,
            "pipes": pipes,
            "params": [list(param) for param in params],
            "quantities": [list(quantity) for quantity in legacy_quantities],
            "atlas_candidates": candidates,
            # 候选已在（来自资产）→ 直埋走自动匹配选组，不查图集；
            # 旧 .stn 模板无候选 → ensure 现场查图集补
            "seed_atlas_defaults": True,
        },
        before_element_id,
    )


def insert_blank_element(unit_id: int, before_element_id: int | None = None) -> Element | None:
    """插入一条空白构件（程序化入口；界面上的构件只能从构件库双击插入）。

    也补图集快照（seed_atlas_defaults=True）：保证任何入口建出的条目都自带
    图集值，计算侧不再依赖现场查表。
    """
    if not project_io.is_open() or not _unit_exists(unit_id):
        return None
    return insert_element_data(
        unit_id,
        {"name": "新建构件", "depth": "0", "amount": "0", "seed_atlas_defaults": True},
        before_element_id,
    )


def update_element(element_id: int, **fields) -> Element | None:
    """修改构件字段（category / name / depth / amount / pe_name / pf_name 及分设字段）。

    pe_name 的左右分设语义（v3）：选「左右分设」占位即进入分设模式，左右
    原则初始化为当前具体原则名（两列皆空时）；从占位改选具体原则则清空
    左右字段退出分设。``support_left`` / ``support_right`` 存布尔。
    ``pf_name`` 切换会触发图集候选重选（v10 起基础/角度属地基原则）。
    类别改为构筑物时清空管材并重置默认参数与工程量行；从构筑物切回其它
    类别时同样重置；其余类别之间切换时按新类别增删图集参数行。
    """
    element = _element(element_id)
    if element is None:
        return None
    from app.core.calc.engine import _DEFAULT_PARAMS

    category_changed = "category" in fields and int(fields["category"]) != element.category
    old_category = element.category
    if element.group_id is not None:
        # 合槽子节点强制左右分设：不允许通过 pe_name 退回普通模式
        fields.pop("pe_name", None)
        # 合槽子节点数量强制 = 父节点数量（旧数据父节点为空时以本次值补齐）
        if "amount" in fields:
            group = orm.session().get(TrenchGroup, element.group_id)
            if group is not None:
                if not group.amount:
                    group.amount = str(fields["amount"])
                    for member in group.members:
                        member.amount = group.amount
                fields["amount"] = _group_amount(group)
    was_lr = element.pe_name == LR_PE_TEXT
    new_pe_name = str(fields.get("pe_name", element.pe_name or ""))
    if "pe_name" in fields:
        if new_pe_name == LR_PE_TEXT and not was_lr:
            # 进入左右分设：左右原则初始化为当前具体原则（没有则取库中第一条）；
            # 调用方显式给了左右原则（格式刷复制分设格式）时按给定值
            original = element.pe_name if element.pe_name != LR_PE_TEXT else ""
            if not original:
                names = project_io.enclosure_names()
                original = names[0] if names else ""
            fields.setdefault("pe_left_name", original)
            fields.setdefault("pe_right_name", original)
        elif new_pe_name != LR_PE_TEXT and was_lr:
            # 退出左右分设：清空左右字段
            fields["pe_left_name"] = ""
            fields["pe_right_name"] = ""
    for key, value in fields.items():
        if key not in _ELEMENT_FIELDS:
            continue
        if key == "category" or key == "order_no":
            setattr(element, key, int(value))
        elif key in ("support_left", "support_right"):
            setattr(element, key, bool(value) if not isinstance(value, bool) else value)
        else:
            setattr(element, key, str(value))
    if category_changed and element.category == CATEGORY_STRUCTURE:
        # 旧版 mcE7 构造：mList.Clear() + 名称/单位参数 + 默认工程量行（构筑物不带管材）
        for pipe in list(element.pipes):
            element.pipes.remove(pipe)  # delete-orphan 级联删除
        for param in list(element.params):
            element.params.remove(param)
        for key, unit, value in _STRUCTURE_DEFAULT_PARAMS:
            element.params.append(ElementParam(key=key, unit=unit, value=value))
        for quantity in list(element.quantities):
            element.quantities.remove(quantity)
        element.quantities.append(_structure_default_quantity())
    elif category_changed and old_category == CATEGORY_STRUCTURE:
        # 从构筑物切回其它类别：按新类别重置扩展参数（含空值图集行）
        for param in list(element.params):
            element.params.remove(param)
        for quantity in list(element.quantities):
            element.quantities.remove(quantity)
        for key, value in _DEFAULT_PARAMS.get(element.category, {}).items():
            element.params.append(
                ElementParam(key=key, unit=DEFAULT_PARAM_UNITS.get(key, ""), value=format_number(value))
            )
        _append_atlas_rows(element)
    elif category_changed:
        # 直埋 ↔ 包封 / 箱涵 / 管廊 等之间切换：基础厚只属于直埋，按新类别增删
        _reconcile_atlas_rows(element)
        if element.category == CATEGORY_BURIED:
            # 切回直埋：候选若已在（曾切走过）直接重匹配；没有则现场查图集补
            from app.services.atlas_match import match_atlas_candidates

            match_atlas_candidates(element, commit=False)
    elif "pf_name" in fields:
        # 地基原则切换（con_found / 基础角度可能变了；v10 起属地基原则）：
        # 从候选自动重选一组
        if element.category == CATEGORY_BURIED:
            from app.services.atlas_match import match_atlas_candidates

            match_atlas_candidates(element, commit=False)
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return element


def delete_element(element_id: int) -> None:
    element = _element(element_id)
    if element is None:
        return
    unit_id = element.unit_id
    group_id = element.group_id
    group = orm.session().get(TrenchGroup, group_id) if group_id is not None else None
    # 删除前先按当前组内状态取判定口径（与复制到组外同口径）
    plan = group_side_plan(group.id) if group is not None else {}
    siblings = list(group.members) if group is not None else []
    orm.session().delete(element)
    project_io.commit()
    if group is not None:
        # 组员少于 2 条：整组解散（父节点删除、其余组员还原）
        remaining = [member for member in siblings if member.id != element_id]
        if len(remaining) < 2:
            _revert_members(remaining, plan)
            orm.session().delete(group)
            project_io.commit()
    bus().unit_changed.emit(unit_id)


def move_element(element_id: int, delta: int) -> None:
    """上移/下移构件条目。

    合槽组员只在组内移动（上下移 = 组内左右移，不破坏成员连续性）；
    独立构件不移动进组块（相邻是别的组成员时不动）。
    """
    element = _element(element_id)
    if element is None:
        return
    ordered = list(_elements_of(element.unit_id))
    try:
        index = ordered.index(element)
    except ValueError:
        return
    if element.group_id is not None:
        # 组内移动：与相邻的同组成员交换（组边界处不动）
        new_index = index + delta
        if not 0 <= new_index < len(ordered):
            return
        if ordered[new_index].group_id != element.group_id:
            return
        ordered[index], ordered[new_index] = ordered[new_index], ordered[index]
    else:
        new_index = index + delta
        if not 0 <= new_index < len(ordered):
            return
        if ordered[new_index].group_id is not None:
            return  # 不拆组：相邻是组成员时不移动
        ordered[index], ordered[new_index] = ordered[new_index], ordered[index]
    for position, item in enumerate(ordered):
        item.order_no = position
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)


# --------------------------------------------------------------------------- #
# 合槽编组（父节点 / 子节点，见 docs/lr_enclosure_and_trench_group_design.md）
# --------------------------------------------------------------------------- #
#: 可入组的构件类别（不开槽的顶管 / 牵引管与构筑物拒绝）
GROUPABLE_CATEGORIES = (CATEGORY_BURIED, CATEGORY_ENCASED, CATEGORY_BOX_CULVERT, CATEGORY_GALLERY)


def group_elements_error(element_ids: list[int]) -> str | None:
    """编组校验；返回提示文案，None = 允许。"""
    if len(element_ids) < 2:
        return "合槽编组至少选择两条构件。"
    elements = [_element(element_id) for element_id in element_ids]
    if any(element is None for element in elements):
        return "部分构件不存在。"
    unit_ids = {element.unit_id for element in elements}
    if len(unit_ids) > 1:
        return "只能编组同一单位工程内的构件。"
    for element in elements:
        if element.category not in GROUPABLE_CATEGORIES:
            return f"构件「{element.name}」不开槽（顶管 / 牵引管 / 构筑物），不能入组。"
        if element.group_id is not None:
            return f"构件「{element.name}」已在合槽组内。"
    return None


def _original_side_name(element: Element, side: str) -> str:
    """构件编组前的左 / 右围护原则名（普通构件左右同值）。"""
    if side == "left":
        if element.pe_left_name:
            return element.pe_left_name
    elif element.pe_right_name:
        return element.pe_right_name
    return "" if element.pe_name == LR_PE_TEXT else (element.pe_name or "")


def _default_internal_side() -> str:
    """合槽内侧（深侧）围护默认原则：库中围护原则列表的第一条。"""
    names = project_io.enclosure_names()
    return names[0] if names else ""


def create_trench_group(element_ids: list[int]) -> tuple[TrenchGroup | None, str | None]:
    """多选构件「合槽编组」：建父节点 + 组员转为左右分设构件 + 成员移到连续位置。

    父节点不持有围护 / 面宽原则（``pe_name`` / ``pw_name`` 留空，规则 1）；
    组员一律转左右分设（规则 2）：首构件左侧 / 末构件右侧保留各自编组前
    原则（规则 3），其余侧为内侧，默认库中第一条（规则 5，等深时计算强制
    "-"）。挖填 / 基础取侧置"按右侧原则"。返回 (父节点, 错误说明)。
    """
    error = group_elements_error(element_ids)
    if error is not None:
        return None, error
    elements = [_element(element_id) for element_id in element_ids]
    unit_id = elements[0].unit_id
    ordered = list(_elements_of(unit_id))
    # 按当前表单顺序（从上到下 = 从左到右）取组员，整体挪到首成员位置
    members = [element for element in ordered if element.id in set(element_ids)]
    head_position = min(ordered.index(member) for member in members)
    rest = [element for element in ordered if element.id not in set(element_ids)]
    display = rest[:head_position] + members + rest[head_position:]

    group = TrenchGroup(
        unit_id=unit_id,
        name=f"{members[0].name}+{members[1].name} 合槽",
        amount=members[0].amount or "",
        pe_name="",
        pw_name="",
        order_no=0,
    )
    orm.session().add(group)
    orm.session().flush()
    internal = _default_internal_side()
    last_index = len(members) - 1
    for position, element in enumerate(display):
        element.order_no = position
        if element not in members:
            continue
        index = members.index(element)
        element.group_id = group.id
        # 边缘（规则 3）保留编组前原则；内侧默认第一条（规则 5）
        element.pe_left_name = (
            _original_side_name(element, "left")
            if index == 0
            else (internal or _original_side_name(element, "left"))
        )
        element.pe_right_name = (
            _original_side_name(element, "right")
            if index == last_index
            else (internal or _original_side_name(element, "right"))
        )
        element.pe_name = LR_PE_TEXT
        # 数量统一取父节点（首成员的值；组员不单独持有数量）
        element.amount = group.amount
    for index, member in enumerate(members):
        member.order_no = head_position + index
    project_io.commit()
    bus().unit_changed.emit(unit_id)
    bus().tree_structure_changed.emit()
    return group, None


def dissolve_trench_group(group_id: int) -> None:
    """解散合槽组：删除父节点，组员按组内实际围护状态还原为独立构件。"""
    group = orm.session().get(TrenchGroup, group_id) if project_io.is_open() else None
    if group is None:
        return
    unit_id = group.unit_id
    plan = group_side_plan(group.id)
    _revert_members(list(group.members), plan)
    orm.session().delete(group)
    project_io.commit()
    bus().unit_changed.emit(unit_id)
    bus().tree_structure_changed.emit()


def delete_trench_group(group_id: int) -> None:
    """删除合槽组及其全部组员（父节点与子节点一并删除）。"""
    group = orm.session().get(TrenchGroup, group_id) if project_io.is_open() else None
    if group is None:
        return
    unit_id = group.unit_id
    for member in list(group.members):
        orm.session().delete(member)  # 管材 / 参数 / 工程量随 ORM 级联删除
    orm.session().delete(group)
    project_io.commit()
    bus().unit_changed.emit(unit_id)
    bus().tree_structure_changed.emit()


def add_to_group(
    element_id: int,
    group_id: int,
    after_element_id: int | None = None,
) -> tuple[bool, str | None]:
    """把构件加入已有合槽组。

    ``after_element_id`` 指定插到该组员之后（粘贴用，可落在组中间）；
    None 时追加为最右成员（「加入合槽」菜单的原有行为）。两种方式都会
    重排 order_no，保证组员连续。
    """
    element = _element(element_id)
    group = orm.session().get(TrenchGroup, group_id) if project_io.is_open() else None
    if element is None or group is None:
        return False, "构件或合槽组不存在。"
    if element.group_id is not None:
        return False, "构件已在合槽组内。"
    if element.unit_id != group.unit_id:
        return False, "只能加入同一单位工程内的合槽组。"
    if element.category not in GROUPABLE_CATEGORIES:
        return False, "不开槽的构件（顶管 / 牵引管 / 构筑物）不能入组。"
    members = sorted(group.members, key=lambda item: (item.order_no, item.id))
    if not members:
        return False, "合槽组没有成员。"

    ordered = list(_elements_of(element.unit_id))
    display = [item for item in ordered if item.id != element.id]
    if after_element_id is None:
        insert_after = members[-1]
    else:
        insert_after = next(
            (member for member in members if member.id == after_element_id), None
        )
        if insert_after is None:
            return False, "插入位置的合槽成员不存在。"
    position = display.index(insert_after) + 1
    display.insert(position, element)
    for order, item in enumerate(display):
        item.order_no = order
    internal = _default_internal_side()
    right_neighbor = display[position + 1] if position + 1 < len(display) else None
    at_right_edge = right_neighbor is None or right_neighbor.group_id != group.id
    if at_right_edge:
        # 追加为最右成员：原末构件右原则转为内侧，新成员保留右侧原原则
        insert_after.pe_right_name = internal or _original_side_name(insert_after, "right")
        element.pe_right_name = _original_side_name(element, "right")
    else:
        # 插在组中间：新成员两侧都是内侧（规则 5）
        element.pe_right_name = internal or _original_side_name(element, "right")
    element.group_id = group.id
    element.pe_left_name = internal or _original_side_name(element, "left")
    element.pe_name = LR_PE_TEXT
    # 新成员数量强制取父节点数量
    if not group.amount:
        group.amount = members[0].amount or element.amount or ""
        for member in members:
            member.amount = group.amount
    element.amount = group.amount
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return True, None


def remove_from_group(element_id: int) -> None:
    """把构件移出合槽组（还原为独立构件；组员不足 2 条时整组解散）。"""
    element = _element(element_id)
    if element is None or element.group_id is None:
        return
    group = orm.session().get(TrenchGroup, element.group_id)
    unit_id = element.unit_id
    # 按移出前的组内状态判定（与复制到组外同口径）
    plan = group_side_plan(group.id) if group is not None else {}
    remaining = [member for member in (group.members if group else []) if member.id != element.id]
    _revert_members([element], plan)
    if len(remaining) < 2:
        _revert_members(remaining, plan)
        if group is not None:
            orm.session().delete(group)
    project_io.commit()
    bus().unit_changed.emit(unit_id)
    bus().tree_structure_changed.emit()


def _revert_members(
    members: list[Element],
    plan: dict[int, tuple[bool, bool]] | None = None,
) -> None:
    """组员还原为独立构件：按组内实际围护状态决定单原则 / 左右分设。

    与复制到组外的口径一致（:func:`_standalone_pe_fields`）：两侧都是
    "-" 取项目第一条原则，单侧 "-" 取另一侧，两侧都有效则保留左右分设
    及左右原则、支撑勾选。``plan`` 由调用方在改动组员前算好传入，避免
    移除成员后邻接关系变化影响判定。
    """
    if not members:
        return
    if plan is None:
        group = members[0].group
        plan = group_side_plan(group.id) if group is not None else {}
    for member in members:
        pe_name, left_name, right_name = _standalone_pe_fields(member, plan)
        member.pe_name = pe_name
        member.pe_left_name = left_name
        member.pe_right_name = right_name
        member.group_id = None


def group_side_plan(group_id: int) -> dict[int, tuple[bool, bool]]:
    """组内 (左侧可编辑, 右侧可编辑)：界面「围护原则」tab 用。"""
    group = orm.session().get(TrenchGroup, group_id) if project_io.is_open() else None
    if group is None:
        return {}
    from app.core.calc.trench_group import group_side_plan as _plan

    return _plan(group)


def update_group(group_id: int, **fields) -> TrenchGroup | None:
    """修改合槽父节点字段（name / amount / backfill_mode / split_mode）。

    ``amount`` 是合槽的计算长度 L_组：写入父节点后**强制同步全部子构件**
    （子构件不单独持有数量）。``backfill_mode`` / ``split_mode`` 是整槽口径
    选项（回填分层方式 / 断面划分方式），只接受合法枚举值，其它取值忽略。
    """
    group = orm.session().get(TrenchGroup, group_id) if project_io.is_open() else None
    if group is None:
        return None
    for key, value in fields.items():
        if key == "name":
            group.name = str(value)
        elif key == "amount":
            group.amount = str(value)
            for member in group.members:
                member.amount = group.amount
        elif key == "backfill_mode" and value in BACKFILL_MODES:
            group.backfill_mode = str(value)
        elif key == "split_mode" and value in SPLIT_MODES:
            group.split_mode = str(value)
    project_io.commit()
    bus().unit_changed.emit(group.unit_id)
    return group


#: 管材行数固定的类别：直埋 / 顶管 / 牵引管恒为一条管材（不能增删）；
#: 构筑物不带管材（也不能加）。只有包封 / 箱涵 / 管廊可以增删管材行。
SINGLE_PIPE_CATEGORIES = (CATEGORY_BURIED, CATEGORY_JACKING, CATEGORY_PULLING)


def pipe_add_error(element: Element | None) -> str | None:
    """当前构件能否新增管材行；返回提示文案，None = 允许。"""
    if element is None:
        return "请先在上表选择构件条目。"
    if element.category == CATEGORY_STRUCTURE:
        return "附属构筑物不带管材，不能添加管材。"
    if element.category in SINGLE_PIPE_CATEGORIES and element.pipes:
        return "直埋 / 非开挖管道只允许一条管材，不能新增。"
    return None


def pipe_delete_error(element: Element | None) -> str | None:
    """当前构件能否删除管材行；返回提示文案，None = 允许。"""
    if element is None:
        return "请先在上表选择构件条目。"
    if element.category == CATEGORY_STRUCTURE:
        return "附属构筑物不带管材。"
    if element.category in SINGLE_PIPE_CATEGORIES:
        return "直埋 / 非开挖管道只允许一条管材，不能删除。"
    return None


def create_pipe(
    element_id: int,
    mat: str = "Ⅱ级混凝土管",
    dn: int = 600,
    content: str = "1",
    t: float | None = None,
    cat: str = "",
) -> Pipe | None:
    from app.core.pipe_category import normalize_category

    element = _element(element_id)
    if element is None:
        return None
    if pipe_add_error(element) is not None:
        return None
    was_empty = not element.pipes
    pipe = Pipe(
        element_id=element_id,
        mat=mat,
        cat=normalize_category(cat, mat=mat),
        dn=int(dn),
        content=str(content),
        t=t,
    )
    orm.session().add(pipe)
    orm.session().flush()  # 让 element.pipes 看到新管（match 按首根管材质选组）
    if was_empty and element.category == CATEGORY_BURIED:
        # 第一根管决定面宽行 / 候选组：从无到有要自动选一次参数值
        # （此时 ensure 才第一次真正生成候选——空管道时不生成）
        from app.services.atlas_match import match_atlas_candidates

        match_atlas_candidates(element, commit=False)
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(element.unit_id)
    return pipe


def update_pipe(pipe_id: int, **fields) -> Pipe | None:
    from app.core.pipe_category import normalize_category

    pipe = _pipe(pipe_id)
    if pipe is None:
        return None
    for key, value in fields.items():
        if key not in _PIPE_FIELDS:
            continue
        if key == "dn":
            setattr(pipe, key, int(value))
        elif key == "t":
            # 壁厚空 = 自动按图集（None）；数字按用户值存
            text = str(value).strip()
            setattr(pipe, key, float(text) if text else None)
        elif key == "cat":
            # 管材类别收敛成合法枚举（非法 / 空值按材质折算）
            setattr(pipe, key, normalize_category(str(value), mat=pipe.mat))
        else:
            setattr(pipe, key, str(value))
    if "cat" in fields:
        # 类别变化（混凝土 ↔ 非混凝土）会换候选组：直埋构件自动重选参数值
        from app.services.atlas_match import match_atlas_candidates

        match_atlas_candidates(pipe.element, commit=False)
    project_io.commit()
    bus().unit_changed.emit(pipe.element.unit_id)
    return pipe


def delete_pipe(pipe_id: int) -> None:
    pipe = _pipe(pipe_id)
    if pipe is None:
        return
    if pipe_delete_error(pipe.element) is not None:
        return
    element = pipe.element
    was_first = bool(element.pipes) and element.pipes[0].id == pipe.id
    unit_id = element.unit_id
    # 从集合移除（delete-orphan 级联成 DELETE，集合即时同步——match 按
    # 剩余首根管材质选组），再与匹配结果一次 commit 落盘（撤销一个快照）
    element.pipes.remove(pipe)
    if was_first and element.category == CATEGORY_BURIED:
        # 第一根管决定面宽行 / 候选组：删掉它（剩下一根类别不同的管）之后
        # 要自动重选参数值；删到没管时 match 会自己跳过（不误清参数值）
        from app.services.atlas_match import match_atlas_candidates

        match_atlas_candidates(element, commit=False)
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(unit_id)


def create_param(element_id: int, key: str = "", unit: str = "", value: str = "") -> ElementParam | None:
    element = _element(element_id)
    if element is None:
        return None
    if is_atlas_param(key, unit) and not supports_atlas_param(element.category, key, unit):
        return None  # 该类别不显示这一行（由界面提示）
    param = ElementParam(element_id=element_id, key=key, unit=unit, value=value)
    orm.session().add(param)
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(element.unit_id)
    return param


def update_param(param_id: int, **fields) -> ElementParam | None:
    """修改参数行（参数名 / 单位 / 值）；返回 None = 没改。

    改成图集参数行（工作面加宽 / 垫层厚 / 基础厚）的只有该类别显示的
    行允许（直埋三行、包封 / 箱涵 / 管廊的工作面加宽与垫层厚；见
    param_naming.ATLAS_PARAM_CATEGORIES）；其余不写库（写了也不参与计算），
    界面提示后下一次刷新回到原值。
    """
    param = orm.session().get(ElementParam, param_id) if project_io.is_open() else None
    if param is None:
        return None
    element = param.element
    key = str(fields.get("key", param.key))
    unit = str(fields.get("unit", param.unit))
    if is_atlas_param(key, unit) and not supports_atlas_param(element.category, key, unit):
        return None
    for name, value in fields.items():
        if name in _PARAM_FIELDS:
            setattr(param, name, str(value))
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(element.unit_id)
    return param


def _candidate_number(value) -> tuple[bool, float | None]:
    """候选格文本 → (是否合法, 数值)；空文本 = 清空（合法，值 None）。"""
    text = str(value).strip()
    if not text:
        return True, None
    try:
        return True, float(text)
    except ValueError:
        return False, None


def update_atlas_candidate(candidate_id: int, field: str, value) -> bool:
    """改一格候选参数（候选列）；空 = 清回图集无值。

    候选是用户可改的快照；改完立刻按当前围护原则重新自动匹配一次参数值
    （改的可能正是当前匹配的那格）。非数字输入忽略并还原显示。
    """
    from app.core.atlas_candidates import CANDIDATE_FIELDS
    from app.core.models.models import ElementAtlasCandidate
    from app.services.atlas_match import match_atlas_candidates

    row = orm.session().get(ElementAtlasCandidate, int(candidate_id)) if project_io.is_open() else None
    if row is None or field not in CANDIDATE_FIELDS:
        return False
    ok, number = _candidate_number(value)
    if not ok:
        bus().unit_changed.emit(row.element.unit_id)  # 还原显示
        return False
    setattr(row, field, number)
    match_atlas_candidates(row.element, commit=False)
    project_io.commit()
    _expire_element(row.element)
    bus().unit_changed.emit(row.element.unit_id)
    return True


def set_atlas_candidate_value(element_id: int, combo: str, field: str, value) -> bool:
    """写一格候选参数；该组合还没有候选行时**就地建行**（手填补图集缺口）。

    图集没有的组合（如 dn<600 的砂基础 90°、砼基础 150°）在面板上是空格，
    原来既不能选也不能填。这里让用户能直接敲一个值进去：没有行就建一行，
    之后它和别的候选一样参与自动匹配（改完立刻重匹配一次）。
    """
    from app.core.atlas_candidates import CANDIDATE_FIELDS, parse_combo_key
    from app.core.models.models import ElementAtlasCandidate
    from app.services.atlas_match import match_atlas_candidates

    if not project_io.is_open():
        return False
    element = _element(element_id)
    parsed = parse_combo_key(combo)
    if element is None or parsed is None or field not in CANDIDATE_FIELDS:
        return False
    ok, number = _candidate_number(value)
    if not ok:
        bus().unit_changed.emit(element.unit_id)  # 还原显示
        return False

    con_found, angle = parsed
    row = next(
        (
            candidate
            for candidate in element.atlas_candidates
            if bool(candidate.con_found) == con_found and int(candidate.angle) == int(angle)
        ),
        None,
    )
    if row is None:
        if number is None:
            return False  # 空格留空：不必建一行全空候选
        row = ElementAtlasCandidate(
            con_found=con_found,
            angle=int(angle),
            order_no=len(element.atlas_candidates),
        )
        element.atlas_candidates.append(row)
    setattr(row, field, number)
    match_atlas_candidates(element, commit=False)
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(element.unit_id)
    return True


def delete_param(param_id: int) -> str | None:
    """删参数行；该类别显示的图集行与构筑物名称 / 单位行锁定。

    返回提示文案；None 表示已删除。
    """
    param = orm.session().get(ElementParam, param_id) if project_io.is_open() else None
    if param is None:
        return None
    element = param.element
    if element.category == CATEGORY_STRUCTURE:
        if (param.key, param.unit) in ((STRUCTURE_NAME_PARAM, ""), (STRUCTURE_UNIT_PARAM, "")):
            return "名称/单位参数行不可删除。"
    elif is_atlas_param(param.key, param.unit) and supports_atlas_param(
        element.category, param.key, param.unit
    ):
        names = " / ".join(name for name, _unit in atlas_param_rows(element.category))
        return f"{names}为图集参数行，不可删除（清空值即自动）。"
    unit_id = element.unit_id
    orm.session().delete(param)
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(unit_id)
    return None


# --------------------------------------------------------------------------- #
# 构筑物工程量行（详情面板“工程量”页）
# --------------------------------------------------------------------------- #
def create_quantity(
    element_id: int,
    category: str = "构筑物",
    item: str = "",
    unit: str = "",
    value: str = "0",
) -> ElementQuantity | None:
    """新增工程量行（值可为算式，随构件数量放大）。"""
    element = _element(element_id)
    if element is None:
        return None
    order_no = max((existing.order_no for existing in element.quantities), default=-1) + 1
    quantity = ElementQuantity(
        element_id=element_id,
        category=category,
        item=item,
        unit=unit,
        value=str(value),
        order_no=order_no,
    )
    orm.session().add(quantity)
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(element.unit_id)
    return quantity


def update_quantity(quantity_id: int, **fields) -> ElementQuantity | None:
    """修改工程量行（类别 / 项目 / 单位 / 值）。"""
    quantity = orm.session().get(ElementQuantity, quantity_id) if project_io.is_open() else None
    if quantity is None:
        return None
    for key, value in fields.items():
        if key in _QUANTITY_FIELDS:
            setattr(quantity, key, str(value))
    project_io.commit()
    bus().unit_changed.emit(quantity.element.unit_id)
    return quantity


def delete_quantity(quantity_id: int) -> None:
    quantity = orm.session().get(ElementQuantity, quantity_id) if project_io.is_open() else None
    if quantity is None:
        return
    element = quantity.element
    unit_id = element.unit_id
    orm.session().delete(quantity)
    project_io.commit()
    _expire_element(element)
    bus().unit_changed.emit(unit_id)


# --------------------------------------------------------------------------- #
# 视图模型
# --------------------------------------------------------------------------- #
class UnitViewModel(QObject):
    unit_loaded = Signal(int, object)  # unit_id, list[ElementRow]
    # element_id, list[PipeRow], list[ParamRow], list[QuantityRow]
    detail_loaded = Signal(int, object, object, object)
    error_occurred = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._unit_id: int | None = None
        self._element_id: int | None = None
        bus().unit_changed.connect(self._on_unit_changed)

    # --- 状态 ---
    def unit_id(self) -> int | None:
        return self._unit_id

    def element_id(self) -> int | None:
        return self._element_id

    # --- 加载 ---
    def load_unit(self, unit_id: int | None) -> None:
        if unit_id != self._unit_id:
            self._element_id = None
        self._unit_id = unit_id
        if unit_id is None:
            self.unit_loaded.emit(0, [])
            self.detail_loaded.emit(0, [], [], [])
            return
        self.unit_loaded.emit(unit_id, table_rows(unit_id))

    def load_detail(self, element_id: int | None) -> None:
        self._element_id = element_id
        if element_id is None:
            self.detail_loaded.emit(0, [], [], [])
            return
        self.detail_loaded.emit(
            element_id, pipe_rows(element_id), param_rows(element_id), quantity_rows(element_id)
        )

    def clear_detail(self) -> None:
        """明细区切到合槽父行 / 多选 / 空态：清掉明细目标（不发信号）。

        合槽父行、多选和空态都没有具体构件，若继续保留上一个构件的 id，
        之后任何一次整表重载（如改合槽父节点数量）都会在 ``unit_loaded``
        之后补发那份过期明细，把下方面板刷成上一个构件的内容。
        """
        self._element_id = None

    def _on_unit_changed(self, unit_id: int) -> None:
        """任何来源（界面 / AI 工具）改了构件都重新加载当前单位工程。

        延后到事件循环再刷新：本槽可能是在表格 itemChanged 里被同步触发的，
        此时重建表格行会把正在处理的单元格删掉。
        """
        if self._unit_id is None or unit_id != self._unit_id:
            return
        QTimer.singleShot(0, self._refresh)

    def _refresh(self) -> None:
        if self._unit_id is None:
            return
        self.unit_loaded.emit(self._unit_id, table_rows(self._unit_id))
        if self._element_id is not None:
            self.detail_loaded.emit(
                self._element_id,
                pipe_rows(self._element_id),
                param_rows(self._element_id),
                quantity_rows(self._element_id),
            )

    # --- 构件操作 ---
    def set_element_field(self, element_id: int, field: str, value) -> None:
        update_element(element_id, **{field: value})

    def remove_element(self, element_id: int) -> None:
        if element_id == self._element_id:
            self._element_id = None
        delete_element(element_id)

    def move_element(self, element_id: int, delta: int) -> None:
        move_element(element_id, delta)

    # --- 合槽编组 / 左右分设 ---
    def create_group(self, element_ids: list[int]) -> tuple[object, str | None]:
        """多选构件编组；错误说明经 error_occurred 展示。"""
        group, error = create_trench_group(element_ids)
        if error is not None:
            self.error_occurred.emit(error)
        return group, error

    def dissolve_group(self, group_id: int) -> None:
        dissolve_trench_group(group_id)

    def add_to_group(self, element_id: int, group_id: int) -> None:
        _ok, error = add_to_group(element_id, group_id)
        if error is not None:
            self.error_occurred.emit(error)

    def remove_from_group(self, element_id: int) -> None:
        remove_from_group(element_id)

    def set_group_field(self, group_id: int, field: str, value) -> None:
        update_group(group_id, **{field: value})

    # --- 明细操作 ---
    def add_pipe(self) -> None:
        element = _element(self._element_id) if self._element_id is not None else None
        message = pipe_add_error(element)
        if message:
            self.error_occurred.emit(message)
            return
        create_pipe(self._element_id)

    def set_pipe_field(self, pipe_id: int, field: str, value) -> None:
        update_pipe(pipe_id, **{field: value})

    def remove_pipe(self, pipe_id: int) -> None:
        pipe = _pipe(pipe_id)
        message = pipe_delete_error(pipe.element if pipe is not None else None)
        if message:
            self.error_occurred.emit(message)
            return
        delete_pipe(pipe_id)

    def set_param_field(self, param_id: int, field: str, value) -> None:
        if update_param(param_id, **{field: value}) is None:
            self.error_occurred.emit(_ATLAS_PARAM_LOCKED_HINT)

    def update_atlas_candidate(self, candidate_id: int, field: str, value) -> None:
        """改一格候选参数（候选列）；改完自动重匹配当前构件的参数值。"""
        if not update_atlas_candidate(candidate_id, field, value):
            self.error_occurred.emit("候选参数行不存在。")

    def set_atlas_candidate_value(
        self, element_id: int, combo: str, field: str, value
    ) -> None:
        """手填补空白候选格；该组合没有候选行时自动建行。"""
        if not set_atlas_candidate_value(element_id, combo, field, value):
            self.error_occurred.emit("候选参数需为数字（可留空）。")

    # --- 工程量行（构筑物） ---
    def add_quantity(self) -> None:
        if self._element_id is None:
            self.error_occurred.emit("请先在上表选择构件条目。")
            return
        create_quantity(self._element_id)

    def set_quantity_field(self, quantity_id: int, field: str, value) -> None:
        update_quantity(quantity_id, **{field: value})

    def remove_quantity(self, quantity_id: int) -> None:
        delete_quantity(quantity_id)


# --------------------------------------------------------------------------- #
# 内部
# --------------------------------------------------------------------------- #
def _elements_of(unit_id: int):
    from sqlalchemy import select

    return list(
        orm.session().scalars(
            select(Element).where(Element.unit_id == unit_id).order_by(Element.order_no, Element.id)
        )
    )


def _unit_exists(unit_id: int) -> bool:
    from app.core.models.models import Unit

    return orm.session().get(Unit, unit_id) is not None


def _element(element_id: int) -> Element | None:
    if not project_io.is_open():
        return None
    return orm.session().get(Element, element_id)


def _pipe(pipe_id: int) -> Pipe | None:
    if not project_io.is_open():
        return None
    return orm.session().get(Pipe, pipe_id)
