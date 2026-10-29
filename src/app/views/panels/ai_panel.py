"""右侧：AI 助手面板（复刻 Quotor views/panels/ai_panel.py，M7 对话 + M8 工具调用）。

结构与交互照抄 Quotor：

* 消息区 = QScrollArea + 容器布局，每条消息一个独立控件：
  - :class:`_MessageBubble` —— 角色标签（用户=主色 / AI 助手=success / 错误=danger）
    + :class:`_MarkdownView`（高度随文档自适应；AI 用 Markdown，用户/错误转义 <pre>）；
  - :class:`_ThinkingBlock` —— 可折叠思考块，"思考中…" 400ms 动画，工具调用与
    流式正文就地刷新；
* 输入区 = QPlainTextEdit#aiInputEdit（圆角、右下角 overlay 模型来源选择器
  #aiSourceBtn + 发送按钮 #aiSendBtn），Enter 发送、Shift/Ctrl+Enter 换行；
  - 模型来源选择器显示「provider 显示名/当前模型」+ 下箭头，点击向上弹出菜单；
    菜单上半部分是 AI 设置左侧的 provider 列表，底部「管理模型」打开设置窗体；
  - 左下角 📎 按钮或把文件拖到面板任意位置上传（Excel / Word / CSV / 文本…）：
    拖拽悬停时整块面板盖一层毛玻璃（:class:`_DropOverlay`，居中提示
    “松开以添加附件”）；文件在本地提取为文本后，以圆角附件片挂在输入框
    左上角。带附件发送走**两段式**：先调一次模型按
    提示词把文件内容提炼成结构化数据（_ExtractionWorker，后台线程、无工具），
    再把「提取数据 + 用户要求」并入用户消息交给 AgentLoop 操作软件——
    提取数据保留在对话历史里，后续追问可直接引用；
* 顶部：标题 + 「清空」（兼停止，运行中点击即中断）+ 齿轮「设置」。

agent 层沿用本项目的 AgentLoop（content/reasoning/status/finished/failed/confirm 信号）。
"""

from __future__ import annotations

import html
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.agent.agent_loop import AgentLoop
from app.agent.context import current as current_agent_context
from app.agent.tool_registry import default_registry
from app.core.config import get_config, set_ai_active_provider
from app.core.event_bus import bus, connect_weak
from app.resources.qss.theme import ThemeManager, combo_arrow_renderer
from app.services.ai import ai_keychain
from app.services.ai.ai_provider import (
    AiProviderError,
    ChatMessage,
    ProviderConfig,
    default_send_reasoning_content,
    new_session_id,
    stream_chat,
)
from app.services.ai.file_extract import FILE_DIALOG_FILTER, FileExtractError, extract_text
from app.views.widgets.frameless_dialog import FramelessMessageBox, load_icon

_SYSTEM_PROMPT = (
    "你是 Section 2.0（市政管道等线性工程工程量计算软件）的助手。"
    "你可以调用工具操作工程数据；涉及新增/修改/删除时，写操作会先弹确认卡。"
    "回答用简体中文，简明扼要；涉及工程量计算时引用工具返回的计算表达式。\n"
    "核心约束：禁止编造 id/原则名（必须先查询再写）；埋深/数量/参数值/管材含量可写算式原文"
    "（如 2.5+0.3），不要把算式预计算后回写；计算结果的 expression/steps 原样引用、不要改写；"
    "用户取消操作后不要重试同一工具。"
)

#: 附件提取阶段（第一段）的提示词：只提炼数据，不操作软件（此阶段无工具）
_EXTRACT_SYSTEM_PROMPT = (
    "你是工程量计算软件 Section 2.0 的数据提取助手。用户上传了文件并给出要求，"
    "请只依据文件内容，围绕用户的要求把相关数据提炼成干净、结构化的结果"
    "（优先 Markdown 表格或 JSON），供后续步骤据此操作软件："
    "构件名称、管材与管径、埋深、数量、原则名等字段逐条对应、不要合并同类项；"
    "文件里没有的信息标注“未提供”，禁止编造；数字保持原文写法"
    "（算式原样保留、不要预计算、不要换单位）。"
    "只输出提取结果本身，不要寒暄，也不要复述用户的要求。"
)


#: 附件片在输入框内左上角的排列参数：起始留白 / 片间距 / 文件名省略宽度
_CHIP_MARGIN = 8
_CHIP_GAP = 4
_CHIP_NAME_MAX = 150

#: 输入框基础高度；实际高度 = 基础高度 + 3 行行高（见 _apply_input_height）
_INPUT_BASE_HEIGHT = 108

#: 拖拽悬停时毛玻璃层中间的提示文字
_DROP_HINT = "松开以添加附件"


def _c():
    return ThemeManager.instance().current()


class _MarkdownView(QTextBrowser):
    """高度随文档内容自动撑开的 Markdown 视图（Quotor 同款技巧）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptDrops(False)  # 文件拖拽统一冒泡给 AiPanel，别被文本框吃掉
        self.viewport().setAcceptDrops(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(0)
        # 必须控件级清零：主题 QSS 对输入类控件设了 padding，否则视口比文档矮 → 内容截断
        self.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; padding: 0px; margin: 0px; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.document().documentLayout().documentSizeChanged.connect(self._apply_height)

    def _apply_height(self, size) -> None:
        height = int(size.height()) + 4  # 余量防下伸部被裁
        if self.minimumHeight() != height or self.maximumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        # 宽度变化 → 延迟一拍重算换行高度
        QTimer.singleShot(0, lambda: self._apply_height(self.document().size()))


class _MessageBubble(QWidget):
    """一条消息：角色标签 + 内容（AI 用 Markdown，用户/错误转义纯文本）。"""

    def __init__(self, role: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._role = role
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 4)
        layout.setSpacing(4)

        self._role_label = QLabel()
        self._role_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._role_label)

        self._content_view = _MarkdownView()
        layout.addWidget(self._content_view)

        self._raw_text = ""
        self._refresh_role_label()
        self.set_text(text)

    def _refresh_role_label(self) -> None:
        colors = _c()
        if self._role == "user":
            label, color = "用户", colors.primary
        elif self._role == "error":
            label, color = "错误", colors.danger
        else:
            label, color = "AI 助手", colors.success
        self._role_label.setText(
            f'<span style="color:{color};font-weight:600;">{label}</span>'
        )

    def set_text(self, text: str) -> None:
        self._raw_text = text
        if self._role == "ai":
            self._content_view.setMarkdown(text)
        else:
            self._content_view.setHtml(
                '<pre style="margin:0;font-family:inherit;white-space:pre-wrap;">'
                f"{html.escape(text)}</pre>"
            )

    def refresh_theme(self) -> None:
        self._refresh_role_label()


class _ThinkingBlock(QWidget):
    """可折叠思考块：同一轮对话的思考/工具调用/流式正文累积在同一块里。"""

    def __init__(self, title: str = "思考过程", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stream_label: QLabel | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        colors = _c()
        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setStyleSheet(
            "QToolButton { border: none; background: transparent; text-align: left;"
            f" color: {colors.text_secondary}; font-weight: 600; padding: 2px; }}\n"
            "QToolButton:hover { background: transparent; }"
        )
        self._toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self._toggle)

        self._content = QFrame()
        self._content.setStyleSheet(
            f"QFrame {{ border: none; border-left: 2px solid {colors.border};"
            " margin-left: 8px; }"
        )
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 0, 0, 0)
        self._content_layout.setSpacing(2)
        self._content.setVisible(False)
        layout.addWidget(self._content)

        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(400)
        self._thinking_timer.timeout.connect(self._on_thinking_tick)
        self._thinking_dots = 0
        self._status_label: QLabel | None = None

    def _on_toggle(self, checked: bool) -> None:
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self._content.setVisible(checked)

    def _ensure_status_label(self) -> QLabel:
        if self._status_label is None:
            self._status_label = QLabel()
            self._status_label.setWordWrap(True)
            self._status_label.setTextFormat(Qt.TextFormat.RichText)
            self._content_layout.addWidget(self._status_label)
        return self._status_label

    def start_thinking(self) -> None:
        self._thinking_dots = 0
        self._thinking_timer.start()
        self._ensure_status_label().setText(self._thinking_text())

    def stop_thinking(self) -> None:
        self._thinking_timer.stop()
        if self._status_label is not None:
            self._status_label.setText(
                f'<span style="color:{_c().text_secondary};font-weight:600;">思考完成</span>'
            )

    def _thinking_text(self) -> str:
        dots = "." * (self._thinking_dots + 1)
        return f'<span style="color:{_c().text_secondary};">思考中{dots}</span>'

    def _on_thinking_tick(self) -> None:
        self._thinking_dots = (self._thinking_dots + 1) % 3
        if self._status_label is not None:
            self._status_label.setText(self._thinking_text())

    def set_stream_text(self, text: str) -> None:
        """流式正文就地刷新（Quotor 同款：反复 setText 同一个 QLabel）。"""
        if self._stream_label is None:
            self._stream_label = QLabel()
            self._stream_label.setWordWrap(True)
            self._stream_label.setTextFormat(Qt.TextFormat.PlainText)
            self._stream_label.setStyleSheet(f"color: {_c().text_primary};")
            self._content_layout.addWidget(self._stream_label)
        self._stream_label.setText(text)

    def rotate_stream_label(self) -> None:
        """换轮/重试时丢弃旧流式标签，下次 set_stream_text 重建。"""
        self._stream_label = None

    def append_html(self, rich_text: str) -> None:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setText(rich_text)
        self._content_layout.addWidget(label)


class _InputEdit(QPlainTextEdit):
    """输入框：Enter 发送，Shift/Ctrl+Enter 换行（Quotor 同款）。"""

    submitted = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
                self.insertPlainText("\n")
                return
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class _SourceButton(QPushButton):
    """模型来源按钮：左侧文字 + 右侧与 AI 设置「默认模型」下拉框同款箭头。"""

    ARROW_SIZE = 12
    ARROW_RIGHT = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._arrow_key: tuple[str, bool] | None = None
        self._arrow_renderer: QSvgRenderer | None = None

    def _arrow_svg(self) -> QSvgRenderer:
        colors = _c()
        key = (colors.name, self.isEnabled())
        if self._arrow_key != key or self._arrow_renderer is None:
            color = colors.text_secondary if self.isEnabled() else colors.text_disabled
            self._arrow_renderer = combo_arrow_renderer(color)
            self._arrow_key = key
        return self._arrow_renderer

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().paintEvent(event)
        painter = QPainter(self)
        x = self.width() - self.ARROW_SIZE - self.ARROW_RIGHT
        y = (self.height() - self.ARROW_SIZE) // 2
        self._arrow_svg().render(
            painter, QRectF(x, y, self.ARROW_SIZE, self.ARROW_SIZE)
        )
        painter.end()


def _frosted_backdrop(snapshot: QPixmap) -> QPixmap:
    """把面板快照模糊成毛玻璃底图（按设备像素处理，DPR 原样带回）。"""
    image = snapshot.toImage()
    dpr = snapshot.devicePixelRatio() or 1.0
    image.setDevicePixelRatio(1.0)  # 场景坐标 = 设备像素，避免 DPR 二次缩放
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    effect = QGraphicsBlurEffect()
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    effect.setBlurRadius(18.0 * dpr)  # 视觉半径不随缩放比例变化
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    result = QPixmap(image.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(
        painter,
        QRectF(result.rect()),
        QRectF(0.0, 0.0, float(image.width()), float(image.height())),
    )
    painter.end()
    result.setDevicePixelRatio(dpr)
    return result


class _DropOverlay(QWidget):
    """拖拽文件悬停时盖住整个面板的毛玻璃层（ZCode 同款交互）。

    底图是开始拖拽瞬间的面板快照，高斯模糊后再压一层主题背景色，保证
    居中提示可读。本层 WA_TransparentForMouseEvents：拖拽事件继续由
    :class:`AiPanel` 接收，面板在 drop / leave 时负责隐藏本层。
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._backdrop: QPixmap | None = None
        self.hide()

    def set_backdrop(self, snapshot: QPixmap) -> None:
        self._backdrop = _frosted_backdrop(snapshot)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        if self._backdrop is not None:
            painter.drawPixmap(0, 0, self._backdrop)
        colors = _c()
        tint = QColor(colors.bg_window)
        tint.setAlpha(170)
        painter.fillRect(self.rect(), tint)
        font = self.font()
        font.setPointSizeF(font.pointSizeF() + 1.0)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(colors.text_primary))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _DROP_HINT)
        painter.end()


class _AttachmentChip(QFrame):
    """输入框左上角的一枚文件片：圆角框内文件图标 + 文件名 + 「×」移除。"""

    removed = Signal(object)  # attachment dict

    def __init__(self, attachment: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._attachment = attachment
        colors = _c()
        self.setStyleSheet(
            "QFrame { background: transparent; border: 1px solid"
            f" {colors.border}; border-radius: 10px; }}\n"
            "QFrame QLabel { background: transparent; border: none; }\n"
            "QFrame QToolButton { background: transparent; border: none;"
            f" color: {colors.text_secondary}; font-weight: 600; }}\n"
            f"QFrame QToolButton:hover {{ color: {colors.text_primary}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)
        icon = QLabel()
        icon.setPixmap(
            load_icon("file-text", color=colors.text_secondary, size=14).pixmap(14, 14)
        )
        layout.addWidget(icon)
        name_label = QLabel()
        # 文件名过长时省略（完整路径在 tooltip 里），免得一枚附件片撑满整行
        name_label.setText(
            name_label.fontMetrics().elidedText(
                str(attachment["name"]), Qt.TextElideMode.ElideRight, _CHIP_NAME_MAX
            )
        )
        name_label.setToolTip(str(attachment["path"]))
        layout.addWidget(name_label)
        close = QToolButton()
        close.setText("×")
        close.setFixedSize(16, 16)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setToolTip("移除该文件")
        close.clicked.connect(lambda: self.removed.emit(self._attachment))
        layout.addWidget(close)


class _ExtractionWorker(QObject):
    """附件流程第一段（后台线程）：按提示词把上传文件内容提炼成结构化数据。

    只发 content / finished / failed 三个信号（跨线程 queued），不碰任何
    控件；「清空」会 cancel()，之后剩余的流式回调静默丢弃、不再发信号。
    该阶段不带工具——先拿到干净的数据，第二段才交给 AgentLoop 操作软件。
    """

    content = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        provider: ProviderConfig,
        api_key: str,
        prompt: str,
        attachments: list[dict],
    ) -> None:
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.prompt = prompt
        self.attachments = attachments
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        blocks = [f"我的要求：{self.prompt}"]
        for index, attachment in enumerate(self.attachments, start=1):
            blocks.append(
                f"\n【上传文件 {index}：{attachment['name']}】\n{attachment['text']}"
            )
        messages = [
            ChatMessage(role="system", content=_EXTRACT_SYSTEM_PROMPT),
            ChatMessage(role="user", content="\n".join(blocks)),
        ]
        chunks: list[str] = []

        def on_content(text: str) -> None:
            if self._cancelled.is_set():
                return
            chunks.append(text)
            self.content.emit(text)

        try:
            stream_chat(self.provider, self.api_key, messages, on_content=on_content)
        except AiProviderError as error:
            if not self._cancelled.is_set():
                self.failed.emit(str(error))
        except Exception as error:  # 后台线程兜底
            if not self._cancelled.is_set():
                self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            if not self._cancelled.is_set():
                self.finished.emit("".join(chunks))


class AiPanel(QWidget):
    """AI 助手面板。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip("AI 助手（Ctrl+L 折叠/展开）")
        self._history: list[ChatMessage] = []
        self._session_id = new_session_id()  # opencode Go 的稳定会话标识
        self._loop: AgentLoop | None = None
        self._thinking_block: _ThinkingBlock | None = None
        self._bubbles: list[_MessageBubble] = []
        #: 附件提取阶段（第一段）的后台工作器；非 None 即流程进行中
        self._extract_worker: _ExtractionWorker | None = None
        #: 📎 上传的文件（已本地提取为文本）：{"path", "name", "text"}
        self._attachments: list[dict] = []
        self.unit_id: int | None = None  # 当前单位工程（AI 工具的作用范围）
        self.unit_name: str = ""
        self._stream_text = ""  # 当前流式正文累计
        self._reasoning_buffer = ""  # 思考流缓冲（节流渲染）
        self._reasoning_last = 0.0
        self._build()
        self._connect()
        self._refresh_hint()

    @property
    def input_widget(self) -> QWidget:
        """底部输入区。主窗体的提示浮层靠它避让，免得盖住发送按钮。"""
        return self._input

    # ------------------------------------------------------------------ 界面
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(2)
        title = QLabel("AI 助手")
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch(1)
        self._btn_clear = QPushButton("清空")
        self._btn_clear.setProperty("secondary", "true")
        self._btn_clear.clicked.connect(self._clear)
        header.addWidget(self._btn_clear)
        self._btn_settings = QPushButton()
        self._btn_settings.setIcon(
            load_icon("settings", color=_c().text_primary, size=16)
        )
        self._btn_settings.setFixedSize(32, 32)
        self._btn_settings.clicked.connect(self._open_settings)
        header.addWidget(self._btn_settings)
        layout.addLayout(header)

        # 对话历史：每条消息一个独立控件，从顶部堆叠
        self._history_scroll = QScrollArea()
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._history_container = QWidget()
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(4, 4, 4, 4)
        self._history_layout.setSpacing(2)
        self._history_layout.addStretch(1)  # stretch 固定在末尾
        self._history_scroll.setWidget(self._history_container)
        layout.addWidget(self._history_scroll, 1)

        # 输入区：圆角输入框 + 右下角 overlay 发送按钮；附件片挂在输入框
        # 内部左上角（见 _reposition_attachment_chips）
        self._input = _InputEdit()
        self._input.setObjectName("aiInputEdit")
        self._input.setPlaceholderText("输入问题... (Enter 发送, Shift+Enter 换行)")
        self._apply_input_height()
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.setAcceptDrops(False)  # 文件拖拽统一交给面板处理
        self._input.viewport().setAcceptDrops(False)  # 文本框视口默认也吃拖放
        # 左下角留给 📎 附件按钮、右侧留给发送按钮；底部整条留给模型选择器 +
        # 发送按钮，正文不会压到它们；顶部给附件片让位（_apply_input_margins）
        self._apply_input_margins(0)
        self._input.submitted.connect(self._send_message)
        layout.addWidget(self._input)

        self._send_btn = QPushButton()
        self._send_btn.setObjectName("aiSendBtn")
        self._send_btn.setProperty("primary", True)
        self._send_btn.setIcon(self._make_send_arrow_icon())
        self._send_btn.setFixedSize(30, 30)
        self._send_btn.setParent(self._input)
        self._send_btn.raise_()
        self._send_btn.clicked.connect(self._send_message)

        # 发送按钮左侧的模型来源选择器：provider 显示名 + 下箭头
        self._source_btn = _SourceButton()
        self._source_btn.setObjectName("aiSourceBtn")
        self._source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._source_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._source_btn.setFixedHeight(30)
        self._source_btn.setParent(self._input)
        self._source_btn.clicked.connect(self._show_source_menu)
        self._source_btn.raise_()

        # 输入框左下角的 📎 附件按钮：选择文件后挂到输入框左上角
        self._attach_btn = QToolButton()
        self._attach_btn.setObjectName("aiAttachBtn")
        self._attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._attach_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._attach_btn.setFixedSize(30, 30)  # 与右侧模型/发送按钮同高，占满按钮行
        self._attach_btn.setStyleSheet("QToolButton { border: none; background: transparent; }")
        self._attach_btn.setToolTip(
            "上传文件（Excel / Word / CSV / 文本…）\n"
            "发送时 AI 先按你的要求提取文件数据，再结合要求操作软件。"
        )
        self._attach_btn.setParent(self._input)
        self._attach_btn.clicked.connect(self._attach_files)
        self._attach_btn.raise_()
        self._refresh_attach_icon()
        # 附件片挂在输入框内部左上角（ZCode 同款）；拖拽上传的毛玻璃层
        # 覆盖整个面板，文件拖拽统一由面板接收
        self._attachment_chips: list[_AttachmentChip] = []
        self._drop_overlay = _DropOverlay(self)
        self.setAcceptDrops(True)
        # 三个 overlay 按钮都就位后再装过滤器：Resize 事件触发的重定位
        # 可以安全访问它们
        self._input.installEventFilter(self)

    def _connect(self) -> None:
        # 连接一律走弱引用：lambda 会被 PySide 整体强引用，闭包里抓着的 self
        # 永远释放不掉（面板会带着整棵控件树一起泄漏）
        connect_weak(bus().project_opened, self, "_refresh_hint")
        bus().project_closed.connect(self._refresh_hint)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ 事件
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        if obj is self._input and event.type() == QEvent.Type.Resize:
            self._reposition_overlay_buttons()
            self._reposition_attachment_chips()  # 宽度变了，附件片重新换行
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        # 面板宽度变化后 provider 名可用宽度也变了，重新省略 + 定位
        if getattr(self, "_source_btn", None) is not None:
            self._refresh_source_button()
        if (
            getattr(self, "_drop_overlay", None) is not None
            and self._drop_overlay.isVisible()
        ):
            self._drop_overlay.setGeometry(self.rect())

    # ------------------------------------------------------------------ 拖拽上传
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._drag_has_files(event.mimeData()):
            event.acceptProposedAction()
            self._show_drop_overlay()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._drag_has_files(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self._hide_drop_overlay()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        event.acceptProposedAction()
        self._hide_drop_overlay()
        if paths:
            self._add_attachment_paths(paths)

    @staticmethod
    def _drag_has_files(mime) -> bool:
        return mime.hasUrls() and any(url.isLocalFile() for url in mime.urls())

    def _show_drop_overlay(self) -> None:
        """拖拽进入面板：抓当前帧做毛玻璃底图，盖住整个面板。"""
        overlay = self._drop_overlay
        overlay.setGeometry(self.rect())
        overlay.set_backdrop(self.grab())  # 必须在显示 overlay 之前抓帧
        overlay.raise_()
        overlay.show()

    def _hide_drop_overlay(self) -> None:
        self._drop_overlay.hide()

    def _reposition_overlay_buttons(self) -> None:
        rect = self._input.rect()
        margin = 6
        self._send_btn.move(
            rect.right() - self._send_btn.width() - margin,
            rect.bottom() - self._send_btn.height() - margin,
        )
        self._send_btn.raise_()
        self._source_btn.move(
            self._send_btn.x() - self._source_btn.width() - 4,
            self._send_btn.y(),
        )
        self._source_btn.raise_()
        self._attach_btn.move(
            margin,
            rect.bottom() - self._attach_btn.height() - margin,
        )
        self._attach_btn.raise_()

    def _apply_input_margins(self, top: int) -> None:
        """正文区留白：正文从输入框最左侧开始、右侧用到最右（左右都为 0），
        底部整条留给 📎 / 模型选择 / 发送按钮，顶部给附件片让位。"""
        self._input.setViewportMargins(0, top, 0, 38)

    def _apply_input_height(self) -> None:
        """输入框高度 = 基础高度 + 3 行行高（按主题字体换算，字体变化时重算）。"""
        lines = self._input.fontMetrics().lineSpacing()
        self._input.setMaximumHeight(_INPUT_BASE_HEIGHT + 3 * lines)

    def _refresh_attach_icon(self) -> None:
        """📎 图标随主题着色。"""
        if getattr(self, "_attach_btn", None) is not None:
            self._attach_btn.setIcon(
                load_icon("paperclip", color=_c().text_secondary, size=20)
            )

    @staticmethod
    def _make_send_arrow_icon():
        """发送箭头：白色圆头上箭头（Quotor _make_send_arrow_icon 同款）。"""
        size = 32
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("white"), 2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(9, 19, 16, 11)
        painter.drawLine(16, 11, 23, 19)
        painter.drawLine(16, 12, 16, 23)
        painter.end()
        from PySide6.QtGui import QIcon

        return QIcon(pixmap)

    # ------------------------------------------------------------------ 状态
    def refresh_theme(self) -> None:
        self._on_theme_changed()

    def _on_theme_changed(self) -> None:
        self._btn_settings.setIcon(load_icon("settings", color=_c().text_primary, size=16))
        self._refresh_attach_icon()
        self._apply_input_height()  # 主题字体可能变，行高按新字体重算
        self._source_btn.update()  # 箭头颜色随主题重绘
        self._refresh_attachments()  # 文件片边框 / 图标颜色随主题重建
        for bubble in self._bubbles:
            bubble.refresh_theme()

    def _active_provider(self) -> dict | None:
        """当前启用的 provider 条目；未指定时退回列表第一个。"""
        config = get_config()
        name = config.ai_active_provider
        provider = config.ai_provider(name) if name else None
        if provider is None:
            providers = config.ai_providers
            provider = providers[0] if providers else None
        return provider

    def _provider(self) -> ProviderConfig | None:
        provider = self._active_provider()
        if provider is None:
            return None
        base_url = str(provider.get("base_url", ""))
        send_reasoning = provider.get("send_reasoning_content")
        if send_reasoning is None:
            send_reasoning = default_send_reasoning_content(base_url)
        return ProviderConfig(
            name=provider.get("name", ""),
            base_url=base_url,
            default_model=provider.get("default_model", ""),
            temperature=float(provider.get("temperature", 0.2)),
            send_reasoning_content=bool(send_reasoning),
        )

    def _refresh_hint(self) -> None:
        provider = self._provider()
        self._input.setEnabled(provider is not None)
        self._send_btn.setEnabled(provider is not None)
        if provider is None:
            self._input.setPlaceholderText("尚未配置 AI 模型，请点击右上角齿轮进行配置。")
        else:
            self._input.setPlaceholderText("输入问题... (Enter 发送, Shift+Enter 换行)")
        self._refresh_source_button()

    def _open_settings(self) -> None:
        from app.views.dialogs.ai_settings_dialog import AiSettingsDialog

        dialog = AiSettingsDialog(self)
        dialog.exec()
        # 「设为当前启用」是即改即存，取消对话框也可能已切换 provider
        self._refresh_hint()

    # ------------------------------------------------------------------ 模型来源
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().showEvent(event)
        self._refresh_source_button()
        self._apply_input_height()  # 显示时主题字体已生效，按实际行高重算

    @staticmethod
    def _source_label(provider: dict) -> str:
        """按钮文字 = 模型来源/当前模型，例如 OpenCodeGo/deepseek-V4.1-flash。"""
        source = str(provider.get("display_name") or provider.get("name") or "").strip()
        model = str(provider.get("default_model") or "").strip()
        if source and model:
            return f"{source}/{model}"
        return source or model or "选择模型来源"

    @staticmethod
    def _elide_source_label(metrics, source: str, model: str, width: int) -> str:
        """空间不足时只省略来源名，尽量保留完整的「/当前模型」。"""
        label = f"{source}/{model}" if source and model else (source or model or "选择模型来源")
        if metrics.horizontalAdvance(label) <= width:
            return label
        if source and model:
            room = width - metrics.horizontalAdvance("/") - metrics.horizontalAdvance(model)
            if room >= metrics.horizontalAdvance("…"):
                short = metrics.elidedText(source, Qt.TextElideMode.ElideRight, room)
                return f"{short}/{model}"
        return metrics.elidedText(label, Qt.TextElideMode.ElideMiddle, width)

    def _refresh_source_button(self) -> None:
        provider = self._active_provider()
        if provider is None:
            self._source_btn.setVisible(False)
            return
        self._source_btn.setVisible(True)
        source = str(provider.get("display_name") or provider.get("name") or "").strip()
        model = str(provider.get("default_model") or "").strip()
        # 面板较窄时给发送按钮和右侧留白让位
        cap = max(72, min(250, self.width() - 70))
        self._source_btn.ensurePolished()
        metrics = self._source_btn.fontMetrics()
        # 右侧内边距 24px 由 QSS 留给箭头，这里再收 8px 作为文字与箭头的间距
        text = self._elide_source_label(metrics, source, model, max(24, cap - 32))
        self._source_btn.setText(text)
        width = min(cap, metrics.horizontalAdvance(text) + 32)
        self._source_btn.setFixedWidth(max(56, width))
        self._source_btn.setEnabled(not self._busy())
        if source and model:
            tooltip = f"模型来源：{source}\n当前模型：{model}"
        elif source:
            tooltip = f"模型来源：{source}\n当前模型：未设置"
        else:
            tooltip = f"当前模型：{model}" if model else "选择模型来源"
        self._source_btn.setToolTip(tooltip + "\n点击切换")
        self._reposition_overlay_buttons()

    def _build_source_menu(self) -> QMenu | None:
        providers = get_config().ai_providers
        if not providers:
            return None
        active = self._active_provider() or {}
        active_name = str(active.get("name", ""))
        menu = QMenu(self)
        menu.setMinimumWidth(max(180, self._source_btn.width()))
        for provider in providers:
            name = str(provider.get("name", ""))
            display = str(provider.get("display_name") or name)
            action = menu.addAction(display)
            action.setCheckable(True)
            action.setChecked(name == active_name)
            action.triggered.connect(
                lambda _checked=False, selected=name: self._select_source(selected)
            )
        menu.addSeparator()
        manage = menu.addAction("管理模型")
        # 等菜单收起后再开模态窗体，避免 QMenu 的事件循环里嵌套 modal
        manage.triggered.connect(lambda: QTimer.singleShot(0, self._open_settings))
        return menu

    def _show_source_menu(self) -> None:
        menu = self._build_source_menu()
        if menu is not None:
            menu.exec(self._source_menu_position(menu))

    def _source_menu_position(self, menu: QMenu) -> QPoint:
        """优先向按钮上方展开（面板贴着窗口底部，下方通常没有空间）。"""
        menu.ensurePolished()
        hint = menu.sizeHint()
        anchor = self._source_btn.mapToGlobal(QPoint(0, 0))
        screen = self._source_btn.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry()
        x = max(available.left(), min(anchor.x(), available.right() - hint.width() + 1))
        above = anchor.y() - hint.height() - 4
        below = anchor.y() + self._source_btn.height() + 4
        if above >= available.top():
            y = above
        elif below + hint.height() <= available.bottom():
            y = below
        else:
            y = max(available.top(), available.bottom() - hint.height() + 1)
        return QPoint(x, y)

    def _select_source(self, name: str) -> None:
        provider = get_config().ai_provider(name)
        if provider is None or get_config().ai_active_provider == name:
            return
        set_ai_active_provider(name)
        self._refresh_hint()
        display = str(provider.get("display_name") or name)
        bus().status_message.emit(f"已切换模型来源：{display}", 3000)

    def set_current_unit(self, unit_id: int | None, name: str = "") -> None:
        """主窗体在树选择变化时调用，让 AI 工具作用于当前单位工程。"""
        self.unit_id = unit_id
        self.unit_name = name

    # ------------------------------------------------------------------ 消息区
    def _insert_widget(self, widget: QWidget) -> None:
        self._history_layout.insertWidget(self._history_layout.count() - 1, widget)
        self._scroll_to_bottom()

    def _append_message(self, role: str, text: str) -> None:
        bubble = _MessageBubble(role, text)
        self._bubbles.append(bubble)
        self._insert_widget(bubble)

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, self._do_scroll)

    def _do_scroll(self) -> None:
        bar = self._history_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _clear(self) -> None:
        if self._loop is not None:
            self._loop.cancel()
        if self._extract_worker is not None:
            # 断开信号再取消：迟到的提取完成 / 失败不再改动已清空的面板
            worker = self._extract_worker
            worker.content.disconnect(self._on_content)
            worker.finished.disconnect(self._on_extract_finished)
            worker.failed.disconnect(self._on_extract_failed)
            worker.cancel()
            self._extract_worker = None
        while self._history_layout.count() > 1:  # 保留末尾 stretch
            item = self._history_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._history.clear()
        self._session_id = new_session_id()
        self._bubbles.clear()
        self._thinking_block = None
        self._send_btn.setEnabled(self._provider() is not None)
        self._source_btn.setEnabled(self._provider() is not None)

    def _busy(self) -> bool:
        """一轮流程进行中：代理循环（第二段）或附件提取（第一段）。"""
        return self._loop is not None or self._extract_worker is not None

    # ------------------------------------------------------------------ 附件
    def _attach_files(self) -> None:
        """📎 选择文件：本地提取为文本后挂到输入框；失败的文件弹状态栏提示。"""
        from PySide6.QtWidgets import QFileDialog

        paths, _filter = QFileDialog.getOpenFileNames(self, "上传文件", "", FILE_DIALOG_FILTER)
        self._add_attachment_paths(paths)

    def _add_attachment_paths(self, paths: list[str]) -> None:
        """把文件提取为文本挂到附件片（📎 对话框与拖拽上传共用）。"""
        added = False
        for path in paths:
            if not path or any(item["path"] == path for item in self._attachments):
                continue
            try:
                text = extract_text(path)
            except FileExtractError as error:
                bus().status_message.emit(str(error), 6000)
                continue
            self._attachments.append(
                {"path": path, "name": Path(path).name, "text": text}
            )
            added = True
        if added:
            self._refresh_attachments()

    def _refresh_attachments(self) -> None:
        """按 self._attachments 重建输入框左上角的附件片（增删文件 / 换主题共用）。"""
        for chip in self._attachment_chips:
            chip.deleteLater()
        self._attachment_chips = []
        for attachment in self._attachments:
            chip = _AttachmentChip(attachment, self._input)
            chip.removed.connect(self._remove_attachment)
            chip.show()
            self._attachment_chips.append(chip)
        self._reposition_attachment_chips()

    def _reposition_attachment_chips(self) -> None:
        """附件片在输入框内左上角流式换行，正文区上边距随之让位。"""
        chips = self._attachment_chips
        if not chips:
            self._apply_input_margins(0)
            return
        right_edge = self._input.width() - _CHIP_MARGIN
        x = y = _CHIP_MARGIN
        row_height = 0
        for chip in chips:
            size = chip.sizeHint()
            chip.resize(size)
            if x > _CHIP_MARGIN and x + size.width() > right_edge + 1:
                x = _CHIP_MARGIN
                y += row_height + _CHIP_GAP
                row_height = 0
            chip.move(x, y)
            chip.raise_()
            x += size.width() + _CHIP_GAP
            row_height = max(row_height, size.height())
        self._apply_input_margins(y + row_height + _CHIP_GAP)

    def _remove_attachment(self, attachment: dict) -> None:
        if attachment in self._attachments:
            self._attachments.remove(attachment)
        self._refresh_attachments()

    # ------------------------------------------------------------------ 发送
    def _send_message(self) -> None:
        provider = self._provider()
        if provider is None or self._busy():
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        api_key = ai_keychain.get_api_key(provider.name)
        self._input.clear()
        attachments = self._attachments
        self._attachments = []
        self._refresh_attachments()
        # 用户气泡：带附件时附上文件清单（提取的数据不进气泡，AI 回复里体现）
        display_text = text
        if attachments:
            display_text += "\n\n📎 " + "、".join(a["name"] for a in attachments)
        self._history.append(ChatMessage(role="user", content=text))
        self._append_message("user", display_text)

        # 预创建思考块并立即启动"思考中"动画（Quotor 同款，消除启动空白期）；
        # 附件流程的提取阶段与随后的工具调用阶段共用同一块
        self._thinking_block = _ThinkingBlock("思考过程")
        self._insert_widget(self._thinking_block)
        self._thinking_block.start_thinking()
        self._send_btn.setEnabled(False)
        self._source_btn.setEnabled(False)
        self._stream_text = ""

        if attachments:
            # 两段式：第一段调模型按提示词从文件提炼数据（无工具），
            # 第二段把「提取数据 + 用户要求」交给带工具的代理操作软件
            self._start_extraction_phase(text, attachments, provider, api_key)
        else:
            self._start_agent_phase(provider, api_key)

    def _start_extraction_phase(
        self, prompt: str, attachments: list[dict], provider: ProviderConfig, api_key: str
    ) -> None:
        """第一段：后台线程调模型提炼文件数据（流式正文进思考块）。"""
        self._extract_worker = _ExtractionWorker(provider, api_key, prompt, attachments)
        self._extract_worker.content.connect(self._on_content)
        self._extract_worker.finished.connect(self._on_extract_finished)
        self._extract_worker.failed.connect(self._on_extract_failed)
        self._extract_worker.start()

    def _on_extract_finished(self, extracted: str) -> None:
        worker = self._extract_worker
        self._extract_worker = None
        if worker is None:
            return
        extracted = (extracted or "").strip()
        names = "、".join(a["name"] for a in worker.attachments)
        if extracted:
            composed = (
                f"{worker.prompt}\n\n---\n"
                f"以下是 AI 根据你的要求从上传文件（{names}）中提取的数据，"
                f"请结合这些数据和上面的要求操作本软件：\n\n{extracted}"
            )
        else:
            composed = (
                f"{worker.prompt}\n\n（未能从上传文件（{names}）中提取到数据，"
                "请直接按上面的要求处理。）"
            )
        # 本条用户消息换成「提示词 + 提取数据」：后续追问仍能引用这份数据
        if self._history and self._history[-1].role == "user":
            self._history[-1].content = composed
        if self._thinking_block is not None:
            self._thinking_block.rotate_stream_label()
        self._stream_text = ""
        self._start_agent_phase(worker.provider, worker.api_key)

    def _on_extract_failed(self, message: str) -> None:
        self._extract_worker = None
        self._on_failed(message)

    def _start_agent_phase(self, provider: ProviderConfig, api_key: str) -> None:
        """第二段：带工具的代理循环（与普通对话同一条路径，写操作弹确认卡）。"""
        agent_context = current_agent_context().as_dict()
        rules = default_registry().to_rules_for_context(agent_context)
        system = ChatMessage(
            role="system",
            content=_SYSTEM_PROMPT + ("\n\n" + rules if rules else ""),
        )
        self._loop = AgentLoop(agent_context, session_id=self._session_id)
        self._loop.content.connect(self._on_content)
        self._loop.reasoning.connect(self._on_reasoning)
        self._loop.status.connect(self._on_status)
        self._loop.finished.connect(self._on_finished)
        self._loop.failed.connect(self._on_failed)
        self._loop.run([system, *self._history], provider, api_key, None)

    # ------------------------------------------------------------------ 流式回调
    def _on_content(self, text: str) -> None:
        """流式正文：在思考块里就地刷新（Quotor stream 同款）。"""
        if self._thinking_block is not None:
            self._stream_text += text
            self._thinking_block.set_stream_text(self._stream_text)
            self._scroll_to_bottom()

    def _on_reasoning(self, text: str) -> None:
        """思考流节流渲染（0.25s 或累计 40 字符刷新一次，避免逐 token 重排）。"""
        if self._thinking_block is None:
            return
        self._reasoning_buffer += text
        now = time.monotonic()
        if now - self._reasoning_last < 0.25 and len(self._reasoning_buffer) < 40:
            return
        self._reasoning_last = now
        self._reasoning_buffer = ""
        self._thinking_block.set_stream_text("（思考）" + text[-500:])
        self._scroll_to_bottom()

    def _on_status(self, text: str) -> None:
        """工具调用：🔧 行 + 换轮时重置流式标签。"""
        if self._thinking_block is None:
            return
        self._stream_text = ""
        self._thinking_block.rotate_stream_label()
        self._thinking_block.append_html(
            f'<p style="color:{_c().warning};font-weight:600;margin:0;">'
            f"🔧 {html.escape(text)}</p>"
        )
        self._scroll_to_bottom()

    def _on_finished(self, text: str) -> None:
        if self._thinking_block is not None:
            self._thinking_block.stop_thinking()
        answer = text or self._stream_text
        self._stream_text = ""
        # 思考模式的端点要求把历史 assistant 的 reasoning_content 原样回传，
        # 否则下一轮对话会 400（AiPanel 每轮用 _history 重建请求）。
        reasoning = (
            getattr(self._loop, "last_reasoning", "")
            if self._loop is not None
            else ""
        )
        self._append_message("ai", answer)
        self._history.append(
            ChatMessage(role="assistant", content=answer, reasoning_content=reasoning)
        )
        self._thinking_block = None
        self._send_btn.setEnabled(self._provider() is not None)
        self._source_btn.setEnabled(self._provider() is not None)
        self._loop = None
        self._scroll_to_bottom()

    def _on_failed(self, message: str) -> None:
        if self._thinking_block is not None:
            self._thinking_block.stop_thinking()
            self._thinking_block.append_html(
                f'<p style="color:{_c().danger};font-weight:600;">'
                f"[错误] {html.escape(str(message))}</p>"
            )
        self._stream_text = ""
        self._append_message("error", str(message))
        self._thinking_block = None
        self._send_btn.setEnabled(self._provider() is not None)
        self._source_btn.setEnabled(self._provider() is not None)
        self._loop = None
        self._scroll_to_bottom()
        if isinstance(message, str) and "401" in message:
            FramelessMessageBox.warning(self, "AI 端点", "鉴权失败，请检查 API key。")

    # 写操作确认统一由主窗体安装的全局确认处理器完成
    # （见 app.agent.confirm_policy.install_confirm_handler）。
