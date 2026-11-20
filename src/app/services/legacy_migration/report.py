"""迁移报告：计数 + 分节明细（UI 必须展示，不得只写日志）。

迁移的一切偏差都进报告，不允许"没有报告的自作主张"（见
docs/legacy_migration_plan.md §8.3）：解析与迁移共用同一份报告实例，
解析阶段的 skipped 不会丢；分节包括 PE×PF 映射、构件拆分明细、管道
匹配、构筑物键处理、单价键重写、补全项与有意差异说明。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MigrationReport:
    """迁移报告（解析 → 建库全程共用一份）。"""

    source: str = ""
    target: str = ""
    schema_version: str = ""
    segments: int = 0
    units: int = 0
    elements: int = 0
    pipes: int = 0
    enclosures: int = 0
    #: 新地基原则条数（PE×PF 交叉生成后）；旧 PF 条数见 source_foundations
    foundations: int = 0
    source_foundations: int = 0
    prices: int = 0
    #: 1.0 多原则条目按比例拆分的源条目数（明细见 split_details）
    splits: int = 0
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    principle_names: list[str] = field(default_factory=list)
    split_details: list[str] = field(default_factory=list)
    #: PE×PF 新地基原则映射表（旧 PF × 旧 PE → 新 PF 名 + 基础参数）
    pf_mappings: list[str] = field(default_factory=list)
    #: 管道匹配明细（旧材质/DN → 模板 / oD/iD/t / 兜底级别）
    pipe_matches: list[str] = field(default_factory=list)
    #: 构筑物键处理明细（原始键 → 解析出的分类/名称/单位）
    structure_keys: list[str] = field(default_factory=list)
    #: 单价键重写（旧 key → 新 key）
    price_rewrites: list[str] = field(default_factory=list)
    #: 2.0 补的默认项（参数 / 宽度表 / 做法 / 止水 / 含钢量），与"原有"区分
    defaults: list[str] = field(default_factory=list)

    def text(self) -> str:
        lines = [
            f"源文件：{self.source}",
            f"目标文件：{self.target}" if self.target else "目标文件：（临时工作库）",
            f"旧版程序版本：{self.schema_version or '未知'}",
            f"标段 {self.segments} 个，单位工程 {self.units} 个，构件 {self.elements} 条，管道 {self.pipes} 根",
            f"围护原则 {self.enclosures} 条，旧地基原则 {self.source_foundations} 条"
            f"（按 围护×地基 交叉生成新地基原则 {self.foundations} 条），单价 {self.prices} 条",
            f"涉及原则：{'、'.join(self.principle_names) if self.principle_names else '（无）'}",
        ]
        for title, items in (
            ("多原则条目按比例拆分", self.split_details),
            ("新地基原则（旧PF·旧PE）", self.pf_mappings),
            ("管道匹配", self.pipe_matches),
            ("构筑物工程量键", self.structure_keys),
            ("单价键重写", self.price_rewrites),
            ("补全项（2.0 补的默认值）", self.defaults),
        ):
            if items:
                lines.append("")
                lines.append(f"{title} {len(items)} 条：")
                lines.extend(f"  · {item}" for item in items)
        lines.append("")
        lines.append("有意差异：多原则条目按 围护×地基 比例拆成独立条目；支撑与管道基础按各条目自己的原则计算（1.0 按主原则）。")
        if self.warnings:
            lines.append("")
            lines.append(f"警告 {len(self.warnings)} 条：")
            lines.extend(f"  · {warning}" for warning in self.warnings)
        if self.skipped:
            lines.append("")
            lines.append(f"跳过 {len(self.skipped)} 条：")
            lines.extend(f"  · {item}" for item in self.skipped)
        if not self.warnings and not self.skipped:
            lines.append("")
            lines.append("无警告，全部数据迁移成功。")
        return "\n".join(lines)
