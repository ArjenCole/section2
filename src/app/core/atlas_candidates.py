"""图集候选参数的"候选参数列"定义（v9）。

候选 = 采用/不采用混凝土基础 × 90/120/150/180 四种基础角度，共 8 组
(a, C1, C2)。来源是构件库资产的一次性快照（`EleInventory.json`），允许
用户在详情面板改，之后**永不自动改写**；参数值列按当前主围护原则的
`con_found + found_angle` 自动从这里选（`unit_vm.match_atlas_candidates`）。

* 混凝土管：8 组都用，界面显示 8 列；
* 其他管材：图集查表不看砼基础开关，con/plain 两组值相同，界面只显示
  "不采用混凝土基础"的 4 列。

注意：06MS201-1 砼管**砼基础表没有 150° 行**（砂基础有），所以
"采用混凝土基础-150°"的快照是 None——匹配时按就近角度跳过空组。
"""

from __future__ import annotations

from dataclasses import dataclass

#: 围护原则基础角度的四种取值
CANDIDATE_ANGLES: tuple[int, ...] = (90, 120, 150, 180)


def combo_key(con_found: bool, angle: int) -> str:
    """候选组合键：``con90``（采用砼基础 90°）… ``plain180``（不采用 180°）。"""
    return f"{'con' if con_found else 'plain'}{angle}"


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

    ``rows`` 为 ElementAtlasCandidate 列表。角度就近（等距取小的），
    且要求 a / C1 / C2 至少一个有值（全 None 的组合视为图集无此数据）。
    """
    usable = [
        row
        for row in rows
        if bool(row.con_found) == bool(con_found) and (row.a is not None or row.c1 is not None or row.c2 is not None)
    ]
    if not usable:
        return None
    return min(usable, key=lambda row: (abs(int(row.angle) - int(angle)), int(row.angle)))
