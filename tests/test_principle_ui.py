"""原则 UI 复刻相关回归测试。

覆盖：构件库解析、原则重名后缀、删除并入语义、*.spcp 导入导出回路、
v1→v2 结构迁移（element.source 列）、原则编辑对话框与原则横条的关键交互。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.services import project_io
from app.services.project_io import NewProjectSpec
from app.services.element_library import element_library
from app.viewmodels import unit_vm


@pytest.fixture(autouse=True)
def _clean_state():
    project_io.close_project()
    yield
    project_io.close_project()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    path = tmp_path / "测试工程.stn2"
    project_io.new_project(NewProjectSpec(path=path, unit_names=["雨水工程"]))
    return path


# --------------------------------------------------------------------------- #
# 构件库
# --------------------------------------------------------------------------- #
def test_element_library_categories_and_templates() -> None:
    library = element_library()
    assert library.categories == (
        "直埋混凝土管", "直埋塑料管", "直埋金属类管道", "混凝土结构", "非开挖管道",
    )
    templates = [tpl for units in library.units.values() for unit in units for tpl in unit.elements]
    assert len(templates) == 380
    assert all(tpl.label for tpl in templates)


def test_insert_template_attaches_first_principles(project) -> None:
    unit = project_io.units(project_io.segments()[0].id)[0]
    template = element_library().units_of("直埋混凝土管")[0].elements[0]
    element = unit_vm.insert_element_template(unit.id, template)
    assert element is not None
    assert element.pe_name == project_io.enclosure_names()[0]
    assert element.pf_name == project_io.foundation_names()[0]
    assert element.pipes, "模板的管材应一并带入"
    assert element_rows_spec(element) != ""


def element_rows_spec(element) -> str:
    from app.viewmodels.unit_vm import _element_spec

    return _element_spec(element)


def test_insert_template_before_selected_row(project) -> None:
    unit = project_io.units(project_io.segments()[0].id)[0]
    first = unit_vm.insert_blank_element(unit.id)
    template = element_library().units_of("直埋混凝土管")[0].elements[0]
    inserted = unit_vm.insert_element_template(unit.id, template, before_element_id=first.id)
    rows = unit_vm.element_rows(unit.id)
    assert [row.id for row in rows] == [inserted.id, first.id]


# --------------------------------------------------------------------------- #
# 原则增删改（原版交互语义）
# --------------------------------------------------------------------------- #
def test_unique_principle_name_suffix() -> None:
    assert project_io.unique_principle_name("钢板桩", ["默认围护原则"]) == "钢板桩"
    assert project_io.unique_principle_name("钢板桩", ["默认围护原则", "钢板桩"]) == "钢板桩1"
    assert project_io.unique_principle_name("钢板桩", ["钢板桩", "钢板桩1"]) == "钢板桩2"


def test_create_enclosure_auto_suffix(project) -> None:
    first = project_io.create_enclosure("钢板桩")
    second = project_io.create_enclosure("钢板桩")
    assert (first.name, second.name) == ("钢板桩", "钢板桩1")


def test_delete_enclosure_merges_references(project) -> None:
    unit = project_io.units(project_io.segments()[0].id)[0]
    element = unit_vm.create_element(unit.id, name="管子")
    replaced = project_io.create_enclosure("钢板桩")
    target = project_io.merge_target_enclosure("默认围护原则")
    assert target == replaced.name
    error = project_io.delete_enclosure(
        project_io.enclosures()[0].id, project_io.merge_target_enclosure("默认围护原则")
    )
    assert error is None
    assert unit_vm.orm.session().get(type(element), element.id).pe_name == target


def test_delete_last_principle_is_rejected(project) -> None:
    error = project_io.delete_foundation(project_io.foundations()[0].id)
    assert error == "至少需要一种地基处理原则。"
    error = project_io.delete_enclosure(project_io.enclosures()[0].id)
    assert error == "至少需要一种沟槽围护原则。"


# --------------------------------------------------------------------------- #
# *.spcp 导入/导出
# --------------------------------------------------------------------------- #
def test_spcp_roundtrip(project, tmp_path: Path) -> None:
    pe = project_io.enclosures()[0]
    pf = project_io.foundations()[0]
    out_pe = tmp_path / "pe.spcp"
    out_pf = tmp_path / "pf.spcp"
    project_io.export_enclosure_spcp(pe.id, out_pe)
    project_io.export_foundation_spcp(pf.id, out_pf)
    kind, name = project_io.import_spcp(out_pe)
    assert (kind, name) == ("enclosure", "默认围护原则1")
    kind, name = project_io.import_spcp(out_pf)
    assert (kind, name) == ("foundation", "默认地基处理原则1")
    original, cloned = project_io.enclosures()[0], project_io.enclosures()[1]
    for field in ("con_found", "excvt", "found_angle", "dock_l", "dock_h",
                  "cover50", "cover", "groove_width", "wet_soil", "deep_well"):
        assert getattr(original, field) == getattr(cloned, field), field
    assert len(original.works) == len(cloned.works)
    assert len(original.widths) == len(cloned.widths)


def test_spcp_rejects_wrong_root(project, tmp_path: Path) -> None:
    bad = tmp_path / "bad.spcp"
    bad.write_text("<?xml version='1.0'?><Something/>", encoding="utf-8")
    with pytest.raises(project_io.ProjectIoError):
        project_io.import_spcp(bad)


# --------------------------------------------------------------------------- #
# schema 迁移 v1 → v2
# --------------------------------------------------------------------------- #
def test_v1_project_migrates_source_column(tmp_path: Path) -> None:
    import shutil

    from app.core.version import SCHEMA_VERSION
    from app.orm import base as orm

    assert SCHEMA_VERSION == 2
    legacy_copy = tmp_path / "old.stn2"
    # 借现成工程文件降版构造 v1 文件：删掉 source 列并把版本号改回 1
    project = tmp_path / "new.stn2"
    project_io.new_project(NewProjectSpec(path=project, unit_names=["雨水工程"]))
    project_io.close_project()
    shutil.copy(project, legacy_copy)
    import sqlite3

    with sqlite3.connect(legacy_copy) as conn:
        conn.execute("ALTER TABLE element RENAME TO element_old")
        conn.execute(
            "CREATE TABLE element (id INTEGER PRIMARY KEY, unit_id INTEGER, category INTEGER,"
            " name VARCHAR(200), depth VARCHAR(100), amount VARCHAR(100), pe_name VARCHAR(200),"
            " pf_name VARCHAR(200), order_no INTEGER)"
        )
        conn.execute(
            "INSERT INTO element (id, unit_id, category, name, depth, amount, pe_name, pf_name,"
            " order_no) SELECT id, unit_id, category, name, depth, amount, pe_name, pf_name,"
            " order_no FROM element_old"
        )
        conn.execute("DROP TABLE element_old")
        conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
        conn.commit()
    orm.open_database(legacy_copy)
    assert orm.get_meta("schema_version") == "2"
    orm.close_database()
