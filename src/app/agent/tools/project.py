"""A 组：工程与会话（T01~T07）。"""

from __future__ import annotations

import getpass
from pathlib import Path

from app.agent.errors import ToolError
from app.agent.serializers import tree_dict
from app.agent.tool_registry import Tool, ToolRegistry
from app.agent.tools._common import check_write_path, require_open
from app.core.event_bus import bus
from app.core.models import base as orm
from app.services import project_io
from app.services.project_io import NewProjectSpec


def _project_info() -> dict:
    info = project_io.basic_info()
    path = project_io.current_path()
    backups = 0
    if path is not None:
        folder = project_io.backup_dir(path)
        if folder.exists():
            backups = len(list(folder.glob(f"{Path(path).stem}_*{Path(path).suffix}")))
    return {
        "project_name": info.project_name if info else project_io.project_name(),
        "project_index": info.project_index if info else "",
        "author": info.author if info else "",
        "atlas_name": info.atlas_name if info else "",
        "path": str(path) if path else "",
        "transient": project_io.is_transient(),
        "schema_version": orm.get_meta("schema_version", ""),
        "backup_dir": str(project_io.backup_dir(path)) if path else "",
        "backup_count": backups,
    }


def tool_create_project(arguments: dict) -> dict:
    path_text = str(arguments.get("path") or "").strip()
    if path_text:
        check_write_path(path_text)
    spec = NewProjectSpec(
        path=Path(path_text) if path_text else None,
        project_name=str(arguments.get("project_name") or "新建项目"),
        project_index=str(arguments.get("project_index") or "001"),
        author=str(arguments.get("author") or getpass.getuser()),
        segment_names=[str(name) for name in (arguments.get("segment_names") or ["新建标段"])],
        unit_names=[
            str(name)
            for name in (
                arguments.get("unit_names")
                or ["雨水工程", "污水工程", "给水工程", "中水工程"]
            )
        ],
        enclosure_name=str(arguments.get("enclosure_name") or "默认围护原则"),
        enclosure_excvt=str(arguments.get("excvt") or "Ⅲ类土"),
        enclosure_found_angle=int(arguments.get("found_angle") or 120),
        enclosure_con_found=bool(arguments.get("con_found", True)),
        foundation_name=str(arguments.get("foundation_name") or "默认地基原则"),
        precipitation_name=str(arguments.get("precipitation_name") or "默认降水原则"),
        width_name=str(arguments.get("width_name") or "默认面宽原则"),
    )
    path = project_io.new_project(spec)
    bus().project_opened.emit("" if project_io.is_transient() else str(path))
    return {
        "ok": True,
        "data": {
            "path": str(path) if path else "",
            "transient": project_io.is_transient(),
            "info": _project_info(),
            "tree": tree_dict(),
        },
        "summary": f"已新建工程“{spec.project_name}”",
    }


def tool_open_project(arguments: dict) -> dict:
    path_text = str(arguments.get("path") or "").strip()
    if not path_text:
        raise ToolError("请提供工程文件路径 path（.stn）。")
    target = Path(path_text)
    current = project_io.current_path()
    if current is not None and target.resolve() == Path(current).resolve():
        return {"ok": True, "data": _project_info(), "summary": "工程已打开"}
    if project_io.is_open() and project_io.is_transient():
        raise ToolError("当前是尚未保存的临时工程：请先在界面保存或关闭后再切换工程。")
    opened = project_io.open_project(target)
    bus().project_opened.emit(str(opened) if opened else "")
    notice = project_io.last_migration_notice()
    if opened is not None:
        summary = f"已打开工程：{opened}"
    else:
        summary = (
            f"已打开旧版工程并自动转译（临时工程，尚未保存，原文件已备份）：{target}"
            if notice
            else "已打开临时工程"
        )
    return {
        "ok": True,
        "data": {**_project_info(), "migration_notice": notice},
        "summary": summary,
    }


def tool_close_project(arguments: dict) -> dict:
    require_open()
    if project_io.is_transient():
        raise ToolError("当前是尚未保存的临时工程，关闭会丢失数据：请在界面中保存或关闭。")
    path = project_io.close_project()
    bus().project_closed.emit()
    return {"ok": True, "data": {"path": str(path) if path else ""}}


def tool_save_project(arguments: dict) -> dict:
    require_open()
    if project_io.is_transient():
        raise ToolError("临时工程尚未保存过：请用 save_project_as 指定保存路径。")
    path = project_io.save()
    if path is not None:
        bus().project_saved.emit(str(path))
    return {"ok": True, "data": {"path": str(path) if path else ""}}


def tool_save_project_as(arguments: dict) -> dict:
    require_open()
    path_text = str(arguments.get("path") or "").strip()
    if not path_text:
        raise ToolError("请提供另存为路径 path。")
    check_write_path(path_text)
    path = project_io.save_as(path_text)
    bus().project_saved.emit(str(path))
    bus().project_opened.emit(str(path))
    return {"ok": True, "data": {"path": str(path)}}


def tool_get_project_info(arguments: dict) -> dict:
    require_open()
    return {"ok": True, "data": _project_info()}


def tool_list_recent_projects(arguments: dict) -> dict:
    from app.core.config import get_config

    rows = [
        {"path": path, "exists": Path(path).exists()}
        for path in get_config().recent_projects
        if Path(path).exists()
    ]
    return {"ok": True, "data": {"projects": rows}}


def register(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "create_project",
            "新建工程（临时工程或指定 .stn 路径），自动创建标段/单位工程与四类默认原则。写操作。",
            {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "工程名称"},
                    "project_index": {"type": "string", "description": "项目编号", "default": "001"},
                    "author": {"type": "string", "description": "编制人（默认当前系统用户）"},
                    "path": {"type": "string", "description": "工程文件路径；省略=临时工程（首次保存再定路径）"},
                    "segment_names": {"type": "array", "items": {"type": "string"},
                                      "description": "标段名称列表，默认 [新建标段]"},
                    "unit_names": {"type": "array", "items": {"type": "string"},
                                   "description": "每个标段下的单位工程（专业），如 雨水工程/污水工程"},
                    "excvt": {"type": "string", "description": "默认围护原则开挖土质", "default": "Ⅲ类土"},
                    "found_angle": {"type": "integer", "description": "基础角度 90/120/150/180", "default": 120},
                    "con_found": {"type": "boolean", "description": "是否混凝土基础", "default": True},
                    "enclosure_name": {"type": "string", "description": "默认围护原则名"},
                    "foundation_name": {"type": "string", "description": "默认地基原则名"},
                    "precipitation_name": {"type": "string", "description": "默认降水原则名"},
                    "width_name": {"type": "string", "description": "默认面宽原则名"},
                },
                "required": ["project_name"],
            },
            tool_create_project,
        )
    )
    registry.register(
        Tool(
            "open_project",
            "打开 .stn 工程文件（2.0 文件抢锁重建工作库；1.0 旧文件自动转译为临时工程并备份原文件）。写操作（会话）。",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            tool_open_project,
        )
    )
    registry.register(
        Tool(
            "close_project",
            "关闭当前工程（先 commit 落盘并释放锁）。写操作（会话）。",
            {"type": "object", "properties": {}},
            tool_close_project,
        )
    )
    registry.register(
        Tool(
            "save_project",
            "保存当前工程并创建备份。写操作。",
            {"type": "object", "properties": {}},
            tool_save_project,
        )
    )
    registry.register(
        Tool(
            "save_project_as",
            "另存为（临时工程的首次保存也走这里）。写操作。",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            tool_save_project_as,
        )
    )
    registry.register(
        Tool(
            "get_project_info",
            "读取当前工程信息（名称/编号/编制人/路径/结构版本/备份数量）。只读。",
            {"type": "object", "properties": {}},
            tool_get_project_info,
            read_only=True,
        )
    )
    registry.register(
        Tool(
            "list_recent_projects",
            "列出最近打开的工程（仅返回仍存在的文件）。只读。",
            {"type": "object", "properties": {}},
            tool_list_recent_projects,
            read_only=True,
        )
    )
