"""Section 2.0 —— 线性工程（市政管道）工程量计算软件。

包结构（见 开发计划.md §3）：

    app/core        版本、路径、配置、事件总线、算式求值
    app/orm         .stn2 工程文件的 SQLAlchemy 表结构
    app/services    工程文件读写、计算引擎、图集、导出、AI
    app/viewmodels  MVVM 视图模型
    app/views       PySide6 界面（主窗体、面板、对话框、向导）
    app/agent       AI 助手工具调用
    app/resources   QSS 主题、图标、字体、图集数据
"""

import ctypes
import os
import sys
from pathlib import Path


def _preload_system_icu() -> None:
    """Windows 上先把系统 ICU 加载进进程，必须在导入 PySide6 之前执行。

    Qt6Core.dll 静态依赖 ``icuuc.dll``。若 PATH 里有第三方 ICU（Anaconda 的
    ``Library\\bin`` 很常见，且它的 icuuc.dll 只有带版本号后缀的符号），
    加载器会绑定到那一份，缺少 Qt 需要的 ``ucnv_*`` 等符号，
    于是 ``import PySide6`` 报 "DLL load failed ... 找不到指定的程序"(WinError 127)。
    这里按绝对路径加载 ``%SystemRoot%\\System32\\icuuc.dll``（转发到系统 icu.dll，
    符号齐全），后续 Qt 就绑定到它。非 Windows 或系统 ICU 缺失时什么都不做。
    """
    if sys.platform != "win32":
        return
    path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "icuuc.dll"
    if not path.exists():
        return
    try:
        ctypes.WinDLL(str(path))
    except OSError:
        pass  # 预加载失败就保持原样，让 PySide6 自己报出真正的原因


_preload_system_icu()

from app.core.version import APP_VERSION  # noqa: E402  必须在 ICU 预加载之后

__all__ = ["APP_VERSION"]
