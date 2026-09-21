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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

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
    EnclosureCushion,
    PcpEnclosure,
    PcpFoundation,
    Segment,
    Unit,
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
    """新建向导收集到的信息。"""

    path: Path
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
    """按向导收集的信息建工程文件并打开。同路径已存在的旧文件会被覆盖。"""
    global _backup_done_for_session

    path = Path(spec.path)
    if path.suffix.lower() != PROJECT_SUFFIX:
        path = path.with_suffix(PROJECT_SUFFIX)
    close_project()
    if path.exists():
        release_lock(path)
        path.unlink()
    acquire_lock(path)
    try:
        orm.create_database(path)
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
        _backup_done_for_session = False
    except Exception:
        orm.close_database()
        release_lock(path)
        raise
    return path


def open_project(path: str | Path) -> Path:
    """打开工程：抢锁 → 校验结构版本 → 绑定会话。"""
    global _backup_done_for_session

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
    _backup_done_for_session = False
    return target


def save() -> Path | None:
    """显式保存：落盘 + 备份一份。"""
    path = orm.database_path()
    if path is None:
        return None
    _commit_and_backup(force_backup=True)
    return path


def save_as(path: str | Path) -> Path:
    """另存为：把当前内容整体复制到新路径，之后继续在新文件上工作。"""
    global _backup_done_for_session

    old_path = orm.database_path()
    target = Path(path)
    if target.suffix.lower() != PROJECT_SUFFIX:
        target = target.with_suffix(PROJECT_SUFFIX)
    if old_path is None:
        raise ProjectIoError("尚未打开工程，无法另存为。")
    if target.resolve() == Path(old_path).resolve():
        return old_path
    if target.exists():
        release_lock(target)
        target.unlink()

    orm.commit()  # 先落盘，保证复制出来的文件是最新的
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old_path, target)
    orm.close_database()
    release_lock(old_path)
    acquire_lock(target)
    try:
        orm.open_database(target)
    except Exception:
        orm.close_database()
        release_lock(target)
        raise
    _backup_done_for_session = False
    return target


def close_project() -> Path | None:
    """关闭工程：落盘 → 关会话 → 释放锁。"""
    global _backup_done_for_session

    path = orm.database_path()
    if path is None:
        return None
    try:
        orm.commit()
    finally:
        orm.close_database()
        release_lock(path)
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
    if force_backup or not _backup_done_for_session:
        create_backup()
        _backup_done_for_session = True


def current_path() -> Path | None:
    return orm.database_path()


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


def next_order_no(model, **filters) -> int:
    """取某张表在给定父行下的下一个 order_no。"""
    if not orm.is_open():
        return 0
    statement = select(func.coalesce(func.max(model.order_no), -1) + 1)
    for column, value in filters.items():
        statement = statement.where(getattr(model, column) == value)
    return int(orm.session().scalar(statement) or 0)


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
    """新工程按向导选定的名称建默认围护/地基原则。

    工作面宽度表、沟槽宽度表来自图集（GB 50268-2008），M3 落地图集后补齐。
    """
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

    foundation = PcpFoundation(name=spec.foundation_name or "默认地基处理原则", order_no=0)
    session.add(foundation)
