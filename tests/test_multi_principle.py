"""多原则引用（多围护原则 / 多地基原则）与附属构筑物（mcE7）回归测试。

覆盖：

* 多原则引用 CRUD 与旧版 setter 语义（选多原则保留引用、选具体原则重置）；
* 多原则计算：断面量按 (pe 比例 × pf 比例) 加权求和，支撑/管道基础/管材用主原则；
* 附属构筑物：非“-”参数逐项出量、井筒方量 = 个数 × max(埋深−井高, 0.4) × 每米方量；
* 旧 .stn 迁移：PEname / PFname 字典与构筑物类别落库；
* 多原则 Tab 控件的表格交互。
"""



def _first_unit_id() -> int:
    from app.services import project_io

    segment = project_io.segments()[0]
    return project_io.units(segment.id)[0].id


# --------------------------------------------------------------------------- #
# 多原则引用语义
# --------------------------------------------------------------------------- #
def test_show_name_setter_semantics(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import MULTI_PE_TEXT, MULTI_PF_TEXT
    from app.services import project_io
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    pe2 = project_io.create_enclosure("钢板桩")
    assert pe2 is not None
    element = unit_vm.create_element(unit_id, name="管子", depth="2.5", amount="100")
    assert element is not None

    # 初始：单原则引用一行 ratio=1
    refs = unit_vm.principle_ref_rows(element.id, "pe")
    assert len(refs) == 1 and refs[0].ratio == 1.0 and refs[0].is_main

    # 切到多原则：引用行原样保留，show 记为“多围护原则”
    unit_vm.update_element(element.id, pe_name=MULTI_PE_TEXT)
    element = orm.session().get(type(element), element.id)
    assert element.pe_name == MULTI_PE_TEXT
    assert [ref.name for ref in element.pe_refs_sorted()] == ["默认围护原则"]

    # 追加引用
    assert unit_vm.add_principle_ref(element.id, "pe", "钢板桩", 0.4) is not None
    # 重复原则被拒绝
    assert unit_vm.add_principle_ref(element.id, "pe", "钢板桩") is None

    # 删掉主原则引用 → 主原则回落到剩余第一条
    first_ref = unit_vm.principle_ref_rows(element.id, "pe")[0]
    assert unit_vm.remove_principle_ref(first_ref.id) is None
    element = orm.session().get(type(element), element.id)
    assert element.main_pe_name == "钢板桩"

    # 最后一条不可删（旧版“至少需要一种围护原则。”）
    assert unit_vm.remove_principle_ref(
        unit_vm.principle_ref_rows(element.id, "pe")[0].id
    ) == "至少需要一种围护原则。"

    # 切回具体原则：引用重置为该原则 ratio=1
    unit_vm.update_element(element.id, pe_name="默认围护原则")
    element = orm.session().get(type(element), element.id)
    assert element.pe_name == "默认围护原则"
    assert element.main_pe_name == "默认围护原则"
    refs = unit_vm.principle_ref_rows(element.id, "pe")
    assert len(refs) == 1 and refs[0].ratio == 1.0

    # 地基同理（无主原则概念）：多引用 → show 记为“多地基原则”
    unit_vm.update_element(element.id, pf_name=MULTI_PF_TEXT)
    element = orm.session().get(type(element), element.id)
    assert element.pf_name == MULTI_PF_TEXT
    pf_refs = unit_vm.principle_ref_rows(element.id, "pf")
    assert len(pf_refs) == 1 and pf_refs[0].name == "默认地基处理原则"
    assert unit_vm.add_principle_ref(element.id, "pf", "默认地基处理原则1") is not None
    assert unit_vm.remove_principle_ref(
        unit_vm.principle_ref_rows(element.id, "pf")[0].id
    ) is None
    assert unit_vm.remove_principle_ref(
        unit_vm.principle_ref_rows(element.id, "pf")[0].id
    ) == "至少需要一种地基处理原则。"


def test_multi_principle_ratio_weighted_calculation(project) -> None:
    """断面量 = Σ(各 pe 组合量 × 比例)；支撑/管道基础/管材只按主原则、不乘比例。"""
    from app.core.calc.engine import build_element_input, compute_element, resolve_element_principles
    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_BURIED, MULTI_PE_TEXT, PcpEnclosure
    from app.services import project_io
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    pe2 = project_io.create_enclosure("钢板桩")
    # 给钢板桩原则换上钢板桩做法（拉森钢板桩等独有公式键）
    session = orm.session()
    work = pe2.works_sorted()[0]
    work.cpnt_cat = "钢板桩"
    level = work.levels[0]
    level.name = "钢板桩"
    old = level.components[0]
    session.delete(old)
    project_io.component_from_template(session, project_io.component_library(), "Ei", "钢板桩",
                                       enclosure_level_id=level.id)
    project_io.commit()

    element = unit_vm.create_element(
        unit_id, category=CATEGORY_BURIED, name="", depth="2.5", amount="100",
        pipes=[("Ⅰ级混凝土管", 600, "1")],
    )
    assert element is not None
    unit_vm.add_principle_ref(element.id, "pe", "钢板桩", 0.4)
    refs = unit_vm.principle_ref_rows(element.id, "pe")
    unit_vm.update_principle_ref(refs[0].id, ratio=0.6)
    unit_vm.update_element(element.id, pe_name=MULTI_PE_TEXT)
    unit_vm.set_main_pe(element.id, "默认围护原则")

    element = orm.session().get(type(element), element.id)
    pe, pf, pe_refs, pf_refs = resolve_element_principles(element, session)
    assert [r.name for r in element.pe_refs_sorted()] == [
        "默认围护原则", "钢板桩",
    ]
    info = build_element_input(element, pe, pf, pe_refs, pf_refs)
    multi = compute_element(info)
    assert multi is not None

    # 单原则对照
    pe1 = session.query(PcpEnclosure).filter_by(name="默认围护原则").one()
    pe2 = session.query(PcpEnclosure).filter_by(name="钢板桩").one()
    info1 = build_element_input(element, pe1, pf, [(pe1, 1.0)], pf_refs)
    info2 = build_element_input(element, pe2, pf, [(pe2, 1.0)], pf_refs)
    single1 = compute_element(info1)
    single2 = compute_element(info2)
    assert single1 is not None and single2 is not None

    # 开挖：两边同键 → 0.6×r1 + 0.4×r2
    dig_key = "开挖|Ⅲ类土|m3"
    expected = single1.get(dig_key).value * 0.6 + single2.get(dig_key).value * 0.4
    assert abs(multi.get(dig_key).value - expected) < 1e-6 * max(1.0, abs(expected))

    # 管材：只按主原则（默认围护原则）一次计入，不乘比例
    pipe_key = next(key for key in multi.keys() if key.startswith("管材|"))
    assert abs(multi.get(pipe_key).value - single1.get(pipe_key).value) < 1e-9

    # 围护键：钢板桩的拉森钢板桩只来自比例 0.4 的那一份
    sheet_key = next((key for key in multi.keys() if "钢板桩" in key), None)
    if sheet_key is not None and single2.get(sheet_key) is not None:
        assert abs(multi.get(sheet_key).value - single2.get(sheet_key).value * 0.4) < 1e-6 * max(
            1.0, abs(single2.get(sheet_key).value)
        )


# --------------------------------------------------------------------------- #
# 附属构筑物（mcE7）
# --------------------------------------------------------------------------- #
def test_structure_element_compute(project) -> None:
    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_STRUCTURE
    from app.services import project_io
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    element = unit_vm.create_element(
        unit_id, category=CATEGORY_STRUCTURE, name="圆形雨水检查井DN1000",
        depth="3.2", amount="4",
        params=[
            ("-名称", "圆形雨水检查井DN1000"),
            ("-单位", "座"),
            ("构筑物|垫层|m3", "0.22698"),
            ("构筑物|井壁|m3", "1.2943"),
            ("-井筒 个", "1"),
            ("-井筒 m3/m", "0.71"),
            ("-井高 m", "1.8"),
        ],
    )
    assert element is not None

    rows = unit_vm.element_rows(unit_id)
    assert rows[0].unit == "座"  # 旧版 Unit getter：-单位 参数覆盖
    assert rows[0].spec == "圆形雨水检查井DN1000"

    summary, detail = unit_vm.compute_unit(unit_id)
    quantities = {quantity.key: quantity.value for quantity in detail[0][1].items()}
    assert abs(quantities["构筑物|垫层|m3"] - 0.22698 * 4) < 1e-9
    # 井筒 = 个数 × max(埋深 − 井高, 0.4) × 每米方量 × 数量
    expected = 1 * max(3.2 - 1.8, 0.4) * 0.71 * 4
    assert abs(quantities["构筑物|井筒|m3"] - expected) < 1e-9
    assert "构筑物|井壁|m3" in summary.keys()


def test_structure_category_switch_resets_params(project) -> None:
    """管道改成构筑物：清空管材、参数重置为 -名称/-单位（旧版 mcE7 构造）。"""
    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_BURIED, CATEGORY_STRUCTURE
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    element = unit_vm.create_element(
        unit_id, category=CATEGORY_BURIED, depth="2.5", amount="100",
        pipes=[("Ⅰ级混凝土管", 600, "1")],
    )
    unit_vm.update_element(element.id, category=CATEGORY_STRUCTURE)
    element = orm.session().get(type(element), element.id)
    assert list(element.pipes) == []
    assert [(param.key, param.value) for param in element.params] == [
        ("-名称", "自定义构筑物"),
        ("-单位", "个"),
    ]
    rows = unit_vm.element_rows(unit_id)
    assert rows[0].unit == "个"


# --------------------------------------------------------------------------- #
# 旧工程迁移：多原则引用 + 构筑物
# --------------------------------------------------------------------------- #
def test_migrate_multi_principle_and_structure(tmp_path) -> None:
    from pathlib import Path

    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_STRUCTURE, MULTI_PE_TEXT
    from app.services import project_io, stn_migration
    from app.viewmodels import unit_vm

    source = Path(__file__).parent / "fixtures" / "legacy" / "样例-多原则与构筑物.stn"
    target = tmp_path / "migrated.stn2"
    report = stn_migration.migrate(source, target)
    # 样例的钢板桩构件参数不全，按构件库默认值补齐的提示属正常行为；
    # 不允许出现原则悬空 / 跳过类警告
    assert not [w for w in report.warnings if "不存在" in w or "未指定" in w], report.warnings
    project_io.open_project(target)
    try:
        segment = project_io.segments()[0]
        unit = project_io.units(segment.id)[0]
        elements = unit_vm.element_rows(unit.id)
        assert [row.category for row in elements] == [1, 1, CATEGORY_STRUCTURE]

        # 多原则构件：引用行 + show 名 + 主原则
        multi = orm.session().get(type(unit), unit.id)
        from sqlalchemy import select

        from app.core.models.models import Element

        rows = list(orm.session().scalars(select(Element).order_by(Element.order_no)))
        multi_element = rows[1]
        assert multi_element.pe_name == MULTI_PE_TEXT
        assert multi_element.main_pe_name == "钢板桩"
        assert [(ref.name, round(ref.ratio, 2)) for ref in multi_element.pe_refs_sorted()] == [
            ("放坡开挖", 0.6), ("钢板桩", 0.4),
        ]

        # 构筑物构件：参数原文迁移，计算含井筒方量
        well = rows[2]
        assert well.name == "圆形雨水检查井DN1000"
        summary, detail = unit_vm.compute_unit(unit.id)
        well_quantities = {q.key: q.value for q in detail[2][1].items()}
        assert abs(well_quantities["构筑物|垫层|m3"] - 0.226980069221863 * 4) < 1e-9
        assert abs(well_quantities["构筑物|井筒|m3"] - 1 * max(3.2 - 1.8, 0.4) * 0.71 * 4) < 1e-9
        assert well_quantities["构筑物|井壁钢筋|kg"] == 205.998580193403 * 4
    finally:
        project_io.close_project()


# --------------------------------------------------------------------------- #
# 多原则 Tab 控件
# --------------------------------------------------------------------------- #
def test_multi_principle_tab_widget(qapp, project, monkeypatch) -> None:
    from PySide6.QtWidgets import QComboBox

    from app.core.models import base as orm
    from app.core.models.models import MULTI_PE_TEXT
    from app.services import project_io
    from app.views.panels.multi_principle_tab import MultiPrincipleTab

    unit_id = _first_unit_id()
    project_io.create_enclosure("钢板桩")
    from app.viewmodels.unit_vm import create_element

    element = create_element(unit_id, name="管子", depth="2.5", amount="100")
    tab = MultiPrincipleTab("pe")
    tab.set_element(element.id)
    assert not tab._element_active()  # 尚未切多原则：显示占位说明

    from app.viewmodels import unit_vm as _unit_vm

    _unit_vm.update_element(element.id, pe_name=MULTI_PE_TEXT)
    tab.reload()
    assert tab._element_active()
    assert tab._table.rowCount() == 1

    tab._add_ref()
    assert tab._table.rowCount() == 2
    # 比例编辑
    tab._table.item(1, 1).setText("0.4")
    from app.viewmodels.unit_vm import principle_ref_rows

    ratios = sorted(round(ref.ratio, 2) for ref in principle_ref_rows(element.id, "pe"))
    assert ratios == [0.4, 1.0]
    # 主要原则下拉
    tab._main_combo.setCurrentText("钢板桩")
    element_row = orm.session().get(type(element), element.id)
    assert element_row.main_pe_name == "钢板桩"
    # 全删被拦截（旧版“至少需要一种围护原则。”弹窗）：批量删两条 → 第二条被拦
    blocked: list[str] = []
    monkeypatch.setattr(
        "app.views.panels.multi_principle_tab.FramelessMessageBox.information",
        lambda *_args, **_kwargs: blocked.append("blocked"),
    )
    tab._table.selectAll()
    tab._delete_selected()
    tab._delete_selected()
    assert len(blocked) >= 1
    assert len(principle_ref_rows(element.id, "pe")) == 1
    tab.set_element(None)
    assert not tab._element_active()
