"""工具层公共辅助。"""

from __future__ import annotations

from pathlib import Path

from app.agent.errors import ToolError
from app.core.models.models import (
    CATEGORY_CHOICES,
    category_from_name,
)


def require_open() -> None:
    from app.services import project_io

    if not project_io.is_open():
        raise ToolError("当前没有打开的工程，请先 open_project（或 create_project）。")


def parse_category(value, default: int | None = None) -> int:
    if value in (None, ""):
        if default is None:
            raise ToolError("请提供构件类别 category。")
        return default
    if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
        number = int(value)
        if number not in CATEGORY_CHOICES:
            raise ToolError(f"类别编号 {number} 无效。可用：{CATEGORY_CHOICES}")
        return number
    number = category_from_name(str(value))
    if number not in CATEGORY_CHOICES:
        raise ToolError("构件类别无效。可用：直埋管道/包封埋管/箱涵/顶管/牵引管/管廊/构筑物。")
    return number


def validate_principle_names(
    pe_name=None,
    pf_name=None,
    pp_name=None,
    pw_name=None,
) -> None:
    from app.services import project_io

    checks = (
        ("围护", pe_name, project_io.enclosure_names()),
        ("地基", pf_name, project_io.foundation_names()),
        ("降水", pp_name, project_io.precipitation_names()),
        ("面宽", pw_name, project_io.width_names()),
    )
    for label, name, names in checks:
        if name and name not in names:
            raise ToolError(f"{label}原则“{name}”不存在。可用：{'、'.join(names) or '（无）'}")


def call_edit(function, *args, **kwargs):
    """调用 principle_edit 纯函数并把业务错误转成 ToolError。"""
    from app.services.principle_edit import PrincipleEditError

    try:
        return function(*args, **kwargs)
    except PrincipleEditError as error:
        raise ToolError(str(error)) from error


def check_write_path(path: str) -> Path:
    """MCP 通道的文件写入路径白名单（[mcp] allowed_dirs；空 = 不限制）。"""
    from app.agent.confirm_policy import CHANNEL_MCP, current_channel
    from app.core.config import get_config

    target = Path(path)
    if current_channel() != CHANNEL_MCP:
        return target
    allowed = get_config().mcp_allowed_dirs
    if not allowed:
        return target
    resolved = target.resolve()
    for folder in allowed:
        try:
            if resolved.is_relative_to(Path(folder).resolve()):
                return target
        except (OSError, ValueError):
            continue
    raise ToolError(f"路径不在 [mcp] allowed_dirs 允许目录内：{target}")


def find_principle(kind: str, name: str):
    """按类型与名称取原则对象（kind: enclosure/foundation/precipitation/width）。"""
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import (
        PcpEnclosure,
        PcpFoundation,
        PcpPrecipitation,
        PcpWidth,
    )

    model = {
        "enclosure": PcpEnclosure,
        "foundation": PcpFoundation,
        "precipitation": PcpPrecipitation,
        "width": PcpWidth,
    }.get(kind)
    if model is None:
        raise ToolError("kind 只能是 enclosure / foundation / precipitation / width。")
    if isinstance(name, int) or (isinstance(name, str) and name.isdigit()):
        obj = orm.session().get(model, int(name))
    else:
        obj = orm.session().scalar(select(model).where(model.name == str(name)).order_by(model.id))
    if obj is None:
        raise ToolError(f"{kind} 原则“{name}”不存在。请先调 list_principles。")
    return obj
