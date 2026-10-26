"""G 组：旧 .stn 工程迁移（T67~T68）。"""

from __future__ import annotations

from pathlib import Path

from app.agent.errors import ToolError
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import check_write_path
from app.core.event_bus import bus
from app.core.version import PROJECT_SUFFIX
from app.services import project_io, stn_migration


def _legacy_counts(legacy) -> dict:
    units = elements = pipes = 0
    for segment in legacy.segments:
        for unit in segment.units:
            units += 1
            for element in unit.elements:
                elements += 1
                pipes += len(getattr(element, "pipes", []) or [])
    return {
        "version": legacy.version,
        "project_name": legacy.project_name,
        "project_index": getattr(legacy, "project_index", ""),
        "author": getattr(legacy, "author", ""),
        "atlas_name": legacy.atlas_name,
        "segments": len(legacy.segments),
        "units": units,
        "elements": elements,
        "pipes": pipes,
        "enclosures": len(legacy.enclosures),
        "foundations": len(legacy.foundations),
        "prices": len(legacy.prices),
        "principle_names": [item.name for item in legacy.enclosures]
        + [entry[0] for entry in legacy.foundations],
    }


def tool_inspect_legacy_project(arguments: dict) -> dict:
    path = str(arguments.get("path") or "").strip()
    if not path:
        raise ToolError("请提供旧工程 .stn 文件路径。")
    try:
        legacy = stn_migration.parse_legacy(path)
    except stn_migration.MigrationError as error:
        raise ToolError(str(error)) from error
    return {
        "ok": True,
        "data": {"source": path, **_legacy_counts(legacy), "wrote_files": False},
    }


def tool_migrate_legacy_project(arguments: dict) -> dict:
    source = str(arguments.get("source_path") or "").strip()
    if not source:
        raise ToolError("请提供 source_path（旧 .stn）。")
    target = str(arguments.get("target_path") or "").strip()
    if not target:
        target = str(Path(source).with_suffix(PROJECT_SUFFIX))
    check_write_path(target)
    if project_io.is_open():
        raise ToolError(
            "迁移会切换数据库连接：请先 close_project（或让用户在界面关闭当前工程）后再迁移。"
        )
    try:
        report = stn_migration.migrate(source, target)
    except stn_migration.MigrationError as error:
        raise ToolError(str(error)) from error
    bus().tree_structure_changed.emit()
    data = {
        "source": report.source,
        "target": report.target,
        "schema_version": report.schema_version,
        "segments": report.segments,
        "units": report.units,
        "elements": report.elements,
        "pipes": report.pipes,
        "enclosures": report.enclosures,
        "foundations": report.foundations,
        "prices": report.prices,
        "warnings": report.warnings,
        "skipped": report.skipped,
        "principle_names": report.principle_names,
        "text": report.text(),
    }
    return {"ok": True, "data": data, "summary": f"迁移完成：{target}"}


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "inspect_legacy_project",
            "只读预览旧 .stn 工程（计数/原则名），不写任何文件。只读。",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            tool_inspect_legacy_project, read_only=True,
        )
    )
    registry.register(
        Tool(
            "migrate_legacy_project",
            "把旧版 1.0 .stn 工程迁移为 2.0 的 .stn 格式（需先关闭当前工程；返回迁移报告）。写操作。",
            {"type": "object", "properties": {
                "source_path": {"type": "string"},
                "target_path": {"type": "string", "description": "默认与源文件同名 .stn"}},
             "required": ["source_path"]},
            tool_migrate_legacy_project,
        )
    )
