"""附属构筑物（mcE7）回归测试。

（多围护/多地基原则引用已在 2.0 取消，相关用例随功能删除；
旧工程多原则条目的迁移拆分见 test_stn_migration.py 的拆条用例。）

覆盖：

* 附属构筑物：非“-”参数逐项出量、井筒方量 = 个数 × max(埋深−井高, 0.4) × 每米方量；
* 类别切换：管道改成构筑物清空管材、参数重置（旧版 mcE7 构造）。
"""



def _first_unit_id() -> int:
    from app.services import project_io

    segment = project_io.segments()[0]
    return project_io.units(segment.id)[0].id


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
            ("名称", "", "圆形雨水检查井DN1000"),
            ("单位", "", "座"),
            ("井筒", "个", "1"),
            ("井筒", "m3/m", "0.71"),
            ("井高", "m", "1.8"),
        ],
        quantities=[
            ("构筑物", "垫层", "m3", "0.22698"),
            ("构筑物", "井壁", "m3", "1.2943"),
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
    # 名称/单位行（单位列留空）+ 默认工程量行
    assert [(param.key, param.unit, param.value) for param in element.params] == [
        ("名称", "", "自定义构筑物"),
        ("单位", "", "个"),
    ]
    assert [
        (quantity.category, quantity.item, quantity.unit, quantity.value)
        for quantity in element.quantities
    ] == [("构筑物", "自定义构筑物", "个", "1")]
    rows = unit_vm.element_rows(unit_id)
    assert rows[0].unit == "个"
