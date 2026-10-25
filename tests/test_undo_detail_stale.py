"""回归（用户报告）：撤销 / 重做到主表格没有构件（无选中）时，下方管材 /
构件参数等明细面板不得残留上一个构件的内容。

撤销到空表格后 ``_restore_current_element`` 直接返回，此前没有任何路径清理
明细面板——管材 / 构件参数表停留在撤销前选中的那个构件上。
"""

from __future__ import annotations


def test_undo_to_empty_clears_detail_panels(qapp, project) -> None:
    from app.services.element_library import element_library
    from app.views.main_window import MainWindow

    window = MainWindow(str(project))
    qapp.processEvents()
    try:
        unit_item = window._tree_panel._tree.topLevelItem(0).child(0).child(0)
        window._tree_panel._tree.setCurrentItem(unit_item)
        qapp.processEvents()
        panel = window._unit_panel
        table = panel._element_table

        # 插入一条直埋混凝土管：主表格与明细面板（管材 / 构件参数）都已装填
        template = element_library().find("直埋混凝土管", "Ⅱ级混凝土管", 0)
        panel.insert_template(template)
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 1
        assert panel._pipe_table.rowCount() == 1
        assert panel._param_table.rowCount() >= 1
        param_columns_before = panel._param_table.columnCount()

        # 撤销到没有构件的状态（回归点）：明细面板必须清空，不得残留
        window._undo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 0
        assert table.currentRow() == -1
        assert panel._pipe_table.rowCount() == 0
        assert panel._param_table.rowCount() == 0
        # 候选参数列一并撤掉（按上一个构件动态追加的）
        assert panel._param_table.columnCount() == 3
        assert panel._current_detail_id is None
        assert panel._section_view._element_id is None

        # 重做构件回来：明细面板恢复显示该构件
        window._redo()
        qapp.processEvents()
        qapp.processEvents()
        assert table.rowCount() == 1
        assert panel._pipe_table.rowCount() == 1
        assert panel._param_table.rowCount() >= 1
        assert panel._param_table.columnCount() == param_columns_before
        assert panel._section_view._element_id == panel._current_element_id()
    finally:
        window.close()
        qapp.processEvents()
