"""`.stn` JSON 数据体 ↔ 工程数据库 的编解码。

数据体是**重新规划的层级结构**（工程 → 标段 → 单位工程 → 构件 → 明细，
原则独立成节），不是 SQLite 表结构的逐表镜像：库里为了关系化引入的
``id`` / 外键 / ``order_no`` 都不进文件，顺序由 JSON 数组次序表达，
落库时按数组次序重排 ``order_no``。

形状约定（与 1.0 的 XML 无关，2.0 专有）：

```json
{
  "format": "Section2",
  "file_version": 2,
  "app_version": "2.0.0.0",
  "created_at": "…", "saved_at": "…",
  "basic_info": {"project_name": "…", "project_index": "…", "author": "…", "atlas_name": "…"},
  "principles": {
    "enclosures":    [{"name": "…", "con_found": true, "excvt": "…", "found_angle": 120,
                       "dock_l": "…", "dock_h": "…", "cover50": "…", "cover": "…",
                       "cushions": [{"name": "中粗砂", "h": 200.0}],
                       "works": [{"min_depth": 0.0, "cpnt_cat": "放坡",
                                  "levels": [{"name": "放坡", "h": -1.0, "step_width": 1.0,
                                              "component": {"name": "…", "formula": "…",
                                                            "params": {"A": "显示名|算式"}}}],
                                  "waterstop": {"name": "…", "formula": "…", "params": {}}}]}],
    "foundations":   [{"name": "…", "replacements": [{"name": "…", "h": 200.0}], "component": {…}}],
    "precipitations": [{"name": "…", "wet_soil": "0|0|0", …}],
    "widths":        [{"name": "…", "groove_width": "WorkWidth",
                       "tables": {"work": {"承插式": {"300": 1.06}}, "groove_b": {…}}}]
  },
  "segments": [{"name": "…", "units": [{"name": "…", "elements": [element…]}]}],
  "prices": [{"key": "…", "value": 100.0}]
}
```

构件（element）字段：``category`` / ``name`` / ``depth`` / ``amount`` /
``pe_name`` / ``pf_name`` / ``pp_name`` / ``pw_name`` / ``source``，
加 ``pipes``（``{"cat","mat","dn","content","t"}``）、
``params``（``[{"key","unit","value"}]``）、
``quantities``（``[{"category","item","unit","value"}]``）、
``atlas_candidates``（``[{"con_found","angle","t","a","c1","c2"}]``，值为 null
表示图集该组合无数据）。

file_version 1 的文件带 ``main_pe_name`` / ``pe_refs`` / ``pf_refs``（多原则
引用，2.0 已取消该功能）：读取时按主原则降级成单引用，见 :func:`_load_element`。

本模块只做忠实的双向转换：值一律存数据库原文（字符串算式、``"显示名|算式"``
等不解不拆），保证 存盘 → 重开 后数据零漂移。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.version import APP_VERSION, STN_FILE_VERSION
from app.core.models import base as orm
from app.core.models.models import (
    PRECIPITATION_COLUMNS,
    BasicInfo,
    Component,
    ComponentParam,
    Element,
    ElementAtlasCandidate,
    ElementParam,
    ElementQuantity,
    EnclosureCushion,
    EnclosureLevel,
    EnclosureWork,
    FoundationReplacement,
    PcpEnclosure,
    PcpFoundation,
    PcpPrecipitation,
    PcpWidth,
    Pipe,
    Price,
    Segment,
    Unit,
    WidthItem,
)

# --------------------------------------------------------------------------- #
# 导出：数据库 → JSON
# --------------------------------------------------------------------------- #
def dump_database() -> dict:
    """把当前打开的工程整体导出成 JSON 数据体（调用前先 orm.commit()）。"""
    session = orm.session()
    # expire_on_commit=False 会让已加载的 relationship 集合变陈旧（绕开集合、
    # 直接按外键插入的子行不在里面），导出前全部过期重读，保证按库内实况导出
    session.expire_all()
    info = session.get(BasicInfo, 1)
    return {
        "format": "Section2",
        "file_version": STN_FILE_VERSION,
        "app_version": APP_VERSION,
        "created_at": orm.get_meta("created_at"),
        "saved_at": orm.get_meta("updated_at"),
        "basic_info": {
            "project_name": (info.project_name or "") if info else "",
            "project_index": (info.project_index or "") if info else "",
            "author": (info.author or "") if info else "",
            "atlas_name": (info.atlas_name or "") if info else "",
        },
        "principles": {
            "enclosures": [_dump_enclosure(item) for item in _ordered(session, PcpEnclosure)],
            "foundations": [_dump_foundation(item) for item in _ordered(session, PcpFoundation)],
            "precipitations": [
                _dump_precipitation(item) for item in _ordered(session, PcpPrecipitation)
            ],
            "widths": [_dump_width(item) for item in _ordered(session, PcpWidth)],
        },
        "segments": [_dump_segment(item) for item in _ordered(session, Segment)],
        "prices": [
            {"key": item.key or "", "value": float(item.value or 0.0)}
            for item in session.query(Price).order_by(Price.id)
        ],
    }


def _ordered(session, model) -> list:
    """按界面语义排序取全表（order_no 优先，同号按 id 稳定）。"""
    return list(session.scalars(select(model).order_by(model.order_no, model.id)))


def _dump_enclosure(item: PcpEnclosure) -> dict:
    works = sorted(item.works, key=lambda work: (work.order_no, work.id))
    return {
        "name": item.name or "",
        "con_found": bool(item.con_found),
        "excvt": item.excvt or "",
        "found_angle": int(item.found_angle or 0),
        "dock_l": item.dock_l or "",
        "dock_h": item.dock_h or "",
        "cover50": item.cover50 or "",
        "cover": item.cover or "",
        "cushions": [
            {"name": cushion.name or "", "h": float(cushion.h or 0.0)}
            for cushion in sorted(item.cushions, key=lambda row: (row.order_no, row.id))
        ],
        "works": [_dump_work(work) for work in works],
    }


def _dump_work(work: EnclosureWork) -> dict:
    levels = sorted(work.levels, key=lambda row: (row.order_no, row.id))
    waterstop = next(iter(work.waterstops), None)
    return {
        "min_depth": float(work.min_depth or 0.0),
        "cpnt_cat": work.cpnt_cat or "",
        "levels": [
            {
                "name": level.name or "",
                "h": float(level.h or 0.0),
                "step_width": float(level.step_width or 0.0),
                "component": _dump_component(next(iter(level.components), None)),
            }
            for level in levels
        ],
        "waterstop": _dump_component(waterstop),
    }


def _dump_foundation(item: PcpFoundation) -> dict:
    component = next(iter(item.components), None)
    return {
        "name": item.name or "",
        "replacements": [
            {"name": row.name or "", "h": float(row.h or 0.0)}
            for row in sorted(item.replacements, key=lambda row: (row.order_no, row.id))
        ],
        "component": _dump_component(component),
    }


def _dump_precipitation(item: PcpPrecipitation) -> dict:
    return {
        "name": item.name or "",
        **{key: getattr(item, key) or "" for key in PRECIPITATION_COLUMNS},
    }


def _dump_width(item: PcpWidth) -> dict:
    tables: dict[str, dict[str, dict[str, float]]] = {"work": {}, "groove_b": {}}
    for row in sorted(item.items, key=lambda entry: (entry.order_no, entry.id)):
        kind = row.kind if row.kind in tables else "work"
        tables[kind].setdefault(row.pipe_type or "", {})[str(row.dn)] = float(row.width or 0.0)
    return {
        "name": item.name or "",
        "groove_width": item.groove_width or "",
        "tables": tables,
    }


def _dump_component(component: Component | None) -> dict | None:
    """构件 → JSON；``null`` 表示该位置没有构件（如做法缺止水构件）。"""
    if component is None:
        return None
    return {
        "name": component.name or "",
        "formula": component.formula or "",
        "params": {param.key: param.value or "" for param in component.params},
    }


def _dump_segment(item: Segment) -> dict:
    return {
        "name": item.name or "",
        "units": [
            {
                "name": unit.name or "",
                "elements": [
                    _dump_element(element)
                    for element in sorted(unit.elements, key=lambda row: (row.order_no, row.id))
                ],
            }
            for unit in sorted(item.units, key=lambda row: (row.order_no, row.id))
        ],
    }


def _dump_element(element: Element) -> dict:
    return {
        "category": int(element.category or 0),
        "name": element.name or "",
        "depth": element.depth or "",
        "amount": element.amount or "",
        "pe_name": element.pe_name or "",
        "pf_name": element.pf_name or "",
        "pp_name": element.pp_name or "",
        "pw_name": element.pw_name or "",
        "source": element.source or "",
        "pipes": [
            {
                "cat": pipe.cat or "",
                "mat": pipe.mat or "",
                "dn": int(pipe.dn or 0),
                "content": pipe.content or "",
                "t": None if pipe.t is None else float(pipe.t),
            }
            for pipe in element.pipes
        ],
        "params": [
            {"key": param.key or "", "unit": param.unit or "", "value": param.value or ""}
            for param in element.params
        ],
        "quantities": [
            {
                "category": row.category or "",
                "item": row.item or "",
                "unit": row.unit or "",
                "value": row.value or "",
            }
            for row in sorted(element.quantities, key=lambda row: (row.order_no, row.id))
        ],
        "atlas_candidates": [
            {
                "con_found": bool(row.con_found),
                "angle": int(row.angle or 0),
                "t": None if row.t is None else float(row.t),
                "a": None if row.a is None else float(row.a),
                "c1": None if row.c1 is None else float(row.c1),
                "c2": None if row.c2 is None else float(row.c2),
            }
            for row in sorted(element.atlas_candidates, key=lambda row: (row.order_no, row.id))
        ],
    }


# --------------------------------------------------------------------------- #
# 导入：JSON → 数据库（要求刚建好的空工作库，见 orm.create_working_database）
# --------------------------------------------------------------------------- #
def load_database(data: dict) -> None:
    """把 JSON 数据体写进当前打开的空工作库并提交。"""
    session = orm.session()

    info = data.get("basic_info") or {}
    session.add(
        BasicInfo(
            id=1,
            project_name=info.get("project_name") or "新建项目",
            project_index=info.get("project_index") or "001",
            author=info.get("author") or "",
            atlas_name=info.get("atlas_name") or "",
        )
    )

    principles = data.get("principles") or {}
    for index, item in enumerate(principles.get("enclosures") or []):
        _load_enclosure(session, item, order_no=index)
    for index, item in enumerate(principles.get("foundations") or []):
        _load_foundation(session, item, order_no=index)
    for index, item in enumerate(principles.get("precipitations") or []):
        session.add(
            PcpPrecipitation(
                name=item.get("name") or "新降水原则",
                order_no=index,
                **{key: str(item.get(key) or "0|0|0") for key in PRECIPITATION_COLUMNS},
            )
        )
    for index, item in enumerate(principles.get("widths") or []):
        _load_width(session, item, order_no=index)

    for index, item in enumerate(data.get("segments") or []):
        segment = Segment(name=item.get("name") or "新建标段", order_no=index)
        for unit_index, unit_data in enumerate(item.get("units") or []):
            unit = Unit(name=unit_data.get("name") or "新建单位工程", order_no=unit_index)
            segment.units.append(unit)
            for element_index, element_data in enumerate(unit_data.get("elements") or []):
                unit.elements.append(_load_element(element_data, order_no=element_index))
        session.add(segment)

    for price in data.get("prices") or []:
        session.add(Price(key=price.get("key") or "", value=float(price.get("value") or 0.0)))

    if data.get("created_at"):
        orm.set_meta("created_at", str(data["created_at"]))
    if data.get("saved_at"):
        orm.set_meta("updated_at", str(data["saved_at"]))
    orm.commit()


def _load_component(parent, data: dict | None) -> None:
    """在 parent（构件的三种所有者之一）下建构件；data 为 None 时保持无构件。"""
    if data is None:
        return
    component = Component(name=data.get("name") or "", formula=data.get("formula") or "")
    for key, value in (data.get("params") or {}).items():
        component.params.append(ComponentParam(key=key, value=value))
    _attach_component(parent, component)


def _attach_component(parent, component: Component) -> None:
    """把构件挂到它的所有者（与模型里三种外键一一对应）。"""
    if isinstance(parent, PcpFoundation):
        parent.components.append(component)
    elif isinstance(parent, EnclosureLevel):
        parent.components.append(component)
    elif isinstance(parent, EnclosureWork):
        parent.waterstops.append(component)
    else:  # pragma: no cover - 所有者类型只可能有这三种
        raise TypeError(f"构件不能挂在 {type(parent).__name__} 上")


def _load_enclosure(session, data: dict, *, order_no: int) -> None:
    enclosure = PcpEnclosure(
        name=data.get("name") or "新围护原则",
        con_found=bool(data.get("con_found", True)),
        excvt=data.get("excvt") or "Ⅲ类土",
        found_angle=int(data.get("found_angle") or 120),
        dock_l=data.get("dock_l") or "中粗砂",
        dock_h=data.get("dock_h") or "中粗砂",
        cover50=data.get("cover50") or "中粗砂",
        cover=data.get("cover") or "素土",
        order_no=order_no,
    )
    for cushion_index, cushion in enumerate(data.get("cushions") or []):
        enclosure.cushions.append(
            EnclosureCushion(
                name=cushion.get("name") or "中粗砂",
                h=float(cushion.get("h") or 0.0),
                order_no=cushion_index,
            )
        )
    session.add(enclosure)
    session.flush()
    for work_index, work_data in enumerate(data.get("works") or []):
        work = EnclosureWork(
            enclosure_id=enclosure.id,
            min_depth=float(work_data.get("min_depth") or 0.0),
            cpnt_cat=work_data.get("cpnt_cat") or "",
            order_no=work_index,
        )
        session.add(work)
        session.flush()
        for level_index, level_data in enumerate(work_data.get("levels") or []):
            level = EnclosureLevel(
                work_id=work.id,
                name=level_data.get("name") or "",
                h=float(level_data.get("h") or 0.0),
                step_width=float(level_data.get("step_width") or 0.0),
                order_no=level_index,
            )
            session.add(level)
            session.flush()
            _load_component(level, level_data.get("component"))
        _load_component(work, work_data.get("waterstop"))


def _load_foundation(session, data: dict, *, order_no: int) -> None:
    foundation = PcpFoundation(name=data.get("name") or "新地基原则", order_no=order_no)
    session.add(foundation)
    session.flush()
    for replace_index, replacement in enumerate(data.get("replacements") or []):
        session.add(
            FoundationReplacement(
                foundation_id=foundation.id,
                name=replacement.get("name") or "中粗砂",
                h=float(replacement.get("h") or 0.0),
                order_no=replace_index,
            )
        )
    _load_component(foundation, data.get("component"))


def _load_width(session, data: dict, *, order_no: int) -> None:
    width = PcpWidth(
        name=data.get("name") or "新面宽原则",
        groove_width=data.get("groove_width") or "WorkWidth",
        order_no=order_no,
    )
    session.add(width)
    session.flush()
    tables = data.get("tables") or {}
    row_no = 0
    for kind in ("work", "groove_b"):
        for pipe_type, values in (tables.get(kind) or {}).items():
            for dn_text, value in values.items():
                try:
                    dn = int(dn_text)
                except (TypeError, ValueError):
                    continue
                session.add(
                    WidthItem(
                        width_id=width.id,
                        pipe_type=pipe_type,
                        dn=dn,
                        width=float(value or 0.0),
                        kind=kind,
                        order_no=row_no,
                    )
                )
                row_no += 1


def _load_element(data: dict, *, order_no: int) -> Element:
    pe_name = data.get("pe_name") or ""
    pf_name = data.get("pf_name") or ""
    # file_version 1 的文件带多原则引用（pe_refs/pf_refs/main_pe_name，2.0 已取消
    # 该功能）：按主原则降级成单引用——围护取 main_pe_name（失效取第一条引用），
    # 地基取第一条引用；旧 show 名若是“多围护原则”等占位文字一并被覆盖
    legacy_main = str(data.get("main_pe_name") or "")
    pe_refs = data.get("pe_refs") or []
    if pe_refs:
        ref_names = [str(ref.get("name") or "") for ref in pe_refs]
        pe_name = legacy_main if legacy_main in ref_names else ref_names[0]
    pf_refs = data.get("pf_refs") or []
    if pf_refs:
        pf_name = str(pf_refs[0].get("name") or "")
    element = Element(
        category=int(data.get("category") or 0),
        name=data.get("name") or "",
        depth=data.get("depth") or "0",
        amount=data.get("amount") or "0",
        pe_name=pe_name,
        pf_name=pf_name,
        pp_name=data.get("pp_name") or "",
        pw_name=data.get("pw_name") or "",
        source=data.get("source") or "",
        order_no=order_no,
    )
    for pipe_data in data.get("pipes") or []:
        thickness = pipe_data.get("t")
        element.pipes.append(
            Pipe(
                cat=pipe_data.get("cat") or "",
                mat=pipe_data.get("mat") or "",
                dn=int(pipe_data.get("dn") or 0),
                content=pipe_data.get("content") or "1",
                t=None if thickness is None else float(thickness),
            )
        )
    for param in data.get("params") or []:
        element.params.append(
            ElementParam(
                key=param.get("key") or "",
                unit=param.get("unit") or "",
                value=param.get("value") or "",
            )
        )
    for row_index, row in enumerate(data.get("quantities") or []):
        element.quantities.append(
            ElementQuantity(
                category=row.get("category") or "",
                item=row.get("item") or "",
                unit=row.get("unit") or "",
                value=row.get("value") or "0",
                order_no=row_index,
            )
        )
    for row_index, row in enumerate(data.get("atlas_candidates") or []):
        element.atlas_candidates.append(
            ElementAtlasCandidate(
                con_found=bool(row.get("con_found", True)),
                angle=int(row.get("angle") or 120),
                t=None if row.get("t") is None else float(row["t"]),
                a=None if row.get("a") is None else float(row["a"]),
                c1=None if row.get("c1") is None else float(row["c1"]),
                c2=None if row.get("c2") is None else float(row["c2"]),
                order_no=row_index,
            )
        )
    return element
