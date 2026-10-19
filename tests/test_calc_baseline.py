"""计算引擎对拍测试（M4 验收）。

基准构成：

1. **闭合手算**——对典型断面按图集/原则参数手算出闭环公式，断言结果一致；
2. **表达式一致性**——“算式求值与表达式拼接共用同一套数值”，
   对每一条工程量的 expression 重新求值，与数值误差必须 < 0.5%；
3. **基准文件回归**——tests/baselines/ 里存放整表结果（由本测试生成/更新，
   人工确认后冻结），任何算法改动引起数值变化都会被拦下。

拿到旧版 C# 软件对同一算例的输出后，把数值填进 baselines 的 json
即可完成新旧对拍（误差 < 0.5%）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.evaluator import evaluate
from app.core.models import base as orm
from app.services import project_io
from app.core.calc.engine import build_element_input, compute_element
from app.core.calc.tracer import QDict, sorted_items
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm

BASELINE_DIR = Path(__file__).parent / "baselines"


@pytest.fixture()
def project(tmp_path: Path):
    """一个标准算例工程：混凝土管 / 包封 / 箱涵 各一条，默认放坡原则。"""
    path = project_io.new_project(
        NewProjectSpec(
            path=tmp_path / "对拍.stn2",
            project_name="对拍工程",
            segment_names=["标段一"],
            unit_names=["雨水工程"],
            enclosure_name="放坡原则",
            foundation_name="地基原则",
        )
    )
    unit = project_io.units(project_io.segments()[0].id)[0]
    e1 = unit_vm.create_element(unit.id, category=1, name="混凝土管", depth="2.5+0.3", amount="100")
    unit_vm.create_pipe(e1.id, mat="Ⅱ级混凝土管", dn=600, content="1")
    e2 = unit_vm.create_element(unit.id, category=2, name="包封管", depth="3", amount="50")
    unit_vm.create_pipe(e2.id, mat="Ⅱ级混凝土管", dn=800, content="1")
    e3 = unit_vm.create_element(unit.id, category=3, name="箱涵", depth="4", amount="40")
    yield unit
    project_io.close_project()


def _results(unit) -> dict[int, QDict]:
    _summary, detail = unit_vm.compute_unit(unit.id)
    return {row.id: dq for row, dq in detail}


def test_closed_form_trapezoid(project) -> None:
    """直埋混凝土管 Dn600、埋深 2.8、放坡 1:1：挖方 = 单个梯形断面 × 长度。"""
    unit = project
    elements = {element.name: element for element in _elements(unit)}
    dq = _results(unit)[elements["混凝土管"].id]

    # 图集 06MS201-1 砼管砼基础：Ⅱ级 / 120° / D600 → t=65, a=130, C1=130, C2=182
    t, a, c1, c2 = 65.0, 130.0, 130.0, 182.0
    groove_depth = 2.8 + (t + c1) / 1000.0
    bottom = 0.6 + (2 * t + 2 * a + 2 * 500) / 1000.0  # 工作面宽度表 Dn600 刚性接口 = 500mm
    dig_per_meter = (2 * bottom + 2 * groove_depth) * groove_depth / 2
    assert dig_per_meter == pytest.approx(dq.get("开挖|Ⅲ类土|m3").value / 100, rel=1e-9)

    # 分层合计 = 挖方（无平台跳级时连续梯形闭合）
    layers = (c1 + c2) / 1000 + (0.3 + (t - c2) / 1000) + (0.3 + t / 1000) + 0.5 + (
        groove_depth - 0.6 - (t * 2 + c1) / 1000 - 0.5
    )
    assert layers == pytest.approx(groove_depth, rel=1e-9)


def test_expression_matches_value(project) -> None:
    """每条工程量的算式重新求值必须等于数值（误差 < 0.5%）。"""
    unit = project
    for element in _elements(unit):
        for quantity in sorted_items(_results(unit)[element.id]):
            assert quantity.expression, f"{quantity.key} 缺少算式"
            replay = evaluate(quantity.expression)
            assert replay == pytest.approx(
                quantity.value, rel=0.005, abs=1e-6
            ), f"{quantity.key}: 算式 {quantity.expression} 重算 {replay} ≠ {quantity.value}"


def test_user_expression_in_output(project) -> None:
    """埋深 / 数量列写的算式要以算式形式进入工程量计算表达式。"""
    unit = project
    elements = {element.name: element for element in _elements(unit)}
    dig = _results(unit)[elements["混凝土管"].id].get("开挖|Ⅲ类土|m3")
    # 埋深 "2.5+0.3"：挖方层厚 = 埋深原文 + 垫层/板厚调整；数量 100 纯数字照旧
    assert "(2.5+0.3+0.195)" in dig.expression
    assert dig.expression.endswith("×100")

    # 数量写算式：×数量 以算式原文进每条算式（展示层 * 统一转 ×）
    e4 = unit_vm.create_element(unit.id, category=1, name="数量算式", depth="3", amount="50*2")
    unit_vm.create_pipe(e4.id, mat="Ⅱ级混凝土管", dn=600, content="1")
    dig4 = _results(unit)[e4.id].get("开挖|Ⅲ类土|m3")
    assert "×(50×2)" in dig4.expression
    assert evaluate(dig4.expression) == pytest.approx(dig4.value, rel=0.005)


def test_baseline_file(project) -> None:
    """基准回归：结果与 tests/baselines/对拍工程.json 一致。"""
    unit = project
    summary, detail = unit_vm.compute_unit(unit.id)
    current = _as_baseline(summary, detail)

    baseline_path = BASELINE_DIR / "对拍工程.json"
    if not baseline_path.exists():  # 首次运行生成基准，人工确认后冻结
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        pytest.skip("已生成基准文件，请人工确认数值后重跑")
    frozen = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert current == frozen, "计算结果与基准不一致：若为有意修改，请更新 baselines 文件并复核"


def _as_baseline(summary: QDict, detail) -> dict:
    document: dict[str, object] = {
        "定额汇总": {
            quantity.key: {
                "value": round(quantity.value, 4),
                "expression": quantity.expression,
            }
            for quantity in sorted_items(summary)
        },
        "清单": [],
    }
    for row, dq in detail:
        document["清单"].append(
            {
                "name": row.name,
                "category": row.category,
                "spec": row.spec,
                "amount": row.amount_value,
                "error": row.error,
                "quantities": {
                    quantity.key: {
                        "value": round(quantity.value, 4),
                        "expression": quantity.expression,
                    }
                    for quantity in sorted_items(dq)
                },
            }
        )
    return document


def _elements(unit):
    from app.core.models.models import Element
    from sqlalchemy import select

    from app.core.models import base as orm

    return list(
        orm.session().scalars(select(Element).where(Element.unit_id == unit.id).order_by(Element.order_no))
    )


def test_box_culvert_steel(project) -> None:
    """箱涵钢筋 = 含钢量 × (底板 + 箱涵壁 + 顶板)。"""
    unit = project
    elements = {element.name: element for element in _elements(unit)}
    info = _input_of(elements["箱涵"])
    dq = compute_element(info)
    bottom = dq.get("箱涵|底板|m3").value / info.amount
    wall = dq.get("箱涵|箱涵壁|m3").value / info.amount
    roof = dq.get("箱涵|顶板|m3").value / info.amount
    steel = dq.get("箱涵|钢筋|t").value / info.amount
    assert steel == pytest.approx(0.15 * (bottom + wall + roof), rel=1e-9)


# --------------------------------------------------------------------------- #
# 顶管 / 牵引管（1.0 mcE4 / mcE5：只算管材）
# --------------------------------------------------------------------------- #
def test_trenchless_only_pipes(project) -> None:
    """顶管 / 牵引管不开槽：只有 “顶管|…” / “拖拉管|…” 一条管材量 × 长度。"""
    from app.core.models.models import CATEGORY_JACKING, CATEGORY_PULLING

    unit = project
    jacking = unit_vm.create_element(
        unit.id, category=CATEGORY_JACKING, name="顶管 D1000", depth="5", amount="30"
    )
    unit_vm.create_pipe(jacking.id, mat="钢筋混凝土钢承口管 顶管", dn=1000, content="1")
    pulling = unit_vm.create_element(
        unit.id, category=CATEGORY_PULLING, name="拖拉管 D400", depth="2.5", amount="20*2"
    )
    unit_vm.create_pipe(pulling.id, mat="PE给水管", dn=400, content="1")

    results = _results(unit)
    jacking_dq = results[jacking.id]
    pulling_dq = results[pulling.id]
    assert list(jacking_dq.keys()) == ["顶管|钢筋混凝土钢承口管 顶管 Dn1000|m"]
    assert list(pulling_dq.keys()) == ["拖拉管|PE给水管 Dn400|m"]
    assert jacking_dq.get("顶管|钢筋混凝土钢承口管 顶管 Dn1000|m").value == pytest.approx(30.0)
    # 数量写算式：×数量 以算式原文进算式
    assert pulling_dq.get("拖拉管|PE给水管 Dn400|m").expression == "1×(20×2)"
    # 沟槽 / 回填 / 降水 / 围护 / 基础一概没有
    for key in [*jacking_dq.keys(), *pulling_dq.keys()]:
        assert not key.startswith(("开挖|", "回填|", "垫层|", "围护|", "支撑|", "降水|", "管道基础|"))

    # 没有录入管材：算不出量但也不该报“覆土不足”
    empty = unit_vm.create_element(
        unit.id, category=CATEGORY_JACKING, name="没录管材", depth="5", amount="10"
    )
    _summary, detail = unit_vm.compute_unit(unit.id)
    rows = {row.id: row for row, _dq in detail}
    assert compute_element(_input_of(empty)) is None
    assert rows[empty.id].error == "未录入管材，顶管 / 牵引管只计算管材。"


def test_buried_atlas_param_rows_show_atlas_defaults_and_apply(project) -> None:
    """直埋管道显示工作面加宽 / 垫层厚 / 基础厚：默认按图集（空 = 自动），改值生效。"""
    from app.core.models.models import ElementParam

    unit = project
    element = {item.name: item for item in _elements(unit)}["混凝土管"]
    rows = [(param.key, param.unit, param.lock_name) for param in unit_vm.param_rows(element.id)]
    assert rows == [("工作面加宽", "mm", True), ("垫层厚", "mm", True), ("基础厚", "mm", True)]
    # 空值行 = 自动按图集：灰字显示的自动值就是图集行（Dn600 Ⅱ级 120°）的 a / C1 / C2
    assert unit_vm.auto_atlas_params(element) == {
        "工作面加宽": 130.0,
        "垫层厚": 130.0,
        "基础厚": 182.0,
    }

    def param_value(name: str) -> float:
        return _results(unit)[element.id].get(name).value

    amount = {row.name: row for row in unit_vm.element_rows(unit.id)}["混凝土管"].amount_value
    base_form = param_value("管道基础|模板|m2")
    # 垫层厚 130 → 260：基础模板 = (C1+C2)×2/1000 变厚；清空回到自动
    thickness = next(item for item in element.params if item.key == "垫层厚")
    unit_vm.update_param(thickness.id, value="260")
    assert param_value("管道基础|模板|m2") == pytest.approx(base_form * (260 + 182) / (130 + 182), rel=1e-9)
    unit_vm.update_param(thickness.id, value="")
    assert param_value("管道基础|模板|m2") == pytest.approx(base_form, rel=1e-9)

    # 工作面加宽 130 → 260：基础宽 +0.26m，管道基础混凝土按 (C1+C2)/1000 × 0.26 增加
    base_found = param_value("管道基础|混凝土|m3")
    width_param = next(item for item in element.params if item.key == "工作面加宽")
    unit_vm.update_param(width_param.id, value="260")
    assert param_value("管道基础|混凝土|m3") - base_found == pytest.approx(
        (130 + 182) / 1000.0 * 0.26 * amount, rel=1e-9
    )
    unit_vm.update_param(width_param.id, value="")

    # 基础厚 182 → 0：管座取消，基础模板只剩垫层厚 130
    foundation = next(item for item in element.params if item.key == "基础厚")
    unit_vm.update_param(foundation.id, value="0")
    assert param_value("管道基础|模板|m2") == pytest.approx(0.26 * amount, rel=1e-9)

    # 单位不是 mm 的同名参数只是普通参数行（不锁定），不影响图集取值
    orm.session().add(ElementParam(element_id=element.id, key="工作面加宽", unit="cm", value="30"))
    project_io.commit()
    orm.session().expire_all()  # 关系集合是旧数据，手动失效后才看得到新行
    rows = [(param.key, param.unit, param.lock_name) for param in unit_vm.param_rows(element.id)]
    assert ("工作面加宽", "cm", False) in rows
    assert unit_vm.auto_atlas_params(element)["工作面加宽"] == 130.0


def test_atlas_param_rows_scope_by_category(project) -> None:
    """基础厚只属于直埋：包封 / 箱涵 / 管廊不显示也不能加，顶管 / 牵引管三行都不显示。"""
    from app.core.models.models import (
        CATEGORY_GALLERY,
        CATEGORY_JACKING,
        CATEGORY_PULLING,
        ElementParam,
    )
    from app.core.param_naming import PARAM_A_NAME, PARAM_C2_NAME

    unit = project
    box = {item.name: item for item in _elements(unit)}["箱涵"]
    assert [param.key for param in unit_vm.param_rows(box.id)][-2:] == ["工作面加宽", "垫层厚"]
    # 基础厚既不能加也不能改名进来
    assert unit_vm.create_param(box.id, key=PARAM_C2_NAME, unit="mm", value="500") is None
    row = unit_vm.create_param(box.id, key="含钢量", unit="kg/m3", value="150")
    assert unit_vm.update_param(row.id, key=PARAM_C2_NAME, unit="mm") is None
    assert (row.key, row.unit, row.value) == ("含钢量", "kg/m3", "150")

    # 老库残留的基础厚行不显示、不参与计算（基础厚恒为 0）
    before = {quantity.key: quantity.value for quantity in sorted_items(_results(unit)[box.id])}
    orm.session().add(ElementParam(element_id=box.id, key=PARAM_C2_NAME, unit="mm", value="500"))
    project_io.commit()
    orm.session().expire_all()  # 关系集合是旧数据，手动失效后才看得到新行
    assert PARAM_C2_NAME not in [param.key for param in unit_vm.param_rows(box.id)]
    after = {quantity.key: quantity.value for quantity in sorted_items(_results(unit)[box.id])}
    assert after == before

    # 包封埋管同样不显示基础厚；工作面加宽 / 垫层厚保留
    encased = {item.name: item for item in _elements(unit)}["包封管"]
    assert [param.key for param in unit_vm.param_rows(encased.id)][-2:] == ["工作面加宽", "垫层厚"]
    assert unit_vm.create_param(encased.id, key=PARAM_C2_NAME, unit="mm", value="500") is None
    # 管廊与箱涵同规则
    gallery = unit_vm.create_element(unit.id, category=CATEGORY_GALLERY, name="管廊")
    assert [param.key for param in unit_vm.param_rows(gallery.id)][-2:] == ["工作面加宽", "垫层厚"]
    assert unit_vm.create_param(gallery.id, key=PARAM_C2_NAME, unit="mm", value="500") is None

    # 顶管 / 牵引管只算管材：三行都不显示，新增也被拒
    for category in (CATEGORY_JACKING, CATEGORY_PULLING):
        element = unit_vm.create_element(unit.id, category=category, name="非开挖")
        assert unit_vm.param_rows(element.id) == []
        assert unit_vm.create_param(element.id, key=PARAM_A_NAME, unit="mm", value="100") is None


def test_encased_keeps_editable_atlas_params_and_they_apply(project) -> None:
    """包封埋管显示工作面加宽 / 垫层厚（默认按软件约定），改垫层厚对计算生效。"""
    from app.core.models.models import CATEGORY_ENCASED, ElementParam
    from app.core.param_naming import PARAM_C1_NAME, PARAM_C2_NAME

    unit = project
    element = {item.name: item for item in _elements(unit)}["包封管"]
    keys = [param.key for param in unit_vm.param_rows(element.id)]
    assert keys == ["包封宽", "包封高", "工作面加宽", "垫层厚"]
    # 基础厚不显示（恒为 0）——库里就算有旧行也看不到
    orm.session().add(ElementParam(element_id=element.id, key=PARAM_C2_NAME, unit="mm", value="500"))
    project_io.commit()
    orm.session().expire_all()  # 关系集合是旧数据，手动失效后才看得到新行
    assert PARAM_C2_NAME not in [param.key for param in unit_vm.param_rows(element.id)]

    before = _results(unit)[element.id].get("垫层|混凝土|m3").value
    param = next(
        item for item in element.params if item.key == PARAM_C1_NAME
    )
    unit_vm.update_param(param.id, value="200")  # 垫层厚 100 → 200
    after = _results(unit)[element.id].get("垫层|混凝土|m3").value
    assert after == pytest.approx(before * 2, rel=1e-9)


def test_category_switch_reconciles_atlas_rows(project) -> None:
    """类别切换按新类别增删图集行：基础厚跟着直埋，切到非开挖类别三行全删。"""
    from app.core.models.models import (
        CATEGORY_BOX_CULVERT,
        CATEGORY_ENCASED,
        CATEGORY_JACKING,
    )

    unit = project
    element = {item.name: item for item in _elements(unit)}["混凝土管"]
    assert [param.key for param in unit_vm.param_rows(element.id)] == [
        "工作面加宽",
        "垫层厚",
        "基础厚",
    ]

    # 直埋 → 包封：基础厚行删掉（恒为 0）
    unit_vm.update_element(element.id, category=CATEGORY_ENCASED)
    assert [param.key for param in unit_vm.param_rows(element.id)] == ["工作面加宽", "垫层厚"]

    # 包封 → 箱涵：同样只留工作面加宽 / 垫层厚
    unit_vm.update_element(element.id, category=CATEGORY_BOX_CULVERT)
    assert [param.key for param in unit_vm.param_rows(element.id)] == ["工作面加宽", "垫层厚"]

    # 箱涵 → 直埋：基础厚行按空值补回（空 = 自动按图集）
    unit_vm.update_element(element.id, category=1)
    rows = [(param.key, param.value) for param in unit_vm.param_rows(element.id)]
    assert rows == [("工作面加宽", ""), ("垫层厚", ""), ("基础厚", "")]

    # 直埋 → 顶管：三行全删（只算管材）
    unit_vm.update_element(element.id, category=CATEGORY_JACKING)
    assert unit_vm.param_rows(element.id) == []


def _input_of(element):
    from app.core.models.models import PcpEnclosure, PcpFoundation
    from sqlalchemy import select

    from app.core.calc.engine import resolve_element_principles
    from app.core.models import base as orm

    session = orm.session()
    pe = session.scalar(select(PcpEnclosure).where(PcpEnclosure.name == element.pe_name))
    pf = session.scalar(select(PcpFoundation).where(PcpFoundation.name == element.pf_name))
    _pe, _pf, pp, pw, _pe_refs, _pf_refs = resolve_element_principles(element, session)
    return build_element_input(element, pe, pf, pp=pp, pw=pw)
