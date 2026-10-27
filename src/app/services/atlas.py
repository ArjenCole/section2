"""图集与构件库加载（M3）。

三块数据都来自随程序分发的 xlsx（只读，openpyxl）：

* **图集** ``app/resources/atlas/*.xlsx`` —— 复刻旧版 mcAtlas：10 张表按
  管径 + 角度 + 级别 查 ``oD/t/a/C1/C2``；
* **构件库** ``app/resources/inventory/ComponentInventory.xlsx`` —— 复刻旧版
  mscInventory.LoadCpnti：Ei(围护)/WSi(止水)/Fi(地基) 三页，每个构件两行
  （discribe=显示名 / value=公式值），参数键 A~Z、FA~FZ；
* **宽度默认表** ``GB 50268-2008.xlsx`` 的 WorkWidth / GrooveB 两页 —— 新建
  围护原则时的初始工作面宽度 / 沟槽宽度表。

与旧版的两处偏差（均为修正旧版缺陷，默认取值模式下结果不变，见各处注释）：
``GetWidthOrB`` 旧版恒读 WorkWidth 表（GrooveB 形同虚设）且把 mm 当 m 用。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from functools import lru_cache

import openpyxl

from app.core.models.models import (
    CATEGORY_BOX_CULVERT,
    CATEGORY_ENCASED,
    CATEGORY_GALLERY,
)
from app.core.paths import atlas_dir, resources_dir
from app.core.pipe_category import CONCRETE_PIPE_CATEGORIES

INVENTORY_DIR = resources_dir() / "inventory"

#: 垫层以上没有包角管座基础的类别（包封埋管 / 箱涵 / 管廊）：基础厚 C2 恒为 0
C2_ZERO_CATEGORIES: tuple[int, ...] = (CATEGORY_ENCASED, CATEGORY_BOX_CULVERT, CATEGORY_GALLERY)

#: 图集表，顺序与旧版 mcAtlas.Init() 的 pvDS.Tables 下标一致
ATLAS_TABLES: tuple[tuple[str, str], ...] = (
    ("06MS201-1.xlsx", "砼管砼基础"),  # 0
    ("06MS201-1.xlsx", "砼管砂基础"),  # 1
    ("JC-T 640-1996.xlsx", "砼顶管"),  # 2
    ("HDPE-PE.xlsx", "HDPE承插式双壁缠绕管"),  # 3
    ("HDPE-PE.xlsx", "PE管"),  # 4
    ("06MS201-2.xlsx", "硬聚氯乙烯(PVC-U)管"),  # 5
    ("06MS201-2.xlsx", "聚氯乙烯(PE)管"),  # 6
    ("06MS201-2.xlsx", "钢带增强聚乙烯(PE)管"),  # 7
    ("金属管道.xlsx", "球墨铸铁管"),  # 8
    ("金属管道.xlsx", "钢管"),  # 9
)


@dataclass(frozen=True)
class AtlasParam:
    """一次图集查询的结果（字段含义同旧版 mcAtlas 的公有字段，长度单位 mm）。"""

    od: float = -1.0  # 外径 mm；-1 表示图集未提供
    t: float = 0.0  # 壁厚 mm
    a: float = 0.0  # 工作面加宽 mm
    c1: float = 0.0  # 垫层厚 mm
    c2: float = 0.0  # 基础厚 mm
    workwidth: float = 0.0  # 工作面宽度 mm（单侧）
    groove_b: float = 0.0  # 沟槽底宽 m（旧版 grooveB；0 表示按断面推算）
    q: float = 0.0


@dataclass
class PipeSpec:
    """查询图集所需的管道信息（管材类别、材质、管径 mm、壁厚覆盖值）。

    ``cat`` 是计算唯一依据（面宽表行 + 图集表分流）；空值才按 ``mat`` 折算
    （见 :func:`app.core.pipe_category.category_of_mat`，仅供库外构件兜底）。
    ``t`` 为详情面板的管道壁厚用户值（mm）；None = 自动按图集。
    """

    mat: str = ""
    dn: int = 600
    t: float | None = None
    cat: str = ""

    def resolved_category(self) -> str:
        from app.core.pipe_category import normalize_category

        return normalize_category(self.cat, mat=self.mat)


@dataclass
class AtlasQuery:
    """图集查询输入：构件类别 + 首管道 + 围护原则相关设定。

    ``a`` / ``c1`` / ``c2`` 为详情面板参数行（工作面加宽 / 垫层厚 / 基础厚）
    的用户覆盖值；None = 未覆盖，按图集行取值。显式 0 是有效覆盖
    （唯垫层厚 0 在引擎处仍按“垫层取原则”的旧语义回退）。
    """

    category: int
    pipes: list[PipeSpec] = field(default_factory=list)
    con_found: bool = True
    found_angle: int = 120
    #: 沟槽宽度取值方式：WorkWidth（按断面推算）/ B（用沟槽宽度表）
    groove_width: str = "WorkWidth"
    size_b: float = 0.0  # 断面宽 m
    widths: dict[str, dict[int, float]] = field(default_factory=dict)
    groove_bs: dict[str, dict[int, float]] = field(default_factory=dict)
    a: float | None = None
    c1: float | None = None
    c2: float | None = None
    #: 角度必须精确命中（不做就近兜底）。候选快照生成用：图集没有该角度的
    #: 行时按"无数据"记空，而不是把 120/180 的值当成 150° 存下来。
    strict_angle: bool = False


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _key_text(value) -> str:
    """把单元格值转成旧版 DataTable.Select 用的字符串键。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


@lru_cache(maxsize=8)
def _load_sheet(path_text: str, sheet: str) -> tuple[tuple[str, ...], ...]:
    workbook = openpyxl.load_workbook(path_text, data_only=True, read_only=True)
    try:
        worksheet = workbook[sheet]
        return tuple(
            tuple("" if cell is None else str(cell) for cell in row)
            for row in worksheet.iter_rows(values_only=True)
        )
    finally:
        workbook.close()


class AtlasCatalog:
    """图集数据目录：加载 10 张表并提供按 管径+角度+级别 的查询。"""

    def __init__(self) -> None:
        self._rows: dict[int, list[dict[str, str]]] = {}
        folder = atlas_dir()
        for index, (file_name, sheet) in enumerate(ATLAS_TABLES):
            path = folder / file_name
            if not path.exists():
                self._rows[index] = []
                continue
            raw = _load_sheet(str(path), sheet)
            if not raw:
                self._rows[index] = []
                continue
            header = [cell.strip() for cell in raw[0]]
            rows: list[dict[str, str]] = []
            for line in raw[1:]:
                record: dict[str, str] = {}
                for column in range(len(header)):
                    name = header[column]
                    if not name:
                        continue
                    # 砼管砼基础表尾部还有一个重名 level 列（图集标识等级 1 / 2、3），
                    # 与旧版 CSV 的 level1 列同源；重名列以首个为准，否则 Ⅱ/Ⅲ 级管查不到
                    if name in record:
                        continue
                    record[name] = _key_text(line[column]) if column < len(line) else ""
                # 标题行（D 列是“D=600~3000…”之类）不参与匹配
                if not record.get("D", "").replace(".", "", 1).isdigit():
                    continue
                rows.append(record)
            self._rows[index] = rows

    def find(
        self,
        table_index: int,
        dn: str,
        angle: str | None = None,
        level: str | None = None,
    ) -> dict[str, str] | None:
        """按 管径(±角度±级别) 查表；多条命中取最后一条（同旧版覆盖语义）。"""
        found: dict[str, str] | None = None
        for record in self._rows.get(table_index, []):
            if record.get("D") != dn:
                continue
            if angle is not None and record.get("angle") != angle:
                continue
            if level is not None and record.get("level") != level:
                continue
            found = record
        return found

    def find_nearest_angle(
        self,
        table_index: int,
        dn: str,
        angle: str,
        level: str | None = None,
    ) -> dict[str, str] | None:
        """同一张表里按 (管径 ± 级别) 取角度最近的一行；等距取小角度。

        用于"图集没有该角度的行"时的兜底（如砼基础表没有 150°，取 120°）——
        旧版是丢掉角度条件取最后一条命中行，实际落到 180°，与"就近"无关。
        """
        try:
            target = float(angle)
        except (TypeError, ValueError):
            return None
        best: dict[str, str] | None = None
        best_key: tuple[float, float] | None = None
        for record in self._rows.get(table_index, []):
            if record.get("D") != dn:
                continue
            if level is not None and record.get("level") != level:
                continue
            try:
                value = float(record.get("angle"))
            except (TypeError, ValueError):
                continue
            key = (abs(value - target), value)
            # 同角度的重复行取最后一条（与 find 的"多条命中取最后一条"一致：
            # 图集里同一 D+级别 会有小管径表和大管径表两处）
            if best_key is None or key <= best_key:
                best, best_key = record, key
        return best

    @staticmethod
    def read(record: dict[str, str] | None) -> tuple[float, float, float, float, float, float]:
        """从图集行读 (oD, t, a, C1, C2, Q)；无 oD 列时记 -1（同旧版容错）。"""
        if record is None:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        od = _num(record.get("oD")) if record.get("oD") else -1.0
        return (
            od,
            _num(record.get("t")),
            _num(record.get("a")),
            _num(record.get("C1")),
            _num(record.get("C2")),
            _num(record.get("Q")),
        )


_CATALOG: AtlasCatalog | None = None


def catalog() -> AtlasCatalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = AtlasCatalog()
    return _CATALOG


def _width_of(table: dict[str, dict[int, float]], category: str, size_b: float) -> float:
    """旧版 GetWidthOrB：断面宽折算成 mm 后向百位取整查表（返回 mm）。

    超出 0~3000 的管径按边界取值（旧版会直接 KeyError）。
    """
    return _width_of_dn(table, category, size_b * 1000.0)


def _width_of_dn(table: dict[str, dict[int, float]], category: str, dn_mm: float) -> float:
    """按管径（mm，向百位取整）查宽度表；超出 0~3000 按边界取值。"""
    dn = int(round(float(dn_mm) / 100.0) * 100)
    dn = max(0, min(3000, dn))
    return table.get(category, {}).get(dn, 0.0)


def _width_pair(query: AtlasQuery) -> tuple[float, float]:
    """(工作面宽度 mm, 沟槽底宽 m)：行由构件类别 + 管材类别决定。

    直埋管道取第一根管的管材类别与管径（这是唯一读管材类别的构件）；
    包封埋管 / 箱涵 / 管廊按构件类别固定取对应行、管径按 0（旧版语义）。
    """
    from app.core.pipe_category import width_dn_for, width_row_for

    pipe = query.pipes[0] if query.pipes else None
    row = width_row_for(query.category, pipe.resolved_category() if pipe else "")
    dn = width_dn_for(query.category, pipe.dn if pipe else 0)
    workwidth = _width_of_dn(query.widths, row, dn)
    groove_b = 0.0 if query.groove_width == "WorkWidth" else _width_of_dn(query.groove_bs, row, dn) / 1000.0
    return workwidth, groove_b


def _snapshot_atlas(query: AtlasQuery) -> AtlasParam | None:
    """快照短路：参数齐了就不再查图集表，返回 None 表示需要查表兜底。

    v8 起构件库资产在插入时就把 工作面加宽 / 垫层厚 / 基础厚 与每根管的壁厚
    快照进条目，计算、断面、包封扣管位都只读这些值。只有库外构件或用户删了
    参数行时才回落查表。
    """
    if not query.pipes or query.pipes[0].t is None:
        return None
    if query.a is None or query.c1 is None:
        return None
    zero_c2 = query.category in C2_ZERO_CATEGORIES
    if not zero_c2 and query.c2 is None:
        return None
    t = 0.0 if zero_c2 else float(query.pipes[0].t)
    workwidth, groove_b = _width_pair(query)
    return AtlasParam(
        od=query.pipes[0].dn + t * 2.0,
        t=t,
        a=float(query.a),
        c1=float(query.c1),
        c2=0.0 if zero_c2 else float(query.c2),
        workwidth=workwidth,
        groove_b=groove_b,
        q=0.0,
    )


def resolve_atlas(query: AtlasQuery) -> AtlasParam:
    """图集参数：优先按条目快照返回，参数不齐时才按管材类别查表。

    分流键是 **管材类别**（``PipeSpec.cat``，见 app.core.pipe_category），
    不再是材质名称；材质名称只用来在本表里细分级别（Ⅱ级 / K9 / 1.6Mpa …），
    且仅走兜底路径时使用。
    """
    snapshot = _snapshot_atlas(query)
    if snapshot is not None:
        return snapshot

    cat = catalog()
    od, t, a, c1, c2, q = -1.0, 0.0, 0.0, 0.0, 0.0, 0.0
    workwidth = 0.0
    groove_b = 0.0
    angle = str(query.found_angle)
    dn_text = _key_text(query.pipes[0].dn if query.pipes else 0)
    pipe_cat = query.pipes[0].resolved_category() if query.pipes else ""

    if query.category == 2:  # 包封埋管
        workwidth, groove_b = _width_pair(query)
        return _apply_overrides(
            query,
            AtlasParam(t=0, a=100, c1=100, c2=0, workwidth=workwidth, groove_b=groove_b),
        )
    if query.category in (3, 6):  # 箱涵 / 管廊
        workwidth, groove_b = _width_pair(query)
        return _apply_overrides(
            query,
            AtlasParam(t=0, a=100, c1=100, c2=0, workwidth=workwidth, groove_b=groove_b),
        )

    mat = query.pipes[0].mat if query.pipes else ""
    level = ""

    if query.category == 4:  # 顶管
        tmp_level = "双插口管"
        if "平口" in mat:
            tmp_level = "平口管"
        if "企口" in mat:
            tmp_level = "企口管"
        if "双插口" in mat:
            tmp_level = "双插口管"
        if "钢承口" in mat:
            tmp_level = "钢承口管"
        od, t, a, c1, c2, q = cat.read(cat.find(2, dn_text, level=tmp_level))
    elif query.category == 5:  # 牵引管
        od, t, a, c1, c2, q = cat.read(cat.find(4, dn_text))
    elif query.category == 1:  # 直埋管道
        is_con_pipe = pipe_cat in CONCRETE_PIPE_CATEGORIES
        if is_con_pipe and query.con_found and ("预应力" not in mat):
            # 混凝土基础：按级别（Ⅰ/Ⅱ/Ⅲ 级管）查砼管砼基础表
            if ("Ⅰ" in mat) or ("一级" in mat):
                level = "1"
            if ("Ⅱ" in mat) or ("二级" in mat):
                level = "2"
            if ("Ⅲ" in mat) or ("三级" in mat):
                level = "3"
            row = cat.find(0, dn_text, angle, level)
            if row is None or _num(row.get("t")) == 0:
                # 该角度图集没有这一行（06MS201-1 砼基础表只有 90/120/180）：
                # 除非要求精确命中，否则取角度最近的一行（等距取小角度）。
                # 旧版是丢掉角度条件取最后一条命中行，实际恒定落到 180°。
                row = (
                    None
                    if query.strict_angle
                    else cat.find_nearest_angle(0, dn_text, angle, level)
                )
            od, t, a, c1, c2, q = cat.read(row)
            workwidth = _width_of_dn(query.widths, pipe_cat, query.pipes[0].dn)
            groove_b = _groove_b_dn(query, pipe_cat, query.pipes[0].dn)
        elif is_con_pipe:
            # 砂基础：06MS201-1 页8~11 是非预应力（90/120/150/180°），
            # 页12~14 是预应力（90/120/180°，**没有 150°**）
            tmp_level = "非预应力"
            if "预应力" in mat:
                tmp_level = "预应力"
            if "非预应力" in mat:
                tmp_level = "非预应力"
            tmp_angle = angle
            if tmp_level == "预应力" and query.size_b < 0.6 and tmp_angle == "90":
                tmp_angle = "120"
            od, t, a, c1, c2, q = cat.read(cat.find(1, dn_text, tmp_angle, tmp_level))
            workwidth = 0.0
            groove_b = _groove_b_dn(query, pipe_cat, query.pipes[0].dn)
        else:
            # 非混凝土：管材类别决定面宽表行（用户可改），材质文字只用于在本
            # 表内细分级别（HDPE / PVC / PE / 球墨 K9 / 焊接 1.6MPa …）。
            width_category = pipe_cat
            if "HDPE" in mat:
                od, t, a, c1, c2, q = cat.read(cat.find(3, dn_text, angle))
            elif ("PVC" in mat) or ("pvc" in mat):
                tmp_level = "硬聚氯乙烯(PVC-U)双壁波纹管"
                if "加筋管" in mat:
                    tmp_level = "硬聚氯乙烯(PVC-U)加筋管"
                if "平壁管" in mat:
                    tmp_level = "硬聚氯乙烯(PVC-U)平壁管 4kN/m2"
                    if "8" in mat:
                        tmp_level = "硬聚氯乙烯(PVC-U)平壁管 8kN/m2"
                od, t, a, c1, c2, q = cat.read(cat.find(5, dn_text, angle, tmp_level))
            elif "PE" in mat:
                if query.size_b < 0.15:
                    od, t, a, c1, c2, q = cat.read(cat.find(4, dn_text))
                elif "钢带" in mat:
                    od, t, a, c1, c2, q = cat.read(
                        cat.find(7, dn_text, angle, "钢带增强聚乙烯(PE)管")
                    )
                else:
                    tmp_level = "聚氯乙烯(PE)双壁波纹管"
                    if "缠绕" in mat:
                        tmp_level = (
                            "聚氯乙烯(PE)缠绕结构壁管 A型"
                            if ("B" in mat or "b" in mat)
                            else "聚氯乙烯(PE)缠绕结构壁管 B型"
                        )
                    od, t, a, c1, c2, q = cat.read(cat.find(6, dn_text, angle, tmp_level))
            elif ("球墨" in mat) or ("球铁" in mat) or ("铸铁" in mat):
                tmp_level = "K9"
                if ("K8" in mat) or ("k8" in mat):
                    tmp_level = "K8"
                if ("K10" in mat) or ("k10" in mat):
                    tmp_level = "K10"
                od, t, a, c1, c2, q = cat.read(cat.find(8, dn_text, angle, tmp_level))
            elif "钢管" in mat:
                tmp_level = "给水钢管"
                if query.size_b <= 0.15:
                    tmp_level = "焊接钢管1.0Mpa"
                else:
                    tmp_level = "无缝钢管"
                if "焊接" in mat:
                    tmp_level = "焊接钢管1.0Mpa"
                    if ("1.6Mpa" in mat) or ("1.6mpa" in mat):
                        tmp_level = "焊接钢管1.6Mpa"
                elif "无缝" in mat:
                    tmp_level = "无缝钢管"
                od, t, a, c1, c2, q = cat.read(cat.find(9, dn_text, angle, tmp_level))
            width_dn = query.pipes[0].dn if query.pipes else 0
            workwidth = _width_of_dn(query.widths, width_category, width_dn)
            groove_b = _groove_b_dn(query, width_category, width_dn)

    if query.groove_width == "WorkWidth":
        groove_b = 0.0

    return _apply_overrides(
        query,
        AtlasParam(od=od, t=t, a=a, c1=c1, c2=c2, workwidth=workwidth, groove_b=groove_b, q=q),
    )


def _apply_overrides(query: AtlasQuery, at: AtlasParam) -> AtlasParam:
    """详情面板覆盖值：工作面加宽 / 垫层厚 / 基础厚（None = 未覆盖，按图集行）。

    覆盖值由计算引擎与断面图按构件类别决定传不传（直埋传三行、包封 / 箱涵 /
    管廊传工作面加宽与垫层厚，见 param_naming.ATLAS_PARAM_CATEGORIES）。
    包封 / 箱涵 / 管廊垫层以上没有包角管座基础，基础厚恒为 0，不认覆盖值。
    管道壁厚只在真正按管线查图的类别生效：包封 / 箱涵 / 管廊的断面宽由自身
    参数决定；壁厚被覆盖时外径按 内径 + 2×壁厚 重推，与图集 oD 列同源。
    """
    a, c1, c2, t, od = at.a, at.c1, at.c2, at.t, at.od
    if query.a is not None:
        a = query.a
    if query.c1 is not None:
        c1 = query.c1
    if query.c2 is not None and query.category not in C2_ZERO_CATEGORIES:
        c2 = query.c2
    t_override = query.pipes[0].t if query.pipes else None
    if t_override is not None and query.category not in (2, 3, 6):
        t = t_override
        od = query.pipes[0].dn + t * 2.0
    return dataclasses.replace(at, od=od, t=t, a=a, c1=c1, c2=c2)


def _groove_b(query: AtlasQuery, category: str, size_b: float) -> float:
    """沟槽底宽（m），按断面宽折算管径查表（兼容旧调用）。"""
    return _groove_b_dn(query, category, size_b * 1000.0)


def _groove_b_dn(query: AtlasQuery, category: str, dn_mm: float) -> float:
    """沟槽底宽（m），按管径 mm 查 GrooveB 表。

    旧版 GetWidthOrB 恒读 WorkWidth 表且未除以 1000（把 mm 当 m 用），
    “沟槽宽度表”形同虚设；这里按字面语义查 GrooveB 表并换算成 m。
    默认模式（WorkWidth）下旧版直接置 0，两者一致。
    """
    return _width_of_dn(query.groove_bs, category, dn_mm) / 1000.0


# --------------------------------------------------------------------------- #
# 构件库（旧版 mscInventory：ComponentInventory.xlsx 的 Ei / WSi / Fi）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ComponentTemplate:
    """构件库条目：名称 + 描述公式 + 参数（key → (显示名, 表达式)）。"""

    group: str
    name: str
    describe: str
    params: dict[str, tuple[str, str]]


class ComponentLibrary:
    """构件库：Ei(围护) / WSi(止水) / Fi(地基)。"""

    def __init__(self) -> None:
        self.groups: dict[str, dict[str, ComponentTemplate]] = {"Ei": {}, "WSi": {}, "Fi": {}}
        path = INVENTORY_DIR / "ComponentInventory.xlsx"
        if not path.exists():
            return
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            for sheet in ("Ei", "WSi", "Fi"):
                worksheet = workbook[sheet]
                rows = tuple(tuple(cell for cell in row) for row in worksheet.iter_rows(values_only=True))
                self._load_group(sheet, rows)
        finally:
            workbook.close()

    def _load_group(self, group: str, rows: tuple[tuple, ...]) -> None:
        if len(rows) < 3:
            return
        header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
        index = 1
        while index + 1 < len(rows) + 1 and index < len(rows):
            describe_row = rows[index]
            value_row = rows[index + 1] if index + 1 < len(rows) else None
            index += 2
            if value_row is None:
                break
            name = str(describe_row[1] or "").strip()
            if not name:
                continue
            params: dict[str, tuple[str, str]] = {}
            for column in range(2, len(header)):
                key = header[column]
                if not key:
                    continue
                display = str(describe_row[column] or "") if column < len(describe_row) else ""
                value = str(value_row[column] or "") if column < len(value_row) else ""
                if display == "" and value == "":
                    continue
                params[key] = (display, value)
            self.groups[group][name] = ComponentTemplate(
                group=group,
                name=name,
                describe=str(value_row[1] or ""),
                params=params,
            )

    def names(self, group: str) -> list[str]:
        return list(self.groups.get(group, {}))

    def template(self, group: str, name: str) -> ComponentTemplate | None:
        return self.groups.get(group, {}).get(name)


_LIBRARY: ComponentLibrary | None = None


def component_library() -> ComponentLibrary:
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = ComponentLibrary()
    return _LIBRARY


def default_width_tables() -> tuple[dict[str, dict[int, float]], dict[str, dict[int, float]]]:
    """读 GB 50268-2008.xlsx 的 WorkWidth / GrooveB 两页（值单位 mm）。"""
    work: dict[str, dict[int, float]] = {}
    groove: dict[str, dict[int, float]] = {}
    path = atlas_dir() / "GB 50268-2008.xlsx"
    if path.exists():
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            for sheet, target in (("WorkWidth", work), ("GrooveB", groove)):
                worksheet = workbook[sheet]
                rows = list(worksheet.iter_rows(values_only=True))
                if len(rows) < 2:
                    continue
                header = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
                for line in rows[1:]:
                    if not line or line[0] is None:
                        continue
                    name = str(line[0]).strip()
                    values: dict[int, float] = {}
                    for column in range(1, len(header)):
                        if not header[column].isdigit():
                            continue
                        values[int(header[column])] = _num(line[column]) if column < len(line) else 0.0
                    target[name] = values
        finally:
            workbook.close()
    return work, groove
