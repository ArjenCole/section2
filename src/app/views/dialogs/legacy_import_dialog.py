"""旧版工程导入向导（M6）。

流程：选择 .stn → 选择 .stn2 保存路径 → 解析摘要预览 → 确认写库并打开 →
结束报告（成功计数 + 警告/跳过明细，支持复制文本）。
原 .stn 文件任何情况下只读。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from app.core.config import update_config
from app.views.widgets.frameless_dialog import FramelessDialog, FramelessMessageBox
from app.core.event_bus import bus
from app.services import stn_migration
from app.views.dialogs.new_project_wizard import suggested_dir


class LegacyImportDialog(FramelessDialog):
    """旧工程导入向导（非模态流程，用窗口自身承载步骤；无边框自绘标题栏）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, "导入旧版工程(.stn)")
        self.resize(680, 520)
        self._source: Path | None = None
        self._target: Path | None = None
        self._legacy = None
        self._build()

    def _build(self) -> None:
        layout = self.bodyLayout()
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        hint = QLabel(
            "把 2017 年老软件（C# 版）的 .stn 工程一次性迁移为 .stn2。\n"
            "原 .stn 文件只读，不会被修改；原则引用匹配不到的会按默认值补齐并列出警告。"
        )
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self._btn_pick = QPushButton("1. 选择旧工程文件(.stn)…")
        self._btn_pick.clicked.connect(self._pick_source)
        self._btn_target = QPushButton("2. 选择保存路径…")
        self._btn_target.setEnabled(False)
        self._btn_target.clicked.connect(self._pick_target)
        self._btn_run = QPushButton("3. 开始迁移")
        self._btn_run.setProperty("primary", "true")
        self._btn_run.setEnabled(False)
        self._btn_run.clicked.connect(self._run)
        row.addWidget(self._btn_pick)
        row.addWidget(self._btn_target)
        row.addWidget(self._btn_run)
        layout.addLayout(row)

        self._summary = QPlainTextEdit()
        self._summary.setReadOnly(True)
        self._summary.setPlaceholderText("选择旧工程后，这里显示解析摘要；迁移完成后显示报告。")
        layout.addWidget(self._summary, 1)

        bottom = QHBoxLayout()
        self._btn_copy = QPushButton("复制报告")
        self._btn_copy.setEnabled(False)
        self._btn_copy.clicked.connect(self._copy_report)
        self._btn_close = QPushButton("关闭")
        self._btn_close.clicked.connect(self.close)
        bottom.addStretch(1)
        bottom.addWidget(self._btn_copy)
        bottom.addWidget(self._btn_close)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------ 步骤
    def _pick_source(self) -> None:
        start = str(suggested_dir())
        target, _filter = QFileDialog.getOpenFileName(
            self, "选择旧工程", start, "旧版 Section 工程 (*.stn)"
        )
        if not target:
            return
        try:
            self._legacy = stn_migration.parse_legacy(target)
        except stn_migration.MigrationError as error:
            FramelessMessageBox.warning(self, "无法读取", str(error))
            return
        self._source = Path(target)
        self._btn_target.setEnabled(True)
        self._show_preview()

    def _show_preview(self) -> None:
        legacy = self._legacy
        names = [enclosure.name for enclosure in legacy.enclosures]
        names += [name for name, _r, _c in legacy.foundations]
        self._summary.setPlainText(
            f"源文件：{self._source}\n"
            f"旧版程序版本：{legacy.version or '未知'}\n"
            f"工程名称：{legacy.project_name}\n"
            f"标段 {len(legacy.segments)} 个 / 单位工程 "
            f"{sum(len(segment.units) for segment in legacy.segments)} 个 / 构件 "
            f"{sum(len(unit.elements) for segment in legacy.segments for unit in segment.units)} 条\n"
            f"围护原则 {len(legacy.enclosures)} 条，地基原则 {len(legacy.foundations)} 条\n"
            f"涉及原则：{'、'.join(names) if names else '（无）'}\n\n"
            "确认后选择 .stn2 保存路径并开始迁移。"
        )

    def _pick_target(self) -> None:
        if self._source is None:
            return
        target, _filter = QFileDialog.getSaveFileName(
            self,
            "保存新工程",
            str(suggested_dir() / f"{self._source.stem}.stn2"),
            "Section 工程 (*.stn2)",
        )
        if not target:
            return
        self._target = Path(target)
        self._btn_run.setEnabled(True)

    def _run(self) -> None:
        if self._source is None or self._target is None:
            return
        try:
            report = stn_migration.migrate(self._source, self._target)
        except Exception as error:
            FramelessMessageBox.critical(self, "迁移失败", f"{error}\n\n半成品文件已删除，原 .stn 未被修改。")
            return
        update_config({"ui": {"last_dir": str(self._target.parent)}})
        self._summary.setPlainText(report.text())
        self._btn_copy.setEnabled(True)
        self._btn_run.setEnabled(False)
        FramelessMessageBox.information(
            self, "迁移完成",
            f"已生成 {report.target}\n"
            f"构件 {report.elements} 条、警告 {len(report.warnings)} 条、跳过 {len(report.skipped)} 条。\n"
            "详细报告见下方文本；请注意核对默认补齐的原则。",
        )

    def _copy_report(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._summary.toPlainText())
        bus().status_message.emit("报告已复制到剪贴板。", 3000)
