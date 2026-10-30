"""汇总与 Excel 导出（无头服务，MCP 工具与桌面 M5 重做共用）。

汇总口径：工程量（QDict 合并后） × 单价（price 表，key = 类别|项目|单位）。
Excel 导出：定额 / 清单两张表，含“计算表达式”列（产品核心数据）。

桌面 M5（汇总面板 / 批量载价）重做时直接复用本模块，避免两套逻辑。
"""

from __future__ import annotations

import csv
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
