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
    """双击构件库：8 组候选整组写入，参数值按当前围护原则自动选组。"""
    from app.core.atlas_candidates import nearest_candidate

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋金属类管道", "球墨铸铁管 K9", 0)
    assert template is not None
    assert template.atlas, "资产里应带 8 组快照"

    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None

    # 候选 8 组整组入库（来自资产，不查图集）
    assert len(element.atlas_candidates) == 8

    # 参数值 = 按当前主围护原则自动选组的结果
    pe = _main_pe(element)
    assert pe is not None
    expected = template.atlas_at(bool(pe.con_found), int(pe.found_angle))
    assert expected is not None
    row = nearest_candidate(element.atlas_candidates, bool(pe.con_found), int(pe.found_angle))
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
    """改管材类别（混凝土 ↔ 非混凝土）→ 自动重选候选组。"""
    from app.core.atlas_candidates import nearest_candidate

    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None

    pipe = element.pipes[0]
    pe = _main_pe(element)
    assert pe is not None

    unit_vm.update_pipe(pipe.id, cat=PIPE_CAT_METAL)
    row = nearest_candidate(element.atlas_candidates, False, int(pe.found_angle))
    params = {(param.key, param.unit): param.value for param in element.params}
    if row is None:
        # Ⅱ级 Dn150 的非砼组（砂基础）图集无数据：匹配不到 → 参数值保持原状
        assert params[("基础厚", "mm")] != ""
    else:
        assert params[("基础厚", "mm")] == (
            format_number(row.c2) if row.c2 is not None else ""
        )


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
