"""应用版本与全局常量。

对应计划 §3 `core/version.py`；工程文件扩展名、备份份数等常量集中在此，
避免散落在各模块里。
"""

APP_NAME = "Section2"  # platformdirs 目录名 / QApplication.applicationName
APP_DISPLAY_NAME = "Section 2.0"
APP_ORG_NAME = "Section"
APP_ORG_DOMAIN = "section.local"

#: 程序版本号，与旧版 C# 程序集版本号衔接（旧版 1.2.2.x → 新版 2.0.0.0）
APP_VERSION = "2.0.0.0"

#: .stn2 库结构版本。结构变更时 +1，并在 app/orm/base.py 的 _MIGRATIONS 中登记迁移函数。
SCHEMA_VERSION = 1

#: 新版工程文件
PROJECT_SUFFIX = ".stn2"
PROJECT_FILE_FILTER = "Section 工程 (*.stn2)"

#: 旧版工程文件（M6 迁移入口只读使用）
LEGACY_SUFFIX = ".stn"
LEGACY_FILE_FILTER = "旧版 Section 工程 (*.stn)"

#: 锁文件 = 工程文件全路径 + LOCK_SUFFIX
LOCK_SUFFIX = ".lock"

#: 自动备份（计划 §5）
BACKUP_DIR_NAME = "Backup"
BACKUP_KEEP = 20

#: 默认图集
DEFAULT_ATLAS_NAME = "06MS201-1"
