"""导出工程数量表对话框（工具栏「导出 Excel」入口，brackets2 同款交互）。

单位工程按 工程 → 标段 → 单位工程 树状勾选（每行带复选框，父节点三态）；
默认分单位工程口径导出（行前带“单位工程”列、各单位各自汇总合计），勾选
合并选项则把所选单位工程的工程量全部加总；导出的 xlsx 固定为定额工程量 /
清单工程量两张 sheet，一张 sheet 只放一个表。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import update_config
from app.core.event_bus import bus
from app.services import project_io, summary
from app.views.dialogs.new_project_wizard import suggested_dir
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox

_CHECKABLE_FLAGS = (
    Qt.ItemFlag.ItemIsEnabled
    | Qt.ItemFlag.ItemIsUserCheckable
    | Qt.ItemFlag.ItemIsAutoTristate
)


def open_exported_file(path: Path) -> None:
    """用系统默认程序打开导出的文件（「导出完成，是否打开文件？」）。"""
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    elif sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - Windows 关联程序打开
    else:
        subprocess.Popen(["xdg-open", str(path)])


class ExportExcelDialog(FramelessDialog):
    """导出工程数量表：树状勾选单位工程 + 分单位工程 / 合并两种导出口径。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, "导出工程数量表")
        self.resize(440, 500)
        #: (单位工程 id, 树叶子项)；父节点（工程 / 标段）不直接对应导出范围
        self._unit_items: list[tuple[int, QTreeWidgetItem]] = []
        self._build()
        self._load_units()

    def _build(self) -> None:
        layout = self.bodyLayout()
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        hint = QLabel(
            "导出定额工程量表与清单工程量表（每张 sheet 一个表）。默认分单位工程"
            "汇总（行前带“单位工程”列）；勾选合并后把所选单位工程的工程量全部加总。"
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(QLabel("选择单位工程："))
        switch_row = QHBoxLayout()
        self._btn_all = QPushButton("全选")
        self._btn_none = QPushButton("全不选")
        self._btn_all.clicked.connect(lambda: self._set_all_checked(True))
        self._btn_none.clicked.connect(lambda: self._set_all_checked(False))
        switch_row.addWidget(self._btn_all)
        switch_row.addWidget(self._btn_none)
        switch_row.addStretch(1)
        layout.addLayout(switch_row)

        # 工程 → 标段 → 单位工程 树状勾选（与左侧工程树同构，父节点三态）
        self._unit_tree = QTreeWidget()
        self._unit_tree.setHeaderHidden(True)
        self._unit_tree.setColumnCount(1)
        layout.addWidget(self._unit_tree, 1)

        self._merge_check = QCheckBox("合并所选单位工程（工程量全部加总后输出）")
        layout.addWidget(self._merge_check)

        bottom = QHBoxLayout()
        self._btn_export = QPushButton("导出…")
        self._btn_export.setProperty("primary", "true")
        self._btn_export.clicked.connect(self._export)
        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.close)
        bottom.addStretch(1)
        bottom.addWidget(self._btn_export)
        bottom.addWidget(self._btn_close)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------ 数据
    def _load_units(self) -> None:
        """按工程树层级建勾选树，默认全部选中。"""
        root = QTreeWidgetItem([project_io.project_name() or "工程"])
        root.setFlags(_CHECKABLE_FLAGS)
        root.setCheckState(0, Qt.CheckState.Checked)
        self._unit_tree.addTopLevelItem(root)
        for segment in project_io.segments():
            segment_item = QTreeWidgetItem([segment.name])
            segment_item.setFlags(_CHECKABLE_FLAGS)
            segment_item.setCheckState(0, Qt.CheckState.Checked)
            root.addChild(segment_item)
            for unit in project_io.units(segment.id):
                unit_item = QTreeWidgetItem([unit.name])
                # 叶子节点是普通复选框（无子项，无需三态）
                unit_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                )
                unit_item.setCheckState(0, Qt.CheckState.Checked)
                unit_item.setData(0, Qt.ItemDataRole.UserRole, unit.id)
                segment_item.addChild(unit_item)
                self._unit_items.append((unit.id, unit_item))
        self._unit_tree.expandAll()
        if not self._unit_items:
            self._btn_export.setEnabled(False)

    def _checked_unit_ids(self) -> list[int]:
        """勾选中的单位工程 id（按树的显示顺序）。"""
        return [
            unit_id
            for unit_id, item in self._unit_items
            if item.checkState(0) == Qt.CheckState.Checked
        ]

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for _unit_id, item in self._unit_items:
            item.setCheckState(0, state)

    # ------------------------------------------------------------------ 导出
    def _export(self) -> None:
        unit_ids = self._checked_unit_ids()
        if not unit_ids:
            FramelessMessageBox.warning(self, "无法导出", "请至少勾选一个单位工程。")
            return
        start = suggested_dir() / "工程数量表.xlsx"
        target, _filter = QFileDialog.getSaveFileName(
            self, "导出 Excel", str(start), "Excel 工作簿 (*.xlsx)"
        )
        if not target:
            return
        path = Path(target)

        error_text = ""
        result: dict = {}
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = summary.export_quantity_tables(
                path, unit_ids, merged=self._merge_check.isChecked()
            )
        except PermissionError:
            error_text = "文件被占用，无法写入。请先关闭已打开的同名 Excel 文件再重试。"
        except Exception as error:  # 计算失败 / 路径非法等，一律弹窗不崩溃
            error_text = str(error)
        finally:
            QApplication.restoreOverrideCursor()
        if error_text:
            FramelessMessageBox.warning(self, "导出失败", error_text)
            return

        update_config({"ui": {"last_dir": str(path.parent)}})
        bus().status_message.emit(f"已导出：{path}", 5000)
        if (
            FramelessMessageBox.question(
                self, "提示", f"导出完成，是否打开文件？\n{result['path']}"
            )
            == FramelessMessageBox.Yes
        ):
            open_exported_file(path)
