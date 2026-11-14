"""导出工程数量表对话框（工具栏「导出 Excel」入口，brackets2 同款交互）。

单位工程按 工程 → 标段 → 单位工程 树状勾选（每行带复选框，父节点三态）；
下方三个导出内容勾选决定输出哪些 sheet（默认全出，取消的项不输出对应
sheet）：标段费用汇总（工程根 / 各标段各一张）、定额 / 清单工程量汇总表
（每个单位工程各一张，行带单价 / 合价；清单勾选右侧的下拉可选“仅清单项”
——清单表隐藏清单项目下的定额工程量行）。勾选合并选项则把所选单位工程的
工程量全部加总，输出定额 / 清单两张合并表（同样受定额 / 清单勾选控制）。
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
    QComboBox,
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
from app.views.widgets.platform_buttons import (
    CLOSE_TEXT,
    DialogButtonSpec,
    add_dialog_buttons,
)

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

        # 导出内容勾选（默认全出；取消的项不输出对应 sheet）
        self._cost_check = QCheckBox("导出标段费用汇总")
        self._cost_check.setChecked(True)
        layout.addWidget(self._cost_check)
        self._quota_check = QCheckBox("导出定额工程量汇总表")
        self._quota_check.setChecked(True)
        layout.addWidget(self._quota_check)

        # 清单勾选同一行右侧：清单表内容下拉（仅清单项 = 隐藏定额工程量行）
        self._listing_check = QCheckBox("导出清单工程量汇总表")
        self._listing_check.setChecked(True)
        self._listing_mode_combo = QComboBox()
        self._listing_mode_combo.addItem("展开工程量项")
        self._listing_mode_combo.addItem("仅清单项")
        self._listing_mode_combo.setToolTip(
            "仅清单项：清单工程量汇总表只输出清单项目行，隐藏其下的定额工程量"
            "行（清单项目行的合价仍按被隐藏行的合计计算）。"
        )
        self._listing_check.toggled.connect(self._listing_mode_combo.setEnabled)
        listing_row = QHBoxLayout()
        listing_row.addWidget(self._listing_check)
        listing_row.addStretch(1)
        listing_row.addWidget(self._listing_mode_combo)
        layout.addLayout(listing_row)

        self._merge_check = QCheckBox("合并所选单位工程（工程量全部加总后输出）")
        # 合并口径没有费用汇总表：费用汇总勾选仅在分单位工程口径生效
        self._merge_check.toggled.connect(
            lambda checked: self._cost_check.setEnabled(not checked)
        )
        layout.addWidget(self._merge_check)

        # 底部标准按钮行（导出/关闭）：顺序、默认按钮、对齐按平台规范，
        # 见 widgets/platform_buttons.py
        bottom = QHBoxLayout()
        self._btn_export = QPushButton("导出…")
        self._btn_export.clicked.connect(self._export)
        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.close)
        add_dialog_buttons(
            bottom,
            [
                DialogButtonSpec("导出…", "accept", button=self._btn_export),
                DialogButtonSpec(
                    CLOSE_TEXT, "reject", on_click=self.close, button=self._btn_close
                ),
            ],
        )
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
        include_cost = self._cost_check.isChecked()
        include_quota = self._quota_check.isChecked()
        include_listing = self._listing_check.isChecked()
        # 至少要出一张表（合并口径没有费用汇总表，费用汇总勾选不参与判断）
        if self._merge_check.isChecked():
            exportable = include_quota or include_listing
        else:
            exportable = include_cost or include_quota or include_listing
        if not exportable:
            FramelessMessageBox.warning(self, "无法导出", "请至少勾选一种要导出的表。")
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
                path,
                unit_ids,
                merged=self._merge_check.isChecked(),
                include_cost=include_cost,
                include_quota=include_quota,
                include_listing=include_listing,
                listing_only=self._listing_mode_combo.currentIndex() == 1,
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
