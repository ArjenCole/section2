"""图集候选参数的补齐与自动匹配（v9）。

候选参数（"候选参数列"）是构件库资产的一次性快照，存在
``element_atlas_candidate`` 表，允许用户改、**永不自动改写**；参数值
（工作面加宽 / 垫层厚 / 基础厚三行参数）按当前主围护原则的
``con_found + found_angle`` 从候选里自动选组写进来。

自动匹配的触发点（都在数据改动处调用 :func:`match_atlas_candidates`）：

* 构件库插入条目 / AI 新增 / 空白新增（候选缺失时现场查图集补一次）；
* 构件的围护原则切换（``update_element``）；
* 围护原则本身修改（``principle_edit.apply_enclosure_fields`` →
  :func:`match_for_enclosure`，对引用该原则的直埋构件逐条重匹配）；
* 管材类别修改（``update_pipe``，混凝土 ↔ 非混凝土会换候选组）。

独立成 services 层模块：``principle_edit``（services）与 ``unit_vm``
（viewmodels）都要用，避免 viewmodels 反向依赖。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.atlas_candidates import CANDIDATE_ANGLES, nearest_candidate
from app.core.event_bus import bus
from app.core.models import base as orm
from app.core.models.models import (
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    Element,
    ElementAtlasCandidate,
    ElementParam,
    PcpEnclosure,
)
from app.core.param_naming import (
    PARAM_A_NAME,
    PARAM_C1_NAME,
    PARAM_C2_NAME,
    atlas_param_rows,
)
from app.core.evaluator import format_number
from app.services import project_io


def _principles(element: Element):
    """主围护 / 面宽原则（同引擎：main_pe_name 优先，缺省取第一条）。"""
    from app.core.calc.engine import resolve_element_principles

    pe, _pf, _pp, pw, _pe_refs, _pf_refs = resolve_element_principles(element, orm.session())
    return pe, pw


def _bare_query(element: Element, pe: PcpEnclosure, pw):
    """强制查表的图集查询：清掉参数覆盖值、管道壁厚留空（否则命中快照短路）。"""
    from app.core.calc.engine import build_atlas_query, build_element_input
    from app.services.atlas import PipeSpec

    info = build_element_input(element, pe, None)
    query = build_atlas_query(info, pe, pw)
    query.a = query.c1 = query.c2 = None
    query.pipes = [type(p)(mat=p.mat, dn=p.dn, cat=p.cat) for p in info.pipes]
    return query


def ensure_atlas_candidates(element: Element) -> bool:
    """直埋构件的候选行为空时，现场查图集补 8 组（一次性）。

    返回是否新建了候选行。候选一旦存在就不再动——它们归用户所有。
    """
    from app.services.atlas import resolve_atlas

    if element.category != CATEGORY_BURIED or element.atlas_candidates:
        return False
    pe, pw = _principles(element)
    if pe is None:
        return False
    for con_found in (True, False):
        for angle in CANDIDATE_ANGLES:
            query = _bare_query(element, pe, pw)
            query.con_found = con_found
            query.found_angle = int(angle)
            at = resolve_atlas(query)
            element.atlas_candidates.append(
                ElementAtlasCandidate(
                    con_found=con_found,
                    angle=angle,
                    a=at.a if at.a else None,
                    c1=at.c1 if at.c1 else None,
                    c2=at.c2 if at.c2 else None,
                    order_no=len(element.atlas_candidates),
                )
            )
    return True


def match_atlas_candidates(element: Element, *, commit: bool = True) -> bool:
    """按当前主围护原则自动选组，把 a / C1 / C2 写进参数行。

    只对直埋构件生效（其他类别的参数值仍由用户自由编辑）；候选行缺失时先
    补（见 :func:`ensure_atlas_candidates`）。图集没有的组合（如砼基础 150°）
    按就近角度跳过。返回是否写入了参数。
    """
    if element.category != CATEGORY_BURIED:
        return False
    pe, _pw = _principles(element)
    if pe is None:
        return False
    ensure_atlas_candidates(element)
    row = nearest_candidate(element.atlas_candidates, bool(pe.con_found), int(pe.found_angle))
    if row is None:
        return False
    values = {PARAM_A_NAME: row.a, PARAM_C1_NAME: row.c1, PARAM_C2_NAME: row.c2}
    existing = {(param.key, param.unit): param for param in element.params}
    changed = False
    for name, unit in atlas_param_rows(element.category):
        value = values.get(name)
        # 候选该字段为 None（图集无值，如金属管的 a / C1）→ 写空 = 引擎回退
        # 自动按图集；候选有值 → 写值。保证参数行的值始终与选中组一致。
        text = format_number(float(value)) if value is not None else ""
        param = existing.get((name, unit))
        if param is None:
            element.params.append(ElementParam(key=name, unit=unit, value=text))
            changed = True
        elif param.value != text:
            param.value = text
            changed = True
    if changed and commit:
        project_io.commit()
        _expire(element)
    return changed


def match_for_enclosure(enclosure_name: str) -> int:
    """围护原则被修改后，对引用它的直埋构件逐条重匹配（原则面板保存时调用）。

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
                (Element.pe_name == enclosure_name)
                | (Element.main_pe_name == enclosure_name),
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
    "match_for_enclosure",
]
