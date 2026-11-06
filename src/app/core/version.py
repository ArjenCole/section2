"""应用版本与全局常量。

工程文件扩展名、结构版本、备份份数等常量集中在此，避免散落在各模块里。
"""

APP_NAME = "Section2"  # platformdirs 目录名 / QApplication.applicationName
APP_DISPLAY_NAME = "Section 2.0"
APP_ORG_NAME = "Section"
APP_ORG_DOMAIN = "section.local"

#: 程序版本号。内测/公测阶段带预发布后缀，正式版把构建序号直接写成第 4 段：
#: 2.0.0-alpha.1 → … → 2.0.0-alpha.6 → 2.0.0-beta.7 → … → 2.0.0-rc.9 → 2.0.0.10
#: 显示在窗口标题、关于框、崩溃报告，并写入 .stn 数据体的 app_version。
#: 序号跨渠道连续累加（alpha 到 .6，首个 beta 就是 .7），每发一次包 +1，
#: 这样四段数字版本号单调递增，正式版不会因为去掉后缀而“退回” .0。
APP_VERSION = "2.0.0-alpha.1"

#: 是否为预发布（内测）版本；界面据此标注“内测版”并提示备份数据。
IS_PRERELEASE = "-" in APP_VERSION


def numeric_version(version: str = APP_VERSION) -> str:
    """把语义化版本压成旧版兼容的四段纯数字。

    预发布取后缀序号：``2.0.0-alpha.1`` → ``2.0.0.1``，``2.0.0-beta.7`` →
    ``2.0.0.7``，alpha/beta/rc 之间天然连续累加。

    正式版没有后缀可依，第 4 段必须直接写进版本号（``2.0.0.10``）：本函数
    拿不到“上一个包是几号”，与其悄悄退回 ``.0`` 让 EXE 版本号变小，不如要求
    显式写清。已经是四段的版本原样返回。
    """
    release, _, pre = version.partition("-")
    parts = release.split(".")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"无法解析版本号：{version!r}")
    if len(parts) >= 4:
        return ".".join(parts[:4])
    if not pre:
        raise ValueError(
            f"正式版版本号要写成四段以延续构建序号（如 {release}.10）：{version!r}"
        )
    _, _, tail = pre.partition(".")
    if not tail.isdigit():
        raise ValueError(f"预发布版本号要带序号（如 {release}-alpha.1）：{version!r}")
    return ".".join([*parts, tail])


#: `.stn` 头部 `<Assembly><Version>` 写入的版本号（也用于 EXE 文件版本）。
#: 必须保持 2~4 段纯数字，不能带 ``-alpha.1`` 这类后缀：1.0 的 C# 程序用
#: ``System.Version`` 解析该节点，带后缀会抛 FormatException，本该弹“高版本
#: 文件”提醒的地方会变成崩溃。真实的内测版本号另存在数据体 app_version 里。
STN_HEADER_VERSION = numeric_version(APP_VERSION)

#: 内部工作库（临时 SQLite）结构版本。业务数据以 .stn 文件的 JSON 体为准，
#: 工作库每次打开都按当前代码结构重建，这里只作库内 meta 诊断记录。
SCHEMA_VERSION = 1

#: `.stn` 文件 JSON 数据体的结构版本（见 services/stn_format.py）。
#: 数据结构变更时 +1；打开时高版本拒绝（提示升级），低版本接受并按当前
#: 结构兼容升级（stn_codec 负责旧字段的降级转换，open_project 弹提示）。
#: v2：删除多围护/多地基原则引用（main_pe_name / pe_refs / pf_refs）。
#: 2.0 开发阶段内新增（不升版本号）：构件左右分设（pe_left/pe_right、
#: 支撑勾选、挖填/基础取侧）与合槽编组（groups + element.group），
#: 全部字段可缺省，旧文件读入即默认值；构件公式键统一为 F 类
#: （旧 Z 键在读取时按顺序转写为下一个空闲 F 键）。
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
