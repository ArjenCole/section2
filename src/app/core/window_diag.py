"""窗口"消失"诊断黑匣子（仅 Windows，仅 ``SECTION2_DIAG=1`` 时启用）。

背景（2026-10-22 两次现场）：弹窗开着时点一下主窗体，主窗体与弹窗一起从屏幕上
消失、进程却还在运行。两次取证都表明**不是崩溃**：GUI 线程空闲在 ``app.exec()``、
``SendMessageTimeout`` 有应答，但 ``EnumWindows`` 里主窗体的 HWND 已经不存在
（健康时类名是 ``Qt6xxxQWindowIcon``）。结论是"顶层原生窗口被销毁且没有再 show"；
弹窗连坐，是因为它是主窗体的 owned 窗口（Windows 规则：owner 销毁 → owned 全灭）。

要定位"谁销毁的"，需要原生窗口事件的时序。本模块做三件事：

1. ``SetWinEventHook`` 监听本进程的 SHOW / HIDE / DESTROY —— 原生真相；
2. 记录可疑路径上的每一次原生窗口操作（自绘圆角 / 影子窗口那一层、原则弹窗、
   主窗体进出事件），带相对时间戳、当前模态窗、HWND 与调用点；
3. 一旦"被跟踪的可视顶层窗口"的 HWND 被销毁（钩子报告，或 1s 自检发现失效），
   立刻落盘 ``logs/window_diag_<时间>.dump.txt``：
   最近 600 条时序 + 本进程全部顶层窗口快照 + 当时的 Python 栈。

正常启动（无 ``SECTION2_DIAG=1``）时 :func:`install` 返回 ``None``，:func:`record`
是空操作——对性能和行为零影响。

用法::

    set SECTION2_DIAG=1 && .venv\\Scripts\\python.exe src\\app\\main.py
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime

from app.core.paths import log_dir

_logger = logging.getLogger("section2.window_diag")

#: 环境变量开关
ENV_FLAG = "SECTION2_DIAG"

#: 环形缓冲保留条数
_RING_SIZE = 600

#: 自检间隔（毫秒）
_POLL_MS = 1000

# --- Win32 常量 ---------------------------------------------------------------
_EVENT_OBJECT_DESTROY = 0x8001
_EVENT_OBJECT_SHOW = 0x8002
_EVENT_OBJECT_HIDE = 0x8003
_WINEVENT_OUTOFCONTEXT = 0x0000
_OBJID_WINDOW = 0
_GWL_EXSTYLE = -20
_GW_OWNER = 4
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_LAYERED = 0x00080000

_EVENT_NAMES = {
    _EVENT_OBJECT_DESTROY: "DESTROY",
    _EVENT_OBJECT_SHOW: "SHOW",
    _EVENT_OBJECT_HIDE: "HIDE",
}

#: 记录的 Qt 事件（只对顶层窗口）
_WATCHED_EVENTS: set = set()

#: 单独用得上的几个事件类型（在 _init_watched_events 里填充）
_EV_SHOW = _EV_HIDE = _EV_CLOSE = _EV_QUIT = None

#: 一个会话最多落盘几份 dump（防止异常循环把磁盘写满）
_MAX_DUMPS = 20


# --------------------------------------------------------------------------- #
# Win32 绑定（只在 Windows 上建立；argtypes 必须写全，否则 64 位下 HWND 会被截断）
# --------------------------------------------------------------------------- #
if sys.platform == "win32":  # pragma: no cover - 平台相关
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _WinEventProc = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,  # hWinEventHook
        wintypes.DWORD,  # event
        wintypes.HWND,  # hwnd
        wintypes.LONG,  # idObject
        wintypes.LONG,  # idChild
        wintypes.DWORD,  # idEventThread
        wintypes.DWORD,  # dwmsEventTime
    )

    _user32.SetWinEventHook.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HMODULE,
        _WinEventProc,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _user32.SetWinEventHook.restype = wintypes.HANDLE
    _user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _kernel32.GetCurrentProcessId.restype = wintypes.DWORD
else:  # pragma: no cover - 非 Windows 只保证 import 不炸
    _user32 = None
    _kernel32 = None


def _init_watched_events() -> None:
    """把需要记录的 QEvent 类型装进集合（延迟到真正启用时再 import PySide6）。"""
    global _EV_SHOW, _EV_HIDE, _EV_CLOSE, _EV_QUIT
    if _WATCHED_EVENTS:
        return
    from PySide6.QtCore import QEvent

    _EV_SHOW = QEvent.Type.Show
    _EV_HIDE = QEvent.Type.Hide
    _EV_CLOSE = QEvent.Type.Close
    _EV_QUIT = getattr(QEvent.Type, "Quit", None)
    for name in (
        "Show",
        "Hide",
        "Close",
        "Destroy",
        "Polish",
        "StyleChange",
        "ActivationChange",
        "WindowActivate",
        "WindowDeactivate",
        "WindowStateChange",
        "ZOrderChange",
    ):
        value = getattr(QEvent.Type, name, None)
        if value is not None:
            _WATCHED_EVENTS.add(value)


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #
#: 当前实例（未启用时为 None；record() 只看这个全局）
_INSTANCE: "WindowDiag | None" = None


def record(kind: str, detail: str = "", *, stack: int = 0) -> None:
    """记录一条诊断事件（未启用时是空操作，调用点不必判断）。

    ``stack`` > 0 时附带 ``stack`` 层调用点（file:line 函数），用于埋点定位。
    """
    instance = _INSTANCE
    if instance is not None:
        instance.record(kind, detail, stack=stack)


def enabled() -> bool:
    """是否已启用（用于避免在热路径上白算参数）。"""
    return _INSTANCE is not None


def install(app) -> "WindowDiag | None":
    """安装诊断（Windows + 真实 windows 平台插件；默认开启）。

    屏幕上的"主窗体+弹窗一起消失、进程还在"目前只能靠这套记录定位，所以默认常开；
    不想要时设环境变量 ``SECTION2_DIAG=0`` 关掉（离屏测试里也自动不启用）。
    """
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    if sys.platform != "win32":
        return None
    try:
        if app.platformName() != "windows":  # 离屏/Qt 测试里不启用
            return None
    except Exception:  # noqa: BLE001
        return None
    if os.environ.get(ENV_FLAG, "").strip().lower() in {"0", "false", "no", "off"}:
        return None
    _INSTANCE = WindowDiag(app)
    return _INSTANCE


def shutdown() -> None:
    """卸载钩子与定时器（退出/测试用）。"""
    global _INSTANCE
    instance = _INSTANCE
    _INSTANCE = None
    if instance is not None:
        instance.dispose()


# --------------------------------------------------------------------------- #
# 黑匣子
# --------------------------------------------------------------------------- #
class WindowDiag:  # pragma: no cover - 需要真实 Windows 窗口
    """窗口事件黑匣子。"""

    def __init__(self, app) -> None:
        from PySide6.QtCore import QObject, QTimer

        _init_watched_events()
        self._app = app
        self._ring: deque[str] = deque(maxlen=_RING_SIZE)
        self._started = time.monotonic()
        self._hwnds: dict[int, str] = {}  # hwnd -> 标签（首次见到可视窗口时登记）
        self._tracked: set[int] = set()  # 已装过滤器的 widget（按 id 去重）
        self._hidden: set[int] = set()  # Qt 侧已经 Hide/Close 过的 hwnd（正常关窗）
        self._widgets: dict[int, object] = {}  # hwnd -> weakref(widget)，用于查 Qt 侧可见性
        self._dumped: set[int] = set()
        self._dump_count = 0
        self._pid = _kernel32.GetCurrentProcessId()
        self._log_path = log_dir() / "window_diag.log"
        # 每启动一次追加一份；超过 8MB 就滚动成 .1（诊断期间默认常开，别让它无限长）
        try:
            if self._log_path.exists() and self._log_path.stat().st_size > 8 * 1024 * 1024:
                self._log_path.replace(self._log_path.with_suffix(".log.1"))
        except OSError:
            pass
        self._log_file = open(self._log_path, "a", encoding="utf-8", buffering=1)

        # ctypes 回调必须持有引用：临时对象被回收后，钩子会调到野指针上，直接崩进程
        self._hook = None
        self._proc = _WinEventProc(self._on_win_event)

        class _Filter(QObject):
            """顶层窗口事件过滤器（同一个实例可装到多个窗口上）。"""

            def __init__(self, owner: "WindowDiag") -> None:
                super().__init__()
                self._owner = owner

            def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
                self._owner._on_widget_event(obj, event)
                return False

        self._filter = _Filter(self)

        class _AppFilter(QObject):
            """应用级事件：收到 Quit 说明有人调了 quit()/closeAllWindows()。"""

            def __init__(self, owner: "WindowDiag") -> None:
                super().__init__()
                self._owner = owner

            def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
                if _EV_QUIT is not None and event.type() == _EV_QUIT:
                    self._owner.record("app.quit", "收到 QEvent::Quit", stack=8)
                    self._owner._dump("应用收到 Quit（窗口即将集体消失）")
                return False

        self._app_filter = _AppFilter(self)
        try:
            app.installEventFilter(self._app_filter)
        except Exception:  # noqa: BLE001
            self._app_filter = None

        self._hook = _user32.SetWinEventHook(
            _EVENT_OBJECT_DESTROY,
            _EVENT_OBJECT_HIDE,
            None,
            self._proc,
            self._pid,
            0,
            _WINEVENT_OUTOFCONTEXT,
        )

        self._timer = QTimer()
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        # 原生崩溃兜底：真出 SIGSEGV 时把崩线程的 Python 栈落到 faulthandler.log
        # （Qt 内部崩溃不会走 sys.excepthook，这是唯一能留下痕迹的地方）
        self._fault_file = None
        try:
            import faulthandler

            self._fault_file = open(log_dir() / "faulthandler.log", "a", encoding="utf-8")
            faulthandler.enable(self._fault_file)
        except Exception:  # noqa: BLE001
            self._fault_file = None

        self._write(f"=== 窗口诊断开启 pid={self._pid} {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        self.record("diag.install", f"事件流：{self._log_path}")
        self._poll()  # 立刻登记当前已有的窗口（主窗体此时还没建也没关系，1s 内会补上）
        _logger.info("窗口诊断已开启：%s", self._log_path)

    # ------------------------------------------------------------------ 记录
    def record(self, kind: str, detail: str = "", *, stack: int = 0) -> None:
        try:
            from PySide6.QtWidgets import QApplication

            line = f"{time.monotonic() - self._started:9.3f}s  [{kind}]"
            if detail:
                line += f"  {detail}"
            modal = QApplication.activeModalWidget()
            if modal is not None:
                line += f"  {{modal={type(modal).__name__}}}"
            if stack:
                line += "  @ " + _call_site(stack + 1)
            self._ring.append(line)
            self._write(line)
        except Exception:  # noqa: BLE001 - 诊断永远不能反过来搞崩程序
            pass

    def _write(self, line: str) -> None:
        try:
            self._log_file.write(line + "\n")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 原生事件
    def _on_win_event(self, hook, event, hwnd, id_object, id_child, thread, when):
        try:
            if id_object != _OBJID_WINDOW or not hwnd:
                return
            label = self._hwnds.get(int(hwnd))
            cls, title = _window_info(int(hwnd))
            mark = f"  <<< 跟踪中：{label}" if label else ""
            self.record(
                f"native.{_EVENT_NAMES.get(event, hex(event))}",
                f"hwnd={hwnd} {cls} {title!r}{mark}",
            )
            if label and event == _EVENT_OBJECT_DESTROY:
                expected = self._destroy_expected(int(hwnd))
                if expected:
                    self.record("native.destroy_expected", f"hwnd={hwnd} {label}（Qt 已关窗，正常）")
                else:
                    # 关键信号：Qt 侧仍认为这个窗口可见，但原生窗口被销毁了
                    self._dump(f"窗口未经 Qt 的 Hide/Close 就被销毁：{label} hwnd={hwnd}")
                self._hwnds.pop(int(hwnd), None)
                self._hidden.discard(int(hwnd))
                self._widgets.pop(int(hwnd), None)
        except Exception:  # noqa: BLE001 - 回调里绝不能抛
            pass

    # ------------------------------------------------------------------ Qt 事件
    def _on_widget_event(self, widget, event) -> None:
        try:
            etype = event.type()
            if etype not in _WATCHED_EVENTS:
                return
            if not widget.isWindow():
                return
            hwnd = int(widget.winId())
            tracked = hwnd in self._hwnds
            # 被跟踪的窗口收到 Close / Hide 时把调用栈一起记下来：
            # 实测本机 PySide6 6.11 下 close() 会**销毁**原生窗口（hide() 不会），
            # 所以"主窗体消失"等价于"有人 close/hide 了它"，栈能直接指出是谁干的。
            self.record(
                f"qt.{etype.name}",
                f"{type(widget).__name__} hwnd={hwnd} title={widget.windowTitle()!r}"
                + (f"  跟踪中：{self._hwnds[hwnd]}" if tracked else ""),
                stack=8 if tracked and etype in (_EV_HIDE, _EV_CLOSE) else 0,
            )
            # 记录"Qt 侧已主动关窗"的信号：这类 DESTROY 属正常，不落盘
            if etype in (_EV_HIDE, _EV_CLOSE):
                self._hidden.add(hwnd)
            elif etype == _EV_SHOW:
                self._hidden.discard(hwnd)
        except Exception:  # noqa: BLE001
            pass

    def _destroy_expected(self, hwnd: int) -> bool:
        """该 HWND 被销毁是否属于"正常关窗"（Qt 已经 Hide/Close，或 widget 已析构）。"""
        if hwnd in self._hidden:
            return True
        reference = self._widgets.get(hwnd)
        widget = reference() if reference is not None else None
        if widget is None:
            return True  # widget 本身已销毁：正常
        try:
            return not widget.isVisible()
        except RuntimeError:
            return True

    # ------------------------------------------------------------------ 自检
    def _poll(self) -> None:
        """登记新出现的可视顶层窗口；校验已登记窗口的 HWND 是否还活着。"""
        try:
            import weakref

            from PySide6.QtWidgets import QApplication

            for widget in QApplication.topLevelWidgets():
                if not _is_alive(widget):
                    continue
                try:
                    if not widget.isWindow() or not widget.isVisible():
                        continue
                    key = id(widget)
                    if key in self._tracked:
                        continue
                    hwnd = int(widget.winId())
                    label = f"{type(widget).__name__}:{widget.windowTitle()}"
                    self._tracked.add(key)
                    # 同一 HWND 只记一次（不同 widget 可能共用同一个原生窗口）
                    self._hwnds.setdefault(hwnd, label)
                    self._widgets.setdefault(hwnd, weakref.ref(widget))
                    self._hidden.discard(hwnd)
                    widget.installEventFilter(self._filter)
                    self.record("track", f"{label} hwnd={hwnd}")
                except (RuntimeError, TypeError):
                    continue

            for hwnd, label in list(self._hwnds.items()):
                if _user32.IsWindow(hwnd):
                    continue
                expected = self._destroy_expected(hwnd)
                self._hwnds.pop(hwnd, None)
                self._widgets.pop(hwnd, None)
                self._hidden.discard(hwnd)
                if not expected:
                    self._dump(f"自检发现窗口的 HWND 已失效（Qt 仍认为可见）：{label} hwnd={hwnd}")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 落盘
    def _dump(self, reason: str) -> None:
        key = hash(reason)
        if key in self._dumped:
            return
        self._dumped.add(key)
        if self._dump_count >= _MAX_DUMPS:
            self._write(f"!!! 已达 dump 上限（{_MAX_DUMPS} 份），忽略：{reason}")
            return
        self._dump_count += 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = log_dir() / f"window_diag_{stamp}_{self._dump_count:02d}.dump.txt"
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(f"窗口诊断 dump —— {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                handle.write(f"原因：{reason}\n")
                handle.write(f"进程：pid={self._pid}\n\n")
                handle.write("== 跟踪表（首次见到时登记的可视顶层窗口）==\n")
                if not self._hwnds:
                    handle.write("  (空)\n")
                for hwnd, label in self._hwnds.items():
                    cls, title = _window_info(int(hwnd))
                    handle.write(
                        f"  hwnd={hwnd} {label} | 存活={bool(_user32.IsWindow(hwnd))} "
                        f"{cls} {title!r}\n"
                    )
                handle.write("\n== 本进程当前全部顶层窗口（EnumWindows）==\n")
                handle.write(_enumerate_process_windows(self._pid) + "\n")
                handle.write(
                    f"\n== 最近 {len(self._ring)} 条事件（时间 = 开启诊断后的秒数）==\n"
                )
                for line in self._ring:
                    handle.write(line + "\n")
                handle.write(
                    "\n== 此刻的 Python 栈 ==\n"
                    "（事件回调发生在消息循环里，真正动手的调用已经返回；"
                    "定位靠上面的时序：DESTROY 前最后几条 qt.* / rounded.* / principle.* 记录）\n"
                )
                import faulthandler

                faulthandler.dump_traceback(file=handle, all_threads=True)
        except Exception as error:  # noqa: BLE001
            _logger.error("窗口诊断落盘失败：%s", error)
            return
        _logger.error("窗口诊断：%s —— 已落盘 %s", reason, path)
        self._write(f"!!! DUMP {reason} -> {path}")

    # ------------------------------------------------------------------ 清理
    def dispose(self) -> None:
        try:
            self._timer.stop()
        except Exception:  # noqa: BLE001
            pass
        app_filter = getattr(self, "_app_filter", None)
        if app_filter is not None:
            try:
                self._app.removeEventFilter(app_filter)
            except Exception:  # noqa: BLE001
                pass
            self._app_filter = None
        try:
            import faulthandler

            faulthandler.disable()
        except Exception:  # noqa: BLE001
            pass
        if getattr(self, "_fault_file", None) is not None:
            try:
                self._fault_file.close()
            except Exception:  # noqa: BLE001
                pass
            self._fault_file = None
        if self._hook:
            try:
                _user32.UnhookWinEvent(self._hook)
            except Exception:  # noqa: BLE001
                pass
            self._hook = None
        self._proc = None
        try:
            self._log_file.close()
        except Exception:  # noqa: BLE001
            pass
        _logger.info("窗口诊断已关闭")


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _call_site(depth: int = 3) -> str:
    """``文件名:行号 函数`` 链（由内向外），用于埋点。"""
    import traceback

    frames = traceback.extract_stack()[:-2]
    picked = frames[-depth:] if depth else frames[-3:]
    return " <- ".join(f"{frame.name}@{os.path.basename(frame.filename)}:{frame.lineno}" for frame in reversed(picked))


def _is_alive(widget) -> bool:
    try:
        import shiboken6

        return shiboken6.isValid(widget)
    except Exception:  # noqa: BLE001
        return True


def _window_info(hwnd: int) -> tuple[str, str]:
    """(类名, 标题)；窗口正在销毁的过程中也尽量取到。"""
    if _user32 is None:
        return "", ""
    cls = ctypes.create_unicode_buffer(256)
    title = ctypes.create_unicode_buffer(256)
    try:
        _user32.GetClassNameW(hwnd, cls, 256)
        _user32.GetWindowTextW(hwnd, title, 256)
    except Exception:  # noqa: BLE001
        pass
    return cls.value, title.value


def _enumerate_process_windows(pid: int) -> str:
    """枚举本进程的全部顶层窗口（含隐藏），一行一个。"""
    from ctypes import wintypes

    lines: list[str] = []

    def _cb(hwnd, _lparam):
        owner_pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value != pid:
            return True
        cls, title = _window_info(int(hwnd))
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        exstyle = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        owner = _user32.GetWindow(hwnd, _GW_OWNER)
        flags = []
        if exstyle & _WS_EX_LAYERED:
            flags.append("LAYERED")
        if exstyle & _WS_EX_TOOLWINDOW:
            flags.append("TOOL")
        lines.append(
            f"  hwnd={hwnd:>10} 可见={str(bool(_user32.IsWindowVisible(hwnd))):<5} "
            f"({rect.left},{rect.top},{rect.right - rect.left},{rect.bottom - rect.top}) "
            f"owner={owner} {'|'.join(flags) or '-'} {cls} | {title!r}"
        )
        return True

    procedure = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(_cb)
    _user32.EnumWindows(procedure, 0)
    return "\n".join(lines) if lines else "  (无)"
