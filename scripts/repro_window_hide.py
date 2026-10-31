"""最小复现：反复 开→关 FramelessDialog + 引用环 + gc.collect()，观察主窗体是否被 Hide。

用法：.venv\\Scripts\\python.exe scripts\\repro_window_hide.py
"""

from __future__ import annotations

import gc
import os
import sys

os.environ.setdefault("SECTION2_DIAG", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import ctypes  # noqa: E402

from PySide6.QtCore import QEvent, QObject, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow  # noqa: E402

from app.core.window_diag import install as install_window_diag  # noqa: E402
from app.views.widgets.frameless_dialog import FramelessDialog  # noqa: E402


class MainWatcher(QObject):
    def __init__(self, main: QMainWindow) -> None:
        super().__init__(main)
        self.main = main

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.main and event.type() in (
            QEvent.Type.Hide,
            QEvent.Type.Show,
            QEvent.Type.Destroy,
        ):
            import traceback

            print(f"!!! MAIN EVENT: {event.type().name}", flush=True)
            traceback.print_stack()
        return False


def main() -> int:
    app = QApplication(sys.argv)
    install_window_diag(app)
    main = QMainWindow()
    main.setWindowTitle("MAIN")
    main.resize(800, 600)
    main.show()
    main_hwnd = int(main.winId())  # 提前抓原生句柄，之后用 IsWindow 查它是否还活着

    watcher = MainWatcher(main)
    main.installEventFilter(watcher)

    dialogs: list = []

    def open_one(index: int) -> None:
        dlg = FramelessDialog(main, f"计算表达式 #{index}")
        dlg.setModal(True)
        body = dlg.bodyLayout()
        body.addWidget(QLabel(f"对话框 {index}"))
        # 模拟 ExpressionDetailDialog 的引用环：信号连回自身方法 + 自引用属性
        dlg._cycle = dlg
        dlg._keep = [dlg]
        QTimer.singleShot(120, dlg.close)
        dlg.exec()
        dialogs.append(dlg)  # 出了函数仍被列表引用？不——函数返回后局部清空，
        dialogs.clear()      # 这里 clear 模拟 _show_expression_detail 返回后无强引用

    def run() -> None:
        for i in range(8):
            open_one(i)
            gc.collect()  # 模拟计算路径中触发的 GC
            alive = main.isVisible()
            native_alive = bool(
                ctypes.windll.user32.IsWindow(ctypes.c_void_p(main_hwnd))
            )
            print(f"[{i}] after close+gc: main.isVisible={alive} "
                  f"native HWND alive={native_alive}", flush=True)
            if not alive:
                print(">>> 复现成功：主窗体被 Hide，进程还活着", flush=True)
                print(">>> 不退出，保持 10 秒观察进程…", flush=True)
                QTimer.singleShot(10000, app.quit)
                return
        print(">>> 未复现：8 轮后主窗体仍然可见", flush=True)
        app.quit()

    QTimer.singleShot(300, run)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
