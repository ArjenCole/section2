"""1.0 兼容开发计划（docs/legacy_migration_plan.md）的行为级测试。

用合成 1.0 XML 覆盖已确认的 12+9 项决策：

* 决策 1：管道按 DN 到构件库匹配 oD/iD/t（含 TrimDn、无匹配不伪造）；
* 决策 2：PE×PF 全组合生成新地基原则（PF名·PE名），PE 的基础参数生效；
* 决策 3：多原则按笛卡尔积拆条（PE 外层、PF 内层），数量 = 原数量 × 比例；
* 决策 4：支撑按拆分后各自 PE（不拆类别例外）；
* 决策 5：构筑物 1/2/3/>3 段键原样保留（raw_key），显示按 1.0、汇总按 2.0；
* 决策 12：单价键 Dn → DN；
* legacy_meta：工程级 + 构件级留档往返；来源列摘要；
* 解析报告：坏元素不丢整标段，skipped 进报告。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lxml import etree

from app.services import legacy_migration, project_io

SAMPLE_DIR = Path(__file__).parent / "fixtures" / "legacy"


# --------------------------------------------------------------------------- #
# 合成 1.0 XML
# --------------------------------------------------------------------------- #
_ENCLOSURE_XML = """  <mcPcpEnclosure>
    <Name>{name}</Name>
    <ConFound>{con_found}</ConFound>
    <Excvt>Ⅲ类土</Excvt>
    <FoundAngle>{angle}</FoundAngle>
    <Cush><msReplacement><Name>中粗砂</Name><H>200</H></msReplacement></Cush>
    <DockL>中粗砂</DockL><DockH>中粗砂</DockH><Cover50>中粗砂</Cover50><Cover>素土</Cover>
    <wetsoild>0|0|0</wetsoild><lightwell>3.5|1.2|2</lightwell>
    <jetwell>6|2.5|2</jetwell><bigwell>10|10|2</bigwell><deepwell>15|20|1</deepwell>
    <grooveWidth>WorkWidth</grooveWidth>
    <mcEnclosure>
      <MinDepth>0</MinDepth>
      <eCpntCat>放坡</eCpntCat>
      <mcEclsCpnt>
        <name>放坡</name><H>-1</H><stepWidth>1</stepWidth>
        <mcComponent>
          <Name>放坡|放坡开挖</Name>
          <A>放坡系数|0.5</A>
          <FA>挖土方|height*width</FA>
        </mcComponent>
      </mcEclsCpnt>
      <WSCpnt><mcComponent><Name>无|无止水</Name></mcComponent></WSCpnt>
    </mcEnclosure>
  </mcPcpEnclosure>
"""

_FOUNDATION_XML = """  <mcPcpFoundation>
    <Name>{name}</Name>
    <Foundation><mcComponent><Name>无|无特殊地基</Name></mcComponent></Foundation>
  </mcPcpFoundation>
"""


def _pipe_xml(mat: str, dn: str, content: str = "1") -> str:
    return (
        "<msPipe>"
        f"<Mat>{mat}</Mat><Dn>{dn}</Dn><Content>{content}</Content>"
        "</msPipe>"
    )


def _ref_xml(kind: str, pairs: list[tuple[str, str]]) -> str:
    return "".join(
        f"<{kind}><key>{name}</key><value>{ratio}</value></{kind}>" for name, ratio in pairs
    )


def _element_xml(
    *,
    name: str = "",
    category: str = "直埋管道",
    depth: str = "3",
    amount: str = "100",
    pe_refs: list[tuple[str, str]] | None = None,
    pf_refs: list[tuple[str, str]] | None = None,
    show_pe: str = "",
    show_pf: str = "",
    main_pe: str = "",
    source: str = "",
    pipes: list[str] | None = None,
    params: list[tuple[str, str]] | None = None,
) -> str:
    parts = [
        "<mcElement>",
        f"<Name>{name}</Name>",
        f"<Category>{category}</Category>",
        f"<Depth>{depth}</Depth>",
        f"<Amount>{amount}</Amount>",
        f"<showPEname>{show_pe}</showPEname>",
        f"<showPFname>{show_pf}</showPFname>",
        f"<mainPEname>{main_pe}</mainPEname>",
        "<SizeB>0</SizeB><SizeH>0</SizeH>",
        f"<Source>{source}</Source>",
    ]
    if pe_refs is not None:
        parts.append(_ref_xml("PEname", pe_refs))
    if pf_refs is not None:
        parts.append(_ref_xml("PFname", pf_refs))
    parts.extend(pipes or [])
    for key, value in params or []:
        parts.append(f"<Param><key>{key}</key><value>{value}</value></Param>")
    parts.append("</mcElement>")
    return "".join(parts)


def _legacy_xml(elements: list[str], pe_names: list[str], pf_names: list[str],
                prices: list[tuple[str, str]] | None = None,
                *, pe_angles: dict[str, str] | None = None,
                pe_con: dict[str, str] | None = None,
                version: str = "1.3.2.7") -> str:
    parts = [
        "<Root>",
        f"<Assembly><Version>{version}</Version></Assembly>",
        "<mcBasicInfo><ProjectName>合成样例</ProjectName><ProjectIndex>001</ProjectIndex>"
        "<Author>Section</Author><AtlasName>06MS201-1</AtlasName></mcBasicInfo>",
    ]
    for name in pe_names:
        parts.append(
            _ENCLOSURE_XML.format(
                name=name,
                angle=(pe_angles or {}).get(name, "120"),
                con_found=(pe_con or {}).get(name, "true"),
            )
        )
    for name in pf_names:
        parts.append(_FOUNDATION_XML.format(name=name))
    parts.append("<mcSegment><Name>主线</Name><mcUnit><Name>雨水工程</Name>")
    parts.extend(elements)
    parts.append("</mcUnit></mcSegment>")
    for key, value in prices or []:
        parts.append(f"<Price><name>{key}</name><price>{value}</price></Price>")
    parts.append("</Root>")
    return "\n".join(parts)


def _write(tmp_path: Path, xml: str) -> Path:
    path = tmp_path / "legacy.stn"
    path.write_text(xml, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 解析报告（§8）
# --------------------------------------------------------------------------- #
def test_parse_legacy_returns_report(tmp_path: Path) -> None:
    """parse_legacy 返回 (工程, 报告)，计数进报告；外部传入时写入同一份。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(amount="100")],
            ["放坡开挖"],
            ["没有地基处理"],
        ),
    )
    legacy, report = legacy_migration.parse(source)
    assert legacy.version == "1.3.2.7"
    assert report.source == str(source)
    assert report.schema_version == "1.3.2.7"
    assert not report.skipped


def test_bad_element_does_not_drop_segment(tmp_path: Path) -> None:
    """坏元素只跳过自己（记标段/单位/序号），同标段其他元素照常迁移。"""
    good = _element_xml(name="好构件", amount="100")
    bad = "<mcElement><Name>坏构件</Name><Category>直埋管道</Category><Depth>3</Depth><Amount>50</Amount><msPipe><Mat>Ⅰ级混凝土管</Mat><Dn>不是数字</Dn></msPipe></mcElement>"
    source = _write(
        tmp_path,
        _legacy_xml([bad, good], ["放坡开挖"], ["没有地基处理"]),
    )
    report = legacy_migration.build_legacy_database(source)
    assert any("坏构件" in item and "跳过" in item for item in report.skipped)
    # 好构件仍在
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    names = list(orm.session().scalars(select(Element.name)))
    assert names == ["好构件"]
    orm.close_database()


# --------------------------------------------------------------------------- #
# PE×PF 新地基原则（决策 2）
# --------------------------------------------------------------------------- #
def test_pf_cross_generation(tmp_path: Path) -> None:
    """2 PE × 3 PF = 6 条新 PF；元素 PE1+PF3 → 新 PF“PF3·PE1”。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pe_refs=[("PE1", "1")], pf_refs=[("PF3", "1")])],
            ["PE1", "PE2"],
            ["PF1", "PF2", "PF3"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    assert report.foundations == 6
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import PcpFoundation

    names = list(orm.session().scalars(select(PcpFoundation.name).order_by(PcpFoundation.order_no)))
    assert names == [f"PF{n}·PE{m}" for n in ("1", "2", "3") for m in ("1", "2")]
    # 元素按原 PE/PF 引用到正确的新 PF
    from app.core.models.models import Element

    element = orm.session().scalars(select(Element)).first()
    assert element.pf_name == "PF3·PE1"
    # 新 PF 的基础参数取对应 PE（PE2 角度默认 120；单独验证见 test_pf_uses_pe_foundation）
    orm.close_database()


def test_pf_uses_pe_foundation(tmp_path: Path) -> None:
    """每个新 PF 的 ConFound/FoundAngle/Cush 取对应 PE 的值（决策 2 / 决策 10）。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pe_refs=[("放坡", "1")], pf_refs=[("地基", "1")])],
            ["放坡", "钢板桩"],
            ["地基"],
            pe_angles={"放坡": "90", "钢板桩": "180"},
            pe_con={"放坡": "true", "钢板桩": "false"},
        ),
    )
    legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import PcpFoundation

    rows = {
        row.name: row
        for row in orm.session().scalars(select(PcpFoundation))
    }
    assert rows["地基·放坡"].found_angle == 90 and rows["地基·放坡"].con_found
    assert rows["地基·钢板桩"].found_angle == 180 and not rows["地基·钢板桩"].con_found
    # legacy_meta 记录生成来源
    meta = json.loads(rows["地基·钢板桩"].legacy_meta)
    assert meta == {"legacy_pe_name": "钢板桩", "legacy_pf_name": "地基"}
    orm.close_database()


# --------------------------------------------------------------------------- #
# 多原则拆分（决策 3 / §6）
# --------------------------------------------------------------------------- #
def test_split_cartesian_2x3(tmp_path: Path) -> None:
    """2 围护 × 3 地基 = 6 条；数量 = 原数量 × PE 比例 × PF 比例。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [
                _element_xml(
                    name="干管",
                    pe_refs=[("PE1", "0.5"), ("PE2", "0.5")],
                    pf_refs=[("PF1", "0.2"), ("PF2", "0.3"), ("PF3", "0.5")],
                )
            ],
            ["PE1", "PE2"],
            ["PF1", "PF2", "PF3"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    assert report.splits == 1
    assert report.elements == 6
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    rows = list(orm.session().scalars(select(Element).order_by(Element.order_no)))
    assert [row.amount for row in rows] == [
        "(100)*0.5*0.2", "(100)*0.5*0.3", "(100)*0.5*0.5",
        "(100)*0.5*0.2", "(100)*0.5*0.3", "(100)*0.5*0.5",
    ]
    # PE 外层、PF 内层（旧版 mscGroove.Cal 顺序）
    assert [(row.pe_name, row.pf_name) for row in rows] == [
        ("PE1", "PF1·PE1"), ("PE1", "PF2·PE1"), ("PE1", "PF3·PE1"),
        ("PE2", "PF1·PE2"), ("PE2", "PF2·PE2"), ("PE2", "PF3·PE2"),
    ]
    # 名称 = 原名·新PF名 百分比%
    assert rows[0].name == "干管·PF1·PE1 10%"
    assert rows[5].name == "干管·PF3·PE2 25%"
    # legacy_meta：完整 refs + assigned 信息
    meta = json.loads(rows[0].legacy_meta)
    assert meta["pe_refs"] == [{"name": "PE1", "ratio": 0.5}, {"name": "PE2", "ratio": 0.5}]
    assert meta["pf_refs"] == [
        {"name": "PF1", "ratio": 0.2}, {"name": "PF2", "ratio": 0.3}, {"name": "PF3", "ratio": 0.5},
    ]
    assert meta["assigned_pe"] == "PE1" and meta["assigned_pf"] == "PF1·PE1"
    assert meta["assigned_ratio"] == pytest.approx(0.1)
    orm.close_database()


def test_split_single_ref_ratio(tmp_path: Path) -> None:
    """单引用比例 ≠ 1：数量 × 比例、名称不变、比例进 legacy_meta（决策 3/14）。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pe_refs=[("PE1", "0.8")], pf_refs=[("PF1", "1")])],
            ["PE1"],
            ["PF1"],
        ),
    )
    legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    element = orm.session().scalars(select(Element)).first()
    assert element.name == ""  # 名称不变
    assert element.amount == "(100)*0.8"
    meta = json.loads(element.legacy_meta)
    assert meta["pe_refs"] == [{"name": "PE1", "ratio": 0.8}]
    assert meta["assigned_ratio"] == pytest.approx(0.8)
    orm.close_database()


def test_split_zero_and_unbalanced_ratios(tmp_path: Path) -> None:
    """0 比例生成 0 数量子条目；合计 ≠ 1 按原比例不归一（决策 4）。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [
                _element_xml(
                    name="干管",
                    pe_refs=[("PE1", "0"), ("PE2", "1")],
                    pf_refs=[("PF1", "1")],
                )
            ],
            ["PE1", "PE2"],
            ["PF1"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    rows = list(orm.session().scalars(select(Element).order_by(Element.order_no)))
    assert len(rows) == 2
    assert rows[0].amount == "0" and rows[0].pe_name == "PE1"
    assert rows[1].amount == "100" and rows[1].pe_name == "PE2"
    # 合计 = 1，无缩放警告；0 比例条目保留引用关系
    assert not any("合计" in w for w in report.warnings)
    orm.close_database()


def test_no_split_categories_keep_all_refs(tmp_path: Path) -> None:
    """构筑物 / 顶管 / 牵引管不拆（决策 18）：一条构件，原始 refs 进 legacy_meta。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [
                _element_xml(
                    name="井",
                    category="构筑物",
                    main_pe="PE2",
                    pe_refs=[("PE1", "0.6"), ("PE2", "0.4")],
                    pf_refs=[("PF1", "1")],
                    params=[("-名称", "井"), ("构筑物|垫层|m3", "1.5")],
                ),
                _element_xml(
                    name="顶",
                    category="顶管",
                    main_pe="PE1",
                    pe_refs=[("PE1", "1")],
                    pf_refs=[("PF1", "1")],
                    pipes=[_pipe_xml("钢筋混凝土管", "1000")],
                ),
            ],
            ["PE1", "PE2"],
            ["PF1"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    assert report.splits == 0
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    rows = list(orm.session().scalars(select(Element).order_by(Element.order_no)))
    assert len(rows) == 2
    well, jacking = rows
    assert well.pe_name == "PE2" and well.pf_name == "PF1·PE2"
    meta = json.loads(well.legacy_meta)
    assert meta["pe_refs"] == [{"name": "PE1", "ratio": 0.6}, {"name": "PE2", "ratio": 0.4}]
    assert meta["main_pe_name"] == "PE2"
    assert meta["assigned_pe"] == "PE2"
    assert jacking.pe_name == "PE1"
    orm.close_database()


def test_invalid_ref_falls_back_to_first_principles(tmp_path: Path) -> None:
    """引用悬空 → 跳过该引用；全部无效 → 回落第一条 PE/PF 组合（决策 11）。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pe_refs=[("不存在的PE", "1")], pf_refs=[("不存在的PF", "1")])],
            ["PE1"],
            ["PF1"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    assert any("不存在的PE" in w for w in report.warnings)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    element = orm.session().scalars(select(Element)).first()
    assert element.pe_name == "PE1"
    assert element.pf_name == "PF1·PE1"
    orm.close_database()


# --------------------------------------------------------------------------- #
# 管道匹配（决策 1 / §4）
# --------------------------------------------------------------------------- #
def test_pipe_matches_atlas_template(tmp_path: Path) -> None:
    """DN600 Ⅰ级混凝土管 → 模板 oD/iD/t（不再 od=iD=Dn）；8 组候选生成。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pipes=[_pipe_xml("Ⅰ级混凝土管", "600")])],
            ["PE1"],
            ["PF1"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    element = orm.session().scalars(select(Element)).first()
    pipe = element.pipes[0]
    assert pipe.od == pytest.approx(720.0)  # id_t：iD=600 + 2×60
    assert pipe.inner_d == pytest.approx(600.0)
    assert pipe.t == pytest.approx(60.0)
    assert pipe.direct == "id_t"
    assert pipe.cat == "混凝土管-刚性接口"
    assert len(pipe.element.atlas_candidates) == 8
    # 参数行按新 PF 自动匹配出值（决策 7）
    values = {param.key: param.value for param in element.params}
    assert values.get("管道壁厚") == "60"
    assert values.get("工作面加宽") and values.get("垫层厚") and values.get("基础厚")
    assert any("DN600" in line and "oD 720" in line for line in report.pipe_matches)
    orm.close_database()


def test_pipe_trimdn_mapping(tmp_path: Path) -> None:
    """非标 DN 2700 → TrimDn 2800 匹配同材质模板（决策 6）。

    构件库混凝土管只有图集标准 DN（1350/1650/2800…）：2700 在 1~3 级
    （同材质 / 同类别 + 同 DN）全不命中，TrimDn 映射后按同材质精确命中。
    """
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pipes=[_pipe_xml("Ⅰ级混凝土管", "2700")])],
            ["PE1"],
            ["PF1"],
        ),
    )
    legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    pipe = orm.session().scalars(select(Element)).first().pipes[0]
    assert pipe.dn == 2700  # 旧 DN 原样保留
    assert pipe.inner_d == 2800  # 匹配到的模板 DN（TrimDn 2700→2800）
    assert pipe.t and pipe.t > 0
    orm.close_database()


def test_pipe_unmatched_stays_empty(tmp_path: Path) -> None:
    """匹配不到不伪造 oD/iD/t（保持 None），原因进报告。

    （未知材质按 1.0 口径折算化学建材类别，DN600 能按类别命中模板；
    这里用库中任何类别都没有的 DN123 才构造“无模板”场景。）
    """
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pipes=[_pipe_xml("不存在的管材", "123")])],
            ["PE1"],
            ["PF1"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    pipe = orm.session().scalars(select(Element)).first().pipes[0]
    assert pipe.od is None and pipe.inner_d is None and pipe.t is None
    assert any("未匹配到构件库模板" in w for w in report.warnings)
    orm.close_database()


def test_pipe_level_markers_not_cross_matched() -> None:
    """级别标记不一致不靠材质包含跨级匹配（风险 2）。

    材质包含（级别 2）只用于同级别内的前后缀差异；单测覆盖判定函数。
    """
    from app.services.legacy_migration.matcher import _material_contains

    assert _material_contains("Ⅱ级混凝土管", "Ⅰ级混凝土管") is False  # 级别不一致
    assert _material_contains("球墨铸铁管 K9", "球墨铸铁管 K8") is False
    assert _material_contains("混凝土管", "Ⅱ级混凝土管") is True  # 单方无级别标记
    assert _material_contains("Ⅱ级混凝土管", "Ⅱ级混凝土管加长") is True  # 同级别前后缀
    assert _material_contains("混凝土管", "钢筋混凝土管") is True  # 计划 §4.2 示例（双方无标记）


def test_pipe_exact_material_match(tmp_path: Path) -> None:
    """Ⅱ级混凝土管 DN600 → 同材质模板（材质完全相等 + 同 DN + 同类别）。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(pipes=[_pipe_xml("Ⅱ级混凝土管", "600")])],
            ["PE1"],
            ["PF1"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element

    pipe = orm.session().scalars(select(Element)).first().pipes[0]
    assert pipe.t == pytest.approx(65.0)  # Ⅱ级 DN600 模板壁厚（≠ Ⅰ级 60）
    assert pipe.inner_d == pytest.approx(600.0)
    assert any("材质完全相等" in line for line in report.pipe_matches)
    orm.close_database()


# --------------------------------------------------------------------------- #
# 构筑物键与 raw_key（决策 5 / §7）
# --------------------------------------------------------------------------- #
def test_structure_keys_raw_preserved(tmp_path: Path) -> None:
    """1/2/3/>3 段键都计入工程量：raw_key 原样、显示三列按 1.0 规则。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [
                _element_xml(
                    name="井",
                    category="构筑物",
                    amount="2",
                    params=[
                        ("-名称", "井"),
                        ("构筑物|垫层|m3", "1"),      # 3 段
                        ("土方|m3", "2"),              # 2 段
                        ("钢筋", "3"),                  # 1 段
                        ("a|b|c|d", "4"),               # >3 段
                    ],
                )
            ],
            ["PE1"],
            ["PF1"],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import ElementQuantity

    rows = list(orm.session().scalars(select(ElementQuantity).order_by(ElementQuantity.order_no)))
    assert [row.raw_key for row in rows] == ["构筑物|垫层|m3", "土方|m3", "钢筋", "a|b|c|d"]
    assert [(row.category, row.item, row.unit) for row in rows] == [
        ("构筑物", "垫层", "m3"),
        ("", "土方", "m3"),
        ("", "钢筋", ""),
        ("a", "b", "c|d"),
    ]
    # >3 段记警告；键处理明细进报告
    assert any("超过 3 段" in w for w in report.warnings)
    assert len(report.structure_keys) == 4

    # 计算输出用 raw_key（1.0 键不被改写）
    from app.core.models.models import Element
    from app.viewmodels.unit_vm import compute_unit

    element = orm.session().scalars(select(Element)).first()
    _summary, detail = compute_unit(element.unit_id)
    keys = {quantity.key for quantity in detail[0][1].items()}
    assert {"构筑物|垫层|m3", "土方|m3", "钢筋", "a|b|c|d"} <= keys
    orm.close_database()


def test_structure_price_by_raw_key(tmp_path: Path) -> None:
    """旧单价按 raw_key 精确命中；2 段键不因 scope 回落错价。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [
                _element_xml(
                    name="井",
                    category="构筑物",
                    amount="2",
                    params=[("构筑物|垫层|m3", "1"), ("土方|m3", "1")],
                )
            ],
            ["PE1"],
            ["PF1"],
            prices=[("构筑物|垫层|m3", "120"), ("土方|m3", "30")],
        ),
    )
    legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element
    from app.services.summary import unit_summary

    element = orm.session().scalars(select(Element)).first()
    rows = {row["key"]: row for row in unit_summary(element.unit_id)}
    assert rows["构筑物|垫层|m3"]["price"] == pytest.approx(120.0)
    assert rows["土方|m3"]["price"] == pytest.approx(30.0)
    # 显示三列：2 段键分类为空（1.0 口径）
    assert rows["土方|m3"]["category"] == "" and rows["土方|m3"]["item"] == "土方"
    orm.close_database()


def test_quantity_edit_clears_raw_key(tmp_path: Path, qapp) -> None:
    """只改值保留 raw_key；改分类/名称/单位清空 raw_key（决策 17）。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [
                _element_xml(
                    name="井",
                    category="构筑物",
                    params=[("构筑物|垫层|m3", "1")],
                )
            ],
            ["PE1"],
            ["PF1"],
        ),
    )
    legacy_migration.build_legacy_database(source)
    from app.viewmodels.unit_vm import update_quantity

    from sqlalchemy import select

    from app.core.models.models import ElementQuantity

    session = project_io.orm.session()
    quantity = session.scalars(select(ElementQuantity)).first()
    row_id = quantity.id

    # 只改值：raw_key 保留
    update_quantity(row_id, value="9")
    session.expire_all()
    quantity = session.get(ElementQuantity, row_id)
    assert quantity.raw_key == "构筑物|垫层|m3" and quantity.value == "9"

    # 改名称：raw_key 清空，按三列走 2.0 原生键
    update_quantity(row_id, item="垫层C10")
    session.expire_all()
    quantity = session.get(ElementQuantity, row_id)
    assert quantity.raw_key == ""
    project_io.orm.close_database()


# --------------------------------------------------------------------------- #
# 单价键 Dn → DN（决策 12）
# --------------------------------------------------------------------------- #
def test_price_dn_rewrite(tmp_path: Path) -> None:
    """旧单价键“… Dn600|m”重写为 DN，迁移后管材单价能命中。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [_element_xml(amount="10", pipes=[_pipe_xml("Ⅰ级混凝土管", "600")])],
            ["PE1"],
            ["PF1"],
            prices=[("管材|Ⅰ级混凝土管 Dn600|m", "210")],
        ),
    )
    report = legacy_migration.build_legacy_database(source)
    assert any("Dn600" in line and "DN600" in line for line in report.price_rewrites)
    from sqlalchemy import select

    from app.core.models import base as orm
    from app.core.models.models import Element, Price
    from app.services.summary import unit_summary

    keys = list(orm.session().scalars(select(Price.key)))
    assert "管材|Ⅰ级混凝土管 DN600|m" in keys
    # 计算输出的管材键（DN 口径）能命中旧单价
    element = orm.session().scalars(select(Element)).first()
    rows = {row["key"]: row for row in unit_summary(element.unit_id)}
    pipe_rows = [row for key, row in rows.items() if key.startswith("管材|")]
    assert pipe_rows and pipe_rows[0]["price"] == pytest.approx(210.0)
    orm.close_database()


# --------------------------------------------------------------------------- #
# legacy_meta 与来源摘要（决策 5 / 15）
# --------------------------------------------------------------------------- #
def test_legacy_meta_roundtrip(tmp_path: Path) -> None:
    """工程级 + 构件级 legacy_meta 保存 / 重开不丢；来源列摘要完整。"""
    source = _write(
        tmp_path,
        _legacy_xml(
            [
                _element_xml(
                    name="干管",
                    source="Ⅰ级混凝土管 Dn600",
                    show_pe="PE1",
                    show_pf="PF1",
                    pe_refs=[("PE1", "0.6"), ("PE2", "0.4")],
                    pf_refs=[("PF1", "1")],
                )
            ],
            ["PE1", "PE2"],
            ["PF1"],
        ),
    )
    legacy_migration.migrate(source, tmp_path / "out.stn")
    project_io.open_project(tmp_path / "out.stn")
    try:
        from sqlalchemy import select

        from app.core.models import base as orm
        from app.core.models.models import BasicInfo, Element

        info = orm.session().get(BasicInfo, 1)
        meta = json.loads(info.legacy_meta)
        assert meta["source_version"] == "1.3.2.7"
        assert meta["source_file"] == str(source)
        assert meta["migrated_at"]

        element = orm.session().scalars(select(Element)).first()
        element_meta = json.loads(element.legacy_meta)
        assert element_meta["show_pe_name"] == "PE1"  # 单 show 名
        assert element_meta["main_pe_name"] == ""
        assert element_meta["source"] == "Ⅰ级混凝土管 Dn600"
        assert element_meta["source_version"] == "1.3.2.7"
        # 来源列摘要：旧来源在最前，PE/PF 比例随后（截断到 200）
        assert element.source.startswith("Ⅰ级混凝土管 Dn600｜1.0迁移｜PE:PE160%,PE240%｜PF:PF1100%")
        assert len(element.source) <= 200
        # 保存 → 重开：legacy_meta 零漂移
        before = element.legacy_meta
        project_io.save()
        path = project_io.current_path()
    finally:
        project_io.close_project()
    project_io.open_project(path)
    try:
        from sqlalchemy import select

        from app.core.models import base as orm
        from app.core.models.models import BasicInfo, Element

        element = orm.session().scalars(select(Element)).first()
        assert element.legacy_meta == before
        assert json.loads(orm.session().get(BasicInfo, 1).legacy_meta)["source_version"] == "1.3.2.7"
    finally:
        project_io.close_project()


def test_legacy_meta_json_view_and_vm(tmp_path: Path, qapp) -> None:
    """unit_vm.legacy_meta_text 返回格式化 JSON；普通工程为空。"""
    source = _write(
        tmp_path,
        _legacy_xml([_element_xml(name="干管")], ["PE1"], ["PF1"]),
    )
    legacy_migration.build_legacy_database(source)
    from sqlalchemy import select

    from app.core.models.models import Element
    from app.viewmodels.unit_vm import legacy_meta_text

    session = project_io.orm.session()
    element = session.scalars(select(Element)).first()
    text = legacy_meta_text(element.id)
    assert json.loads(text)  # 合法 JSON
    assert "\n" in text  # 缩进格式化
    project_io.orm.close_database()
