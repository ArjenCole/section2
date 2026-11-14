"""附属构筑物（mcE7）回归测试。

（多围护/多地基原则引用已在 2.0 取消，相关用例随功能删除；
旧工程多原则条目的迁移拆分见 test_stn_migration.py 的拆条用例。）

覆盖：

* 附属构筑物：非“-”参数逐项出量、井筒方量 = 个数 × max(埋深−井高, 0.4) × 每米方量；
* 类别切换：管道改成构筑物清空管材、参数重置（旧版 mcE7 构造）；
* 主表格规格 / 单位列直编辑（写回“名称 / 单位”参数行）；
* 主表格插入空行（附属构筑物占位构件）。
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


def test_structure_spec_unit_direct_edit(project) -> None:
    """主表格规格 / 单位列直编辑：内容写回“名称 / 单位”参数行并回显。

    替代旧版在构件参数表改“名称 / 单位”行的入口（这两行不再进参数表）。
    """
    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_STRUCTURE
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    element = unit_vm.create_element(unit_id, category=CATEGORY_STRUCTURE, name="检查井")
    assert element is not None

    unit_vm.set_structure_spec(element.id, "圆形雨水检查井 DN1000")
    unit_vm.set_structure_unit(element.id, "座")
    rows = unit_vm.element_rows(unit_id)
    assert rows[0].spec == "圆形雨水检查井 DN1000"
    assert rows[0].unit == "座"
    # 写回的是“名称 / 单位”参数行（存储载体与 .stn 导出格式不变）
    element = orm.session().get(type(element), element.id)
    assert [(param.key, param.unit, param.value) for param in element.params] == [
        ("名称", "", "圆形雨水检查井 DN1000"),
        ("单位", "", "座"),
    ]

    # 清空合法：单位显示空（类别默认“个”只在参数行缺失时兜底）
    unit_vm.set_structure_unit(element.id, "")
    rows = unit_vm.element_rows(unit_id)
    assert rows[0].unit == ""
    # 切成其它类别后调用直接忽略：规格 / 单位列只对附属构筑物开放
    unit_vm.update_element(element.id, category=1)
    unit_vm.set_structure_spec(element.id, "不应生效")
    unit_vm.set_structure_unit(element.id, "不应生效")
    element = orm.session().get(type(element), element.id)
    assert all(param.key not in ("名称", "单位") for param in element.params)


def test_structure_empty_row_defaults(project) -> None:
    """主表格插入空行：附属构筑物占位构件——规格 / 单位空、埋深 / 数量 0、
    无工程量行（用户在“工程量”页自行增加），原则自动取库第一条。"""
    from app.core.models.models import CATEGORY_STRUCTURE
    from app.services import project_io
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    element = unit_vm.insert_empty_row(unit_id)
    assert element is not None and element.category == CATEGORY_STRUCTURE
    rows = unit_vm.element_rows(unit_id)
    assert len(rows) == 1
    assert rows[0].spec == ""
    assert rows[0].unit == ""  # 空值原样显示，不回退类别默认“个”
    assert rows[0].depth == "0" and rows[0].amount == "0"
    assert rows[0].pe_name == project_io.enclosure_names()[0]
    # 名称 / 单位参数行仍建（存空值，主表格直编辑写回）；无默认工程量行
    assert [(param.key, param.unit, param.value) for param in element.params] == [
        ("名称", "", ""),
        ("单位", "", ""),
    ]
    assert unit_vm.quantity_rows(element.id) == []
    # 数量为 0：不出量（与既有构筑物行为一致）
    _summary, detail = unit_vm.compute_unit(unit_id)
    assert list(detail[0][1].items()) == []


def test_structure_empty_row_insert_position(project) -> None:
    """插入空行的落点：指定锚点构件时插到它之前（后续行整体后移），无锚点追加末尾。"""
    from app.viewmodels import unit_vm

    unit_id = _first_unit_id()
    a = unit_vm.create_element(unit_id, name="A", pipes=[("Ⅱ级混凝土管", 600, "1")])
    b = unit_vm.create_element(unit_id, name="B", pipes=[("Ⅱ级混凝土管", 600, "1")])
    assert a is not None and b is not None

    empty = unit_vm.insert_empty_row(unit_id, before_element_id=b.id)
    assert empty is not None
    rows = unit_vm.element_rows(unit_id)
    assert [row.id for row in rows] == [a.id, empty.id, b.id]

    tail = unit_vm.insert_empty_row(unit_id)
    assert tail is not None
    rows = unit_vm.element_rows(unit_id)
    assert [row.id for row in rows] == [a.id, empty.id, b.id, tail.id]
