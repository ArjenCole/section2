"""config.toml 读写：界面主题、最近打开工程、AI profile、新建向导默认值。

- 配置文件位置见 core.paths.config_file_path()，与工程文件严格分离；
- API key 一律不进配置文件（只进 keyring，见 §8.1），此模块不提供保存 key 的接口；
- 读取用标准库 tomllib（Python 3.11+），写入用 tomli_w。
"""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from app.core.paths import config_file_path
from app.core.version import DEFAULT_ATLAS_NAME

DEFAULT_CONFIG: dict[str, Any] = {
    "ui": {
        "theme": "light",
        "ai_panel_expanded": False,
        "last_dir": "",
    },
    "new_project": {
        "project_name": "新建项目",
        "project_index": "001",
        "author": "",
        "atlas_name": DEFAULT_ATLAS_NAME,
        "segment_name": "新建标段",
        "unit_name": "新建单位工程",
        "enclosure_name": "默认围护原则",
        "foundation_name": "默认地基处理原则",
    },
    # M7 使用；providers 为 [[ai.providers]] 数组表，key 存 keyring 不在此处
    "ai": {
        "active_provider": "",
        "temperature": 0.2,
        "providers": [],
    },
    "recent_projects": [],
}

_RECENT_LIMIT = 10


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并，保证新增默认项对老配置文件也生效。"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    """读取 config.toml；文件不存在或损坏时返回默认配置。"""
    path = config_file_path()
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return copy.deepcopy(DEFAULT_CONFIG)
    return _merge(DEFAULT_CONFIG, data)


def save_config(config: dict[str, Any]) -> None:
    """整份写回 config.toml 并刷新缓存。"""
    with config_file_path().open("wb") as handle:
        tomli_w.dump(config, handle)
    _Proxy.reload()


def update_config(updates: dict[str, Any]) -> dict[str, Any]:
    """按键合并写回（嵌套 dict 递归合并）。"""
    merged = _merge(load_config(), updates)
    save_config(merged)
    return merged


def add_recent_project(path: str | Path) -> None:
    """把工程路径插到最近打开列表首位（去重、限长）。"""
    config = load_config()
    text = str(path)
    recent: list[str] = [p for p in config.get("recent_projects", []) if p != text]
    recent.insert(0, text)
    config["recent_projects"] = recent[:_RECENT_LIMIT]
    save_config(config)


def remove_recent_project(path: str) -> None:
    config = load_config()
    text = str(path)
    config["recent_projects"] = [p for p in config.get("recent_projects", []) if p != text]
    save_config(config)


class _Proxy:
    """配置读取代理，带缓存；任何写操作后缓存自动失效。"""

    _cache: dict[str, Any] | None = None

    @classmethod
    def reload(cls) -> None:
        cls._cache = None

    @classmethod
    def _data(cls) -> dict[str, Any]:
        if cls._cache is None:
            cls._cache = load_config()
        return cls._cache

    @property
    def ui(self) -> dict[str, Any]:
        return self._data().get("ui", {})

    @property
    def ui_theme(self) -> str:
        theme = self.ui.get("theme", "light")
        return theme if theme in ("light", "dark") else "light"

    @property
    def ai_panel_expanded(self) -> bool:
        return bool(self.ui.get("ai_panel_expanded", False))

    @property
    def last_dir(self) -> str:
        return str(self.ui.get("last_dir", ""))

    @property
    def new_project(self) -> dict[str, Any]:
        return self._data().get("new_project", {})

    @property
    def ai(self) -> dict[str, Any]:
        return self._data().get("ai", {})

    @property
    def ai_providers(self) -> list[dict[str, Any]]:
        return list(self.ai.get("providers", []))

    @property
    def ai_active_provider(self) -> str:
        return str(self.ai.get("active_provider", ""))

    @property
    def ai_temperature(self) -> float:
        try:
            return float(self.ai.get("temperature", 0.2))
        except (TypeError, ValueError):
            return 0.2

    def ai_provider(self, name: str) -> dict[str, Any] | None:
        for provider in self.ai_providers:
            if provider.get("name") == name:
                return provider
        return None

    @property
    def recent_projects(self) -> list[str]:
        return [str(p) for p in self._data().get("recent_projects", [])]


def get_config() -> _Proxy:
    return _Proxy()
