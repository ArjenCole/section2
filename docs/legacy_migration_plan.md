# 1.0 `.stn` → 2.0 迁移开发计划

> 状态：计划稿（未改代码）
>
> 目标：1.0 工程打开后，**1.0 里填写的原则、参数、构件关系必须能在 2.0 数据里找到对应值**；不要求新旧算量数字一致，但不能静默丢数据、错配原则或把 1.0 没有的值写进 2.0。
>
> 本文把已确认的五项决策写成可执行方案，并列出仍需产品/业务确认的问题。

---

## 0. 已确认的决策

### 决策 1：管道按 DN 到 2.0 构件库匹配 oD / iD / t / a / C1 / C2

- 1.0 管道只有 `Mat / Dn / Content`；2.0 迁移时以 `Dn` 为键，到 2.0 构件库 `EleInventory.json` 里匹配同材质、同 DN 的模板。
- 匹配结果写进 2.0 构件：
  - 管道行：`od`、`inner_d`、`t`、`direct`；
  - 直埋构件：生成 8 组候选并自动匹配出 `工作面加宽`、`垫层厚`、`基础厚` 三行参数（见 §4.4 / §10.1 第 7 条）；
  - 包封 / 箱涵 / 管廊：按 2.0 约定取固定 `a=100 / C1=100 / C2=0`，不按管道图集匹配；
  - 顶管 / 牵引管：只匹配管道 `od/iD/t`，不写 `a/C1/C2`。
- 1.0 里所有 `Dn` 字样，导入 2.0 后统一为 `DN`：
  - 管道字段、构件规格文本、管材工程量键、旧单价键；
  - 不盲目替换用户自己输入的材料名/参数文本（范围见 §10.1 第 9 条）。

### 决策 2：多围护原则的基础参数，按 PE × PF 生成新地基原则

- 1.0 的 `ConFound / FoundAngle / Cush` 挂在围护原则 PE 上；2.0 挂在地基原则 PF 上。
- 原 PE1/PE2/PE3 × PF1/PF2，迁移后生成（实际名称采用“旧PF名·旧PE名”，下表用编号示意）：

  | 旧 PF | 旧 PE | 新 PF（示意） | 实际名称示例 |
  |---|---|---|---|
  | PF1 | PE1 | PF11 | `PF1·PE1` |
  | PF1 | PE2 | PF12 | `PF1·PE2` |
  | PF1 | PE3 | PF13 | `PF1·PE3` |
  | PF2 | PE1 | PF21 | `PF2·PE1` |
  | PF2 | PE2 | PF22 | `PF2·PE2` |
  | PF2 | PE3 | PF23 | `PF2·PE3` |

- 每个新 PF 克隆旧 PF 的换填层和特殊地基构件，但 `ConFound / FoundAngle / Cush` 取对应 PE 的值。
- 每条构件按 1.0 原本匹配的 PE 和 PF 取新 PF：原 PE1 + PF2 → 新 PE1 + `PF2·PE1`。
- 这样 1.0 里所有 PE 的 `ConFound / FoundAngle / Cush` 和所有 PF 的换填/特殊地基都能保留下来。

### 决策 3：多原则条目拆成多条单原则构件

- 原条目 PE1 40% + PE2 60% → 拆成两条，分别引用 PE1、PE2，数量分别为原数量的 40%、60%。
- 围护、地基都是多原则时做笛卡尔积：
  - 2 围护 × 2 地基 = 4 条；
  - 2 围护 × 3 地基 = 6 条；
  - 每条数量 = 原数量 × PE 比例 × PF 比例。
- 拆分后的每条构件只引用一条 PE、一条 PF（新 PF 见决策 2）。
- 例外：构筑物 / 顶管 / 牵引管的工程量不随原则比例变化，**不拆**（见 §6.9），原始 refs 写入 `legacy_meta`。

### 决策 4：支撑按拆分后各自分配到的 PE 计算

- 1.0 多原则条目的支撑统一按 `mainPEname` 计算；2.0 拆分后每条单原则构件按自己的 PE 计算支撑。
- 这是有意设计，接受与 1.0 支撑结果不一致；迁移报告里注明即可，不要求兼容 1.0 的 mainPE 支撑口径。
- `mainPEname` 不再参与 2.0 计算；作为旧数据写入 `legacy_meta`（见 §10.1 第 5 条）。

### 决策 5：构筑物工程量键不足三段时，沿用 1.0 的识别逻辑

1.0 的真实逻辑（[FormSum.cs](../section/section-master/section/FmData/FormSum.cs#L297-L347)）：

- `mcE7.getDQ` 把 `Param` 里**所有不以 `-` 开头的键**都当作工程量键，键原文直接作为工程量 key，不要求 `|`，也不解析分类/名称。
- 汇总表显示时按 `|` 切分：
  - 3 段：`分类 | 名称 | 单位`；
  - 2 段：`分类=空`，`名称=第1段`，`单位=第2段`；
  - 1 段：`分类=空`，`名称=第1段`，`单位=空`；
  - 大于 3 段：1.0 的 `if` 分支不处理，显示为空（1.0 自身缺陷）。
- 计价：1.0 `getPrice` 用**原始 key** 精确查价，不按分类/名称重新拼。
- 汇总分组：1.0 用 `tStr[0]`（第一段）作为分组键；2 段键按第 1 段分组，1 段键按整个 key 分组。

因此 2.0 不能再用“必须三段”的假设。方案见 §7：保留原始 key，按 1.0 规则解析显示，计价和汇总用原始 key。

---

## 0.1 架构约束（新增，优先级最高）

> 兼容 1.0 的改动**不能影响任何 2.0 功能**；迁移逻辑必须独立；迁移后的文件按正常 2.0 文件打开，2.0 打开路径不区别对待。

### 0.1.1 独立迁移模块

新增独立包：

```text
src/app/services/legacy_migration/
├── __init__.py          # 对外 API：detect / parse / build_database / migrate / backup / report
├── parser.py            # 1.0 XML → LegacyProject（原 stn_migration 解析部分）
├── matcher.py           # DN → 2.0 构件库模板匹配
├── principles.py        # PE × PF 新地基原则生成
├── splitter.py          # 多原则拆分 / 比例 / 名称
├── structure_keys.py    # 构筑物 1/2/3/>3 段键解析
├── writer.py            # 写工作库 / 生成 2.0 数据
└── report.py            # 迁移报告
```

`project_io.open_legacy_project` 保留为 2.0 侧的薄入口：只负责“检测到 1.0 → 延迟 import 迁移包 → 打开工作库 / 备份 / 提示 / undo 重置”，不承载解析/匹配/拆分逻辑。

依赖方向：

- `legacy_migration` 可以依赖 `app.core.models`、`app.services.element_library`、`app.services.atlas_match` 等 2.0 服务；
- **2.0 核心不得反向依赖 `legacy_migration`**；
- 2.0 启动、正常打开/保存/计算/汇总/导出路径不得 import 迁移包；
- 只有两个入口延迟 import：
  1. `project_io.open_project` 检测到 1.0 XML 后，才 `from app.services import legacy_migration`；
  2. `legacy_import_dialog` 打开导入向导时，才 import。
- `element_library._from_legacy`（没有 JSON 资产时的兜底）改为函数内延迟 import；
- `.spcp` 单原则导入也归到 `legacy_migration`，由 `project_io` 延迟 import。

### 0.1.2 迁移后的文件就是普通 2.0 文件

- 迁移写出标准 `Section2` JSON，`file_version` 为当前 2.0 版本，不带 `migrated`/`is_legacy` 标记；
- `legacy_meta` / `raw_key` 是**普通可选字段**，不是“迁移文件标记”；
- 2.0 打开迁移文件走 `open_project` 的正常分支，不检查 `legacy_meta`、不检查来源、不弹迁移提示；
- 2.0 计算/汇总/导出不写 `if migrated` / `if legacy_meta` 之类的分支：
  - `compute_structure` 对所有工程量行统一“有 `raw_key` 用 `raw_key`，否则用 `category|item|unit`”；
  - `summary` 对所有行统一“先精确 key，再 scope 回落”；
  - `unit_vm` 来源列统一显示 `Element.source` 文本。
- 迁移器只负责“把 1.0 数据写成正常的 2.0 数据”，不负责运行时特殊逻辑。

### 0.1.3 对 2.0 的影响面

| 改动 | 对正常 2.0 文件的影响 |
|---|---|
| `ElementQuantity.raw_key` 可选字段 | 正常文件为空；`compute_structure` 行为不变 |
| `Element.legacy_meta` / `BasicInfo.legacy_meta` 可选字段 | 正常文件为空；不参与计算/UI 主流程 |
| `Element.source` 写迁移摘要 | 正常文件仍由现有“来源”列显示，无新分支 |
| `STN_FILE_VERSION` 保持 2（不升版本） | 2.0 未正式发布，没有需要兼容的旧 2.0 文件；新增可选字段不升版本 |
| 新增迁移包 | 2.0 启动/正常路径不 import；无启动开销、无循环依赖 |

---

## 1. 现状与问题清单（只列与“数据原样”有关的）

| 编号 | 现状 | 影响 | 处理方向 |
|---|---|---|---|
| P0-1 | 迁移把管道写成 `od = inner_d = Dn`，`t` 被反算成 0 | 1.0 没有 oD/iD，2.0 却写入了错误的外径/壁厚 | 改为按 DN 到构件库匹配，见 §4 |
| P0-2 | 所有 PF 都套第一条 PE 的 `ConFound/FoundAngle/Cush` | 多 PE 工程基础参数丢失/错配 | 按 PE×PF 生成新 PF，见 §5 |
| P0-3 | 多原则比例只进数量算式/名称，单引用比例≠1 直接丢 | 比例不是结构化数据，用户改数量后不可恢复 | 拆分时写数量；增加 `legacy_meta` 留档（已确认），见 §6/§10 |
| P0-4 | `mainPEname / showPEname / showPFname` 没有对应字段 | 用户选择的主原则/显示名丢失 | 写入 `legacy_meta`（已确认） |
| P0-5 | 构筑物工程量键按三段硬拆；两段直接 `ValueError`，无 `|` 变参数 | 迁移中断或工程量丢失 | 保留原始 key，见 §7 |
| P0-6 | `parse_legacy` 的 skipped 报告没有回传；单元素坏会丢整标段 | 静默丢数据，报告空白 | 重构解析报告，见 §8 |
| P0-7 | 旧单价键 `Dn` 与 2.0 新键 `DN` 不一致 | 单价数据在但用不上 | 迁移时统一 `Dn → DN`，见 §9 |
| P1-1 | 参数键被拆成 `key/unit`，结构参数去 `-`，Z 键转 F | 语义保留，原文不保留 | 可接受；报告中注明转换规则 |
| P1-2 | 缺参数/缺宽度表/缺做法/缺止水自动补默认 | 2.0 出现 1.0 没有的数据 | 补默认时写报告；区分“原有/补全” |
| P1-3 | 未知 `Category` → 0；宽度表“箱涵” → “箱涵-管廊” | 原始字符串丢失 | 报告中记录原名；必要时加 legacy 字段 |
| P1-4 | 文本 `strip`、`Dn/FoundAngle` 转 int | 首尾空白/小数精度丢失 | 能保留原文的保留；不能的写报告 |
| P1-5 | 旧版本号只进报告/备份名 | 新工程数据里没有来源版本 | 写入 `BasicInfo.legacy_meta`（已确认） |

---

## 2. 目标数据模型改动

### 2.1 `ElementQuantity` 增加原始键

新增列：

- `raw_key: str = ""`：1.0 工程量键原文（如 `构筑物|垫层`、`土方`、`a|b|c|d`）。

用途：

- `compute_structure` 输出工程量时优先用 `raw_key`，保证 1.0 的 1/2 段键、带空段的键不被改写；
- 计价按原始 key 精确优先；汇总/导出按 2.0 原生口径（`category/item/unit`）；
- `category/item/unit` 用于显示、编辑和 2.0 原生分组。

`stn_codec`：

- 导出：`quantities` 每行增加可选 `"raw_key"`；
- 导入：缺省 `""`，旧 2.0 文件不受影响。

`STN_FILE_VERSION`：

- **保持 2，不升版本**。2.0 未正式发布过，不存在需要兼容的旧 2.0 文件；`raw_key` 作为可选字段直接加入当前结构，读取缺省 `""`。

### 2.2 `legacy_meta`（已确认增加）

新增两个可空 JSON 文本列，保存 1.0 原始信息，**不参与计算**：

**工程级：`BasicInfo.legacy_meta`**

```json
{
  "source_version": "1.2.2.1",
  "source_file": "（可选，本机路径）",
  "migrated_at": "2026-11-18T16:00:00"
}
```

**构件级：`Element.legacy_meta`**

```json
{
  "show_pe_name": "多围护原则",
  "show_pf_name": "多地基原则",
  "main_pe_name": "钢板桩",
  "pe_refs": [{"name": "放坡开挖", "ratio": 0.6}, {"name": "钢板桩", "ratio": 0.4}],
  "pf_refs": [{"name": "没有地基处理", "ratio": 1.0}],
  "assigned_pe": "钢板桩",
  "assigned_pf": "没有地基处理·钢板桩",
  "assigned_ratio": 0.4,
  "source": "旧版来源原文（Element.Source）",
  "source_version": "1.2.2.1"
}
```

说明：

- 拆分后的每个子构件都保留**原构件的完整 refs**，并额外记录自己分到的 `assigned_pe / assigned_pf / assigned_ratio`；
- `show/main` 名、比例、旧版本号不再只存在于报告或名称后缀里；
- **主表单来源列**：迁移时把 `legacy_meta` 的紧凑摘要写进 `Element.source`，例如：
  `1.0迁移｜PE:放坡开挖60%,钢板桩40%｜PF:没有地基处理100%｜主PE:钢板桩`
  - 旧 1.0 的 `Element.Source` 原文不能丢：先保留原文，再拼摘要：
    `旧Source｜1.0迁移｜PE:…｜PF:…`；旧 Source 为空时只写摘要；
  - 旧 Source 原文同时存 `legacy_meta["source"]`，保证可还原；
  - 2.0 正常显示 `source` 文本，不新增 UI 分支；
  - `source` 是 `String(200)`，摘要超长时截断；完整内容在 `Element.legacy_meta`；
  - **只读面板**：详情面板新增“来源信息”页，只在 `Element.legacy_meta` 非空时显示；
    - 只读，格式化 JSON，提供复制；
    - 显示 show/main/PEname/PFname 比例/assigned 信息/旧版本号/旧 Source；
    - 正常 2.0 文件该页隐藏，不出现空页；
    - 来源列显示摘要，完整 JSON 在这个只读页看。
- `STN_FILE_VERSION` **保持 2**；`stn_codec` 读写可选字段，缺省为空。

### 2.3 `PcpFoundation` 增加来源标记（可选）

新增 `legacy_meta`（JSON）或 `legacy_pe_name`，记录该新 PF 由哪条旧 PE + 旧 PF 生成，便于报告和排查。不是算量必需。

---

## 3. 迁移总流程

```
读取 1.0 XML
  ↓
解析为 LegacyProject（保留原始 PE/PF/元素/参数/价格/版本）
  ↓
建立 PE/PF 索引与原始引用
  ↓
为每个 (旧 PF, 旧 PE) 生成新 PF（§5）
  ↓
为每个旧构件：
    解析 PEname/PFname 比例
    笛卡尔积拆成单原则子构件（§6）
    匹配 2.0 构件库管道参数（§4）
    写入子构件、管道、参数、候选、工程量行
  ↓
单价键 Dn → DN（§9）
  ↓
生成迁移报告（§8）
  ↓
写临时工作库 / 另存为 .stn
```

关键原则：

- **先建原则，再建构件**：新 PF 必须先落库，子构件才能按名引用。
- **一条旧构件可能变成多条**：拆分在主循环内完成，保持原顺序。
- **所有无法原样保留的值都要进报告**：不能静默跳过。

---

## 4. 管道 DN → 2.0 构件库匹配

### 4.1 输入

- 旧管道：`mat`（材质）、`dn`（Dn，mm）、`content`；
- 旧构件类别（直埋/包封/箱涵/顶管/牵引管/管廊/构筑物）；
- 该子构件对应的新 PF 的 `con_found`、`found_angle`（用于取 t/a/C1/C2）。

### 4.2 匹配键

优先顺序（已确认）：

1. **材质完全相等 + DN 完全相等 + 构件类别相同**；
2. **材质包含关系 + DN 完全相等 + 构件类别相同**（例如旧 `Ⅱ级混凝土管` 与库 `Ⅱ级混凝土管`，或旧名带前缀/后缀）；
3. **管材类别（`cat`）+ DN 完全相等 + 构件类别相同**；
4. **同材质 + 1.0 TrimDn 映射 DN**：1400→1350、1600→1650、2700→2800、>2800→3000；映射后仍按 1~3 的材质/类别规则匹配；
5. **同材质 + 最近 DN**（1.0 TrimDn 映射不覆盖时；等距取大尺寸）；
6. 以上都不命中：不写 oD/iD/t，记 warning，计算时由 2.0 图集兜底。

补充约束：

- 每一级都**先限同构件类别**（直埋/顶管/牵引管等）；没有同类别候选时才放宽到其他类别，并在报告里注明；
- **级别标记必须一致**：Ⅰ/Ⅱ/Ⅲ 级混凝土管、K8/K9/K10 球墨管、1.0/1.6MPa 焊接钢管等，不能只靠“材质包含”跨级别匹配；
- 材质包含关系只用于同级别/同管材类别内的前缀、后缀差异（如“钢筋混凝土管”与“混凝土管”）。

**多个模板命中时，只看 DN**（已确认）：

- DN 大者优先；
- DN 相同，按“材质完全相等 → 级别一致 → 构件类别相同 → 构件库顺序”选；
- 不再比较 `od` / `t`；
- 报告记录所有候选和最终选择，避免“静默选了另一个”。

匹配范围：

- `app/resources/inventory/EleInventory.json` 的 `categories → units → elements → pipes`；
- 用 `services/element_library.py` 的 `element_library()` 读取，避免直接读 JSON。

### 4.3 从模板取 oD / iD / t

模板管道字段（见 `PipeTemplate`）：

- `direct`：`id_t` / `od_t` / `od_id` / `""`；
- `od`、`inner_d`：直取对里给出的值，另一个为 `None`；
- `thickness`：`{"con90": ..., "plain120": ...}` 八组。

取值：

1. `t = pipe.thickness_at(con_found, found_angle)`；
   - 该方法已做“同组就近 → 砼组同角度”兜底；
   - 仍为 `None` 时，`t = 0` 并记 warning。
2. 按 `direct` 归一化：
   - `id_t`：`iD = pipe.inner_d or dn`；`oD = iD + 2t`；
   - `od_t`：`oD = pipe.od or dn`；`iD = oD - 2t`；
   - `od_id`：`oD = pipe.od`；`iD = pipe.inner_d`；`t = (oD - iD) / 2`；
   - `""`：若 `od`/`inner_d` 都有，用 `normalize`；否则按 `iD = dn`、`oD = iD + 2t` 兜底。
3. 结果写入 `Pipe`：
   - `dn`、`mat`、`content` 保留旧值；
   - `od`、`inner_d`、`t`、`direct` 写匹配值；
   - `cat` 优先用模板的 `cat`，否则留空（2.0 计算时按 `mat` 折算）。

### 4.4 从模板取 a / C1 / C2

模板 `ElementTemplate.atlas` 是 `{"con90": (a,c1,c2), ...}`：

- 用 `template.atlas_at(con_found, found_angle)` 取值；
- 该值可能是 `None`（图集无该组合），此时不写参数，让 2.0 引擎按图集兜底，并记 warning。

写入方式（已确认：与 2.0 构件库插入行为一致）：

1. 为直埋构件生成 8 行 `ElementAtlasCandidate`：
   - `con_found` × `angle`（90/120/150/180）；
   - `t` 取模板 `pipe.thickness` 同键值；
   - `a/c1/c2` 取模板 `atlas` 同键值；
   - 模板该组合无数据时写 `None`（与 2.0 资产一致）。
2. 调用 `services.atlas_match.match_atlas_candidates(element, commit=False)`：
   - 按新 PF 的 `con_found + found_angle` 选组；
   - 自动写 `工作面加宽/垫层厚/基础厚/管道壁厚` 参数行；
   - 同步首根管 `t`。
3. 模板 `atlas` 为空或全 `None` 时，候选也全 `None`；`match_atlas_candidates` 会把参数行清空，计算回退 2.0 图集，并记 warning。

不采用“直接写三行参数、不建候选”的方案，避免丢失 8 组候选和 2.0 的自动匹配能力。

### 4.5 非直埋类别

- **包封埋管 / 箱涵 / 管廊**：
  - 2.0 构件库插入时本来就不生成候选，计算固定 `a=100, C1=100, C2=0`；
  - 迁移保持同样行为：**不生成候选、不写 a/C1/C2 参数行**，参数行留空 = 引擎按 2.0 约定取固定值；
  - 管道 oD/iD/t 仍按模板匹配（包封埋管有管道行）。
- **顶管 / 牵引管**：
  - 只匹配管道 oD/iD/t；
  - 不写 a/C1/C2（2.0 不算沟槽）。
- **构筑物**：
  - 没有管道，跳过。

### 4.6 多根管

- 每条管道独立按 `mat + dn` 匹配；
- 直埋的 a/C1/C2 取首根管的模板；
- 包封等多根管的 a/C1/C2 固定，不随管变。

### 4.7 匹配失败

- 不写 `od/inner_d/t`，保持 `None`；
- 2.0 计算时按图集/DN 兜底；
- 迁移报告列出：旧材质、旧 DN、构件类别、失败原因（无材质/无 DN/无模板/模板无壁厚）。

---

## 5. PE × PF 新地基原则生成

### 5.1 输入

- `legacy.enclosures`：旧 PE 列表（名称、ConFound、FoundAngle、Cush、works 等）；
- `legacy.foundations`：旧 PF 列表（名称、换填层、Foundation 构件）。

### 5.2 生成范围（已确认）

**所有 PE × PF 组合全部生成**：

- 旧 PF 外层、旧 PE 内层；
- 例：3 PE × 2 PF = 6 条新 PF；10 × 10 = 100 条；
- 未使用的组合也生成，便于“按原 PE/PF 任意匹配”和后续审计；
- 报告统计生成数量、未使用数量。

### 5.3 新 PF 名称（已确认）

采用名称式：

```text
{旧PF名}·{旧PE名}
```

例：

- `没有地基处理·放坡开挖`
- `PF1·PE2`

规则：

- 旧 PF/PE 名称为空时，用默认名（`未命名地基原则` / `未命名围护原则`）；
- 名称重复时追加 `#2`、`#3`；
- 超过 `PcpFoundation.name` 长度（200）时截断并追加 `#n`；
- 名称中已有 `·` 不特殊处理；
- 名称只用于显示和引用，**不参与算量**；引用仍按名字，改名需同步 `pf_name`（2.0 原则改名逻辑已有类似处理）。

### 5.4 新 PF 内容

对每个 `(old_pf, old_pe)`：

1. 新建 `PcpFoundation`：
   - `name` = 新 PF 名；
   - `con_found` = `old_pe.con_found`；
   - `found_angle` = `old_pe.found_angle`；
   - `order_no` = 旧 PF 顺序 × PE 数 + 旧 PE 顺序（或相反，需固定）。
2. 克隆旧 PF 的换填层：
   - `FoundationReplacement(name, h)` 逐条复制；
3. 克隆旧 PF 的特殊地基构件：
   - `Component(name, formula, params)` 逐条复制；
4. 垫层：
   - `FoundationCushion(name=old_pe.cushion.name, h=old_pe.cushion.h)`；
   - 1.0 的 Cush 在 PE 上，所以每个新 PF 用对应 PE 的 Cush。
5. 如果旧 PF 自己带 `ConFound/FoundAngle/Cush`（新版格式）：
   - **已确认以 PE 为准**（1.0 语义）；
   - 旧 PF 的值与 PE 不同时，写 warning，不覆盖 PE 值；
   - 旧 PF 的换填层/特殊地基仍按旧 PF 克隆。

### 5.5 映射表

建立：

```python
pf_map[(old_pf_name, old_pe_name)] = new_pf_name
```

构件拆分子条目时：

- 旧 PE = `pe_name`，旧 PF = `pf_name`；
- 新 `pf_name = pf_map[(old_pf_name, old_pe_name)]`；
- 如果旧 PF/PE 名无效，按 §5.6 回退。

### 5.6 引用无效/缺失

- 旧 PE 名不在 PE 列表：跳过该引用，记 warning；
- 旧 PF 名不在 PF 列表：跳过该引用，记 warning；
- 一条有效引用都不剩：**回退到第一条 PE + 第一条 PF 的组合**（即 `第一条PF名·第一条PE名`），记 warning；
- 旧构件没有 PE/PF：同样回退第一条 PE/PF 组合，记 warning；
- 如果工程里连一条 PE 或 PF 都没有：`pe_name/pf_name` 留空，记 warning（无法凭空造原则；2.0 计算会失败，但数据不伪造）。

---

## 6. 多原则拆分

### 6.1 解析原始引用

对每条旧构件：

- `pe_refs`：`PEname` 列表 `[(name, ratio), ...]`；
- `pf_refs`：`PFname` 列表 `[(name, ratio), ...]`；
- 如果没有 `PEname`/`PFname`，用 `showPEname`/`showPFname` 作为单引用，比例 1；
- `showPEname == "多围护原则"` 等占位文字不算原则名；
- 无效引用按 §5.6 处理。

### 6.2 笛卡尔积

按 1.0 `mscGroove.Cal` 的顺序：**PE 外层、PF 内层**。

```python
pairs = [
    (pe_name, pe_ratio, pf_name, pf_ratio)
    for pe_name, pe_ratio in pe_refs
    for pf_name, pf_ratio in pf_refs
]
```

- 2 PE × 2 PF = 4 条；
- 2 PE × 3 PF = 6 条；
- 单 PE × 单 PF = 1 条（不拆）。

### 6.3 子条目字段

对每个 pair：

| 字段 | 值 |
|---|---|
| `pe_name` | `pe_name` |
| `pf_name` | `pf_map[(pf_name, pe_name)]` |
| `pp_name` / `pw_name` | `pe_name`（与现在一致） |
| `name` | 见 §6.4 |
| `amount` | 见 §6.5 |
| `depth` / `params` / `pipes` / `quantities` | 原样复制 |
| `source` | 旧 `Source` 原文 + `｜` + `legacy_meta` 摘要（见 §2.2）；旧原文同时存 `legacy_meta["source"]` |
| `legacy_meta` | 原构件完整 refs/比例 + `assigned_pe/assigned_pf/assigned_ratio` + 旧 Source |
| `order_no` | 原构件顺序 + pair 顺序 |

### 6.4 名称

- 单 pair：**保留原名，不追加后缀**（比例≠1 也一样；比例写进 `legacy_meta` 和报告）；
- 多 pair：`原名·{新PF名} {百分比}%`；
  - 新 PF 名本身是 `旧PF名·旧PE名`，已经能看出两条原则来源，不再重复拼 `PE名×PF名`；
  - 百分比 = `pe_ratio * pf_ratio * 100`，用 `g` 格式去掉多余 0；
  - 例：`雨水管·没有地基处理·钢板桩 40%`；
  - 原名为空时，去掉前导 `·`，直接用 `{新PF名} {百分比}%`。

### 6.5 数量

- 单 pair 且比例 = 1：保留原数量字符串，不包算式；
- 单 pair 比例 ≠ 1：`(原数量)*比例`；
- 多 pair：`(原数量)*pe_ratio*pf_ratio`，比例为 1 的因子省略；
- 原数量为空：按 `"0"`；
- 原数量本身是算式：保留原文，外层加括号；
- 比例为 0：数量写 `"0"`（原始比例写进 `legacy_meta`），仍生成子条目。

### 6.6 比例边界（已确认）

- 比例 = 0：**生成 0 数量子条目**，保留引用关系，报告注明；
- 比例合计 ≠ 1：**按原比例计算**，不做归一化；总量随比例缩放，报告注明；
- 单引用比例 ≠ 1：数量 × 比例，名称不变，`legacy_meta` 记录比例；
- 负比例：保留算式，报告异常（不阻止迁移）。

### 6.7 支撑

- 拆分后每条子构件用自己的 `pe_name`；
- 2.0 `works_quantities` 自然按该 PE 的做法计算支撑；
- 不再使用 `mainPEname`；
- 报告注明“支撑口径已按决策 4 变更”。

### 6.8 地基

- 每条子构件用 `pf_map[(old_pf, old_pe)]`；
- 该新 PF 的 `ConFound/FoundAngle/Cush` 来自该子构件的 PE；
- 因此 2.0 的管道基础/垫层/换填按“该子构件的 PE + 原 PF 的换填/特殊地基”计算；
- 与 1.0 用 `mainPE` 算基础的口径可能不同，报告注明。

### 6.9 不拆的类别：构筑物 / 顶管 / 牵引管

- 1.0 里这三类的工程量**不随 PE/PF 比例变化**：
  - 构筑物只按自己的工程量行 × 数量；
  - 顶管 / 牵引管只按管材 × 数量。
- 如果按 PE×PF 拆，会重复计算工程量，所以**不拆**：
  - 仍生成一条构件；
  - PE 取 `mainPEname`（无效取第一条 PE），PF 取第一条 PF；
  - 新 PF 按 `PF名·PE名` 映射；
  - 原始 `PEname/PFname` 的全部引用和比例写入 `legacy_meta`，保证数据不丢。
- 报告注明“未拆，原因：1.0 计算不使用多原则比例”。

---

## 7. 构筑物工程量键（<3 段）

### 7.1 1.0 行为回顾

- `mcE7.getDQ`：所有不以 `-` 开头的 `Param` 键都是工程量，键原文即工程量 key；
- `FormSum.FlashItem` 按 `|` 切分显示：
  - 3 段：分类/名称/单位；
  - 2 段：分类空，名称=第 1 段，单位=第 2 段；
  - 1 段：分类空，名称=第 1 段，单位空；
  - >3 段：1.0 不处理，显示空；
- 计价：原始 key 精确查价；
- 汇总分组：`tStr[0]`。

### 7.2 2.0 方案

1. **判定规则改为 1.0 规则**：
   - `Param` 键以 `-` 开头 → 参数行（名称/单位/井筒/井高等）；
   - 其他键 → 工程量行，**不再要求包含 `|`**。
2. **保留原始键**：
   - `ElementQuantity.raw_key = 原始键`；
   - `value` 原文保留。
3. **解析显示字段**：
   - 3 段：`category=段1, item=段2, unit=段3`；
   - 2 段：`category="", item=段1, unit=段2`；
   - 1 段：`category="", item=段1, unit=""`；
   - >3 段：`category=段1, item=段2, unit=段3..n`，raw_key 保留，记 warning；
   - 空键：跳过，记 warning。
4. **计算输出**：
   - `compute_structure` 优先用 `raw_key` 作为工程量 key；
   - `raw_key` 为空时才用 `category|item|unit` 拼。
5. **计价**：
   - `resolve_price` 先用 `raw_key` 精确匹配（保留 1.0 旧单价）；
   - 旧单价键同样按 `Dn → DN` 归一；
   - 精确不命中时，再按 2.0 原生 `(category, item)` scope 回落。
6. **显示**（已确认按 1.0）：
   - 工程量明细/汇总按 1.0 规则显示：2 段分类空、名称/单位按上表；
   - 原始 key 可放在 tooltip 或“旧版键”列；
   - 编辑行为与 2.0 原生插入行一致：**可编辑**；
     - 只改“值”：保留 `raw_key`；
     - 改分类/名称/单位任一列：清空 `raw_key`，按编辑后的三列走 2.0 原生 key；
     - 这样既不阻止用户修改，也不会在未修改时悄悄改掉旧 key。
7. **汇总分组**（已确认按 2.0）：
   - 使用 2.0 原生分组口径（`category` / `item` / `unit`），不按 1.0 的 `raw_key.split("|")[0]`；
   - 因此 2 段键在汇总里分类为空，和 1.0 的“分类空”显示一致；分组落在空分类下；
   - 3 段键与现在一致。

### 7.3 会有什么问题

- **模型字段**：`ElementQuantity` 现在只有 `category/item/unit`，直接塞 2 段会多出空段或前导/尾随 `|`；必须加 `raw_key`，否则 key 一定变。
- **计算**：`compute_structure` 现在 `if not item and not unit: continue`，1 段键会被跳过；必须改成按 `raw_key` 判断。
- **UI**：详情面板的工程量表默认三列；1/2 段行需要空白分类/单位显示规则。编辑策略见 §7.2 第 6 条：改值保留 raw_key，改分类/名称/单位清空 raw_key。
- **计价**：1.0 精确查原始 key；2.0 的 `price_scope` 按 `category/item` 回落，2 段键会变成 `("", 第1段)`，可能匹配到意外单价。已确认先用 `raw_key` 精确匹配，不命中再走 2.0 scope。
- **导出**：Excel 导出按三列写；1/2 段行会出现空分类/空单位，和 1.0 的显示一致；导出时按 raw_key 计价，避免旧价丢失。
- **数据版本**：新增 `raw_key`/`legacy_meta` 是可选字段，`STN_FILE_VERSION` **保持 2**，不升版本；2.0 未正式发布，无旧 2.0 文件兼容负担。

---

## 8. 解析与迁移报告

### 8.1 现状问题

- `parse_legacy` 内部建 `MigrationReport`，但只返回 `LegacyProject`，skipped 丢失；
- `_parse_segment` 没有逐元素容错，一个元素坏会丢整个标段；
- `build_legacy_database` 新建报告，看不到解析阶段的 skipped。

### 8.2 改造

1. `parse_legacy(path, report=None) -> tuple[LegacyProject, MigrationReport]`：
   - 或接受外部 report，解析阶段直接写入；
   - 更新 `element_library._from_legacy` 等调用方。
2. `_parse_segment`：
   - 逐 `mcElement` try/except；
   - 失败的元素记 `skipped`（含标段/单位/元素序号、名称、异常）；
   - 继续解析同标段其他元素。
3. `_parse_enclosure` / `_parse_foundation`：
   - 保持单节点跳过；
   - 把原因写入 report，不再丢失。
4. `build_legacy_database`：
   - 合并解析报告与迁移报告；
   - 计数、警告、跳过、拆分明细、PF 映射、管道匹配结果统一输出。

### 8.3 报告内容

建议分节：

1. 源文件/版本/目标路径；
2. 计数：标段/单位/构件/管道/PE/PF/单价；
3. **PE × PF 映射表**：旧 PE、旧 PF、新 PF、ConFound/FoundAngle/Cush；
4. **构件拆分明细**：原名、原 PE/PF 及比例、子条目名称/数量/新 PF；
5. **管道匹配明细**：旧材质/DN、匹配到的模板、oD/iD/t/a/C1/C2、兜底级别；
6. **构筑物键处理**：原始 key、解析出的分类/名称/单位、警告；
7. **单价键重写**：旧 key → 新 key；
8. **补全项**：哪些参数/宽度表/做法/止水是 2.0 补的；
9. **跳过/失败**：节点、原因；
10. 有意差异说明：支撑按 PE、基础按 PE、多原则拆条等。

UI：

- `views/dialogs/legacy_import_dialog.py` 增加可折叠分节；
- 报告可复制；
- 有 skipped 时用警告色，不能只显示“迁移成功”。

---

## 9. 单价键 Dn → DN

### 9.1 规则

只重写“生成的管材工程量键”里的直径标记：

- 旧：`管材|Ⅱ级混凝土管 Dn400|m`
- 新：`管材|Ⅱ级混凝土管 DN400|m`

建议正则：

```python
re.sub(r"(?<=\s)Dn(?=\d)", "DN", key)
```

覆盖：

- `管材|... Dn...|m`
- `顶管|... Dn...|m`
- `拖拉管|... Dn...|m`

不覆盖（已确认）：

- 用户材料名/参数值/构件名里的 `Dn`（只改生成的管材键和单价键，避免误改用户文本）；
- 已经是 `DN` 的键；
- 非管材键（开挖/回填/垫层等）不含 `Dn`。

### 9.2 其他键

- 1.0 其他工程量键（`开挖|Ⅲ类土|m3` 等）与 2.0 一致，不改；
- 构筑物键按 §7 原样保留；
- 如果旧单价键本身是 2 段/1 段，按原样保留并走 raw_key 精确匹配。

### 9.3 已确认

迁移时直接重写 Price 键，`Dn → DN`；不在 `resolve_price` 查询时做兼容归一。这样数据本身统一，后续导出/汇总/重开都不需要额外兼容。

---

## 10. 决策记录与剩余问题

### 10.1 已确认（2026-11-18）

| # | 问题 | 决定 |
|---|---|---|
| 1 | 新 PF 命名 | `旧PF名·旧PE名` 名称式 |
| 2 | 生成范围 | 所有 PE×PF 全生成 |
| 3 | 单引用比例≠1 | 数量 × 比例 |
| 4 | 0 比例 / 合计≠1 | 0 比例生成 0 数量子条目；合计≠1 按原比例，不归一 |
| 5 | legacy_meta | 增加；保存 show/main/PEname/PFname 比例/旧版本号 |
| 6 | 构件库匹配兜底 | 精确 材质+DN+类别；不命中按 1.0 TrimDn（1400→1350、1600→1650、2700→2800、>2800→3000）；多个命中**只看 DN**，DN 大者优先 |
| 7 | a/C1/C2 | 生成 8 组 `ElementAtlasCandidate`，再 `match_atlas_candidates` |
| 8 | 构筑物 1/2 段 | 显示按 1.0；编辑按 2.0 原生；汇总按 2.0 |
| 9 | `Dn → DN` 范围 | 只改生成的管材键/单价键 |
| 10 | 旧 PF 自带基础参数 | 以 PE 为准 |
| 11 | 无 PE/PF 引用 | 回退第一条 PE/PF 组合 |
| 12 | 旧单价键 | 迁移时重写 `Dn → DN` |
| 13 | “多个模板命中优先大尺寸” | **只看 DN**，不比 od/t |
| 14 | 单引用比例≠1 的名称 | 保持原名 |
| 15 | `legacy_meta` 可见性 | 写到主表单来源列（摘要） |
| 16 | PF 重名后缀 | `#2` 可以 |
| 17 | 构筑物 1/2 段编辑 | 可以；改分类/名称/单位清空 `raw_key` |
| 18 | 构筑物/顶管/牵引管不拆 | 同意 |
| 19 | 来源列内容 | 摘要（完整 JSON 进只读面板） |
| 20 | `STN_FILE_VERSION` | **不升，保持 2**；2.0 未正式发布，无旧 2.0 兼容负担 |
| 21 | `legacy_meta` 完整内容 | 详情面板新增只读“来源信息”页 |

### 10.2 由决策推导的默认（无需再确认，除非有异议）

1. **PF 名称冲突**：重名追加 `#2/#3`；空名用默认名；超长截断。
2. **单引用比例≠1 的名称**：名称不变，比例写入 `legacy_meta`/报告；不追加后缀。
3. **多个模板命中**：只看 DN；DN 相同按“材质完全相等 → 级别一致 → 类别相同 → 库顺序”。
4. **构筑物编辑**：只改“值”保留 `raw_key`；改分类/名称/单位清空 `raw_key`，按 2.0 原生三列走。
5. **构筑物计价**：`raw_key` 精确优先；不命中再走 2.0 scope。
6. **无 PE/PF 且工程里一条原则都没有**：留空 + warning（无法回退）。
7. **负比例**：保留算式 + warning，不阻止迁移。
8. **legacy_meta 展示**：`Element.source` 写紧凑摘要；完整 JSON 存 `Element.legacy_meta`；详情面板只读“来源信息”页展示全量；2.0 打开/计算不特殊处理。
9. **构筑物/顶管/牵引管不拆**：只保留一条，原 refs 写 `legacy_meta`。
10. **迁移模块独立**：2.0 正常路径不 import；迁移文件按正常 2.0 文件打开。
11. **版本号**：`STN_FILE_VERSION` 保持 2，不升版本。

### 10.3 无阻塞问题（按以下默认实现）

1. **来源列**：显示紧凑摘要，例如 `1.0迁移｜PE:放坡开挖60%,钢板桩40%｜PF:没有地基处理100%｜主PE:钢板桩`；完整 JSON 不进单元格。
2. **版本号**：`STN_FILE_VERSION` **保持 2**，不升版本；2.0 未正式发布，无旧 2.0 文件兼容负担。
3. **只读面板**：详情面板新增“来源信息”页，`legacy_meta` 非空时显示；格式化 JSON、只读、可复制；正常 2.0 文件隐藏该页。

如无异议，按此实现；有异议再调整。

---

## 11. 开发阶段与工作量估算

### 阶段 0：准备（1 天）

- 固化本计划与决策记录；
- 建 `legacy_migration` 包骨架与依赖规则；
- 写“正常 2.0 路径不 import 迁移包”的静态/启动测试；
- 准备测试样例：
  - 单 PE/PF 基础样例（现有）；
  - 多 PE × 多 PF 样例；
  - 多原则比例样例；
  - 1/2/3/>3 段构筑物键样例；
  - 非标 DN（1400/1600/2700）样例；
  - Z 支撑样例；
  - 旧单价 `Dn` 样例。

### 阶段 1：迁移包与解析报告（1.5 天）

- 把解析/写库逻辑迁入 `legacy_migration` 包；
- 去掉 `project_io` / `element_library` 顶层 import，改延迟 import；
- `parse_legacy` 返回报告；
- 逐元素容错；
- 报告结构；
- `BasicInfo.legacy_meta` / `Element.legacy_meta` 模型与编解码；
- 测试：坏元素不丢整标段、报告有 skipped、legacy_meta 往返、正常 2.0 路径不 import 迁移包。

### 阶段 2：PF 交叉生成（1.5 天）

- 新 PF 命名/映射；
- 克隆换填/特殊地基；
- PE 的 ConFound/FoundAngle/Cush 写入；
- 测试：3 PE × 2 PF 生成 6 条；元素 PE1+PF2 → `PF2·PE1`。

### 阶段 3：管道库匹配（2 天）

- 匹配服务（材质/DN/类别/兜底）；
- oD/iD/t 归一化；
- 8 组 `ElementAtlasCandidate` + `match_atlas_candidates`；
- 非直埋处理；
- 测试：id_t/od_t/od_id、非标 DN、无匹配、多管。

### 阶段 4：多原则拆分（1.5 天）

- 笛卡尔积；
- 数量/名称/顺序；
- 单引用比例、0 比例、合计≠1；
- 支撑按 PE；
- 构筑物/顶管/牵引管不拆，refs 写入 `legacy_meta`；
- 测试：2×2=4、2×3=6、比例合计、不拆类别。

### 阶段 5：构筑物键与 raw_key（2 天）

- `ElementQuantity.raw_key` 模型/编解码；
- 1.0 解析规则；
- 计算/汇总/导出/UI 适配（显示按 1.0，编辑按 2.0，汇总按 2.0）；
- 测试：1/2/3/>3 段、价格、编辑清空 raw_key。

### 阶段 6：单价键（0.5 天）

- `Dn → DN` 重写；
- 测试：旧管材单价迁移后生效。

### 阶段 7：报告 UI、只读面板与文档（1.5 天）

- 导入向导报告分节；
- 详情面板“来源信息”只读页（legacy_meta 非空时显示，格式化 JSON + 复制）；
- 来源列摘要；
- README/CHANGELOG；
- 迁移说明。

### 阶段 8：回归（1.5 天）

- 全量迁移样例；
- 保存/重开；
- 字段级快照对比；
- 性能（大工程 1000+ 构件）。

总估算：约 **14 人天**（含独立迁移包、`legacy_meta`、raw_key、只读面板、隔离测试）。

---

## 12. 验收标准

1. **原则**
   - 1.0 每个 PE 的 `ConFound/FoundAngle/Cush` 都能在某个新 PF 中找到；
   - 1.0 每个 PF 的换填层/特殊地基都在每个新 PF 中复制；
   - 构件按原 PE/PF 引用到正确的新 PF；
   - 不再出现“所有 PF 套第一条 PE”。

2. **管道**
   - 1.0 每个 `Dn` 都变成 2.0 的 `DN`；
   - 能匹配的管道都有 `od/iD/t`，且与构件库模板一致；
   - 匹配不到的有 warning，不伪造 `od/iD/t`；
   - 旧单价键 `Dn → DN` 后能命中。

3. **拆分**
   - 多原则条目按 PE×PF 拆成 N 条；
   - 数量 = 原数量 × 各比例；
   - 每条只引用一条 PE、一条 PF；
   - 支撑按各自 PE 计算（有意差异已注明）。

4. **构筑物**
   - 1/2/3/>3 段键都能计入工程量；
   - 原始 key 保留，价格按 `raw_key` 精确优先；汇总按 2.0 原生口径；
   - 不再因两段键中断迁移。

5. **报告**
   - 坏节点/坏元素有 skipped 及原因；
   - 不再出现“0 标段、0 警告”的静默丢失；
   - 报告包含 PF 映射、拆分明细、管道匹配、补全项。

6. **数据完整性**
   - 迁移前后字段快照对比：1.0 有的原则/参数，2.0 要么有对应值，要么在报告里明确说明为什么没有；
   - 不允许“没有报告的自作主张”；
   - 来源列显示摘要；详情面板“来源信息”页可看完整 `legacy_meta`（只读、可复制）；
   - `STN_FILE_VERSION` 保持 2，不升版本。

7. **2.0 零影响（硬性）**
   - 现有 2.0 测试全部通过；新增可选字段导致的 JSON 形状断言差异需逐条确认，但算量/UI 行为断言不得改变；
   - 正常 2.0 工程保存/重开后，`raw_key` 为空、`legacy_meta` 为空、`source` 原样，算量/汇总/导出结果与改动前一致；
   - 2.0 启动、正常打开/保存/计算/汇总/导出路径不 import `legacy_migration`；
   - 迁移后的 `.stn` 由 `open_project` 正常打开，不出现“迁移文件”分支、不弹迁移提示；
   - `compute_structure` / `summary` / `unit_vm` 中没有 `if migrated` / `if legacy_meta` 分支，只有通用的可选字段处理。

---

## 13. 风险与回滚

- **风险 1：新 PF 数量爆炸**。已确认全生成；10 PE × 10 PF = 100 条 PF，报告需给出数量提示，界面/性能要能承受。
- **风险 2：模板匹配错误**。材质名相近但规格不同（如Ⅰ/Ⅱ级混凝土管）可能匹配错；匹配键要带类别/级别，报告要列出匹配到的模板。
- **风险 3：raw_key 改造面大**。涉及模型、编解码、计算、汇总、导出、UI；建议单独一个 PR，先加字段并保持旧行为，再切换。
- **风险 4：版本号**。已确认不升 `STN_FILE_VERSION`（2.0 未正式发布，无旧 2.0 文件兼容负担）；新增字段作为可选字段读写，缺省为空。
- **风险 5：迁移包被 2.0 正常路径意外 import**。用测试/静态检查守住：正常启动和正常打开路径的 import 图里不能出现 `legacy_migration`。
- **风险 6：迁移后的文件被 2.0 特殊对待**。代码评审检查：`open_project`、`compute_structure`、`summary`、`unit_vm` 不得出现迁移专用分支。
- **回滚**：迁移仍是单向、原文件备份；新字段可空，旧数据读取不受影响；出问题可回退到备份的 1.0 文件重新迁移。

---

## 14. 代码落点（供开发参考，不在本阶段修改）

| 模块 | 预计改动 |
|---|---|
| `src/app/services/legacy_migration/`（新建包） | 1.0 解析、PF 交叉、拆分、管道匹配、构筑物键、报告；原 `stn_migration.py` 逻辑迁入 |
| `src/app/services/stn_migration.py` | 保留薄兼容层（re-export）供旧测试/旧调用；2.0 正常路径不 import |
| `src/app/services/legacy_migration/matcher.py`（新建） | 1.0 管道 → 2.0 构件库模板匹配（只看 DN） |
| `src/app/services/element_library.py` | 提供按材质/DN 搜索模板的接口；把顶层 `from app.services.stn_migration import ...` 改成 `_from_legacy` 内延迟 import |
| `src/app/services/project_io.py` | 去掉顶层 `stn_migration` import；`open_project` 检测到 1.0 XML 后才延迟 import 迁移包；`.spcp` 导入同样延迟 |
| `src/app/views/dialogs/legacy_import_dialog.py` | 延迟 import 迁移包；报告分节 |
| `src/app/core/models/models.py` | `ElementQuantity.raw_key`；`BasicInfo.legacy_meta`；`Element.legacy_meta`；可选 `PcpFoundation.legacy_meta` |
| `src/app/services/stn_codec.py` | raw_key / legacy_meta 可选字段编解码；不升版本；不写迁移专用分支 |
| `src/app/core/calc/engine.py` | `compute_structure` 通用处理 raw_key（非迁移专用） |
| `src/app/services/summary.py` | raw_key 精确计价；分组保持 2.0 原生口径（非迁移专用） |
| `src/app/services/atlas_match.py` | 迁移时复用 `match_atlas_candidates`（commit=False） |
| `src/app/viewmodels/unit_vm.py` | 工程量行 raw_key 显示/编辑；来源列显示 `source` 摘要；提供 legacy_meta 读取 |
| `src/app/views/panels/unit_panel.py` | 详情面板新增“来源信息”只读页（legacy_meta 非空时显示，格式化 JSON + 复制） |
| `tests/test_stn_migration.py` | 新增字段级/拆分/PF/管道/构筑物/价格测试 |
| `tests/test_legacy_isolation.py`（新建） | 正常 2.0 启动/打开/计算路径不 import 迁移包；正常文件行为不变 |
| `docs/legacy_migration_plan.md` | 本计划 |

---

## 15. 附：1.0 管道扣减的 DN 口径（供实现参考）

1.0 把 `Dn` 当**内径/公称内径**：

- `mcE1.rtSizeB()/rtSizeH()`：`Dn / 1000.0`；
- `mcE1.cal_found()`：`outsideDn = At.oD > 0 ? At.oD : Dn + At.t * 2`；
- `mcE2.cal_pipes()`：`tR = (Dn / 2.0 + At.t) / 1000.0`，扣 `π * tR² * Content`；
- 基础弓形扣减：`Bow(outsideDn, angle)`。

因此 2.0 迁移必须：

- `dn = Dn`；
- `inner_d = Dn`（或留空，让 2.0 按 DN 兜底）；
- `od` 不直接写 `Dn`，应按构件库匹配或 `Dn + 2t`；
- `t` 按构件库匹配；
- 不能出现 `od = inner_d = Dn` 这种“外径=内径、壁厚=0”的写法。

---

*本计划为开发前梳理；12 项主决策 + 9 项补充决策已确认，§10.3 为无阻塞实现默认。确认后进入编码。*
