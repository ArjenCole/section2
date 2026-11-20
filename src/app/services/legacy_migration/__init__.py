"""1.0 `.stn` → 2.0 迁移独立包（docs/legacy_migration_plan.md §0.1）。

架构约束（优先级最高）：

* **2.0 核心不得反向依赖本包**：启动、正常打开 / 保存 / 计算 / 汇总 / 导出
  路径不 import ``legacy_migration``；只有两处入口延迟 import——
  ``project_io.open_project`` 检测到 1.0 XML 后、``legacy_import_dialog``
  打开导入向导时（另有 ``element_library._from_legacy`` 无 JSON 资产时的
  兜底、``project_io.import_spcp``、AI 迁移工具三处按需延迟 import）；
* **迁移后的文件就是普通 2.0 文件**：写出标准 ``Section2`` JSON，不带
  ``migrated`` / ``is_legacy`` 标记；``legacy_meta`` / ``raw_key`` 是普通
  可选字段，2.0 打开 / 计算路径不区别对待。

对外 API：

* :func:`detect` —— 是否为 1.0 旧版文件；
* :func:`parse` —— 1.0 XML → LegacyProject + 解析报告（逐元素容错）；
* :func:`build_database` —— 解析并写入临时工作库（自动转译共用）；
* :func:`migrate` —— 解析 + 建库 + 写出新 `.stn`（导入向导 / AI 工具用）；
* :func:`backup` —— 原文件备份到软件数据目录（原文件任何情况下不修改）；
* :class:`MigrationReport` —— 迁移报告（计数 + 分节明细 + 警告 / 跳过）。
"""

from __future__ import annotations

from pathlib import Path

from app.services.legacy_migration.parser import (  # noqa: F401（供 project_io.import_spcp 延迟引用）
    LegacyProject,
    MigrationError,
    _parse_enclosure,
    _parse_foundation,
    parse_legacy,
)
from app.services.legacy_migration.report import MigrationReport
from app.services.legacy_migration.writer import (
    MIGRATION_BACKUP_DIR_NAME,
    backup_legacy_file,
    build_legacy_database,
    migrate,
    write_legacy_enclosure,
    write_legacy_foundation,
)

__all__ = [
    "MigrationError",
    "MigrationReport",
    "LegacyProject",
    "MIGRATION_BACKUP_DIR_NAME",
    "detect",
    "parse",
    "parse_legacy",
    "build_database",
    "build_legacy_database",
    "migrate",
    "backup",
    "backup_legacy_file",
    "write_legacy_enclosure",
    "write_legacy_foundation",
    # project_io.import_spcp 延迟引用的解析入口
    "_parse_enclosure",
    "_parse_foundation",
]


def detect(path: str | Path) -> bool:
    """是否为 1.0 旧版程序保存的 `.stn`（XML 整体、无 Section2 数据体）。"""
    from app.services.stn_format import looks_like_legacy_file

    return looks_like_legacy_file(path)


#: 解析入口（与 parse_legacy 同一实现；报告可传入共用）
def parse(path: str | Path, report: MigrationReport | None = None):
    return parse_legacy(path, report)
