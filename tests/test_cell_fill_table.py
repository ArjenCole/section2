"""CellFillTable 延迟补位回调的生命周期回归测试。

复现并回归 Windows 上公式编辑窗体（ComponentEditDialog）点确定/取消后的
``RuntimeError: libshiboken: Internal C++ object (CellFillTable) already deleted``：

表格每次布局结束都会调度一个 ``singleShot(0)`` 延迟校准回调；外层原则窗体关闭
销毁时 C++ 子树（含公式编辑窗体与它的三张表）一并析构，若挂起回调未绑定接收者
上下文，会在对象死后触发并弹错误窗（修复：singleShot 绑定接收者 + 兜底守卫）。
"""

import sys

from PySide6.QtCore import QEvent


def test_component_edit_dialog_close_no_dead_callback(qapp, project, monkeypatch) -> None:
    """完全复刻应用调用链：原则窗体 exec → 公式编辑 exec → 确定 → 外层关闭销毁。

    修复前：3 张表的挂起回调各在死对象上触发一次（dead_fires == 3）；修复后为 0。
    """
    from app.services import project_io
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog
    from app.views.dialogs.principle_dialogs import ComponentEditDialog

    errors: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda t, v, tb: errors.append(v))

    # 记录在已销毁 C++ 对象上触发的回调（修复前：3 张表各一条；修复后：0）
    from app.views.widgets import cell_fill_table as cell_fill_module

    dead_fires: list = []
    orig_once = cell_fill_module.CellFillTable._fit_editors_once

    def traced_once(table):
        import shiboken6

        if not shiboken6.isValid(table):
            dead_fires.append(table)
            return None
        return orig_once(table)

    monkeypatch.setattr(cell_fill_module.CellFillTable, "_fit_editors_once", traced_once)

    # 打开外层原则窗体（真实应用为 principle_bar 的临时对象 + exec）
    enclosure = project_io.enclosures()[0]
    outer = EnclosureEditDialog(enclosure.id)
    outer.show()
    qapp.processEvents()
    work = outer._enclosure().works_sorted()[0]

    # 打开公式编辑窗体并布局（触发 updateEditorGeometries → 调度挂起回调）
    sub = ComponentEditDialog(work.levels[0].components[0], outer)
    sub.show()
    qapp.processEvents()

    # 点确定关闭公式编辑窗体（exec 返回后其局部包裹器在调用方离开作用域时回收）
    sub._accept()
    qapp.processEvents()
    outer._fill()
    qapp.processEvents()

    # 关闭外层窗体 → C++ 子树（含公式编辑窗体与三张表）析构
    outer._confirm()
    outer.hide()
    # 模拟真实 Windows 上关闭序列中的最后一轮布局调度（三张表各挂起一个回调）
    for pending_table in sub._tables.values():
        pending_table._fit_cell_widgets()
    outer.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # 强制完成销毁
    import shiboken6

    table = next(iter(sub._tables.values()))
    assert not shiboken6.isValid(table)
    qapp.processEvents()  # 挂起回调若未绑定接收者，会在此打到已删除对象
    qapp.processEvents()
    assert not dead_fires
    assert errors == []


def test_fit_editors_once_guarded_after_deletion(qapp, project) -> None:
    """兜底防线：C++ 对象已删除时直接触发回调也不得抛 RuntimeError。"""
    import shiboken6

    from app.services import project_io
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog
    from app.views.dialogs.principle_dialogs import ComponentEditDialog
    from app.views.widgets import cell_fill_table as module

    enclosure = project_io.enclosures()[0]
    outer = EnclosureEditDialog(enclosure.id)
    outer.show()
    qapp.processEvents()
    work = outer._enclosure().works_sorted()[0]
    sub = ComponentEditDialog(work.levels[0].components[0], outer)
    sub.show()
    qapp.processEvents()
    table = next(iter(sub._tables.values()))
    sub.hide()
    outer.hide()
    outer.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # 强制完成销毁
    assert not shiboken6.isValid(table)
    # 死对象上直接触发回调：兜底守卫必须吞掉，不得抛 libshiboken RuntimeError
    module.CellFillTable._fit_editors_once(table)  # type: ignore[arg-type]
