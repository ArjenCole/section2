"""SQLAlchemy 基础：Base、引擎与会话生命周期、meta 表读写。

工程文件 = 单个 SQLite 文件（计划 §5）。业务代码不自己建连接，
统一通过本模块拿会话；一次 `commit()` 就是一次落盘（自动保存）。

会话只有一个、长驻、跑在界面线程上——桌面单用户场景下这样才能让
“改完立刻 commit”的自动保存最简单可靠。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, MetaData, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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
    """不是有效的 .stn2（缺 meta 表）。"""


class SchemaTooNewError(ProjectFileError):
    """文件由更高版本的程序创建，拒绝打开（计划 §5）。"""


class NoProjectOpenError(ProjectFileError):
    """尚未打开任何工程。"""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_path: Path | None = None
_session: Session | None = None

def _migrate_v1_add_element_source(engine: Engine) -> None:
    """v1 → v2：element 表加 source 列（复刻旧版主表格“来源”列）。"""
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE element ADD COLUMN source VARCHAR(200) DEFAULT ''")
        )


#: 结构迁移入口（计划 §5）。键为源版本号，值为“从该版本迁到 +1 版本”的函数。
_MIGRATIONS: dict[int, "callable"] = {
    1: _migrate_v1_add_element_source,
}


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
    global _engine, _session_factory, _path, _session
    _engine = engine
    _path = Path(path)
    _session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    _session = _session_factory()


def create_database(path: str | Path) -> Engine:
    """新建 .stn2：建库 + 建表 + 写 meta。"""
    from app.orm import models  # noqa: F401  建表前先注册全部表

    close_database()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
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
    return engine


def open_database(path: str | Path) -> Engine:
    """打开已有 .stn2：校验结构版本 → 迁移 → 补建缺失的表。"""
    from app.orm import models  # noqa: F401

    close_database()
    target = Path(path)
    if not target.exists():
        raise ProjectFileError(f"工程文件不存在：{target}")
    engine = _make_engine(target)
    try:
        version = _read_schema_version(engine)
        if version > SCHEMA_VERSION:
            raise SchemaTooNewError(
                f"工程文件结构版本为 {version}，本程序仅支持到 {SCHEMA_VERSION}；"
                "文件由更高版本的 Section 创建，请升级程序后再打开。"
            )
        if version < SCHEMA_VERSION:
            _migrate(engine, version)
        Base.metadata.create_all(engine)
    except Exception:
        engine.dispose()
        raise
    _bind(engine, target)
    return engine


def _read_schema_version(engine: Engine) -> int:
    """直接读 meta 表，此时 ORM 还没绑定，用原生 SQL。"""
    try:
        tables = inspect(engine).get_table_names()
        if "meta" not in tables:
            raise NotAProjectFileError("不是有效的 .stn2 工程文件（缺少 meta 表）。")
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT value FROM meta WHERE key = 'schema_version'")
            ).first()
    except NotAProjectFileError:
        raise
    except Exception as error:  # 比如把普通文本文件改名成 .stn2
        raise NotAProjectFileError(f"不是有效的 .stn2 工程文件：{error}") from error
    if row is None:
        raise NotAProjectFileError("工程文件缺少 schema_version 记录。")
    try:
        return int(row[0])
    except (TypeError, ValueError) as error:
        raise NotAProjectFileError("schema_version 不是整数。") from error


def _migrate(engine: Engine, from_version: int) -> None:
    """按版本号顺序执行迁移函数，逐个 +1 直到当前版本。"""
    version = from_version
    while version < SCHEMA_VERSION:
        migrate = _MIGRATIONS.get(version)
        if migrate is None:
            raise ProjectFileError(
                f"缺少 {version} → {version + 1} 的结构迁移函数，无法打开该工程文件。"
            )
        migrate(engine)
        version += 1
        _write_meta_raw(engine, "schema_version", str(version))


def _write_meta_raw(engine: Engine, key: str, value: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO meta (key, value) VALUES (:k, :v) "
                 "ON CONFLICT(key) DO UPDATE SET value = :v"),
            {"k": key, "v": value},
        )


def close_database() -> None:
    """关闭会话、释放引擎；调用后工程处于“未打开”状态。"""
    global _engine, _session_factory, _path, _session
    if _session is not None:
        try:
            _session.rollback()
        finally:
            _session.close()
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _session = None
    _path = None


def database_path() -> Path | None:
    """当前工程文件路径；未打开时为 None。"""
    return _path


def is_open() -> bool:
    return _engine is not None


def session() -> Session:
    """当前工程的共享会话。"""
    if _session is None:
        raise NoProjectOpenError("尚未打开工程。")
    return _session


def new_session() -> Session:
    """独立会话（测试、后台任务用），调用方负责关闭。"""
    if _session_factory is None:
        raise NoProjectOpenError("尚未打开工程。")
    return _session_factory()


def commit() -> None:
    """落盘：commit + 刷新 meta.updated_at（“保存”与自动保存都走这里）。"""
    if _session is None:
        return
    _session.commit()
    set_meta("updated_at", datetime.now().isoformat(timespec="seconds"), commit_now=True)


def get_meta(key: str, default: str = "") -> str:
    """读取 meta 表某项。"""
    return get_meta_with(session(), key, default)


def get_meta_with(target: Session, key: str, default: str = "") -> str:
    from app.orm import models

    row = target.get(models.Meta, key)
    return row.value if row is not None else default


def set_meta(key: str, value: str, *, commit_now: bool = False) -> None:
    """写 meta 表某项。"""
    from app.orm import models

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
    from app.orm import models

    return {row.key: row.value for row in session().query(models.Meta).all()}
