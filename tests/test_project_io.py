"""工程文件读写测试（计划 §5、M2 验收标准）。

覆盖：新建 → 录入 → 关闭 → 重开数据完整、双开被拒、锁文件、自动备份、结构版本校验。
所有用例都在 tmp_path 下建工程，不碰用户目录里的任何真实文件。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.version import SCHEMA_VERSION
from app.orm import base as orm
from app.orm.models import BasicInfo, Element, Pipe, Segment, Unit
from app.services import project_io
from app.services.project_io import (
    NewProjectSpec,
    ProjectLockedError,
    ProjectIoError,
    backup_dir,
    lock_path,
)
from app.viewmodels import unit_vm


@pytest.fixture(autouse=True)
def _clean_state():
    """每个用例前后都保证没有打开着的工程。"""
    project_io.close_project()
    yield
    project_io.close_project()


def _make_project(tmp_path: Path, name: str = "测试工程") -> Path:
    spec = NewProjectSpec(
        path=tmp_path / f"{name}.stn2",
        project_name=name,
        project_index="T-001",
        author="测试员",
        segment_names=["第一标段", "第二标段"],
        unit_names=["雨水工程", "污水工程"],
        enclosure_name="默认围护原则",
        foundation_name="默认地基处理原则",
    )
    return project_io.new_project(spec)


# --------------------------------------------------------------------------- #
# 新建 / 打开 / 数据完整
# --------------------------------------------------------------------------- #
def test_new_project_structure(tmp_path: Path) -> None:
    path = _make_project(tmp_path)

    assert path.exists()
    assert project_io.is_open()
    assert project_io.current_path() == path
    assert lock_path(path).exists()

    info = project_io.basic_info()
    assert info is not None
    assert (info.project_name, info.project_index, info.author) == ("测试工程", "T-001", "测试员")
    assert info.atlas_name == "06MS201-1"

    segments = project_io.segments()
    assert [segment.name for segment in segments] == ["第一标段", "第二标段"]
    assert [unit.name for unit in project_io.units(segments[0].id)] == ["雨水工程", "污水工程"]

    assert project_io.enclosure_names() == ["默认围护原则"]
    assert project_io.foundation_names() == ["默认地基处理原则"]

    meta = orm.read_meta()
    assert meta["schema_version"] == str(SCHEMA_VERSION)
    assert meta["app_version"]
    assert meta["created_at"] and meta["updated_at"]


def test_reopen_keeps_everything(tmp_path: Path) -> None:
    path = _make_project(tmp_path)
    unit = project_io.units(project_io.segments()[0].id)[0]

    element = unit_vm.create_element(unit.id, category=1, name="污水管 D600")
    assert element is not None
    unit_vm.update_element(element.id, depth="2.5+0.3", amount="100")
    unit_vm.create_pipe(element.id, mat="HDPE", dn=600, content="1")
    unit_vm.create_param(element.id, key="含钢量", value="35")

    project_io.close_project()
    assert not project_io.is_open()
    assert not lock_path(path).exists()

    project_io.open_project(path)
    rows = unit_vm.element_rows(unit.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.name == "污水管 D600"
    assert row.depth == "2.5+0.3"  # 存字符串原文
    assert row.depth_value == pytest.approx(2.8)  # 运行时求值
    assert row.amount_value == pytest.approx(100.0)
    assert row.unit == "m"
    assert row.pe_name == "默认围护原则"
    assert row.pf_name == "默认地基处理原则"

    pipes = unit_vm.pipe_rows(element.id)
    assert [(pipe.mat, pipe.dn, pipe.content) for pipe in pipes] == [("HDPE", 600, "1")]
    params = unit_vm.param_rows(element.id)
    assert [(param.key, param.value) for param in params] == [("含钢量", "35")]


def test_commit_is_autosave(tmp_path: Path) -> None:
    """每次修改都 commit 落盘：另开连接应能读到。"""
    path = _make_project(tmp_path)
    unit = project_io.units(project_io.segments()[0].id)[0]
    unit_vm.create_element(unit.id, name="落盘检查")

    connection = sqlite3.connect(path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM element").fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_cascade_delete(tmp_path: Path) -> None:
    _make_project(tmp_path)
    segment = project_io.segments()[0]
    unit = project_io.units(segment.id)[0]
    element = unit_vm.create_element(unit.id, name="将被级联删除")
    assert element is not None
    unit_vm.create_pipe(element.id)

    session = orm.session()
    session.delete(session.get(Unit, unit.id))
    project_io.commit()

    session = orm.session()
    assert session.query(Element).count() == 0
    assert session.query(Pipe).count() == 0


# --------------------------------------------------------------------------- #
# 文件锁
# --------------------------------------------------------------------------- #
def test_double_open_rejected(tmp_path: Path) -> None:
    """另一个活着的进程持有锁时拒绝打开（M2 验收标准）。"""
    path = _make_project(tmp_path)
    project_io.close_project()

    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        lock_path(path).write_text(
            json.dumps({"pid": holder.pid, "opened_at": "2026-09-21T10:00:00"}),
            encoding="utf-8",
        )
        with pytest.raises(ProjectLockedError):
            project_io.open_project(path)
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_stale_lock_taken_over(tmp_path: Path) -> None:
    """上次崩溃留下的锁（进程已不存在）应被自动接管。"""
    path = _make_project(tmp_path)
    project_io.close_project()
    lock_path(path).write_text(
        json.dumps({"pid": 999_999_999, "opened_at": "2020-01-01T00:00:00"}),
        encoding="utf-8",
    )

    project_io.open_project(path)
    assert project_io.is_open()
    data = json.loads(lock_path(path).read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()


def test_release_lock_keeps_others_lock(tmp_path: Path) -> None:
    path = _make_project(tmp_path)
    project_io.close_project()
    lock_path(path).write_text(json.dumps({"pid": 999_999_999}), encoding="utf-8")
    project_io.release_lock(path)
    assert lock_path(path).exists()


# --------------------------------------------------------------------------- #
# 备份
# --------------------------------------------------------------------------- #
def test_backup_on_first_change_and_on_save(tmp_path: Path) -> None:
    path = _make_project(tmp_path)
    folder = backup_dir(path)
    unit = project_io.units(project_io.segments()[0].id)[0]

    assert not list(folder.glob("*.stn2"))

    unit_vm.create_element(unit.id, name="第一次修改")  # 本次打开后的首次修改 → 备份 1 份
    first = list(folder.glob("*.stn2"))
    assert len(first) == 1
    assert first[0].name.startswith(f"{path.stem}_")

    unit_vm.create_element(unit.id, name="第二次修改")  # 不再重复备份
    assert len(list(folder.glob("*.stn2"))) == 1

    project_io.save()  # 显式保存 → 再备份一份
    assert len(list(folder.glob("*.stn2"))) == 2


def test_backup_keeps_only_20(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_io, "BACKUP_KEEP", 3)
    path = _make_project(tmp_path)
    folder = backup_dir(path)

    for index in range(5):
        project_io.create_backup()
        # 文件名带秒级时间戳，避免同名覆盖影响计数
        target = sorted(folder.glob("*.stn2"))[-1]
        target.rename(folder / f"{path.stem}_250101_00000{index}{path.suffix}")

    remaining = sorted(folder.glob("*.stn2"))
    assert len(remaining) == 3
    assert [item.name for item in remaining] == [
        f"{path.stem}_250101_000002{path.suffix}",
        f"{path.stem}_250101_000003{path.suffix}",
        f"{path.stem}_250101_000004{path.suffix}",
    ]


def test_backup_content_is_readable_project(tmp_path: Path) -> None:
    path = _make_project(tmp_path)
    unit = project_io.units(project_io.segments()[0].id)[0]
    unit_vm.create_element(unit.id, name="备份内容")
    backup = sorted(backup_dir(path).glob("*.stn2"))[0]

    project_io.close_project()
    project_io.open_project(backup)
    assert project_io.project_name() == "测试工程"
    assert unit_vm.element_rows(unit.id)[0].name == "备份内容"


# --------------------------------------------------------------------------- #
# 另存为 / 结构版本
# --------------------------------------------------------------------------- #
def test_save_as_moves_lock_and_keeps_data(tmp_path: Path) -> None:
    path = _make_project(tmp_path)
    unit = project_io.units(project_io.segments()[0].id)[0]
    unit_vm.create_element(unit.id, name="另存前")

    target = tmp_path / "另存为" / "副本.stn2"
    saved = project_io.save_as(target)

    assert saved == target
    assert target.exists()
    assert path.exists()  # 原文件保留
    assert project_io.current_path() == target
    assert not lock_path(path).exists()
    assert lock_path(target).exists()
    assert unit_vm.element_rows(unit.id)[0].name == "另存前"

    project_io.close_project()
    project_io.open_project(target)
    assert unit_vm.element_rows(unit.id)[0].name == "另存前"


def test_schema_too_new_is_rejected(tmp_path: Path) -> None:
    path = _make_project(tmp_path)
    project_io.close_project()

    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(orm.SchemaTooNewError):
        project_io.open_project(path)
    assert not project_io.is_open()


def test_not_a_project_file_is_rejected(tmp_path: Path) -> None:
    bogus = tmp_path / "随便一个文件.stn2"
    connection = sqlite3.connect(bogus)
    connection.execute("CREATE TABLE other (id INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(orm.NotAProjectFileError):
        project_io.open_project(bogus)
    assert not project_io.is_open()


def test_garbage_file_is_rejected(tmp_path: Path) -> None:
    """把普通文本改名成 .stn2 也要给出明确提示，不能抛底层数据库异常。"""
    bogus = tmp_path / "伪装成工程.txt.stn2"
    bogus.write_text("这不是一个 SQLite 库", encoding="utf-8")

    with pytest.raises(orm.NotAProjectFileError):
        project_io.open_project(bogus)
    assert not project_io.is_open()
    assert not lock_path(bogus).exists()  # 失败的打开要释放锁


def test_open_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ProjectIoError):
        project_io.open_project(tmp_path / "不存在.stn2")


def test_new_project_overwrites_existing(tmp_path: Path) -> None:
    path = _make_project(tmp_path)
    project_io.close_project()
    again = _make_project(tmp_path)
    assert again == path
    assert project_io.segments()[0].name == "第一标段"
    assert orm.session().query(BasicInfo).count() == 1
    assert orm.session().query(Segment).count() == 2


# --------------------------------------------------------------------------- #
# 临时工程（新建不选路径，首次保存时才定位置，与 Quotor 一致）
# --------------------------------------------------------------------------- #
def test_transient_new_project_has_no_path(tmp_path: Path) -> None:
    spec = NewProjectSpec(project_name="临时工程", unit_names=["雨水工程"])
    project_io.new_project(spec)

    assert project_io.is_open()
    assert project_io.is_transient()
    assert project_io.current_path() is None  # 没有正式文件，标题栏/最近列表不能拿到路径
    assert project_io.project_name() == "临时工程"
    # 数据本身完整可用
    assert [u.name for u in project_io.units(project_io.segments()[0].id)] == ["雨水工程"]
    assert project_io.enclosure_names() == ["默认围护原则"]


def test_transient_save_requires_path_first(tmp_path: Path) -> None:
    spec = NewProjectSpec(project_name="临时工程")
    project_io.new_project(spec)

    with pytest.raises(ProjectIoError):
        project_io.save()  # 界面层引导用户走另存为；直接 save 必须报错而不是写丢


def test_transient_first_save_promotes_to_real_file(tmp_path: Path) -> None:
    spec = NewProjectSpec(project_name="首次保存")
    project_io.new_project(spec)
    temp_path = orm.database_path()
    assert temp_path is not None and temp_path.exists()

    target = tmp_path / "首次保存.stn2"
    saved = project_io.save_as(target)

    assert saved == target
    assert target.exists()
    assert not project_io.is_transient()
    assert project_io.current_path() == target
    assert lock_path(target).exists()  # 首次保存后才有文件锁
    assert not temp_path.exists()  # 临时库用完即删
    # 保存后的工程数据完整
    assert project_io.project_name() == "首次保存"


def test_transient_close_discards_temp_database(tmp_path: Path) -> None:
    spec = NewProjectSpec(project_name="关闭即弃")
    project_io.new_project(spec)
    temp_path = orm.database_path()

    project_io.close_project()

    assert not project_io.is_open()
    assert temp_path is not None and not temp_path.exists()  # 临时库不残留
    assert project_io.current_path() is None


def test_transient_switching_to_open_keeps_data(tmp_path: Path) -> None:
    spec = NewProjectSpec(project_name="带数据临时工程", unit_names=["雨水工程"])
    project_io.new_project(spec)
    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, category=1, name="雨水管 D800")
    assert element is not None
    temp_path = orm.database_path()

    target = tmp_path / "带数据临时工程.stn2"
    project_io.save_as(target)
    project_io.close_project()
    project_io.open_project(target)

    units = project_io.units(project_io.segments()[0].id)
    assert units
    assert orm.session().query(Element).filter(Element.unit_id == units[0].id).count() >= 1
    assert temp_path is not None and not temp_path.exists()
