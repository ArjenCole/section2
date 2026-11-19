"""自绘按钮样式（views/widgets/button_style.py）的行为锁定。

标准按钮不再交系统原生样式：ButtonStyle 接管 CE_PushButton，颜色/圆角/
悬停/按下按 alpha.2 的按钮 QSS。这里用离屏渲染采样像素，锁住四件事：

1. 普通按钮 bg_card、默认按钮 primary 填充；
2. 悬停 bg_hover、按下 bg_pressed、禁用 bg_hover；
3. 默认按钮悬停/按下走 primary_hover / primary_pressed；
4. 尺寸 = 文字宽 + 2×14px 内边距 + 2×1px 边框（alpha.2 QSS 的盒模型），
   且带 role / objectName 的 QSS 按钮不被重复加内边距。
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton

from app.resources.qss.theme import DARK, LIGHT
from app.views.widgets import button_style
from app.views.widgets.button_style import ButtonStyle

pytestmark = pytest.mark.usefixtures("qapp")

_W, _H = 140, 34
_SAMPLE = (12, _H // 2)  # 文字左侧的空白区，避开字形


def _button(text: str = "确定", *, default: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setFont(QFont("Microsoft YaHei", 9))
    button.resize(_W, _H)
    if default:
        button.setDefault(True)
    return button


def _option(button: QPushButton, state: QStyle.StateFlag, *, default: bool = False):
    option = QStyleOptionButton()
    option.rect = button.rect()
    option.text = button.text()
    option.state = state
    if default:
        option.features |= QStyleOptionButton.ButtonFeature.DefaultButton
    return option


def _paint(button: QPushButton, state: QStyle.StateFlag, *, default: bool = False):
    if default:
        button.setProperty("primary", True)
    option = _option(button, state, default=default)
    pixmap = QPixmap(button.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    ButtonStyle().drawControl(
        QStyle.ControlElement.CE_PushButton, option, painter, button
    )
    painter.end()
    return pixmap.toImage()


def test_normal_button_uses_card_background(qapp) -> None:
    image = _paint(_button(), QStyle.StateFlag.State_Enabled)
    assert image.pixelColor(*_SAMPLE).name() == LIGHT.bg_card.lower()


def test_default_button_uses_primary_fill(qapp) -> None:
    button = _button()
    image = _paint(button, QStyle.StateFlag.State_Enabled, default=True)
    assert image.pixelColor(*_SAMPLE).name() == LIGHT.primary.lower()


def test_hover_and_pressed_backgrounds(qapp) -> None:
    button = _button()
    hover = _paint(
        button, QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver
    )
    pressed = _paint(
        button, QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Sunken
    )
    assert hover.pixelColor(*_SAMPLE).name() == LIGHT.bg_hover.lower()
    assert pressed.pixelColor(*_SAMPLE).name() == LIGHT.bg_pressed.lower()


def test_default_hover_and_pressed_use_primary_variants(qapp) -> None:
    button = _button()
    hover = _paint(
        button,
        QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver,
        default=True,
    )
    pressed = _paint(
        button, QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Sunken, default=True
    )
    assert hover.pixelColor(*_SAMPLE).name() == LIGHT.primary_hover.lower()
    assert pressed.pixelColor(*_SAMPLE).name() == LIGHT.primary_pressed.lower()


def test_disabled_button_uses_hover_background(qapp) -> None:
    image = _paint(_button(), QStyle.StateFlag.State_Enabled)
    disabled = _paint(_button(), QStyle.StateFlag.State_None)
    assert disabled.pixelColor(*_SAMPLE).name() == LIGHT.bg_hover.lower()
    assert image.pixelColor(*_SAMPLE).name() != disabled.pixelColor(*_SAMPLE).name()


def test_dark_theme_uses_dark_palette(qapp, monkeypatch) -> None:
    monkeypatch.setattr(button_style, "_theme", lambda: DARK)
    image = _paint(_button(), QStyle.StateFlag.State_Enabled)
    assert image.pixelColor(*_SAMPLE).name() == DARK.bg_card.lower()


def test_size_matches_alpha2_box_model(qapp) -> None:
    """尺寸 = 文字宽 + 2×14 内边距 + 2×1 边框；高 = 行高 + 2×5 + 2。"""
    button = _button("确定")
    style = ButtonStyle()
    option = _option(button, QStyle.StateFlag.State_Enabled)
    size = style.sizeFromContents(
        QStyle.ContentsType.CT_PushButton, option, QSize(), button
    )
    metrics = QFontMetrics(button.font())
    assert size.width() == metrics.horizontalAdvance("确定") + 30
    assert size.height() == metrics.height() + 12


def test_qss_role_button_keeps_stylesheet_size(qapp) -> None:
    """role=icon-btn 等 QSS 按钮不走自绘盒模型，避免重复加内边距。"""
    button = _button("+")
    button.setProperty("role", "icon-btn")
    style = ButtonStyle()
    option = _option(button, QStyle.StateFlag.State_Enabled)
    custom = style.sizeFromContents(
        QStyle.ContentsType.CT_PushButton, option, QSize(10, 10), button
    )
    base = style.baseStyle().sizeFromContents(
        QStyle.ContentsType.CT_PushButton, option, QSize(10, 10), button
    )
    assert custom == base


def test_polish_enables_hover_tracking(qapp) -> None:
    button = QPushButton("确定")
    assert not button.testAttribute(Qt.WidgetAttribute.WA_Hover)
    ButtonStyle().polish(button)
    assert button.testAttribute(Qt.WidgetAttribute.WA_Hover)


def test_focus_does_not_draw_inner_ring(qapp) -> None:
    """alpha.2 的 QSS 按钮没有内侧焦点环：Tab/按压后不应出现圆角线框。"""
    image = _paint(
        _button("确定"),
        QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_HasFocus,
    )
    assert image.pixelColor(3, _H // 2).name() == LIGHT.bg_card.lower()


def test_auto_default_without_primary_stays_normal(qapp) -> None:
    """QDialog 的 autoDefault 不会把辅助按钮画成主色：只看 primary 属性。"""
    button = _button("编辑")
    button.setDefault(True)
    image = _paint(button, QStyle.StateFlag.State_Enabled)
    assert image.pixelColor(*_SAMPLE).name() == LIGHT.bg_card.lower()


def test_mnemonic_is_not_measured(qapp) -> None:
    """QWizard 的 &Finish 等助记符不参与宽度计算（绘制时也会剥掉）。"""
    style = ButtonStyle()
    with_amp = _button("&Finish")
    plain = _button("Finish")
    option_amp = _option(with_amp, QStyle.StateFlag.State_Enabled)
    option_plain = _option(plain, QStyle.StateFlag.State_Enabled)
    size_amp = style.sizeFromContents(
        QStyle.ContentsType.CT_PushButton, option_amp, QSize(), with_amp
    )
    size_plain = style.sizeFromContents(
        QStyle.ContentsType.CT_PushButton, option_plain, QSize(), plain
    )
    assert size_amp == size_plain
