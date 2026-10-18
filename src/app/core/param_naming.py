"""构件参数“参数名 / 单位”的拆分与拼接。

旧版 C# 的构件参数（mcElement.Li）把单位和名字写在同一段文本里
（如 ``净宽 m(含内壁厚度)``、``内壁 道``）；新版拆成两列存储，
``element_param.key`` 只存参数名、``unit`` 列存单位。本模块：

* :func:`split_param_key` —— 旧键 → (参数名, 单位)，迁移与构件库共用；
* :func:`join_param_key` —— (参数名, 单位) → 旧键（.stn 导出仍要旧格式）；
* 图集约定参数（工作面加宽 a / 垫层厚 C1 / 基础厚 C2）的固定名称与单位，
  计算引擎按这两个名字取用户覆盖值。
"""

from __future__ import annotations

import re

#: 管道工作面加宽（图集工作面宽度表 a 列），单位 mm
PARAM_A_NAME = "工作面加宽"
#: 管道垫层厚（图集 C1 列），单位 mm
PARAM_C1_NAME = "垫层厚"
#: 管道（管）基厚（图集 C2 列），单位 mm
PARAM_C2_NAME = "基础厚"

#: 图集约定参数 → 单位；这三行参数名/单位固定（锁定），只允许改值
ATLAS_PARAM_NAMES: tuple[tuple[str, str], ...] = (
    (PARAM_A_NAME, "mm"),
    (PARAM_C1_NAME, "mm"),
    (PARAM_C2_NAME, "mm"),
)

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
