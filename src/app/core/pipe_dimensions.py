"""管道三直径（DN / oD / iD）的换算与兜底。

新版把管道直径拆成三个概念：

* **DN**（公称直径）：管材的名义规格，只用于显示、构件库与图集查找，不参与
  断面几何计算；
* **oD**（外径，mm）：管外皮直径，参与沟槽 / 基础 / 断面绘制；
* **iD**（内径，mm）：管内腔直径，参与管内体积 / 管位扣减等。

构件库资产从图集一次性提取 ``oD`` / ``iD``；旧工程或手填管道没有这两个值时，
按 ``iD = DN``、``oD = iD + 2t`` 兜底（``t`` 为壁厚，空按 0）。
"""

from __future__ import annotations

#: 展示用符号（表达式 / 界面统一用这三个）
DN_SYMBOL = "DN"
OD_SYMBOL = "oD"
ID_SYMBOL = "iD"


def as_float(value) -> float | None:
    """把任意输入转成 float；空 / 非法返回 None。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def wall_thickness(
    od: float | None,
    inner_d: float | None,
    t: float | None = None,
) -> float:
    """有效壁厚：优先 ``t``，否则 ``(oD-iD)/2``，都没有按 0。"""
    if t is not None:
        return max(float(t), 0.0)
    if od is not None and inner_d is not None:
        return max((float(od) - float(inner_d)) / 2.0, 0.0)
    return 0.0


def normalize(
    dn: int | float,
    od: float | None = None,
    inner_d: float | None = None,
    t: float | None = None,
) -> tuple[float, float, float]:
    """返回 ``(oD, iD, t)``，保证三者关系 ``oD = iD + 2t``。

    优先级：

    1. 同时给了 ``oD`` / ``iD``：以它们为准，``t`` 由差值反算（忽略传入 t，
       避免图集 t 与几何壁厚不一致）；
    2. 只给 ``iD``：``oD = iD + 2t``；
    3. 只给 ``oD``：``iD = oD - 2t``（不得小于 0）；
    4. 都没给：``iD = DN``，``oD = iD + 2t``。
    """
    dn_value = max(float(dn or 0), 0.0)
    t_value = max(float(t or 0), 0.0)
    if od is not None and inner_d is not None:
        outer = max(float(od), 0.0)
        inner = max(float(inner_d), 0.0)
        if outer < inner:
            outer = inner
        return outer, inner, max((outer - inner) / 2.0, 0.0)
    if inner_d is not None:
        inner = max(float(inner_d), 0.0)
        return inner + 2.0 * t_value, inner, t_value
    if od is not None:
        outer = max(float(od), 0.0)
        inner = max(outer - 2.0 * t_value, 0.0)
        return outer, inner, max((outer - inner) / 2.0, 0.0)
    inner = dn_value
    return inner + 2.0 * t_value, inner, t_value


def link_od(inner_d: float, t: float) -> tuple[float, float, float]:
    """改壁厚默认联动外径：保持内径，``oD = iD + 2t``。"""
    return normalize(0, inner_d=inner_d, t=t)


def link_id(od: float, t: float) -> tuple[float, float, float]:
    """改外径联动内径：保持壁厚，``iD = oD - 2t``。"""
    return normalize(0, od=od, t=t)


def sync_pipe_wall(pipe, value: float | None) -> bool:
    """把壁厚写回管道，默认联动外径（内径不动，``oD = iD + 2t``）。

    返回是否发生变化。``value=None`` 表示壁厚未知，保留现有 oD/iD 不动。
    """
    t_value = as_float(value)
    if t_value is None:
        return False
    t_value = max(t_value, 0.0)
    inner = pipe.inner_d if pipe.inner_d is not None else float(pipe.dn)
    od = inner + 2.0 * t_value
    changed = pipe.t != t_value or pipe.od != od or pipe.inner_d != inner
    pipe.t = t_value
    pipe.od = od
    pipe.inner_d = inner
    return changed


__all__ = [
    "sync_pipe_wall",
    "DN_SYMBOL",
    "ID_SYMBOL",
    "OD_SYMBOL",
    "as_float",
    "link_id",
    "link_od",
    "normalize",
    "wall_thickness",
]
