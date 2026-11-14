"""汇总与 Excel 导出（无头服务，MCP 工具与桌面 M5 重做共用）。

汇总口径：工程量（QDict 合并后） × 单价（price 表，key = 类别|项目|单位；
单价联动与回落都按“类别 + 项目”判断是否同一工程量，见 :func:`resolve_price`）。
Excel 导出：分单位工程口径按项目结构出 sheet（工程根 / 各标段费用汇总表 +
各单位工程定额 / 清单工程量汇总表，行带单价 / 合价）；合并口径固定定额 /
清单两张表；均含“计算表达式”列（产品核心数据）。

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
from app.services import undo as undo_stack


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
    # 撤销焦点：告诉撤销栈这一步改的是哪条单价（联动修改动到多条，快照
    # 对比只能给出集合，用户改的那条只有这里知道）
    undo_stack.note_intent({"kind": "price", "key": key})
    project_io.commit()


def price_scope(key: str) -> tuple[str, str]:
    """单价联动口径：``(类别, 项目)``。

    单价 key 是 ``类别|项目|单位``。判断两条工程量是否同一工程量时，项目名
    必须连同类别一起看：``垫层|中粗砂`` 与 ``回填|中粗砂`` 是两种工程量，
    不能因为项目名都叫“中粗砂”就联动。
    """
    parts = str(key or "").split("|")
    category = parts[0] if parts else ""
    item = parts[1] if len(parts) > 1 else ""
    return category, item


def price_maps() -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """单价索引：``(key → 单价, (类别, 项目) → 单价)``。

    综合单价汇总页的单价按“类别 + 项目”联动：工程量 key 没有显式记录时
    回落到同类别同项目任意一条记录的单价（每组取第一条）。只看项目名会把
    “垫层|中粗砂”和“回填|中粗砂”错当成同一工程量，因此回落键必须带类别。
    """
    if not orm.is_open():
        return {}, {}
    by_key: dict[str, float] = {}
    by_scope: dict[tuple[str, str], float] = {}
    for row in orm.session().scalars(select(Price)):
        by_key[row.key] = float(row.value)
        category, item = price_scope(row.key)
        if item and (category, item) not in by_scope:
            by_scope[(category, item)] = float(row.value)
    return by_key, by_scope


def resolve_price(
    key: str,
    by_key: dict[str, float],
    by_scope: dict[tuple[str, str], float],
) -> float:
    """解析一条工程量的单价：key 显式记录优先，否则回落同（类别, 项目）。"""
    price = by_key.get(key)
    if price is not None:
        return price
    return by_scope.get(price_scope(key), 0.0)


def set_price_propagate(key: str, value: float) -> None:
    """设置单价并按“类别 + 项目”联动：同类别同项目的已有记录同步。

    在综合单价汇总页改某一行的单价（如标段 1 的“回填|中粗砂”改为 350）后，
    全项目所有类别、项目名都相同的记录（含其他标段）都变成同一单价；
    类别不同（如“垫层|中粗砂”）互不影响。
    """
    set_price(key, value)
    category, item = price_scope(key)
    if not item:
        return
    from app.services import project_io

    session = orm.session()
    changed = False
    for row in session.scalars(select(Price)):
        row_category, row_item = price_scope(row.key)
        if (
            row_category == category
            and row_item == item
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
    by_key, by_scope = price_maps()
    rows: list[dict] = []
    for quantity in sorted_items(summary):
        parts = quantity.key.split("|")
        price = resolve_price(quantity.key, by_key, by_scope)
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
    by_key, by_scope = price_maps()

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
                price = resolve_price(quantity.key, by_key, by_scope)
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
                    price = resolve_price(quantity.key, by_key, by_scope)
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
# 工程数量表导出（工具栏「导出 Excel」）
# --------------------------------------------------------------------------- #
#: 合并口径的固定列：类别 / 名称 / 单位 / 数量 / 表达式（主式） / 算式（纯数字代入式）
_QUANTITY_HEADERS = ["类别", "名称", "单位", "数量", "表达式", "算式"]
_QUOTA_WIDTHS = (14, 34, 10, 14, 46, 60)
#: 分单位工程口径的固定列：每张 sheet 对应一个单位工程，数量右侧带单价 / 合价
_PRICE_QUANTITY_HEADERS = ["类别", "名称", "单位", "数量", "单价", "合价", "表达式", "算式"]
#: 对应列宽（单价 / 合价列宽沿用工程量明细表导出）
_PRICE_QUOTA_WIDTHS = (*_QUOTA_WIDTHS[:4], 12, 14, *_QUOTA_WIDTHS[4:])
#: 写成数字（float）并限定小数位显示的列（单元格里仍可直接再计算）
_NUMBER_COLUMNS = ("数量", "单价", "合价")
#: 费用汇总表固定列（与汇总页费用汇总表同序：序号 / 名称 / 合价）
_COST_SHEET_HEADERS = ["序号", "名称", "合价"]
_COST_SHEET_WIDTHS = (14, 40, 16)
#: 清单项目行底色（删除版 excel_export 同款浅蓝）
_LISTING_FILL = "D6EAF8"
#: Excel sheet 名的非法字符与长度上限
_INVALID_SHEET_CHARS = re.compile(r'[\\/:*?\[\]]')
_SHEET_NAME_MAX = 31


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


def _sheet_title(workbook, name: str, suffix: str) -> str:
    """节点名 + 固定后缀的 sheet 名：替换非法字符、超长截名、重名加序号。

    Excel sheet 名上限 31 字符且不能含 ``: \\ / ? * [ ]``；超长时截节点名
    保住后缀（如“-定额表”），重名（同一标段下的同名单位工程）用 ``(2)``
    起的序号区分。
    """
    name = _INVALID_SHEET_CHARS.sub("_", str(name or "")).strip()
    title = f"{name}{suffix}"
    if len(title) > _SHEET_NAME_MAX:
        title = name[: _SHEET_NAME_MAX - len(suffix)] + suffix
    existing = {sheet.title for sheet in workbook.worksheets}
    if title not in existing:
        return title
    index = 2
    while True:
        tail = f"({index})"
        candidate = title[: _SHEET_NAME_MAX - len(tail)] + tail
        if candidate not in existing:
            return candidate
        index += 1


def _priced_rows(
    rows: list[tuple[list, bool]],
    by_key: dict[str, float],
    by_scope: dict[tuple[str, str], float],
) -> list[tuple[list, bool]]:
    """给行生成器的行补上单价 / 合价（插在数量右侧）。

    定额行单价按 key（类别|项目|单位）/ “类别 + 项目”取价目表，合价 =
    数量 × 单价；清单项目行合价 = 该条目下所有定额行合价的合计、单价 =
    合价 ÷ 数量（派生值，与工程量明细表面板 :meth:`QuantityDetailPanel._compose`
    同口径）。
    """
    priced: list[tuple[list, bool]] = []
    for index, (values, is_listing) in enumerate(rows):
        category, name, unit, amount = values[:4]
        amount = float(amount)
        if is_listing:
            total = 0.0
            for child_values, child_is_listing in rows[index + 1:]:
                if child_is_listing:
                    break
                child_key = f"{child_values[0]}|{child_values[1]}|{child_values[2]}"
                total += float(child_values[3]) * resolve_price(child_key, by_key, by_scope)
            price = total / amount if amount else 0.0
        else:
            price = resolve_price(f"{category}|{name}|{unit}", by_key, by_scope)
            total = amount * price
        priced.append(([category, name, unit, amount, price, total, *values[4:]], is_listing))
    return priced


def _write_sheet(
    sheet, headers: list[str], rows: list[tuple[list, bool]], widths: tuple
) -> None:
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
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
    for name in _NUMBER_COLUMNS:
        if name in headers:
            column = headers.index(name) + 1
            for row in range(2, sheet.max_row + 1):
                sheet.cell(row=row, column=column).number_format = "0.####"
    sheet.freeze_panes = "A2"


def _write_cost_sheet(sheet, rows: list[tuple[str, str, float, int]]) -> None:
    """写一张费用汇总表（序号 / 名称 / 合价）：表头加粗、名称按层级缩进、冻结首行。

    ``rows`` 为 ``(序号, 名称, 合价, 缩进层级)``，序号即项目结构的层级编号
    （工程根 1 → 标段 1.1 → 单位工程 1.1.1），与汇总页费用汇总表同口径。
    """
    import openpyxl
    from openpyxl.styles import Alignment, Font

    sheet.append(_COST_SHEET_HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for seq, name, total, indent in rows:
        sheet.append([seq, name, total])
        sheet.cell(row=sheet.max_row, column=2).alignment = Alignment(indent=indent)
    for index, width in enumerate(_COST_SHEET_WIDTHS, start=1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(index)].width = width
    for row in range(2, sheet.max_row + 1):
        sheet.cell(row=row, column=3).number_format = "0.####"
    sheet.freeze_panes = "A2"


def export_quantity_tables(
    path: str | Path,
    unit_ids: list[int],
    merged: bool = False,
    include_cost: bool = True,
    include_quota: bool = True,
    include_listing: bool = True,
    listing_only: bool = False,
) -> dict:
    """导出工程数量表（一次一个 xlsx 文件）。

    ``merged=True``（合并口径）：所选单位工程的工程量全部加总，输出
    ``定额工程量`` / ``清单工程量`` 两张 sheet（分别受 ``include_quota`` /
    ``include_listing`` 控制），一张 sheet 只放一个表。

    默认（分单位工程口径）：sheet 按项目结构从上到下排列——工程根一张
    费用汇总表；每个勾了单位工程的标段一张费用汇总表，其下每个单位工程
    各出定额 / 清单两张工程量汇总表（行内数量右侧带单价 / 合价）。费用
    汇总表 / 定额表 / 清单表分别受 ``include_cost`` / ``include_quota`` /
    ``include_listing`` 控制，取消的项不输出对应 sheet。``listing_only=True``
    （仅清单项）时清单表隐藏清单项目下的定额工程量行，只留清单项目行——
    清单项目行的合价仍按被隐藏行的合计计算（先计价后过滤）。未勾选的
    单位工程不参与任何表；标段下的单位工程一个都没勾时该标段不出表。
    费用汇总表列见 :data:`_COST_SHEET_HEADERS`，工程量表列见
    :data:`_PRICE_QUANTITY_HEADERS`（数量列为 float，表达式为主算式、算式
    为纯数字代入式）。返回 ``{path, sheets, rows}``。
    """
    import openpyxl

    from app.core.calc.tracer import QDict
    from app.viewmodels.unit_vm import compute_unit

    if not unit_ids:
        raise ValueError("请至少选择一个单位工程。")
    if not (include_cost or include_quota or include_listing):
        raise ValueError("请至少选择一种要导出的表。")
    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)

    if merged:
        computed: list[tuple[str, QDict, list]] = []
        for uid in unit_ids:
            unit = orm.session().get(Unit, int(uid))
            if unit is None:
                raise ValueError(f"找不到 id={uid} 的单位工程。")
            unit_summary, detail = compute_unit(int(uid))
            computed.append((unit.name, unit_summary, detail))
        if include_quota:
            merged_summary = QDict()
            for _name, unit_summary, _detail in computed:
                merged_summary.extend(unit_summary)
            _write_sheet(
                workbook.create_sheet("定额工程量"),
                _QUANTITY_HEADERS,
                [(row, False) for row in _quota_rows(merged_summary)],
                _QUOTA_WIDTHS,
            )
        if include_listing:
            listing_rows = _merged_listing_rows(computed)
            if listing_only:  # 仅清单项：隐藏清单项目下的定额工程量行
                listing_rows = [(values, True) for values, flag in listing_rows if flag]
            _write_sheet(
                workbook.create_sheet("清单工程量"),
                _QUANTITY_HEADERS,
                listing_rows,
                _QUOTA_WIDTHS,
            )
    else:
        # 分单位工程口径：按项目结构（工程 → 标段 → 单位工程）从上到下出 sheet
        from app.services import project_io

        checked = {int(uid) for uid in unit_ids}
        groups: list[tuple[object, list]] = []
        for segment in project_io.segments():
            units = [unit for unit in project_io.units(segment.id) if unit.id in checked]
            if units:
                groups.append((segment, units))
        found = {unit.id for _segment, units in groups for unit in units}
        for uid in unit_ids:  # 勾选里混进无效 id 时保持原有报错行为
            if int(uid) not in found:
                raise ValueError(f"找不到 id={uid} 的单位工程。")

        summaries: dict[int, QDict] = {}
        details: dict[int, list] = {}
        for _segment, units in groups:
            for unit in units:
                summaries[unit.id], details[unit.id] = compute_unit(unit.id)

        by_key, by_scope = price_maps()

        def unit_total(unit_id: int) -> float:
            """单位工程合价：Σ(工程量 × 单价)，与汇总页费用汇总表同口径。"""
            return sum(
                quantity.value * resolve_price(quantity.key, by_key, by_scope)
                for quantity in summaries[unit_id].items()
            )

        # 工程根费用汇总表：工程 → 标段 → 单位工程，逐行合价
        if include_cost:
            project = project_io.project_name() or "未命名工程"
            root_rows: list[tuple[str, str, float, int]] = []
            root_total = 0.0
            for seg_index, (segment, units) in enumerate(groups, start=1):
                seg_total = sum(unit_total(unit.id) for unit in units)
                root_total += seg_total
                root_rows.append((f"1.{seg_index}", segment.name, seg_total, 1))
                root_rows.extend(
                    (f"1.{seg_index}.{unit_index}", unit.name, unit_total(unit.id), 2)
                    for unit_index, unit in enumerate(units, start=1)
                )
            root_rows.insert(0, ("1", project, root_total, 0))
            _write_cost_sheet(
                workbook.create_sheet(_sheet_title(workbook, project, "-费用")),
                root_rows,
            )

        for segment, units in groups:
            # 标段费用汇总表：标段为根（序号 1），下属单位工程 1.x
            if include_cost:
                seg_rows: list[tuple[str, str, float, int]] = [
                    ("1", segment.name, sum(unit_total(unit.id) for unit in units), 0)
                ]
                seg_rows.extend(
                    (f"1.{unit_index}", unit.name, unit_total(unit.id), 1)
                    for unit_index, unit in enumerate(units, start=1)
                )
                _write_cost_sheet(
                    workbook.create_sheet(_sheet_title(workbook, segment.name, "-费用")),
                    seg_rows,
                )
            # 单位工程的定额 / 清单工程量汇总表（行带单价 / 合价），
            # sheet 名带标段前缀（如“加油站-雨水工程-定额表”）
            for unit in units:
                prefixed = f"{segment.name}-{unit.name}"
                if include_quota:
                    _write_sheet(
                        workbook.create_sheet(
                            _sheet_title(workbook, prefixed, "-定额表")
                        ),
                        _PRICE_QUANTITY_HEADERS,
                        _priced_rows(
                            [(row, False) for row in _quota_rows(summaries[unit.id])],
                            by_key,
                            by_scope,
                        ),
                        _PRICE_QUOTA_WIDTHS,
                    )
                if include_listing:
                    listing_priced = _priced_rows(
                        _listing_rows(details[unit.id]), by_key, by_scope
                    )
                    if listing_only:  # 仅清单项：隐藏清单项目下的定额工程量行
                        listing_priced = [
                            (values, True) for values, flag in listing_priced if flag
                        ]
                    _write_sheet(
                        workbook.create_sheet(
                            _sheet_title(workbook, prefixed, "-清单表")
                        ),
                        _PRICE_QUANTITY_HEADERS,
                        listing_priced,
                        _PRICE_QUOTA_WIDTHS,
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


# --------------------------------------------------------------------------- #
# 工程量明细表「导出当前表格」：单 sheet，列 = 页面 7 列（+ 展开态的表达式 / 算式）
# --------------------------------------------------------------------------- #
#: 页面表格列（与 quantity_detail_panel._HEADERS 同序）
_DETAIL_HEADERS = ["编号", "类别", "名称", "单位", "数量", "单价", "合价"]
#: 展开态在右侧追加的两列（与导出工程数量表同名同序）
_DETAIL_EXPRESSION_HEADERS = ["表达式", "算式"]
#: 页面列宽（字符宽）：编号 / 类别 / 名称 / 单位 / 数量 / 单价 / 合价
_DETAIL_WIDTHS = (10, 14, 34, 10, 14, 12, 14)
#: 写成数字（float）的列：数量 / 单价 / 合价，其余列按文本写
_DETAIL_NUMBER_COLUMNS = ("数量", "单价", "合价")


def detail_export_headers(with_expression: bool = True) -> list[str]:
    """「导出当前表格」的表头：页面 7 列，展开态再追加表达式 / 算式。"""
    if with_expression:
        return [*_DETAIL_HEADERS, *_DETAIL_EXPRESSION_HEADERS]
    return list(_DETAIL_HEADERS)


def export_detail_table(
    path: str | Path,
    rows: list[tuple[list, bool]],
    with_expression: bool = True,
    sheet_title: str = "工程量明细表",
) -> dict:
    """把工程量明细表当前显示的内容导出成单 sheet xlsx。

    ``rows`` 为 ``(值, 是否清单项目行)``：值 = (编号, 类别, 名称, 单位, 数量,
    单价, 合价)；``with_expression=True`` 时右侧再带 (表达式, 算式) 两列。
    数量 / 单价 / 合价按 float 写（Excel 里可直接再计算），清单项目行保留导出
    工程数量表同款浅蓝底；表头加粗、冻结首行。返回 ``{path, rows}``。
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")

    headers = detail_export_headers(with_expression)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    fill = PatternFill("solid", fgColor=_LISTING_FILL)
    for values, is_listing in rows:
        sheet.append(values)
        if is_listing:
            for cell in sheet[sheet.max_row]:
                cell.fill = fill
    widths = (*_DETAIL_WIDTHS, *_QUOTA_WIDTHS[4:]) if with_expression else _DETAIL_WIDTHS
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for name in _DETAIL_NUMBER_COLUMNS:
        column = headers.index(name) + 1
        for row in range(2, sheet.max_row + 1):
            sheet.cell(row=row, column=column).number_format = "0.####"
    sheet.freeze_panes = "A2"

    target.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(target)
    return {"path": str(target), "rows": sheet.max_row - 1}
