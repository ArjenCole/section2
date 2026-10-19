"""SQLAlchemy 基础：Base、引擎与会话生命周期、meta 表读写。

工程文件 = 单个 SQLite 文件。业务代码不自己建连接，
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
    """文件由更高版本的程序创建，拒绝打开。"""


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


def _migrate_v2_add_multi_principle(engine: Engine) -> None:
    """v2 → v3：多原则引用 + 附属构筑物。

    * element 表加 main_pe_name 列（旧版 mainPEname）；
    * 建 element_principle 表，并把已有的 pe_name / pf_name 单原则引用
      补成 ratio=1 的引用行（旧版 showPEname setter 的等价数据）。
    """
    from sqlalchemy import inspect as sqla_inspect

    from app.core.models.models import ElementPrinciple

    existing_columns = {column["name"] for column in sqla_inspect(engine).get_columns("element")}
    if "main_pe_name" not in existing_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE element ADD COLUMN main_pe_name VARCHAR(200) DEFAULT ''")
            )
    ElementPrinciple.__table__.create(engine, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO element_principle (element_id, kind, name, ratio, order_no) "
                "SELECT id, 'pe', pe_name, 1, 0 FROM element "
                "WHERE pe_name IS NOT NULL AND pe_name != '' "
                "AND id NOT IN (SELECT element_id FROM element_principle WHERE kind = 'pe')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO element_principle (element_id, kind, name, ratio, order_no) "
                "SELECT id, 'pf', pf_name, 1, 0 FROM element "
                "WHERE pf_name IS NOT NULL AND pf_name != '' "
                "AND id NOT IN (SELECT element_id FROM element_principle WHERE kind = 'pf')"
            )
        )
        connection.execute(
            text(
                "UPDATE element SET main_pe_name = pe_name "
                "WHERE (main_pe_name IS NULL OR main_pe_name = '') "
                "AND pe_name IS NOT NULL AND pe_name != ''"
            )
        )


def _migrate_v3_split_precipitation_width(engine: Engine) -> None:
    """v3 → v4：降水 / 面宽从围护原则独立成原则。

    * element 表加 pp_name / pw_name 列（旧版降水、面宽随围护原则，v4 起单独引用）；
    * 建 principle_precipitation / principle_width / principle_width_item 表，
      把每条围护原则的降水参数与宽度表迁成同名独立原则；
    * 元素引用：pp/pw 名与原围护名一致（多围护原则的行落到第一条降水/面宽原则）；
    * 旧 work_width 表留在库里不再使用（SQLite 不便删表，模型已不映射）。
    """
    from sqlalchemy import inspect as sqla_inspect

    from app.core.models.models import PcpPrecipitation, PcpWidth, WidthItem

    inspection = sqla_inspect(engine)
    element_columns = {column["name"] for column in inspection.get_columns("element")}
    enclosure_columns = {column["name"] for column in inspection.get_columns("principle_enclosure")}
    statements = []
    if "pp_name" not in element_columns:
        statements.append("ALTER TABLE element ADD COLUMN pp_name VARCHAR(200) DEFAULT ''")
    if "pw_name" not in element_columns:
        statements.append("ALTER TABLE element ADD COLUMN pw_name VARCHAR(200) DEFAULT ''")
    PcpPrecipitation.__table__.create(engine, checkfirst=True)
    PcpWidth.__table__.create(engine, checkfirst=True)
    WidthItem.__table__.create(engine, checkfirst=True)
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        # 正常 v3 库的 principle_enclosure 带降水/宽度列；按新结构降版构造的
        # 测试文件可能没有，此时新表已由 create_all 建好，只补元素引用列
        if "wet_soil" in enclosure_columns:
            connection.execute(
                text(
                    "INSERT INTO principle_precipitation (name, wet_soil, light_well, jet_well, "
                    "big_well, deep_well, order_no) "
                    "SELECT name, wet_soil, light_well, jet_well, big_well, deep_well, order_no "
                    "FROM principle_enclosure"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO principle_width (name, groove_width, order_no) "
                    "SELECT name, groove_width, order_no FROM principle_enclosure"
                )
            )
            if "work_width" in inspection.get_table_names():
                # 旧 work_width 行按所属围护原则名挂到同名面宽原则
                connection.execute(
                    text(
                        "INSERT INTO principle_width_item (width_id, pipe_type, dn, width, kind, order_no) "
                        "SELECT pw.id, w.pipe_type, w.dn, w.width, w.kind, w.order_no "
                        "FROM work_width w JOIN principle_enclosure pe ON pe.id = w.enclosure_id "
                        "JOIN principle_width pw ON pw.name = pe.name"
                    )
                )
        connection.execute(
            text(
                "UPDATE element SET pp_name = CASE "
                "WHEN pe_name IN (SELECT name FROM principle_precipitation) THEN pe_name "
                "ELSE COALESCE((SELECT name FROM principle_precipitation "
                "ORDER BY order_no, id LIMIT 1), '') END"
            )
        )
        connection.execute(
            text(
                "UPDATE element SET pw_name = CASE "
                "WHEN pe_name IN (SELECT name FROM principle_width) THEN pe_name "
                "ELSE COALESCE((SELECT name FROM principle_width "
                "ORDER BY order_no, id LIMIT 1), '') END"
            )
        )


def _migrate_v4_param_naming_quantities(engine: Engine) -> None:
    """v4 → v5：构件参数拆“参数名 / 单位”，附属构筑物工程量独立成表。

    * pipe 表加 t 列（管道壁厚 mm 用户值；空 = 按图集自动）；
    * element_param 表加 unit 列，key 只存参数名（旧键尾部“ 单位”拆出）；
    * 建 element_quantity 表：附属构筑物（category=7）“类别|项目|单位”三段参数
      迁成工程量行并删除原参数行；
    * 附属构筑物的以“-”为前缀的旧键去掉前缀（-名称/-单位/井筒…）；
    * 直埋 / 包封 / 箱涵 / 顶管 / 牵引 / 管廊（category 1~6）构件补
      工作面加宽 / 垫层厚 / 基础厚 三行参数（空值 = 自动按图集）。
    """
    from sqlalchemy import inspect as sqla_inspect

    from app.core.models.models import ElementQuantity
    from app.core.param_naming import ATLAS_PARAM_NAMES, split_param_key

    inspection = sqla_inspect(engine)
    statements: list[str] = []
    param_columns = {column["name"] for column in inspection.get_columns("element_param")}
    if "unit" not in param_columns:
        statements.append("ALTER TABLE element_param ADD COLUMN unit VARCHAR(50) DEFAULT ''")
    pipe_columns = {column["name"] for column in inspection.get_columns("pipe")}
    if "t" not in pipe_columns:
        statements.append("ALTER TABLE pipe ADD COLUMN t FLOAT")
    ElementQuantity.__table__.create(engine, checkfirst=True)

    atlas_names = {name for name, _unit in ATLAS_PARAM_NAMES}
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

        # 解析每行旧参数：按类别决定拆分 / 迁移动作
        rows = connection.execute(
            text(
                "SELECT p.id, p.element_id, p.key, p.value, e.category FROM element_param p "
                "LEFT JOIN element e ON e.id = p.element_id"
            )
        ).fetchall()
        renames: dict[int, tuple[str, str]] = {}
        drops: list[int] = []
        quantity_rows: list[dict[str, object]] = []
        for (param_id, element_id, key, value, category) in rows:
            key = str(key or "")
            if int(category or 0) == 7 and "|" in key:  # 三段工程量键 → element_quantity
                segments = key.split("|", 2)
                quantity_rows.append(
                    {
                        "element_id": int(element_id or 0),
                        "category": segments[0],
                        "item": segments[1],
                        "unit": segments[2] if len(segments) > 2 else "",
                        "value": str(value or ""),
                        "order_no": len(quantity_rows),
                    }
                )
                drops.append(param_id)
                continue
            name = key
            if int(category or 0) == 7 and name.startswith("-"):
                name = name.lstrip("-")  # 构筑物 -前缀键在新版里去掉（含 -名称/-单位）
            name, unit = split_param_key(name)
            renames[param_id] = (name, unit)

        for param_id, (name, unit) in renames.items():
            connection.execute(
                text("UPDATE element_param SET key = :name, unit = :unit WHERE id = :id"),
                {"name": name, "unit": unit, "id": param_id},
            )
        for param_id in drops:
            connection.execute(
                text("DELETE FROM element_param WHERE id = :id"), {"id": param_id}
            )
        for row in quantity_rows:
            connection.execute(
                text(
                    "INSERT INTO element_quantity "
                    "(element_id, category, item, unit, value, order_no) "
                    "VALUES (:element_id, :category, :item, :unit, :value, :order_no)"
                ),
                row,
            )

        # 混凝土类构件补三行图集覆盖参数（category 1~6；名称 / 单位锁定，空值 = 自动）
        for element_id, in connection.execute(
            text("SELECT id FROM element WHERE category BETWEEN 1 AND 6")
        ).fetchall():
            keys = {
                row[0]
                for row in connection.execute(
                    text("SELECT key FROM element_param WHERE element_id = :e"),
                    {"e": element_id},
                ).fetchall()
            }
            missing = [
                (name, unit) for name, unit in ATLAS_PARAM_NAMES if name not in keys
            ]
            if not missing or keys & atlas_names:
                continue  # 三行一起补，已删过其一的老库视为已迁移
            for name, unit in missing:
                connection.execute(
                    text(
                        "INSERT INTO element_param (element_id, key, unit, value) "
                        "VALUES (:e, :name, :unit, '')"
                    ),
                    {"e": element_id, "name": name, "unit": unit},
                )


def _reconcile_atlas_param_rows(engine: Engine) -> None:
    """按 param_naming.ATLAS_PARAM_CATEGORIES 收敛三行图集参数（v6 / v7 共用）。

    * 类别上不显示的行删掉（包封 / 箱涵 / 管廊的基础厚、顶管 / 牵引管的全部
      三行）——这些行不参与计算（基础厚恒为 0），留着只会误导；
    * 该类别的行缺失时补空值行（空 = 自动按图集 / 软件约定），与新建 /
      构件库插入的条目保持一致。
    """
    from app.core.param_naming import ATLAS_PARAM_CATEGORIES, ATLAS_PARAM_NAMES

    with engine.begin() as connection:
        for name, unit in ATLAS_PARAM_NAMES:
            allowed = sorted(
                category
                for category, names in ATLAS_PARAM_CATEGORIES.items()
                if name in names
            )
            if allowed:
                marks = ", ".join(f":c{index}" for index in range(len(allowed)))
                scope = f"element_id IN (SELECT id FROM element WHERE category NOT IN ({marks}))"
                scope_params = {f"c{index}": value for index, value in enumerate(allowed)}
            else:  # 没有任何类别显示这一行：全部删除
                scope = "1 = 1"
                scope_params = {}
            connection.execute(
                text(
                    f"DELETE FROM element_param WHERE key = :name AND unit = :unit AND {scope}"
                ),
                {"name": name, "unit": unit, **scope_params},
            )
        for category, names in sorted(ATLAS_PARAM_CATEGORIES.items()):
            element_ids = [
                row[0]
                for row in connection.execute(
                    text("SELECT id FROM element WHERE category = :category"),
                    {"category": category},
                ).fetchall()
            ]
            for element_id in element_ids:
                keys = {
                    (row[0], row[1])
                    for row in connection.execute(
                        text("SELECT key, unit FROM element_param WHERE element_id = :element"),
                        {"element": element_id},
                    ).fetchall()
                }
                for name, unit in ATLAS_PARAM_NAMES:
                    if name not in names or (name, unit) in keys:
                        continue
                    connection.execute(
                        text(
                            "INSERT INTO element_param (element_id, key, unit, value) "
                            "VALUES (:element, :name, :unit, '')"
                        ),
                        {"element": element_id, "name": name, "unit": unit},
                    )


def _migrate_v5_scope_atlas_params(engine: Engine) -> None:
    """v5 → v6：三行图集参数按构件类别收敛。

    v5 给全部管道类别（category 1~6）都补了这三行，并可能预填了图集值。
    v6 起按 :data:`app.core.param_naming.ATLAS_PARAM_CATEGORIES` 决定显示：
    直埋管道三行都显示（默认按图集、用户可改）；包封埋管 / 箱涵 / 管廊的
    基础厚恒为 0（不显示、不可改），只显示工作面加宽 / 垫层厚；顶管 / 牵引管
    只算管材，三行都不显示。不显示的行删除（含残留值），缺失的行补空值行。
    """
    _reconcile_atlas_param_rows(engine)


def _migrate_v6_scope_atlas_params(engine: Engine) -> None:
    """v6 → v7：按类别再收敛一次三行图集参数。

    v6 的早期实现把这三行只留在包封埋管上（直埋 / 箱涵 / 管廊上的行被删掉了），
    与显示规则不符；已经迁到那个版本的文件在这里按新规则补回空值行
    （直埋三行、包封 / 箱涵 / 管廊的工作面加宽与垫层厚）。
    """
    _reconcile_atlas_param_rows(engine)


#: 结构迁移入口。键为源版本号，值为“从该版本迁到 +1 版本”的函数。
_MIGRATIONS: dict[int, "callable"] = {
    1: _migrate_v1_add_element_source,
    2: _migrate_v2_add_multi_principle,
    3: _migrate_v3_split_precipitation_width,
    4: _migrate_v4_param_naming_quantities,
    5: _migrate_v5_scope_atlas_params,
    6: _migrate_v6_scope_atlas_params,
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
    from app.core.models import models  # noqa: F401  建表前先注册全部表

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
    from app.core.models import models  # noqa: F401

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
    from app.core.models import models

    row = target.get(models.Meta, key)
    return row.value if row is not None else default


def set_meta(key: str, value: str, *, commit_now: bool = False) -> None:
    """写 meta 表某项。"""
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
