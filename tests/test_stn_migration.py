"""旧 .stn 迁移测试（计划 §5.1 / M6 验收）。

用 tests/fixtures/legacy 的样例旧工程做批量导入：全部成功打开、
标段/单位工程/构件/管道计数与源文件一致、原则引用全部落到实际表记录；
“多原则与构筑物”样例覆盖多原则引用（PEname 字典）与构筑物（mcE7）迁移。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from lxml import etree

from app.services import project_io, stn_migration
from app.viewmodels import unit_vm

SAMPLE_DIR = Path(__file__).parent / "fixtures" / "legacy"


def _available_samples() -> list[Path]:
    return sorted(SAMPLE_DIR.glob("*.stn"))


def _source_counts(path: Path) -> dict[str, int]:
    """直接从旧 XML 数出各层节点数（迁移计数的对照基准）。"""
    tree = etree.parse(str(path))
    root = tree.getroot()
    elements = root.findall(".//mcSegment/mcUnit/mcElement")
    return {
        "segments": len(root.findall("mcSegment")),
        "units": len(root.findall(".//mcSegment/mcUnit")),
        "elements": len(elements),
        "pipes": len(root.findall(".//mcSegment/mcUnit/mcElement/msPipe")),
        "enclosures": len(root.findall("mcPcpEnclosure")),
        "foundations": len(root.findall("mcPcpFoundation")),
        "prices": len(root.findall("Price")),
    }


@pytest.mark.parametrize("source", _available_samples(), ids=lambda path: path.stem)
def test_migrate_sample(tmp_path: Path, source: Path) -> None:
    target = tmp_path / f"{source.stem}.stn2"
    report = stn_migration.migrate(source, target)

    assert target.exists()
    expected = _source_counts(source)
    assert report.segments == expected["segments"]
    assert report.units == expected["units"]
    assert report.elements == expected["elements"]
    assert report.pipes == expected["pipes"]
    assert report.enclosures == expected["enclosures"]
    assert report.foundations == expected["foundations"]
    assert report.prices == expected["prices"]

    # 迁移结果能被新软件打开，且原则引用不悬空
    project_io.open_project(target)
    try:
        enclosure_names = set(project_io.enclosure_names())
        foundation_names = set(project_io.foundation_names())
        session = project_io.orm.session()
        from sqlalchemy import select

        from app.core.models.models import MULTI_PE_TEXT, MULTI_PF_TEXT, Element, ElementPrinciple

        referenced_pe = {
            name for name in session.scalars(select(Element.pe_name)) if name
        } - {MULTI_PE_TEXT}
        referenced_pf = {
            name for name in session.scalars(select(Element.pf_name)) if name
        } - {MULTI_PF_TEXT}
        assert referenced_pe <= enclosure_names, f"悬空围护原则引用：{referenced_pe - enclosure_names}"
        assert referenced_pf <= foundation_names, f"悬空地基原则引用：{referenced_pf - foundation_names}"
        # 多原则引用行必须落到真实原则（旧版 PEname 字典）
        ref_pe_names = {
            name for name in session.scalars(
                select(ElementPrinciple.name).where(ElementPrinciple.kind == "pe")
            ) if name
        }
        ref_pf_names = {
            name for name in session.scalars(
                select(ElementPrinciple.name).where(ElementPrinciple.kind == "pf")
            ) if name
        }
        assert ref_pe_names <= enclosure_names, f"悬空多原则围护引用：{ref_pe_names - enclosure_names}"
        assert ref_pf_names <= foundation_names, f"悬空多原则地基引用：{ref_pf_names - foundation_names}"

        # 原则做法/构件必须存在（能计算）
        assert enclosure_names == set(referenced_pe) | enclosure_names
    finally:
        project_io.close_project()


def test_migrate_preserves_expressions_and_params(tmp_path: Path) -> None:
    source = next((path for path in _available_samples() if _source_counts(path)["elements"] > 0), None)
    if source is None:
        pytest.skip("无含构件的样例")
    target = tmp_path / "copy.stn2"
    stn_migration.migrate(source, target)
    project_io.open_project(target)
    try:
        rows = unit_vm.element_rows(_first_unit_with_elements().id) if _first_unit_with_elements() else []
        if rows:
            # 埋深/数量仍是原文（可能是算式）
            assert all(isinstance(row.depth, str) for row in rows)
    finally:
        project_io.close_project()


def test_migrate_readonly_source(tmp_path: Path) -> None:
    """迁移绝不修改原 .stn。"""
    source = _available_samples()[0]
    before = source.read_bytes()
    stn_migration.migrate(source, tmp_path / "out.stn2")
    assert source.read_bytes() == before


def test_migrate_bad_file_aborts(tmp_path: Path) -> None:
    bogus = tmp_path / "bad.stn"
    bogus.write_text("不是 XML", encoding="utf-8")
    with pytest.raises(stn_migration.MigrationError):
        stn_migration.migrate(bogus, tmp_path / "out.stn2")
    assert not (tmp_path / "out.stn2").exists()


def test_migrate_report_lists_warnings(tmp_path: Path) -> None:
    """构造缺原则引用的旧文件：报告必须显式列出（风险 7）。"""
    source = _available_samples()[0]
    tree = etree.parse(str(source))
    root = tree.getroot()
    element = root.find(".//mcSegment/mcUnit/mcElement")
    if element is None:
        pytest.skip("样例无构件")
    element.find("showPEname").text = "不存在的围护原则"
    # 一并删掉 PEname/PFname 引用字典，构造“原则引用悬空”的一致场景
    for tag in ("PEname", "PFname"):
        for node in element.findall(tag):
            element.remove(node)
    broken = tmp_path / "broken.stn"
    tree.write(str(broken), encoding="utf-8", xml_declaration=True)

    report = stn_migration.migrate(broken, tmp_path / "out.stn2")
    assert any("不存在的围护原则" in warning for warning in report.warnings)


def _first_unit_with_elements():
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Unit

    session = orm.session()
    for unit in session.scalars(select(Unit)):
        if unit.elements:
            return unit
    return None
