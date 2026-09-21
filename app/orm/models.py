"""`.stn2` 表结构（计划 §4.1）。

语义照搬旧版 C#（工程 → 标段 → 单位工程 → 构件 → 管道），实现改为规范化的关系表：
原则（围护 PE / 地基 PF）独立成表，可被多个构件按名字引用。

通用约定（§4.2）：

* ``depth`` / ``amount`` / ``content`` 存字符串原文（可能是 ``2.5+0.3``），
  求值结果不落库，运行时用 :mod:`app.core.evaluator` 算，避免两份数据不一致；
* 所有表带 ``order_no`` 保序；外键 ``ondelete="CASCADE"``，删父行级联清理子行；
* 写操作后由 :func:`app.services.project_io.commit` 落盘。
"""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.version import DEFAULT_ATLAS_NAME
from app.orm.base import Base

# --------------------------------------------------------------------------- #
# 构件类别（对应旧版 mcElement.typeDic，键改为 0~6 整数）
# --------------------------------------------------------------------------- #
CATEGORY_NONE = 0  # 空
CATEGORY_BURIED = 1  # 直埋管道   mcE1
CATEGORY_ENCASED = 2  # 包封埋管   mcE2
CATEGORY_BOX_CULVERT = 3  # 箱涵       mcE3
CATEGORY_JACKING = 4  # 顶管       mcE4
CATEGORY_PULLING = 5  # 牵引管     mcE5
CATEGORY_GALLERY = 6  # 管廊       mcE6

CATEGORY_NAMES: dict[int, str] = {
    CATEGORY_NONE: "",
    CATEGORY_BURIED: "直埋管道",
    CATEGORY_ENCASED: "包封埋管",
    CATEGORY_BOX_CULVERT: "箱涵",
    CATEGORY_JACKING: "顶管",
    CATEGORY_PULLING: "牵引管",
    CATEGORY_GALLERY: "管廊",
}

#: 下拉框顺序（不含“空”类别）
CATEGORY_CHOICES: tuple[int, ...] = (
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_JACKING,
    CATEGORY_PULLING,
    CATEGORY_GALLERY,
)

#: 工程量单位：旧版 mcE1~mcE6 的 unit 字段都是 "m"
UNIT_BY_CATEGORY: dict[int, str] = {
    CATEGORY_NONE: "",
    CATEGORY_BURIED: "m",
    CATEGORY_ENCASED: "m",
    CATEGORY_BOX_CULVERT: "m",
    CATEGORY_JACKING: "m",
    CATEGORY_PULLING: "m",
    CATEGORY_GALLERY: "m",
}


def category_name(category: int | None) -> str:
    return CATEGORY_NAMES.get(int(category or 0), "")


def category_from_name(name: str) -> int:
    for value, text in CATEGORY_NAMES.items():
        if text == name:
            return value
    return CATEGORY_NONE


def unit_of(category: int | None) -> str:
    return UNIT_BY_CATEGORY.get(int(category or 0), "")


# --------------------------------------------------------------------------- #
# 降水参数（对应旧版 mcPrecipitation.toXML()："elevation|gap|sides"）
# --------------------------------------------------------------------------- #
PRECIPITATION_COLUMNS: tuple[str, ...] = (
    "wet_soil",
    "light_well",
    "jet_well",
    "big_well",
    "deep_well",
)

PRECIPITATION_LABELS: dict[str, str] = {
    "wet_soil": "湿土排水",
    "light_well": "轻型井点",
    "jet_well": "喷射井点",
    "big_well": "大口径井点",
    "deep_well": "深井",
}

#: 旧版 mcPcpEnclosure 构造函数里的默认值：(深度阈值 m, 井距 m, 侧数)
PRECIPITATION_DEFAULTS: dict[str, tuple[float, float, float]] = {
    "wet_soil": (0.0, 0.0, 0.0),
    "light_well": (3.5, 1.2, 2.0),
    "jet_well": (6.0, 2.5, 2.0),
    "big_well": (10.0, 10.0, 2.0),
    "deep_well": (15.0, 20.0, 1.0),
}


def format_precipitation(elevation: float, gap: float, sides: float) -> str:
    """拼成库内存储格式；深度阈值 < 0 表示该井型不启用（旧版用 -1 表示）。"""
    return f"{elevation:g}|{gap:g}|{sides:g}"


def parse_precipitation(text: str | None, key: str = "") -> tuple[float, float, float]:
    """解析库内存储格式；``"-"`` 或空表示不启用（返回 -1 深度阈值）。"""
    default = PRECIPITATION_DEFAULTS.get(key, (0.0, 0.0, 0.0))
    if text is None or str(text).strip() in ("", "-"):
        return (-1.0, default[1], default[2])
    parts = str(text).split("|")
    try:
        elevation = float(parts[0])
    except (TypeError, ValueError):
        return (-1.0, default[1], default[2])
    gap = default[1]
    sides = default[2]
    if len(parts) >= 2:
        try:
            gap = float(parts[1])
        except (TypeError, ValueError):
            pass
    if len(parts) >= 3:
        try:
            sides = float(parts[2])
        except (TypeError, ValueError):
            pass
    return (elevation, gap, sides)


# --------------------------------------------------------------------------- #
# 工作面宽度 / 沟槽宽度表（旧版 mcPcpEnclosure.WorkWidth 与 GrooveB 两张同构表）
# --------------------------------------------------------------------------- #
#: work_width.kind：工作面宽度表
WIDTH_KIND_WORK = "work"
#: work_width.kind：沟槽宽度表（旧版 GrooveB）
WIDTH_KIND_GROOVE_B = "groove_b"

#: principle_enclosure.groove_width：沟槽宽度取值方式（旧版 GrooveWidth 枚举）
GROOVE_WIDTH_WORK = "WorkWidth"
GROOVE_WIDTH_B = "B"


# --------------------------------------------------------------------------- #
# 表
# --------------------------------------------------------------------------- #
class Meta(Base):
    """结构版本与时间戳（新建时写入，见 orm.base.create_database）。"""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")


class BasicInfo(Base):
    """工程基本信息（对应旧版 mcBasicInfo），单行表。"""

    __tablename__ = "basic_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    project_name: Mapped[str] = mapped_column(String(200), default="新建项目")
    project_index: Mapped[str] = mapped_column(String(100), default="001")
    author: Mapped[str] = mapped_column(String(100), default="")
    atlas_name: Mapped[str] = mapped_column(String(100), default=DEFAULT_ATLAS_NAME)


class Segment(Base):
    """标段（对应旧版 mcSegment）。"""

    __tablename__ = "segment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), default="新建标段")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    units: Mapped[list["Unit"]] = relationship(
        back_populates="segment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Unit.order_no",
    )


class Unit(Base):
    """单位工程（对应旧版 mcUnit）。"""

    __tablename__ = "unit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(
        ForeignKey("segment.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), default="新建单位工程")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    segment: Mapped[Segment] = relationship(back_populates="units")
    elements: Mapped[list["Element"]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Element.order_no",
    )


class Element(Base):
    """构件条目（对应旧版 mcElement 及其子类 mcE1~mcE6）。

    ``pe_name`` / ``pf_name`` 是旧版的 showPEname / showPFname：按名字引用原则，
    原则本体在 principle_enclosure / principle_foundation 表里。
    """

    __tablename__ = "element"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), index=True)
    category: Mapped[int] = mapped_column(Integer, default=CATEGORY_BURIED)
    name: Mapped[str] = mapped_column(String(200), default="")
    #: 埋深（m），字符串原文，可能是算式
    depth: Mapped[str] = mapped_column(String(100), default="0")
    #: 数量/长度（m），字符串原文，可能是算式
    amount: Mapped[str] = mapped_column(String(100), default="0")
    pe_name: Mapped[str] = mapped_column(String(200), default="")
    pf_name: Mapped[str] = mapped_column(String(200), default="")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    unit: Mapped[Unit] = relationship(back_populates="elements")
    pipes: Mapped[list["Pipe"]] = relationship(
        back_populates="element",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Pipe.id",
    )
    params: Mapped[list["ElementParam"]] = relationship(
        back_populates="element",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ElementParam.id",
    )


class ElementParam(Base):
    """构件扩展参数（如箱涵含钢量），key-value 便于扩展。"""

    __tablename__ = "element_param"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(100), default="")
    value: Mapped[str] = mapped_column(String(200), default="")

    element: Mapped[Element] = relationship(back_populates="params")


class Pipe(Base):
    """管道（对应旧版 mcPipe）：材质 / 管径(mm) / 含量。"""

    __tablename__ = "pipe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), index=True
    )
    mat: Mapped[str] = mapped_column(String(100), default="Ⅱ级混凝土管")
    #: 管径 mm（旧版为 double，图集查表按 mm 整数）
    dn: Mapped[int] = mapped_column(Integer, default=600)
    #: 含量，字符串原文（可写算式）
    content: Mapped[str] = mapped_column(String(100), default="1")

    element: Mapped[Element] = relationship(back_populates="pipes")


class PcpEnclosure(Base):
    """围护原则 PE（对应旧版 mcPcpEnclosure）。"""

    __tablename__ = "principle_enclosure"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), default="新围护原则")
    #: 是否砼基础
    con_found: Mapped[bool] = mapped_column(Boolean, default=True)
    #: 开挖土质
    excvt: Mapped[str] = mapped_column(String(50), default="Ⅲ类土")
    #: 基础角度 °（120 / 180 …）
    found_angle: Mapped[int] = mapped_column(Integer, default=120)
    #: 坞塝：管道下半 / 上半回填材料
    dock_l: Mapped[str] = mapped_column(String(50), default="中粗砂")
    dock_h: Mapped[str] = mapped_column(String(50), default="中粗砂")
    #: 管顶 50cm 以内回填材料
    cover50: Mapped[str] = mapped_column(String(50), default="中粗砂")
    #: 覆土材料
    cover: Mapped[str] = mapped_column(String(50), default="素土")
    #: 降水参数，列名即井型；值为 "elevation|gap|sides"（见 parse_precipitation）
    wet_soil: Mapped[str] = mapped_column(String(50), default="0|0|0")
    light_well: Mapped[str] = mapped_column(String(50), default="3.5|1.2|2")
    jet_well: Mapped[str] = mapped_column(String(50), default="6|2.5|2")
    big_well: Mapped[str] = mapped_column(String(50), default="10|10|2")
    deep_well: Mapped[str] = mapped_column(String(50), default="15|20|1")
    #: 沟槽宽度取值方式：WorkWidth 用工作面宽度表，B 用沟槽宽度表
    groove_width: Mapped[str] = mapped_column(String(20), default=GROOVE_WIDTH_WORK)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cushions: Mapped[list["EnclosureCushion"]] = relationship(
        back_populates="enclosure",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EnclosureCushion.order_no",
    )
    widths: Mapped[list["WorkWidth"]] = relationship(
        back_populates="enclosure",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkWidth.order_no",
    )


class EnclosureCushion(Base):
    """围护原则下的垫层 / 换填层（对应旧版 mcReplacement Cush）。

    旧版围护原则只带一层垫层，这里按列表实现，语义一致。
    """

    __tablename__ = "enclosure_cushion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enclosure_id: Mapped[int] = mapped_column(
        ForeignKey("principle_enclosure.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="中粗砂")
    #: 厚度 mm（旧版 mcReplacement.H 默认 200）
    h: Mapped[float] = mapped_column(Float, default=200.0)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    enclosure: Mapped[PcpEnclosure] = relationship(back_populates="cushions")


class WorkWidth(Base):
    """工作面宽度 / 沟槽宽度表（旧版按管材接口类型分组，管径 d0~d3000 每 100 一档）。"""

    __tablename__ = "work_width"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enclosure_id: Mapped[int] = mapped_column(
        ForeignKey("principle_enclosure.id", ondelete="CASCADE"), index=True
    )
    #: 管材接口类型名（图集表首列，如“承插式”“企口式”）
    pipe_type: Mapped[str] = mapped_column(String(100), default="")
    #: 管径 mm
    dn: Mapped[int] = mapped_column(Integer, default=0)
    #: 宽度 m
    width: Mapped[float] = mapped_column(Float, default=0.0)
    #: WIDTH_KIND_WORK / WIDTH_KIND_GROOVE_B
    kind: Mapped[str] = mapped_column(String(20), default=WIDTH_KIND_WORK)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    enclosure: Mapped[PcpEnclosure] = relationship(back_populates="widths")


class PcpFoundation(Base):
    """地基原则 PF（对应旧版 mcPcpFoundation）：换填层列表 + 特殊地基构件。"""

    __tablename__ = "principle_foundation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), default="新地基原则")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    replacements: Mapped[list["FoundationReplacement"]] = relationship(
        back_populates="foundation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FoundationReplacement.order_no",
    )
    components: Mapped[list["Component"]] = relationship(
        back_populates="foundation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Component.order_no",
    )


class FoundationReplacement(Base):
    """换填层（对应旧版 mcReplacement）。"""

    __tablename__ = "foundation_replacement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    foundation_id: Mapped[int] = mapped_column(
        ForeignKey("principle_foundation.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="中粗砂")
    #: 厚度 mm
    h: Mapped[float] = mapped_column(Float, default=200.0)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    foundation: Mapped[PcpFoundation] = relationship(back_populates="replacements")


class Component(Base):
    """特殊地基构件（对应旧版 mcComponent）：名称 + 描述公式，参数另存 component_param。"""

    __tablename__ = "component"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    foundation_id: Mapped[int] = mapped_column(
        ForeignKey("principle_foundation.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="")
    #: 描述公式（旧版 mcComponent.DiscribeFmla）
    formula: Mapped[str] = mapped_column(Text, default="")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    foundation: Mapped[PcpFoundation] = relationship(back_populates="components")
    params: Mapped[list["ComponentParam"]] = relationship(
        back_populates="component",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ComponentParam.id",
    )


class ComponentParam(Base):
    """构件参数。

    对应旧版 mcComponent.param：key 为参数字母（A~Z、FA~FZ 为工程量公式、ZA~ZZ），
    value 保持旧版 ``"显示名|表达式"`` 的写法，便于与旧数据一一对应。
    """

    __tablename__ = "component_param"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component_id: Mapped[int] = mapped_column(
        ForeignKey("component.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(10), default="")
    value: Mapped[str] = mapped_column(Text, default="")

    component: Mapped[Component] = relationship(back_populates="params")


class Price(Base):
    """单价字典（汇总页用，旧版 mcDataCarrier.price）。"""

    __tablename__ = "price"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(300), default="", index=True)
    value: Mapped[float] = mapped_column(Float, default=0.0)
