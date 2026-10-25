"""旧 .stn 迁移测试（M6 验收）。

用 tests/fixtures/legacy 的样例旧工程做批量导入：全部成功打开、
标段/单位工程/构件/管道计数与源文件一致（多原则条目按比例拆条后只多不少）、
原则引用全部落到实际表记录；“多原则与构筑物”样例覆盖多原则引用按比例
拆条（方案 B）与构筑物（mcE7）迁移。
"""

from __future__ import annotations

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
    target = tmp_path / f"{source.stem}.stn"
    report = stn_migration.migrate(source, target)

    assert target.exists()
    expected = _source_counts(source)
    assert report.segments == expected["segments"]
    assert report.units == expected["units"]
    # 1.0 多原则条目按比例拆条（方案 B），构件/管道只会增多不会减少；
    # 精确拆分数见 test_migrate_multi_principle_split
    assert report.elements >= expected["elements"]
    assert report.pipes >= expected["pipes"]
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

        from app.core.models.models import Element

        referenced_pe = {
            name for name in session.scalars(select(Element.pe_name)) if name
        }
        referenced_pf = {
            name for name in session.scalars(select(Element.pf_name)) if name
        }
        assert referenced_pe <= enclosure_names, f"悬空围护原则引用：{referenced_pe - enclosure_names}"
        assert referenced_pf <= foundation_names, f"悬空地基原则引用：{referenced_pf - foundation_names}"
        # 降水/面宽引用（迁移时跟随围护原则名）同样不悬空
        referenced_pp = {
            name for name in session.scalars(select(Element.pp_name)) if name
        }
        referenced_pw = {
            name for name in session.scalars(select(Element.pw_name)) if name
        }
        precipitation_names = set(project_io.precipitation_names())
        width_names = set(project_io.width_names())
        assert referenced_pp <= precipitation_names, f"悬空降水原则引用：{referenced_pp - precipitation_names}"
        assert referenced_pw <= width_names, f"悬空面宽原则引用：{referenced_pw - width_names}"
    finally:
        project_io.close_project()


def test_migrate_multi_principle_split(tmp_path: Path) -> None:
    """1.0 多原则条目按比例拆条（方案 B）：pe×pf 组合逐对拆、数量 = 原数量 × 比例。

    样例的第二条构件：放坡开挖 0.6 + 钢板桩 0.4（旧主原则 钢板桩）、数量 200.5；
    拆成两条后断面量与旧版 Σ(组合 × 比例) 一致，构筑物 / 单原则条目不拆。
    """
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import CATEGORY_STRUCTURE, Element

    source = next(
        path for path in _available_samples() if "多原则" in path.stem
    )
    target = tmp_path / "split.stn"
    report = stn_migration.migrate(source, target)

    # 3 条源构件 → 4 条（多原则条目拆 2），管道 2 → 3（两个子条目各带一根）
    assert report.elements == 4
    assert report.pipes == 3
    assert report.splits == 1
    assert len(report.split_details) == 1
    assert "放坡开挖 60%" in report.split_details[0]
    assert "钢板桩 40%" in report.split_details[0]
    assert "旧主围护原则：钢板桩" in report.split_details[0]

    project_io.open_project(target)
    try:
        rows = list(orm.session().scalars(select(Element).order_by(Element.order_no, Element.id)))
        assert len(rows) == 4

        # 单原则条目原样保留（名称/数量原文不动）
        assert rows[0].name == ""
        assert rows[0].amount == "100"
        assert rows[0].pe_name == "放坡开挖"
        assert rows[0].pp_name == "放坡开挖" and rows[0].pw_name == "放坡开挖"

        # 拆分条目：名称加“·原则名 占比%”后缀，数量合成算式，各引用自己的原则
        assert rows[1].name == "·放坡开挖 60%"
        assert rows[1].amount == "(200.5)*0.6"
        assert rows[1].pe_name == "放坡开挖"
        assert rows[1].pp_name == "放坡开挖" and rows[1].pw_name == "放坡开挖"
        assert rows[2].name == "·钢板桩 40%"
        assert rows[2].amount == "(200.5)*0.4"
        assert rows[2].pe_name == "钢板桩"
        assert rows[2].pp_name == "钢板桩" and rows[2].pw_name == "钢板桩"
        # 管道行原样复制到每个子条目
        for row in rows[1:3]:
            assert len(row.pipes) == 1 and row.pipes[0].dn == 800

        # 构筑物不拆：围护取旧主原则（mainPEname 在文件中存在）
        well = rows[3]
        assert well.category == CATEGORY_STRUCTURE
        assert well.name == "圆形雨水检查井DN1000"
        assert well.pe_name == "不起作用的原则"

        # 拆分条目可正常计算（深度 3.6 > 围护做法适用范围即可出量）
        from app.viewmodels.unit_vm import compute_unit

        _summary, detail = compute_unit(rows[1].unit_id)
        keys = {quantity.key for quantity in detail[1][1].items()}
        assert any(key.startswith("开挖|") for key in keys)
    finally:
        project_io.close_project()


def test_migrate_preserves_expressions_and_params(tmp_path: Path) -> None:
    """埋深/数量按原文逐字保留（可以是算式，如 “3+0.5”），不换算成数值。"""
    source = next((path for path in _available_samples() if _source_counts(path)["elements"] > 0), None)
    if source is None:
        pytest.skip("无含构件的样例")
    tree = etree.parse(str(source))
    originals = [
        (node.findtext("Depth") or "", node.findtext("Amount") or "")
        for node in tree.getroot().findall(".//mcSegment/mcUnit/mcElement")
    ]
    target = tmp_path / "copy.stn"
    stn_migration.migrate(source, target)
    project_io.open_project(target)
    try:
        from sqlalchemy import select

        from app.core.models import base as orm
        from app.core.models.models import Unit

        units = list(orm.session().scalars(select(Unit).order_by(Unit.order_no, Unit.id)))
        rows = [row for unit in units for row in unit_vm.element_rows(unit.id)]
        assert [(row.depth, row.amount) for row in rows] == originals
        assert any("+" in depth for depth, _ in originals)  # 样例里确实带算式
    finally:
        project_io.close_project()


def test_migrate_gets_category_atlas_params(tmp_path: Path) -> None:
    """旧档按类别补空值图集参数行：直埋三行、包封 / 箱涵的工作面加宽与垫层厚。

    1.0 没有这些行，新版补成空值（空 = 自动按图集 / 软件约定），
    所以补行不改变工程量。
    """
    source = _available_samples()[0]
    tree = etree.parse(str(source))
    element = tree.getroot().find(".//mcSegment/mcUnit/mcElement")
    if element is None:
        pytest.skip("样例无构件")
    element.find("Category").text = "包封埋管"
    patched = tmp_path / "包封样例.stn"
    tree.write(str(patched), encoding="utf-8", xml_declaration=True)

    target = tmp_path / "out.stn"
    stn_migration.migrate(patched, target)
    project_io.open_project(target)
    try:
        from sqlalchemy import select

        from app.core.models import base as orm
        from app.core.models.models import CATEGORY_BURIED, CATEGORY_ENCASED, Element

        encased = orm.session().scalars(
            select(Element).where(Element.category == CATEGORY_ENCASED)
        ).first()
        assert encased is not None
        assert [param.key for param in unit_vm.param_rows(encased.id)][-2:] == [
            "工作面加宽",
            "垫层厚",
        ]
        # 同档里改成直埋的构件补三行（基础厚只属于直埋）
        buried_element = tree.getroot().find(".//mcSegment/mcUnit/mcElement")
        buried_element.find("Category").text = "直埋管道"
        buried_path = tmp_path / "直埋样例.stn"
        tree.write(str(buried_path), encoding="utf-8", xml_declaration=True)
        buried_target = tmp_path / "buried.stn"
        stn_migration.migrate(buried_path, buried_target)
        orm.close_database()
        project_io.open_project(buried_target)
        buried = orm.session().scalars(
            select(Element).where(Element.category == CATEGORY_BURIED)
        ).first()
        assert buried is not None
        assert [param.key for param in unit_vm.param_rows(buried.id)][-3:] == [
            "工作面加宽",
            "垫层厚",
            "基础厚",
        ]
    finally:
        project_io.close_project()


def test_migrate_readonly_source(tmp_path: Path) -> None:
    """迁移绝不修改原 .stn。"""
    source = _available_samples()[0]
    before = source.read_bytes()
    stn_migration.migrate(source, tmp_path / "out.stn")
    assert source.read_bytes() == before


def test_migrate_bad_file_aborts(tmp_path: Path) -> None:
    bogus = tmp_path / "bad.stn"
    bogus.write_text("不是 XML", encoding="utf-8")
    with pytest.raises(stn_migration.MigrationError):
        stn_migration.migrate(bogus, tmp_path / "out.stn")
    assert not (tmp_path / "out.stn").exists()


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

    report = stn_migration.migrate(broken, tmp_path / "out.stn")
    assert any("不存在的围护原则" in warning for warning in report.warnings)

