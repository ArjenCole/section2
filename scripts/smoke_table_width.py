"""冒烟：offscreen 实例化各表格，验证固定列宽行为（不随父控件拉伸）。

本机 System32 里若有旧版 msvcp140.dll 会抢在 PySide6 自带运行时之前加载，
导致 Qt 6.11 DLL 报“找不到指定的程序”（打包版 exe 目录自带运行时不受影响）。
这里先按全路径预加载 PySide6 目录里的 VC 运行时：加载器对已加载模块按名字
复用，后续 QtCore 的依赖就落在正确版本上。
"""
import ctypes
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import PySide6

_PYSIDE_DIR = os.path.dirname(PySide6.__file__)
# 本机 System32 的旧版 VC 运行时会抢在 PySide6 自带版本之前被解析，
# Qt 6.11 DLL 因此报“找不到指定的程序”（打包版 exe 目录自带运行时不受影响）。
# 预加载 PySide6 目录里的全部 DLL：加载器对已加载模块按名字复用，
# 之后 QtCore/QtWidgets 的依赖就都落在正确版本上。
for _name in sorted(os.listdir(_PYSIDE_DIR)):
    if _name.lower().endswith(".dll"):
        try:
            ctypes.WinDLL(os.path.join(_PYSIDE_DIR, _name), winmode=8)
        except OSError:
            pass

from PySide6.QtWidgets import QApplication, QHeaderView

app = QApplication([])

failures = []


def check(name, table):
    header = table.horizontalHeader()
    if header.stretchLastSection():
        failures.append(f"{name}: stretchLastSection 仍为 True")
    for col in range(table.columnCount()):
        mode = header.sectionResizeMode(col)
        if mode != QHeaderView.ResizeMode.Interactive:
            failures.append(f"{name}: 第 {col} 列模式为 {mode}")
    # 用户拖动调整：resizeSection 后宽度应保持（Interactive 的定义）
    old = header.sectionSize(0)
    header.resizeSection(0, old + 50)
    if header.sectionSize(0) != old + 50:
        failures.append(f"{name}: 列宽拖动（resizeSection）未保持")
    header.resizeSection(0, old)


from app.views.dialogs.enclosure_edit_dialog import _WorkTable
from app.views.dialogs.foundation_edit_dialog import _ReplaceTable
from app.views.dialogs.principle_dialogs import _LevelTable
from app.views.panels.multi_principle_tab import MultiPrincipleTab
from app.views.panels.unit_panel import UnitPanel
from app.views.widgets.row_button_column import RowButtonColumn

panel = UnitPanel()
for name in ("_element_table", "_pipe_table", "_param_table", "_qty_table"):
    check(name, getattr(panel, name))
for name, table in panel._quantity_tables.items():
    check(f"quantity[{name}]", table)

mp = MultiPrincipleTab("pe")
check("multi_principle", mp._table)

check("_LevelTable", _LevelTable())
check("_WorkTable", _WorkTable())

replace_table = _ReplaceTable()
check("_ReplaceTable", replace_table)
RowButtonColumn(replace_table).attach()
check("_ReplaceTable+buttons", replace_table)
# RowButtonColumn 前一列不再被设为 Stretch
mode_prev = replace_table.horizontalHeader().sectionResizeMode(1)
if mode_prev != QHeaderView.ResizeMode.Interactive:
    failures.append(f"RowButtonColumn: 按钮列前一列模式为 {mode_prev}")

# 窄父控件出横向滚动条：视口远窄于列宽之和时横向滚动范围应大于 0
wide = panel._element_table
wide.resize(120, 300)
wide.show()
app.processEvents()
app.processEvents()
if wide.horizontalScrollBar().maximum() <= 0:
    failures.append("主表格：视口压窄后未出现横向滚动范围")

if failures:
    print("FAIL")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("SMOKE_OK")
