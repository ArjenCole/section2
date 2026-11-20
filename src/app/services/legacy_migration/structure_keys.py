"""附属构筑物工程量键的 1.0 兼容解析（1 / 2 / 3 / >3 段）。

解析规则的单点实现放 2.0 核心 :mod:`app.core.quantity_keys`（显示 / 汇总
切分也要用，而 2.0 核心不得依赖迁移包，见 docs/legacy_migration_plan.md
§0.1.1）；本模块按计划 §0.1.1 的包结构保留入口，转发实现。
"""

from __future__ import annotations

from app.core.quantity_keys import parse_quantity_key, split_display

__all__ = ["split_display", "parse_quantity_key"]
