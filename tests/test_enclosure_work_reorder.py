"""围护原则窗体做法表：拖动行调序（一次只拖一行）。

拖拽本身是模态循环，离屏用例里不能真跑，所以分三层验证：
* ``_move_work_row``：行顺序与埋深阈值的重排口径（顺序变了阈值升序贴回）；
* ``_WorkTable`` 的落点解析 / 单行抓取 / 拖拽循环后再落地（不重建表格）；
* 信号接线：``row_move_requested`` → 对话框重排。
"""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest


def _enclosure_id() -> int:
    from app.services import project_io

    return project_io.enclosures()[0].id


def _dialog_with_works(count: int):
    """开窗并追加做法到 ``count`` 行（埋深 0 / 3.5 / 7 / …）。"""
    from app.views.dialogs.enclosure_edit_dialog import EnclosureEditDialog

    dialog = EnclosureEditDialog(_enclosure_id())
    for _ in range(count - 1):
        dialog._insert_work()
    return dialog


def _ids(dialog) -> list[int]:
    return [work.id for work in dialog._enclosure().works_sorted()]


def _depths(dialog) -> list[float]:
    return [work.min_depth for work in dialog._enclosure().works_sorted()]


def test_move_work_row_reorders_and_reassigns_depths(qapp, project):
    dialog = _dialog_with_works(4)
    try:
        before = _ids(dialog)
        assert _depths(dialog) == [0.0, 3.5, 7.0, 10.5]

        # 末行拖到最前：顺序整体后移一位，阈值仍升序贴回（首行恒 0）
        dialog._work_table.row_move_requested.emit(3, 0)
        works = dialog._enclosure().works_sorted()
        assert [work.id for work in works] == [before[3], before[0], before[1], before[2]]
        assert [work.min_depth for work in works] == [0.0, 3.5, 7.0, 10.5]
        assert [work.order_no for work in works] == [0, 1, 2, 3]
        # 表格回显：首行是被拖来的做法、范围列跟着新顺序、移动行保持选中
        table = dialog._work_table
        assert table.item(0, 0).data(Qt.ItemDataRole.UserRole) == before[3]
        assert [table.item(row, 1).text() for row in range(4)] == [
            "3.5", "7", "10.5", "+∞",
        ]
        assert table.currentRow() == 0

        # 再把它往下拖两格（插到第 3 行之前）：只动这一行，其余顺序不变
        dialog._work_table.row_move_requested.emit(0, 3)
        works = dialog._enclosure().works_sorted()
        assert [work.id for work in works] == [before[0], before[1], before[3], before[2]]
        assert [work.min_depth for work in works] == [0.0, 3.5, 7.0, 10.5]
        assert dialog._work_table.currentRow() == 2
    finally:
        dialog.close()


def test_move_work_row_ignores_in_place_and_bad_rows(qapp, project):
    dialog = _dialog_with_works(3)
    try:
        before = _ids(dialog)
        # 插到自己前面 / 后面都是原地：不动
        dialog._work_table.row_move_requested.emit(1, 1)
        dialog._work_table.row_move_requested.emit(1, 2)
        # 越界源行 / 目标行：不崩、不动
        dialog._work_table.row_move_requested.emit(-1, 0)
        dialog._work_table.row_move_requested.emit(9, 0)
        assert _ids(dialog) == before
        assert _depths(dialog) == [0.0, 3.5, 7.0]
    finally:
        dialog.close()


class _FakeDropEvent:
    """只实现 ``dropEvent`` 用到的接口（离屏下拿不到真的拖拽 source）。"""

    def __init__(self, source, pos: QPointF) -> None:
        self._source = source
        self._pos = pos
        self.accepted = False
        self.ignored = False

    def source(self):
        return self._source

    def position(self) -> QPointF:
        return self._pos

    def acceptProposedAction(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


def test_work_table_press_captures_single_row(qapp, project):
    dialog = _dialog_with_works(3)
    try:
        dialog.show()
        qapp.processEvents()
        table = dialog._work_table
        # 多选状态下按第 1 行：只记这一行（一次只拖一行）
        table.selectAll()
        qapp.processEvents()
        point = table.visualRect(table.model().index(1, 0)).center()
        QTest.mousePress(
            table.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, point,
        )
        qapp.processEvents()
        assert table._drag_row == 1
        QTest.mouseRelease(
            table.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, point,
        )
        qapp.processEvents()
        # 按在末行下方的空白区：没有可拖的行
        blank = QPoint(5, table.visualRect(table.model().index(2, 0)).bottom() + 20)
        assert blank.y() < table.viewport().height()
        QTest.mousePress(
            table.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, blank,
        )
        qapp.processEvents()
        assert table._drag_row is None
        QTest.mouseRelease(
            table.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, blank,
        )
    finally:
        dialog.close()


def test_work_table_start_drag_needs_pressed_row(qapp, project):
    dialog = _dialog_with_works(2)
    try:
        dialog.show()
        qapp.processEvents()
        table = dialog._work_table
        # 没有按下行 / 行号越界：直接返回，不进入模态拖拽循环
        table._drag_row = None
        table.startDrag(Qt.DropAction.MoveAction)
        table._drag_row = table.rowCount()
        table.startDrag(Qt.DropAction.MoveAction)
        assert table._pending_move is None
    finally:
        dialog.close()


def test_work_table_resolve_drop(qapp, project):
    dialog = _dialog_with_works(4)
    try:
        dialog.show()
        qapp.processEvents()
        table = dialog._work_table
        row2 = table.visualRect(table.model().index(2, 0))

        # 第 2 行上半 → 插到第 2 行之前，落点线画在行顶
        table._drag_row = 0
        assert table._resolve_drop(QPoint(5, row2.top() + 2)) == (2, row2.top())
        # 第 2 行下半 → 插到第 2 行之后，落点线画在行底
        assert table._resolve_drop(QPoint(5, row2.bottom() - 2)) == (3, row2.bottom() + 1)
        # 拖到自己身上（上下半都算原地）→ 没有落点
        table._drag_row = 2
        assert table._resolve_drop(QPoint(5, row2.top() + 2)) is None
        assert table._resolve_drop(QPoint(5, row2.bottom() - 2)) is None
        # 拖到末行下方空白区 → 追加到末尾
        table._drag_row = 0
        last = table.visualRect(table.model().index(3, 0))
        assert table._resolve_drop(QPoint(5, last.bottom() + 20)) == (4, last.bottom() + 1)
        # 末行自己拖到空白区 → 原地
        table._drag_row = 3
        assert table._resolve_drop(QPoint(5, last.bottom() + 20)) is None
        # 没有按下行 → 没有落点
        table._drag_row = None
        assert table._resolve_drop(QPoint(5, row2.center().y())) is None
    finally:
        dialog.close()


def test_work_table_drop_defers_move_until_drag_loop_ends(qapp, project):
    dialog = _dialog_with_works(4)
    try:
        dialog.show()
        qapp.processEvents()
        table = dialog._work_table
        moves: list[tuple[int, int]] = []
        table.row_move_requested.connect(lambda source, insert: moves.append((source, insert)))

        before = _ids(dialog)
        table._drag_row = 3
        row0 = table.visualRect(table.model().index(0, 0))
        event = _FakeDropEvent(table, QPointF(5, row0.top() + 2))
        table.dropEvent(event)
        # 拖拽循环里只记意图（重建表格要等 exec 返回），先不动数据
        assert event.accepted
        assert table._pending_move == (3, 0)
        assert moves == []
        assert _ids(dialog) == before
        assert table._drop_line_y is None
        # 循环结束（startDrag 里 exec 返回后）才发信号 → 对话框重排
        table._consume_pending_move()
        assert moves == [(3, 0)]
        assert table._pending_move is None
        assert _ids(dialog) == [before[3], before[0], before[1], before[2]]

        # 原地松手 / 外部来源：都不产生移动
        table._drag_row = 1
        row1 = table.visualRect(table.model().index(1, 0))
        event = _FakeDropEvent(table, QPointF(5, row1.top() + 2))
        table.dropEvent(event)
        assert table._pending_move is None
        table._drag_row = 1
        foreign = _FakeDropEvent(object(), QPointF(5, row0.top() + 2))
        table.dropEvent(foreign)
        assert foreign.ignored and table._pending_move is None
        assert moves == [(3, 0)]
    finally:
        dialog.close()


def test_work_table_full_drag_moves_pressed_row_only(qapp, project, monkeypatch):
    """整条链路：按下 → 移动（Qt 调 startDrag）→ 落点投递 → exec 返回后重排。

    拖拽的模态循环用替身 ``QDrag`` 顶掉（exec 里同步投递 dropEvent，与 Qt 一致），
    离屏也能跑完整流程；多选状态下也只拖按下的那一行。
    """
    import app.views.dialogs.enclosure_edit_dialog as module

    recorded: dict = {}

    class _FakeDrag:
        drop_pos = QPoint(5, 0)

        def __init__(self, source) -> None:
            self._source = source
            recorded["drag"] = self

        def setMimeData(self, mime) -> None:
            self.mime = mime

        def setPixmap(self, pixmap) -> None:
            self.pixmap = pixmap

        def setHotSpot(self, point) -> None:
            self.hotspot = point

        def exec(self, *_args) -> Qt.DropAction:
            # Qt 在 exec 的模态循环里投递 dragMove / drop：这里直接投 drop
            self._source.dropEvent(_FakeDropEvent(self._source, QPointF(_FakeDrag.drop_pos)))
            return Qt.DropAction.MoveAction

    monkeypatch.setattr(module, "QDrag", _FakeDrag)

    dialog = _dialog_with_works(4)
    try:
        dialog.show()
        qapp.processEvents()
        table = dialog._work_table
        before = _ids(dialog)

        # 全选后按第 3 行往第 0 行上方拖：只移动按下的那一行
        table.selectAll()
        qapp.processEvents()
        _FakeDrag.drop_pos = QPoint(5, table.visualRect(table.model().index(0, 0)).top() + 2)
        start = table.visualRect(table.model().index(3, 0)).center()
        QTest.mousePress(
            table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start,
        )
        qapp.processEvents()
        QTest.mouseMove(table.viewport(), start + QPoint(0, 40))
        qapp.processEvents()
        QTest.mouseRelease(
            table.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, start + QPoint(0, 40),
        )
        qapp.processEvents()

        # 拖拽影像与 MIME 都只带这一行
        drag = recorded["drag"]
        assert drag.mime.data(module._WORK_ROW_MIME) == b"3"
        assert drag.pixmap.height() == table.rowHeight(0) * (table.devicePixelRatioF() or 1.0)
        # 顺序只动这一行，阈值仍升序；拖拽状态已清空
        assert _ids(dialog) == [before[3], before[0], before[1], before[2]]
        assert _depths(dialog) == [0.0, 3.5, 7.0, 10.5]
        assert table.currentRow() == 0
        assert table._drag_row is None
        assert table._pending_move is None
        assert table._drop_line_y is None
    finally:
        dialog.close()


def test_work_table_drop_line_paints_accent_color(qapp, project):
    from PySide6.QtGui import QColor

    from app.resources.qss.theme import ThemeManager

    dialog = _dialog_with_works(3)
    try:
        dialog.show()
        qapp.processEvents()
        table = dialog._work_table
        y = table.visualRect(table.model().index(1, 0)).top()
        table._set_drop_line(y)
        assert table._drop_line_y == y
        image = table.viewport().grab().toImage()
        expected = QColor(ThemeManager.instance().current().border_focus).name()
        assert expected in {image.pixelColor(5, y).name(), image.pixelColor(5, y + 1).name()}
        # 清掉落点线：恢复表格本身（不再有强调色横线）
        table._set_drop_line(None)
        image = table.viewport().grab().toImage()
        assert expected not in {
            image.pixelColor(5, y).name(), image.pixelColor(5, y + 1).name(),
        }
    finally:
        dialog.close()
