"""应用版本与全局常量。

工程文件扩展名、结构版本、备份份数等常量集中在此，避免散落在各模块里。
"""

APP_NAME = "Section2"  # platformdirs 目录名 / QApplication.applicationName
APP_DISPLAY_NAME = "Section 2.0"
APP_ORG_NAME = "Section"
APP_ORG_DOMAIN = "section.local"

#: 程序版本号，与旧版 C# 程序集版本号衔接（旧版 1.2.2.x → 新版 2.0.0.0）
APP_VERSION = "2.0.0.0"

#: .stn2 库结构版本。结构变更时 +1，并在 core/models/base.py 的 _MIGRATIONS 中登记迁移函数。
#: v3：附属构筑物（mcE7，category=7）+ 多原则引用（element_principle 表、element.main_pe_name 列）
#: v4：降水原则 / 面宽原则独立（principle_precipitation / principle_width /
#:     principle_width_item 表、element.pp_name / pw_name 列；围护原则不再携带这两项）
SCHEMA_VERSION = 4

#: 新版工程文件
PROJECT_SUFFIX = ".stn2"
PROJECT_FILE_FILTER = "Section 工程 (*.stn2)"

#: 锁文件 = 工程文件全路径 + LOCK_SUFFIX
LOCK_SUFFIX = ".lock"

#: 自动备份
BACKUP_DIR_NAME = "Backup"
BACKUP_KEEP = 20

#: 默认图集
DEFAULT_ATLAS_NAME = "06MS201-1"
