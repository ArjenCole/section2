"""AI 面板附件：拖拽上传（毛玻璃悬浮层）与输入框左上角附件片。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QDragLeaveEvent

from app.views.panels.ai_panel import AiPanel


class _FakeDragEvent:
    """拖拽事件替身：只实现面板处理器用到的接口。

    本机 PySide6 6.11.2 从 Python 构造 QDragEnterEvent / QDropEvent 会段错误
    （绑定层问题，运行时事件由 Qt 内部构造不受影响），因此测试不构造真实事件。
    """

    def __init__(self, mime: QMimeData) -> None:
        self._mime = mime
        self._accepted = False

    def mimeData(self) -> QMimeData:
        return self._mime

    def acceptProposedAction(self) -> None:
        self._accepted = True

    def ignore(self) -> None:
        self._accepted = False

    def isAccepted(self) -> bool:
        return self._accepted


def _make_panel() -> AiPanel:
    panel = AiPanel()
    panel.resize(360, 500)
    panel.layout().activate()
    return panel


def _file_mime(paths: list[Path]) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


def test_drag_with_file_shows_frosted_overlay(qapp, tmp_path) -> None:
    panel = _make_panel()
    source = tmp_path / "参数.csv"
    source.write_text("名称,数量\n排水管,10", encoding="utf-8")

    event = _FakeDragEvent(_file_mime([source]))
    panel.dragEnterEvent(event)

    assert event.isAccepted()
    assert not panel._drop_overlay.isHidden()
    assert panel._drop_overlay.size() == panel.size()  # 覆盖整个面板
    assert panel._drop_overlay._backdrop is not None  # 毛玻璃底图已生成

    panel.dragLeaveEvent(QDragLeaveEvent())
    assert panel._drop_overlay.isHidden()


def test_drag_without_files_ignored(qapp) -> None:
    panel = _make_panel()
    mime = QMimeData()
    mime.setText("普通文本拖拽")

    event = _FakeDragEvent(mime)
    panel.dragEnterEvent(event)

    assert not event.isAccepted()
    assert panel._drop_overlay.isHidden()


def test_drop_adds_chip_inside_input_top_left(qapp, tmp_path) -> None:
    panel = _make_panel()
    source = tmp_path / "清单.csv"
    source.write_text("名称,数量\n排水管,10", encoding="utf-8")

    panel.dropEvent(_FakeDragEvent(_file_mime([source])))

    assert [item["name"] for item in panel._attachments] == ["清单.csv"]
    assert len(panel._attachment_chips) == 1
    chip = panel._attachment_chips[0]
    assert chip.parent() is panel._input  # 附件片在输入框内部
    assert 0 <= chip.x() < panel._input.width() // 2
    assert 0 <= chip.y() < panel._input.height() // 2
    # 正文让位：顶部留白被附件片撑开
    assert panel._input.viewportMargins().top() > 0
    assert panel._drop_overlay.isHidden()


def test_add_skips_duplicate_and_unreadable_files(qapp, tmp_path) -> None:
    panel = _make_panel()
    source = tmp_path / "参数.txt"
    source.write_text("埋深 2.5", encoding="utf-8")
    binary = tmp_path / "模型.bin"
    binary.write_bytes(b"\x00\x01\x02")

    panel._add_attachment_paths([str(source), str(binary), str(source)])

    assert [item["name"] for item in panel._attachments] == ["参数.txt"]


def test_panel_is_drop_target_and_text_views_do_not_swallow(qapp) -> None:
    panel = _make_panel()
    assert panel.acceptDrops()  # 整个面板都是拖拽区
    # 文本控件及其视口默认接受拖放，必须让位，否则拖到输入框/消息区会被吃掉
    assert not panel._input.acceptDrops()
    assert not panel._input.viewport().acceptDrops()
    panel._append_message("user", "你好")
    view = panel._bubbles[0]._content_view
    assert not view.acceptDrops()
    assert not view.viewport().acceptDrops()


def test_remove_chip_restores_input_margins(qapp, tmp_path) -> None:
    panel = _make_panel()
    source = tmp_path / "参数.txt"
    source.write_text("埋深 2.5", encoding="utf-8")
    panel._add_attachment_paths([str(source)])

    chip = panel._attachment_chips[0]
    chip.removed.emit(panel._attachments[0])

    assert panel._attachments == []
    assert panel._attachment_chips == []
    assert panel._input.viewportMargins().top() == 0
