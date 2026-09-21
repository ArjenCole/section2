"""中部：汇总页（计划 §7.1，M5 实现）。

选中项目树根节点时显示：量 × 单价 = 合价，单价字典可编辑。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.core.event_bus import bus
from app.services import project_io


class SummaryPanel(QWidget):
    """汇总页占位面板（显示工程基本信息，量价汇总在 M5 补齐）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self._title = QLabel("工程汇总")
        self._title.setProperty("role", "panel-title")
        layout.addWidget(self._title)
        self._info = QLabel("")
        self._info.setProperty("role", "hint")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)
        hint = QLabel("M5 实现：按构件汇总工程量 × 单价 = 合价，并支持编辑单价字典。")
        hint.setProperty("role", "placeholder")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint, 1)

        bus().project_opened.connect(lambda _path: self.refresh())
        bus().project_closed.connect(self.refresh)
        bus().tree_structure_changed.connect(self.refresh)
        bus().unit_changed.connect(lambda _unit_id: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        info = project_io.basic_info()
        if info is None:
            self._title.setText("工程汇总")
            self._info.setText("尚未打开工程。")
            return
        self._title.setText(info.project_name or "工程汇总")
        segments = project_io.segments()
        unit_count = sum(len(project_io.units(segment.id)) for segment in segments)
        self._info.setText(
            f"项目编号：{info.project_index or '-'}　编制人：{info.author or '-'}　"
            f"通用图集：{info.atlas_name or '-'}　标段数：{len(segments)}　单位工程数：{unit_count}"
        )
