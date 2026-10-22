"""事件总线弱引用连接（connect_weak）的语义与"不许再写 lambda"的回归防护。

背景：`bus().x.connect(lambda: self.y())` 会被 PySide 整体强引用，闭包里的 self
因此永远释放不掉——窗体 close() 后仍活着、仍继续收信号，曾在"已关闭的面宽原则
窗体收到延迟补发的 currentChanged 后重入 commit()"这条路径上打坏 SQLAlchemy
的提交状态机，最后以随机原生崩溃收场（2026-10-22 排查）。
"""

from __future__ import annotations

import gc
import re
import weakref
from pathlib import Path

from PySide6.QtWidgets import QWidget

from app.core.event_bus import EventBus, connect_weak


class _Receiver:
    """普通 Python 接收者（用来验证弱引用语义）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def handle(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


def test_connect_weak_passes_extra_args_and_ignores_signal_args(qapp) -> None:
    """信号自带的参数被忽略，连接时夹带的常量参数原样传给方法。"""
    signal_bus = EventBus()
    receiver = _Receiver()
    connect_weak(signal_bus.project_opened, receiver, "handle", 7, flag=True)
    signal_bus.project_opened.emit("工程路径.stn2")
    assert receiver.calls == [((7,), {"flag": True})]


def test_connect_weak_keeps_receiver_collectable(qapp) -> None:
    """连接后不得残留强引用：接收者被回收，emit 静默跳过。"""
    signal_bus = EventBus()
    receiver = _Receiver()
    reference = weakref.ref(receiver)
    connect_weak(signal_bus.unit_changed, receiver, "handle", "x")
    del receiver
    gc.collect()
    assert reference() is None, "connect_weak 仍在强引用接收者"
    signal_bus.unit_changed.emit(1)  # 不抛异常即可


def test_connect_weak_survives_destroyed_widget(qapp) -> None:
    """底层 C++ 对象已销毁时，回调静默跳过而不是抛 RuntimeError。"""
    signal_bus = EventBus()
    widget = QWidget()
    connect_weak(signal_bus.project_opened, widget, "setEnabled", True)
    signal_bus.project_opened.emit("p")
    assert widget.isEnabled()
    widget.deleteLater()
    qapp.processEvents()
    signal_bus.project_opened.emit("p")  # 已销毁：不抛异常


def test_missing_method_is_ignored(qapp) -> None:
    """接收者改名/删方法时只跳过，不该炸。"""
    signal_bus = EventBus()
    receiver = _Receiver()
    connect_weak(signal_bus.project_closed, receiver, "no_such_method")
    signal_bus.project_closed.emit()


def test_no_lambda_connected_to_global_bus() -> None:
    """回归防护：视图里不许把 lambda 直接连到全局总线上（会钉死接收者）。"""
    root = Path(__file__).resolve().parents[1] / "src" / "app"
    pattern = re.compile(r"bus\(\)\.[a-z_]+\.connect\(\s*lambda")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(root)}:{number}")
    assert not offenders, "这些位置用了 lambda，请改成 connect_weak 或绑定方法：" + ", ".join(offenders)


def test_main_window_released_after_close(qapp, project) -> None:
    """关掉并释放主窗体后，整棵控件树要能被回收（曾因 lambda 抓 self 而永久泄漏）。

    泄漏量实测（修复前）：每轮 +14 个顶层窗口、+约 370 个 QWidget，且单调增长。
    """
    from PySide6.QtWidgets import QApplication

    from app.views.main_window import MainWindow

    baseline = len(QApplication.allWidgets())
    window = MainWindow()
    window.show()
    qapp.processEvents()
    assert len(QApplication.allWidgets()) > baseline, "主窗体没建出控件树，用例前提不成立"

    window.close()
    del window
    gc.collect()
    qapp.processEvents()
    assert len(QApplication.allWidgets()) == baseline, "主窗体没被回收，又有东西在钉住它"

