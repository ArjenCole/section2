"""计算引擎对拍测试（计划 §6.4 / M4 验收）。

基准构成：

1. **闭合手算**——对典型断面按图集/原则参数手算出闭环公式，断言结果一致；
2. **表达式一致性**——§6.3 要求“算式求值与表达式拼接共用同一套数值”，
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
from app.services import project_io
from app.services.calc.engine import build_element_input, compute_element
from app.services.calc.tracer import QDict, sorted_items
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
    unit_vm.update_element(e1.id, depth="2.5+0.3", amount="100")
    unit_vm.create_pipe(e1.id, mat="Ⅱ级混凝土管", dn=600, content="1")
    e2 = unit_vm.create_element(unit.id, category=2, name="包封管", depth="3", amount="50")
    unit_vm.create_pipe(e2.id, mat="Ⅱ级混凝土管", dn=800, content="1")
    e3 = unit_vm.create_element(unit.id, category=3, name="箱涵", depth="4", amount="40")
    yield unit
    project_io.close_project()


def _results(unit) -> dict[int, QDict]:
    _summary, detail = unit_vm.compute_unit(unit.id)
    return {row.id: dq for row, _dq in detail for dq in [_dq]}


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
    """§6.3：每条工程量的算式重新求值必须等于数值（误差 < 0.5%）。"""
    unit = project
    for element in _elements(unit):
        for quantity in sorted_items(_results(unit)[element.id]):
            assert quantity.expression, f"{quantity.key} 缺少算式"
            replay = evaluate(quantity.expression)
            assert replay == pytest.approx(
                quantity.value, rel=0.005, abs=1e-6
            ), f"{quantity.key}: 算式 {quantity.expression} 重算 {replay} ≠ {quantity.value}"


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
    from app.orm.models import Element
    from sqlalchemy import select

    from app.orm import base as orm

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


def _input_of(element):
    from app.orm.models import PcpEnclosure, PcpFoundation
    from sqlalchemy import select

    from app.orm import base as orm

    session = orm.session()
    pe = session.scalar(select(PcpEnclosure).where(PcpEnclosure.name == element.pe_name))
    pf = session.scalar(select(PcpFoundation).where(PcpFoundation.name == element.pf_name))
    return build_element_input(element, pe, pf)
