"""汇总与 Excel 导出（无头服务，MCP 工具与桌面 M5 重做共用）。

汇总口径：工程量（QDict 合并后） × 单价（price 表，key = 类别|项目|单位）。
Excel 导出：定额 / 清单两张表，含“计算表达式”列（产品核心数据）。

桌面 M5（汇总面板 / 批量载价）重做时直接复用本模块，避免两套逻辑。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from sqlalchemy import select

from app.core.models import base as orm
from app.core.models.models import Price, Unit
from app.core.models.models import category_name


def _unit_ids(unit_id: int | None) -> list[tuple[int, str]]:
    from app.services import project_io

    if unit_id is not None:
        unit = orm.session().get(Unit, unit_id)
        if unit is None:
            raise ValueError(f"找不到 id={unit_id} 的单位工程。")
        return [(unit.id, unit.name)]
    result: list[tuple[int, str]] = []
    for segment in project_io.segments():
        for unit in project_io.units(segment.id):
            result.append((unit.id, unit.name))
    return result


def prices() -> dict[str, float]:
    if not orm.is_open():
        return {}
    return {row.key: float(row.value) for row in orm.session().scalars(select(Price))}


def set_price(key: str, value: float) -> None:
    """设置/更新一条单价（key = 类别|项目|单位）。"""
    from app.services import project_io

    if not orm.is_open():
        raise ValueError("当前没有打开的工程。")
    key = str(key or "").strip()
    if not key:
        raise ValueError("单价 key 不能为空（格式：类别|项目|单位）。")
    session = orm.session()
    row = session.scalar(select(Price).where(Price.key == key).order_by(Price.id))
    if row is None:
        session.add(Price(key=key, value=float(value)))
    else:
        row.value = float(value)
    project_io.commit()


def price_maps() -> tuple[dict[str, float], dict[str, float]]:
    """单价索引：``(key → 单价, 项目名 → 单价)``。

    综合单价汇总页的单价按“项目”列全局联动：工程量 key 没有显式记录时
    回落到同项目名任意一条记录的单价（每名取第一条）。
    """
    if not orm.is_open():
        return {}, {}
    by_key: dict[str, float] = {}
    by_item: dict[str, float] = {}
    for row in orm.session().scalars(select(Price)):
        by_key[row.key] = float(row.value)
        parts = row.key.split("|")
        item = parts[1] if len(parts) > 1 else ""
        if item and item not in by_item:
            by_item[item] = float(row.value)
    return by_key, by_item


def set_price_propagate(key: str, value: float) -> None:
    """设置单价并按“项目”名联动：同项目名的所有已有记录同步为同一单价。

    在综合单价汇总页改某一行的单价（如标段 1 的“中粗砂”改为 350）后，
    全项目所有“项目”名相同的记录（含其他标段）都变成同一单价。
    """
    set_price(key, value)
    parts = key.split("|")
    item = parts[1] if len(parts) > 1 else ""
    if not item:
        return
    from app.services import project_io

    session = orm.session()
    changed = False
    for row in session.scalars(select(Price)):
        row_parts = row.key.split("|")
        if (
            len(row_parts) > 1
            and row_parts[1] == item
            and row.key != key
            and row.value != float(value)
        ):
            row.value = float(value)
            changed = True
    if changed:
        project_io.commit()


def batch_import_prices(path: str | Path) -> dict:
    """从 CSV / xlsx（两列：key、单价）批量载价。返回 {imported, skipped}。"""
    target = Path(path)
    if not target.exists():
        raise ValueError(f"文件不存在：{target}")
    rows: list[tuple[str, str]] = []
    if target.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        workbook = openpyxl.load_workbook(target, data_only=True, read_only=True)
        try:
            worksheet = workbook.active
            for index, line in enumerate(worksheet.iter_rows(values_only=True)):
                if index == 0 and line and str(line[0] or "").strip() in ("key", "编号", "类别|项目|单位"):
                    continue
                if not line or len(line) < 2:
                    continue
                rows.append((str(line[0] or ""), str(line[1] or "")))
        finally:
            workbook.close()
    else:
        with target.open("r", encoding="utf-8-sig", newline="") as handle:
            for index, line in enumerate(csv.reader(handle)):
                if index == 0 and line and line[0].strip() in ("key", "编号", "类别|项目|单位"):
                    continue
                if len(line) < 2:
                    continue
                rows.append((line[0], line[1]))
    imported = 0
    skipped = 0
    from app.services import project_io

    session = orm.session()
    existing = {row.key: row for row in session.scalars(select(Price))}
    for key, value in rows:
        key = key.strip()
        try:
            number = float(value)
        except (TypeError, ValueError):
            skipped += 1
            continue
        if not key:
            skipped += 1
            continue
        if key in existing:
            existing[key].value = number
        else:
            session.add(Price(key=key, value=number))
        imported += 1
    project_io.commit()
    return {"imported": imported, "skipped": skipped}


def unit_summary(unit_id: int) -> list[dict]:
    """单位工程汇总：量 × 单价 = 合价。"""
    from app.core.calc.tracer import sorted_items
    from app.viewmodels.unit_vm import compute_unit

    summary, _detail = compute_unit(unit_id)
    price_map = prices()
    rows: list[dict] = []
    for quantity in sorted_items(summary):
        parts = quantity.key.split("|")
        price = price_map.get(quantity.key, 0.0)
        rows.append(
            {
                "key": quantity.key,
                "category": parts[0] if parts else "",
                "item": parts[1] if len(parts) > 1 else "",
                "unit": parts[2] if len(parts) > 2 else "",
                "amount": quantity.value,
                "price": price,
                "total": quantity.value * price,
                "expression": quantity.expression,
                "display_expression": quantity.display_expression,
            }
        )
    return rows


def export_excel(
    path: str | Path,
    kind: str = "定额",
    unit_id: int | None = None,
) -> dict:
    """导出 Excel（kind=定额 / 清单），含计算表达式列。

    返回 ``{path, rows, sheets}``。整工程导出（unit_id=None）时多一列“单位工程”。
    """
    import openpyxl
    from openpyxl.styles import Font

    from app.core.calc.tracer import fmt, sorted_items
    from app.viewmodels.unit_vm import compute_unit

    if kind not in ("定额", "清单"):
        raise ValueError("kind 只能是“定额”或“清单”。")
    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")
    units = _unit_ids(unit_id)
    price_map = prices()

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = kind
    units_mode = unit_id is None
    headers = (
        (["单位工程"] if units_mode else [])
        + [
            "类别",
            "项目",
            "单位",
            "计算表达式（主式）",
            "完整数值算式",
            "工程量",
            "单价",
            "合价",
        ]
    )
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    exported_rows = 0
    for uid, unit_name in units:
        summary, detail = compute_unit(uid)
        if kind == "定额":
            for quantity in sorted_items(summary):
                parts = quantity.key.split("|")
                price = price_map.get(quantity.key, 0.0)
                row = [
                    parts[0] if parts else "",
                    parts[1] if len(parts) > 1 else "",
                    parts[2] if len(parts) > 2 else "",
                    quantity.display_expression,
                    quantity.expression,
                    quantity.value,
                    price,
                    quantity.value * price,
                ]
                if units_mode:
                    row.insert(0, unit_name)
                sheet.append(row)
                exported_rows += 1
        else:
            for element_row, qdict in detail:
                row = [
                    category_name(element_row.category),
                    element_row.spec or element_row.name,
                    element_row.unit,
                    element_row.amount,
                    element_row.amount_value,
                    "",
                    "",
                ]
                if units_mode:
                    row.insert(0, unit_name)
                sheet.append(row)
                exported_rows += 1
                for quantity in sorted_items(qdict):
                    parts = quantity.key.split("|")
                    price = price_map.get(quantity.key, 0.0)
                    row = [
                        parts[0] if parts else "",
                        parts[1] if len(parts) > 1 else "",
                        parts[2] if len(parts) > 2 else "",
                        quantity.display_expression,
                        quantity.expression,
                        quantity.value,
                        price,
                        quantity.value * price,
                    ]
                    if units_mode:
                        row.insert(0, unit_name)
                    sheet.append(row)
                    exported_rows += 1
    widths = ([18] if units_mode else []) + [14, 34, 10, 50, 50, 14, 12, 14]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return {"path": str(target), "rows": exported_rows, "kind": kind}


# --------------------------------------------------------------------------- #
# 工程数量表导出（工具栏「导出 Excel」）：6 列，1.0 基础上右侧增添纯数字算式列
# --------------------------------------------------------------------------- #
#: 导出表格固定列：类别 / 名称 / 单位 / 数量 / 表达式（主式） / 算式（纯数字代入式）
_QUANTITY_HEADERS = ["类别", "名称", "单位", "数量", "表达式", "算式"]
#: 分单位工程口径：行前带“单位工程”列（合并口径不用）
_UNIT_QUANTITY_HEADERS = ["单位工程", *_QUANTITY_HEADERS]
_UNIT_COL_WIDTH = 18
#: 清单项目行底色（删除版 excel_export 同款浅蓝）
_LISTING_FILL = "D6EAF8"
_QUOTA_WIDTHS = (14, 34, 10, 14, 46, 60)


def _main_expression(quantity) -> str:
    """表达式列的内容：主算式（带符号）；退化为 V1+V2 时改用完整数值算式。

    单位工程内部的主算式是 (S1-S2)/10^6*120 这类带几何符号的真式子；跨单位
    合并后各分项不再共享符号，展示层只能给 V1+V2 这类占位式——脱离详情弹窗
    （中间量定义）没有意义，导出静态表格时改用完整数值算式。
    """
    main = quantity.display_expression
    if "V" in main and re.fullmatch(r"[V\d+\-()\s]+", main):
        return quantity.expression
    return main


def _quantity_row(quantity, with_expression: bool = True) -> list:
    """一条定额量 → [类别, 名称, 单位, 数量, 表达式(主式), 算式(纯数字)]。

    ``with_expression=False`` 时不解析主算式（解析极重，见 tracer 展示层），
    两列以空串占位——只显示数量、不需要算式的调用方（工程量明细表）用。
    """
    parts = quantity.key.split("|")
    if not with_expression:
        return [
            parts[0] if parts else "",
            parts[1] if len(parts) > 1 else "",
            parts[2] if len(parts) > 2 else "",
            quantity.value,
            "",
            "",
        ]
    return [
        parts[0] if parts else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
        quantity.value,
        _main_expression(quantity),
        quantity.expression,
    ]


def _quota_rows(qdict, with_expression: bool = True) -> list[list]:
    """定额汇总表行（按类别排序），``qdict`` 为单位工程或跨单位合并后的 QDict。"""
    from app.core.calc.tracer import sorted_items

    return [
        _quantity_row(quantity, with_expression) for quantity in sorted_items(qdict)
    ]


def _listing_rows(detail, with_expression: bool = True) -> list[tuple[list, bool]]:
    """清单工程量表行：``(值, 是否清单项目行)``，清单项目行下挂定额拆分行。

    ``detail`` 是 :func:`app.viewmodels.unit_vm.compute_unit` 返回的
    ``[(构件行, 该构件 QDict)]``。
    """
    rows: list[tuple[list, bool]] = []
    for element_row, qdict in detail:
        rows.append(
            (
                [
                    category_name(element_row.category),
                    element_row.spec or element_row.name,
                    element_row.unit,
                    element_row.amount_value,
                    element_row.amount,
                    element_row.amount,
                ],
                True,
            )
        )
        rows.extend(
            (row, False) for row in _quota_rows(qdict, with_expression)
        )
    return rows


def _merged_listing_rows(computed) -> list[tuple[list, bool]]:
    """合并口径的清单行：清单项目按 (类别, 名称, 单位) 跨单位加总。

    数量求和、数量原文用 " + " 连接（同 :meth:`UnitPanel._merge_quantities`
    跳过空 / "0" 的规则），拆分行把组内各构件 QDict 逐项合并后输出。
    """
    from app.core.calc.tracer import QDict

    groups: dict[tuple[str, str, str], dict] = {}
    for _unit_name, _summary, detail in computed:
        for element_row, qdict in detail:
            key = (
                category_name(element_row.category),
                element_row.spec or element_row.name,
                element_row.unit,
            )
            entry = groups.get(key)
            if entry is None:
                entry = groups[key] = {"amount": 0.0, "exprs": [], "qdict": QDict()}
            entry["amount"] += element_row.amount_value
            if element_row.amount.strip() not in ("", "0"):
                entry["exprs"].append(element_row.amount)
            entry["qdict"].extend(qdict)
    rows: list[tuple[list, bool]] = []
    for (category, name, unit), entry in groups.items():
        joined = " + ".join(entry["exprs"])
        rows.append(([category, name, unit, entry["amount"], joined, joined], True))
        rows.extend((row, False) for row in _quota_rows(entry["qdict"]))
    return rows


def _write_sheet(sheet, headers: list[str], rows: list[tuple[list, bool]]) -> None:
    """把一张工程数量表写进 sheet：表头加粗、清单项目行浅蓝、冻结首行。"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    fill = PatternFill("solid", fgColor=_LISTING_FILL)
    for values, is_listing in rows:
        sheet.append(values)
        if is_listing:
            for cell in sheet[sheet.max_row]:
                cell.fill = fill
    widths = (_UNIT_COL_WIDTH, *_QUOTA_WIDTHS) if len(headers) > len(_QUANTITY_HEADERS) else _QUOTA_WIDTHS
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
    # 数量列写的是 float，限定最多 4 位小数显示（单元格里仍可直接再计算）
    amount_column = headers.index("数量") + 1
    for row in range(2, sheet.max_row + 1):
        sheet.cell(row=row, column=amount_column).number_format = "0.####"
    sheet.freeze_panes = "A2"


def export_quantity_tables(
    path: str | Path,
    unit_ids: list[int],
    merged: bool = False,
) -> dict:
    """导出工程数量表（定额 + 清单，一次一个 xlsx 文件，固定两张 sheet）。

    sheet 只放一个表：``定额工程量`` / ``清单工程量``。默认分单位工程口径，
    行前带“单位工程”列、各单位工程各自汇总合计；``merged=True`` 为合并口径
    ——所选单位工程的工程量全部加总，不带单位工程列。列见
    :data:`_QUANTITY_HEADERS`（数量列为 float，表达式为主算式、算式为纯数字
    代入式）。返回 ``{path, sheets, rows}``。
    """
    import openpyxl

    from app.core.calc.tracer import QDict
    from app.viewmodels.unit_vm import compute_unit

    if not unit_ids:
        raise ValueError("请至少选择一个单位工程。")
    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")

    computed: list[tuple[str, QDict, list]] = []
    for uid in unit_ids:
        unit = orm.session().get(Unit, int(uid))
        if unit is None:
            raise ValueError(f"找不到 id={uid} 的单位工程。")
        summary, detail = compute_unit(int(uid))
        computed.append((unit.name, summary, detail))

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    if merged:
        merged_summary = QDict()
        for _name, unit_summary, _detail in computed:
            merged_summary.extend(unit_summary)
        _write_sheet(
            workbook.create_sheet("定额工程量"),
            _QUANTITY_HEADERS,
            [(row, False) for row in _quota_rows(merged_summary)],
        )
        _write_sheet(
            workbook.create_sheet("清单工程量"),
            _QUANTITY_HEADERS,
            _merged_listing_rows(computed),
        )
    else:
        # 分单位工程口径：各单位工程各自汇总合计，行前带“单位工程”列
        quota_rows: list[tuple[list, bool]] = []
        listing_rows: list[tuple[list, bool]] = []
        for unit_name, unit_summary, detail in computed:
            quota_rows.extend(
                ([unit_name, *row], False) for row in _quota_rows(unit_summary)
            )
            listing_rows.extend(
                ([unit_name, *row], is_listing)
                for row, is_listing in _listing_rows(detail)
            )
        _write_sheet(
            workbook.create_sheet("定额工程量"), _UNIT_QUANTITY_HEADERS, quota_rows
        )
        _write_sheet(
            workbook.create_sheet("清单工程量"), _UNIT_QUANTITY_HEADERS, listing_rows
        )

    exported_rows = sum(
        sheet.max_row - 1 for sheet in workbook.worksheets  # 不含表头
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return {
        "path": str(target),
        "sheets": [sheet.title for sheet in workbook.worksheets],
        "rows": exported_rows,
    }
