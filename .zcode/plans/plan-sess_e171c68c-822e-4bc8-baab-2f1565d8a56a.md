## Context

section2（Python 3.12 + PySide6 桌面应用）需要新增「导出 Excel 工程数量表」功能。现有代码里只有无头的 `services/summary.py::export_excel`（供 MCP/AI 用，列结构与新需求不符，保持不动）；被删除的 M5 汇总面板（git `3885512^`）提供了对话框/错误处理模板。openpyxl 已是核心依赖。同级仓库 `F:\GithubRepos\ArjenCole\brackets2` 的工具栏有现成的「导出 EXCEL」图标（`export-excel`）和「导出完成是否打开文件」交互，本次照搬同款。

**两条默认取值（提问未收到回复，如不符请在批准时指出）：**
1. 表格为 **6 列**：类别、名称、单位、数量、表达式（主算式，含 B/H 等符号 = `Quantity.display_expression`）、算式（右侧新增，纯数字代入式 = `Quantity.expression`）。
2. 清单工程量表**带定额拆分行**（浅蓝清单项目行 + 下挂定额拆分行，与 1.0 dGVL 及软件内清单页一致）；合并导出时按「类别+名称+单位」跨单位加总。

## 改动文件

### 1. `src/app/views/widgets/frameless_dialog.py` — 新增图标
在 `_ICON_BODIES`（59 行）加 `"export-excel"`，SVG body 逐字复制 brackets2 `src/brackets/views/widgets/icons.py` 的同名片（折角页面 + 绿色 Excel 磁贴白 X；rect 带 `fill="#21A366" stroke="none"`、白 X 带显式 `stroke="#FFFFFF"`，会覆盖主题色根 stroke，亮暗主题均正常，与 brackets2 行为一致）。

### 2. `src/app/services/summary.py` — 新增导出服务
新增 `export_quantity_tables(path, unit_ids: list[int], merged: bool = False) -> dict`（复用 `_unit_ids` 校验、`compute_unit`、`tracer.sorted_items/fmt`、`models.category_name`；现有 `export_excel` 不动）：

- **定额表行**：`summary, detail = compute_unit(uid)`；行 = `[类别, 名称, 单位, 数量(float), display_expression, expression]`，key 按 `|` 拆分。合并模式：新建 QDict，把各单位 summary 逐个 `QDict.extend()`（tracer.py:1849，项级合并，数值累加、算式自然拼接），再 `sorted_items` 输出——不需要自写合并类。
- **清单表行**：遍历 `detail`，每个构件先写清单项目行 `[category_name(row.category), row.spec or row.name, row.unit, fmt/float(amount_value), 数量原文, 数量原文]`（浅蓝底），下挂 `sorted_items(qdict)` 拆分行（同定额行结构）。合并模式：按 `(类别, spec-or-name, 单位)` 分组，数量求和、数量原文用 `" + "` 连接（跳过空/"0"，同 `unit_panel._merge_quantities` 1201 行规则），拆分行用组内 QDict extend 后 `sorted_items`。
- **工作簿**：openpyxl 单文件；分单位工程模式 → 每个单位工程两张 sheet `{单位工程名}-定额`、`{单位工程名}-清单`；合并模式 → `定额工程量`、`清单工程量` 两张。sheet 名消毒（替换 `:*?/\[]`、截断 ≤31 字符、重名加序号）。表头加粗、冻结首行、列宽 `[14, 34, 10, 14, 46, 60]`、清单项目行填充 `D6EAF8`（删除版 excel_export 同款）。

### 3. `src/app/views/dialogs/export_excel_dialog.py` — 新建导出对话框（新文件）
`ExportExcelDialog(FramelessDialog)`，照 `legacy_import_dialog.py` 的写法：标题「导出工程数量表」；单位工程复选框列表（每项 `标段 / 单位工程`，默认全选，附全选/全不选按钮）；合并选项复选框「合并所选单位工程（工程量全部加总后输出）」默认不勾（= 默认分单位工程导出，满足需求 4）；底部「导出…(primary) / 关闭」。导出流程：校验至少勾 1 项 → `QFileDialog.getSaveFileName(self, "导出 Excel", suggested_dir()/"工程数量表.xlsx", "Excel 工作簿 (*.xlsx)")` → 忙碌光标下调服务 → `update_config({"ui": {"last_dir": …}})` → `FramelessMessageBox.question("导出完成，是否打开文件？")`（brackets2 同款，是则 `os.startfile`/mac `opener`）→ `bus().status_message.emit("已导出：…")`；`PermissionError` → warning「文件被占用，请先关闭 Excel」。

### 4. `src/app/views/main_window.py` — 动作与工具栏
- `_build_actions`：`self._act_export_excel = self._action("导出 Excel(&E)…", self._export_excel, "Ctrl+E")`（Ctrl+E 同 brackets2）；slot `_export_excel` 惰性导入并 `exec` 对话框（同 `_ai_settings` 等现有 slot 风格）。
- `_ACTION_ICONS` 加 `"act_export_excel": "export-excel"`（主题切换自动重着色走现有 `_refresh_action_icons`）。
- `_build_toolbar`：格式刷之后加分隔线 + 导出按钮 + 分隔线，再接主题/AI 组。
- 文件菜单「另存为」后加该动作；动作加入 `_project_actions`（仅工程打开时可用）。

### 5. `tests/test_export_quantity_tables.py` — 新增测试（新文件）
用 conftest 的 `project` fixture（`new_project(NewProjectSpec(unit_names=[…]))`）建两个单位工程、各加一条简单构件（参照 `test_structure_quantities.py` 的加构件方式），分别验证：分单位工程导出的 sheet 名与行数、合并导出后定额表数量 = 两单位之和、sheet 名消毒、清单项目行存在。运行 `pytest tests/test_export_quantity_tables.py`。

## 验证
1. `pytest tests/test_export_quantity_tables.py`（以及既有 `test_project_io.py` 回归）。
2. 手动跑应用打开示例工程：工具栏出现绿色 Excel 图标（亮/暗主题各看一次）→ 分单位工程导出（每单位两张 sheet）→ 勾选合并再导出（两张汇总 sheet）→ 打开 xlsx 核对 6 列结构、清单项目行底色、数量可再计算（数值列）。
3. 打开目标文件夹被 Excel 占用时再导出一次，确认得到「文件被占用」提示而非崩溃。