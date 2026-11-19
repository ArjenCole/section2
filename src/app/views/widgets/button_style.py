"""自绘按钮样式：全项目 QPushButton 的平台无关绘制。

alpha.3 起标准按钮交还系统原生样式（Windows 的 windows11 / macOS 的
QMacStyle），平台差异只由 ``platform_buttons`` 负责排序。原生样式的问题是
按钮外观随系统版本/深浅色漂移，且 Win10 与 Win11 观感不一致。

这里改为**完全自绘**：``ButtonStyle`` 是一个 QProxyStyle，只接管
``CE_PushButton`` 系列（背景、边框、文字、图标），其余控件仍委托
给底层原生样式。颜色与圆角/内边距照 alpha.2 的按钮 QSS：

- 普通按钮：``bg_card`` 底 + ``border_strong`` 1px 边 + 6px 圆角；
- 悬停 ``bg_hover``、按下 ``bg_pressed``、禁用 ``bg_hover`` + ``text_disabled``；
- 默认按钮（``primary`` 属性为 True，或 Qt 自己创建的默认按钮）：主色填充 +
  反白文字 + 半粗体，悬停/按下用 ``primary_hover`` / ``primary_pressed``。

QSS 里带 ``role`` / ``objectName`` 的功能性按钮（``icon-btn``、分段控件、
AI 发送等）仍由样式表绘制——它们本来就是 alpha.2 的自绘规则，不受本样式
影响；本样式只接管没有专属 QSS 规则的标准按钮（对话框/消息框/向导）。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleOptionButton,
    QWidget,
)

#: alpha.2 按钮 QSS：border-radius: 6px; padding: 5px 14px; border: 1px
_RADIUS = 6.0
_PAD_X = 14.0
_PAD_Y = 5.0
_BORDER = 1.0
#: 图标与文字间距
_ICON_GAP = 6.0
#: 没有显式 iconSize 时的兜底图标尺寸
_DEFAULT_ICON = 16


def _theme():
    """当前主题调色板；主题尚未初始化时退回亮色。"""
    from app.resources.qss.theme import LIGHT, ThemeManager

    try:
        return ThemeManager.instance().current()
    except Exception:  # noqa: BLE001 - 启动极早期主题未就绪
        return LIGHT


def _is_default(option: QStyleOptionButton) -> bool:
    features = getattr(option, "features", None)
    if features is None:
        return False
    return bool(features & QStyleOptionButton.ButtonFeature.DefaultButton)


def _visual_default(option: QStyleOptionButton, widget: QWidget | None) -> bool:
    """是否按“主色按钮”绘制。

    只看 ``primary`` 属性：``platform_buttons`` 给整排按钮显式写 True/False，
    这样 QDialog 里 autoDefault 的辅助按钮（“编辑”“全选”…）不会因为
    ``isDefault()`` 被误画成主色，纯“关闭”对话框也不会变蓝。Qt 自己创建
    的按钮（QWizard 的完成按钮）由 ``NewProjectWizard`` 显式标 primary。
    没有 widget 的尺寸查询退回 ``isDefault()``，只影响字重测量。
    """
    if widget is not None:
        return bool(widget.property("primary"))
    return _is_default(option)


def _is_hovered(option: QStyleOptionButton) -> bool:
    # QPushButton::initStyleOption 在鼠标进入时置 State_MouseOver；不要再用
    # widget.underMouse() 兜底——多个按钮重叠（如离屏测试/浮动层）时会误判。
    return bool(option.state & QStyle.StateFlag.State_MouseOver)


def _display_text(text: str) -> str:
    """去掉 Windows/Qt 的助记符 ``&``（``&&`` 表示字面量 &）。

    标准按钮（尤其 QWizard 的 ``&Finish``）文本里带助记符；自绘时直接
    drawText 会把 ``&`` 画出来，必须先剥掉。项目自己的中文按钮不带助记符。
    """
    if "&" not in text:
        return text
    placeholder = "\x00"
    return text.replace("&&", placeholder).replace("&", "").replace(placeholder, "&")


class ButtonStyle(QProxyStyle):
    """只重绘按钮的代理样式；其余控件走底层原生样式。"""

    def __init__(self, base=None) -> None:
        super().__init__(base)

    # ------------------------------------------------------------------ 状态
    def polish(self, widget) -> None:  # noqa: N802 - Qt 命名
        # 自绘悬停需要 Enter/Leave 事件驱动重绘；QPushButton 默认不开 WA_Hover
        # （原生样式自己处理鼠标态），这里统一打开并挂事件过滤器。
        if isinstance(widget, QAbstractButton):
            widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            # polish 可能被重复调用（换肤/样式重设）：先摘再挂，避免过滤器叠加
            widget.removeEventFilter(self)
            widget.installEventFilter(self)
        super().polish(widget)

    def unpolish(self, widget) -> None:  # noqa: N802 - Qt 命名
        if isinstance(widget, QAbstractButton):
            widget.removeEventFilter(self)
        super().unpolish(widget)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 命名
        # 悬停/离开只改背景色，控件本身不一定收到 update()，这里补一次重绘。
        if event.type() in (
            QEvent.Type.Enter,
            QEvent.Type.Leave,
            QEvent.Type.HoverEnter,
            QEvent.Type.HoverLeave,
        ):
            obj.update()
        return False

    # ------------------------------------------------------------------ 尺寸
    def sizeFromContents(self, ct, option, size, widget=None):  # noqa: N802 - Qt 命名
        if (
            ct == QStyle.ContentsType.CT_PushButton
            and isinstance(option, QStyleOptionButton)
            and not self._qss_paints(widget)
        ):
            return self._button_size(option, widget)
        return super().sizeFromContents(ct, option, size, widget)

    @staticmethod
    def _qss_paints(widget: QWidget | None) -> bool:
        """该按钮是否已由 QSS 专属规则绘制（role / objectName / 控件级样式表）。

        这类按钮（icon-btn、分段控件、AI 发送等）的尺寸与外观都交给
        QStyleSheetStyle，本样式不能重复加内边距。
        """
        if widget is None:
            return False
        if widget.property("role") or widget.styleSheet():
            return True
        return widget.objectName() in {"aiSendBtn", "aiSourceBtn"}

    def _button_size(self, option: QStyleOptionButton, widget=None) -> QSize:
        font = self._button_font(option, widget)
        metrics = QFontMetrics(font)
        text = _display_text(option.text or "")
        text_w = metrics.horizontalAdvance(text) if text else 0
        text_h = metrics.height() if text else 0
        icon = getattr(option, "icon", None)
        icon_size = self._icon_size(option)
        has_icon = icon is not None and not icon.isNull()
        icon_w = icon_size.width() if has_icon else 0
        icon_h = icon_size.height() if has_icon else 0
        gap = _ICON_GAP if (has_icon and text) else 0.0
        width = text_w + icon_w + gap + 2 * _PAD_X + 2 * _BORDER
        height = max(text_h, icon_h) + 2 * _PAD_Y + 2 * _BORDER
        return QSize(int(round(width)), int(round(height)))

    # ------------------------------------------------------------------ 绘制
    def drawControl(self, element, option, painter, widget=None):  # noqa: N802 - Qt 命名
        if element == QStyle.ControlElement.CE_PushButton:
            self._paint_button(option, painter, widget, background=True, label=True)
            return
        if element == QStyle.ControlElement.CE_PushButtonBevel:
            self._paint_button(option, painter, widget, background=True, label=False)
            return
        if element == QStyle.ControlElement.CE_PushButtonLabel:
            self._paint_button(option, painter, widget, background=False, label=True)
            return
        super().drawControl(element, option, painter, widget)

    def _paint_button(
        self,
        option: QStyleOptionButton,
        painter: QPainter,
        widget: QWidget | None,
        *,
        background: bool,
        label: bool,
    ) -> None:
        colors = _theme()
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        pressed = bool(
            option.state & (QStyle.StateFlag.State_Sunken | QStyle.StateFlag.State_On)
        )
        hovered = enabled and _is_hovered(option)
        default = _visual_default(option, widget)

        if background:
            self._paint_background(
                painter,
                option.rect,
                colors,
                enabled=enabled,
                pressed=pressed,
                hovered=hovered,
                default=default,
            )
        if label:
            self._paint_label(
                painter,
                option,
                colors,
                enabled=enabled,
                pressed=pressed,
                default=default,
                widget=widget,
            )

    def _paint_background(
        self,
        painter: QPainter,
        rect,
        colors,
        *,
        enabled: bool,
        pressed: bool,
        hovered: bool,
        default: bool,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = QRectF(rect).adjusted(
            _BORDER / 2, _BORDER / 2, -_BORDER / 2, -_BORDER / 2
        )

        if not enabled:
            fill = QColor(colors.bg_hover)
            border = QColor(colors.border)
        elif default:
            if pressed:
                fill = QColor(colors.primary_pressed)
            elif hovered:
                fill = QColor(colors.primary_hover)
            else:
                fill = QColor(colors.primary)
            border = QColor(fill)
        else:
            if pressed:
                fill = QColor(colors.bg_pressed)
            elif hovered:
                fill = QColor(colors.bg_hover)
            else:
                fill = QColor(colors.bg_card)
            border = QColor(colors.border_strong)

        path = QPainterPath()
        path.addRoundedRect(box, _RADIUS, _RADIUS)
        painter.fillPath(path, fill)
        pen = QPen(border)
        pen.setWidthF(_BORDER)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.restore()

    def _paint_label(
        self,
        painter: QPainter,
        option: QStyleOptionButton,
        colors,
        *,
        enabled: bool,
        pressed: bool,
        default: bool,
        widget: QWidget | None,
    ) -> None:
        text = _display_text(option.text or "")
        icon = getattr(option, "icon", None)
        has_icon = icon is not None and not icon.isNull()
        if not text and not has_icon:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font = self._button_font(option, widget)
        painter.setFont(font)
        if not enabled:
            color = QColor(colors.text_disabled)
        elif default:
            color = QColor(colors.text_inverse)
        else:
            color = QColor(colors.text_primary)

        inset_x = _BORDER + _PAD_X
        inset_y = _BORDER + _PAD_Y
        content = QRectF(option.rect).adjusted(
            inset_x, inset_y, -inset_x, -inset_y
        )
        metrics = QFontMetrics(font)
        text_w = metrics.horizontalAdvance(text) if text else 0
        text_h = metrics.height() if text else 0
        icon_size = self._icon_size(option)
        icon_w = icon_size.width() if has_icon else 0
        icon_h = icon_size.height() if has_icon else 0
        gap = _ICON_GAP if (has_icon and text) else 0.0

        total_w = text_w + icon_w + gap
        start_x = content.center().x() - total_w / 2.0

        if has_icon:
            mode = QIcon.Mode.Disabled if not enabled else QIcon.Mode.Normal
            state = QIcon.State.On if pressed else QIcon.State.Off
            icon_rect = QRectF(
                start_x,
                content.center().y() - icon_h / 2.0,
                float(icon_size.width()),
                float(icon_size.height()),
            )
            icon.paint(
                painter, icon_rect.toRect(), Qt.AlignmentFlag.AlignCenter, mode, state
            )
            start_x += icon_w + gap

        if text:
            # 按钮被布局压窄时按可用宽度省略；正常情况可用宽度 ≥ 文字宽。
            available = max(0.0, content.width() - icon_w - gap)
            draw_w = min(float(text_w), available) if available else float(text_w)
            text_rect = QRectF(
                start_x,
                content.center().y() - text_h / 2.0,
                draw_w,
                float(text_h),
            )
            elided = metrics.elidedText(
                text, Qt.TextElideMode.ElideRight, int(text_rect.width())
            )
            painter.setPen(color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, elided)
        painter.restore()

    # ------------------------------------------------------------------ 字体/图标
    @staticmethod
    def _button_font(option: QStyleOptionButton, widget=None) -> QFont:
        base = widget.font() if widget is not None else QApplication.font()
        font = QFont(base)
        if _visual_default(option, widget):
            font.setWeight(QFont.Weight.DemiBold)
        return font

    @staticmethod
    def _icon_size(option: QStyleOptionButton) -> QSize:
        size = getattr(option, "iconSize", QSize())
        if size is None or size.width() <= 0 or size.height() <= 0:
            return QSize(_DEFAULT_ICON, _DEFAULT_ICON)
        return size
