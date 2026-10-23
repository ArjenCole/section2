"""管材类别：管道在“面宽原则宽度表”里的行归属，以及断面图 / 图集分流的唯一依据。

旧版（1.0）没有这个字段：每次计算都把管材名称（``mcPipe.Mat``）拿去做字符串
包含判断（``"混凝土" in mat`` …），既无法由用户纠正，也让同一份数据在不同
版本的代码里给出不同结果。新版把它固化成管道行上的一个字段：

* **存什么**：宽度表的四类行名（见 :data:`PIPE_CATEGORIES`），不是自由文本；
* **谁来填**：构件库模板自带的类别（生成资产时由管材名称折算一次并固化），
  用户可在详情面板改；
* **谁读它**：面宽匹配（直埋取第一根管的类别 + 管径）、图集表分流、
  断面图是否画混凝土基础矩形、包封砼扣管位取壁厚。

管材名称（:class:`app.core.models.models.Pipe` 的 ``mat``）保留为描述性文字
（构件规格、设备材料表用），**不再参与任何计算判断**。

映射规则刻意与旧版 ``resolve_atlas`` 的 elif 链保持同一优先级，避免老工程
翻新后算量漂移：混凝土优先（``钢筋混凝土钢承口管`` 归混凝土而非金属），
化学建材优先于金属（``钢带增强聚乙烯(PE)管`` 归化学建材而非钢管）。
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# 四类管材（宽度表行）：管材面板下拉的候选，也是 Pipe.cat 的合法取值
# --------------------------------------------------------------------------- #
PIPE_CAT_CONCRETE_RIGID = "混凝土管-刚性接口"
PIPE_CAT_CONCRETE_FLEX = "混凝土管-柔性接口"
PIPE_CAT_METAL = "金属类管道"
PIPE_CAT_CHEMICAL = "化学建材管道"

PIPE_CATEGORIES: tuple[str, ...] = (
    PIPE_CAT_CONCRETE_RIGID,
    PIPE_CAT_CONCRETE_FLEX,
    PIPE_CAT_METAL,
    PIPE_CAT_CHEMICAL,
)

PIPE_CAT_DEFAULT = PIPE_CAT_CONCRETE_RIGID

# --------------------------------------------------------------------------- #
# 非管材的宽度表行：由构件类别固定取，不读管道行上的管材类别
# --------------------------------------------------------------------------- #
WIDTH_ROW_ENCASED = "包封埋管"
WIDTH_ROW_BOX_GALLERY = "箱涵-管廊"

#: 宽度表全部行（含上面两行非管材行）；保存/导出时接受的全集
WIDTH_PIPE_TYPES: tuple[str, ...] = PIPE_CATEGORIES + (WIDTH_ROW_ENCASED, WIDTH_ROW_BOX_GALLERY)

#: 混凝土类（断面图画砼基础矩形、图集查砼管表）
CONCRETE_PIPE_CATEGORIES: tuple[str, ...] = (
    PIPE_CAT_CONCRETE_RIGID,
    PIPE_CAT_CONCRETE_FLEX,
)

# --------------------------------------------------------------------------- #
# 管材名称 → 类别（构件库资产生成时用一次，之后不再看名称）
# --------------------------------------------------------------------------- #
#: 混凝土类关键词（先判，避免“钢筋混凝土钢承口管”被当成钢管）
_CONCRETE_HINTS: tuple[str, ...] = ("混凝土", "砼")

#: 化学建材类关键词（先于金属判，避免“钢带增强聚乙烯”被当成钢管）
_CHEMICAL_HINTS: tuple[str, ...] = (
    "HDPE",
    "hdpe",
    "PVC",
    "pvc",
    "PE",
    "pe",
    "聚乙烯",
    "聚氯乙烯",
    "BWFRP",
    "BWFRP".lower(),
    "纤维编绕",
    "玻璃钢",
    "夹砂",
)

#: 金属类关键词
_METAL_HINTS: tuple[str, ...] = ("球墨", "球铁", "铸铁", "钢管", "钢带", "不锈钢")


def category_of_mat(mat: str) -> str:
    """按管材名称折算管材类别（仅在构件库资产生成 / 库外构件补值用）。

    >>> category_of_mat("Ⅱ级混凝土管")
    '混凝土管-刚性接口'
    >>> category_of_mat("球墨铸铁管 K9")
    '金属类管道'
    >>> category_of_mat("钢带增强聚乙烯(PE)管")
    '化学建材管道'
    >>> category_of_mat("钢筋混凝土钢承口管")
    '混凝土管-刚性接口'
    >>> category_of_mat("")
    '化学建材管道'
    """
    text = (mat or "").strip()
    if not text:
        return PIPE_CAT_CHEMICAL
    if any(hint in text for hint in _CONCRETE_HINTS):
        # 旧版无法从名称区分柔性接口（承插式橡胶圈），一律按刚性取宽度表
        return PIPE_CAT_CONCRETE_RIGID
    if any(hint in text for hint in _CHEMICAL_HINTS):
        return PIPE_CAT_CHEMICAL
    if any(hint in text for hint in _METAL_HINTS):
        return PIPE_CAT_METAL
    # 兜底：旧版把未知材质当化学建材（宽度表按化学建材取，图集不查）
    return PIPE_CAT_CHEMICAL


def normalize_category(value: str | None, *, mat: str = "") -> str:
    """把任意输入收敛成合法类别：空值 / 非法值按 ``mat`` 折算，再兜底刚性接口。"""
    text = (value or "").strip()
    if text in PIPE_CATEGORIES:
        return text
    return category_of_mat(mat) if mat else PIPE_CAT_DEFAULT


def is_concrete(cat: str | None, *, mat: str = "") -> bool:
    """是否混凝土管（断面图画砼基础矩形、图集查砼管表）。"""
    return normalize_category(cat, mat=mat) in CONCRETE_PIPE_CATEGORIES


def width_row_for(element_category: int, pipe_cat: str | None, *, mat: str = "") -> str:
    """构件该取哪一行宽度表。

    直埋管道是唯一要看管材类别的构件（按第一根管）；包封埋管 / 箱涵 / 管廊
    的断面由构件自身参数决定，宽度表行固定；顶管 / 牵引管不算沟槽，不取值。
    """
    from app.core.models.models import (
        CATEGORY_BOX_CULVERT,
        CATEGORY_BURIED,
        CATEGORY_ENCASED,
        CATEGORY_GALLERY,
    )

    if int(element_category or 0) == CATEGORY_BURIED:
        return normalize_category(pipe_cat, mat=mat)
    if int(element_category or 0) == CATEGORY_ENCASED:
        return WIDTH_ROW_ENCASED
    if int(element_category or 0) in (CATEGORY_BOX_CULVERT, CATEGORY_GALLERY):
        return WIDTH_ROW_BOX_GALLERY
    return normalize_category(pipe_cat, mat=mat)


def width_dn_for(element_category: int, first_dn: int) -> int:
    """宽度表查表用的管径：直埋按第一根管的管径，其余构件按 0（旧版语义）。"""
    from app.core.models.models import CATEGORY_BURIED

    return int(first_dn) if int(element_category or 0) == CATEGORY_BURIED else 0
