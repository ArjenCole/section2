"""钢制品参数库（旧版 mscInventory.SteelProducts）。

构件编辑器参数表里，右键「钢板桩型号 / 支撑延米重量 kg/m / 钢围檩延米重量
kg/m / 工法桩轴数 轴 / 型钢延米重量 kg/m」这几行，弹出候选型号，选中后把型号
对应的参数值填进「值」列——复刻旧版 FormCpntEdit 的 ``CMS`` 右键菜单
（``dGVparam_SelectionChanged`` 按行名过滤候选，``CMS_ItemClicked`` 回填）。

数据是 1.0 ``Inventory\\SteelProducts--SteelProducts.csv`` 的 xlsx 移植
（``app/resources/inventory/SteelProducts.xlsx``）。六列：名称 / 类型 /
延米重量 / 宽度 / 名称 / F6，**列含义随「类型」变化**（旧版 switch 的语义）：

* ``钢板桩型号``：名称 = 型号（菜单文字）、延米重量 = 单桩延米重量 kg/m、
  宽度 = 单桩宽度 mm（桩中心间隔取同值）、名称列 = 写进「钢板桩型号」参数的
  类别名（槽型钢板桩 / 拉森钢板桩 / 钢板桩）；
* ``工法桩轴数 轴``：延米重量列实为单套截面积 m2、宽度 = 桩径 mm、
  名称列 = 轴数、F6 = 搭接 mm；
* 其余类型（支撑 / 钢围檩 / 型钢延米重量）：名称 = 规格（如 Ø609×16）、
  延米重量 = 该规格的延米重量 kg/m。

2.0 在 1.0 原表基础上补充了工程常用断面，重量都能按下面的口径复核（测试
``tests/test_steel_products.py`` 里有对应断言）：

* **钢管支撑**：``π(D−t)·t·ρ/1000``（ρ = 7.85），1.0 的 Ø203×10 = 47.597、
  Ø609×16 = 233.988 就是这条式子；补 Ø273×8 至 Ø1000×16 共 13 个常用规格。
* **焊接 H 型钢**（钢围檩 / SMW 插芯型钢）：``(2·b·tf + (h−2tf)·tw) × 0.00785``，
  1.0 的 H300×200×6×8 = 38.49、H700×300×13×24 = 179.57 就是这条式子。
* **热轧工字钢 / 槽钢**：GB/T 706 理论重量（1.0 的 I45a = 80.4、槽型 [25a =
  27.5 即该表），补 I40 / I50、槽钢 [40。
* **钢板桩**：拉森Ⅱ 与 FSP-Ⅱ/Ⅲ/Ⅳ/ⅤL 取日标 SP 系列公开数据（SP-Ⅱ 48、
  SP-Ⅲ 60、SP-Ⅳ 76.1、SP-ⅤL 105 kg/m），与表内已有的 FSP VIL（120）同源。

工法桩的搭接按「桩径 − 相邻钻杆中心距」的机械模数补全：Ø850/Ø900 中心距
650 → 250 mm，Ø700/Ø650 中心距 500/450 → 200 mm（与表内 Ø850/700/650 的
单套截面积反算一致；Ø850 三轴 搭接 250 对 1.495 m² 也见江苏省造价管理信息
系统的三轴搅拌桩工程量推导）。**单套截面积沿用 1.0 表值不动**，避免改变已有
工程的围护量。

与旧版的一处偏差：F6（搭接）为空的工法桩型号，旧版会把「搭接 mm」参数写成
空串（该型号的 ``A-E`` / ``(A*3-E*2)/1000`` 随即算不出来），这里改为保留用户
当前值，只在表里有值时覆盖（现表内每个型号都有搭接，这条只作兜底）。

另一处放宽：旧版菜单只挂在参数名与「类型」完全相同的那一行，「单桩延米重量
kg/m」行是空的；这里让该行也调出钢板桩型号菜单（见 ``_KIND_ALIASES``，回填
结果与型号行一致）——用户想选重量时未必记得去点型号行。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import openpyxl

from app.core.paths import resources_dir

#: 类型：钢板桩型号 —— 填「钢板桩型号 / 单桩宽度 / 桩中心间隔 / 单桩延米重量」
KIND_SHEET_PILE = "钢板桩型号"
#: 类型：工法桩轴数 轴 —— 填「桩径 / 工法桩轴数 / 单套截面积 / 搭接」
KIND_MIXING_PILE = "工法桩轴数 轴"

#: 同一张表的另一列也能调出菜单：用户想「选重量」时未必记得去点型号行
#: （旧版只在型号行给菜单，这里放宽到重量行，回填结果与型号行完全一致）
_KIND_ALIASES = {
    "单桩延米重量 kg/m": KIND_SHEET_PILE,
}


def format_number(value: float | int | None) -> str:
    """数值 → 表格文本：整数不带小数点，其余取最短可回读表示。

    ``1.495346490125`` 这类单套截面积必须原样写回（``%g`` 会截成 1.49535，
    面积变了围护量就跟着错），所以走 ``repr`` 而不是格式化。
    """
    if value is None:
        return ""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


@dataclass(frozen=True)
class SteelProduct:
    """一个钢制品型号（旧版 ``SteelProducts[key]`` 的一行）。"""

    #: 型号 / 规格（右键菜单文字）
    name: str
    #: 类型：与构件参数显示名一致（决定填哪几行、菜单挂在哪一行）
    kind: str
    #: 延米重量 kg/m（工法桩行为单套截面积 m2）
    weight: float
    #: 单桩宽度 mm（工法桩行为桩径 mm）
    width: float | None = None
    #: 钢板桩：写进「钢板桩型号」的类别名
    pile_label: str = ""
    #: 工法桩：轴数
    axes: int | None = None
    #: 工法桩：搭接 mm（None = 表里没有该型号的搭接值）
    overlap: float | None = None

    def param_values(self) -> dict[str, str]:
        """型号 → {参数显示名: 值}（旧版 CMS_ItemClicked 的 tDic）。"""
        if self.kind == KIND_SHEET_PILE:
            width = format_number(self.width)
            return {
                "钢板桩型号": self.pile_label,
                "单桩宽度 mm": width,
                "桩中心间隔 mm": width,
                "单桩延米重量 kg/m": format_number(self.weight),
            }
        if self.kind == KIND_MIXING_PILE:
            values = {
                "桩径 mm": format_number(self.width),
                "工法桩轴数 轴": format_number(self.axes),
                "单套截面积 m2": format_number(self.weight),
            }
            if self.overlap:
                values["搭接 mm"] = format_number(self.overlap)
            return values
        return {self.kind: format_number(self.weight)}

    def detail(self) -> str:
        """菜单项的悬停说明（型号本身看不出来的重量 / 宽度 / 轴数）。"""
        parts: list[str] = []
        if self.kind == KIND_SHEET_PILE:
            if self.pile_label:
                parts.append(self.pile_label)
            if self.width:
                parts.append(f"单桩宽度 {format_number(self.width)} mm")
            parts.append(f"单桩延米重量 {format_number(self.weight)} kg/m")
        elif self.kind == KIND_MIXING_PILE:
            if self.width:
                parts.append(f"桩径 {format_number(self.width)} mm")
            if self.axes:
                parts.append(f"{format_number(self.axes)} 轴")
            parts.append(f"单套截面积 {format_number(self.weight)} m2")
            if self.overlap:
                parts.append(f"搭接 {format_number(self.overlap)} mm")
        else:
            parts.append(f"延米重量 {format_number(self.weight)} kg/m")
        return "，".join(parts)


def inventory_path() -> Path:
    """钢制品参数表（1.0 同名 xlsx 原样移植，随程序分发）。"""
    return resources_dir() / "inventory" / "SteelProducts.xlsx"


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    number = _to_float(value)
    return None if number is None else int(round(number))


@lru_cache(maxsize=1)
def steel_products() -> tuple[SteelProduct, ...]:
    """全部型号（文件缺失 / 读不动时返回空，构件编辑器右键只给提示）。"""
    path = inventory_path()
    if not path.exists():
        return ()
    try:
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception:  # noqa: BLE001 - 数据文件坏了不该让编辑器打不开
        return ()
    try:
        worksheet = (
            workbook["SteelProducts"]
            if "SteelProducts" in workbook.sheetnames
            else workbook.worksheets[0]
        )
        rows = tuple(worksheet.iter_rows(values_only=True))
    finally:
        workbook.close()

    products: list[SteelProduct] = []
    for line in rows[1:]:  # 首行是表头（名称 / 类型 / 延米重量 / 宽度 / 名称 / F6）
        if len(line) < 3 or not line[0] or not line[1]:
            continue
        name = str(line[0]).strip()
        kind = str(line[1]).strip()
        extra = line[4] if len(line) > 4 else None
        overlap = _to_float(line[5]) if len(line) > 5 else None
        weight = _to_float(line[2])
        products.append(
            SteelProduct(
                name=name,
                kind=kind,
                weight=weight or 0.0,
                width=_to_float(line[3]),
                # 名称列一列两用：钢板桩是类别名，工法桩是轴数（旧版列语义）
                pile_label="" if kind == KIND_MIXING_PILE else str(extra or "").strip(),
                axes=_to_int(extra) if kind == KIND_MIXING_PILE else None,
                overlap=overlap,
            )
        )
    return tuple(products)


def products_of(kind: str) -> tuple[SteelProduct, ...]:
    """某类型下的全部型号（菜单项；按表内顺序）。"""
    return tuple(product for product in steel_products() if product.kind == kind)


def kind_for_param(display: str) -> str:
    """参数显示名 → 钢制品类型（含别名行）；不是钢制品行时返回 ""。"""
    kind = _KIND_ALIASES.get(display, display)
    return kind if products_of(kind) else ""


def kinds() -> tuple[str, ...]:
    """表内出现过的类型（按首次出现顺序）。"""
    seen: list[str] = []
    for product in steel_products():
        if product.kind not in seen:
            seen.append(product.kind)
    return tuple(seen)


def reload_products() -> None:
    """清缓存（数据文件替换后调用）。"""
    steel_products.cache_clear()


__all__ = [
    "KIND_MIXING_PILE",
    "KIND_SHEET_PILE",
    "SteelProduct",
    "format_number",
    "inventory_path",
    "kind_for_param",
    "kinds",
    "products_of",
    "reload_products",
    "steel_products",
]
