"""管材类别（pipe.cat）：名称折算、面宽匹配、快照短路、构件库快照插入。

背景：v8 起管材类别是计算唯一依据，材质名（mat）只作显示。本文件锁住四条：
1. 名称 → 类别的优先级（混凝土 > 化学建材 > 金属，与旧版 elif 链一致）；
2. 面宽表行只读类别与管径，不看材质名；
3. a / C1 / C2 / 壁厚齐了就不查图集表（快照短路）；
4. 从构件库插入时把资产里的快照写进参数，不再现场查图集。
"""

from __future__ import annotations

import app  # noqa: F401  # ICU 预加载必须先于 PySide6
import pytest

from app.core.evaluator import format_number
from app.core.pipe_category import (
    PIPE_CAT_CHEMICAL,
    PIPE_CAT_CONCRETE_RIGID,
    PIPE_CAT_DEFAULT,
    PIPE_CAT_METAL,
    PIPE_CATEGORIES,
    category_of_mat,
    is_concrete,
    normalize_category,
    width_row_for,
)
from app.services import project_io
from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas
from app.services.element_library import element_library
from app.viewmodels import unit_vm


def _main_pe(element):
    """构件的主围护原则对象（测试用，同引擎 main_pe 语义）。"""
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import PcpEnclosure

    name = element.main_pe_name or element.pe_name
    return orm.session().scalar(select(PcpEnclosure).where(PcpEnclosure.name == name))


@pytest.mark.parametrize(
    ("mat", "expected"),
    [
        ("Ⅱ级混凝土管", PIPE_CAT_CONCRETE_RIGID),
        ("预应力混凝土管", PIPE_CAT_CONCRETE_RIGID),
        # 含“钢”但是混凝土管：混凝土优先
        ("钢筋混凝土钢承口管", PIPE_CAT_CONCRETE_RIGID),
        ("球墨铸铁管 K9", PIPE_CAT_METAL),
        ("焊接钢管 1.0Mpa", PIPE_CAT_METAL),
        ("给水钢管", PIPE_CAT_METAL),
        # 含“钢”但是塑料管：化学建材优先于金属
        ("钢带增强聚乙烯(PE)管", PIPE_CAT_CHEMICAL),
        ("HDPE承插式双壁缠绕管", PIPE_CAT_CHEMICAL),
        ("硬聚氯乙烯(PVC-U)加筋管", PIPE_CAT_CHEMICAL),
        ("纤维编绕拉挤管BWFRP", PIPE_CAT_CHEMICAL),
        ("", PIPE_CAT_CHEMICAL),
    ],
)
def test_category_of_mat_priority(mat: str, expected: str) -> None:
    assert category_of_mat(mat) == expected


def test_normalize_category_falls_back_to_mat() -> None:
    assert normalize_category("", mat="球墨铸铁管 K9") == PIPE_CAT_METAL
    assert normalize_category("不存在的类别", mat="Ⅱ级混凝土管") == PIPE_CAT_CONCRETE_RIGID
    assert normalize_category("") == PIPE_CAT_DEFAULT
    assert set(PIPE_CATEGORIES) == {
        "混凝土管-刚性接口",
        "混凝土管-柔性接口",
        "金属类管道",
        "化学建材管道",
    }


def test_is_concrete_reads_category_not_name() -> None:
    # 名称是塑料管，但类别被用户改成混凝土：以类别为准
    assert is_concrete(PIPE_CAT_CONCRETE_RIGID, mat="HDPE管")
    assert not is_concrete(PIPE_CAT_METAL, mat="Ⅱ级混凝土管")


def test_width_row_only_depends_on_element_category_and_pipe_category() -> None:
    assert width_row_for(1, PIPE_CAT_METAL) == PIPE_CAT_METAL
    assert width_row_for(1, PIPE_CAT_CHEMICAL) == PIPE_CAT_CHEMICAL
    # 非直埋不看管材类别，按构件类别固定取行
    assert width_row_for(2, PIPE_CAT_METAL) == "包封埋管"
    assert width_row_for(3, PIPE_CAT_METAL) == "箱涵-管廊"
    assert width_row_for(6, PIPE_CAT_CONCRETE_RIGID) == "箱涵-管廊"


def test_workwidth_follows_pipe_category_not_mat() -> None:
    """同一根球墨铸铁管，只改类别 → 面宽表行跟着换（材质名不变）。"""
    widths = {"金属类管道": {600: 900}, "化学建材管道": {600: 300}}
    base = dict(
        category=1,
        con_found=True,
        found_angle=120,
        groove_width="WorkWidth",
        widths=widths,
    )

    metal = resolve_atlas(
        AtlasQuery(**base, pipes=[PipeSpec(mat="球墨铸铁管 K9", dn=600, cat=PIPE_CAT_METAL)])
    )
    chemical = resolve_atlas(
        AtlasQuery(**base, pipes=[PipeSpec(mat="球墨铸铁管 K9", dn=600, cat=PIPE_CAT_CHEMICAL)])
    )
    assert metal.workwidth == 900
    assert chemical.workwidth == 300


def test_snapshot_short_circuit_does_not_touch_atlas(monkeypatch) -> None:
    """a / C1 / C2 / 壁厚齐了就返回快照，连图集目录都不该打开。"""

    def boom():  # pragma: no cover - 真被调用就说明短路失效
        raise AssertionError("参数齐全时不应查图集表")

    monkeypatch.setattr("app.services.atlas.catalog", boom)
    query = AtlasQuery(
        category=1,
        pipes=[PipeSpec(mat="球墨铸铁管 K9", dn=600, t=9.9, cat=PIPE_CAT_METAL)],
        a=110,
        c1=120,
        c2=180,
        widths={"金属类管道": {600: 800}},
        groove_width="WorkWidth",
    )
    at = resolve_atlas(query)
    assert at.a == 110
    assert at.c1 == 120
    assert at.c2 == 180
    assert at.t == 9.9
    assert at.od == pytest.approx(600 + 9.9 * 2)
    assert at.workwidth == 800


def test_insert_template_writes_candidates_and_matches(project) -> None:
    """双击构件库：8 组候选整组写入，参数值按当前围护原则自动选组。

    金属管只显示"不采用混凝土基础"的 4 列，匹配也走这一组（con/plain 快照
    相同），保证高亮的格子就是参数值的来源。
    """
    from app.core.atlas_candidates import nearest_candidate
    from app.services.atlas_match import selected_combo

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋金属类管道", "球墨铸铁管 K9", 0)
    assert template is not None
    assert template.atlas, "资产里应带 8 组快照"

    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None

    # 候选 8 组整组入库（来自资产，不查图集）
    assert len(element.atlas_candidates) == 8

    # 参数值 = 按当前主围护原则自动选组的结果（金属管固定走 plain 组）
    pe = _main_pe(element)
    assert pe is not None
    expected = template.atlas_at(False, int(pe.found_angle))
    assert expected is not None
    key, level = selected_combo(element)
    assert key == f"plain{int(pe.found_angle)}" and level is not None
    row = nearest_candidate(element.atlas_candidates, False, int(pe.found_angle))
    assert row is not None

    params = {(param.key, param.unit): param.value for param in element.params}

    def fmt(value):
        from app.core.evaluator import format_number

        return format_number(value) if value is not None else ""

    # 金属管图集没有 a / C1 列值（候选为 None）→ 参数空 = 引擎回退自动查表
    assert params[("工作面加宽", "mm")] == fmt(row.a)
    assert params[("垫层厚", "mm")] == fmt(row.c1)
    assert params[("基础厚", "mm")] == fmt(row.c2)


def test_candidates_auto_rematch_on_enclosure_change(project) -> None:
    """换围护原则（角度/砼基础变了）→ 参数值自动从候选里重选，候选本身不变。"""
    from app.core.atlas_candidates import nearest_candidate
    from app.services import project_io as pio

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None
    before = {(c.con_found, c.angle, c.a, c.c1, c.c2) for c in element.atlas_candidates}

    pe = _main_pe(element)
    assert pe is not None
    old_angle = int(pe.found_angle)
    new_angle = 180 if old_angle != 180 else 90
    from app.services.principle_edit import apply_enclosure_fields

    apply_enclosure_fields(pe.id, {"found_angle": new_angle})

    row = nearest_candidate(element.atlas_candidates, bool(pe.con_found), new_angle)
    params = {(param.key, param.unit): param.value for param in element.params}
    if row is None:
        assert params[("基础厚", "mm")] == ""  # 全空组 → 回退自动
    else:
        assert params[("基础厚", "mm")] == (
            format_number(row.c2) if row.c2 is not None else ""
        )
    # 候选本身没有被改写
    assert {(c.con_found, c.angle, c.a, c.c1, c.c2) for c in element.atlas_candidates} == before


def test_candidates_auto_rematch_on_category_change(project) -> None:
    """改管材类别（混凝土 ↔ 非混凝土）→ 自动重选候选组（必要时跨组借值）。"""
    from app.core.atlas_candidates import select_candidate

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None

    pipe = element.pipes[0]
    pe = _main_pe(element)
    assert pe is not None

    unit_vm.update_pipe(pipe.id, cat=PIPE_CAT_METAL)
    row, _level = select_candidate(element.atlas_candidates, False, int(pe.found_angle))
    params = {(param.key, param.unit): param.value for param in element.params}
    if row is None:
        # 四级都不命中 → 参数清空（不再保留旧组的值），交给引擎按图集回退
        assert params[("基础厚", "mm")] == ""
    else:
        assert params[("基础厚", "mm")] == (
            format_number(row.c2) if row.c2 is not None else ""
        )


class _FakeCandidate:
    """select_candidate 的纯函数测试替身（只要 con_found / angle / a / c1 / c2）。"""

    def __init__(self, con_found, angle, value=None):
        self.con_found = con_found
        self.angle = angle
        self.a = value
        self.c1 = None
        self.c2 = None


def test_select_candidate_priority_order() -> None:
    """选组顺序：同组精确 → 同组就近 → 跨组精确 → 跨组就近 → 全不命中。"""
    from app.core.atlas_candidates import (
        MATCH_CROSS_EXACT,
        MATCH_CROSS_NEAREST,
        MATCH_SAME_EXACT,
        MATCH_SAME_NEAREST,
        select_candidate,
    )

    rows = [
        _FakeCandidate(True, 90, 1.0),
        _FakeCandidate(True, 120, 2.0),
        _FakeCandidate(False, 150, 3.0),
        _FakeCandidate(False, 180, 4.0),
    ]

    row, level = select_candidate(rows, True, 90)
    assert (row.angle, level) == (90, MATCH_SAME_EXACT)

    # 同组没有 150°：就近取 120°（|Δ|=30，等距时取小角度也落在 120）
    row, level = select_candidate(rows, True, 150)
    assert (row.angle, level) == (120, MATCH_SAME_NEAREST)

    # 另一组有精确的 180°，但同组就近仍优先（同组优先于跨组）
    row, level = select_candidate(rows, True, 180)
    assert (row.angle, level) == (120, MATCH_SAME_NEAREST)

    # 同组全空 → 跨组精确
    empty_same = [
        _FakeCandidate(True, 90),
        _FakeCandidate(True, 120),
        _FakeCandidate(False, 150, 3.0),
        _FakeCandidate(False, 180, 4.0),
    ]
    row, level = select_candidate(empty_same, True, 150)
    assert (row.angle, level) == (150, MATCH_CROSS_EXACT)

    # 同组全空且另一组没有该角度 → 跨组就近
    row, level = select_candidate(empty_same, True, 170)
    assert (row.angle, level) == (180, MATCH_CROSS_NEAREST)

    # 四级都不命中
    assert select_candidate([_FakeCandidate(True, 120)], True, 90) == (None, None)


def test_match_clears_params_when_no_candidate_usable(project) -> None:
    """匹配条件变化后四级都不命中 → 参数清空，绝不保留上一次匹配的旧值。"""
    from app.services.atlas_match import match_atlas_candidates, selected_combo

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None
    pe = _main_pe(element)
    assert pe is not None

    # 插入后应立即匹配到本组该角度的格子
    key, level = selected_combo(element)
    assert key == f"{'con' if pe.con_found else 'plain'}{int(pe.found_angle)}"
    assert level is not None

    # 造出"上一次匹配的旧值"
    for param in element.params:
        if param.key in ("工作面加宽", "垫层厚", "基础厚"):
            param.value = "999"
    # 候选全部改成空 = 四级都不命中（候选行仍在，ensure 不会重建）
    for candidate in element.atlas_candidates:
        candidate.a = candidate.c1 = candidate.c2 = None
    project_io.commit()

    match_atlas_candidates(element)
    params = {(param.key, param.unit): param.value for param in element.params}
    assert params[("工作面加宽", "mm")] == ""
    assert params[("垫层厚", "mm")] == ""
    assert params[("基础厚", "mm")] == ""
    assert selected_combo(element) == (None, None)


def test_match_borrows_other_group_when_same_group_empty(project) -> None:
    """同组候选全空 → 跨组借同角度的值（界面按"跨组"提示），不再留旧值。"""
    from app.core.atlas_candidates import MATCH_CROSS_EXACT
    from app.services.atlas_match import match_atlas_candidates, selected_combo

    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, category=1, name="排管")
    assert element is not None
    unit_vm.create_pipe(element.id, mat="Ⅱ级混凝土管", dn=600, content="1")
    pe = _main_pe(element)
    assert pe is not None

    # 本组（砼基础）全部改空 → 只剩另一组（砂基础）有数据
    for candidate in element.atlas_candidates:
        if candidate.con_found:
            candidate.a = candidate.c1 = candidate.c2 = None
    project_io.commit()

    match_atlas_candidates(element)
    key, level = selected_combo(element)
    assert level == MATCH_CROSS_EXACT
    assert key == f"plain{int(pe.found_angle)}"

    borrowed = next(
        c
        for c in element.atlas_candidates
        if not c.con_found and int(c.angle) == int(pe.found_angle)
    )
    params = {(param.key, param.unit): param.value for param in element.params}
    assert params[("基础厚", "mm")] == format_number(borrowed.c2)


def test_concrete_foundation_falls_back_to_nearest_angle() -> None:
    """砼基础表没有 150°：兜底取角度最近的 120°，不再是 180°。

    旧版是"该角度无此级别时退回不限角度"，`find` 取最后一条命中行——
    恒定为 180°，把 180° 的基础尺寸当 150° 用。
    """
    from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas

    def query(angle: int, *, strict: bool = False) -> AtlasQuery:
        return AtlasQuery(
            category=1,
            pipes=[PipeSpec(mat="Ⅱ级混凝土管", dn=600, cat=PIPE_CAT_CONCRETE_RIGID)],
            con_found=True,
            found_angle=angle,
            size_b=0.6,
            groove_width="WorkWidth",
            strict_angle=strict,
        )

    # 页21 Ⅱ管级 D600 120°：a=130、C1=130、C2=182；页19 180°：C2=365
    exact = resolve_atlas(query(120))
    assert (exact.a, exact.c1, exact.c2) == (130, 130, 182)

    nearest = resolve_atlas(query(150))
    assert (nearest.a, nearest.c1, nearest.c2) == (130, 130, 182), "150° 应就近取 120°"

    # 候选快照用 strict：图集没有该角度的行就什么都不返回（记空）
    strict = resolve_atlas(query(150, strict=True))
    assert (strict.a, strict.c1, strict.c2) == (0, 0, 0)


def test_candidates_leave_missing_angle_empty(project) -> None:
    """候选快照按"图集真有这一行"存：150° 砼基础、Ⅰ级管 90° 都记空。"""
    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, category=1, name="排管")
    assert element is not None
    unit_vm.create_pipe(element.id, mat="Ⅱ级混凝土管", dn=600, content="1")

    candidates = {
        (bool(c.con_found), int(c.angle)): c for c in unit_vm._element(element.id).atlas_candidates
    }
    # 图集有：90/120/180（页20/17/19）
    for angle in (90, 120, 180):
        row = candidates[(True, angle)]
        assert row.c2 is not None, f"{angle}° 砼基础图集有数据"
    # 图集没有 150° 砼基础（06MS201-1 只有 90/120/180）→ 记空，不存就近值
    assert candidates[(True, 150)].c2 is None


def test_fill_missing_candidate_creates_row_and_matches(project) -> None:
    """手填空白候选格：就地建行，并立刻成为匹配目标（补图集缺口）。"""
    from app.core.atlas_candidates import MATCH_SAME_EXACT, MATCH_SAME_NEAREST
    from app.services.atlas_match import selected_combo
    from app.services.principle_edit import apply_enclosure_fields

    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, category=1, name="排管")
    assert element is not None
    unit_vm.create_pipe(element.id, mat="Ⅱ级混凝土管", dn=600, content="1")
    pe = _main_pe(element)
    assert pe is not None

    # 原则改成 150° 砼基础：图集没有这一行 → 就近取 120°
    apply_enclosure_fields(pe.id, {"found_angle": 150})
    assert selected_combo(unit_vm._element(element.id))[1] == MATCH_SAME_NEAREST

    # 手填 con150 的基础厚 → 建行，且立刻变成本组精确匹配
    assert unit_vm.set_atlas_candidate_value(element.id, "con150", "c2", "300")
    filled = unit_vm._element(element.id)
    key, level = selected_combo(filled)
    assert (key, level) == ("con150", MATCH_SAME_EXACT)

    row = next(c for c in filled.atlas_candidates if c.con_found and int(c.angle) == 150)
    assert row.c2 == 300
    params = {(param.key, param.unit): param.value for param in filled.params}
    assert params[("基础厚", "mm")] == "300"

    # 非数字输入不改库
    assert not unit_vm.set_atlas_candidate_value(element.id, "con150", "c2", "abc")
    assert unit_vm._element(element.id).atlas_candidates and next(
        c for c in unit_vm._element(element.id).atlas_candidates
        if c.con_found and int(c.angle) == 150
    ).c2 == 300


def test_prestressed_pipe_has_no_150_degree_table() -> None:
    """预应力砂基础只有 90/120/180°：180° 取 180 表，150° 无数据。

    回归：xlsx 曾把「预应力 180° 表（图集页14）」错标成 150°，代码再用
    "预应力 180° → 改查 150°" 兜回来——结果 150° 拿到的是 180° 的尺寸。
    """
    from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas

    def lookup(angle: int):
        return resolve_atlas(
            AtlasQuery(
                category=1,
                pipes=[PipeSpec(mat="预应力混凝土管", dn=600, cat=PIPE_CAT_CONCRETE_RIGID)],
                con_found=False,
                found_angle=angle,
                size_b=0.6,
                groove_width="WorkWidth",
            )
        )

    # 图集页14 D=600：a=500、C1=110、C2=355、t=55
    assert (lookup(180).a, lookup(180).c1, lookup(180).c2, lookup(180).t) == (500, 110, 355, 55)
    assert lookup(150).c2 == 0 and lookup(150).t == 0


def test_sand_table_120_degree_starts_at_dn400() -> None:
    """图集页9 砂基础 120° 是 D=400~3000：dn=300 无数据（xlsx 曾多一行 D=300）。"""
    from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas

    def lookup(dn: int):
        return resolve_atlas(
            AtlasQuery(
                category=1,
                pipes=[PipeSpec(mat="Ⅱ级混凝土管", dn=dn, cat=PIPE_CAT_CONCRETE_RIGID)],
                con_found=False,
                found_angle=120,
                size_b=dn / 1000,
                groove_width="WorkWidth",
            )
        )

    assert lookup(300).c2 == 0
    # 图集页9：D=400 非预应力 t=40 / a=400 / C1=100 / C2=120；
    # D=600 t=60 / a=500 / C1=100 / C2=180（xlsx 曾误抄成预应力表的 50/400/100/125 与 55/500/110/178）
    assert (lookup(400).t, lookup(400).a, lookup(400).c1, lookup(400).c2) == (40, 400, 100, 120)
    assert (lookup(600).t, lookup(600).a, lookup(600).c1, lookup(600).c2) == (60, 500, 100, 180)


def test_editing_pipe_category_is_normalized(project) -> None:
    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, category=1, name="测试管", pipes=[("Ⅱ级混凝土管", 600, "1")])
    assert element is not None
    pipe = element.pipes[0]
    assert pipe.cat == PIPE_CAT_CONCRETE_RIGID

    unit_vm.update_pipe(pipe.id, cat=PIPE_CAT_METAL)
    assert unit_vm.update_pipe(pipe.id).pipe_category == PIPE_CAT_METAL

    # 非法值按材质折算回混凝土
    unit_vm.update_pipe(pipe.id, cat="瞎写的类别")
    assert unit_vm.update_pipe(pipe.id).pipe_category == PIPE_CAT_CONCRETE_RIGID


def test_enclosure_dialog_save_rematches_candidates(project, qapp) -> None:
    """围护原则编辑对话框保存（UI 路径）→ 引用它的直埋构件自动重选候选组。

    回归：对话框曾直接给 con_found / found_angle 赋值、绕过
    apply_enclosure_fields，导致原则修改后参数值不自动更新。
    """
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
    element = unit_vm.insert_element_template(unit.id, template)
    pe = _main_pe(element)
    old_angle = int(pe.found_angle)
    new_angle = 180 if old_angle != 180 else 90

    dialog = EnclosureEditDialog(pe.id)
    dialog._angle.setCurrentText(str(new_angle))
    dialog._confirm()

    from app.core.atlas_candidates import nearest_candidate

    row = nearest_candidate(element.atlas_candidates, bool(pe.con_found), new_angle)
    params = {(param.key, param.unit): param.value for param in element.params}
    expected = format_number(row.c2) if row is not None and row.c2 is not None else ""
    assert params[("基础厚", "mm")] == expected
    # 就近选组生效：角度真的换到了新值那一组（参数值不再是旧角度的值）
    if row is not None:
        assert params[("基础厚", "mm")] != "" or row.c2 is None


def test_enclosure_dialog_save_rematches_candidates(project, qapp) -> None:
    """围护原则编辑对话框保存（UI 路径）→ 引用它的直埋构件自动重选候选组。

    回归：对话框曾直接给 con_found / found_angle 赋值、绕过
    apply_enclosure_fields，导致原则修改后参数值不自动更新。
    """
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
    element = unit_vm.insert_element_template(unit.id, template)
    pe = _main_pe(element)
    old_angle = int(pe.found_angle)
    new_angle = 180 if old_angle != 180 else 90

    dialog = EnclosureEditDialog(pe.id)
    dialog._angle.setCurrentText(str(new_angle))
    dialog._confirm()

    from app.core.atlas_candidates import nearest_candidate

    row = nearest_candidate(element.atlas_candidates, bool(pe.con_found), new_angle)
    params = {(param.key, param.unit): param.value for param in element.params}
    expected = format_number(row.c2) if row is not None and row.c2 is not None else ""
    assert params[("基础厚", "mm")] == expected
    # 就近选组生效：角度真的换到了新值那一组（参数值不再是旧角度的值）
    if row is not None:
        assert params[("基础厚", "mm")] != "" or row.c2 is None
