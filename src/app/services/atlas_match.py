"""图集候选参数的补齐与自动匹配（v9）。

候选参数（"候选参数列"）是构件库资产的一次性快照，存在
``element_atlas_candidate`` 表，允许用户改、**永不自动改写**；参数值
（工作面加宽 / 垫层厚 / 基础厚三行参数）按当前地基原则的
``con_found + found_angle`` 从候选里自动选组写进来。

自动匹配的触发点（都在数据改动处调用 :func:`match_atlas_candidates`）：

* 构件库插入条目 / AI 新增 / 空白新增（候选缺失时现场查图集补一次）；
* 构件的围护或地基原则切换（``update_element``）；
* 地基原则本身修改（``principle_edit.apply_foundation`` →
  :func:`match_for_foundation`，对引用该原则的直埋构件逐条重匹配）；
* 管材类别修改（``update_pipe``，混凝土 ↔ 非混凝土会换候选组）；
* 候选格被手改（``update_atlas_candidate``）。

每次触发都按"同组精确 → 同组就近 → 跨组精确 → 跨组就近"整组重算；四级
都不命中就把参数行清空。任何情况下都不保留上一次匹配的旧值。

独立成 services 层模块：``principle_edit``（services）与 ``unit_vm``
（viewmodels）都要用，避免 viewmodels 反向依赖。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.atlas_candidates import CANDIDATE_ANGLES, combo_key, select_candidate
from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import (
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    Element,
    ElementAtlasCandidate,
    ElementParam,
    PcpEnclosure,
    PcpFoundation,
)
from app.core.param_naming import (
    PARAM_A_NAME,
    PARAM_C1_NAME,
    PARAM_C2_NAME,
    PARAM_T_NAME,
    atlas_param_rows,
)
from app.core.evaluator import format_number
from app.services import project_io


def _principles(element: Element):
    """围护 / 地基 / 面宽原则（同引擎：按引用名解析，失效取第一条）。"""
    from app.core.calc.engine import resolve_element_principles

    pe, pf, _pp, pw = resolve_element_principles(element, orm.session())
    return pe, pf, pw


def _bare_query(element: Element, pe: PcpEnclosure, pf: PcpFoundation, pw):
    """强制查表的图集查询：清掉参数覆盖值、管道壁厚留空（否则命中快照短路）。

    ``strict_angle=True``：图集没有该角度的行时按"无数据"记空，不把兜底就
    近值（如砼基础 150° 会落到 120/180）当成该角度的快照存下来。
    """
    from app.core.calc.engine import build_atlas_query, build_element_input
    from app.services.atlas import PipeSpec

    info = build_element_input(element, pe, pf)
    query = build_atlas_query(info, pf, pw)
    query.a = query.c1 = query.c2 = None
    query.pipes = [type(p)(mat=p.mat, dn=p.dn, cat=p.cat) for p in info.pipes]
    query.strict_angle = True
    return query


def _match_con_found(element: Element, pf: PcpFoundation) -> bool:
    """参与匹配的砼基础开关（取地基原则 ``pf.con_found``）。

    非混凝土管（金属 / 化学建材）的图集查表不看砼基础开关，界面也只给
    "不采用混凝土基础"的 4 列（见 ``atlas_candidates.columns_for``）。匹配
    跟着显示组走 ``False``：否则会选中界面根本不显示的 con 组，参数值虽
    相同，但高亮的那一格和用户能改的那一格对不上。
    """
    from app.core.pipe_category import is_concrete

    if not element.pipes:
        return bool(pf.con_found)
    pipe = element.pipes[0]
    return bool(pf.con_found) if is_concrete(pipe.cat, mat=pipe.mat) else False


def _has_pipes(element: Element) -> bool:
    """构件是否有管材行。

    ``element.pipes`` 可能是本次改动前缓存的空集合（新建构件后刚插入第一根
    管，关系还没过期），直接读它会误判"没有管道"而跳过补候选——候选一旦
    缺失，参数值就永远是空的。这里先强制从库里重读一次再判断。
    """
    if element.pipes:
        return True
    try:
        orm.session().expire(element, ["pipes"])
    except Exception:  # 未入会话 / 已分离：只能信缓存
        return False
    return bool(element.pipes)


def ensure_atlas_candidates(element: Element) -> bool:
    """直埋构件的候选行为空时，现场查图集补 8 组（一次性）。

    返回是否新建了候选行。候选一旦存在就不再动——它们归用户所有。
    没有管道时不生成：空管道查出来的 8 组全是空值，而候选“存在就不再补”，
    会让之后加的第一根管永远拿不到候选（等加管时再生成）。
    """
    from app.services.atlas import resolve_atlas

    if element.category != CATEGORY_BURIED or element.atlas_candidates:
        return False
    if not _has_pipes(element):
        return False
    pe, pf, pw = _principles(element)
    if pf is None:
        return False
    for con_found in (True, False):
        for angle in CANDIDATE_ANGLES:
            query = _bare_query(element, pe, pf, pw)
            query.con_found = con_found
            query.found_angle = int(angle)
            at = resolve_atlas(query)
            element.atlas_candidates.append(
                ElementAtlasCandidate(
                    con_found=con_found,
                    angle=angle,
                    t=at.t if at.t else None,
                    a=at.a if at.a else None,
                    c1=at.c1 if at.c1 else None,
                    c2=at.c2 if at.c2 else None,
                    order_no=len(element.atlas_candidates),
                )
            )
    return True


def match_atlas_candidates(element: Element, *, commit: bool = True) -> bool:
    """按当前地基原则自动选组，把 a / C1 / C2 写进参数行。

    只对直埋构件生效（其他类别的参数值仍由用户自由编辑）；候选行缺失时先
    补（见 :func:`ensure_atlas_candidates`）。选组顺序见
    :func:`app.core.atlas_candidates.select_candidate`：同组精确 → 同组就近 →
    跨组精确 → 跨组就近。

    匹配条件一变就整组重算：四级都不命中时把三行参数**清空**（空 = 引擎按
    图集自动），绝不保留上一次匹配的旧值——旧值会让计算静默按旧角度/旧基础
    形式走。返回是否写入了参数。
    """
    if element.category != CATEGORY_BURIED:
        return False
    _pe, pf, _pw = _principles(element)
    if pf is None:
        return False
    ensure_atlas_candidates(element)
    row, _level = select_candidate(
        element.atlas_candidates, _match_con_found(element, pf), int(pf.found_angle)
    )
    values = (
        {PARAM_T_NAME: None, PARAM_A_NAME: None, PARAM_C1_NAME: None, PARAM_C2_NAME: None}
        if row is None
        else {
            PARAM_T_NAME: row.t,
            PARAM_A_NAME: row.a,
            PARAM_C1_NAME: row.c1,
            PARAM_C2_NAME: row.c2,
        }
    )
    existing = {(param.key, param.unit): param for param in element.params}
    changed = False
    for name, unit in atlas_param_rows(element.category):
        value = values.get(name)
        # 候选该字段为 None（图集无值，如金属管的 a / C1）或一级都没命中
        # → 写空 = 引擎回退自动按图集；候选有值 → 写值。保证参数行的值
        # 始终与"当前匹配到的组"一致。
        text = format_number(float(value)) if value is not None else ""
        param = existing.get((name, unit))
        if param is None:
            element.params.append(ElementParam(key=name, unit=unit, value=text))
            changed = True
        elif param.value != text:
            param.value = text
            changed = True
    # 管道壁厚以参数行为准：同步回首根管的 t（引擎 / 断面 / 包封扣管位都读它）
    if _sync_pipe_thickness(element, values.get(PARAM_T_NAME)):
        changed = True
    if changed and commit:
        project_io.commit()
        _expire(element)
    return changed


def _sync_pipe_thickness(element: Element, value: float | None) -> bool:
    """把参数行的管道壁厚写回首根管；无管或值未变返回 False。"""
    pipes = list(element.pipes)
    if not pipes:
        return False
    head = pipes[0]
    target = float(value) if value is not None else None
    if head.t == target:
        return False
    head.t = target
    return True


def selected_combo(element: Element) -> tuple[str | None, str | None]:
    """当前匹配到的候选组合 ``(组合键, 层级)``，供界面标注；不补候选、不写库。

    ``(None, None)`` = 四级都没命中（参数行应为空、计算按图集走）。
    """
    if element.category != CATEGORY_BURIED or not element.atlas_candidates:
        return None, None
    _pe, pf, _pw = _principles(element)
    if pf is None:
        return None, None
    row, level = select_candidate(
        element.atlas_candidates, _match_con_found(element, pf), int(pf.found_angle)
    )
    if row is None:
        return None, None
    return combo_key(row.con_found, row.angle), level


def match_for_foundation(foundation_name: str) -> int:
    """地基原则被修改后，对引用它的直埋构件逐条重匹配（原则面板保存时调用）。

    返回重新匹配的构件数。匹配是"从候选选组"，不改动候选本身。
    """
    if not project_io.is_open():
        return 0
    elements = (
        orm.session()
        .scalars(
            select(Element)
            .where(
                Element.category == CATEGORY_BURIED,
                Element.pf_name == foundation_name,
            )
            .order_by(Element.order_no, Element.id)
        )
        .all()
    )
    matched = 0
    for element in elements:
        if match_atlas_candidates(element, commit=False):
            matched += 1
    if matched:
        project_io.commit()
        unit_ids = {element.unit_id for element in elements}
        for unit_id in unit_ids:
            bus().unit_changed.emit(unit_id)
    return matched


def _expire(element: Element) -> None:
    try:
        orm.session().expire(element)
    except Exception:
        pass


__all__ = [
    "ensure_atlas_candidates",
    "match_atlas_candidates",
    "match_for_foundation",
    "selected_combo",
]
