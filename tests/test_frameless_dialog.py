"""FramelessDialog 关闭后确定性销毁（2026-10-31 主窗体消失事故的回归防护）。

背景：弹窗关闭后 Python 引用成环（信号回绑、自引用属性），C++ 对象簇一直
赖到 GC；GC 恰好在别的计算路径中途回收时，级联销毁把主窗体原生窗口也拖下水
（21:38 崩溃、22:23 主窗体 HWND 被销毁）。修复：done() 收尾后用 0ms 定时器
排期 deleteLater——析构发生在事件循环的下一拍，永远不等 GC。

两条语义必须同时成立：
- exec() 返回的调用栈上 C++ 仍存活（``wizard.values()`` 读控件不炸）；
- 调用方栈回到主循环后的第一拍，C++ 立即销毁（不再留给 GC）。
"""

from __future__ import annotations

import gc

import shiboken6
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QDialog, QLineEdit

from app.views.widgets.frameless_dialog import FramelessDialog


def _drain(qapp) -> None:
    """完整排干一轮：先派发 0ms 定时器（触发 deleteLater），再投递 deferred delete。"""
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_accept_destroys_cpp_deterministically(qapp):
    """accept() 收尾后 C++ 对象必须被销毁，不能留给 GC。"""
    dlg = FramelessDialog(None, "计算表达式")
    dlg._cycle = dlg  # 模拟 ExpressionDetailDialog 的引用环
    dlg.accept()
    _drain(qapp)
    assert not shiboken6.isValid(dlg)


def test_close_destroys_cpp_deterministically(qapp):
    """点 X（close() → closeEvent → reject → done）收尾后同样确定性销毁。"""
    dlg = FramelessDialog(None, "计算表达式")
    dlg._cycle = dlg
    dlg.show()  # 隐藏窗体的 close() 是空操作，先 show 出来
    dlg.close()
    _drain(qapp)
    assert not shiboken6.isValid(dlg)


def test_gc_after_close_cannot_touch_cpp(qapp):
    """销毁完成后引用环再被 GC 扫到，也只是回收空壳，C++ 不会再死一次。

    这是事故的直接机制：GC 在计算中途回收赖着的弹窗簇时级联销毁原生窗口。
    """
    dlg = FramelessDialog(None, "计算表达式")
    dlg._cycle = dlg
    dlg._keep = [dlg]
    dlg.show()
    dlg.close()
    _drain(qapp)
    assert not shiboken6.isValid(dlg)
    gc.collect()  # 事故现场 GC 触发的等价物
    assert not shiboken6.isValid(dlg)  # 仍是"已销毁"，没有复活/异常


def test_exec_returns_with_cpp_alive_then_destroyed_on_next_pass(qapp):
    """exec() 返回时 C++ 必须存活（新建工程向导 values() 回归），下一拍销毁。

    修复历程：v1 用 WA_DeleteOnClose + deleteLater，两者都在 exec 循环退出的
    瞬间（调用方恢复执行之前）析构 C++，``wizard.values()`` 直接 RuntimeError
    （2026-10-31 新建工程报错）；0ms 定时器把析构推迟到调用方栈返回之后。
    """

    class _Wizard(FramelessDialog):
        def __init__(self) -> None:
            super().__init__(None, "新建工程向导")
            self._name = QLineEdit("默认工程", self)

        def values(self) -> dict:
            return {"name": self._name.text()}  # 读 C++ 控件

    wizard = _Wizard()
    wizard.show()
    QTimer.singleShot(0, wizard.accept)
    code = wizard.exec()
    assert code == QDialog.DialogCode.Accepted
    # exec 返回的调用栈上：C++ 存活，读控件安全
    assert shiboken6.isValid(wizard)
    assert wizard.values() == {"name": "默认工程"}
    # 调用方栈回到主循环后的第一拍：立即销毁，不给 GC 留活口
    _drain(qapp)
    assert not shiboken6.isValid(wizard)
