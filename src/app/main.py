"""程序入口（计划 §3）。

用法：

    .venv\\Scripts\\python.exe src\\app\\main.py [工程文件.stn2]

启动参数可带一个 .stn2 路径，直接打开该工程。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def _bootstrap_path() -> None:
    """支持 `python app/main.py` 直接运行：把项目根目录加进 sys.path。"""
    if __package__ in (None, ""):
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)


_bootstrap_path()

import app  # noqa: E402,F401  先导入本包：内含 Windows 系统 ICU 预加载，必须早于 PySide6
from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator  # noqa: E402
from PySide6.QtGui import QFontDatabase, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.paths import fonts_dir, log_dir, resources_dir  # noqa: E402
from app.core.version import (  # noqa: E402
    APP_DISPLAY_NAME,
    APP_NAME,
    APP_ORG_DOMAIN,
    APP_ORG_NAME,
    APP_VERSION,
    PROJECT_SUFFIX,
)
from app.resources.qss.theme import apply_initial_theme  # noqa: E402
from app.views.main_window import MainWindow  # noqa: E402
from app.views.widgets.frameless_dialog import FramelessMessageBox

_logger = logging.getLogger("section2")


def setup_logging() -> None:
    """日志同时写 stderr 与用户数据目录下的 section2.log。"""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        handlers.append(logging.FileHandler(log_dir() / "section2.log", encoding="utf-8"))
    except OSError:  # 目录不可写时只保留 stderr
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _install_excepthook() -> None:
    """未捕获异常写日志并提示，避免界面无声退出。"""

    def _hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        _logger.error("未捕获异常", exc_info=(exc_type, exc_value, exc_traceback))
        FramelessMessageBox.critical(
            None,
            "程序错误",
            f"发生未处理的错误：\n{exc_type.__name__}: {exc_value}\n\n"
            f"详细信息见日志：{log_dir() / 'section2.log'}",
        )

    sys.excepthook = _hook


def _load_fonts() -> None:
    """加载随程序分发的字体（app/resources/fonts，缺失则用系统字体）。"""
    folder = fonts_dir()
    if not folder.exists():
        return
    for font_file in folder.iterdir():
        if font_file.suffix.lower() in {".ttf", ".otf"}:
            QFontDatabase.addApplicationFont(str(font_file))


def install_translations(app: QApplication) -> None:
    """装 Qt 自带的中文翻译，让向导/消息框的标准按钮也是中文。"""
    translator = QTranslator(app)
    translations = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    locale = QLocale.system().name()  # 例如 zh_CN
    for name in (f"qtbase_{locale}", f"qt_{locale}", "qtbase_zh_CN"):
        if translator.load(name, translations):
            app.installTranslator(translator)
            _logger.info("已加载 Qt 翻译：%s", name)
            return
    _logger.info("未找到 Qt 中文翻译，界面按钮使用英文")


def _apply_window_icon(app: QApplication) -> None:
    """用随程序分发的 logo 设置窗口/Dock 图标（app/resources/logo/icon_512.png）。"""
    icon_file = resources_dir() / "logo" / "icon_512.png"
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))


def _project_from_args(argv: list[str]) -> str | None:
    for argument in argv[1:]:
        if argument.startswith("-"):
            continue
        if argument.lower().endswith(PROJECT_SUFFIX) or Path(argument).exists():
            return argument
    return None


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    setup_logging()
    _logger.info("启动 %s %s", APP_DISPLAY_NAME, APP_VERSION)

    app = QApplication(arguments)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ORG_NAME)
    app.setOrganizationDomain(APP_ORG_DOMAIN)
    # 不设 Fusion：Fusion 对非可编辑组合框返回 SH_ComboBox_Popup=true，弹出层被按
    # 菜单渲染（位置带偏移、容器带框和阴影）；系统原生样式（windowsvista）下弹出层
    # 紧贴输入框、无框无影，与 Quotor / brackets2 的表现一致。外观差异由 QSS 统一。

    _load_fonts()
    install_translations(app)
    apply_initial_theme(app)
    _apply_window_icon(app)
    _install_excepthook()

    window = MainWindow(project_path=_project_from_args(arguments))
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
