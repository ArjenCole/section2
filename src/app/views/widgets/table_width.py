"""表格固定宽度行为（全项目约定）。

所有表格都不随父控件宽度拉伸：每列有自己的固定宽度（用户拖动列边界调整），
父控件够宽时整个表格显示完整、右侧多余空间留空；父控件不够宽时出横向滚动条。

Qt 侧的做法见 :func:`fixed_width_behavior`：关闭 horizontalHeader 的
stretchLastSection、全部列用 Interactive 模式（用户可拖动，之后新增的列——
如参数表的候选列——沿用同一模式）。需要按内容定初始列宽的表格在装填后调
一次 ``resizeColumnsToContents()``：Interactive 不会随内容自动重算，用户
拖过的宽度得以保留。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QTableView


def fixed_width_behavior(table: QTableView) -> None:
    """把表格横向宽度切成「固定列宽、不随父控件拉伸」行为。"""
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


#: 列头一行的横向开销：QSS ``QHeaderView::section`` 的 padding（左右各 10px）
#: 加 1px 右分隔线，再留 1px 防不同机器字体微差把末字裁出省略号
_HEADER_TEXT_OVERHEAD = 22


def header_fit_width(table: QTableView, text: str) -> int:
    """「列头文字刚好完整显示」的列宽：文字实宽 + 列头内边距。

    按表头字体现量（构建 UI 在窗体显示之前，必须先 ensurePolished 把全局
    QSS 的 13px 字体刷到控件上，否则量出来的是 9pt 默认字体）。候选参数
    列这类列头随数据变化的列（砼90° / 非砼180° …）每次重建表头后用它逐列
    定宽；管径mm 这类固定列头用它算一次即可。
    """
    table.ensurePolished()
    return table.fontMetrics().horizontalAdvance(text) + _HEADER_TEXT_OVERHEAD
