"""单位工程面板视图模型（计划 §7.2）。

中部下半区：构件录入表（埋深 / 数量支持算式）+ 选中构件的明细（管材、构件参数）。
埋深、数量在库里存字符串原文，展示时用 core.evaluator 求值，失败不写 0 而是标出错误。

构件/管道/参数的数据操作写成模块级函数（create_element / update_element / …）：
界面用它们，M8 的 AI 工具也用它们，保持一条代码路径。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.evaluator import EvalError, evaluate, format_number
from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import (
    CATEGORY_BURIED,
    CATEGORY_STRUCTURE,
    MULTI_PE_TEXT,
    MULTI_PF_TEXT,
    Element,
    ElementParam,
    ElementPrinciple,
    Pipe,
    unit_of,
)
from app.services import project_io

_ELEMENT_FIELDS = {"category", "name", "depth", "amount", "pe_name", "pf_name", "source", "order_no"}
_PIPE_FIELDS = {"mat", "dn", "content"}
_PARAM_FIELDS = {"key", "value"}


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


@dataclass
class PipeRow:
    id: int
    mat: str
    dn: int
    content: str


@dataclass
class ParamRow:
    id: int
    key: str
    value: str


@dataclass
class PrincipleRefRow:
    """多原则引用行（旧版 dGVPE / dGVPF 的一行）。"""

    id: int
    name: str
    ratio: float
    order_no: int
    is_main: bool = False


def _evaluate_field(text: str) -> tuple[float, str]:
    """返回 (值, 错误信息)；错误信息非空表示该格算式不合法。"""
    try:
        return evaluate(text), ""
    except EvalError as error:
        return 0.0, str(error)


def element_rows(unit_id: int) -> list[ElementRow]:
    """读取某单位工程的构件列表（含算式求值结果）。"""
    if not project_io.is_open():
        return []
    rows: list[ElementRow] = []
    for element in _elements_of(unit_id):
        row = _element_row(element)
        row.spec = _element_spec(element)
        rows.append(row)
    return rows


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
    return [PipeRow(id=pipe.id, mat=pipe.mat, dn=pipe.dn, content=pipe.content) for pipe in element.pipes]


def param_rows(element_id: int) -> list[ParamRow]:
    element = _element(element_id)
    if element is None:
        return []
    return [
        ParamRow(id=param.id, key=param.key, value=param.value)
        for param in element.params
    ]


def compute_unit(unit_id: int):
    """计算整个单位工程（M4）。

    返回 ``(定额汇总 QDict, [(构件行, 该构件的 QDict)])``；构件计算失败
    （数量为 0 / 原则缺失 / 覆土不足）时其 QDict 为空字典并在行上带错误说明。
    多原则引用（旧版 PEname 字典）按 pe×pf 组合与比例在引擎里合并。
    """
    from app.core.calc.engine import (
        build_element_input,
        compute_element,
        resolve_element_principles,
    )
    from app.core.calc.tracer import QDict
    from app.core.models.models import PcpEnclosure, PcpFoundation

    summary = QDict()
    detail: list[tuple[ElementRow, QDict]] = []
    if not project_io.is_open():
        return summary, detail
    session = orm.session()
    for element in _elements_of(unit_id):
        row = _element_row(element)
        pe, pf, pe_refs, pf_refs = resolve_element_principles(element, session)
        info = build_element_input(element, pe, pf, pe_refs, pf_refs)
        row.spec = info.spec()
        try:
            result = compute_element(info) or QDict()
            if element.category == CATEGORY_STRUCTURE and not result:
                row.error = "数量为 0，未生成工程量。"
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
        # 旧版 mcElement.Unit getter：Param 里的“-单位”覆盖默认单位（座/个/套…）
        for param in element.params:
            if param.key == "-单位" and param.value.strip():
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
        order_no=element.order_no,
        unit=unit,
        depth_value=depth_value,
        amount_value=amount_value,
        depth_error=depth_error,
        amount_error=amount_error,
        source=element.source,
    )


# --------------------------------------------------------------------------- #
# 数据操作（界面与 AI 工具共用）
# --------------------------------------------------------------------------- #
_STRUCTURE_DEFAULT_PARAMS = (
    ("-名称", "自定义构筑物"),
    ("-单位", "个"),
)


def create_element(
    unit_id: int,
    category: int = CATEGORY_BURIED,
    name: str = "",
    depth: str = "0",
    amount: str = "0",
    pe_name: str | None = None,
    pf_name: str | None = None,
    source: str = "",
    pipes: list[tuple[str, int, str]] | None = None,
    params: list[tuple[str, str]] | None = None,
    order_no: int | None = None,
    pe_refs: list[tuple[str, float]] | None = None,
    pf_refs: list[tuple[str, float]] | None = None,
    main_pe_name: str = "",
) -> Element | None:
    """新增构件条目；未指定原则时取库中第一条（旧版 mcElement.GetData 的做法）。

    包封埋管 / 箱涵 / 管廊按旧版构造函数补默认扩展参数（包封宽、净宽、含钢量…）；
    构筑物（附属构筑物）补“-名称/-单位”两个默认参数且不带管材；
    ``pe_refs`` / ``pf_refs`` 传入多原则引用（旧版 PEname / PFname 字典，
    多于一条时 show 名自动记为“多围护原则”/“多地基原则”）。
    """
    if not project_io.is_open() or not _unit_exists(unit_id):
        return None
    session = orm.session()
    enclosure_names = project_io.enclosure_names()
    foundation_names = project_io.foundation_names()
    category = int(category)
    element = Element(
        unit_id=unit_id,
        category=category,
        name=name,
        depth=str(depth),
        amount=str(amount),
        pe_name=pe_name if pe_name is not None else (enclosure_names[0] if enclosure_names else ""),
        pf_name=pf_name if pf_name is not None else (foundation_names[0] if foundation_names else ""),
        main_pe_name=main_pe_name,
        source=source,
        order_no=order_no
        if order_no is not None
        else project_io.next_order_no(Element, unit_id=unit_id),
    )
    from app.core.calc.engine import _DEFAULT_PARAMS

    if pipes and category != CATEGORY_STRUCTURE:
        for mat, dn, content in pipes:
            element.pipes.append(Pipe(mat=mat, dn=int(dn), content=str(content)))
    if params:
        for key, value in params:
            element.params.append(ElementParam(key=key, value=str(value)))
    elif category == CATEGORY_STRUCTURE:
        for key, value in _STRUCTURE_DEFAULT_PARAMS:
            element.params.append(ElementParam(key=key, value=value))
    else:
        for key, value in _DEFAULT_PARAMS.get(category, {}).items():
            element.params.append(ElementParam(key=key, value=format_number(value)))
    session.add(element)
    session.flush()
    _seed_principle_refs(session, element, pe_refs, pf_refs)
    project_io.commit()
    bus().unit_changed.emit(unit_id)
    return element


def _seed_principle_refs(
    session,
    element: Element,
    pe_refs: list[tuple[str, float]] | None,
    pf_refs: list[tuple[str, float]] | None,
) -> None:
    """写入多原则引用行并按旧版 setter 语义同步 show 名 / 主原则。"""
    if pe_refs is None:
        pe_refs = [(element.pe_name, 1.0)] if element.pe_name else []
    if pf_refs is None:
        pf_refs = [(element.pf_name, 1.0)] if element.pf_name else []
    for order, (ref_name, ratio) in enumerate(pe_refs):
        element.principle_refs.append(
            ElementPrinciple(kind="pe", name=ref_name, ratio=float(ratio), order_no=order)
        )
    for order, (ref_name, ratio) in enumerate(pf_refs):
        element.principle_refs.append(
            ElementPrinciple(kind="pf", name=ref_name, ratio=float(ratio), order_no=order)
        )
    if len(pe_refs) > 1:
        element.pe_name = MULTI_PE_TEXT
        if not element.main_pe_name or element.main_pe_name == MULTI_PE_TEXT:
            element.main_pe_name = pe_refs[0][0]
    elif pe_refs:
        element.pe_name = pe_refs[0][0]
        element.main_pe_name = element.pe_name
    if len(pf_refs) > 1:
        element.pf_name = MULTI_PF_TEXT
    elif pf_refs:
        element.pf_name = pf_refs[0][0]


def element_snapshot(element_id: int) -> dict | None:
    """构件条目完整快照（复制/剪切/粘贴用，含管材、参数与多原则引用）。"""
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
        "main_pe_name": element.main_pe_name,
        "source": element.source,
        "pipes": [(pipe.mat, pipe.dn, pipe.content) for pipe in element.pipes],
        "params": [(param.key, param.value) for param in element.params],
        "pe_refs": [(ref.name, ref.ratio) for ref in element.pe_refs_sorted()],
        "pf_refs": [(ref.name, ref.ratio) for ref in element.pf_refs_sorted()],
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
    pe_refs = data.get("pe_refs") or None
    if pe_refs is None:
        pe_name = data.get("pe_name")
        pe_refs = [(pe_name, 1.0)] if pe_name and pe_name != MULTI_PE_TEXT else None
    pf_refs = data.get("pf_refs") or None
    if pf_refs is None:
        pf_name = data.get("pf_name")
        pf_refs = [(pf_name, 1.0)] if pf_name and pf_name != MULTI_PF_TEXT else None
    return create_element(
        unit_id,
        category=data.get("category", CATEGORY_BURIED),
        name=data.get("name", ""),
        depth=data.get("depth", "0"),
        amount=data.get("amount", "0"),
        source=data.get("source", ""),
        pipes=list(data.get("pipes") or []) or None,
        params=list(data.get("params") or []) or None,
        order_no=order_no,
        pe_refs=pe_refs,
        pf_refs=pf_refs,
        main_pe_name=data.get("main_pe_name", "") or "",
    )


def insert_element_template(unit_id: int, template, before_element_id: int | None = None) -> Element | None:
    """把构件库模板插入主表格（原版 FormMdi 构件库双击 + FormUnit.Insert）。"""
    return insert_element_data(
        unit_id,
        {
            "category": template.category,
            "name": template.name,
            "depth": template.depth,
            "amount": template.amount,
            "source": template.source,
            "pipes": [list(pipe) for pipe in template.pipes],
            "params": [list(param) for param in template.params],
        },
        before_element_id,
    )


def insert_blank_element(unit_id: int, before_element_id: int | None = None) -> Element | None:
    """插入一条空白构件（主表格 Insert 键 / “新增构件条目”按钮）。"""
    if not project_io.is_open() or not _unit_exists(unit_id):
        return None
    return insert_element_data(unit_id, {"name": "新建构件", "depth": "0", "amount": "0"}, before_element_id)


def update_element(element_id: int, **fields) -> Element | None:
    """修改构件字段（category / name / depth / amount / pe_name / pf_name）。

    pe_name / pf_name 按旧版 showPEname / showPFname setter 语义处理：
    选“多围护原则/多地基原则”只切换显示名、保留引用行；选具体原则则把
    引用重置为该原则（比例 1）。类别改为构筑物时清空管材并重置默认参数。
    """
    element = _element(element_id)
    if element is None:
        return None
    category_changed = "category" in fields and int(fields["category"]) != element.category
    for key, value in fields.items():
        if key not in _ELEMENT_FIELDS:
            continue
        if key == "pe_name":
            _apply_show_name(element, "pe", str(value))
            continue
        if key == "pf_name":
            _apply_show_name(element, "pf", str(value))
            continue
        setattr(element, key, int(value) if key in ("category", "order_no") else str(value))
    if category_changed and element.category == CATEGORY_STRUCTURE:
        # 旧版 mcE7 构造：mList.Clear() + 默认参数（构筑物不带管材）
        element.main_pe_name = element.main_pe_name or element.pe_name
        for pipe in list(element.pipes):
            element.pipes.remove(pipe)  # delete-orphan 级联删除
        for param in list(element.params):
            element.params.remove(param)
        for key, value in _STRUCTURE_DEFAULT_PARAMS:
            element.params.append(ElementParam(key=key, value=value))
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return element


def _apply_show_name(element: Element, kind: str, value: str) -> None:
    """旧版 showPEname / showPFname setter：具体原则重置引用为 1 条，多原则只改显示名。"""
    multi_text = MULTI_PE_TEXT if kind == "pe" else MULTI_PF_TEXT
    refs = element.pe_refs_sorted() if kind == "pe" else element.pf_refs_sorted()
    if value == multi_text:
        # 切到多原则：引用行原样保留；主原则失效时回落到第一条引用
        if kind == "pe":
            element.pe_name = value
            ref_names = [ref.name for ref in refs]
            if element.main_pe_name not in ref_names:
                element.main_pe_name = ref_names[0] if ref_names else ""
        else:
            element.pf_name = value
        return
    # 切到具体原则：引用重置为该原则（旧版 PEname.Clear() + Add(name, 1)）
    for ref in refs:
        element.principle_refs.remove(ref)  # delete-orphan 级联删除
    element.principle_refs.append(
        ElementPrinciple(kind=kind, name=value, ratio=1.0, order_no=0)
    )
    if kind == "pe":
        element.pe_name = value
        element.main_pe_name = value
    else:
        element.pf_name = value


def delete_element(element_id: int) -> None:
    element = _element(element_id)
    if element is None:
        return
    unit_id = element.unit_id
    orm.session().delete(element)
    project_io.commit()
    bus().unit_changed.emit(unit_id)


def move_element(element_id: int, delta: int) -> None:
    """上移/下移构件条目。"""
    element = _element(element_id)
    if element is None:
        return
    ordered = list(_elements_of(element.unit_id))
    try:
        index = ordered.index(element)
    except ValueError:
        return
    new_index = index + delta
    if new_index < 0 or new_index >= len(ordered):
        return
    ordered[index], ordered[new_index] = ordered[new_index], ordered[index]
    for position, item in enumerate(ordered):
        item.order_no = position
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)


def create_pipe(element_id: int, mat: str = "Ⅱ级混凝土管", dn: int = 600, content: str = "1") -> Pipe | None:
    element = _element(element_id)
    if element is None:
        return None
    pipe = Pipe(element_id=element_id, mat=mat, dn=int(dn), content=str(content))
    orm.session().add(pipe)
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return pipe


def update_pipe(pipe_id: int, **fields) -> Pipe | None:
    pipe = _pipe(pipe_id)
    if pipe is None:
        return None
    for key, value in fields.items():
        if key not in _PIPE_FIELDS:
            continue
        setattr(pipe, key, int(value) if key == "dn" else str(value))
    project_io.commit()
    bus().unit_changed.emit(pipe.element.unit_id)
    return pipe


def delete_pipe(pipe_id: int) -> None:
    pipe = _pipe(pipe_id)
    if pipe is None:
        return
    unit_id = pipe.element.unit_id
    orm.session().delete(pipe)
    project_io.commit()
    bus().unit_changed.emit(unit_id)


def create_param(element_id: int, key: str = "", value: str = "") -> ElementParam | None:
    element = _element(element_id)
    if element is None:
        return None
    param = ElementParam(element_id=element_id, key=key, value=value)
    orm.session().add(param)
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return param


def update_param(param_id: int, **fields) -> ElementParam | None:
    param = orm.session().get(ElementParam, param_id) if project_io.is_open() else None
    if param is None:
        return None
    for key, value in fields.items():
        if key in _PARAM_FIELDS:
            setattr(param, key, str(value))
    project_io.commit()
    bus().unit_changed.emit(param.element.unit_id)
    return param


def delete_param(param_id: int) -> None:
    param = orm.session().get(ElementParam, param_id) if project_io.is_open() else None
    if param is None:
        return
    unit_id = param.element.unit_id
    orm.session().delete(param)
    project_io.commit()
    bus().unit_changed.emit(unit_id)


# --------------------------------------------------------------------------- #
# 多原则引用（旧版 FormUnit 的 dGVPE / dGVPF 子表）
# --------------------------------------------------------------------------- #
def principle_ref_rows(element_id: int, kind: str) -> list[PrincipleRefRow]:
    """读取某构件的多原则引用（kind = "pe" / "pf"）。"""
    element = _element(element_id)
    if element is None:
        return []
    refs = element.pe_refs_sorted() if kind == "pe" else element.pf_refs_sorted()
    return [
        PrincipleRefRow(
            id=ref.id,
            name=ref.name,
            ratio=ref.ratio,
            order_no=ref.order_no,
            is_main=(kind == "pe" and ref.name == element.main_pe_name),
        )
        for ref in refs
    ]


def add_principle_ref(element_id: int, kind: str, name: str, ratio: float = 1.0) -> ElementPrinciple | None:
    """新增一条引用（旧版 dGVPE 允许追加行）。重名时返回 None 由界面提示。"""
    element = _element(element_id)
    if element is None or not name:
        return None
    existing = element.pe_refs_sorted() if kind == "pe" else element.pf_refs_sorted()
    if any(ref.name == name for ref in existing):
        return None
    ref = ElementPrinciple(
        kind=kind,
        name=name,
        ratio=float(ratio),
        order_no=(existing[-1].order_no + 1) if existing else 0,
    )
    element.principle_refs.append(ref)
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return ref


def update_principle_ref(ref_id: int, *, name: str | None = None, ratio: float | None = None) -> ElementPrinciple | None:
    """修改引用的原则名 / 比例（旧版 dGVPE CellEndEdit）。"""
    ref = orm.session().get(ElementPrinciple, ref_id) if project_io.is_open() else None
    if ref is None:
        return None
    element = ref.element
    if name is not None and name != ref.name:
        siblings = element.pe_refs_sorted() if ref.kind == "pe" else element.pf_refs_sorted()
        if any(other.name == name for other in siblings if other.id != ref.id):
            return None  # 旧版 CellValidating：“原则已存在于列表中。”
        ref.name = name
        if ref.kind == "pe":
            ref_names = [row.name for row in element.pe_refs_sorted()]
            if element.main_pe_name not in ref_names:
                element.main_pe_name = ref_names[0] if ref_names else ""
    if ratio is not None:
        ref.ratio = float(ratio)
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return ref


def remove_principle_ref(ref_id: int) -> str | None:
    """删除引用（旧版 dGVPE_KeyUp Delete）；全部删光时返回提示文案。"""
    ref = orm.session().get(ElementPrinciple, ref_id) if project_io.is_open() else None
    if ref is None:
        return None
    element = ref.element
    refs = element.pe_refs_sorted() if ref.kind == "pe" else element.pf_refs_sorted()
    if len(refs) <= 1:
        return "至少需要一种围护原则。" if ref.kind == "pe" else "至少需要一种地基处理原则。"
    if ref.kind == "pe" and element.main_pe_name == ref.name:
        remaining = [row.name for row in refs if row.id != ref.id]
        element.main_pe_name = remaining[0] if remaining else ""
    # 从集合移除（delete-orphan 级联成 DELETE），保证内存集合同步
    element.principle_refs.remove(ref)
    project_io.commit()
    bus().unit_changed.emit(element.unit_id)
    return None


def set_main_pe(element_id: int, name: str) -> Element | None:
    """设置多围护原则下的主要围护原则（旧版 cmbBoxMainPE_DropDownClosed）。"""
    element = _element(element_id)
    if element is None:
        return None
    ref_names = [ref.name for ref in element.pe_refs_sorted()]
    if name and name in ref_names:
        element.main_pe_name = name
        project_io.commit()
        bus().unit_changed.emit(element.unit_id)
    return element


# --------------------------------------------------------------------------- #
# 视图模型
# --------------------------------------------------------------------------- #
class UnitViewModel(QObject):
    unit_loaded = Signal(int, object)  # unit_id, list[ElementRow]
    detail_loaded = Signal(int, object, object)  # element_id, list[PipeRow], list[ParamRow]
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
            self.detail_loaded.emit(0, [], [])
            return
        self.unit_loaded.emit(unit_id, element_rows(unit_id))

    def load_detail(self, element_id: int | None) -> None:
        self._element_id = element_id
        if element_id is None:
            self.detail_loaded.emit(0, [], [])
            return
        self.detail_loaded.emit(element_id, pipe_rows(element_id), param_rows(element_id))

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
        self.unit_loaded.emit(self._unit_id, element_rows(self._unit_id))
        if self._element_id is not None:
            self.detail_loaded.emit(
                self._element_id, pipe_rows(self._element_id), param_rows(self._element_id)
            )

    # --- 构件操作 ---
    def add_element(self, category: int = CATEGORY_BURIED, name: str = "新建构件") -> None:
        if self._unit_id is None:
            self.error_occurred.emit("请先在左侧选择单位工程。")
            return
        element = create_element(self._unit_id, category=category, name=name)
        if element is not None:
            self._element_id = element.id
            self.load_detail(element.id)

    def set_element_field(self, element_id: int, field: str, value) -> None:
        update_element(element_id, **{field: value})

    def remove_element(self, element_id: int) -> None:
        if element_id == self._element_id:
            self._element_id = None
        delete_element(element_id)

    def move_element(self, element_id: int, delta: int) -> None:
        move_element(element_id, delta)

    # --- 明细操作 ---
    def add_pipe(self) -> None:
        if self._element_id is None:
            self.error_occurred.emit("请先在上表选择构件条目。")
            return
        create_pipe(self._element_id)

    def set_pipe_field(self, pipe_id: int, field: str, value) -> None:
        update_pipe(pipe_id, **{field: value})

    def remove_pipe(self, pipe_id: int) -> None:
        delete_pipe(pipe_id)

    def add_param(self) -> None:
        if self._element_id is None:
            self.error_occurred.emit("请先在上表选择构件条目。")
            return
        create_param(self._element_id)

    def set_param_field(self, param_id: int, field: str, value) -> None:
        update_param(param_id, **{field: value})

    def remove_param(self, param_id: int) -> None:
        delete_param(param_id)


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
