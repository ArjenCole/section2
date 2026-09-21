"""主窗体（计划 §7.1）：单窗体 + 三栏，不做 MDI、不做子窗体。

    ┌ 菜单栏 + 工具栏 ─────────────────────────────┐
    │ 项目树 280px │ 中部工作区（Tab） │ AI 助手 360px │
    └ 状态栏 ────────────────────────────────────┘

中部工作区只显示项目树里当前选中的节点：单位工程 → 单位工程 Tab，
根/标段 → 汇总 Tab，原则节点（M3 起）→ 原则 Tab。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import add_recent_project, get_config, remove_recent_project, update_config
from app.core.event_bus import bus
from app.core.version import (
    APP_DISPLAY_NAME,
    APP_VERSION,
    LEGACY_FILE_FILTER,
    PROJECT_FILE_FILTER,
)
from app.orm.base import NotAProjectFileError, ProjectFileError, SchemaTooNewError
from app.resources.qss.theme import ThemeManager
from app.services import project_io
from app.services.project_io import ProjectIoError, ProjectLockedError, NewProjectSpec
from app.viewmodels.project_vm import KIND_UNIT, TreeNode
from app.views.panels.ai_panel import AiPanel
from app.views.panels.principle_panel import PrinciplePanel
from app.views.panels.summary_panel import SummaryPanel
from app.views.panels.tree_panel import TreePanel
from app.views.panels.unit_panel import UnitPanel
from app.views.wizard.new_project_wizard import (
    NewProjectWizard,
    suggested_dir,
    suggested_file_name,
)

_TREE_WIDTH = 280
_AI_WIDTH = 360
_AI_TOGGLE_WIDTH = 14


class _ToggleBar(QToolButton):
    """AI 面板折叠条（竖条，14px）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "toggle-bar")
        self.setFixedWidth(_AI_TOGGLE_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)

    def set_expanded(self, expanded: bool) -> None:
        self.setText("›" if expanded else "‹")
        self.setToolTip("折叠 AI 助手 (Ctrl+L)" if expanded else "展开 AI 助手 (Ctrl+L)")


class MainWindow(QMainWindow):
    """Section 2.0 主窗体。"""

    def __init__(self, project_path: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.resize(1440, 900)
        self._build_central()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_events()
        self._update_title()
        self._refresh_recent_menu()
        if project_path:
            QTimer.singleShot(0, lambda: self._open_path(project_path))

    # ------------------------------------------------------------------ 布局
    def _build_central(self) -> None:
        self._tree_panel = TreePanel()
        self._unit_panel = UnitPanel()
        self._principle_panel = PrinciplePanel()
        self._summary_panel = SummaryPanel()
        self._ai_panel = AiPanel()

        self._center_stack = QStackedWidget()
        placeholder = QLabel("请从左侧选择节点。\n文件 → 新建工程 / 打开工程")
        placeholder.setProperty("role", "placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center_stack.addWidget(placeholder)

        self._workbench = QTabWidget()
        self._workbench.addTab(self._unit_panel, "单位工程")
        self._workbench.addTab(self._principle_panel, "原则")
        self._workbench.addTab(self._summary_panel, "汇总")
        self._center_stack.addWidget(self._workbench)

        ai_container = QWidget()
        ai_layout = QHBoxLayout(ai_container)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.setSpacing(0)
        self._ai_toggle = _ToggleBar()
        self._ai_toggle.clicked.connect(self._toggle_ai_panel)
        ai_layout.addWidget(self._ai_toggle)
        ai_layout.addWidget(self._ai_panel)
        self._ai_container = ai_container

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree_panel)
        splitter.addWidget(self._center_stack)
        splitter.addWidget(ai_container)
        splitter.setHandleWidth(1)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        self._splitter = splitter
        self.setCentralWidget(splitter)

        self._ai_saved_width = _AI_WIDTH
        expanded = get_config().ai_panel_expanded
        self._apply_ai_visible(expanded, initial=True)

    def _apply_ai_visible(self, expanded: bool, *, initial: bool = False) -> None:
        self._ai_panel.setVisible(expanded)
        self._ai_toggle.set_expanded(expanded)
        if expanded:
            self._ai_container.setMaximumWidth(16777215)
        else:
            self._ai_container.setMaximumWidth(_AI_TOGGLE_WIDTH)

        if initial:
            # 窗口还没显示过，splitter.sizes() 全是 0，直接用默认宽度
            # （中间给 600，剩下的宽度由窗口分配，保证左右两栏拿到计划里的 280 / 360）
            sizes = [
                _TREE_WIDTH,
                600,
                _AI_WIDTH + _AI_TOGGLE_WIDTH if expanded else _AI_TOGGLE_WIDTH,
            ]
        else:
            sizes = self._splitter.sizes()
            if expanded:
                target = self._ai_saved_width + _AI_TOGGLE_WIDTH
                take = min(max(0, target - sizes[2]), max(0, sizes[1] - 200))
                sizes[1] -= take
                sizes[2] += take
            else:
                self._ai_saved_width = max(240, self._ai_panel.width())
                sizes[1] += max(0, sizes[2] - _AI_TOGGLE_WIDTH)
                sizes[2] = _AI_TOGGLE_WIDTH
        self._splitter.setSizes(sizes)

    # ------------------------------------------------------------------ 动作
    def _build_actions(self) -> None:
        self._act_new = self._action("新建工程(&N)", self._new_project, "Ctrl+N")
        self._act_open = self._action("打开工程(&O)…", self._open_project, "Ctrl+O")
        self._act_save = self._action("保存(&S)", self._save_project, "Ctrl+S")
        self._act_save_as = self._action("另存为(&A)…", self._save_project_as, "Ctrl+Shift+S")
        self._act_close = self._action("关闭工程(&C)", self._close_project)
        self._act_import_legacy = self._action("导入旧版工程(.stn)…", self._import_legacy)
        self._act_import_legacy.setEnabled(False)
        self._act_import_legacy.setToolTip("M6 实现：旧 .stn(XML) 单向迁移导入")
        self._act_exit = self._action("退出(&Q)", self.close, "Ctrl+Q")

        self._act_add_segment = self._action("新增标段", lambda: self._tree_panel.add_segment())
        self._act_add_unit = self._action("新增单位工程", lambda: self._tree_panel.add_unit())
        self._act_add_element = self._action("新增构件条目", self._add_element)
        self._act_refresh = self._action("刷新", self._refresh, "F5")
        self._act_theme = self._action("切换暗色主题", self._toggle_theme, "Ctrl+Shift+T")
        self._act_ai_panel = self._action("AI 助手", lambda: self._toggle_ai_panel(), "Ctrl+L")
        self._act_ai_settings = self._action("AI 设置…", self._ai_settings)
        self._act_ai_settings.setEnabled(False)
        self._act_ai_settings.setToolTip("M7 实现")
        self._act_about = self._action("关于 Section", self._about)

        for action in (
            self._act_save,
            self._act_save_as,
            self._act_close,
            self._act_add_segment,
            self._act_add_unit,
            self._act_add_element,
            self._act_refresh,
        ):
            action.setEnabled(False)
        self._project_actions = (
            self._act_save,
            self._act_save_as,
            self._act_close,
            self._act_add_segment,
            self._act_add_unit,
            self._act_add_element,
            self._act_refresh,
        )

    def _action(self, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")
        file_menu.addAction(self._act_new)
        file_menu.addAction(self._act_open)
        self._recent_menu = file_menu.addMenu("最近打开")
        file_menu.addSeparator()
        file_menu.addAction(self._act_save)
        file_menu.addAction(self._act_save_as)
        file_menu.addAction(self._act_close)
        file_menu.addSeparator()
        file_menu.addAction(self._act_import_legacy)
        file_menu.addSeparator()
        file_menu.addAction(self._act_exit)

        project_menu = menubar.addMenu("项目(&P)")
        project_menu.addAction(self._act_add_segment)
        project_menu.addAction(self._act_add_unit)
        project_menu.addAction(self._act_add_element)
        project_menu.addSeparator()
        project_menu.addAction(self._act_refresh)

        view_menu = menubar.addMenu("视图(&V)")
        view_menu.addAction(self._act_theme)
        view_menu.addSeparator()
        view_menu.addAction(self._act_ai_panel)
        view_menu.addAction(self._action("单位工程工作台", lambda: self._show_tab(0)))
        view_menu.addAction(self._action("原则编辑器", lambda: self._show_tab(1)))
        view_menu.addAction(self._action("汇总", lambda: self._show_tab(2)))

        ai_menu = menubar.addMenu("AI(&A)")
        ai_menu.addAction(self._act_ai_settings)
        ai_menu.addAction(self._act_ai_panel)

        help_menu = menubar.addMenu("帮助(&H)")
        help_menu.addAction(self._act_about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.addAction(self._act_new)
        toolbar.addAction(self._act_open)
        toolbar.addAction(self._act_save)
        toolbar.addSeparator()
        toolbar.addAction(self._act_add_segment)
        toolbar.addAction(self._act_add_unit)
        toolbar.addAction(self._act_add_element)
        toolbar.addSeparator()
        toolbar.addAction(self._act_refresh)
        toolbar.addAction(self._act_theme)
        toolbar.addAction(self._act_ai_panel)
        self.addToolBar(toolbar)

    def _build_statusbar(self) -> None:
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)
        self._status_path = QLabel("未打开工程")
        self._status_path.setProperty("role", "hint")
        statusbar.addPermanentWidget(self._status_path)
        statusbar.showMessage("就绪")

    # ------------------------------------------------------------------ 事件
    def _connect_events(self) -> None:
        bus().project_opened.connect(self._on_project_opened)
        bus().project_closed.connect(self._on_project_closed)
        bus().project_saved.connect(lambda path: self._set_status(f"已保存：{path}"))
        bus().node_selected.connect(self._on_node_selected)
        bus().status_message.connect(self._set_status)
        bus().ai_panel_toggle_requested.connect(self._apply_ai_visible)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _on_project_opened(self, path: str) -> None:
        add_recent_project(path)
        update_config({"ui": {"last_dir": str(Path(path).parent)}})
        self._refresh_recent_menu()
        self._set_project_actions(True)
        self._update_title()
        self._status_path.setText(str(path))
        self._set_status(f"已打开工程：{path}")
        self._summary_panel.refresh()

    def _on_project_closed(self) -> None:
        self._set_project_actions(False)
        self._update_title()
        self._status_path.setText("未打开工程")
        self._center_stack.setCurrentIndex(0)

    def _on_node_selected(self, node: TreeNode | None) -> None:
        if node is None:
            self._center_stack.setCurrentIndex(0)
            return
        self._center_stack.setCurrentIndex(1)
        if node.kind == KIND_UNIT:
            self._show_tab(0)
        else:
            self._show_tab(2)

    def _show_tab(self, index: int) -> None:
        self._center_stack.setCurrentIndex(1)
        self._workbench.setCurrentIndex(index)

    def _on_theme_changed(self, _name: str) -> None:
        self._unit_panel.refresh()
        self._ai_panel.refresh_theme()

    def _set_status(self, message: str, timeout: int = 0) -> None:
        self.statusBar().showMessage(message, timeout)

    def _set_project_actions(self, enabled: bool) -> None:
        for action in self._project_actions:
            action.setEnabled(enabled)

    def _update_title(self) -> None:
        path = project_io.current_path()
        if path is None:
            self.setWindowTitle(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        else:
            name = project_io.project_name() or Path(path).stem
            self.setWindowTitle(f"{name} - {APP_DISPLAY_NAME} {APP_VERSION}")

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = get_config().recent_projects
        if not recent:
            action = self._recent_menu.addAction("（空）")
            action.setEnabled(False)
            return
        for path in recent:
            action = self._recent_menu.addAction(path)
            action.triggered.connect(lambda _checked=False, target=path: self._open_path(target))

    # ------------------------------------------------------------------ 工程操作
    def _new_project(self) -> None:
        wizard = NewProjectWizard(self)
        if wizard.exec() != NewProjectWizard.DialogCode.Accepted:
            return
        values = wizard.values()
        target, _filter = QFileDialog.getSaveFileName(
            self,
            "保存新工程",
            str(suggested_dir() / suggested_file_name(values["project_name"])),
            PROJECT_FILE_FILTER,
        )
        if not target:
            return
        spec = NewProjectSpec(path=Path(target), **values)
        try:
            path = project_io.new_project(spec)
        except ProjectIoError as error:
            self._error("新建工程失败", str(error))
            return
        bus().project_opened.emit(str(path))
        self._tree_panel.vm.load()

    def _open_project(self) -> None:
        start = get_config().last_dir or str(suggested_dir())
        target, _filter = QFileDialog.getOpenFileName(self, "打开工程", start, PROJECT_FILE_FILTER)
        if target:
            self._open_path(target)

    def _open_path(self, path: str) -> None:
        if not Path(path).exists():
            self._error("打开工程失败", f"文件不存在：{path}")
            remove_recent_project(path)
            self._refresh_recent_menu()
            return
        try:
            opened = project_io.open_project(path)
        except ProjectLockedError as error:
            self._error("工程已打开", str(error))
            return
        except SchemaTooNewError as error:
            self._error("版本不兼容", str(error))
            return
        except NotAProjectFileError as error:
            self._error("无法打开", str(error))
            return
        except ProjectFileError as error:
            self._error("打开工程失败", str(error))
            return
        bus().project_opened.emit(str(opened))
        self._tree_panel.vm.load()

    def _save_project(self) -> None:
        try:
            path = project_io.save()
        except ProjectIoError as error:
            self._error("保存失败", str(error))
            return
        if path is not None:
            bus().project_saved.emit(str(path))

    def _save_project_as(self) -> None:
        start = str(project_io.current_path() or suggested_dir())
        target, _filter = QFileDialog.getSaveFileName(self, "另存为", start, PROJECT_FILE_FILTER)
        if not target:
            return
        try:
            path = project_io.save_as(target)
        except ProjectIoError as error:
            self._error("另存为失败", str(error))
            return
        bus().project_saved.emit(str(path))
        bus().project_opened.emit(str(path))
        self._tree_panel.vm.load()

    def _close_project(self) -> None:
        if project_io.current_path() is None:
            return
        project_io.close_project()
        bus().project_closed.emit()

    def _import_legacy(self) -> None:  # pragma: no cover - M6 实现
        self._set_status("旧版工程导入将在 M6 实现。", 4000)

    def _add_element(self) -> None:
        node = self._tree_panel.vm.current()
        if node is None or not node.is_unit:
            self._set_status("请先在左侧选择单位工程。", 4000)
            return
        self._show_tab(0)
        self._unit_panel.add_element()

    def _refresh(self) -> None:
        self._tree_panel.vm.load()
        self._summary_panel.refresh()
        self._unit_panel.refresh()
        self._set_status("已刷新", 2000)

    def _toggle_theme(self) -> None:
        name = ThemeManager.instance().toggle(QApplication.instance())
        update_config({"ui": {"theme": name}})
        self._set_status("已切换到暗色主题" if name == "dark" else "已切换到亮色主题", 3000)

    def _toggle_ai_panel(self) -> None:
        expanded = not self._ai_panel.isVisible()
        self._apply_ai_visible(expanded)
        update_config({"ui": {"ai_panel_expanded": expanded}})

    def _ai_settings(self) -> None:  # pragma: no cover - M7 实现
        self._set_status("AI 设置将在 M7 实现。", 4000)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "关于 Section",
            f"{APP_DISPLAY_NAME}　版本 {APP_VERSION}<br><br>"
            "线性工程（市政管道）工程量计算软件，Python + PySide6 重写版。<br>"
            "工程文件：.stn2（单文件 SQLite）<br><br>"
            "参考初代 C# 版 section 1.2.2.171220_beta。",
        )

    def _error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    # ------------------------------------------------------------------ 退出
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """退出前落盘并释放锁（计划 §11 风险 6）。"""
        try:
            project_io.close_project()
        except Exception as error:  # pragma: no cover - 退出路径不阻塞
            self._set_status(f"关闭工程时出错：{error}", 5000)
        super().closeEvent(event)
