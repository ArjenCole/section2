"""图集候选参数的"候选参数列"定义（v9）。

候选 = 采用/不采用混凝土基础 × 90/120/150/180 四种基础角度，共 8 组
(a, C1, C2)。来源是构件库资产的一次性快照（`EleInventory.json`），允许
用户在详情面板改，之后**永不自动改写**；参数值列按当前主围护原则的
`con_found + found_angle` 自动从这里选（`unit_vm.match_atlas_candidates`）。

* 混凝土管：8 组都用，界面显示 8 列；
* 其他管材：图集查表不看砼基础开关，con/plain 两组值相同，界面只显示
  "不采用混凝土基础"的 4 列。

选组顺序（:func:`select_candidate`，由强到弱，前一级命中就停）：

1. 同组精确 —— 砼基础开关相同、角度相同；
2. 同组就近 —— 砼基础开关相同，角度取 |Δ| 最小（等距取小角度）；
3. 跨组精确 —— 换到另一组（砼 ↔ 非砼），角度相同；
4. 跨组就近 —— 另一组里角度取最近。

四级都不命中即"图集确实没这组数据"，返回 ``(None, None)``，调用方必须把
参数行清空（空 = 引擎按图集自动），**不能保留上一次匹配的旧值**。

注意：06MS201-1 砼管**砼基础表没有 150° 行**（砂基础有），所以
"采用混凝土基础-150°"的快照是 None——此时按第 2 级就近取 120°。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 围护原则基础角度的四种取值
CANDIDATE_ANGLES: tuple[int, ...] = (90, 120, 150, 180)

#: 候选行里的数值字段（顺序 = 参数面板的图集参数行顺序）
CANDIDATE_FIELDS: tuple[str, ...] = ("t", "a", "c1", "c2")


def combo_key(con_found: bool, angle: int) -> str:
    """候选组合键：``con90``（采用砼基础 90°）… ``plain180``（不采用 180°）。"""
    return f"{'con' if con_found else 'plain'}{angle}"


def parse_combo_key(key: str) -> tuple[bool, int] | None:
    """:func:`combo_key` 的逆运算；键不合法返回 None。

    手工补候选格时用：界面只传回来列键，落库要还原成 (砼基础开关, 角度)。
    """
    text = str(key or "").strip()
    for prefix, con_found in (("con", True), ("plain", False)):
        if not text.startswith(prefix):
            continue
        try:
            return con_found, int(text[len(prefix):])
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class CandidateColumn:
    """候选参数列（参数面板里"参数值"右侧的一列）。"""

    key: str  # con90 / plain120 …
    label: str  # 界面列头
    tooltip: str
    con_found: bool
    angle: int


def _columns(con_found: bool, prefix: str, tooltip: str) -> tuple[CandidateColumn, ...]:
    return tuple(
        CandidateColumn(
            key=combo_key(con_found, angle),
            label=f"{prefix}{angle}°",
            tooltip=tooltip,
            con_found=con_found,
            angle=angle,
        )
        for angle in CANDIDATE_ANGLES
    )


_CONCRETE_TOOLTIP = "采用混凝土基础（对应围护原则 con_found=true）的图集快照，可改"
_PLAIN_TOOLTIP = "不采用混凝土基础（con_found=false）的图集快照，可改"

#: 混凝土管显示的 8 列：砼基础 4 列 + 非砼基础 4 列
CONCRETE_COLUMNS: tuple[CandidateColumn, ...] = _columns(
    True, "砼", _CONCRETE_TOOLTIP
) + _columns(False, "非砼", _PLAIN_TOOLTIP)

#: 非混凝土管显示的 4 列：图集查表不看砼基础，只给一组
PLAIN_COLUMNS: tuple[CandidateColumn, ...] = _columns(False, "", _PLAIN_TOOLTIP)


def columns_for(is_concrete: bool) -> tuple[CandidateColumn, ...]:
    """该管材显示的候选列（混凝土 8 列 / 其他 4 列）。"""
    return CONCRETE_COLUMNS if is_concrete else PLAIN_COLUMNS


def nearest_candidate(
    rows, con_found: bool, angle: int
):
    """从候选行里选与 (con_found, angle) 最近的非空行；没有返回 None。

    兼容旧调用（只取值）。实际选组顺序见 :func:`select_candidate`：同组精确 →
    同组就近 → 跨组精确 → 跨组就近。
    """
    return select_candidate(rows, con_found, angle)[0]


#: 匹配层级：由强到弱
MATCH_SAME_EXACT = "same_exact"
MATCH_SAME_NEAREST = "same_nearest"
MATCH_CROSS_EXACT = "cross_exact"
MATCH_CROSS_NEAREST = "cross_nearest"

#: 层级 → 界面文案
MATCH_LEVEL_LABELS: dict[str, str] = {
    MATCH_SAME_EXACT: "同组精确",
    MATCH_SAME_NEAREST: "同组就近",
    MATCH_CROSS_EXACT: "跨组精确",
    MATCH_CROSS_NEAREST: "跨组就近",
}


def is_cross_group(level: str | None) -> bool:
    """该层级是否借用了另一组（砼基础 ↔ 非砼基础）的候选值。"""
    return level in (MATCH_CROSS_EXACT, MATCH_CROSS_NEAREST)


def _usable_rows(rows, con_found: bool):
    """该组里有数据的候选行；t / a / C1 / C2 全 None = 图集无此组合，剔除。"""
    return [
        row
        for row in rows
        if bool(row.con_found) == bool(con_found)
        and any(getattr(row, field, None) is not None for field in CANDIDATE_FIELDS)
    ]


def _exact_row(rows, angle: int):
    target = int(angle)
    for row in rows:
        if int(row.angle) == target:
            return row
    return None


def _nearest_row(rows, angle: int):
    if not rows:
        return None
    return min(rows, key=lambda row: (abs(int(row.angle) - int(angle)), int(row.angle)))


def select_candidate(
    rows, con_found: bool, angle: int
) -> tuple[object | None, str | None]:
    """按四级顺序选一组候选，返回 ``(row, level)``；全不命中返回 ``(None, None)``。

    顺序：同组精确 → 同组就近 → 跨组精确 → 跨组就近。``level`` 供界面标注
    当前选中的格子、以及提示"这一格是跨组借来的"。
    """
    same_group = _usable_rows(rows, con_found)
    row = _exact_row(same_group, angle)
    if row is not None:
        return row, MATCH_SAME_EXACT
    row = _nearest_row(same_group, angle)
    if row is not None:
        return row, MATCH_SAME_NEAREST
    other_group = _usable_rows(rows, not con_found)
    row = _exact_row(other_group, angle)
    if row is not None:
        return row, MATCH_CROSS_EXACT
    row = _nearest_row(other_group, angle)
    if row is not None:
        return row, MATCH_CROSS_NEAREST
    return None, None
