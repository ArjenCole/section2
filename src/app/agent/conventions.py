"""领域约定单一事实来源。

工具 description、system prompt 基础层与 `get_conventions` 工具都从这里取文本，
避免三处各写一份（改一处即可）。
"""

from __future__ import annotations

from app.core.models.models import CATEGORY_CHOICES, CATEGORY_NAMES
from app.core.pipe_category import PIPE_CATEGORIES, WIDTH_PIPE_TYPES

#: 构件类别枚举（不含空类别）
CATEGORY_ENUM: list[str] = [CATEGORY_NAMES[value] for value in CATEGORY_CHOICES]

#: 原则类型枚举
PRINCIPLE_KINDS: dict[str, str] = {
    "enclosure": "沟槽围护原则",
    "foundation": "地基处理原则",
    "precipitation": "挖填降水原则",
    "width": "面宽原则",
}

#: 开挖土质枚举（挖填降水原则 excvt，v10 起由围护原则移入）
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

#: 面宽原则的六类管材接口（宽度表行）——定义在 core.pipe_category，此处仅转出
#: （前四类是管道行“管材”列的候选；包封埋管 / 箱涵-管廊由构件类别固定取）

CONVENTIONS_TEXT = f"""\
# Section 2.0 领域约定（AI 工具必读）

## 构件与原则
- 构件类别：{'、'.join(CATEGORY_ENUM)}。
- 每个构件按名字引用四类原则：沟槽围护(pe_name)、地基处理(pf_name)、降水(pp_name)、
  面宽(pw_name)。原则名必须来自 list_principles 的结果，禁止编造。
  （多围护/多地基原则引用已取消：每个构件只引用一条围护、一条地基原则。）
- 构件埋深(depth)/数量(amount)/参数值/管材含量都可写算式原文（如 "2.5+0.3"），
  工具按字符串原文接收，另返回 *_value 数值。

## 管材与图集（v9）
- 每根管材都有“类别” cat，取值只能是：{' / '.join(PIPE_CATEGORIES)}。
  它是**计算的唯一依据**（面宽表行 / 图集表分流 / 断面图是否画砼基础 / 包封砼扣管位），
  mat（材质文字，如“球墨铸铁管 K9”）只用于显示与规格，不参与计算。
- 面宽匹配：只有直埋构件读类别与管径（取第一根管）；包封埋管固定取“包封埋管”行，
  箱涵 / 管廊固定取“箱涵-管廊”行，不看 cat。
- **候选参数列（v10）**：直埋构件的 管道壁厚 / 工作面加宽 / 垫层厚 / 基础厚 来自
  element_atlas_candidate 表的 8 组快照（采用/不采用混凝土基础 × 90/120/150/180，
  含 t；混凝土管 8 组、其他管材 4 组值相同）。参数值按当前围护原则的
  con_found + found_angle 自动选组，**参数值列锁定不可手填**；候选本身是一次性
  快照，用户可改，改完立即自动重匹配。围护原则 / 管材类别变化都会自动重匹配。
- 图集事实：06MS201-1 砼管**砼基础表没有 150° 行**（砂基础有），所以
  “采用混凝土基础-150°”的候选为空，匹配时按就近角度跳过空组；金属 / 化学建材
  管材图集的 a / C1 列常为空（候选 None → 参数值空 = 引擎回退自动查表）。
- 直埋管材行的壁厚只读，值由参数行「管道壁厚」带出（要改就改候选值）。
- 包封埋管 / 箱涵 / 管廊 / 顶管 / 牵引管没有候选列，参数值仍由用户自由编辑。
- 管材行数限制：直埋管道 / 顶管 / 牵引管只允许一条管材（不能 add_pipe 也不能
  delete_pipe）；附属构筑物不带管材（不能 add_pipe）。只有包封埋管 / 箱涵 /
  管廊可以增删管材行。
- add_pipe / update_pipe 传 cat 会立即触发重匹配；不传则按 mat 折算。
- resolve_atlas 工具仍可用于核对某个材质 + 管径的图集取值（单位 mm，groove_b 为 m）。

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
