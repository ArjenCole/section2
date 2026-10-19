"""路径解析：用户配置目录、日志目录、随程序分发的资源目录。

配置文件（config.toml）与工程文件严格分离：配置文件放 platformdirs 的用户目录，
工程文件由用户自己选路径。
"""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs

from app.core.version import APP_NAME


def app_data_dir() -> Path:
    """用户配置/数据目录（Windows: %APPDATA%\\Section2）。

    环境变量 ``SECTION2_DATA_DIR`` 可指到别的目录：测试（tests/conftest.py）
    用它把配置 / 数据目录换成临时目录，不碰开发机上的真实 config.toml。
    """
    override = os.environ.get("SECTION2_DATA_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))


def ensure_app_data_dir() -> Path:
    """确保用户数据目录存在并返回。"""
    path = app_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_file_path() -> Path:
    """config.toml 全路径。"""
    return ensure_app_data_dir() / "config.toml"


def log_dir() -> Path:
    """日志目录（自动创建）。"""
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_project_dir() -> Path:
    """新建工程时的默认目录：<我的文档>\\Section2（自动创建）。"""
    path = Path(platformdirs.user_documents_dir()) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def resources_dir() -> Path:
    """随程序分发的资源目录 app/resources。"""
    return Path(__file__).resolve().parent.parent / "resources"


def atlas_dir() -> Path:
    """图集 xlsx 目录 app/resources/atlas（M3 填充数据）。"""
    return resources_dir() / "atlas"


def fonts_dir() -> Path:
    return resources_dir() / "fonts"
