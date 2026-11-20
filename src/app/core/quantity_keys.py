"""附属构筑物工程量键的三列显示切分（1.0 兼容口径，2.0 核心通用）。

1.0 的工程量键不要求三段（FormSum.FlashItem 按 ``|`` 切分显示，见
docs/legacy_migration_plan.md §7.1）：3 段 = 分类|名称|单位；2 段 = 分类空、
名称 = 第 1 段、单位 = 第 2 段；1 段 = 分类空、名称 = 第 1 段、单位空；
>3 段 = 前两段分类 / 名称、其余合并为单位。

计算输出对所有行统一"有 ``raw_key`` 用 ``raw_key``，否则按三列拼"
（compute_structure，无迁移专用分支）；本模块只负责"键 → 三列显示字段"，
供汇总 / 导出 / 界面显示与迁移写行共用。
"""

from __future__ import annotations


def split_display(key: str) -> tuple[str, str, str]:
    """工程量键 → (分类, 项目, 单位) 三列显示字段（按 1.0 规则）。

    * 3 段：分类 = 段1，项目 = 段2，单位 = 段3；
    * 2 段：分类 = 空，项目 = 段1，单位 = 段2；
    * 1 段：分类 = 空，项目 = 段1，单位 = 空；
    * >3 段：分类 = 段1，项目 = 段2，单位 = 段3 起用 ``|`` 原样合并；
    * 空键：三列全空（调用方跳过该行）。
    """
    parts = str(key or "").split("|")
    if not key or not any(part for part in parts):
        return ("", "", "")
    if len(parts) == 1:
        return ("", parts[0], "")
    if len(parts) == 2:
        return ("", parts[0], parts[1])
    return (parts[0], parts[1], "|".join(parts[2:]))


def parse_quantity_key(key: str) -> tuple[str, str, str, str | None]:
    """迁移用：键 → (分类, 项目, 单位, 警告)。

    与 :func:`split_display` 同规则；>3 段额外给警告（1.0 自身不处理，
    2.0 按"段 3 起合并为单位"显示，键原文经 raw_key 保留）；空键返回
    三列空 + 警告（调用方跳过）。
    """
    text = str(key or "").strip()
    if not text:
        return ("", "", "", "工程量键为空，已跳过。")
    parts = text.split("|")
    if len(parts) > 3:
        return (
            parts[0],
            parts[1],
            "|".join(parts[2:]),
            f"工程量键“{text}”超过 3 段（1.0 不处理该形态），按前两段解析、其余并入单位。",
        )
    return (*split_display(text), None)
