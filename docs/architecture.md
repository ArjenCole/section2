# 架构说明

Section 2.0 是 PySide6 单窗体桌面应用，分层与 Quotor 一致：

```
views/  ──►  viewmodels/  ──►  services/  ──►  orm/
（控件）      （状态与信号）      （业务逻辑）      （.stn2 数据）
                    ▲                              │
                    └──────── core/event_bus ──────┘
```

## 分层职责

| 层 | 职责 | 不做什么 |
|---|---|---|
| `views/` | 只画界面、把用户操作转成 VM 调用、渲染 VM 发来的数据 | 不碰数据库、不写业务规则 |
| `viewmodels/` | 持有当前选中状态，调用 services，用 Signal 广播结果 | 不引用 Qt 控件 |
| `services/` | 工程文件读写、计算引擎、图集、导出、AI（纯 Python，不依赖 Qt） | 不管界面 |
| `orm/` | `.stn2` 表结构与连接生命周期 | 不含业务规则 |

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

`.stn2` = 单个 SQLite 库，表结构见 `orm/models.py`，约定见 开发计划.md §4。
`orm/base.py` 负责引擎/会话与 `meta` 表（`schema_version` / `app_version` / `created_at` / `updated_at`），
`services/project_io.py` 负责新建/打开/保存/另存/关闭、`.lock` 防双开、Backup 备份与结构版本校验。

结构变更时：改 `orm/models.py` → `core/version.py` 的 `SCHEMA_VERSION` +1 →
在 `orm/base.py` 的 `_MIGRATIONS` 里登记 `{旧版本号: 迁移函数}`。

## 主题

`resources/qss/theme.py` 里是 `ThemeColors` 调色板（light/dark）与由调色板生成的整份 QSS，
`ThemeManager` 单例负责 `setStyleSheet` 并广播 `theme_changed`（自绘控件据此重取颜色）。
QSS 用 `string.Template` 的 `$token`，不用 f-string——样式表里大括号太多，转义易错。

## Windows 上的启动前置：系统 ICU 预加载

`app/__init__.py` 在导入 PySide6 之前会按绝对路径加载 `%SystemRoot%\System32\icuuc.dll`。

原因：Qt6Core.dll 静态依赖 `icuuc.dll`，而 PATH 里的第三方 ICU（Anaconda 的
`Library\bin` 很常见）只有带版本号后缀的符号，Qt 需要的 `ucnv_*` 等无版本号符号缺失，
于是 `import PySide6` 报 `DLL load failed ... 找不到指定的程序`(WinError 127)。
先加载系统 ICU 即可让 Qt 绑定到正确的那一份。

因此约定：**任何自己写的脚本/工具，先 `import app` 再 `import PySide6`**
（`app/main.py` 与 `tests/conftest.py` 都已照此处理）。
