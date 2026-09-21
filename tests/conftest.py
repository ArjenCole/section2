"""pytest 全局配置。

这里先 ``import app``：包初始化里会预加载 Windows 系统 ICU，
必须早于任何模块导入 PySide6（详见 app/__init__.py 的说明）。
"""

import app  # noqa: F401
