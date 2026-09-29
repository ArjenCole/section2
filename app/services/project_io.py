"""工程文件生命周期（计划 §5）。

新建 / 打开 / 保存 / 另存为 / 关闭、``.lock`` 文件锁防双开、Backup 自动备份、
结构版本校验。业务代码不直接建连接，统一走这里。

本模块刻意不依赖 Qt，方便直接跑测试；界面层的刷新由调用方通过 EventBus 广播。
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import SubElement

from sqlalchemy import func, select

from app.core.version import (
    APP_VERSION,
    BACKUP_DIR_NAME,
    BACKUP_KEEP,
    DEFAULT_ATLAS_NAME,
    LOCK_SUFFIX,
    PROJECT_SUFFIX,
)
from app.orm import base as orm
from app.orm.models import (
    PRECIPITATION_DEFAULTS,
    BasicInfo,
    Component,
    ComponentParam,
    EnclosureCushion,
    EnclosureLevel,
    EnclosureWork,
    PcpEnclosure,
    PcpFoundation,
    Segment,
    Unit,
    WorkWidth,
    format_precipitation,
)


class ProjectIoError(orm.ProjectFileError):
    """工程文件操作失败（统一继承 orm.ProjectFileError，上层只 catch 基类即可）。"""


class ProjectLockedError(ProjectIoError):
    """工程已在另一个窗口打开。"""

    def __init__(self, path: Path, pid: int | None, opened_at: str) -> None:
        self.path = Path(path)
        self.pid = pid
        self.opened_at = opened_at
        detail = f"（进程 {pid}，{opened_at}）" if pid else ""
        super().__init__(f"该工程已在另一窗口打开{detail}：{self.path}")


@dataclass
class NewProjectSpec:
    """新建向导收集到的信息。

    ``path`` 为 ``None`` 时新建"临时工程"：数据库建在系统临时目录，
    不要求用户立即选择保存位置，首次保存（另存为）时才确定文件路径
    （与 Quotor 的临时项目机制一致）。
    """

    path: Path | None = None
    project_name: str = "新建项目"
    project_index: str = "001"
    author: str = ""
    atlas_name: str = DEFAULT_ATLAS_NAME
    #: 标段名称列表（向导里通常都是“新建标段”）
    segment_names: list[str] = field(default_factory=lambda: ["新建标段"])
    #: 每个标段下默认建的单位工程名称（对应旧版“涵盖专业”勾选项）
    unit_names: list[str] = field(default_factory=list)
    #: 默认围护原则
    enclosure_name: str = "默认围护原则"
    enclosure_excvt: str = "Ⅲ类土"
    enclosure_found_angle: int = 120
    enclosure_con_found: bool = True
    #: 默认地基处理原则
    foundation_name: str = "默认地基处理原则"


# 最近一次“首次修改备份”是否已做过：每打开一个工程重置一次
_backup_done_for_session = False
# 工程原文件路径；None 表示临时工程（尚未保存到文件，数据库在临时目录）
_original_path: Path | None = None


# --------------------------------------------------------------------------- #
# 路径与锁
# --------------------------------------------------------------------------- #
def lock_path(path: str | Path) -> Path:
    return Path(f"{path}{LOCK_SUFFIX}")


def backup_dir(path: str | Path) -> Path:
    """备份目录：工程同级\\Backup。"""
    return Path(path).parent / BACKUP_DIR_NAME


def _process_alive(pid: int) -> bool:
    """判断进程是否还活着（不依赖第三方库）。

    Windows 上不能用 os.kill(pid, 0)——那会真的把目标进程 TerminateProcess 掉。
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        return _process_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except OSError as error:
        return error.errno == errno.EPERM  # 无权限 = 进程存在
    return True


def _process_alive_windows(pid: int) -> bool:
    """OpenProcess + GetExitCodeProcess；HANDLE 是 64 位，必须显式声明 restype。"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # 打不开：拒绝访问说明进程还在（只是权限不够），其余情况视为不存在
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def acquire_lock(path: str | Path) -> None:
    """获取工程锁；已被存活进程占用则抛 ProjectLockedError。

    锁文件里是上一次写入的 pid + 时间，pid 已死（上次崩溃/强杀）时自动接管。
    """
    lock = lock_path(path)
    if lock.exists():
        pid: int | None = None
        opened_at = ""
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0)) or None
            opened_at = str(data.get("opened_at", ""))
        except (OSError, ValueError, TypeError):
            data = {}
        if pid and pid != os.getpid() and _process_alive(pid):
            raise ProjectLockedError(Path(path), pid, opened_at)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "opened_at": datetime.now().isoformat(timespec="seconds"),
                "app_version": APP_VERSION,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def release_lock(path: str | Path | None) -> None:
    """释放自己持有的锁；别人的锁不动。"""
    if path is None:
        return
    lock = lock_path(path)
    if not lock.exists():
        return
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
        if int(data.get("pid", 0)) not in (0, os.getpid()):
            return
    except (OSError, ValueError, TypeError):
        pass
    try:
        lock.unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# 新建 / 打开 / 保存 / 关闭
# --------------------------------------------------------------------------- #
def new_project(spec: NewProjectSpec) -> Path:
    """按向导收集的信息建工程并打开。

    ``spec.path`` 为 ``None`` 时新建临时工程：数据库建在系统临时目录、
    不加文件锁、不进最近列表，首次保存（save_as）时才确定正式路径。
    指定路径时同路径已存在的旧文件会被覆盖。
    """
    global _original_path, _backup_done_for_session

    path = Path(spec.path) if spec.path is not None else None
    close_project()
    if path is None:
        # 临时工程：临时目录里建唯一文件（Quotor create_transient_project_db 同款）
        handle, temp_name = tempfile.mkstemp(prefix="section2_", suffix=PROJECT_SUFFIX)
        os.close(handle)
        path = Path(temp_name)
        _original_path = None
        try:
            orm.create_database(path)
            _seed_new_project(spec)
        except Exception:
            orm.close_database()
            path.unlink(missing_ok=True)
            raise
        _backup_done_for_session = False
        return path

    if path.suffix.lower() != PROJECT_SUFFIX:
        path = path.with_suffix(PROJECT_SUFFIX)
    if path.exists():
        release_lock(path)
        path.unlink()
    acquire_lock(path)
    try:
        orm.create_database(path)
        _seed_new_project(spec)
    except Exception:
        orm.close_database()
        release_lock(path)
        raise
    _original_path = path
    _backup_done_for_session = False
    return path


def _seed_new_project(spec: NewProjectSpec) -> None:
    """往刚建好的空库里写工程信息、标段/单位工程与默认原则。"""
    session = orm.session()
    session.add(
        BasicInfo(
            id=1,
            project_name=spec.project_name or "新建项目",
            project_index=spec.project_index,
            author=spec.author,
            atlas_name=spec.atlas_name or DEFAULT_ATLAS_NAME,
        )
    )
    root_names = spec.segment_names or ["新建标段"]
    for index, name in enumerate(root_names):
        segment = Segment(name=name or "新建标段", order_no=index)
        for unit_index, unit_name in enumerate(spec.unit_names):
            segment.units.append(Unit(name=unit_name, order_no=unit_index))
        session.add(segment)
    _seed_default_principles(session, spec)
    orm.commit()


def open_project(path: str | Path) -> Path:
    """打开工程：抢锁 → 校验结构版本 → 绑定会话。"""
    global _original_path, _backup_done_for_session

    target = Path(path)
    close_project()
    if not target.exists():
        raise ProjectIoError(f"工程文件不存在：{target}")
    acquire_lock(target)
    try:
        orm.open_database(target)
        _ensure_basic_info()
    except Exception as error:
        orm.close_database()
        release_lock(target)
        if isinstance(error, orm.ProjectFileError):
            raise
        raise ProjectIoError(f"打开工程失败：{error}") from error
    _original_path = target
    _backup_done_for_session = False
    return target


def save() -> Path | None:
    """显式保存：落盘 + 备份一份。

    临时工程（尚未保存过）没有可保存的文件，由界面层引导用户
    走另存为流程选择保存位置。
    """
    if _original_path is None:
        raise ProjectIoError("工程尚未保存过，请先选择保存位置。")
    path = orm.database_path()
    if path is None:
        return None
    _commit_and_backup(force_backup=True)
    return path


def save_as(path: str | Path) -> Path:
    """另存为（也承担临时工程的首次保存）：把当前内容整体复制到新路径，
    之后继续在新文件上工作；临时工程的临时库随手删除。"""
    global _original_path, _backup_done_for_session

    old_path = orm.database_path()
    was_transient = _original_path is None
    target = Path(path)
    if target.suffix.lower() != PROJECT_SUFFIX:
        target = target.with_suffix(PROJECT_SUFFIX)
    if old_path is None:
        raise ProjectIoError("尚未打开工程，无法另存为。")
    if not was_transient and target.resolve() == Path(old_path).resolve():
        return _original_path
    if target.exists():
        release_lock(target)
        target.unlink()

    orm.commit()  # 先落盘，保证复制出来的文件是最新的
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old_path, target)
    orm.close_database()
    release_lock(old_path)
    if was_transient:
        old_path.unlink(missing_ok=True)  # 临时库不再需要
    acquire_lock(target)
    try:
        orm.open_database(target)
    except Exception:
        orm.close_database()
        release_lock(target)
        raise
    _original_path = target
    _backup_done_for_session = False
    return target


def close_project() -> Path | None:
    """关闭工程：落盘 → 关会话 → 释放锁；临时工程随手删掉临时库。"""
    global _original_path, _backup_done_for_session

    path = orm.database_path()
    if path is None:
        return None
    was_transient = _original_path is None
    try:
        orm.commit()
    finally:
        orm.close_database()
        release_lock(path)
    if was_transient:
        path.unlink(missing_ok=True)
    _original_path = None
    _backup_done_for_session = False
    return path


def commit() -> None:
    """一次修改落盘（自动保存）；本次打开后的第一次修改会顺手备份一份。"""
    _commit_and_backup(force_backup=False)


def _commit_and_backup(*, force_backup: bool) -> None:
    global _backup_done_for_session

    if not orm.is_open():
        return
    orm.commit()
    if _original_path is None:
        return  # 临时工程没有原文件，备份到临时目录没有意义
    if force_backup or not _backup_done_for_session:
        create_backup()
        _backup_done_for_session = True


def current_path() -> Path | None:
    """工程原文件路径；临时工程（尚未保存）返回 None。"""
    return _original_path


def is_transient() -> bool:
    """当前是否为临时工程：已打开但从未保存到文件。"""
    return orm.is_open() and _original_path is None


def is_open() -> bool:
    return orm.is_open()


def project_name() -> str:
    if not orm.is_open():
        return ""
    session = orm.session()
    info = session.get(BasicInfo, 1)
    return info.project_name if info is not None else ""


def basic_info() -> BasicInfo | None:
    if not orm.is_open():
        return None
    return orm.session().get(BasicInfo, 1)


def set_basic_info(**fields: str) -> None:
    """修改工程基本信息（项目名称/编号/编制人/图集）。"""
    info = basic_info()
    if info is None:
        return
    for key, value in fields.items():
        if hasattr(info, key):
            setattr(info, key, value)
    commit()


# --------------------------------------------------------------------------- #
# 查询辅助（供树面板 / 下拉框使用）
# --------------------------------------------------------------------------- #
def segments() -> list[Segment]:
    if not orm.is_open():
        return []
    return list(orm.session().scalars(select(Segment).order_by(Segment.order_no, Segment.id)))


def units(segment_id: int) -> list[Unit]:
    if not orm.is_open():
        return []
    return list(
        orm.session().scalars(
            select(Unit).where(Unit.segment_id == segment_id).order_by(Unit.order_no, Unit.id)
        )
    )


def move_segment(segment_id: int, index: int) -> None:
    """把标段移到同级第 index 个位置（其余标段顺序归一化；Quotor move_node 语义）。"""
    if not orm.is_open():
        return
    session = orm.session()
    segment = session.get(Segment, segment_id)
    if segment is None:
        return
    ordered = [item for item in segments() if item.id != segment_id]
    index = max(0, min(index, len(ordered)))
    ordered.insert(index, segment)
    for position, item in enumerate(ordered):
        item.order_no = position
    commit()


def move_unit(unit_id: int, target_segment_id: int, index: int) -> None:
    """把单位工程移到 target_segment 下第 index 个位置（跨标段移动与排序二合一）。"""
    if not orm.is_open():
        return
    session = orm.session()
    unit = session.get(Unit, unit_id)
    if unit is None or session.get(Segment, target_segment_id) is None:
        return
    unit.segment_id = target_segment_id
    siblings = [item for item in units(target_segment_id) if item.id != unit_id]
    index = max(0, min(index, len(siblings)))
    siblings.insert(index, unit)
    for position, item in enumerate(siblings):
        item.order_no = position
    commit()


def unit_names() -> list[str]:
    if not orm.is_open():
        return []
    return [unit.name for unit in orm.session().scalars(select(Unit).order_by(Unit.order_no, Unit.id))]


def enclosure_names() -> list[str]:
    if not orm.is_open():
        return []
    return [
        row
        for row in orm.session().scalars(
            select(PcpEnclosure.name).order_by(PcpEnclosure.order_no, PcpEnclosure.id)
        )
    ]


def foundation_names() -> list[str]:
    if not orm.is_open():
        return []
    return [
        row
        for row in orm.session().scalars(
            select(PcpFoundation.name).order_by(PcpFoundation.order_no, PcpFoundation.id)
        )
    ]


# --------------------------------------------------------------------------- #
# 单价字典（M5 汇总页用；key = 类别|项目|单位）
# --------------------------------------------------------------------------- #
def prices() -> dict[str, float]:
    if not orm.is_open():
        return {}
    from app.orm.models import Price

    return {row.key: row.value for row in orm.session().scalars(select(Price))}


def get_price(key: str) -> float:
    """单价；未填为 0（旧版 mscCtrl.getPrice）。"""
    if not orm.is_open():
        return 0.0
    from app.orm.models import Price

    row = orm.session().scalars(select(Price).where(Price.key == key)).first()
    return row.value if row is not None else 0.0


def set_price(key: str, value: float) -> None:
    """写入/更新单价（旧版 mscCtrl.setPrice）。"""
    if not orm.is_open():
        return
    from app.orm.models import Price

    session = orm.session()
    row = session.scalars(select(Price).where(Price.key == key)).first()
    if row is None:
        session.add(Price(key=key, value=float(value)))
    else:
        row.value = float(value)
    commit()


def clear_prices() -> None:
    if not orm.is_open():
        return
    from app.orm.models import Price

    orm.session().query(Price).delete()
    commit()


def next_order_no(model, **filters) -> int:
    """取某张表在给定父行下的下一个 order_no。"""
    if not orm.is_open():
        return 0
    statement = select(func.coalesce(func.max(model.order_no), -1) + 1)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int(orm.session().scalar(statement) or 0)


# --------------------------------------------------------------------------- #
# 原则的增删改（M3 原则编辑器用）
# --------------------------------------------------------------------------- #
def enclosures() -> list[PcpEnclosure]:
    if not orm.is_open():
        return []
    return list(
        orm.session().scalars(
            select(PcpEnclosure).order_by(PcpEnclosure.order_no, PcpEnclosure.id)
        )
    )


def foundations() -> list[PcpFoundation]:
    if not orm.is_open():
        return []
    return list(
        orm.session().scalars(
            select(PcpFoundation).order_by(PcpFoundation.order_no, PcpFoundation.id)
        )
    )


def enclosure_users(name: str) -> list[str]:
    """引用某围护原则的构件条目名（删除确认框展示用）。"""
    if not orm.is_open() or not name:
        return []
    from app.orm.models import Element

    return [
        row
        for row in orm.session().scalars(
            select(Element.name).where(Element.pe_name == name).limit(20)
        )
    ]


def foundation_users(name: str) -> list[str]:
    if not orm.is_open() or not name:
        return []
    from app.orm.models import Element

    return [
        row
        for row in orm.session().scalars(
            select(Element.name).where(Element.pf_name == name).limit(20)
        )
    ]


def create_enclosure(name: str = "新围护原则") -> PcpEnclosure | None:
    """新建围护原则：默认做法 + 默认宽度表（复刻旧版 mcPcpEnclosure 构造）。

    重名时自动追加数字后缀（原版 mscMslns.ReNameToAdd）。
    """
    if not orm.is_open():
        return None
    library = component_library()
    session = orm.session()
    enclosure = PcpEnclosure(
        name=unique_principle_name(name or "新围护原则", enclosure_names()),
        order_no=next_order_no(PcpEnclosure),
    )
    enclosure.cushions.append(EnclosureCushion(name="中粗砂", h=200.0, order_no=0))
    for key, (elevation, gap, sides) in PRECIPITATION_DEFAULTS.items():
        setattr(enclosure, key, format_precipitation(elevation, gap, sides))
    session.add(enclosure)
    orm.session().flush()
    new_enclosure_work(session, enclosure, library, order_no=0)
    seed_width_tables(session, enclosure, *default_width_tables())
    commit()
    return enclosure


def create_foundation(name: str = "新地基原则") -> PcpFoundation | None:
    """新建地基原则（换填层为空 + 特殊地基构件“无”）。重名自动加后缀。"""
    if not orm.is_open():
        return None
    session = orm.session()
    foundation = PcpFoundation(
        name=unique_principle_name(name or "新地基原则", foundation_names()),
        order_no=next_order_no(PcpFoundation),
    )
    session.add(foundation)
    orm.session().flush()
    attach_foundation_component(session, foundation, component_library())
    commit()
    return foundation


def rename_enclosure(enclosure_id: int, name: str) -> None:
    enclosure = orm.session().get(PcpEnclosure, enclosure_id)
    if enclosure is None or not name.strip() or enclosure.name == name.strip():
        return
    old = enclosure.name
    new = name.strip()
    enclosure.name = new
    _rename_principle_reference(orm.session(), "pe_name", old, new)
    commit()


def rename_foundation(foundation_id: int, name: str) -> None:
    foundation = orm.session().get(PcpFoundation, foundation_id)
    if foundation is None or not name.strip() or foundation.name == name.strip():
        return
    old = foundation.name
    new = name.strip()
    foundation.name = new
    _rename_principle_reference(orm.session(), "pf_name", old, new)
    commit()


def _rename_principle_reference(session, field: str, old: str, new: str) -> None:
    from app.orm.models import Element

    for element in session.scalars(select(Element).where(getattr(Element, field) == old)):
        setattr(element, field, new)


def merge_target_enclosure(name: str) -> str | None:
    """删除围护原则时引用的替代去向（原版取“其余原则的最后一条”）。"""
    names = [item.name for item in enclosures() if item.name != name]
    return names[-1] if names else None


def merge_target_foundation(name: str) -> str | None:
    names = [item.name for item in foundations() if item.name != name]
    return names[-1] if names else None


def unique_principle_name(base: str, existing: list[str]) -> str:
    """原则名重名时自动追加数字后缀（原版 mscMslns.ReNameToAdd）。"""
    name = base
    index = 1
    while name in existing:
        name = f"{base}{index}"
        index += 1
    return name


def delete_enclosure(enclosure_id: int, replacement: str | None = None) -> str | None:
    """删除围护原则（原版 mscCtrl.Delete 语义）。

    只剩最后一条时返回提示文案、不删除；删除时所有引用并入 ``replacement``
    原则（缺省取其余原则的最后一条），调用方负责先弹确认框。
    """
    if not orm.is_open():
        return "尚未打开工程。"
    enclosure = orm.session().get(PcpEnclosure, enclosure_id)
    if enclosure is None:
        return None
    if len(enclosures()) <= 1:
        return "至少需要一种沟槽围护原则。"
    target = replacement or merge_target_enclosure(enclosure.name)
    if not target or target == enclosure.name:
        return "找不到可替代引用的围护原则。"
    _rename_principle_reference(orm.session(), "pe_name", enclosure.name, target)
    orm.session().delete(enclosure)
    commit()
    return None


def delete_foundation(foundation_id: int, replacement: str | None = None) -> str | None:
    """删除地基原则（原版 mscCtrl.Delete 语义），引用并入另一条。"""
    if not orm.is_open():
        return "尚未打开工程。"
    foundation = orm.session().get(PcpFoundation, foundation_id)
    if foundation is None:
        return None
    if len(foundations()) <= 1:
        return "至少需要一种地基处理原则。"
    target = replacement or merge_target_foundation(foundation.name)
    if not target or target == foundation.name:
        return "找不到可替代引用的地基处理原则。"
    _rename_principle_reference(orm.session(), "pf_name", foundation.name, target)
    orm.session().delete(foundation)
    commit()
    return None


# --------------------------------------------------------------------------- #
# *.spcp 单原则导入/导出（复刻旧版 CMSpcp 菜单，XML 字段与旧版 toXML 一致）
# --------------------------------------------------------------------------- #
_SPCP_PE_ROOT = "mcPcpEnclosure"
_SPCP_PF_ROOT = "mcPcpFoundation"
_PRECIPITATION_XML_KEYS = (
    ("wet_soil", "wetsoild"),
    ("light_well", "lightwell"),
    ("jet_well", "jetwell"),
    ("big_well", "bigwell"),
    ("deep_well", "deepwell"),
)


def export_enclosure_spcp(enclosure_id: int, path: str | Path) -> Path:
    """导出围护原则为 *.spcp（旧版 mcPcpEnclosure.toXML 格式）。"""
    enclosure = orm.session().get(PcpEnclosure, enclosure_id)
    if enclosure is None:
        raise ProjectIoError("围护原则不存在。")
    root = ET.Element(_SPCP_PE_ROOT)
    SubElement(root, "Name").text = enclosure.name
    SubElement(root, "ConFound").text = "true" if enclosure.con_found else "false"
    SubElement(root, "Excvt").text = enclosure.excvt
    SubElement(root, "FoundAngle").text = str(enclosure.found_angle)
    SubElement(root, "Count").text = str(max(1, len(enclosure.cushions)))
    cushion = root.makeelement("Cush", {})
    for item in enclosure.cushions:
        replacement = SubElement(cushion, "msReplacement")
        SubElement(replacement, "Name").text = item.name
        SubElement(replacement, "H").text = _number_text(item.h)
    root.append(cushion)
    SubElement(root, "DockL").text = enclosure.dock_l
    SubElement(root, "DockH").text = enclosure.dock_h
    SubElement(root, "Cover50").text = enclosure.cover50
    SubElement(root, "Cover").text = enclosure.cover
    for field, tag in _PRECIPITATION_XML_KEYS:
        SubElement(root, tag).text = getattr(enclosure, field)
    SubElement(root, "grooveWidth").text = enclosure.groove_width
    for kind, tag in (("work", "WorkWidth"), ("groove_b", "GrooveB")):
        container = SubElement(root, tag)
        tables: dict[str, dict[int, float]] = {}
        for row in enclosure.widths:
            if row.kind != kind:
                continue
            tables.setdefault(row.pipe_type, {})[row.dn] = row.width
        for pipe_type in sorted(tables):
            category_node = SubElement(container, pipe_type)
            for dn in sorted(tables[pipe_type]):
                SubElement(category_node, f"d{dn}").text = _number_text(tables[pipe_type][dn])
    for work in enclosure.works:
        work_node = SubElement(root, "mcEnclosure")
        SubElement(work_node, "MinDepth").text = _number_text(work.min_depth)
        SubElement(work_node, "eCpntCat").text = work.cpnt_cat
        for level in work.levels:
            level_node = SubElement(work_node, "mcEclsCpnt")
            SubElement(level_node, "name").text = level.name
            SubElement(level_node, "H").text = _number_text(level.h)
            SubElement(level_node, "stepWidth").text = _number_text(level.step_width)
            for component in level.components:
                level_node.append(_component_xml(component))
        waterstop_node = SubElement(work_node, "WSCpnt")
        for component in work.waterstops:
            waterstop_node.append(_component_xml(component))
    return _write_spcp(root, path)


def export_foundation_spcp(foundation_id: int, path: str | Path) -> Path:
    """导出地基处理原则为 *.spcp（旧版 mcPcpFoundation.toXML 格式）。"""
    foundation = orm.session().get(PcpFoundation, foundation_id)
    if foundation is None:
        raise ProjectIoError("地基处理原则不存在。")
    root = ET.Element(_SPCP_PF_ROOT)
    SubElement(root, "Name").text = foundation.name
    for item in foundation.replacements:
        replacement = SubElement(root, "msReplacement")
        SubElement(replacement, "Name").text = item.name
        SubElement(replacement, "H").text = _number_text(item.h)
    foundation_node = SubElement(root, "Foundation")
    for component in foundation.components:
        foundation_node.append(_component_xml(component))
    return _write_spcp(root, path)


def import_spcp(path: str | Path) -> tuple[str, str]:
    """导入 *.spcp，返回 (kind, 新原则名)；kind 为 "enclosure" / "foundation"。

    XML 结构与旧版一致；原则名与现有原则重名时自动加后缀。
    """
    source = Path(path)
    try:
        root = ET.parse(source).getroot()
    except ET.ParseError as error:
        raise ProjectIoError(f"原则文件不是有效的 XML：{error}") from error
    from app.services import stn_migration
    from app.services.atlas import component_library

    library = component_library()
    session = orm.session()
    if root.tag == _SPCP_PE_ROOT:
        legacy = stn_migration._parse_enclosure(root, "")
        legacy.name = unique_principle_name(legacy.name, enclosure_names())
        enclosure = stn_migration.write_legacy_enclosure(session, legacy, library,
                                                         order_no=next_order_no(PcpEnclosure))
        commit()
        return "enclosure", enclosure.name
    if root.tag == _SPCP_PF_ROOT:
        legacy = stn_migration._parse_foundation(root)
        legacy = (unique_principle_name(legacy[0], foundation_names()), legacy[1], legacy[2])
        foundation = stn_migration.write_legacy_foundation(session, legacy, library,
                                                           order_no=next_order_no(PcpFoundation))
        commit()
        return "foundation", foundation.name
    raise ProjectIoError("不是有效的原则文件（缺少 mcPcpEnclosure / mcPcpFoundation 根元素）。")


def _component_xml(component: Component) -> ET.Element:
    node = ET.Element("mcComponent")
    SubElement(node, "Name").text = f"{component.name}|{component.formula or ''}"
    for param in component.params:
        SubElement(node, param.key).text = param.value or ""
    return node


def _write_spcp(root: ET.Element, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    text = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n' + body
    target.write_text(text, encoding="utf-8")
    return target


def _number_text(value) -> str:
    number = float(value)
    return f"{number:g}"


# --------------------------------------------------------------------------- #
# 备份
# --------------------------------------------------------------------------- #
def create_backup() -> Path | None:
    """把当前工程文件复制到 工程同级\\Backup\\<工程名>_yyMMdd_HHmmss.stn2，并只保留最近 20 份。"""
    path = orm.database_path()
    if path is None or not Path(path).exists():
        return None
    target = _next_backup_path(Path(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    _prune_backups(Path(path))
    return target


def _next_backup_path(path: Path) -> Path:
    folder = backup_dir(path)
    stamp = datetime.now().strftime("%y%m%d_%H%M%S")
    candidate = folder / f"{path.stem}_{stamp}{path.suffix}"
    counter = 1
    while candidate.exists():
        candidate = folder / f"{path.stem}_{stamp}_{counter}{path.suffix}"
        counter += 1
    return candidate


def _prune_backups(path: Path) -> None:
    """同名工程的备份只保留最近 BACKUP_KEEP 份（按文件名时间戳排序）。"""
    folder = backup_dir(path)
    if not folder.exists():
        return
    backups = sorted(
        folder.glob(f"{path.stem}_*{path.suffix}"),
        key=lambda item: item.name,
    )
    for stale in backups[:-BACKUP_KEEP]:
        try:
            stale.unlink()
        except OSError:
            pass


def backups(path: str | Path) -> list[Path]:
    """列出某工程的备份文件（新到旧）。"""
    folder = backup_dir(path)
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{Path(path).stem}_*{Path(path).suffix}"), key=lambda i: i.name, reverse=True)


# --------------------------------------------------------------------------- #
# 内部
# --------------------------------------------------------------------------- #
def _ensure_basic_info() -> None:
    """老文件或异常文件缺 basic_info 行时补一行，避免界面取不到工程名。"""
    session = orm.session()
    if session.get(BasicInfo, 1) is None:
        session.add(BasicInfo(id=1))
        orm.commit()


def _seed_default_principles(session, spec: NewProjectSpec) -> None:
    """新工程按向导选定的名称建默认围护/地基原则（复刻旧版构造函数的初始状态）。"""
    library = component_library()
    work_widths, groove_bs = default_width_tables()

    enclosure = PcpEnclosure(
        name=spec.enclosure_name or "默认围护原则",
        excvt=spec.enclosure_excvt,
        found_angle=int(spec.enclosure_found_angle),
        con_found=bool(spec.enclosure_con_found),
        order_no=0,
    )
    enclosure.cushions.append(EnclosureCushion(name="中粗砂", h=200.0, order_no=0))
    for key, (elevation, gap, sides) in PRECIPITATION_DEFAULTS.items():
        setattr(enclosure, key, format_precipitation(elevation, gap, sides))
    session.add(enclosure)
    session.flush()
    new_enclosure_work(session, enclosure, library, order_no=0)
    seed_width_tables(session, enclosure, work_widths, groove_bs)

    foundation = PcpFoundation(name=spec.foundation_name or "默认地基处理原则", order_no=0)
    session.add(foundation)
    session.flush()
    attach_foundation_component(session, foundation, library)


# --------------------------------------------------------------------------- #
# 原则结构装配（新建向导与原则编辑器共用）
# --------------------------------------------------------------------------- #
def component_library():
    """构件库（Ei/WSi/Fi，见 services.atlas）。"""
    from app.services.atlas import component_library as _load

    return _load()


def default_width_tables():
    """默认工作面 / 沟槽宽度表（GB 50268-2008，见 services.atlas）。"""
    from app.services.atlas import default_width_tables as _load

    return _load()


def component_from_template(session, library, group: str, name: str, **owner) -> Component:
    """把构件库条目复制成一条 Component（含参数），挂在 owner 外键上。"""
    template = library.template(group, name)
    if template is None:
        names = library.names(group)
        template = library.template(group, names[0]) if names else None
    component = Component(
        name=template.name if template else (name or ""),
        formula=template.describe if template else "",
        **owner,
    )
    if template is not None:
        for key, (display, value) in template.params.items():
            component.params.append(ComponentParam(key=key, value=f"{display}|{value}"))
    session.add(component)
    session.flush()
    return component


def new_enclosure_work(
    session,
    enclosure: PcpEnclosure,
    library,
    *,
    min_depth: float = 0.0,
    level_name: str | None = None,
    waterstop_name: str | None = None,
    order_no: int = 0,
) -> EnclosureWork:
    """给围护原则新增一条做法（旧版 mcPcpEnclosure.Add(new mcEnclosure())）。"""
    ei_names = library.names("Ei")
    ws_names = library.names("WSi")
    level_name = level_name or (ei_names[0] if ei_names else "放坡")
    waterstop_name = waterstop_name or (ws_names[0] if ws_names else "无")
    work = EnclosureWork(
        enclosure_id=enclosure.id,
        min_depth=min_depth,
        cpnt_cat=level_name,
        order_no=order_no,
    )
    session.add(work)
    session.flush()

    level = EnclosureLevel(work_id=work.id, name=level_name, h=-1.0, step_width=1.0, order_no=0)
    session.add(level)
    session.flush()
    component_from_template(session, library, "Ei", level_name, enclosure_level_id=level.id)
    component_from_template(session, library, "WSi", waterstop_name, enclosure_work_id=work.id)
    return work


def seed_width_tables(session, enclosure: PcpEnclosure, work_widths: dict, groove_bs: dict) -> None:
    """把工作面 / 沟槽宽度默认表写进围护原则（旧版 DeepClone(mscInventory.WorkWidth/GrooveB)）。"""
    for kind, table in (("work", work_widths), ("groove_b", groove_bs)):
        for category_index, (category, values) in enumerate(table.items()):
            for dn_index, dn in enumerate(sorted(values)):
                session.add(
                    WorkWidth(
                        enclosure_id=enclosure.id,
                        pipe_type=category,
                        dn=dn,
                        width=values[dn],
                        kind=kind,
                        order_no=category_index * 100 + dn_index,
                    )
                )


def attach_foundation_component(session, foundation: PcpFoundation, library, name: str | None = None) -> Component:
    """给地基原则挂特殊地基构件（旧版 Fcpnti 第一项，默认“无”）。"""
    names = library.names("Fi")
    return component_from_template(
        session, library, "Fi", name or (names[0] if names else "无"), foundation_id=foundation.id
    )
