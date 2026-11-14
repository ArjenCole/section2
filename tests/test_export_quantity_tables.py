"""工程数量表导出（services.summary.export_quantity_tables）测试。

覆盖：分单位工程 / 合并两种口径的 sheet 结构与加总规则、按项目结构的
sheet 排序、费用汇总表、行内单价 / 合价、清单项目行浅蓝标记、导出内容
勾选（费用汇总 / 定额 / 清单）与仅清单项、导出对话框的树状勾选与内容勾选。
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


def _listing_header_rows(rows) -> list:
    return [row for row in rows if "D6EAF8" in str(row[0].fill.start_color.rgb)]


# --------------------------------------------------------------------------- #
# 分单位工程导出（默认口径：按项目结构出 sheet，行带单价 / 合价）
# --------------------------------------------------------------------------- #
def test_export_per_unit(tmp_path) -> None:
    unit_ids = _two_unit_project(tmp_path)
    summary.set_price("构筑物|垫层|m3", 100.0)
    result = summary.export_quantity_tables(tmp_path / "out.xlsx", unit_ids)
    # sheet 按项目结构从上到下：工程根费用汇总 → 标段费用汇总 → 各单位定额 / 清单
    assert result["sheets"] == [
        "新建项目-费用汇总表",
        "新建标段-费用汇总表",
        "雨水工程-定额工程量汇总表",
        "雨水工程-清单工程量汇总表",
        "污水工程-定额工程量汇总表",
        "污水工程-清单工程量汇总表",
    ]

    workbook = openpyxl.load_workbook(tmp_path / "out.xlsx")
    quota = workbook["雨水工程-定额工程量汇总表"]
    assert [cell.value for cell in quota[1]] == [
        "类别",
        "名称",
        "单位",
        "数量",
        "单价",
        "合价",
        "表达式",
        "算式",
    ]
    rows = _quota_rows(quota)
    assert len(rows) == 1
    rain = rows[0]
    assert rain[0].value == "构筑物" and rain[2].value == "m3"
    assert abs(rain[3].value - 4.0) < 1e-9  # 2.0 × 数量 2
    assert abs(rain[4].value - 100.0) < 1e-9  # 单价
    assert abs(rain[5].value - 400.0) < 1e-9  # 合价 = 数量 × 单价
    assert rain[6].value and rain[7].value  # 表达式 / 算式都有内容

    listing = workbook["雨水工程-清单工程量汇总表"]
    listing_rows = _quota_rows(listing)
    header_row = _listing_header_rows(listing_rows)[0]
    assert header_row[1].value == "雨水检查井"  # 名称 = 规格 / 名称
    assert abs(header_row[3].value - 2.0) < 1e-9
    # 清单项目行合价 = 定额拆分行合价合计（4.0 × 100），单价 = 合价 ÷ 数量
    assert abs(header_row[5].value - 400.0) < 1e-9
    assert abs(header_row[4].value - 200.0) < 1e-9
    assert header_row[6].value == "2" and header_row[7].value == "2"  # 数量原文
    # 清单项目行浅蓝标记（D6EAF8），下挂定额拆分行
    assert "D6EAF8" in str(header_row[0].fill.start_color.rgb)
    assert listing_rows[1][1].value == "垫层"
    # 各单位工程一张 sheet：污水块在污水工程自己的清单表里
    sewage_rows = _quota_rows(workbook["污水工程-清单工程量汇总表"])
    assert [row[1].value for row in _listing_header_rows(sewage_rows)] == ["污水检查井"]
    assert abs(sewage_rows[0][5].value - 300.0) < 1e-9  # 3.0 × 100

    # 费用汇总表：工程根 → 标段 → 单位工程，逐行合价
    root_rows = _quota_rows(workbook["新建项目-费用汇总表"])
    assert [cell.value for cell in workbook["新建项目-费用汇总表"][1]] == [
        "序号", "名称", "合价",
    ]
    assert [(row[0].value, row[1].value) for row in root_rows] == [
        ("1", "新建项目"),
        ("1.1", "新建标段"),
        ("1.1.1", "雨水工程"),
        ("1.1.2", "污水工程"),
    ]
    assert abs(root_rows[0][2].value - 700.0) < 1e-9  # 400 + 300
    assert abs(root_rows[2][2].value - 400.0) < 1e-9
    assert abs(root_rows[3][2].value - 300.0) < 1e-9
    seg_rows = _quota_rows(workbook["新建标段-费用汇总表"])
    assert [(row[0].value, row[1].value) for row in seg_rows] == [
        ("1", "新建标段"),
        ("1.1", "雨水工程"),
        ("1.2", "污水工程"),
    ]
    assert abs(seg_rows[0][2].value - 700.0) < 1e-9


def test_export_subset_excludes_unchecked(tmp_path) -> None:
    """只勾部分单位工程：未勾选的不出表，费用汇总也不计未勾选的。"""
    unit_ids = _two_unit_project(tmp_path)
    result = summary.export_quantity_tables(tmp_path / "part.xlsx", unit_ids[:1])
    assert result["sheets"] == [
        "新建项目-费用汇总表",
        "新建标段-费用汇总表",
        "雨水工程-定额工程量汇总表",
        "雨水工程-清单工程量汇总表",
    ]
    workbook = openpyxl.load_workbook(tmp_path / "part.xlsx")
    root_rows = _quota_rows(workbook["新建项目-费用汇总表"])
    assert [(row[0].value, row[1].value) for row in root_rows] == [
        ("1", "新建项目"),
        ("1.1", "新建标段"),
        ("1.1.1", "雨水工程"),
    ]


def test_export_empty_unit_writes_header_only(tmp_path) -> None:
    """没有构件的单位工程也照常出表（工程量表只有表头，费用汇总合计 0）。"""
    path = tmp_path / "空工程.stn"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    segment = project_io.segments()[0]
    unit_ids = [unit.id for unit in project_io.units(segment.id)]
    summary.export_quantity_tables(tmp_path / "empty.xlsx", unit_ids)
    workbook = openpyxl.load_workbook(tmp_path / "empty.xlsx")
    assert workbook["雨水工程-定额工程量汇总表"].max_row == 1  # 只有表头
    root_rows = _quota_rows(workbook["新建项目-费用汇总表"])
    assert abs(root_rows[0][2].value) < 1e-9  # 无量 → 合计 0


def test_same_name_units_get_distinct_sheets(tmp_path) -> None:
    """不同标段下的同名单位工程：sheet 名按结构顺序排列并加序号区分。"""
    path = tmp_path / "同名.stn"
    project_io.new_project(
        NewProjectSpec(
            path=path, segment_names=["标段一", "标段二"], unit_names=["同名工程"]
        )
    )
    unit_ids = [unit.id for unit in project_io.units(project_io.segments()[0].id)]
    unit_ids += [unit.id for unit in project_io.units(project_io.segments()[1].id)]
    result = summary.export_quantity_tables(tmp_path / "same.xlsx", unit_ids)
    assert result["sheets"] == [
        "新建项目-费用汇总表",
        "标段一-费用汇总表",
        "同名工程-定额工程量汇总表",
        "同名工程-清单工程量汇总表",
        "标段二-费用汇总表",
        "同名工程-定额工程量汇总表(2)",
        "同名工程-清单工程量汇总表(2)",
    ]


# --------------------------------------------------------------------------- #
# 导出内容勾选（费用汇总 / 定额 / 清单）与仅清单项
# --------------------------------------------------------------------------- #
def test_export_include_flags(tmp_path) -> None:
    """取消勾选的导出内容不输出对应 sheet，剩余 sheet 保持结构顺序。"""
    unit_ids = _two_unit_project(tmp_path)

    result = summary.export_quantity_tables(
        tmp_path / "no_cost.xlsx", unit_ids, include_cost=False
    )
    assert result["sheets"] == [
        "雨水工程-定额工程量汇总表",
        "雨水工程-清单工程量汇总表",
        "污水工程-定额工程量汇总表",
        "污水工程-清单工程量汇总表",
    ]

    result = summary.export_quantity_tables(
        tmp_path / "no_quota.xlsx", unit_ids, include_quota=False
    )
    assert result["sheets"] == [
        "新建项目-费用汇总表",
        "新建标段-费用汇总表",
        "雨水工程-清单工程量汇总表",
        "污水工程-清单工程量汇总表",
    ]

    result = summary.export_quantity_tables(
        tmp_path / "no_listing.xlsx", unit_ids, include_listing=False
    )
    assert result["sheets"] == [
        "新建项目-费用汇总表",
        "新建标段-费用汇总表",
        "雨水工程-定额工程量汇总表",
        "污水工程-定额工程量汇总表",
    ]


def test_export_listing_only(tmp_path) -> None:
    """仅清单项：清单表隐藏定额工程量行，清单项目行合价仍按被隐藏行合计。"""
    unit_ids = _two_unit_project(tmp_path)
    summary.set_price("构筑物|垫层|m3", 100.0)
    summary.export_quantity_tables(tmp_path / "only.xlsx", unit_ids, listing_only=True)

    workbook = openpyxl.load_workbook(tmp_path / "only.xlsx")
    rows = _quota_rows(workbook["雨水工程-清单工程量汇总表"])
    assert len(rows) == 1  # 只剩清单项目行
    assert "D6EAF8" in str(rows[0][0].fill.start_color.rgb)
    assert abs(rows[0][5].value - 400.0) < 1e-9  # 合价 = 被隐藏定额行合计（4 × 100）
    assert abs(rows[0][4].value - 200.0) < 1e-9  # 派生单价不变


def test_export_merged_include_flags(tmp_path) -> None:
    """合并口径同样受定额 / 清单勾选与仅清单项控制（无费用汇总表）。"""
    unit_ids = _two_unit_project(tmp_path)
    result = summary.export_quantity_tables(
        tmp_path / "m1.xlsx", unit_ids, merged=True, include_quota=False
    )
    assert result["sheets"] == ["清单工程量"]
    result = summary.export_quantity_tables(
        tmp_path / "m2.xlsx", unit_ids, merged=True, include_listing=False
    )
    assert result["sheets"] == ["定额工程量"]

    summary.export_quantity_tables(
        tmp_path / "m3.xlsx", unit_ids, merged=True, listing_only=True
    )
    workbook = openpyxl.load_workbook(tmp_path / "m3.xlsx")
    rows = _quota_rows(workbook["清单工程量"])
    assert len(rows) == 2  # 两个清单项目行，定额拆分行被隐藏
    assert all("D6EAF8" in str(row[0].fill.start_color.rgb) for row in rows)


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
# sheet 名合法化（单位工程名可能带 Excel 非法字符）
# --------------------------------------------------------------------------- #
def test_unit_name_with_invalid_chars_sanitized_in_sheet_title(tmp_path) -> None:
    """单位工程名带 Excel 非法字符：sheet 名里替换为下划线，表内容不受影响。"""
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
    assert result["sheets"] == [
        "新建项目-费用汇总表",
        "新建标段-费用汇总表",
        "雨_水_工程-定额工程量汇总表",
        "雨_水_工程-清单工程量汇总表",
    ]
    workbook = openpyxl.load_workbook(tmp_path / "name.xlsx")
    rows = _quota_rows(workbook["雨_水_工程-定额工程量汇总表"])
    assert rows[0][1].value == "垫层"  # 定额行内容原样
    listing_rows = _quota_rows(workbook["雨_水_工程-清单工程量汇总表"])
    assert listing_rows[0][1].value == "检查井"  # 清单项目行内容原样


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


def test_dialog_content_checks(qapp, tmp_path) -> None:
    """三个导出内容勾选默认全出；仅清单项下拉默认展开态、随清单勾选启停。"""
    from app.views.dialogs.export_excel_dialog import ExportExcelDialog

    _two_unit_project(tmp_path)
    dialog = ExportExcelDialog()
    assert dialog._cost_check.isChecked()
    assert dialog._quota_check.isChecked()
    assert dialog._listing_check.isChecked()
    assert dialog._listing_mode_combo.currentIndex() == 0  # 展开工程量项
    assert dialog._listing_mode_combo.isEnabled()

    dialog._listing_check.setChecked(False)
    assert not dialog._listing_mode_combo.isEnabled()  # 不导清单表时下拉禁用
    dialog._listing_check.setChecked(True)
    assert dialog._listing_mode_combo.isEnabled()

    # 合并口径没有费用汇总表：费用汇总勾选随合并选项禁用
    dialog._merge_check.setChecked(True)
    assert not dialog._cost_check.isEnabled()
    dialog._merge_check.setChecked(False)
    assert dialog._cost_check.isEnabled()
    dialog.deleteLater()
