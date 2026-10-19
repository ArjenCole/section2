"""构件参数“参数名 / 单位”的拆分与拼接。

旧版 C# 的构件参数（mcElement.Li）把单位和名字写在同一段文本里
（如 ``净宽 m(含内壁厚度)``、``内壁 道``）；新版拆成两列存储，
``element_param.key`` 只存参数名、``unit`` 列存单位。本模块：

* :func:`split_param_key` —— 旧键 → (参数名, 单位)，迁移与构件库共用；
* :func:`join_param_key` —— (参数名, 单位) → 旧键（.stn 导出仍要旧格式）；
* 图集参数（工作面加宽 a / 垫层厚 C1 / 基础厚 C2）的固定名称与单位，
  计算引擎按这两个名字取用户覆盖值，
  :data:`ATLAS_PARAM_CATEGORIES` 决定各构件类别显示哪几行。

C1 = 垫层厚 / C2 = 基础厚的依据（图集 06MS201-1 的管道基础断面图，
旧版 mcAtlas 读的 ``C1`` / ``C2`` 两列就是图上的这两个竖向尺寸）：

* **C1** 是管底以下那一层基础的厚度（垫层）：1.0 里沟槽底就在管底以下 C1 处
  （``mscGroove.Cal``：``槽深 = 埋深 + 换填厚 + t + C1``），图集也把 C1
  当作分开浇注的底层（04S516：“C1、C2 分开浇注时，C1 部分表面要求凿毛”）；
* **C2** 是管底以上包裹管道、到基础包角（120° / 180°）的那部分基础厚度
  （管座）：数值上等于管外半径的弓高 ``R(1−cos(包角/2))``，1.0 里
  ``垫层`` 层高 = C1 + C2、``坞膀下半`` 层高 = 管半径 + t − C2。
  这个量只对圆管有意义：直埋管道按图集行取；包封埋管 / 箱涵 / 管廊垫层
  以上没有包角管座基础，恒为 0（不显示、不可改）。
"""

from __future__ import annotations

import re

from app.core.models.models import (
    CATEGORY_BOX_CULVERT,
    CATEGORY_BURIED,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
)

#: 管道工作面加宽（图集工作面宽度表 a 列），单位 mm
PARAM_A_NAME = "工作面加宽"
#: 管道垫层厚（图集 C1 列：管底以下的基础垫层），单位 mm
PARAM_C1_NAME = "垫层厚"
#: 管道（管）基厚（图集 C2 列：管底以上包裹管道的基础），单位 mm
PARAM_C2_NAME = "基础厚"

#: 图集约定参数 → 单位；这三行参数名/单位固定（锁定），只允许改值
ATLAS_PARAM_NAMES: tuple[tuple[str, str], ...] = (
    (PARAM_A_NAME, "mm"),
    (PARAM_C1_NAME, "mm"),
    (PARAM_C2_NAME, "mm"),
)

#: 各类别显示（并允许用户改值）的图集参数行（按 图集参数名 排列）：
#:
#: * **直埋管道**：工作面加宽 / 垫层厚 / 基础厚 三行都显示，默认值按图集
#:   （空值 = 自动按图集，界面灰字显示图集值），用户可改；
#: * **包封埋管 / 箱涵 / 管廊**：垫层以上没有包角管座基础，基础厚恒为 0
#:   （不显示、不可改），只显示工作面加宽 / 垫层厚（默认按软件约定
#:   a=100、C1=100，用户可改）；
#: * **顶管 / 牵引管**：只算管材，三行都不显示。
ATLAS_PARAM_CATEGORIES: dict[int, tuple[str, ...]] = {
    CATEGORY_BURIED: (PARAM_A_NAME, PARAM_C1_NAME, PARAM_C2_NAME),
    CATEGORY_ENCASED: (PARAM_A_NAME, PARAM_C1_NAME),
    CATEGORY_BOX_CULVERT: (PARAM_A_NAME, PARAM_C1_NAME),
    CATEGORY_GALLERY: (PARAM_A_NAME, PARAM_C1_NAME),
}

#: 引擎默认扩展参数 → 单位（_DEFAULT_PARAMS 的键；新建/类别切换补行时用）
DEFAULT_PARAM_UNITS: dict[str, str] = {
    "包封宽": "m",
    "包封高": "m",
    "净宽(含内壁厚度)": "m",
    "净高": "m",
    "外包宽": "m",
    "外包高": "m",
    "底板厚": "mm",
    "顶板厚": "mm",
    "外壁厚": "mm",
    "内壁厚": "mm",
    "内壁": "道",
    "含钢量": "kg/m3",
}

#: 附属构筑物专有：前两行固定为名称 / 单位（值影响主表格规格、单位列）
STRUCTURE_NAME_PARAM = "名称"
STRUCTURE_UNIT_PARAM = "单位"

#: 带 ASCII 前缀的单位（如 m、mm、m3/m、kg/m3）；后跟的括注属于参数名的一部分
_UNIT_PATTERN = re.compile(r"([A-Za-z0-9/^%.]+)(.*)")


def is_atlas_param(name: str, unit: str) -> bool:
    """是否为三行图集参数（工作面加宽 / 垫层厚 / 基础厚）之一。"""
    return any(
        name == param_name and unit == param_unit for param_name, param_unit in ATLAS_PARAM_NAMES
    )


def is_atlas_param_name(name: str) -> bool:
    """参数名是否是图集参数名（不看单位；同名其它单位的行只是普通参数）。"""
    return any(name == param_name for param_name, _unit in ATLAS_PARAM_NAMES)


def atlas_param_rows(category: int | None) -> tuple[tuple[str, str], ...]:
    """该类别显示的图集参数行（参数名, 单位）；不显示的类别返回空。

    新建 / 类别切换补行、迁移补行与界面显示都用它，保证“显示哪些行”只有
    :data:`ATLAS_PARAM_CATEGORIES` 一处定义。
    """
    names = ATLAS_PARAM_CATEGORIES.get(int(category or 0), ())
    return tuple((name, unit) for name, unit in ATLAS_PARAM_NAMES if name in names)


def supports_atlas_param(category: int | None, name: str, unit: str) -> bool:
    """该类别是否显示（并认）指定的图集参数行（基础厚对包封 / 箱涵 / 管廊为否）。"""
    return any(
        param_name == name and param_unit == unit
        for param_name, param_unit in atlas_param_rows(category)
    )


def split_param_key(key: str) -> tuple[str, str]:
    """把旧版“名称 单位[若有括注]”键拆成 (参数名, 单位)。

    >>> split_param_key("净宽 m(含内壁厚度)")
    ('净宽(含内壁厚度)', 'm')
    >>> split_param_key("内壁 道")
    ('内壁', '道')
    >>> split_param_key("含钢量 kg/m3")
    ('含钢量', 'kg/m3')
    >>> split_param_key("abc")
    ('abc', '')
    """
    text = str(key or "").strip()
    name, _, rest = text.partition(" ")
    rest = rest.strip()
    if not rest:
        return (name, "")
    match = _UNIT_PATTERN.match(rest)
    if match is None:  # 中文单位（如“道”），整段作为单位
        return (name, rest)
    unit, suffix = match.group(1), match.group(2)
    if suffix:
        name = f"{name}{suffix}"  # 旧键括注属于参数名：“净宽(含内壁厚度)”
    return (name, unit)


def join_param_key(name: str, unit: str) -> str:
    """(参数名, 单位) → 旧版单键文本；无单位时只留参数名。"""
    name = str(name or "").strip()
    unit = str(unit or "").strip()
    if not name:
        return unit
    if not unit:
        return name
    return f"{name} {unit}"
