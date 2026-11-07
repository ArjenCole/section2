"""工程数量表导出（services.summary.export_quantity_tables）测试。

覆盖：分单位工程 / 合并两种口径的 sheet 结构与加总规则、单位工程列、
清单项目行浅蓝标记、导出对话框的树状勾选。
"""

from pathlib import Path

import openpyxl

from app.services import project_io, summary
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm


def _two_unit_project(tmp_path: Path) -> list[int]:
    """两个单位工程、各一条附属构筑物构件（定额量确定，不依赖原则）。

    雨水工程：垫层 2.0 × 数量 2 = 4；污水工程：垫层 1.0 × 数量 3 = 3。
    """
    path = tmp_path / "导出测试.stn"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程", "污水工程"]))
    segment = project_io.segments()[0]
    units = project_io.units(segment.id)
    from app.core.models.models import CATEGORY_STRUCTURE

    for unit, name, per_amount, amount in (
        (units[0], "雨水检查井", "2.0", "2"),
        (units[1], "污水检查井", "1.0", "3"),
    ):
        element = unit_vm.create_element(
            unit.id,
            category=CATEGORY_STRUCTURE,
            name=name,
            depth="3.2",
            amount=amount,
            params=[("名称", "", name), ("单位", "", "座")],
            quantities=[("构筑物", "垫层", "m3", per_amount)],
        )
        assert element is not None
    return [unit.id for unit in units]


def _quota_rows(sheet) -> list:
    return [row for row in sheet.iter_rows(min_row=2)]


# --------------------------------------------------------------------------- #
# 分单位工程导出（默认口径：行前带“单位工程”列）
# --------------------------------------------------------------------------- #
def test_export_per_unit(tmp_path) -> None:
    unit_ids = _two_unit_project(tmp_path)
    result = summary.export_quantity_tables(tmp_path / "out.xlsx", unit_ids)
    # 不为单个单位工程出 sheet：固定两张表
    assert result["sheets"] == ["定额工程量", "清单工程量"]

    workbook = openpyxl.load_workbook(tmp_path / "out.xlsx")
    quota = workbook["定额工程量"]
    assert [cell.value for cell in quota[1]] == [
        "单位工程",
        "类别",
        "名称",
        "单位",
        "数量",
        "表达式",
        "算式",
    ]
    rows = {(row[0].value, row[2].value): row for row in _quota_rows(quota)}
    rain = rows["雨水工程", "垫层"]
    assert rain[1].value == "构筑物" and rain[3].value == "m3"
    assert abs(rain[4].value - 4.0) < 1e-9  # 2.0 × 数量 2
    assert rain[5].value and rain[6].value  # 表达式 / 算式都有内容
    sewage = rows["污水工程", "垫层"]
    assert abs(sewage[4].value - 3.0) < 1e-9  # 1.0 × 数量 3，未与雨水合并

    listing = workbook["清单工程量"]
    listing_rows = _quota_rows(listing)
    header_row = listing_rows[0]
    assert header_row[0].value == "雨水工程"
    assert header_row[2].value == "雨水检查井"  # 名称 = 规格 / 名称
    assert abs(header_row[4].value - 2.0) < 1e-9
    assert header_row[5].value == "2" and header_row[6].value == "2"  # 数量原文
    # 清单项目行浅蓝标记（D6EAF8），下挂定额拆分行
    assert "D6EAF8" in str(header_row[1].fill.start_color.rgb)
    assert listing_rows[1][2].value == "垫层"
    # 之后是污水工程块
    assert listing_rows[-1][0].value == "污水工程"


def test_export_empty_unit_writes_header_only(tmp_path) -> None:
    """没有构件的单位工程也照常出表（只有表头）。"""
    path = tmp_path / "空工程.stn"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    segment = project_io.segments()[0]
    unit_ids = [unit.id for unit in project_io.units(segment.id)]
    result = summary.export_quantity_tables(tmp_path / "empty.xlsx", unit_ids)
    assert result["rows"] == 0
    workbook = openpyxl.load_workbook(tmp_path / "empty.xlsx")
    assert workbook.sheetnames == ["定额工程量", "清单工程量"]
    assert [cell.value for cell in workbook["定额工程量"][1]][0] == "单位工程"


# --------------------------------------------------------------------------- #
# 合并导出（所选单位工程加总）
# --------------------------------------------------------------------------- #
def test_export_merged(tmp_path) -> None:
    unit_ids = _two_unit_project(tmp_path)
    result = summary.export_quantity_tables(tmp_path / "merged.xlsx", unit_ids, merged=True)
    assert result["sheets"] == ["定额工程量", "清单工程量"]

    workbook = openpyxl.load_workbook(tmp_path / "merged.xlsx")
    quota_rows = _quota_rows(workbook["定额工程量"])
    assert len(quota_rows) == 1  # 两单位同键定额合并为一行
    assert abs(quota_rows[0][3].value - 7.0) < 1e-9  # 4 + 3
    # 合并后主算式退化为 V1+V2，表达式列回退为完整数值算式（与算式列一致）
    assert quota_rows[0][4].value == quota_rows[0][5].value

    listing_rows = _quota_rows(workbook["清单工程量"])
    listing_headers = [
        row for row in listing_rows if "D6EAF8" in str(row[0].fill.start_color.rgb)
    ]
    assert len(listing_headers) == 2  # 名称不同，各自一行
    amounts = {row[1].value: row[3].value for row in listing_headers}
    assert abs(amounts["雨水检查井"] - 2.0) < 1e-9
    assert abs(amounts["污水检查井"] - 3.0) < 1e-9


def test_export_merged_same_name_listing_groups(tmp_path) -> None:
    """同名同规格的清单项目跨单位合并：数量相加、拆分行合并。"""
    from app.core.models.models import CATEGORY_STRUCTURE

    path = tmp_path / "同名工程.stn"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程", "污水工程"]))
    segment = project_io.segments()[0]
    units = project_io.units(segment.id)
    for unit, amount in ((units[0], "2"), (units[1], "3")):
        unit_vm.create_element(
            unit.id,
            category=CATEGORY_STRUCTURE,
            name="同款检查井",
            depth="3.2",
            amount=amount,
            params=[("名称", "", "同款检查井"), ("单位", "", "座")],
            quantities=[("构筑物", "垫层", "m3", "1.0")],
        )
    unit_ids = [unit.id for unit in units]
    summary.export_quantity_tables(tmp_path / "same.xlsx", unit_ids, merged=True)

    workbook = openpyxl.load_workbook(tmp_path / "same.xlsx")
    listing_rows = _quota_rows(workbook["清单工程量"])
    listing_headers = [
        row for row in listing_rows if "D6EAF8" in str(row[0].fill.start_color.rgb)
    ]
    assert len(listing_headers) == 1
    assert abs(listing_headers[0][3].value - 5.0) < 1e-9
    assert listing_headers[0][4].value == "2 + 3"  # 数量原文用 " + " 连接
    # 拆分行垫层 = 两单位合计 5.0
    assert abs(listing_rows[-1][3].value - 5.0) < 1e-9


# --------------------------------------------------------------------------- #
# 单位工程列原样输出（sheet 名固定，不再参与命名）
# --------------------------------------------------------------------------- #
def test_unit_name_with_invalid_chars_kept_in_column(tmp_path) -> None:
    """单位工程名带 Excel 非法字符：不出独立 sheet，名字原样进“单位工程”列。"""
    from app.core.models.models import CATEGORY_STRUCTURE

    path = tmp_path / "名字测试.stn"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨/水:工程"]))
    segment = project_io.segments()[0]
    unit = project_io.units(segment.id)[0]
    assert unit_vm.create_element(
        unit.id,
        category=CATEGORY_STRUCTURE,
        name="检查井",
        depth="3.2",
        amount="1",
        params=[("名称", "", "检查井"), ("单位", "", "座")],
        quantities=[("构筑物", "垫层", "m3", "1.0")],
    ) is not None

    result = summary.export_quantity_tables(
        tmp_path / "name.xlsx", [unit.id]
    )
    assert result["sheets"] == ["定额工程量", "清单工程量"]
    workbook = openpyxl.load_workbook(tmp_path / "name.xlsx")
    rows = _quota_rows(workbook["定额工程量"])
    assert rows[0][0].value == "雨/水:工程"


# --------------------------------------------------------------------------- #
# 导出对话框：树状勾选
# --------------------------------------------------------------------------- #
def test_dialog_unit_tree(qapp, tmp_path) -> None:
    """工程 → 标段 → 单位工程 三层勾选树：默认全选，父节点三态联动。"""
    from PySide6.QtCore import Qt

    from app.views.dialogs.export_excel_dialog import ExportExcelDialog

    unit_ids = _two_unit_project(tmp_path)
    dialog = ExportExcelDialog()
    assert dialog._checked_unit_ids() == unit_ids  # 默认全选

    _unit_id, leaf = dialog._unit_items[0]
    leaf.setCheckState(0, Qt.CheckState.Unchecked)
    assert dialog._checked_unit_ids() == unit_ids[1:]
    # 标段父节点呈半选态；工程根节点同样半选
    assert leaf.parent().checkState(0) == Qt.CheckState.PartiallyChecked
    assert leaf.parent().parent().checkState(0) == Qt.CheckState.PartiallyChecked

    # 勾回标段节点 → 其下单位工程全部选中
    leaf.parent().setCheckState(0, Qt.CheckState.Checked)
    assert dialog._checked_unit_ids() == unit_ids

    dialog._set_all_checked(False)
    assert dialog._checked_unit_ids() == []
    dialog.deleteLater()
