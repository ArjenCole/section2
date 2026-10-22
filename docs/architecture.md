# 架构说明

Section 2.0 是 PySide6 单窗体桌面应用，分层与 Quotor 一致：

```
views/  ──►  viewmodels/  ──►  services/  ──►  core/models/
（控件）      （状态与信号）      （业务逻辑）      （.stn2 数据）
                    ▲                              │
                    └──────── core/event_bus ──────┘
```

## 分层职责

| 层 | 职责 | 不做什么 |
|---|---|---|
| `views/` | 只画界面、把用户操作转成 VM 调用、渲染 VM 发来的数据 | 不碰数据库、不写业务规则 |
| `viewmodels/` | 持有当前选中状态，调用 services，用 Signal 广播结果 | 不引用 Qt 控件 |
| `services/` | 工程文件读写、计算引擎、图集、旧档迁移、AI（纯 Python，不依赖 Qt） | 不管界面 |
| `core/models/` | `.stn2` 表结构与连接生命周期 | 不含业务规则 |

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

## 工程文件

`.stn2` = 单个 SQLite 库，表结构以 `core/models/models.py` 为权威定义。
`core/models/base.py` 负责引擎/会话与 `meta` 表（`schema_version` / `app_version` / `created_at` / `updated_at`），
`services/project_io.py` 负责新建/打开/保存/另存/关闭、`.lock` 防双开、Backup 备份与结构版本校验。

结构变更时：改 `core/models/models.py` → `core/version.py` 的 `SCHEMA_VERSION` +1 →
在 `core/models/base.py` 的 `_MIGRATIONS` 里登记 `{旧版本号: 迁移函数}`。

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

新增工程量条目时照此办理：任何 `fmt(数值)` 拼进算式前先想一遍“这个数字是不是
别的输入算出来的”，是就用 `Dim` 运算或显式模板把过程写出来。
`tests/baselines/对拍工程.json` 冻结了算例的数值与算式，有意修改表达式后需
重新生成并复核 diff。

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
