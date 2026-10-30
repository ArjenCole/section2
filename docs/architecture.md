# 架构说明

Section 2.0 是 PySide6 单窗体桌面应用，分层与 Quotor 一致：

```
views/  ──►  viewmodels/  ──►  services/  ──►  core/models/
（控件）      （状态与信号）      （业务逻辑）      （工作库/文件数据）
                    ▲                              │
                    └──────── core/event_bus ──────┘
```

## 分层职责

| 层 | 职责 | 不做什么 |
|---|---|---|
| `views/` | 只画界面、把用户操作转成 VM 调用、渲染 VM 发来的数据 | 不碰数据库、不写业务规则 |
| `viewmodels/` | 持有当前选中状态，调用 services，用 Signal 广播结果 | 不引用 Qt 控件 |
| `services/` | 工程文件读写、计算引擎、图集、旧档迁移、AI（纯 Python，不依赖 Qt） | 不管界面 |
| `core/models/` | 临时工作库（SQLite）表结构与连接生命周期 | 不含业务规则 |

面板之间不互相持有引用：跨面板通知走 `core/event_bus.py` 的全局 Signal 总线
（`project_opened` / `tree_structure_changed` / `node_selected` / `unit_changed` / `status_message`）。
载荷是自定义对象时统一用 `Signal(object)`，避免 Shiboken 转换失败导致槽函数不触发。

## 数据流（改一条数据）

1. 界面控件（表格单元格 / 下拉框）发出信号；
2. `views/panels/*` 调用 viewmodel 方法；
3. viewmodel 调用 `viewmodels/unit_vm.py` 里的数据操作函数（`create_element` / `update_element` / …）；
4. 数据操作函数改 ORM 对象后调用 `services/project_io.commit()` —— 一次 commit 就是一次落盘（自动保存），
   本次打开工程的首次修改会顺手备份一份到 `Backup\`；
5. 数据操作函数广播 `EventBus.unit_changed`；
6. viewmodel 收到广播后**延后到事件循环**重新读库并 emit，界面刷新
   （延后是必要的：本槽可能是在表格 `itemChanged` 里被同步触发的，此时重建表格行会删掉正在处理的单元格）。

AI 工具（M8）走同一条 3~6，因此界面与 AI 改数据不会出现两套逻辑。

## 撤销 / 重做（快照式，brackets 同款）

`services/undo.py` 保存**整工程快照**而不是操作反演：`project_io.commit()` 是
所有修改的唯一漏斗，落盘的同时把 `stn_codec.dump_database()` 的 JSON 数据体
（剔除每次提交都变的 `saved_at`，保证"内容未变"可判定）连同界面状态压进撤销栈。
撤销 / 重做就是用快照重建临时工作库（`project_io.restore_snapshot`，期间
`_restoring_snapshot` 抑制重复记录），再按"提交即落盘"语义重写 `.stn` 文件。

原则（与 brackets2 的 `services/undo.py` 一致）：最多 25 步且快照总字节 ≤ 10 MB
双上限淘汰最旧；内容未变的重复提交只刷新界面状态、不占步数；新变更清除重做
分支；写入前先用当前界面状态刷新"变更前"快照（撤销回来时恢复操作时刻的
选中/焦点）；200ms 时间窗内的连续提交合并为一步（吸收"一次操作内部多次
commit"的中间态，如改一格候选参数触发重匹配）。

**界面状态的两段式捕获**（与 brackets2 的关键差异）：commit 发生在界面刷新
之前（`unit_changed` → QTimer 延后重装表格），所以 record() 里捕获的选中/焦点
是"变更前"的视图——撤销用它正好，**重做到栈顶却会指向已删除/已移位的行**。
因此主窗体订阅 `unit_changed` / `tree_structure_changed` / `principle_changed` /
`project_opened`，在广播落定（延后的表格重装执行完）后经
`UndoStack.patch_top_ui` 回填栈顶快照的界面状态——每个快照最终携带的都是
用户当时实际看到的视图，撤销与重做两个方向恢复的选中一致。

界面状态的携带与恢复按**位置**而不是 id（恢复会重建工作库，id 全变，只有
行序稳定）：树选中 = `TreePanel.selection_path()` 的（标段序号, 单位工程序号），
工作台 = `UnitPanel.ui_state()` 的主表格焦点/滚动与页签。主窗体经
`undo.set_ui_provider` / `undo.set_listener` 注入捕获回调与按钮刷新
（弱引用持有，避免钉住窗体，与 `connect_weak` 同理）。重建后的库按位置重新
编号构件 id，`UnitPanel.mark_ids_stale()` 让重载期间不再按旧 id 恢复选中
（按 id 恢复会撞到别的构件或回落第 0 行——重做选中错乱的第二个病根）。

**每一步只选中该步修改的条目（数据对比驱动）**：撤销 / 重做恢复选中时，
把相邻两份快照的构件清单做对比（`undo._diff_focus`），定位该步新增 / 改值 /
删除的条目位置——撤销与重做都只落在这一条上（删除方向没有该行，收敛到
原位置的相邻行）。快照携带的视图选中只作兜底：构件清单无差异（原则 / 单价 /
工程结构变化）或多个单位工程同时变化（原则保存触发的批量重匹配）时退回
视图位置。之所以不直接信视图：提交会用"当前视图"刷新"变更前"快照
（brackets2 语义），操作之间一旦浏览过别的行，视图选中就与步骤脱节，
重做会恢复出错误的条目。新增构件（按钮 / 构件库插入 / AI 共用
`create_element`）提交后广播 `EventBus.element_focused`，面板选中新行，
保证插入路径的视图同样跟随每一步。

**恢复选中必须用显式选择命令**（`UnitPanel._select_row`，
`ClearAndSelect | Rows`）：撤销 / 重做在 Ctrl+Z / Ctrl+Y 按键处理过程中同步
执行，Ctrl 修饰键还按着，`QAbstractItemView::selectionCommand` 会把
`setCurrentCell` 推断成"追加选择"——重做的每一步都把新行加进选区，最终
整表被持续选中（表格增长方向累积、收缩方向因旧行截断而不可见）。
显式命令不受修饰键影响。

注意：数据操作里"改数据 + 自动重匹配 + 落盘"应当**一次 commit 完成**
（参见 `unit_vm.create_pipe` / `delete_pipe` / `update_atlas_candidate`），
多次 commit 会产生中间态快照——时间窗合并是兜底，不是替代。

## 工程文件

`.stn` = **1.0 风格 XML 头 + CDATA 包裹的 JSON 数据体**（单文本文件）：

* XML 头沿用 1.0 格式（`Assembly/Version` + `mcBasicInfo`），唯一目的是让旧 1.0 软件
  误打开 2.0 文件时能读出高版本号弹提醒，而不是崩溃；1.0 不认识的 `Section2`
  元素会被它忽略；
* JSON 数据体是 2.0 的正式数据，层级结构（工程 → 标段 → 单位工程 → 构件 → 明细，
  原则独立成节），不含库里的 `id` / 外键 / `order_no`，顺序由数组次序表达；
  结构版本记录在 JSON 的 `file_version`（`core/version.py` 的 `STN_FILE_VERSION`）。

信封读写：`services/stn_format.py`；JSON ↔ 数据库编解码：`services/stn_codec.py`。
运行时数据载体是**临时目录里的 SQLite 工作库**（`core/models/base.py` 的
`create_working_database`）：打开工程时由 JSON 重建、保存时整体写出为 `.stn`、
关闭即删除。`meta` 表（`schema_version` / `app_version` / `created_at` / `updated_at`）
只作库内诊断记录；`services/project_io.py` 负责新建/打开/保存/另存/关闭、
`.lock` 防双开与 Backup 备份。

JSON 数据结构变更时：改 `services/stn_codec.py`（与涉及的模型）→
`core/version.py` 的 `STN_FILE_VERSION` +1。2.0 未发布，不做旧文件迁移：
`file_version` 与代码不一致即拒绝打开（高版本提示升级程序，低版本出自内部预览版）。

打开 1.0 旧版文件走自动转译（brackets 同款，`services/stn_migration.py` +
`project_io.open_legacy_project`）：识别（`stn_format.looks_like_legacy_file`）→
转译进临时工作库（工程处于“尚未保存”的临时状态）→ 原文件备份到软件数据目录
`migration_backup` → 界面经 `project_io.last_migration_notice()` 弹提示。
导入向导（`migrate`）按所选路径写出新文件，两者共用 `build_legacy_database`。

## 计算表达式：不做预运算

每个工程量除数值外还输出一条“数值代入”的算式（表格表达式列 / 详情弹窗），
供人工复核。规则是**算式里不出现预先算好的派生数字**：

- 派生量以 `core/calc/tracer.py` 的 `Dim`（数值 `v` + 算式 `e`）参与计算，
  加减乘除都在 `Dim` 上做，算式按运算逐级拼出来。槽底宽这类量在算式里保留
  完整推导，例如
  `(2*(600/1000+(65*2+130*2+500*2)/1000)+2*2.995*1)*2.995/2`
  （槽底宽 = 管径/1000 + 2*(壁厚+工作面加宽+工作面)/1000）；
- 算式按 **Excel 语法** 输出（`tracer.prettify`）：乘 `*`、除 `/`、乘方 `^`、
  函数名大写（`CEILING(x,1)` / `SIN` / `ROUND` / `ROUNDUP` / `SQRT` / `ABS` /
  `POWER`）、常量 `PI()`，用户复制进 Excel 即可当公式用；`evaluator` 的归一化
  保证这些写法自己也能求值，且 `ROUND` 与 Excel 一样逢 5 远离零；
- `CEILING(x,1)` 求值时会先把商收敛到 9 位小数再取整（`evaluator.ceil_ratio`），
  避免 `4.2/1.4 = 3.0000000000000004` 这类二进制浮点噪声让井点座数多算一座。
  收敛**只在求值实现里**，算式文本仍是标准 `CEILING(x,1)`，不带辅助函数；
- 只有**直接录入或查表的原始数据**（管径、图集 t/a/C1/C2、面宽表值、换填层厚
  等原则表值）和软件常数（0.5、π 系数）才是单个数字；毫米→米写成 `值/1000`；
- 用户在埋深 / 数量 / 构件参数 / 管材含量列写的算式按原文进表达式
  （`raw_dim`）；数值与算式同源，`Dim.e` 重算必须等于 `Dim.v`；
- 图集参数的算式伴随见 `core/calc/measures.py`（`AtlasDims`）：覆盖值取参数行
  原文，查表值取表值，外径按 `管径+2*壁厚` 写全推导；
- **括号只在语法必需处出现**，由 `tracer.wrap` 按运算优先级判断：顶层加减进
  乘除上下文才加括号，顶层只有乘除的算式（`a/b*c` 与 `a*(b/c)*c` 等价）不加；
  除数位置与乘方底数位置用 `wrap(..., tight=True)`。往公式里代入变量时
  （`engine.pre_sub` / `value_exp`）按占位符在公式里的位置决定括号（`_embed`）：
  原子表达式（`2`、`SIN(1.2)`）哪里都不括，乘除式只在除数 / 乘方位置括，
  顶层加减一律括（保守但不会算错）。不要手工在模板里塞括号。

- **中间步骤**（`Quantity.steps()`）＝逐项一行「说明 + 该步算式」：说明（分层、
  扣减、公式类别）挂在项（`Term.note`）上，由项本身派生，所以**各步算式按顺序
  拼接恒等于完整算式**——展示层（表格 tooltip / 详情弹窗）不再另拼字符串。
  数值为 0 的项不进算式，其说明一并丢弃；多选构件的合并行按构件分组列出。

### 展示层：主算式 + 中间量

`Quantity.expression` 始终是上面那条完整数值算式（复制 Excel、逐项复核用）。
`Quantity.presentation()` 另给一份展示结构：

* `main` / `formula`：把重复或较长的派生片段提成符号后的主算式，例如
  `V=(2*B+2*H*1)*H/2*100`；多分项工程量使用 `V=V1+V2-V3`，每个分项一行的
  说明与算式；
* `definitions`：中间量定义表，每行含符号、中文含义、**仍由原始参数组成的
  代入式**、计算结果与来源。`value` 只用于核对列，绝不代回主算式或其它定义；
* `full`：完整数值算式，默认只读展示，不参与符号化简。

派生量的语义名称由 `Dim.tags`（`NamedValue(expr, label, source)`）随
`Dim` 运算传递，`tracer` 用语法树 canonical key 对齐片段；因此槽底宽、计算深度、
外径、弓形面积、箱涵板厚等能显示为中文含义。提取规则只依赖“语义标记 / 确有重复”，
不按数值相等合并；只出现一次的普通片段不会被提成 `X1`。`X*X` 展示为 `X^2`，
其余不做算术折叠，避免把原始参数预先算成一个数字。多构件合并行按构件编号分组，
各自的定义与完整式互不串名。

**表格首屏不生成展示层**：每次点击构件、编辑单元格都会重算并重填工程量表；
`UnitPanel` 此时只写 `Quantity.expression_outline`（单分项原式或多分项说明摘要，
纯字符串拼接），不调用 `presentation()`。只有鼠标进入“计算表达式”格、双击打开
详情、或右键复制主式时才生成完整 presentation，并用 item data role 缓存；
生成过一次后同一格不再解析。导出 Excel / MCP 等确实需要主式的路径仍可直接读
`display_expression`。

新增工程量条目时照此办理：任何 `fmt(数值)` 拼进算式前先想一遍“这个数字是不是
别的输入算出来的”，是就用 `Dim` 运算或显式模板把过程写出来。
`tests/baselines/对拍工程.json` 冻结了算例的数值与算式，有意修改表达式后需
重新生成并复核 diff。

## 交互性能：点击 / 编辑不重算全单位工程

- **只算当前显示对象**：工程量面板填充走 `unit_vm.compute_elements(ids)`，
  只计算当前选中构件 / 合槽成员 / 多选行；`compute_unit()` 仍用于导出、汇总等
  需要整单位工程的路径。点击单构件从 O(单位工程构件数) 降为 O(1~选中数)。
- **原则名称 / 面宽表缓存**：`engine.lookup_principle` / `first_principle` /
  `_width_tables` 在同一次工程会话内缓存。`Session.before_flush` 发现原则、
  做法、构件公式或面宽表变化时打标记，`project_io.commit()` 成功后统一清缓存；
  普通埋深 / 数量编辑不清，连续点击可复用。
- **工作库 WAL**：临时 SQLite 工作库使用 `journal_mode=WAL` +
  `synchronous=NORMAL`，降低每次自动保存的 fsync；正式 `.stn` 文件仍完整写入。
- **展示懒加载**：工程量表刷新只写 `expression_outline`，悬停 / 双击才生成
  主算式和中间量说明（见上节）。
- **避免重复断面重建**：`_show_single_detail` 依赖 `load_detail` 同步触发的
  `_on_detail_loaded` 刷新断面，不再提前额外 build 一次。

这些优化不改变工程量数值、完整表达式和自动保存语义。

## 主题

`resources/qss/theme.py` 里是 `ThemeColors` 调色板（light/dark）与由调色板生成的整份 QSS，
`ThemeManager` 单例负责 `setStyleSheet` 并广播 `theme_changed`（自绘控件据此重取颜色）。
QSS 用 `string.Template` 的 `$token`，不用 f-string——样式表里大括号太多，转义易错。

## Windows 上的启动前置：系统 ICU 预加载

`src/app/__init__.py` 在导入 PySide6 之前会按绝对路径加载 `%SystemRoot%\System32\icuuc.dll`。

原因：Qt6Core.dll 静态依赖 `icuuc.dll`，而 PATH 里的第三方 ICU（Anaconda 的
`Library\bin` 很常见）只有带版本号后缀的符号，Qt 需要的 `ucnv_*` 等无版本号符号缺失，
于是 `import PySide6` 报 `DLL load failed ... 找不到指定的程序`(WinError 127)。
先加载系统 ICU 即可让 Qt 绑定到正确的那一份。

因此约定：**任何自己写的脚本/工具，先 `import app` 再 `import PySide6`**
（`src/app/main.py` 与 `tests/conftest.py` 都已照此处理）。
