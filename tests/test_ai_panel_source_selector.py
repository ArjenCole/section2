"""AI 面板模型来源选择器：按钮定位、provider 菜单、管理模型入口与切换落盘。"""

from __future__ import annotations

import pytest

from app.core.config import get_config, set_ai_active_provider, update_config
from app.views.panels.ai_panel import AiPanel


def _configure_providers() -> None:
    update_config(
        {
            "ai": {
                "active_provider": "p1",
                "providers": [
                    {
                        "name": "p1",
                        "display_name": "OpenCode Go",
                        "base_url": "",
                        "default_model": "model-a",
                    },
                    {
                        "name": "p2",
                        "display_name": "DeepSeek 官方",
                        "base_url": "",
                        "default_model": "deepseek-chat",
                    },
                ],
            }
        }
    )


@pytest.fixture(autouse=True)
def _reset_ai_config():
    update_config({"ai": {"active_provider": "", "providers": []}})
    yield
    update_config({"ai": {"active_provider": "", "providers": []}})


def test_source_button_shows_active_provider_left_of_send(qapp) -> None:
    _configure_providers()
    panel = AiPanel()
    panel.resize(360, 500)
    panel.layout().activate()
    panel._refresh_source_button()
    panel._reposition_overlay_buttons()

    assert not panel._source_btn.isHidden()
    assert panel._source_label(panel._active_provider()) == "OpenCode Go/model-a"
    # 窄面板可能省略来源名，但“/模型”部分保留
    assert "/model-a" in panel._source_btn.text()
    # 箭头由按钮自绘（与 QComboBox 同款），不再是文字里的 ▾
    assert "▾" not in panel._source_btn.text()
    assert panel._source_btn.x() < panel._send_btn.x()
    assert panel._source_btn.x() >= 0


def test_source_button_hidden_without_provider(qapp) -> None:
    panel = AiPanel()
    panel._refresh_hint()

    assert panel._source_btn.isHidden()


def test_source_menu_lists_providers_with_manage_entry(qapp) -> None:
    _configure_providers()
    panel = AiPanel()

    menu = panel._build_source_menu()
    assert menu is not None
    actions = menu.actions()
    texts = [action.text() for action in actions]
    assert texts == ["OpenCode Go", "DeepSeek 官方", "", "管理模型"]
    assert actions[2].isSeparator()
    assert actions[0].isChecked()
    assert not actions[1].isChecked()


def test_selecting_provider_updates_config_and_button(qapp) -> None:
    _configure_providers()
    panel = AiPanel()

    menu = panel._build_source_menu()
    assert menu is not None
    menu.actions()[1].trigger()

    assert get_config().ai_active_provider == "p2"
    assert get_config().ai_provider("p1")["default_model"] == "model-a"
    assert get_config().ai_provider("p2")["default_model"] == "deepseek-chat"
    assert panel._source_label(panel._active_provider()) == "DeepSeek 官方/deepseek-chat"
    # 离屏环境没有字体、来源名被省略，但当前模型部分保留
    assert "/deepseek-chat" in panel._source_btn.text()


def test_source_label_uses_slash_format() -> None:
    assert (
        AiPanel._source_label(
            {"display_name": "OpenCodeGo", "default_model": "deepseek-V4.1-flash"}
        )
        == "OpenCodeGo/deepseek-V4.1-flash"
    )
    assert AiPanel._source_label({"name": "p", "default_model": ""}) == "p"


def test_manage_model_action_opens_settings(qapp, monkeypatch) -> None:
    _configure_providers()
    panel = AiPanel()
    calls: list[bool] = []
    monkeypatch.setattr(panel, "_open_settings", lambda: calls.append(True))

    menu = panel._build_source_menu()
    assert menu is not None
    menu.actions()[-1].trigger()
    qapp.processEvents()  # 菜单动作经 singleShot 打开窗体

    assert calls == [True]


def test_set_ai_active_provider_ignores_unknown_name() -> None:
    _configure_providers()

    set_ai_active_provider("missing")

    assert get_config().ai_active_provider == "p1"
