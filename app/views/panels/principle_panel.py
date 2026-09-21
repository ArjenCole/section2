"""中部：原则编辑器（计划 §7.1，M3 实现）。

围护原则 PE / 地基原则 PF / 围护做法 / 构件公式 / 工作面宽度 / 降水 六个编辑器
将在 M3 按 §4.1 的表结构落地，这里先占位，保证主窗体的 Tab 结构完整。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PrinciplePanel(QWidget):
    """原则编辑器占位面板。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("原则编辑器")
        title.setProperty("role", "panel-title")
        layout.addWidget(title)
        hint = QLabel(
            "M3 实现：围护原则（PE）、地基原则（PF）、围护做法、构件公式、工作面宽度、降水。\n"
            "当前阶段可在项目树中维护标段 / 单位工程，在中部维护构件条目。"
        )
        hint.setProperty("role", "placeholder")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint, 1)
