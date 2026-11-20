"""旧 1.0 `.stn` 迁移的薄兼容层（re-export）。

实际实现全部在独立包 :mod:`app.services.legacy_migration`（架构约束见
docs/legacy_migration_plan.md §0.1.1）：2.0 正常路径不得 import 迁移包，
本模块只为既有调用 / 测试保留旧导入路径（``from app.services import
stn_migration``），自身不做任何解析 / 匹配 / 拆分逻辑。

2.0 侧的正式入口是 :func:`app.services.project_io.open_project`（检测到
1.0 XML 后延迟 import 迁移包）与导入向导
（``views/dialogs/legacy_import_dialog.py``，同样延迟 import）。
"""

from __future__ import annotations

from app.services.legacy_migration import (
    MIGRATION_BACKUP_DIR_NAME,
    LegacyProject,
    MigrationError,
    MigrationReport,
    backup_legacy_file,
    build_legacy_database,
    migrate,
    parse_legacy,
    write_legacy_enclosure,
    write_legacy_foundation,
)
from app.services.legacy_migration.parser import (  # noqa: F401（兼容旧导入路径，全部有意 re-export）
    _LegacyComponent,
    _LegacyElement,
    _LegacyEnclosure,
    _LegacyPipe,
    _LegacySegment,
    _LegacyUnit,
    _LegacyWork,
    _parse_component,
    _parse_enclosure,
    _parse_element,
    _parse_foundation,
    _parse_segment,
    _version_tuple,
)

__all__ = [
    "MigrationError",
    "MigrationReport",
    "LegacyProject",
    "MIGRATION_BACKUP_DIR_NAME",
    "parse_legacy",
    "build_legacy_database",
    "migrate",
    "backup_legacy_file",
    "write_legacy_enclosure",
    "write_legacy_foundation",
    # 兼容旧导入路径的内部名（project_io.import_spcp / 旧测试引用）
    "_LegacyComponent",
    "_LegacyElement",
    "_LegacyEnclosure",
    "_LegacyPipe",
    "_LegacySegment",
    "_LegacyUnit",
    "_LegacyWork",
    "_parse_component",
    "_parse_element",
    "_parse_enclosure",
    "_parse_foundation",
    "_parse_segment",
    "_version_tuple",
]
