# 标准按钮：自绘外观 + 平台摆放规则

标准按钮（对话框、消息框、向导里的确定/取消/保存/关闭等）**不再使用系统
原生按钮绘制**。按钮长什么样、悬停/按下怎么反馈，全部由项目自绘；平台
差异只剩**摆放顺序、默认按钮和宽度策略**。

## 分工

| 关注点 | 归属 | 说明 |
|---|---|---|
| 外观 / 悬停 / 按下 / 禁用 / 默认态 | `views/widgets/button_style.py` 的 `ButtonStyle` | QProxyStyle，只接管 `CE_PushButton`，其余控件委托底层原生样式 |
| 顺序 / 默认按钮 / 对齐 / 等宽 | `views/widgets/platform_buttons.py` | 只加控件、排布局，不设颜色 |
| 功能性按钮（＋/－、分段、AI 发送等） | `resources/qss/theme.py` 的 role/objectName 规则 | alpha.2 起就是 QSS 自绘，保持原样 |

`ButtonStyle` 在 `main.py` 启动时安装：`app.setStyle(ButtonStyle(app.style()))`。
因为它是 QProxyStyle，`QWizard` 等 Qt 内部创建的按钮也会被同一套绘制接管，
不需要逐个替换控件类（项目里的 `QDialogButtonBox` 也已替换为
`add_dialog_buttons`，不再保留另一套按钮布局）。

## 平台摆放规则

| 维度 | Windows（Win32 对话框惯例） | macOS（Apple HIG） |
|---|---|---|
| 按钮顺序 | 肯定按钮在**左**，取消在右 | 取消在左，肯定（默认）按钮在**最右** |
| 默认按钮 | 肯定动作；Enter 触发 | 肯定动作；Enter 触发 |
| 外观 | 自绘：普通卡片按钮 / 默认按钮主色填充 | 同左（两平台一致） |
| 宽度 | 同排等宽，按当前字体量标准文案取宽（≥84px） | 按文字自然宽度，不设固定宽 |
| 对齐 | 按钮行**右对齐** | 按钮行**右对齐** |
| 文案 | 确定 / 取消 / 保存 / 关闭 / 是 / 否 / 不保存 | 同左 |
| 键盘焦点 | 不额外绘制内侧焦点框（与 alpha.2 的 QSS 按钮一致） | 同左 |
| Esc | 取消（reject） | 取消（reject） |
| 向导按钮 | 完成/取消同在下排（QWizard 自排） | 取消在左下、完成在右下 |

## 自绘外观（回到 alpha.2）

取自 alpha.2 的按钮 QSS，两套主题都从 `ThemeColors` 取色：

| 状态 | 普通按钮 | 主色按钮（`primary=True`） |
|---|---|---|
| 常态 | `bg_card` 底、`border_strong` 1px 边、`text_primary` 字 | `primary` 底、`primary` 边、`text_inverse` 字、600 字重 |
| 悬停 | `bg_hover` | `primary_hover` |
| 按下 | `bg_pressed` | `primary_pressed` |
| 禁用 | `bg_hover` 底、`border` 边、`text_disabled` 字 | 同左（不保留主色） |

圆角 6px；内边距 5px 14px；边框 1px（与 alpha.2 QSS 的盒模型一致）。
尺寸由 `ButtonStyle.sizeFromContents` 计算：文字宽 + 30px、行高 + 12px，
这样 `platform_buttons` 的等宽/最小宽计算不依赖原生样式。

Windows 上标准动作按钮统一宽度：以 **84px** 为下限，再按当前字体量一遍
标准文案（含「完成(F)」「允许执行」「不保存」），取最长者；对话框按钮行和
`QWizard` 内部按钮共用 `platform_buttons.apply_standard_widths`，所以向导的
完成/取消不会比其它窗体的确定/取消宽出一截。更长的非标准文案（如
「1. 选择旧工程文件…」）仍按自然宽度展开。

`primary` 属性由 `platform_buttons` 统一写：显式 `default=True` 或第一个
accept 角色为 True，其余（含“只有关闭”的整排）为 False。`setDefault(True)`
只负责 Enter 键落点，不再直接决定是否主色填充——否则纯“关闭”对话框会
被画成蓝色肯定按钮。

## 约束

1. **QSS 里不要写通用 `QPushButton` 背景/边框规则**。写了 Qt 会改走
   `QStyleSheetStyle`，`ButtonStyle.drawControl` 就接管不到，按钮会退回
   原生外观。`tests/test_theme_color_scheme.py` 已锁定这一点。
2. 新对话框统一用 `platform_buttons.add_dialog_buttons`，不要手写按钮行、
   不要再用 `QDialogButtonBox`（它内部是原生按钮布局；项目里已全部替换）。
3. 功能性按钮继续用 `role` / `objectName` 的 QSS 规则；`ButtonStyle` 的
   `sizeFromContents` 会跳过这些控件，避免重复加内边距。
4. 不要手写 `primary` 属性——它由 `platform_buttons` 统一写（True = 主色，
   False = 普通）；Enter 落点由 `setDefault(True)` 单独表达。
5. **不要给按钮画内侧焦点圆角线框**：alpha.2 的 QSS 按钮没有这个线框，
   自绘时也不要加。需要键盘焦点可访问性时另开选项，且只在键盘 focus
   （`State_KeyboardFocusChange`）时画系统惯用的焦点框，不能按压就出现。
6. 原生文件选择框（`QFileDialog`）是系统对话框，不在自绘范围内。
