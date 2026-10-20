"""原则编辑的纯函数层（AI 工具与对话框共用）。

对话框的落库逻辑原先直接写在 Qt 槽里；这里抽出等价纯函数，供 MCP / AI 工具
调用。函数只依赖 SQLAlchemy 与 project_io 原语，不依赖 Qt。

失败抛 :class:`PrincipleEditError`（中文、带可执行指引），由工具层转成
``{"error": ...}``。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.models import base as orm
from app.core.models.models import (
    GROOVE_WIDTH_B,
    GROOVE_WIDTH_WORK,
    MULTI_LEVEL_TEXT,
    PRECIPITATION_COLUMNS,
    PRECIPITATION_LABELS,
    WIDTH_KIND_GROOVE_B,
    WIDTH_KIND_WORK,
    Component,
    EnclosureCushion,
    EnclosureLevel,
    EnclosureWork,
    FoundationReplacement,
    PcpEnclosure,
    PcpFoundation,
    PcpPrecipitation,
    PcpWidth,
    WidthItem,
    format_precipitation,
    parse_precipitation,
)
from app.services import project_io


class PrincipleEditError(ValueError):
    """原则编辑失败（业务错误，可自纠）。"""


# --------------------------------------------------------------------------- #
# 查找
# --------------------------------------------------------------------------- #
def _enclosure(key) -> PcpEnclosure:
    session = orm.session()
    if isinstance(key, int):
        enclosure = session.get(PcpEnclosure, key)
    else:
        enclosure = session.scalar(
            select(PcpEnclosure).where(PcpEnclosure.name == str(key)).order_by(PcpEnclosure.id)
        )
    if enclosure is None:
        names = project_io.enclosure_names()
        raise PrincipleEditError(
            f"围护原则“{key}”不存在。可用：{'、'.join(names) if names else '（无）'}"
        )
    return enclosure


def _foundation(key) -> PcpFoundation:
    session = orm.session()
    if isinstance(key, int):
        foundation = session.get(PcpFoundation, key)
    else:
        foundation = session.scalar(
            select(PcpFoundation).where(PcpFoundation.name == str(key)).order_by(PcpFoundation.id)
        )
    if foundation is None:
        names = project_io.foundation_names()
        raise PrincipleEditError(
            f"地基原则“{key}”不存在。可用：{'、'.join(names) if names else '（无）'}"
        )
    return foundation


def _precipitation(key) -> PcpPrecipitation:
    session = orm.session()
    if isinstance(key, int):
        precipitation = session.get(PcpPrecipitation, key)
    else:
        precipitation = session.scalar(
            select(PcpPrecipitation)
            .where(PcpPrecipitation.name == str(key))
            .order_by(PcpPrecipitation.id)
        )
    if precipitation is None:
        names = project_io.precipitation_names()
        raise PrincipleEditError(
            f"降水原则“{key}”不存在。可用：{'、'.join(names) if names else '（无）'}"
        )
    return precipitation


def _width(key) -> PcpWidth:
    session = orm.session()
    if isinstance(key, int):
        width = session.get(PcpWidth, key)
    else:
        width = session.scalar(
            select(PcpWidth).where(PcpWidth.name == str(key)).order_by(PcpWidth.id)
        )
    if width is None:
        names = project_io.width_names()
        raise PrincipleEditError(
            f"面宽原则“{key}”不存在。可用：{'、'.join(names) if names else '（无）'}"
        )
    return width


def _component(component_id: int) -> Component:
    component = orm.session().get(Component, int(component_id))
    if component is None:
        raise PrincipleEditError(f"找不到 component_id={component_id} 的构件。")
    return component


# --------------------------------------------------------------------------- #
# 围护原则
# --------------------------------------------------------------------------- #
def apply_enclosure_fields(
    enclosure_id: int,
    fields: dict | None = None,
    cushions: list[dict] | None = None,
) -> PcpEnclosure:
    """修改围护原则顶部参数；cushions 非 None 时整表替换垫层。"""
    enclosure = _enclosure(enclosure_id)
    session = orm.session()
    fields = fields or {}
    for key in ("excvt", "dock_l", "dock_h", "cover50", "cover"):
        if fields.get(key) is not None:
            setattr(enclosure, key, str(fields[key]))
    if fields.get("found_angle") is not None:
        try:
            enclosure.found_angle = int(fields["found_angle"])
        except (TypeError, ValueError) as error:
            raise PrincipleEditError("found_angle 需为整数（90/120/150/180）。") from error
    if fields.get("con_found") is not None:
        enclosure.con_found = bool(fields["con_found"])
    if cushions is not None:
        if not cushions:
            raise PrincipleEditError("至少需要一层垫层。")
        for cushion in list(enclosure.cushions):
            session.delete(cushion)
        session.flush()
        for index, item in enumerate(cushions):
            name = str(item.get("name") or "").strip()
            if not name:
                raise PrincipleEditError("垫层材质不能为空。")
            try:
                height = float(item.get("h", 0) or 0)
            except (TypeError, ValueError) as error:
                raise PrincipleEditError("垫层厚度 h 需为数字（mm）。") from error
            session.add(
                EnclosureCushion(
                    enclosure_id=enclosure.id, name=name, h=height, order_no=index
                )
            )
        session.flush()
        session.expire(enclosure)
    project_io.commit()
    session.expire(enclosure)
    return enclosure


def _normalize_levels(levels: list[dict], library) -> list[dict]:
    if not levels:
        raise PrincipleEditError("至少需要一级围护做法。")
    names = library.names("Ei")
    normalized: list[dict] = []
    for level in levels:
        level_type = str(level.get("level_type") or level.get("name") or "").strip()
        if not level_type:
            level_type = names[0] if names else "放坡"
        if library.template("Ei", level_type) is None:
            raise PrincipleEditError(
                f"围护类型“{level_type}”不在构件库。可用：{'、'.join(names)}"
            )
        try:
            h = float(level.get("h", -1) if level.get("h") is not None else -1)
            step_width = float(level.get("step_width", 1) if level.get("step_width") is not None else 1)
        except (TypeError, ValueError) as error:
            raise PrincipleEditError("分级高度/平台宽需为数字。") from error
        normalized.append({"level_type": level_type, "h": h, "step_width": step_width})
    return normalized


def apply_enclosure_works(enclosure_id: int, works: list[dict]) -> PcpEnclosure:
    """整表替换围护做法（含多级与止水）。

    works 每项：``{min_depth, cpnt_cat, stop_type, levels:[{h, step_width, level_type}]}``。
    首行 min_depth 必须为 0（主表格按埋深取做法）。
    """
    enclosure = _enclosure(enclosure_id)
    library = project_io.component_library()
    if not works:
        raise PrincipleEditError("至少需要一种围护做法。")
    session = orm.session()
    # 先校验，再删除旧数据（避免校验失败留下半成品）
    prepared: list[dict] = []
    for index, work in enumerate(works):
        try:
            min_depth = float(work.get("min_depth", 0) or 0)
        except (TypeError, ValueError) as error:
            raise PrincipleEditError("min_depth 需为数字（m）。") from error
        if index == 0 and min_depth != 0:
            raise PrincipleEditError("第一条做法的埋深必须为 0。")
        cpnt_cat = str(work.get("cpnt_cat") or "").strip()
        stop_type = str(work.get("stop_type") or "无").strip()
        if library.template("WSi", stop_type) is None:
            stop_names = library.names("WSi")
            raise PrincipleEditError(
                f"止水类型“{stop_type}”不在构件库。可用：{'、'.join(stop_names)}"
            )
        if cpnt_cat == MULTI_LEVEL_TEXT:
            levels = _normalize_levels(work.get("levels") or [], library)
        else:
            level_type = cpnt_cat or (library.names("Ei")[0] if library.names("Ei") else "放坡")
            if library.template("Ei", level_type) is None:
                raise PrincipleEditError(
                    f"围护类型“{level_type}”不在构件库。可用：{'、'.join(library.names('Ei'))}"
                )
            levels = _normalize_levels(
                [
                    {
                        "level_type": level_type,
                        "h": (work.get("levels") or [{}])[0].get("h", -1),
                        "step_width": (work.get("levels") or [{}])[0].get("step_width", 1),
                    }
                ],
                library,
            )
        prepared.append(
            {
                "min_depth": min_depth,
                "cpnt_cat": cpnt_cat or levels[0]["level_type"],
                "stop_type": stop_type,
                "levels": levels,
            }
        )
    # 删除旧做法（级联删除分级与构件）；expire_all 清掉身份映射里已删对象，
    # 避免新行复用 id 时触发 "Identity map already had an identity" 警告
    for work in list(enclosure.works):
        session.delete(work)
    session.flush()
    session.expire_all()
    for index, work_data in enumerate(prepared):
        work = EnclosureWork(
            enclosure_id=enclosure.id,
            min_depth=work_data["min_depth"],
            cpnt_cat=work_data["cpnt_cat"],
            order_no=index,
        )
        session.add(work)
        session.flush()
        for level_index, level_data in enumerate(work_data["levels"]):
            level = EnclosureLevel(
                work_id=work.id,
                name=level_data["level_type"],
                h=level_data["h"],
                step_width=level_data["step_width"],
                order_no=level_index,
            )
            session.add(level)
            session.flush()
            project_io.component_from_template(
                session, library, "Ei", level_data["level_type"],
                enclosure_level_id=level.id,
            )
        project_io.component_from_template(
            session, library, "WSi", work_data["stop_type"], enclosure_work_id=work.id
        )
    session.expire(enclosure)
    project_io.commit()
    return enclosure


def apply_work_levels(work_id: int, levels: list[dict]) -> EnclosureWork:
    """整表替换某做法的分级（多级围护编辑器的等价操作）。"""
    work = orm.session().get(EnclosureWork, int(work_id))
    if work is None:
        raise PrincipleEditError(f"找不到 work_id={work_id} 的围护做法。")
    library = project_io.component_library()
    normalized = _normalize_levels(levels, library)
    session = orm.session()
    for level in list(work.levels):
        session.delete(level)
    session.flush()
    session.expire_all()
    for index, level_data in enumerate(normalized):
        level = EnclosureLevel(
            work_id=work.id,
            name=level_data["level_type"],
            h=level_data["h"],
            step_width=level_data["step_width"],
            order_no=index,
        )
        session.add(level)
        session.flush()
        project_io.component_from_template(
            session, library, "Ei", level_data["level_type"], enclosure_level_id=level.id
        )
    session.expire(work)
    project_io.commit()
    return work


def apply_foundation(
    foundation_id: int,
    layers: list[dict] | None = None,
    component: dict | None = None,
) -> PcpFoundation:
    """修改地基原则：layers 整表替换换填层；component 指定特殊地基模板。

    component 形如 ``{template_name, params: {key: {display, expression}}}``；
    None = 不修改。传 ``{"remove": true}`` 删除特殊地基构件。
    """
    foundation = _foundation(foundation_id)
    session = orm.session()
    if layers is not None:
        for layer in list(foundation.replacements):
            session.delete(layer)
        session.flush()
        for index, item in enumerate(layers):
            name = str(item.get("name") or "").strip()
            if not name:
                raise PrincipleEditError("换填材质不能为空。")
            try:
                height = float(item.get("h", 0) or 0)
            except (TypeError, ValueError) as error:
                raise PrincipleEditError("换填层厚度 h 需为数字（mm）。") from error
            session.add(
                FoundationReplacement(
                    foundation_id=foundation.id, name=name, h=height, order_no=index
                )
            )
        session.flush()
        session.expire(foundation)
    if component is not None:
        if component.get("remove"):
            for old in list(foundation.components):
                session.delete(old)
            session.flush()
        else:
            template_name = str(component.get("template_name") or "").strip()
            library = project_io.component_library()
            if not template_name or library.template("Fi", template_name) is None:
                raise PrincipleEditError(
                    f"特殊地基构件“{template_name}”不在构件库。"
                    f"可用：{'、'.join(library.names('Fi'))}"
                )
            for old in list(foundation.components):
                session.delete(old)
            session.flush()
            new_component = project_io.component_from_template(
                session, library, "Fi", template_name, foundation_id=foundation.id
            )
            if component.get("params"):
                _apply_component_params(session, new_component, component["params"])
        session.expire(foundation)
    project_io.commit()
    session.expire(foundation)
    return foundation


# --------------------------------------------------------------------------- #
# 降水 / 面宽
# --------------------------------------------------------------------------- #
def apply_precipitation_wells(precipitation_id: int, wells: dict) -> PcpPrecipitation:
    """按井型标签或列名整体/增量设置降水参数。"""
    precipitation = _precipitation(precipitation_id)
    label_to_column = {label: key for key, label in PRECIPITATION_LABELS.items()}
    for label, spec in (wells or {}).items():
        column = label_to_column.get(label) or (label if label in PRECIPITATION_COLUMNS else None)
        if column is None:
            raise PrincipleEditError(
                f"未知井型“{label}”。可用：{'、'.join(PRECIPITATION_LABELS.values())}"
            )
        if not isinstance(spec, dict):
            raise PrincipleEditError(f"井型“{label}”的参数必须是对象。")
        current = parse_precipitation(getattr(precipitation, column), column)
        enabled = bool(spec.get("enabled", True))
        try:
            elevation = float(spec["elevation"]) if enabled and spec.get("elevation") is not None else -1.0
        except (TypeError, ValueError) as error:
            raise PrincipleEditError(f"井型“{label}”的埋深需为数字（m）。") from error
        if enabled and elevation < 0:
            raise PrincipleEditError(f"井型“{label}”启用时埋深必须 >= 0。")
        try:
            gap = float(spec["gap"]) if spec.get("gap") is not None else current[1]
            sides = float(spec["sides"]) if spec.get("sides") is not None else current[2]
        except (TypeError, ValueError) as error:
            raise PrincipleEditError(f"井型“{label}”的井距/侧数需为数字。") from error
        setattr(precipitation, column, format_precipitation(elevation, gap, sides))
    project_io.commit()
    orm.session().expire(precipitation)
    return precipitation


def apply_width_items(
    width_id: int,
    mode: str | None = None,
    items: list[dict] | None = None,
) -> PcpWidth:
    """设置面宽原则取值方式与矩阵条目（按 pipe_type+dn 增量替换）。"""
    width = _width(width_id)
    session = orm.session()
    if mode:
        if mode in (GROOVE_WIDTH_WORK, "work", "按工作面宽度"):
            width.groove_width = GROOVE_WIDTH_WORK
        elif mode in (GROOVE_WIDTH_B, "groove_b", "按沟槽总宽度"):
            width.groove_width = GROOVE_WIDTH_B
        else:
            raise PrincipleEditError("mode 只能是 WorkWidth（工作面宽度）或 B（沟槽总宽度）。")
    if items is not None:
        default_kind = (
            WIDTH_KIND_WORK if width.groove_width == GROOVE_WIDTH_WORK else WIDTH_KIND_GROOVE_B
        )
        from app.agent.conventions import WIDTH_PIPE_TYPES

        for item in items:
            pipe_type = str(item.get("pipe_type") or "").strip()
            if pipe_type not in WIDTH_PIPE_TYPES:
                raise PrincipleEditError(
                    f"管材类别“{pipe_type}”无效。可用：{'、'.join(WIDTH_PIPE_TYPES)}"
                )
            try:
                dn = int(item.get("dn"))
                value = float(item.get("width"))
            except (TypeError, ValueError) as error:
                raise PrincipleEditError("dn 需为整数（0~3000，步长 100），width 需为数字（mm）。") from error
            if dn < 0 or dn > 3000:
                raise PrincipleEditError("dn 超出范围（0~3000）。")
            kind = str(item.get("kind") or default_kind)
            if kind not in (WIDTH_KIND_WORK, WIDTH_KIND_GROOVE_B):
                raise PrincipleEditError("kind 只能是 work 或 groove_b。")
            for existing in list(width.items):
                if existing.kind == kind and existing.pipe_type == pipe_type and existing.dn == dn:
                    session.delete(existing)
            session.add(
                WidthItem(
                    width_id=width.id,
                    pipe_type=pipe_type,
                    dn=dn,
                    width=value,
                    kind=kind,
                    order_no=0,
                )
            )
        session.flush()
        session.expire(width)
    project_io.commit()
    session.expire(width)
    return width


def reset_width_to_atlas(width_id: int) -> PcpWidth:
    """把面宽原则的两张表恢复为图集默认（GB 50268-2008）。"""
    width = _width(width_id)
    session = orm.session()
    for item in list(width.items):
        session.delete(item)
    session.flush()
    work, groove = project_io.default_width_tables()
    project_io.seed_width_tables(session, width, work, groove)
    session.expire(width)
    project_io.commit()
    return width


# --------------------------------------------------------------------------- #
# 构件参数
# --------------------------------------------------------------------------- #
def _template_group_for(component: Component, library) -> tuple[str, dict] | None:
    for group in ("Ei", "WSi", "Fi"):
        template = library.template(group, component.name)
        if template is not None:
            return group, template.params
    return None


def _apply_component_params(session, component: Component, params: dict) -> None:
    library = project_io.component_library()
    found = _template_group_for(component, library)
    allowed = set(found[1]) if found else set()
    existing = {param.key: param for param in component.params}
    for key, spec in (params or {}).items():
        key = str(key)
        if key not in existing and key not in allowed:
            raise PrincipleEditError(
                f"参数键“{key}”不在构件模板中（不增删行）。可用：{'、'.join(sorted(existing) or sorted(allowed))}"
            )
        if isinstance(spec, dict):
            display = str(spec.get("display", "")).strip()
            expression = str(spec.get("expression", "")).strip()
        else:
            display = ""
            expression = str(spec).strip()
        value = f"{display}|{expression}"
        if key in existing:
            existing[key].value = value
        else:
            component.params.append(
                ComponentParam(component_id=component.id, key=key, value=value)
            )
    session.flush()


def apply_component_params(component_id: int, params: dict) -> Component:
    """修改构件参数（只允许模板键集内的键，不增删行）。"""
    component = _component(component_id)
    _apply_component_params(orm.session(), component, params or {})
    project_io.commit()
    orm.session().expire(component)
    return component
