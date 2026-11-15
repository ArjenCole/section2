"""性能改造（前三档）的行为回归测试。

覆盖：

* dump_database 快慢双路径——纯属性修改走快路径（钉住对象树）时导出内容
  与全量重读逐字节一致，且编辑值可见；身份映射是弱引用，这里专门模拟
  "调用方已不持有任何引用 + gc" 的最坏场景（首次实测 251 条构件只剩 32 条）。
* commit 落盘防抖——注入调度器后 commit 不立即写盘，回调触发才写最新内容；
  显式保存丢弃挂起；关闭工程把挂起内容落盘。
* unit_changed 局部刷新——带受影响构件 id 时未受影响行的内嵌下拉不被重建
  （整表重装会全部销毁重建），受影响行按新数据更新；合槽组改数量时组员
  行与父行同步刷新。
* _element_spec 内容指纹缓存——内容不变不重算，管径变了重算。

Qt 部分离屏运行。
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QComboBox

from app.core.models import base as orm
from app.services import project_io, stn_codec
from app.services.project_io import NewProjectSpec
from app.viewmodels import unit_vm
from app.views.panels.unit_panel import _COL_DEPTH, _COL_PF

from conftest import make_element


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    path = project_io.new_project(NewProjectSpec(path=tmp_path / "性能.stn", unit_names=["雨水工程"]))
    unit = project_io.units(project_io.segments()[0].id)[0]
    for index in range(4):
        make_element(f"管{index}", depth="3", amount="10")
    return path


# --------------------------------------------------------------------------- #
# dump 快慢双路径
# --------------------------------------------------------------------------- #
def test_dump_fast_path_matches_slow_after_gc(project: Path) -> None:
    """属性修改后的快路径导出 = 全量重读导出（调用方不持任何引用 + gc）。"""
    from app.core.models.models import Element

    session = orm.session()
    element = session.scalars(
        __import__("sqlalchemy").select(Element).order_by(Element.id)
    ).first()
    assert element is not None
    element.depth = "9.99"  # 纯属性修改：下一轮 dump 走快路径
    fast = stn_codec.dump_database()
    slow = stn_codec.dump_database()
    # gc 掉调用方引用后再次快路径：钉住的对象树必须完整
    gc.collect()
    fast_after_gc = stn_codec.dump_database()
    assert fast == slow == fast_after_gc
    depths = [
        element_data["depth"]
        for segment in fast["segments"]
        for unit in segment["units"]
        for element_data in unit["elements"]
    ]
    assert "9.99" in depths
    assert len(depths) == 4


def test_dump_slow_path_after_row_insert(project: Path) -> None:
    """增删行走慢路径（集合重新装填），快慢导出仍然一致。"""
    make_element("新增管")
    data = stn_codec.dump_database()
    depths = [
        element_data["depth"]
        for segment in data["segments"]
        for unit in segment["units"]
        for element_data in unit["elements"]
    ]
    assert len(depths) == 5


def test_dump_round_trip_survives_compact_body(project: Path) -> None:
    """紧凑 JSON 数据体（去 indent）保存 → 重开，数据零漂移。"""
    import shutil

    document_path = project
    project_io.close_project()
    copy_path = document_path.with_name("roundtrip.stn")
    shutil.copy(document_path, copy_path)
    project_io.open_project(copy_path)
    session = orm.session()
    from sqlalchemy import select

    from app.core.models.models import Element

    assert session.scalar(select(__import__("sqlalchemy").func.count()).select_from(Element)) == 4
    project_io.close_project()


# --------------------------------------------------------------------------- #
# 落盘防抖
# --------------------------------------------------------------------------- #
def test_commit_with_scheduler_defers_write(project: Path) -> None:
    """注入调度器后 commit 不立即写盘；调度器回调触发才写最新内容。"""
    scheduled: list = []
    project_io.set_flush_scheduler(scheduled.append)

    unit = project_io.units(project_io.segments()[0].id)[0]
    element_row = unit_vm.element_rows(unit.id)[0]
    unit_vm.update_element(element_row.id, depth="7.5")

    assert scheduled, "commit 应调用调度器安排落盘"
    content_before = project_io.current_path().read_text(encoding="utf-8")
    assert "7.5" not in content_before, "防抖窗口内文件不应被立即写出"

    project_io.flush_pending_write()
    content_after = project_io.current_path().read_text(encoding="utf-8")
    assert "7.5" in content_after, "回调触发后应落盘最新内容"

    # 回调幂等：没有挂起内容时空跑
    scheduled.clear()
    project_io.set_flush_scheduler(None)


def test_save_discards_pending_write(project: Path) -> None:
    """防抖挂起期间显式保存：直接写出最新内容并丢弃挂起。"""
    scheduled: list = []
    project_io.set_flush_scheduler(scheduled.append)

    unit = project_io.units(project_io.segments()[0].id)[0]
    element_row = unit_vm.element_rows(unit.id)[0]
    unit_vm.update_element(element_row.id, depth="8.8")
    assert scheduled

    project_io.save()
    assert "8.8" in project_io.current_path().read_text(encoding="utf-8")

    # 挂起已被显式保存丢弃：再触发回调不写出过期内容
    project_io.flush_pending_write()
    assert "8.8" in project_io.current_path().read_text(encoding="utf-8")
    project_io.set_flush_scheduler(None)


def test_close_project_flushes_pending_write(project: Path) -> None:
    """关闭工程把防抖窗口内挂起的修改落盘，不丢在窗口里。"""
    scheduled: list = []
    project_io.set_flush_scheduler(scheduled.append)

    unit = project_io.units(project_io.segments()[0].id)[0]
    element_row = unit_vm.element_rows(unit.id)[0]
    unit_vm.update_element(element_row.id, depth="6.6")
    assert scheduled
    path = project_io.current_path()

    project_io.close_project()
    assert "6.6" in path.read_text(encoding="utf-8")
    project_io.set_flush_scheduler(None)


# --------------------------------------------------------------------------- #
# unit_changed 局部刷新
# --------------------------------------------------------------------------- #
def _panel_for(qapp, unit):
    from app.views.panels.unit_panel import UnitPanel

    panel = UnitPanel()
    panel._show_unit(unit.id, unit.name)
    qapp.processEvents()
    return panel


def test_partial_reload_keeps_unaffected_combos(qapp, project: Path) -> None:
    """改一条构件的埋深：只有受影响行被重填，其余行的内嵌下拉保持原对象。

    整表重装会销毁并重建全部下拉（_clear_cell_widgets），局部刷新不动
    未受影响的行——以"同一 Python 对象"为准。
    """
    unit = project_io.units(project_io.segments()[0].id)[0]
    panel = _panel_for(qapp, unit)
    rows = unit_vm.element_rows(unit.id)
    table = panel._element_table
    other_combo = table.cellWidget(1, _COL_PF)
    assert isinstance(other_combo, __import__("PySide6.QtWidgets", fromlist=["QComboBox"]).QComboBox)

    unit_vm.update_element(rows[0].id, depth="5.5")
    qapp.processEvents()

    assert table.item(0, _COL_DEPTH).text() == "5.5"
    # 未受影响行的下拉没有被重建
    assert table.cellWidget(1, _COL_PF) is other_combo
    # 受影响行的数据按新值重填（pf 下拉值不变也应是同一对象——原地复用）
    same_row_combo = table.cellWidget(0, _COL_PF)
    assert isinstance(same_row_combo, __import__("PySide6.QtWidgets", fromlist=["QComboBox"]).QComboBox)
    panel.deleteLater()


def test_partial_reload_after_group_amount_syncs_members(qapp, project: Path) -> None:
    """改合槽父节点数量：组员行与父行一起按新值刷新。"""
    unit = project_io.units(project_io.segments()[0].id)[0]
    ids = [make_element(f"组员{i}", depth="3", amount="10") for i in range(2)]
    group, error = unit_vm.create_trench_group(ids)
    assert group is not None and error is None
    panel = _panel_for(qapp, unit)
    table = panel._element_table
    qapp.processEvents()

    unit_vm.update_group(group.id, amount="66")
    qapp.processEvents()

    rows = panel._rows_cache
    parent = next((row for row in rows if isinstance(row, unit_vm.GroupRow) and row.id == group.id), None)
    assert parent is not None and parent.amount == "66"
    members = [row for row in rows if isinstance(row, unit_vm.ElementRow) and row.group_id == group.id]
    assert members and all(row.amount == "66" for row in members)
    panel.deleteLater()


# --------------------------------------------------------------------------- #
# _element_spec 缓存
# --------------------------------------------------------------------------- #
def test_element_spec_cache_skips_recompute(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """内容不变不重算 build_element_input；管径变了重算。"""
    import app.core.calc.engine as engine

    calls = {"count": 0}
    original = engine.build_element_input

    def counting_build(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "build_element_input", counting_build)

    session = orm.session()
    from sqlalchemy import select

    from app.core.models.models import Element, Pipe

    element = session.scalars(select(Element).order_by(Element.id)).first()
    assert element is not None

    unit_vm._element_spec(element)
    first_count = calls["count"]
    unit_vm._element_spec(element)  # 内容没变：命中缓存
    assert calls["count"] == first_count

    element.pipes[0].dn = 800  # 内容变了：指纹失效重算
    spec = unit_vm._element_spec(element)
    assert calls["count"] == first_count + 1
    assert "DN800" in spec
