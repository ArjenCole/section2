"""写操作确认策略（计划 §8.3 / 风险 4）：AI 的写操作一律弹确认窗。

工作线程里通过 :class:`ConfirmBridge` 发起确认请求：Signal 以排队方式投递到
界面线程弹窗，用户答复后放行工作线程继续执行。
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class ConfirmBridge(QObject):
    """跨线程确认桥：worker 调 ask()，界面槽弹窗并回填结果。"""

    request = Signal(str)  # 确认说明文本

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._event: threading.Event | None = None
        self._answer = False

    def ask(self, description: str) -> bool:
        """工作线程调用：阻塞直到用户答复。"""
        self._event = threading.Event()
        self._answer = False
        self.request.emit(description)
        self._event.wait(timeout=300)
        return self._answer

    # 界面线程调用
    def answer(self, approved: bool) -> None:
        self._answer = approved
        if self._event is not None:
            self._event.set()
