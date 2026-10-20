"""H 组：汇总与导出（T69~T72）。"""

from __future__ import annotations

from app.agent.context import optional_unit_id
from app.agent.errors import ToolError
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import check_write_path, require_open
from app.services import summary as summary_service


def tool_get_unit_summary(arguments: dict) -> dict:
    require_open()
    unit_id = optional_unit_id(arguments)
    if unit_id is None:
        raise ToolError("请提供 unit_id（可先调 get_project_tree）。")
    rows = summary_service.unit_summary(unit_id)
    total = sum(row["total"] for row in rows)
    priced = sum(1 for row in rows if row["price"])
    return {
        "ok": True,
        "data": {"unit_id": unit_id, "rows": rows, "total": total, "priced_rows": priced,
                 "hint": "单价为 0 的行可先用 set_price / batch_import_prices 载价。"},
    }


def tool_set_price(arguments: dict) -> dict:
    require_open()
    key = str(arguments.get("key") or "").strip()
    if not key:
        raise ToolError("请提供 key（格式：类别|项目|单位，见 get_unit_summary）。")
    try:
        value = float(arguments.get("value"))
    except (TypeError, ValueError) as error:
        raise ToolError("单价 value 需为数字。") from error
    summary_service.set_price(key, value)
    return {"ok": True, "data": {"key": key, "value": value}}


def tool_batch_import_prices(arguments: dict) -> dict:
    require_open()
    path = str(arguments.get("path") or "").strip()
    if not path:
        raise ToolError("请提供 CSV/xlsx 路径（两列：key、单价）。")
    try:
        result = summary_service.batch_import_prices(path)
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error
    return {"ok": True, "data": result}


def tool_export_excel(arguments: dict) -> dict:
    require_open()
    path = str(arguments.get("path") or "").strip()
    if not path:
        raise ToolError("请提供导出路径 path（.xlsx）。")
    check_write_path(path)
    kind = str(arguments.get("kind") or "定额")
    unit_id = optional_unit_id(arguments)
    try:
        result = summary_service.export_excel(path, kind=kind, unit_id=unit_id)
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error
    return {"ok": True, "data": result, "summary": f"已导出：{result['path']}"}


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_unit_summary",
            "单位工程汇总：量×单价=合价（单价来自 price 表）。只读。",
            {"type": "object", "properties": {"unit_id": {"type": "integer"}}},
            tool_get_unit_summary, read_only=True,
        )
    )
    registry.register(
        Tool(
            "set_price", "设置一条单价（key=类别|项目|单位）。写操作。",
            {"type": "object", "properties": {
                "key": {"type": "string"}, "value": {"type": "number"}},
             "required": ["key", "value"]},
            tool_set_price,
        )
    )
    registry.register(
        Tool(
            "batch_import_prices", "从 CSV/xlsx 批量载价（两列：key、单价）。写操作。",
            {"type": "object", "properties": {"path": {"type": "string"}},
             "required": ["path"]},
            tool_batch_import_prices,
        )
    )
    registry.register(
        Tool(
            "export_excel", "导出定额或清单工程量表为 Excel（含计算表达式列）。写操作（文件）。",
            {"type": "object", "properties": {
                "path": {"type": "string"},
                "kind": {"type": "string", "enum": ["定额", "清单"], "default": "定额"},
                "unit_id": {"type": "integer", "description": "省略=全工程"}},
             "required": ["path", "kind"]},
            tool_export_excel,
        )
    )
