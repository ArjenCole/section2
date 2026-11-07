"""图集直取对（direct）测试：快照只存图集直取的两个值，第三个反算。

口径见 ``AtlasCatalog.read``（映射的单一事实源）与 ``scripts/build_element_inventory.py``：

* ``id_t``：图集直接给 iD + t（混凝土 / 顶管 / HDPE 缠绕表），oD = iD+2t 反算；
* ``od_t``：直接给 oD + t（PE 给水 / 钢带 / 金属管表），iD = oD-2t 反算；
* ``od_id``：直接给 oD + iD（PVC-U 加筋 / PE 缠绕等结构壁管，图集 t 不含肋高），
  t = (oD-iD)/2 反算；
* ``""``：旧数据 / 无图集行，维持旧口径（iD/oD 直取样式、t 反算）。

覆盖四条链路：图集行 → direct 映射；双击插入 → 第三值补齐 + 直取对带进条目；
计算表达式基本参数页的直取 / 反算标注；.stn 往返保留标记。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.calc.engine import pipe_direct_labels
from app.core.pipe_category import category_of_mat
from app.services import element_library, project_io
from app.services.atlas import AtlasQuery, PipeSpec, resolve_atlas
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm


# --------------------------------------------------------------------------- #
# 图集行 → direct 映射
# --------------------------------------------------------------------------- #
def _resolve(category: int, mat: str, dn: int):
    """按管材类别 + 材质 + DN 查图集（无快照，走真实表；同构建脚本口径）。"""
    query = AtlasQuery(
        category=category,
        pipes=[PipeSpec(mat=mat, dn=dn, cat=category_of_mat(mat))],
        con_found=True,
        found_angle=120,
        strict_angle=True,
        widths={},
        groove_bs={},
        size_b=dn / 1000.0,  # 同构建脚本 _size_b：直埋 = DN（决定 PE 走表 4 / 6 分流）
    )
    query.a = query.c1 = query.c2 = None
    return resolve_atlas(query)


@pytest.mark.parametrize(
    "category,mat,dn,expected",
    [
        (1, "Ⅱ级混凝土管", 600, "id_t"),  # 表0 砼管砼基础（D=内径，无 oD 列）
        (4, "平口管", 800, "id_t"),  # 表2 砼顶管
        (1, "HDPE双壁缠绕管", 300, "id_t"),  # 表3 HDPE 承插双壁缠绕
        (5, "PE给水管", 200, "od_t"),  # 表4 PE 给水管（D=外径）
        (1, "硬聚氯乙烯(PVC-U)加筋管", 300, "od_id"),  # 表5 加筋（有 oD 列，D=内径）
        (1, "PVC双壁波纹管", 200, "od_t"),  # 表5 双壁波纹（有 oD 列，D=公称外径）
        (1, "聚氯乙烯(PE)缠绕结构壁管A型", 300, "od_id"),  # 表6 缠绕（有 oD 列，D=内径）
        # 注：表 7 钢带增强 PE 的图集级别文字与 resolve_atlas 用的不一致（既有
        # 问题），resolve 查不到行，不纳入直取对断言
        (1, "球墨铸铁管 K9", 100, "od_t"),  # 表8 球墨铸铁
        (1, "焊接钢管1.6Mpa", 100, "od_t"),  # 表9 钢管
    ],
)
def test_atlas_row_direct_pair(category, mat, dn, expected) -> None:
    at = _resolve(category, mat, dn)
    assert at.direct == expected, f"{mat}: direct={at.direct!r} ≠ {expected!r}"
    if at.od <= 0 or at.id <= 0:
        return
    if expected == "od_id":
        # 结构壁管：图集 t 不含肋高 / 结构壁，几何有效壁厚 (oD-iD)/2 与图集 t
        # 是两回事——这正是直取对选 oD+iD 的原因
        assert (at.od - at.id) / 2.0 > 0
    else:
        # id_t / od_t：图集 t 就是几何壁厚，三值关系恒成立
        assert at.od == pytest.approx(at.id + 2 * at.t)


def test_atlas_read_without_row_has_no_direct() -> None:
    from app.services.atlas import AtlasCatalog

    od, inner, t, _a, _c1, _c2, _q, direct = AtlasCatalog.read(None, 0, "")
    assert (od, inner, t) == (-1.0, -1.0, 0.0)
    assert direct == ""


def test_pipe_direct_labels_cover_all_marks() -> None:
    """三种直取对与旧口径的 (来源, 代入式) 标注。"""
    assert pipe_direct_labels("id_t")["oD"] == ("反算：iD+2t", "iD+2*t")
    assert pipe_direct_labels("id_t")["t"] == ("图集直取", "")
    assert pipe_direct_labels("od_t")["iD"] == ("反算：oD-2t", "oD-2*t")
    assert pipe_direct_labels("od_id")["t"] == ("反算：(oD-iD)/2", "(oD-iD)/2")
    # 旧数据（无标记）维持旧口径
    assert pipe_direct_labels("")["t"] == ("（oD-iD）/2", "(oD-iD)/2")
    assert pipe_direct_labels("")["oD"] == ("构件管材·外径", "")


# --------------------------------------------------------------------------- #
# 双击插入：快照只存直取对，第三值在插入时反算补齐
# --------------------------------------------------------------------------- #
def _project_with_unit(tmp_path: Path):
    project_io.new_project(
        NewProjectSpec(
            path=tmp_path / "直取对.stn",
            project_name="直取对",
            segment_names=["标段一"],
            unit_names=["雨水工程"],
            enclosure_name="放坡原则",
            foundation_name="地基原则",
        )
    )
    return project_io.units(project_io.segments()[0].id)[0]


def _first_template(direct: str):
    """构件库里首根管带指定直取对、且有图集参数候选的模板。"""
    for result in element_library.search_templates():
        template = result["template"]
        if template.pipes and template.pipes[0].direct == direct and template.atlas:
            return template
    return None


@pytest.mark.parametrize("direct", ["id_t", "od_t", "od_id"])
def test_insert_template_fills_derived_value(tmp_path, direct) -> None:
    unit = _project_with_unit(tmp_path)
    template = _first_template(direct)
    assert template is not None, f"构件库缺少 {direct} 型模板"
    head = template.pipes[0]

    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None
    pipe = element.pipes[0]
    assert pipe.direct == direct
    # 三个值在插入后都齐（oD = iD + 2t 恒成立）
    assert pipe.od is not None and pipe.inner_d is not None and pipe.t is not None
    assert pipe.od == pytest.approx(pipe.inner_d + 2 * pipe.t)
    # 快照里没存的那个值 == 反算值（直取值与资产一致）
    if direct == "id_t":
        assert head.od is None and head.inner_d is not None
        assert pipe.inner_d == pytest.approx(head.inner_d)
        assert pipe.od == pytest.approx(head.inner_d + 2 * pipe.t)
    elif direct == "od_t":
        assert head.inner_d is None and head.od is not None
        assert pipe.od == pytest.approx(head.od)
        assert pipe.inner_d == pytest.approx(head.od - 2 * pipe.t)
    else:  # od_id
        assert head.od is not None and head.inner_d is not None
        assert pipe.od == pytest.approx(head.od)
        assert pipe.inner_d == pytest.approx(head.inner_d)
        assert pipe.t == pytest.approx((head.od - head.inner_d) / 2.0)
        # 候选参数列的壁厚也按反算值填好（不留空）
        assert all(row.t is not None for row in element.atlas_candidates)


# --------------------------------------------------------------------------- #
# 计算表达式：基本参数页标注直取 / 反算
# --------------------------------------------------------------------------- #
def _results(unit) -> dict[int, dict]:
    _summary, detail = unit_vm.compute_unit(unit.id)
    return {row.id: dq for row, dq in detail}


def test_presentation_marks_direct_and_derived(tmp_path) -> None:
    """id_t 混凝土管：iD / t 标图集直取，oD 代入式显示反算公式。"""
    from app.core.calc.tracer import sorted_items

    unit = _project_with_unit(tmp_path)
    element = unit_vm.create_element(
        unit.id, category=1, name="混凝土管", depth="2.5+0.3", amount="100"
    )
    unit_vm.create_pipe(element.id, mat="Ⅱ级混凝土管", dn=600, content="1")
    pipe = element.pipes[0]
    assert pipe.t is not None  # 候选自动匹配已按图集补齐三值
    pipe.direct = "id_t"
    project_io.commit()

    dq = _results(unit)[element.id]
    quantities = {quantity.key: quantity for quantity in sorted_items(dq)}
    dig = quantities["开挖|Ⅲ类土|m3"]
    view = dig.presentation()
    definitions = {item.symbol: item for item in view.definitions}
    assert definitions["t"].expression == "65"
    assert definitions["t"].source == "图集直取"
    assert definitions["iD"].expression == "600"
    assert definitions["iD"].source == "图集直取"
    # 槽底宽的符号展开不变；完整数值算式里壁厚以直取值出现
    assert definitions["B"].expression == "iD+t*2+a*2+b1*2"
    assert "65*2" in view.full
    assert "(730-600)" not in view.full
    from app.core.evaluator import evaluate

    assert evaluate(view.full) == pytest.approx(dig.value, rel=1e-9)
    # 开挖推导只用 iD + 2t，oD 不再进开挖的基本参数页；用到外径的量
    # （弓形回填）里 oD 以反算式出现
    assert "oD" not in definitions
    backfill = quantities["回填|中粗砂|m3"]
    backfill_defs = {
        item.symbol: item for item in backfill.presentation().definitions
    }
    assert backfill_defs["oD"].expression == "iD+2*t"
    assert backfill_defs["oD"].source == "反算：iD+2t"
    assert backfill_defs["oD"].value == pytest.approx(730)


def test_presentation_marks_derived_inner_diameter(tmp_path) -> None:
    """od_t 管：oD / t 标图集直取，iD 代入式显示 oD-2*t。"""
    from app.core.calc.tracer import sorted_items

    unit = _project_with_unit(tmp_path)
    element = unit_vm.create_element(
        unit.id, category=1, name="PE管", depth="3", amount="100"
    )
    # 显式给 oD / t（直取对），iD 留空由插入归一化反算；不开候选自动匹配，
    # 避免图集匹配回写覆盖测试值
    element2 = unit_vm.insert_element_data(
        unit.id,
        {
            "category": 1,
            "name": "PE给水",
            "depth": "3",
            "amount": "100",
            "pipes": [["PE给水管", "", 200, "1", 3.5, 200.0, None, "od_t"]],
        },
    )
    assert element2 is not None
    assert element is not None
    pipe = element2.pipes[0]
    assert pipe.inner_d == pytest.approx(193.0)  # 200 - 2*3.5 反算补齐
    assert pipe.direct == "od_t"

    dq = _results(unit)[element2.id]
    quantities = {quantity.key: quantity for quantity in sorted_items(dq)}
    dig = quantities["开挖|Ⅲ类土|m3"]
    definitions = {item.symbol: item for item in dig.presentation().definitions}
    assert definitions["t"].expression == "3.5"
    assert definitions["t"].source == "图集直取"
    assert definitions["iD"].expression == "oD-2*t"
    assert definitions["iD"].source == "反算：oD-2t"
    assert definitions["iD"].value == pytest.approx(193)
    # 用到外径的量（弓形回填）里 oD 标图集直取
    backfill = quantities["回填|中粗砂|m3"]
    backfill_defs = {
        item.symbol: item for item in backfill.presentation().definitions
    }
    assert backfill_defs["oD"].expression == "200"
    assert backfill_defs["oD"].source == "图集直取"


def test_presentation_legacy_pipe_keeps_old_forms(tmp_path) -> None:
    """无标记（旧数据 / AI 插入）：维持 iD/oD 直取样式、t 反算的旧口径。"""
    from app.core.calc.tracer import sorted_items

    unit = _project_with_unit(tmp_path)
    element = unit_vm.create_element(
        unit.id, category=1, name="混凝土管", depth="2.5+0.3", amount="100"
    )
    unit_vm.create_pipe(element.id, mat="Ⅱ级混凝土管", dn=600, content="1")
    assert element.pipes[0].direct == ""

    dq = _results(unit)[element.id]
    dig = sorted_items(dq)[0]
    definitions = {item.symbol: item for item in dig.presentation().definitions}
    # 代入式列显示符号式（display），数值式在完整算式里
    assert definitions["t"].expression == "(oD-iD)/2"
    assert definitions["t"].source == "（oD-iD）/2"
    assert definitions["oD"].expression == "730"
    assert definitions["iD"].source == "构件管材·内径"


# --------------------------------------------------------------------------- #
# .stn 往返：直取对标记随工程文件保留
# --------------------------------------------------------------------------- #
def test_stn_roundtrip_keeps_direct(tmp_path) -> None:
    project_io.new_project(
        NewProjectSpec(path=tmp_path / "往返.stn", project_name="往返", unit_names=["雨水工程"])
    )
    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, category=1, name="PE管", depth="3", amount="1")
    unit_vm.create_pipe(element.id, mat="PE给水管", dn=200, t=3.5, od=200.0, direct="od_t")

    path = project_io.current_path()
    project_io.close_project()
    project_io.open_project(path)

    reopened = unit_vm.element_rows(unit.id)[0]
    pipes = unit_vm.pipe_rows(reopened.id)
    assert pipes[0].direct == "od_t"
