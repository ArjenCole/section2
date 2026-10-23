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
#: v5：构件参数拆“参数名 / 单位”（element_param.unit 列、pipe.t 管道壁厚列）；
#:     附属构筑物工程量独立成表（element_quantity，“类别|项目|单位”三段参数迁走）
#: v6：工作面加宽 / 垫层厚 / 基础厚 三行按构件类别收敛：直埋管道三行都显示
#:     （默认按图集、可改），包封埋管 / 箱涵 / 管廊只显示工作面加宽 / 垫层厚
#:     （基础厚恒为 0，不显示、不可改），顶管 / 牵引管不显示
#:     （见 param_naming.ATLAS_PARAM_CATEGORIES）
#: v7：按类别再收敛一次（v6 的早期实现误删了直埋 / 箱涵 / 管廊上的图集行）
#: v8：管道行加“管材类别”列（pipe.cat）：面宽匹配 / 图集分流 / 断面图砼判断 /
#:     包封扣管位统一读它，不再按管材名称做字符串包含判断（见 core.pipe_category）
#: v9：图集候选参数列（element_atlas_candidate 表）：直埋构件的 a/C1/C2 按
#:     当前围护原则从 8 组快照（砼/非砼 × 90/120/150/180）自动选组，参数值列
#:     锁定；候选是一次性快照、可手改（见 core.atlas_candidates）
SCHEMA_VERSION = 9

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
