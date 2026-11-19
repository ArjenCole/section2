# Section 2.0 按钮清单（当前实现）

统计口径：PySide6 控件里**可点击触发动作**的按钮，包括 `QPushButton`、
`QToolButton`、工具栏 `QAction`（视觉上就是按钮）、`QRadioButton`（分段/单选）、
自绘按钮（`DragToggleBar`、窗口控制按钮）以及以“卡片/标签”形式承载点击的
`QLabel`。纯菜单项（`QMenu.addAction`）单独标注，不计入按钮总数；输入框、
下拉框、表格单元格不算按钮。

代码位置均相对仓库根目录。行号为当前工作区版本。

## 总览

| 区域 | 数量 | 说明 |
|---|---:|---|
| 主窗口标题栏 / 工具栏 | 18 | 3 个窗口按钮 + 1 条 AI 折叠条 + 14 个工具栏按钮 |
| 左侧项目树 | 9 | 2 个上移/下移图标按钮 + 7 个右键菜单项 |
| 原则横条 | 14 | 4 个单选 + 1 个「+」+ 1 组可点击原则卡片 + 8 个右键菜单项 |
| 单位工程工作台 | 23 | 表格 +/− 按钮列、合槽展开框、3 组右键菜单 |
| 工程量明细表 | 5 | 2 个分段按钮 + 3 个表格动作按钮 |
| AI 助手 | 9 | 5 个常驻按钮 + 附件移除 + 2 个折叠标题 + 1 个菜单项 |
| 各对话框 | 50 | 13 个对话框的底部按钮与功能按钮 |
| 通用控件 | 6 | 对话框关闭、消息框标准按钮组、输入框、表格 +/− 列 |
| **合计** | **134** | 不含动态生成的“每个模型/每条原则/每个合槽组”菜单项 |

## 一、主窗口标题栏与 AI 折叠条

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 1 | 最小化（— 图标） | `_WindowButton`（QToolButton） | `showMinimized()` | `src/app/views/main_window.py:189` |
| 2 | 最大化 / 还原（□ 图标，随窗口状态切换） | `_WindowButton` | `showMaximized()` / `showNormal()` | `src/app/views/main_window.py:190` |
| 3 | 关闭（× 图标） | `_WindowButton` | `window.close()` | `src/app/views/main_window.py:191` |
| 4 | AI 助手折叠条（› / ‹ 箭头，无文字） | `DragToggleBar`（QPushButton 自绘） | 展开/收起右侧 AI 面板 | `src/app/views/main_window.py:536`、`src/app/views/widgets/panel_splitter.py:105` |

> macOS 上 1–3 隐藏，改用系统红绿灯（`main_window.py:199-202`）。

## 二、主工具栏（14 个）

均为 `QAction`，由 `QToolBar` 渲染成图标按钮；同一动作也出现在菜单里。

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 5 | 新建工程（Ctrl+N） | QAction | `_new_project` | `src/app/views/main_window.py:629` |
| 6 | 打开工程…（Ctrl+O） | QAction | `_open_project` | `src/app/views/main_window.py:630` |
| 7 | 保存（Ctrl+S） | QAction | `_save_project` | `src/app/views/main_window.py:631` |
| 8 | 撤销（Ctrl+Z） | QAction | `_undo` | `src/app/views/main_window.py:635` |
| 9 | 重做（Ctrl+Y） | QAction | `_redo` | `src/app/views/main_window.py:636` |
| 10 | 新增标段 | QAction | `TreePanel.add_segment` | `src/app/views/main_window.py:669` |
| 11 | 新增单位工程 | QAction | `TreePanel.add_unit` | `src/app/views/main_window.py:670` |
| 12 | 剪切（Ctrl+X） | QAction | `UnitPanel.cut_selection` | `src/app/views/main_window.py:638` |
| 13 | 复制（Ctrl+C） | QAction | `UnitPanel.copy_selection` | `src/app/views/main_window.py:639` |
| 14 | 粘贴（Ctrl+V） | QAction | `UnitPanel.paste_selection` | `src/app/views/main_window.py:640` |
| 15 | 格式刷（可勾选） | QAction（checkable） | `_toggle_format_painter` | `src/app/views/main_window.py:659` |
| 16 | 导出 Excel…（Ctrl+E） | QAction | `_export_excel` | `src/app/views/main_window.py:634` |
| 17 | 切换暗色/亮色主题 | QAction | `_toggle_theme`；文案随主题变 | `src/app/views/main_window.py:671`、`876` |
| 18 | AI 助手（Ctrl+L） | QAction | `_toggle_ai_panel` | `src/app/views/main_window.py:672` |

> 仅菜单、不在工具栏的同类动作：另存为、关闭工程、导入旧版工程、退出、合槽编组/解散/移出/组内左右移、AI 设置、MCP 服务、关于。

## 三、左侧项目树

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 19 | 上移（chevron-up 图标） | QToolButton | 节点上移一位 | `src/app/views/panels/tree_panel.py:314` |
| 20 | 下移（chevron-down 图标） | QToolButton | 节点下移一位 | `src/app/views/panels/tree_panel.py:315` |
| 21 | 添加标段 | 右键菜单项 | `_add_segment` | `src/app/views/panels/tree_panel.py:423` |
| 22 | 添加单位工程 | 右键菜单项 | `_add_unit` | `src/app/views/panels/tree_panel.py:426` |
| 23 | 删除标段 | 右键菜单项 | `_delete`（带确认） | `src/app/views/panels/tree_panel.py:428` |
| 24 | 删除单位工程 | 右键菜单项 | `_delete`（带确认） | `src/app/views/panels/tree_panel.py:433` |
| 25 | 重命名 | 右键菜单项 | 弹 `FramelessInputDialog` | `src/app/views/panels/tree_panel.py:439` |
| 26 | 展开全部 | 右键菜单项 | `expandAll()` | `src/app/views/panels/tree_panel.py:440` |
| 27 | 折叠全部 | 右键菜单项 | `collapseAll()` | `src/app/views/panels/tree_panel.py:441` |

> 构件库面板本身没有按钮：类别用 `QComboBox`，条目靠双击插入。

## 四、原则横条

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 28 | 沟槽围护 | QRadioButton | 切换下方原则卡片列表 | `src/app/views/panels/principle_bar.py:104` |
| 29 | 地基处理 | QRadioButton | 同上 | `src/app/views/panels/principle_bar.py:104` |
| 30 | 挖填降水 | QRadioButton | 同上 | `src/app/views/panels/principle_bar.py:104` |
| 31 | 工作面宽 | QRadioButton | 同上 | `src/app/views/panels/principle_bar.py:104` |
| 32 | ＋（新建当前类原则） | QPushButton（icon-btn） | `_add_principle`，按当前单选新建 | `src/app/views/panels/principle_bar.py:122` |
| 33 | 原则卡片（彩色标签，非按钮外观） | `_PrincipleLabel`（QLabel） | 双击打开编辑；右键弹菜单 | `src/app/views/panels/principle_bar.py:177`、`356` |
| 34 | 编辑原则 | 右键菜单项 | `_open_editor` | `src/app/views/panels/principle_bar.py:262` |
| 35 | 导入原则 | 右键菜单项 | 选 `*.spcp` 导入 | `src/app/views/panels/principle_bar.py:263` |
| 36 | 导出原则 | 右键菜单项 | 导出 `*.spcp` | `src/app/views/panels/principle_bar.py:264` |
| 37 | 删除原则 | 右键菜单项 | 弹 `DeletePrincipleDialog` | `src/app/views/panels/principle_bar.py:265` |
| 38 | 添加沟槽围护原则 | 右键菜单项 | `_add_kind("enclosure")` | `src/app/views/panels/principle_bar.py:267-268` |
| 39 | 添加地基处理原则 | 右键菜单项 | `_add_kind("foundation")` | 同上 |
| 40 | 添加挖填降水原则 | 右键菜单项 | `_add_kind("precipitation")` | 同上 |
| 41 | 添加面宽原则 | 右键菜单项 | `_add_kind("width")` | 同上 |

## 五、单位工程工作台

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 42 | 管材表「＋」（表头格） | QPushButton（icon-btn） | `_add_pipe` | `src/app/views/panels/unit_panel.py:623`、`src/app/views/widgets/row_button_column.py:47` |
| 43 | 管材行「－」（每行一个） | QPushButton（icon-btn） | `_delete_pipe_row(row)` | `src/app/views/panels/unit_panel.py:629`、`row_button_column.py:106` |
| 44 | 工程量表「＋」（表头格，仅附属构筑物） | QPushButton（icon-btn） | `_add_quantity` | `src/app/views/panels/unit_panel.py:631` |
| 45 | 工程量行「－」（每行一个） | QPushButton（icon-btn） | `_delete_qty_row(row)` | `src/app/views/panels/unit_panel.py:637` |
| 46 | 合槽组展开/收起方框（＋/－） | 自绘（`_ElementNameDelegate`） | 展开/收起合槽成员行 | `src/app/views/panels/unit_panel.py:448-460` |
| 47 | 插入空行（Insert） | 右键菜单项 | `_insert_empty_row` | `src/app/views/panels/unit_panel.py:2365` |
| 48 | 删除选中构件 | 右键菜单项 | `_delete_selected_elements` | `src/app/views/panels/unit_panel.py:2366` |
| 49 | 复制（Ctrl+C） | 右键菜单项 | `_copy_elements` | `src/app/views/panels/unit_panel.py:2371` |
| 50 | 剪切（Ctrl+X） | 右键菜单项 | `_cut_elements` | `src/app/views/panels/unit_panel.py:2372` |
| 51 | 粘贴（Ctrl+V） | 右键菜单项 | `_paste_elements`；无剪贴板内容时禁用 | `src/app/views/panels/unit_panel.py:2373` |
| 52 | 选择沟槽围护原则（子菜单） | 右键菜单项 | 批量套用到多选构件 | `src/app/views/panels/unit_panel.py:2381` |
| 53 | 选择地基处理原则（子菜单） | 右键菜单项 | 同上 | `src/app/views/panels/unit_panel.py:2382` |
| 54 | 选择挖填降水原则（子菜单） | 右键菜单项 | 同上 | `src/app/views/panels/unit_panel.py:2383` |
| 55 | 选择工作面宽原则（子菜单） | 右键菜单项 | 同上 | `src/app/views/panels/unit_panel.py:2384` |
| 56 | 合槽编组 | 右键菜单项 | `create_group_from_selection` | `src/app/views/panels/unit_panel.py:2408` |
| 57 | 加入合槽…（子菜单） | 右键菜单项 | `join_group_from_selection` | `src/app/views/panels/unit_panel.py:2414` |
| 58 | 解散合槽 | 右键菜单项 | `dissolve_selected_group` | `src/app/views/panels/unit_panel.py:2421` |
| 59 | 移出合槽 | 右键菜单项 | `remove_selected_from_group` | `src/app/views/panels/unit_panel.py:2423` |
| 60 | 组内左移（上移） | 右键菜单项 | `move_selected_in_group(-1)` | `src/app/views/panels/unit_panel.py:2424` |
| 61 | 组内右移（下移） | 右键菜单项 | `move_selected_in_group(1)` | `src/app/views/panels/unit_panel.py:2427` |
| 62 | 复制主算式 | 右键菜单项 | 复制表达式主式 | `src/app/views/panels/unit_panel.py:1393` |
| 63 | 复制完整数值算式（Excel） | 右键菜单项 | 复制可粘进 Excel 的数值式 | `src/app/views/panels/unit_panel.py:1394` |
| 64 | 查看计算过程… | 右键菜单项 | 打开 `ExpressionDetailDialog` | `src/app/views/panels/unit_panel.py:1396` |

> 主表格双击「计算表达式」列也会打开计算过程窗体（不是按钮）。

## 六、工程量明细表页

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 65 | 定额工程量 | QPushButton（segment-btn，可勾选） | 切到定额表 | `src/app/views/panels/quantity_detail_panel.py:217` |
| 66 | 清单工程量 | QPushButton（segment-btn，可勾选） | 切到清单表 | 同上 |
| 67 | 收起表格 / 展开表格（图标+文字，文案随状态变） | QToolButton（table-action） | `_toggle_listing_collapse` | `src/app/views/panels/quantity_detail_panel.py:179`、`278` |
| 68 | 复制当前表格 | QToolButton（table-action） | 表格含表头复制到剪贴板 | `src/app/views/panels/quantity_detail_panel.py:185` |
| 69 | 导出当前表格 | QToolButton（table-action） | 导出当前表为 Excel | `src/app/views/panels/quantity_detail_panel.py:191` |

## 七、AI 助手面板

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 70 | 清空 | QPushButton | `_clear`，清空对话/附件/停止生成 | `src/app/views/panels/ai_panel.py:654` |
| 71 | 设置（齿轮图标，无文字） | QPushButton | 打开 `AiSettingsDialog` | `src/app/views/panels/ai_panel.py:657` |
| 72 | 发送（↑ 箭头图标，无文字） | QPushButton（aiSendBtn） | `_send_message` | `src/app/views/panels/ai_panel.py:694` |
| 73 | 模型来源（provider 名 + 下拉箭头，文字动态） | `_SourceButton`（QPushButton） | 弹模型切换菜单 | `src/app/views/panels/ai_panel.py:703`、`412` |
| 74 | 上传文件（回形针图标） | QToolButton（aiAttachBtn） | `_attach_files`，选文件挂附件 | `src/app/views/panels/ai_panel.py:713` |
| 75 | 附件移除「×」（每个附件一枚） | QToolButton | 从待发送附件里移除 | `src/app/views/panels/ai_panel.py:537` |
| 76 | 思考过程（折叠标题，文字带省略号动画） | QToolButton（checkable） | 展开/收起思考正文 | `src/app/views/panels/ai_panel.py:304` |
| 77 | 🔧 工具名（折叠标题，每次工具调用一个） | QToolButton（checkable） | 展开/收起该次工具的参数与结果 | `src/app/views/panels/ai_panel.py:246` |
| 78 | 管理模型 | 模型菜单项 | 打开 AI 设置 | `src/app/views/panels/ai_panel.py:988` |

> 模型菜单里每个 provider 一项（`ai_panel.py:981`），数量随配置变化，未逐项计入。

## 八、对话框

### 8.1 新建工程向导（`NewProjectWizard`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 79 | 完成 | QWizard 内置 | 收集 `values()` 并 accept | `src/app/views/dialogs/new_project_wizard.py:119-130` |
| 80 | 取消 | QWizard 内置 | reject | 同上 |

> 单页向导，`上一步` 在起始页自动隐藏、`下一步` 在末页自动隐藏；按钮布局由 QWizard 按平台排。

### 8.2 AI 模型设置（`AiSettingsDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 81 | 新增... | QPushButton | 弹预设菜单（各 provider 预设） | `src/app/views/dialogs/ai_settings_dialog.py:247`、`484` |
| 82 | 删除 | QPushButton | 删除当前 provider（带确认） | `src/app/views/dialogs/ai_settings_dialog.py:250` |
| 83 | 设为当前启用 / 当前已启用 | QPushButton | `_on_activate`；已启用时禁用并改文案 | `src/app/views/dialogs/ai_settings_dialog.py:255`、`443` |
| 84 | 测试连接 | QPushButton | `_on_test_connection`，后台线程请求 | `src/app/views/dialogs/ai_settings_dialog.py:307` |
| 85 | 确定 | 标准按钮（accept） | `_on_ok` 保存 | `src/app/views/dialogs/ai_settings_dialog.py:331-337` |
| 86 | 取消 | 标准按钮（reject） | 丢弃 | 同上 |

### 8.3 MCP 服务设置（`McpSettingsDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 87 | 生成 | QPushButton | 生成随机 Bearer token | `src/app/views/dialogs/mcp_settings_dialog.py:96` |
| 88 | 显示（可勾选） | QPushButton（checkable） | 切换 token 明文/密文 | `src/app/views/dialogs/mcp_settings_dialog.py:99` |
| 89 | 启动服务 | QPushButton | `_start` | `src/app/views/dialogs/mcp_settings_dialog.py:122` |
| 90 | 停止服务 | QPushButton | `_stop` | `src/app/views/dialogs/mcp_settings_dialog.py:125` |
| 91 | 复制配置 | QPushButton | 复制客户端 JSON 片段 | `src/app/views/dialogs/mcp_settings_dialog.py:139` |
| 92 | 保存 | 标准按钮（accept） | `_save` | `src/app/views/dialogs/mcp_settings_dialog.py:147-153` |
| 93 | 关闭 | 标准按钮（reject） | reject | 同上 |

### 8.4 导出工程数量表（`ExportExcelDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 94 | 全选 | QPushButton | 勾选全部单位工程 | `src/app/views/dialogs/export_excel_dialog.py:79` |
| 95 | 全不选 | QPushButton | 取消全部勾选 | `src/app/views/dialogs/export_excel_dialog.py:80` |
| 96 | 导出… | 标准按钮（accept） | `_export` | `src/app/views/dialogs/export_excel_dialog.py:129` |
| 97 | 关闭 | 标准按钮（reject） | close | `src/app/views/dialogs/export_excel_dialog.py:131` |

### 8.5 导入旧版工程 .stn（`LegacyImportDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 98 | 1. 选择旧工程文件(.stn)… | QPushButton | 选源文件并解析预览 | `src/app/views/dialogs/legacy_import_dialog.py:55` |
| 99 | 2. 选择保存路径… | QPushButton | 选目标路径；选源前禁用 | `src/app/views/dialogs/legacy_import_dialog.py:57` |
| 100 | 3. 开始迁移 | QPushButton | `_run`；前两步完成前禁用 | `src/app/views/dialogs/legacy_import_dialog.py:60` |
| 101 | 复制报告 | QPushButton | 复制迁移报告 | `src/app/views/dialogs/legacy_import_dialog.py:76` |
| 102 | 关闭 | 标准按钮（reject） | close | `src/app/views/dialogs/legacy_import_dialog.py:80` |

### 8.6 删除原则（`DeletePrincipleDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 103 | 确定 | 标准按钮（accept，默认焦点） | 按所选替代原则删除 | `src/app/views/dialogs/delete_principle_dialog.py:94` |
| 104 | 取消 | 标准按钮（reject） | 放弃 | `src/app/views/dialogs/delete_principle_dialog.py:99` |

### 8.7 地基处理原则编辑（`FoundationEditDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 105 | 编辑（特殊地基构件） | QPushButton | `_edit_component`，打开构件编辑器 | `src/app/views/dialogs/foundation_edit_dialog.py:142` |
| 106 | 换填层「＋」 | QPushButton（icon-btn） | `_insert_replacement` | `src/app/views/dialogs/foundation_edit_dialog.py:127` |
| 107 | 换填层行「－」 | QPushButton（icon-btn） | `_delete_replacement_row` | `src/app/views/dialogs/foundation_edit_dialog.py:133` |
| 108 | 确定 | 标准按钮（accept） | `_confirm` 落库 | `src/app/views/dialogs/foundation_edit_dialog.py:163-169` |
| 109 | 取消 | 标准按钮（reject） | 回滚会话 | 同上 |

### 8.8 沟槽围护原则编辑（`EnclosureEditDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 110 | 围护做法「＋」 | QPushButton（icon-btn） | `_insert_work` | `src/app/views/dialogs/enclosure_edit_dialog.py:92` |
| 111 | 围护做法行「－」 | QPushButton（icon-btn） | `_delete_work_rows`；仅剩一条时不装 | `src/app/views/dialogs/enclosure_edit_dialog.py:98` |
| 112 | 确定 | 标准按钮（accept） | `_confirm` 落库 | `src/app/views/dialogs/enclosure_edit_dialog.py:107-113` |
| 113 | 取消 | 标准按钮（reject） | 回滚 | 同上 |

### 8.9 工作面宽原则编辑（`WidthEditDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 114 | 恢复图集默认 | QPushButton | `_reset_current`，当前 tab 回默认值 | `src/app/views/dialogs/principle_dialogs.py:1078` |
| 115 | 确定 | 标准按钮（accept） | `_confirm` | `src/app/views/dialogs/principle_dialogs.py:1084-1090` |
| 116 | 取消 | 标准按钮（reject） | 放弃 | 同上 |

### 8.10 挖填降水原则编辑（`PrecipitationEditDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 117 | 确定 | 标准按钮（accept） | `_confirm` | `src/app/views/dialogs/principle_dialogs.py:1304-1310` |
| 118 | 取消 | 标准按钮（reject） | 放弃 | 同上 |

### 8.11 多级围护编辑窗体（`EnclosureWorkDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 119 | ＋（添加分级） | QPushButton（icon-btn） | `_add_level`；也可按 Insert | `src/app/views/dialogs/principle_dialogs.py:277` |
| 120 | 确定 | 标准按钮（accept） | `_accept` 写回围护做法 | `src/app/views/dialogs/principle_dialogs.py:288-294` |
| 121 | 取消 | 标准按钮（reject） | 按进入时快照还原 | 同上 |

> 该窗体的分级表还支持 Delete 删除选中分级、双击“围护形式描述”打开构件编辑器，均非按钮。

### 8.12 构件编辑器（`ComponentEditDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 122 | 参数表「＋」 | QPushButton（icon-btn） | 新增参数行（A~Z） | `src/app/views/dialogs/principle_dialogs.py:663-664` |
| 123 | 参数表行「－」 | QPushButton（icon-btn） | 删除该参数行 | `src/app/views/dialogs/principle_dialogs.py:667-669` |
| 124 | 公式表「＋」 | QPushButton（icon-btn） | 新增公式行（FA~FZ） | `src/app/views/dialogs/principle_dialogs.py:666` |
| 125 | 公式表行「－」 | QPushButton（icon-btn） | 删除该公式行 | 同上 |
| 126 | 确定 | 标准按钮（自绘，accept） | `_accept` 保存 | `src/app/views/dialogs/principle_dialogs.py:221-228` |
| 127 | 取消 | 标准按钮（自绘，reject） | reject | 同上 |

### 8.13 计算表达式（`ExpressionDetailDialog`）

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 128 | 复制计算式（图标，无文字） | QToolButton | `_copy_full_expression` | `src/app/views/dialogs/expression_detail_dialog.py:443` |

## 九、通用控件

| # | 按钮 | 类型 | 行为 | 位置 |
|---|---|---|---|---|
| 129 | 对话框关闭「×」（每个无边框对话框一枚） | `_DialogCloseButton`（QToolButton） | `window.close()` | `src/app/views/widgets/frameless_dialog.py:335` |
| 130 | 消息框标准按钮组（按调用方传入动态生成） | QPushButton（`add_dialog_buttons`） | 返回对应 `StandardButton` | `src/app/views/widgets/frameless_dialog.py:658-673` |
| 131 | 输入框「确定」 | 标准按钮（accept） | 返回文本 | `src/app/views/widgets/frameless_dialog.py:787-793` |
| 132 | 输入框「取消」 | 标准按钮（reject） | 返回空 | 同上 |
| 133 | 表格「＋」（表头格） | QPushButton（icon-btn） | 由使用方接 `add_clicked` | `src/app/views/widgets/row_button_column.py:47` |
| 134 | 表格行「－」 | QPushButton（icon-btn） | 由使用方接 `delete_clicked(row)` | `src/app/views/widgets/row_button_column.py:106` |

消息框文案映射（`frameless_dialog.py:44-60`）：确定 / 取消 / 是 / 否 / 保存 /
不保存 / 关闭 / 中止 / 重试 / 忽略 / 应用 / 重置 / 恢复默认 / 帮助 / 全部保存 /
全是 / 全否。工程里实际用到的是 确定、取消、是、否、保存、不保存、关闭，
以及 AI 写确认的“允许执行 / 拒绝”（`main_window.py:1427-1428`）。

## 附：开关类控件（非按钮，供参考）

| 控件 | 数量 | 位置 |
|---|---:|---|
| 沟槽围护 / 地基处理 / 挖填降水 / 工作面宽 | 4 | `src/app/views/panels/principle_bar.py:104` |
| 涵盖专业（雨水/污水/给水/中水） | 4 | `src/app/views/dialogs/new_project_wizard.py:83` |
| 导出标段费用汇总 / 定额表 / 清单表 / 合并所选单位工程 | 4 | `src/app/views/dialogs/export_excel_dialog.py:95,98,103,119` |
| MCP 自动启动 / 允许写操作 / 写操作弹确认 | 3 | `src/app/views/dialogs/mcp_settings_dialog.py:85,109,112` |
| AI 回传思考内容 / 写操作需人工确认 | 2 | `src/app/views/dialogs/ai_settings_dialog.py:295,321` |
| 计算支撑（左侧 / 右侧） | 2 | `src/app/views/panels/unit_panel.py:3010,3024` |

## 备注

1. 工具栏按钮全部是 `QAction`，同一动作在菜单里复用；按钮本身没有独立控件实例。
2. 表格行「－」按行动态创建（`RowButtonColumn.add_row_button`），数量随数据变化。
3. 消息框按钮按 `StandardButton` 组合动态生成，不是固定实例。
4. 原则卡片、合槽展开框、AI 折叠标题不是 `QAbstractButton` 子类，但承担点击交互，已计入。
5. 纯菜单项（文件/编辑/视图/AI/帮助、最近打开、加入合槽列表等）未逐条计入按钮总数。
