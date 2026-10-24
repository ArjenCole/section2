"""SQLAlchemy 基础：Base、引擎与会话生命周期、meta 表读写。

工程文件 = `.stn`（1.0 风格 XML 头 + JSON 数据体，见 services/stn_format），
而 SQLAlchemy 工作库是**临时目录里的 SQLite 文件**：打开工程时由
JSON 重建、关闭时删除，业务代码不接触它也不自己建连接，
统一通过本模块拿会话；一次 `commit()` 就是一次落盘（自动保存），
`.stn` 文件的写出由 services.project_io 负责。

会话只有一个、长驻、跑在界面线程上——桌面单用户场景下这样才能让
“改完立刻 commit”的自动保存最简单可靠。界面启动时由
:func:`app.core.main_thread.mark_main_thread` 标记主线程；此后
:func:`session` / :func:`commit` / 工程生命周期函数在 worker 线程调用会直接报错，
AI/MCP 工具统一经 ``execute_on_main`` 投递回主线程执行。
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, MetaData, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.main_thread import ensure_main_thread
from app.core.version import APP_VERSION, SCHEMA_VERSION

#: 统一的约束命名，方便以后在 SQLite 上做结构迁移
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class ProjectFileError(RuntimeError):
    """工程文件相关错误基类。"""


class NotAProjectFileError(ProjectFileError):
    """不是有效的 .stn 工程文件（头/数据体无法解析）。"""


class SchemaTooNewError(ProjectFileError):
    """文件由更高版本的程序创建，拒绝打开。"""


class NoProjectOpenError(ProjectFileError):
    """尚未打开任何工程。"""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_path: Path | None = None
_session: Session | None = None


def create_working_database() -> Path:
    """在系统临时目录新建工作库（SQLite）：建库 + 建表 + 写 meta 并绑定会话。

    工作库是每次打开工程的临时载体，真正的工程文件（.stn）由
    services.project_io / stn_format 负责。返回工作库路径。
    """
    ensure_main_thread("新建工程数据库")
    from app.core.models import models  # noqa: F401  建表前先注册全部表

    close_database()
    handle, temp_name = tempfile.mkstemp(prefix="section2_work_", suffix=".sqlite3")
    os.close(handle)
    target = Path(temp_name)
    engine = _make_engine(target)
    Base.metadata.create_all(engine)
    _bind(engine, target)
    with engine.begin() as connection:
        now = datetime.now().isoformat(timespec="seconds")
        connection.execute(
            models.Meta.__table__.insert(),
            [
                {"key": "schema_version", "value": str(SCHEMA_VERSION)},
                {"key": "app_version", "value": APP_VERSION},
                {"key": "created_at", "value": now},
                {"key": "updated_at", "value": now},
            ],
        )
    return target


# --------------------------------------------------------------------------- #
# 内部
# --------------------------------------------------------------------------- #
def _make_engine(path: Path) -> Engine:
    engine = create_engine(
        f"sqlite:///{Path(path).as_posix()}",
        echo=False,
        future=True,
        # 界面线程之外的短任务（如备份、AI 工具）也要能读，因此放开线程检查
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):  # pragma: no cover - 驱动回调
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")  # 让 ondelete=CASCADE 真正生效
        cursor.close()

    return engine


def _bind(engine: Engine, path: Path) -> None:
    ensure_main_thread("绑定工程数据库")
    global _engine, _session_factory, _path, _session
    _engine = engine
    _path = Path(path)
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    _session = _session_factory()


def close_database() -> None:
    """关闭会话、释放引擎并删除临时工作库；调用后工程处于“未打开”状态。"""
    ensure_main_thread("关闭工程数据库")
    global _engine, _session_factory, _path, _session
    if _session is not None:
        try:
            _session.rollback()
        finally:
            _session.close()
    if _engine is not None:
        _engine.dispose()
    working = _path
    _engine = None
    _session_factory = None
    _session = None
    _path = None
    if working is not None:
        try:
            working.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - 临时目录偶发占用，残留文件无害
            pass


def working_path() -> Path | None:
    """当前临时工作库路径（诊断/测试用）；未打开时为 None。"""
    return _path


def is_open() -> bool:
    return _engine is not None


def session() -> Session:
    """当前工程的共享会话（只能在界面主线程使用）。"""
    ensure_main_thread("访问工程数据库")
    if _session is None:
        raise NoProjectOpenError("尚未打开工程。")
    return _session


def commit() -> None:
    """落盘：commit + 刷新 meta.updated_at（“保存”与自动保存都走这里）。"""
    ensure_main_thread("保存工程数据")
    if _session is None:
        return
    _session.commit()
    set_meta("updated_at", datetime.now().isoformat(timespec="seconds"), commit_now=True)


def get_meta(key: str, default: str = "") -> str:
    """读取 meta 表某项。"""
    return get_meta_with(session(), key, default)


def get_meta_with(target: Session, key: str, default: str = "") -> str:
    from app.core.models import models

    row = target.get(models.Meta, key)
    return row.value if row is not None else default


def set_meta(key: str, value: str, *, commit_now: bool = False) -> None:
    """写 meta 表某项。"""
    ensure_main_thread("写入工程元数据")
    from app.core.models import models

    if _session is None:
        return
    row = _session.get(models.Meta, key)
    if row is None:
        _session.add(models.Meta(key=key, value=value))
    else:
        row.value = value
    if commit_now:
        _session.commit()


def read_meta() -> dict[str, str]:
    """整表读出（关于对话框、诊断用）。"""
    from app.core.models import models

    return {row.key: row.value for row in session().query(models.Meta).all()}
