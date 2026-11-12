# 标准按钮的平台规范与统一实现

对话框、消息框里的**标准按钮**（确定/取消/保存/关闭等文字按钮）按所在平台的
原生规范呈现；自绘功能性控件（+/- 行按钮、分段控件、AI 发送、标题栏按钮等）
不属于标准按钮，仍由应用 QSS 描画（见 `src/app/resources/qss/theme.py`）。

## 平台规范

| 维度 | Windows（Win32 对话框惯例） | macOS（Apple HIG） |
|---|---|---|
| 按钮顺序 | 肯定按钮在**左**，取消在右 | 取消在**左**，肯定（默认）按钮在**最右** |
| 默认按钮 | 肯定动作；Enter 触发，原生样式带强调色 | 肯定动作；Enter 触发，accent 蓝底 |
| 外观 | 系统原生样式（Win11 上即 windows11 样式，默认按钮带系统强调色） | QMacStyle 原生 bezel |
| 宽度 | 同排等宽，最小 75px（Win32 基准 50 DLU） | 按文字自然宽度，不设固定宽 |
| 对齐 | 按钮行**右对齐** | 按钮行**右对齐** |
| 文案 | 确定 / 取消 / 保存 / 关闭 / 是 / 否 / 不保存 | 同左（两平台统一标准中文文案） |
| 键盘焦点 | 原生焦点框（不被 QSS 抹掉） | 系统键盘焦点环 |
| Esc | 取消（reject） | 取消（reject） |
| 向导按钮 | 上一步/下一步/取消同在右下角 | 取消在左下角、完成在右下角 |

配色不进 QSS：原生控件只读 QPalette。`theme.build_palette()` 在应用主题
（亮/暗）切换时把窗口/文字/按钮/高亮色同步进 QPalette；mac 上另由
`mac_window.apply_mac_app_appearance()` 把 NSAppearance 一并同步。

## 实现

- `src/app/views/widgets/platform_buttons.py` —— 唯一的按钮行构造点：
  - `DialogButtonSpec(text, role, on_click, default, button)`：`role` 取
    `"accept"`（肯定动作）/`"reject"`（取消、关闭）/`"other"`（辅助动作，
    如"不保存""复制报告"）；
  - `add_dialog_buttons(row, specs)`：按平台排好序加入 `row`（行首自带
    stretch 右对齐），确定默认按钮（显式 `default=True` > 第一个 accept >
    第一个 reject），Windows 上同排等宽；返回视觉顺序的按钮列表；
  - 需要保留按钮引用时传 `button=预建实例`（helper 收编该实例）；行内最左
    的辅助按钮先自行 `row.addWidget(...)` 再调 helper。
- `FramelessMessageBox` 把 `QMessageBox.StandardButton` 映射为三种 role 后
  走同一构造器（`frameless_dialog._STANDARD_BUTTON_ROLES`）。
- `QDialogButtonBox`（PrincipleSubDialog）与 `QWizard` 自带平台自适应，
  不再覆写按钮布局。
- 测试：`tests/test_platform_buttons.py` 锁定顺序/默认按钮/等宽/右对齐的
  平台行为（monkeypatch `is_mac` 覆盖两个分支）。

## 约束

1. 新对话框不要手写按钮行、不要 `setProperty("primary"/"secondary"/...)`
   （这些属性已随按钮 QSS 移除，挂了也是死属性）；
2. 不要给 `QPushButton` 加任何全局 QSS 背景/边框——任何盒模型属性都会让
   按钮改走样式表渲染、丢失原生观感；
3. 全局 `*` 规则不再含 `color`/`outline`，自绘控件各自的规则里按需补
   `outline: none`（输入类/表格/树/列表已补）。
4. **容器底色用 `.QWidget`（精确类选择器）**：主窗体是无边框半透明窗口，
   普通 QWidget 容器必须有底色否则透出桌面。`theme.py` 用
   `.QWidget { background-color: $bg_window; }` 只命中 QWidget 本身、不命中
   QPushButton 等子类，因此按钮保持原生渲染。QWidget 子类容器
   （TreePanel/AiPanel 等）不受该规则覆盖，需要在自己的 objectName 规则里
   显式写 `background-color`；对话框内部用 `QDialog .QWidget` 保持透明
   （对话框 body 自带 bg_dialog）。
