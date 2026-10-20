"""领域约定单一事实来源。

工具 description、system prompt 基础层与 `get_conventions` 工具都从这里取文本，
避免三处各写一份（改一处即可）。
"""

from __future__ import annotations

from app.core.models.models import CATEGORY_CHOICES, CATEGORY_NAMES

#: 构件类别枚举（不含空类别）
CATEGORY_ENUM: list[str] = [CATEGORY_NAMES[value] for value in CATEGORY_CHOICES]

#: 原则类型枚举
PRINCIPLE_KINDS: dict[str, str] = {
    "enclosure": "沟槽围护原则",
    "foundation": "地基处理原则",
    "precipitation": "降水原则",
    "width": "面宽原则",
}

#: 开挖土质枚举（围护原则 excvt）
EXCVT_CHOICES: tuple[str, ...] = (
    "Ⅰ、Ⅱ类土",
    "Ⅲ类土",
    "Ⅳ类土",
    "松石",
    "次坚石",
    "普坚石",
    "特坚石",
)

#: 坞塝回填枚举（围护原则 dock_h 的界面语义）
DOCK_CHOICES: tuple[str, ...] = ("至管顶50cm", "至管顶标高", "至管中心标高", "至沟槽顶标高")

#: 降水井型（五个列名）
PRECIPITATION_WELLS: tuple[str, ...] = (
    "湿土排水",
    "轻型井点",
    "喷射井点",
    "大口径井点",
    "深井",
)

#: 面宽原则的六类管材接口（宽度表行）
WIDTH_PIPE_TYPES: tuple[str, ...] = (
    "混凝土管-刚性接口",
    "混凝土管-柔性接口",
    "金属类管道",
    "化学建材管道",
    "包封埋管",
    "箱涵-管廊",
)

CONVENTIONS_TEXT = f"""\
# Section 2.0 领域约定（AI 工具必读）

## 构件与原则
- 构件类别：{'、'.join(CATEGORY_ENUM)}。
- 每个构件按名字引用四类原则：沟槽围护(pe_name)、地基处理(pf_name)、降水(pp_name)、
  面宽(pw_name)。原则名必须来自 list_principles 的结果，禁止编造。
- 多围护/多地基：构件可引用多条原则（pe_refs/pf_refs，按 ratio 加权）；
  多围护时 main_pe_name 是主要围护原则（支撑 Z 量按它计算）。
- 构件埋深(depth)/数量(amount)/参数值/管材含量都可写算式原文（如 "2.5+0.3"），
  工具按字符串原文接收，另返回 *_value 数值。

## 单位与格式
- 图集查询（resolve_atlas）返回的 od/t/a/c1/c2/workwidth/groove_b 单位是 mm；
  groove_b 例外：已换算为 m。
- 降水井型存储格式 "深度阈值|井距|侧数"，阈值 -1 表示不启用。
- 构件参数（component_param）值格式 "显示名|表达式"；update_component_params
  按 key 传 {{display, expression}}。
- 面宽原则矩阵：DN 0~3000，步长 100，宽度单位 mm；取值方式
  WorkWidth=按工作面宽度表，B=按沟槽宽度表。

## 计算表达式（产品核心规则，改数据前必须理解）
- 每个工程量除数值外还有一条“数值代入”算式；派生量不做预运算
  （槽底宽、毫米→米换算、换填总厚、弓形占位都写全过程）。
- 只有直接录入或查表的原始数据与软件常数是单个数字；mm→m 写成 `值/1000`。
- 括号只在语法必需处出现。
- 中间步骤（steps）逐项为“说明 + 该步算式”，各步拼接恒等于完整算式；
  工具返回的 steps 不得自行改写或拼接。
- 用户录入的算式以原文进表达式，不要替用户预计算后回写。

## 操作约定
- 写操作即时 commit 落盘（自动保存），首次修改自动备份到工程同级 Backup\\。
- 禁止编造 id / 原则名：先查询（get_project_tree / list_elements /
  list_principles / list_library_templates）再写。
- 找不到目标时按错误文案里的指引先查询，不要反复重试同一调用。
- 大批量操作前先用只读工具确认范围；写操作在客户端会请求用户确认。
"""
