"""工作库（临时 SQLite）表结构。工程文件 `.stn` 的 JSON 数据体与这些表一一对应
（见 services/stn_codec.py）。

语义照搬旧版 C#（工程 → 标段 → 单位工程 → 构件 → 管道），实现改为规范化的关系表：
原则（围护 PE / 地基 PF）独立成表，可被多个构件按名字引用。

通用约定：

* ``depth`` / ``amount`` / ``content`` 存字符串原文（可能是 ``2.5+0.3``），
  求值结果不落库，运行时用 :mod:`app.core.evaluator` 算，避免两份数据不一致；
* 所有表带 ``order_no`` 保序；外键 ``ondelete="CASCADE"``，删父行级联清理子行；
* 写操作后由 :func:`app.services.project_io.commit` 落盘。
"""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.version import DEFAULT_ATLAS_NAME
from app.core.models.base import Base

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
CATEGORY_STRUCTURE = 7  # 构筑物（附属构筑物）   mcE7

CATEGORY_NAMES: dict[int, str] = {
    CATEGORY_NONE: "",
    CATEGORY_BURIED: "直埋管道",
    CATEGORY_ENCASED: "包封埋管",
    CATEGORY_BOX_CULVERT: "箱涵",
    CATEGORY_JACKING: "顶管",
    CATEGORY_PULLING: "牵引管",
    CATEGORY_GALLERY: "管廊",
    CATEGORY_STRUCTURE: "构筑物",
}

#: 下拉框顺序（不含“空”类别；构筑物对应旧版 typeDic 最后一项）
CATEGORY_CHOICES: tuple[int, ...] = (
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    CATEGORY_BOX_CULVERT,
    CATEGORY_JACKING,
    CATEGORY_PULLING,
    CATEGORY_GALLERY,
    CATEGORY_STRUCTURE,
)

#: 工程量单位：旧版 mcE1~mcE6 的 unit 字段都是 "m"，mcE7 为 "个"
UNIT_BY_CATEGORY: dict[int, str] = {
    CATEGORY_NONE: "",
    CATEGORY_BURIED: "m",
    CATEGORY_ENCASED: "m",
    CATEGORY_BOX_CULVERT: "m",
    CATEGORY_JACKING: "m",
    CATEGORY_PULLING: "m",
    CATEGORY_GALLERY: "m",
    CATEGORY_STRUCTURE: "个",
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


#: 围护做法"围护类型"列的多级围护选项（旧版 mcEnclosure.MultiScpntTxt）
MULTI_LEVEL_TEXT = "多级围护"

#: 主表格「沟槽围护原则」下拉的左右分设占位项（对应 1.0 多原则时代的
#: showPEname 占位机制）：pe_name 存该文本时读 pe_left_name / pe_right_name，
#: 不按名解析原则（resolve_element_principles 跳过占位名）
LR_PE_TEXT = "左右分设"

# --------------------------------------------------------------------------- #
# 合槽父节点的两个整槽选项（主表格挖填降水 / 面宽两列的下拉，v3.1）
# --------------------------------------------------------------------------- #
#: 回填分层方式：每条构件按自己的回填分层界面计算（现状口径）
BACKFILL_INDEPENDENT = "独立回填标高"
#: 回填分层方式：每层取组内各构件该层顶的最浅标高作为所有构件的界面
BACKFILL_UNIFIED = "统一回填标高"
#: 断面划分方式：相邻面分界在深侧起坡点（现状口径）
SPLIT_SLOPE_POINT = "起坡点分隔"
#: 断面划分方式：分界取相邻两构件水平中心连线中点的虚拟竖直线
SPLIT_CENTER_LINE = "管中心分隔"
#: 断面划分方式：分界取相邻构件"间距计算起始点"水平中点的虚拟竖直线
#: （砼基础管道取基础共享侧边线、砂基础管道取管外皮共享侧切线、
#:   混凝土结构取结构本体共享侧最外侧边线）
SPLIT_SPACING_MID = "间距平分分隔"

#: 合槽回填分层方式的下拉项（按序显示）
BACKFILL_MODES = (BACKFILL_INDEPENDENT, BACKFILL_UNIFIED)
#: 合槽断面划分方式的下拉项（按序显示）
SPLIT_MODES = (SPLIT_SLOPE_POINT, SPLIT_CENTER_LINE, SPLIT_SPACING_MID)
#: 旧版措辞（"起坡点分割"）→ 现值的兼容映射
SPLIT_MODE_ALIASES = {"起坡点分割": SPLIT_SLOPE_POINT}


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
    """结构版本与时间戳（建工作库时写入，见 orm.base.create_working_database）。"""

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
    groups: Mapped[list["TrenchGroup"]] = relationship(
        back_populates="unit",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TrenchGroup.order_no",
    )


class Element(Base):
    """构件条目（对应旧版 mcElement 及其子类 mcE1~mcE7）。

    ``pe_name`` / ``pf_name`` 按名字引用原则，原则本体在
    principle_enclosure / principle_foundation 表里；降水 / 面宽原则
    （``pp_name`` / ``pw_name``）同级、同样按名字引用。

    左右分设（v3）：``pe_name`` 存 :data:`LR_PE_TEXT` 占位时为分设模式，
    左右两条围护原则按名引用（``pe_left_name`` / ``pe_right_name``，两列
    皆空 = 普通单原则模式，现状语义）；挖填类型在挖填降水原则、管道基础在
    地基原则里，均与左右围护无关，故不再需要取侧字段；左右支撑是否参与计算
    由 ``support_left`` / ``support_right`` 勾选。

    合槽编组（v3）：``group_id`` 指向所属合槽组（父节点），组内 ``order_no``
    即沟槽从左到右的顺序；父节点本体是 :class:`TrenchGroup` 行，不持有工程量。
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
    #: 降水原则 / 面宽原则（与 pe/pf 同级、按名字引用，本体在 principle_precipitation /
    #: principle_width 表里；旧版这两项挂在围护原则下，v4 起独立）
    pp_name: Mapped[str] = mapped_column(String(200), default="")
    pw_name: Mapped[str] = mapped_column(String(200), default="")
    #: 左侧 / 右侧围护原则名（左右分设模式；两列皆空 = 普通单原则模式）
    pe_left_name: Mapped[str] = mapped_column(String(200), default="")
    pe_right_name: Mapped[str] = mapped_column(String(200), default="")
    #: 左侧 / 右侧支撑（类别为“支撑”的公式）是否参与计算（左右分设模式）
    support_left: Mapped[bool] = mapped_column(Boolean, default=True)
    support_right: Mapped[bool] = mapped_column(Boolean, default=True)
    #: 所属合槽组（父节点）；空 = 独立构件
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("trench_group.id", ondelete="CASCADE"), index=True, nullable=True
    )
    #: 来源（旧版主表格“来源”列，构件库插入时记录模板出处）
    source: Mapped[str] = mapped_column(String(200), default="")
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
    #: 图集候选参数（"候选参数列"，v9；只有直埋构件用，见 ElementAtlasCandidate）
    atlas_candidates: Mapped[list["ElementAtlasCandidate"]] = relationship(
        back_populates="element",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ElementAtlasCandidate.order_no",
    )
    #: 附属构筑物的工程量行（mcE7 的“类别|项目|单位”三段参数，v5 起独立成表）
    quantities: Mapped[list["ElementQuantity"]] = relationship(
        back_populates="element",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ElementQuantity.order_no",
    )
    #: 所属合槽组（父节点）；None = 独立构件
    group: Mapped["TrenchGroup | None"] = relationship(
        back_populates="members",
    )


class TrenchGroup(Base):
    """合槽组（父节点行，v3）。

    多选构件「合槽编组」后插入主表格的一行：不持有任何工程量（全部工程量
    按横向区间切到子构件名下，父节点仅作合计视图）。父节点也**不持有围护 /
    面宽原则**（``pe_name`` / ``pw_name`` 恒空，界面显示 "-"）：左边坡取首
    构件左原则，右边坡取末构件右原则，每条构件的工作面宽按自己的面宽原则
    确定；相邻等深两侧强制 "-"，异深时深侧按所选原则向浅槽底放坡。

    父节点持有两个整槽口径的选项（主表格挖填降水 / 面宽两列的下拉）：

    * ``backfill_mode`` 回填分层方式：``独立回填标高``（每条构件按自己的
      回填分层界面计算，现状口径）或 ``统一回填标高``（每条构件先各自算出
      每一层的层顶标高，再逐层统筹取组内最浅标高作为所有构件该层的界面）；
    * ``split_mode`` 断面划分方式：``起坡点分隔``（相邻面的分界在深侧起坡
      点，现状口径）、``管中心分隔``（分界取相邻两构件水平中心连线的中点
      的虚拟竖直线）或 ``间距平分分隔``（分界取相邻构件"间距计算起始点"
      ——砼基础管道的基础共享侧边线 / 砂基础管道的管外皮共享侧切线 /
      混凝土结构的本体共享侧最外侧边线——的水平中点）。

    ``amount`` 是父节点唯一持有的数据：合槽的**计算长度 L_组**，子构件数量
    强制与之一致（改父节点即同步全部子构件）；父节点埋深无效（界面显示 "-"），
    组内槽深全部由子构件自己的埋深 + 基础推导。

    组员的左右顺序 = 组内 ``Element.order_no``（从上到下 = 从左到右）；
    组员引用失效（原则被删）时回退库中第一条，与构件的解析规则一致。
    """

    __tablename__ = "trench_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("unit.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), default="合槽组")
    #: 合槽数量（计算长度 L_组，字符串原文可写算式）；子构件 amount 强制等于此值
    amount: Mapped[str] = mapped_column(String(100), default="")
    #: 恒空（父节点不选围护原则；字段保留仅为旧工程兼容）
    pe_name: Mapped[str] = mapped_column(String(200), default="")
    #: 恒空（父节点不选工作面宽原则；字段保留仅为旧工程兼容）
    pw_name: Mapped[str] = mapped_column(String(200), default="")
    #: 回填分层方式（挖填降水列的下拉）：独立回填标高 / 统一回填标高
    backfill_mode: Mapped[str] = mapped_column(String(50), default=BACKFILL_INDEPENDENT)
    #: 断面划分方式（面宽列的下拉）：起坡点分隔 / 管中心分隔 / 间距平分分隔
    split_mode: Mapped[str] = mapped_column(String(50), default=SPLIT_SLOPE_POINT)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    unit: Mapped[Unit] = relationship(back_populates="groups")
    members: Mapped[list["Element"]] = relationship(
        back_populates="group",
        foreign_keys="Element.group_id",
        order_by="Element.order_no",
        passive_deletes=True,
    )


class ElementParam(Base):
    """构件扩展参数（key-value 便于扩展，如箱涵含钢量、图集壁厚覆盖）。

    v5 起参数名与单位分两列：``key`` 只存参数名（旧版尾部“ 单位”已拆出，
    见 :mod:`app.core.param_naming`），``unit`` 存单位（空 = 无单位，
    如构筑物的名称 / 单位行）；``value`` 保持字符串原文，可写算式。
    """

    __tablename__ = "element_param"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(100), default="")
    unit: Mapped[str] = mapped_column(String(50), default="")
    value: Mapped[str] = mapped_column(String(200), default="")

    element: Mapped[Element] = relationship(back_populates="params")


class ElementQuantity(Base):
    """附属构筑物的工程量行（对应旧版 mcE7 的“类别|项目|单位”三段参数）。

    v5 起独立成表；界面上在详情面板“工程量”页编辑，行可增删。
    计算时每行输出一条工程量“类别|项目|单位”，``value`` 为值原文（可写算式），
    随构件数量（amount）放大。
    """

    __tablename__ = "element_quantity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), index=True
    )
    #: 工程量类别（如“构筑物”）
    category: Mapped[str] = mapped_column(String(100), default="")
    #: 项目名称（如“垫层”）
    item: Mapped[str] = mapped_column(String(100), default="")
    unit: Mapped[str] = mapped_column(String(50), default="")
    value: Mapped[str] = mapped_column(String(200), default="0")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    element: Mapped[Element] = relationship(back_populates="quantities")


class Pipe(Base):
    """管道（对应旧版 mcPipe）：管材类别 / 材质 / 管径(mm) / 含量 / 壁厚。

    ``cat`` 是计算的唯一依据（面宽表行、图集表分流、断面图是否砼基础、
    包封扣管位取壁厚），由构件库资产快照写入、允许用户改；``mat`` 只作
    描述性材质文字（构件规格、设备材料表），不参与任何计算判断。
    """

    __tablename__ = "pipe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), index=True
    )
    #: 管材类别（宽度表行名，见 app.core.pipe_category.PIPE_CATEGORIES）；
    #: 空 = 按 mat 折算一次（v8 之前的工程文件由迁移回填）
    cat: Mapped[str] = mapped_column(String(50), default="")
    #: 材质文字（如“球墨铸铁管 K9”）：只用于构件规格与设备材料表，不参与计算
    mat: Mapped[str] = mapped_column(String(100), default="Ⅱ级混凝土管")
    #: 管径 mm（旧版为 double，图集查表按 mm 整数）
    dn: Mapped[int] = mapped_column(Integer, default=600)
    #: 含量，字符串原文（可写算式）
    content: Mapped[str] = mapped_column(String(100), default="1")
    #: 管道壁厚 mm（用户覆盖值；空 = 按图集自动，并参与计算自动回退，
    #: 见 resolve_atlas 的覆盖处理。v5 起在详情面板“管道壁厚”列直接编辑）
    t: Mapped[float | None] = mapped_column(Float, nullable=True)

    element: Mapped[Element] = relationship(back_populates="pipes")

    @property
    def pipe_category(self) -> str:
        """计算用管材类别（空值按材质折算，不写库）。"""
        from app.core.pipe_category import normalize_category

        return normalize_category(self.cat, mat=self.mat)


class ElementAtlasCandidate(Base):
    """直埋构件的图集候选参数（"候选参数列"，构件库一次性快照，用户可改）。

    每行 = 一个"基础形式 × 角度"组合的 (a, C1, C2)，mm；值 None 表示图集
    该组合没有数据（如砼管**砼基础表没有 150° 行**）。混凝土管 8 组都用，
    其他管材的 con/plain 两组值相同、界面只展示"不采用混凝土基础"的 4 列。

    参数值（工作面加宽 / 垫层厚 / 基础厚三行参数）按当前地基原则的
    ``con_found + found_angle`` 从这里自动选（:func:`unit_vm.match_atlas_candidates`）；
    地基原则 / 管材类别变化时自动重新匹配，但候选行本身永不自动改写。
    """

    __tablename__ = "element_atlas_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    element_id: Mapped[int] = mapped_column(
        ForeignKey("element.id", ondelete="CASCADE"), index=True
    )
    #: 是否采用混凝土基础（对应地基原则 con_found）
    con_found: Mapped[bool] = mapped_column(Boolean, default=True)
    #: 基础角度 °（90 / 120 / 150 / 180）
    angle: Mapped[int] = mapped_column(Integer, default=120)
    #: 管道壁厚 mm（图集 t 列）；None = 图集该组合无值
    t: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: 工作面加宽 mm；None = 图集该组合无值
    a: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: 垫层厚 mm；None = 图集该组合无值
    c1: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: 基础厚 mm；None = 图集该组合无值
    c2: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    element: Mapped[Element] = relationship(back_populates="atlas_candidates")


class PcpEnclosure(Base):
    """围护原则 PE（对应旧版 mcPcpEnclosure），只保留围护做法相关内容。

    1.0 里围护原则囊括降水、工作面/沟槽宽度表、挖填材质、管道基础等大量参数；
    2.0 逐项拆出：降水（并入:class:`PcpPrecipitation`）、工作面/沟槽宽度表
    （:class:`PcpWidth`）、管道基础与垫层（:class:`PcpFoundation`）、
    挖填类型（并入:class:`PcpPrecipitation`）都已独立成原则或挂到别的原则下。
    本表只剩名称与围护做法列表（``works``）。
    """

    __tablename__ = "principle_enclosure"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), default="新围护原则")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    works: Mapped[list["EnclosureWork"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EnclosureWork.order_no",
        primaryjoin="PcpEnclosure.id == EnclosureWork.enclosure_id",
    )

    def works_sorted(self) -> list["EnclosureWork"]:
        """做法列表（按 order_no）；计算时按此顺序取最后一个 min_depth ≤ 深度的做法。"""
        return sorted(self.works, key=lambda work: (work.order_no, work.id))


class PcpPrecipitation(Base):
    """挖填降水原则（旧版降水参数在围护原则里，v4 起独立成原则，与 PE/PF 同级）。

    除降水井型参数外，v10 起还接收原本挂在围护原则里的**挖填类型**
    （开挖土质与回填材质），这两组参数与左右围护不一致无关，独立成原则后
    不必再区分取左 / 取右。
    """

    __tablename__ = "principle_precipitation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), default="新挖填降水原则")
    #: 降水参数，列名即井型；值为 "elevation|gap|sides"（见 parse_precipitation）
    wet_soil: Mapped[str] = mapped_column(String(50), default="0|0|0")
    light_well: Mapped[str] = mapped_column(String(50), default="3.5|1.2|2")
    jet_well: Mapped[str] = mapped_column(String(50), default="6|2.5|2")
    big_well: Mapped[str] = mapped_column(String(50), default="10|10|2")
    deep_well: Mapped[str] = mapped_column(String(50), default="15|20|1")
    #: 开挖土质（旧版 PE.excvt）
    excvt: Mapped[str] = mapped_column(String(50), default="Ⅲ类土")
    #: 坞塝：管道下半 / 上半回填材料
    dock_l: Mapped[str] = mapped_column(String(50), default="中粗砂")
    dock_h: Mapped[str] = mapped_column(String(50), default="中粗砂")
    #: 管顶 50cm 以内回填材料
    cover50: Mapped[str] = mapped_column(String(50), default="中粗砂")
    #: 覆土材料
    cover: Mapped[str] = mapped_column(String(50), default="素土")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PcpWidth(Base):
    """面宽原则（旧版工作面宽度/沟槽宽度表在围护原则里，v4 起独立成原则）。"""

    __tablename__ = "principle_width"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), default="新面宽原则")
    #: 沟槽宽度取值方式：WorkWidth 用工作面宽度表，B 用沟槽宽度表
    groove_width: Mapped[str] = mapped_column(String(20), default=GROOVE_WIDTH_WORK)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    items: Mapped[list["WidthItem"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WidthItem.order_no",
    )


class WidthItem(Base):
    """工作面宽度 / 沟槽宽度表行（旧版按管材接口类型分组，管径 d0~d3000 每 100 一档）。"""

    __tablename__ = "principle_width_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    width_id: Mapped[int] = mapped_column(
        ForeignKey("principle_width.id", ondelete="CASCADE"), index=True
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


class PcpFoundation(Base):
    """地基原则 PF（对应旧版 mcPcpFoundation）。

    内容：管道基础（砼基础开关 / 基础角度 / 垫层） + 换填层列表 + 特殊地基构件。
    其中管道基础与垫层原本挂在围护原则下，v10 起移到本表（与左右围护不一致
    无关，独立成一条口径）。
    """

    __tablename__ = "principle_foundation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), default="新地基原则")
    #: 是否砼基础（旧版 PE.con_found）
    con_found: Mapped[bool] = mapped_column(Boolean, default=True)
    #: 基础角度 °（旧版 PE.found_angle；120 / 180 …）
    found_angle: Mapped[int] = mapped_column(Integer, default=120)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cushions: Mapped[list["FoundationCushion"]] = relationship(
        back_populates="foundation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FoundationCushion.order_no",
    )
    replacements: Mapped[list["FoundationReplacement"]] = relationship(
        back_populates="foundation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FoundationReplacement.order_no",
    )
    #: 特殊地基构件（旧版 mcPcpFoundation.Foundation，至多一个）
    components: Mapped[list["Component"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Component.order_no",
        primaryjoin="PcpFoundation.id == Component.foundation_id",
    )


class FoundationCushion(Base):
    """地基原则下的垫层（对应旧版 mcReplacement Cush）。

    旧版围护原则只带一层垫层，这里按列表实现，语义一致；v10 起随管道基础
    一起挂到地基原则（PF）下。
    """

    __tablename__ = "foundation_cushion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    foundation_id: Mapped[int] = mapped_column(
        ForeignKey("principle_foundation.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="中粗砂")
    #: 厚度 mm（旧版 mcReplacement.H 默认 200）
    h: Mapped[float] = mapped_column(Float, default=200.0)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    foundation: Mapped[PcpFoundation] = relationship(back_populates="cushions")


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
    """构件（对应旧版 mcComponent）：名称 + 描述公式，参数另存 component_param。

    一个构件挂在三种所有者之一上（对应旧版 mcComponent 被三处复用）：

    * ``foundation_id`` —— 地基原则的特殊地基构件（PF.Foundation）；
    * ``enclosure_level_id`` —— 围护做法某一级的围护构件（mcEclsCpnt.Cpnt）；
    * ``enclosure_work_id`` —— 围护做法的止水构件（mcEnclosure.WSCpnt）。
    """

    __tablename__ = "component"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    foundation_id: Mapped[int | None] = mapped_column(
        ForeignKey("principle_foundation.id", ondelete="CASCADE"), index=True, nullable=True
    )
    enclosure_level_id: Mapped[int | None] = mapped_column(
        ForeignKey("enclosure_level.id", ondelete="CASCADE"), index=True, nullable=True
    )
    enclosure_work_id: Mapped[int | None] = mapped_column(
        ForeignKey("enclosure_work.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), default="")
    #: 描述公式（旧版 mcComponent.DiscribeFmla）
    formula: Mapped[str] = mapped_column(Text, default="")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    params: Mapped[list["ComponentParam"]] = relationship(
        back_populates="component",
        cascade="all, delete-orphan",
        order_by="ComponentParam.id",
    )


class ComponentParam(Base):
    """构件参数。

    对应旧版 mcComponent.param：key 为参数字母（A~Z 为一般参数，FA~FZ 为
    构件公式——围护 / 支撑只由显示名类别区分），
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


class EnclosureWork(Base):
    """围护做法（对应旧版 mcEnclosure）：按 min_depth 选用的做法，含多级围护与止水构件。

    旧版围护原则 PE 下是做法列表，计算时 ChoiceEcls(沟槽深度) 取最后一个
    min_depth <= 深度 的做法；做法内是若干级围护构件（多级围护）+ 一个止水构件。
    """

    __tablename__ = "enclosure_work"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enclosure_id: Mapped[int] = mapped_column(
        ForeignKey("principle_enclosure.id", ondelete="CASCADE"), index=True
    )
    #: 最小适用埋深 m（旧版 MinDepth）
    min_depth: Mapped[float] = mapped_column(Float, default=0.0)
    #: 做法类别名（旧版 eCpntCat：库构件名或“多级围护”）
    cpnt_cat: Mapped[str] = mapped_column(String(100), default="")
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    levels: Mapped[list["EnclosureLevel"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EnclosureLevel.order_no",
        primaryjoin="EnclosureWork.id == EnclosureLevel.work_id",
    )
    #: 止水构件（旧版 WSCpnt，至多一个）
    waterstops: Mapped[list["Component"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Component.order_no",
        primaryjoin="EnclosureWork.id == Component.enclosure_work_id",
    )


class EnclosureLevel(Base):
    """围护做法的一级构件（对应旧版 mcEclsCpnt）。

    ``h`` 为该级固定高度 m；``h < 0`` 表示与其它负值级均分剩余深度（旧版约定）。
    """

    __tablename__ = "enclosure_level"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(
        ForeignKey("enclosure_work.id", ondelete="CASCADE"), index=True
    )
    #: 库构件名（旧版 name，指向构件库 Ei 里的条目）
    name: Mapped[str] = mapped_column(String(100), default="")
    h: Mapped[float] = mapped_column(Float, default=-1.0)
    #: 平台宽度 m（旧版 stepWidth）
    step_width: Mapped[float] = mapped_column(Float, default=1.0)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: 该级的围护构件（旧版 Cpnt）
    components: Mapped[list["Component"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Component.order_no",
        primaryjoin="EnclosureLevel.id == Component.enclosure_level_id",
    )


class Price(Base):
    """单价字典（汇总页用，旧版 mcDataCarrier.price）。"""

    __tablename__ = "price"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(300), default="", index=True)
    value: Mapped[float] = mapped_column(Float, default=0.0)
