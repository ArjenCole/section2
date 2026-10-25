"""应用版本与全局常量。

工程文件扩展名、结构版本、备份份数等常量集中在此，避免散落在各模块里。
"""

APP_NAME = "Section2"  # platformdirs 目录名 / QApplication.applicationName
APP_DISPLAY_NAME = "Section 2.0"
APP_ORG_NAME = "Section"
APP_ORG_DOMAIN = "section.local"

#: 程序版本号，与旧版 C# 程序集版本号衔接（旧版 1.2.2.x → 新版 2.0.0.0）
APP_VERSION = "2.0.0.0"

#: 内部工作库（临时 SQLite）结构版本。业务数据以 .stn 文件的 JSON 体为准，
#: 工作库每次打开都按当前代码结构重建，这里只作库内 meta 诊断记录。
SCHEMA_VERSION = 1

#: `.stn` 文件 JSON 数据体的结构版本（见 services/stn_format.py）。
#: 数据结构变更时 +1；打开时高版本拒绝（提示升级），低版本接受并按当前
#: 结构兼容升级（stn_codec 负责旧字段的降级转换，open_project 弹提示）。
#: v2：删除多围护/多地基原则引用（main_pe_name / pe_refs / pf_refs）。
#: 2.0 开发阶段内新增（不升版本号）：构件左右分设（pe_left/pe_right、
#: 支撑勾选、挖填/基础取侧）与合槽编组（groups + element.group），
#: 全部字段可缺省，旧文件读入即默认值。
STN_FILE_VERSION = 2

#: 新版工程文件：1.0 风格的 XML 头（供 1.0 软件识别“高版本文件”并提醒）
#: + CDATA 包裹的 JSON 数据体（services/stn_format.py）。
PROJECT_SUFFIX = ".stn"
PROJECT_FILE_FILTER = "Section 工程 (*.stn)"

#: 锁文件 = 工程文件全路径 + LOCK_SUFFIX
LOCK_SUFFIX = ".lock"

#: 自动备份
BACKUP_DIR_NAME = "Backup"
BACKUP_KEEP = 20

#: 默认图集
DEFAULT_ATLAS_NAME = "06MS201-1"
