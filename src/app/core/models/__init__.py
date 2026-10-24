"""core.models 子包：临时工作库（SQLite）的表结构与连接生命周期。

工程文件 `.stn` 是 1.0 风格 XML 头 + JSON 数据体（见 services/stn_format）；
每次打开工程由 JSON 重建临时工作库、关闭即删除
（见 base.create_working_database / close_database）。
"""

from app.core.models.base import Base

__all__ = ["Base"]
