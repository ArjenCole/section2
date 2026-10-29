"""原生崩溃黑匣子（Windows）：未处理异常 → minidump + 文本报告。

背景（2026-10-27 09:56 现场）：``python.exe`` 在 ``Qt6Core.dll`` 内以
``0xc0000409``（fast-fail）终止。``sys.excepthook`` 只接 Python 异常，
``faulthandler`` 也只覆盖它注册的几种信号，这类 Qt/C++ 层崩溃两条路都留不下
现场。本模块用 ``SetUnhandledExceptionFilter`` 挂一个进程级兜底：

* 写 ``logs/crash_<时间>_<pid>.txt``：异常代码 / 地址 / 故障模块+偏移 /
  异常参数 / Python 线程栈；
* 写 ``logs/crash_<时间>_<pid>.dmp``：``MiniDumpWriteDump`` 生成的 minidump，
  可用 WinDbg / Visual Studio 打开看原生调用栈。

局限：``__fastfail``（含 ``0xc0000409``）按设计不可被 SEH/VEH 拦截，仍可能只由
WER 处理；访问冲突（``0xc0000005``）、C++ 异常等绝大多数崩溃都能留下 dump。
另外 ``faulthandler`` 在这里统一开启，写 ``logs/faulthandler.log``。

用法（``app.main`` 已自动调用）::

    from app.core.native_crash import install
    install()
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from app.core.paths import log_dir

_logger = logging.getLogger("section2.native_crash")

try:  # 崩溃回调里只做最少的 import
    import faulthandler as _faulthandler
except Exception:  # pragma: no cover - 极少数精简发行版没有 faulthandler
    _faulthandler = None

_INSTALLED = False
_FILTER = None
_KERNEL32 = None
_DBGHELP = None
_FAULT_FILE = None
_LOG_DIR: Path | None = None
_PID = os.getpid()
_ENV: dict[str, str] = {}
_WRITING = False

#: 崩溃时最多保留几个异常参数（EXCEPTION_MAXIMUM_PARAMETERS）
_MAX_EXCEPTION_PARAMS = 15

#: MiniDump 内容：句柄、卸载模块、间接引用内存、进程/线程数据、内存信息、线程信息、模块头。
#: 不含 FullMemory，避免动辄几百 MB；排障所需的栈、线程、模块信息已经齐全。
_MINI_DUMP_TYPE = (
    0x00000004  # MiniDumpWithHandleData
    | 0x00000020  # MiniDumpWithUnloadedModules
    | 0x00000080  # MiniDumpWithIndirectlyReferencedMemory
    | 0x00000100  # MiniDumpWithProcessThreadData
    | 0x00000800  # MiniDumpWithFullMemoryInfo
    | 0x00001000  # MiniDumpWithThreadInfo
    | 0x00080000  # MiniDumpWithModuleHeaders
)

_EXCEPTION_CONTINUE_SEARCH = 1

_GENERIC_WRITE = 0x40000000
_CREATE_ALWAYS = 2
_FILE_ATTRIBUTE_NORMAL = 0x80
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS = 0x00000004
_GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT = 0x00000002


if sys.platform == "win32":  # pragma: no cover - 平台相关
    from ctypes import wintypes

    _ULONG_PTR = ctypes.c_size_t

    class _EXCEPTION_RECORD(ctypes.Structure):
        _fields_ = [
            ("ExceptionCode", wintypes.DWORD),
            ("ExceptionFlags", wintypes.DWORD),
            ("ExceptionRecord", ctypes.c_void_p),
            ("ExceptionAddress", ctypes.c_void_p),
            ("NumberParameters", wintypes.DWORD),
            ("ExceptionInformation", _ULONG_PTR * _MAX_EXCEPTION_PARAMS),
        ]

    class _EXCEPTION_POINTERS(ctypes.Structure):
        _fields_ = [
            ("ExceptionRecord", ctypes.POINTER(_EXCEPTION_RECORD)),
            ("ContextRecord", ctypes.c_void_p),
        ]

    class _MINIDUMP_EXCEPTION_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("ThreadId", wintypes.DWORD),
            ("ExceptionPointers", ctypes.POINTER(_EXCEPTION_POINTERS)),
            ("ClientPointers", wintypes.BOOL),
        ]

    _TOP_LEVEL_EXCEPTION_FILTER = ctypes.WINFUNCTYPE(
        wintypes.LONG, ctypes.POINTER(_EXCEPTION_POINTERS)
    )
else:  # pragma: no cover - 非 Windows 只保证 import 不炸
    _TOP_LEVEL_EXCEPTION_FILTER = None
    _EXCEPTION_POINTERS = None


def install() -> bool:
    """安装原生崩溃兜底（Windows）。可重复调用；非 Windows 返回 False。"""
    global _INSTALLED, _FILTER, _LOG_DIR

    if sys.platform != "win32":
        return False
    if _INSTALLED:
        return True
    try:
        _init_win32()
    except Exception as error:  # noqa: BLE001 - 兜底装不上不能拖垮启动
        _logger.warning("原生崩溃兜底安装失败：%s", error)
        return False

    try:
        _LOG_DIR = log_dir()
    except Exception:  # noqa: BLE001
        _LOG_DIR = None
    _capture_env()
    _enable_faulthandler()
    _FILTER = _TOP_LEVEL_EXCEPTION_FILTER(_on_unhandled_exception)
    _KERNEL32.SetUnhandledExceptionFilter(_FILTER)
    _INSTALLED = True
    _logger.info("原生崩溃兜底已开启：%s", _LOG_DIR)
    return True


def uninstall() -> None:
    """卸载兜底（主要给测试/嵌入场景用；正常进程不需要）。"""
    global _INSTALLED, _FILTER
    if sys.platform == "win32" and _KERNEL32 is not None:
        try:
            _KERNEL32.SetUnhandledExceptionFilter(None)
        except Exception:  # noqa: BLE001
            pass
    _FILTER = None
    _INSTALLED = False


# --------------------------------------------------------------------------- #
# Win32 绑定
# --------------------------------------------------------------------------- #
def _init_win32() -> None:  # pragma: no cover - 平台相关
    global _KERNEL32, _DBGHELP

    if _KERNEL32 is not None and _DBGHELP is not None:
        return
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.SetUnhandledExceptionFilter.argtypes = [_TOP_LEVEL_EXCEPTION_FILTER]
    kernel32.SetUnhandledExceptionFilter.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetModuleHandleExW.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.HMODULE),
    ]
    kernel32.GetModuleHandleExW.restype = wintypes.BOOL
    kernel32.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel32.GetModuleFileNameW.restype = wintypes.DWORD

    dbghelp = ctypes.WinDLL("dbghelp", use_last_error=True)
    dbghelp.MiniDumpWriteDump.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(_MINIDUMP_EXCEPTION_INFORMATION),
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    dbghelp.MiniDumpWriteDump.restype = wintypes.BOOL

    _KERNEL32 = kernel32
    _DBGHELP = dbghelp


def _capture_env() -> None:
    """启动时快照环境，崩溃回调里不再 import / 读文件。"""
    global _ENV
    _ENV = {
        "python": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "platform": sys.platform,
        "pid": str(_PID),
    }
    try:
        import PySide6

        _ENV["pyside6"] = getattr(PySide6, "__version__", "?")
        from PySide6.QtCore import qVersion

        _ENV["qt"] = qVersion()
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.core.version import APP_DISPLAY_NAME, APP_VERSION

        _ENV["app"] = f"{APP_DISPLAY_NAME} {APP_VERSION}"
    except Exception:  # noqa: BLE001
        pass


def _enable_faulthandler() -> None:
    global _FAULT_FILE
    if _faulthandler is None or _faulthandler.is_enabled():
        return
    try:
        directory = _LOG_DIR or log_dir()
        _FAULT_FILE = open(directory / "faulthandler.log", "a", encoding="utf-8")
        _faulthandler.enable(_FAULT_FILE)
    except Exception as error:  # noqa: BLE001
        _logger.warning("faulthandler 开启失败：%s", error)


# --------------------------------------------------------------------------- #
# 崩溃回调
# --------------------------------------------------------------------------- #
def _on_unhandled_exception(exception_pointers):  # pragma: no cover - 只在真崩时执行
    global _WRITING

    if _WRITING:
        return _EXCEPTION_CONTINUE_SEARCH
    _WRITING = True
    try:
        record = exception_pointers.contents.ExceptionRecord
        if record:
            code = int(record.contents.ExceptionCode)
            flags = int(record.contents.ExceptionFlags)
            address = int(record.contents.ExceptionAddress or 0)
            count = min(int(record.contents.NumberParameters), _MAX_EXCEPTION_PARAMS)
            params = [int(record.contents.ExceptionInformation[index]) for index in range(count)]
        else:  # pragma: no cover - 理论上不会发生
            code = flags = address = 0
            params = []

        thread_id = int(_KERNEL32.GetCurrentThreadId())
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        directory = _LOG_DIR or log_dir()
        base = directory / f"crash_{stamp}_{_PID}"
        info = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "pid": _PID,
            "tid": thread_id,
            "code": code,
            "flags": flags,
            "address": address,
            "params": params,
            "module": _faulting_module(address),
            "env": dict(_ENV),
        }
        _write_text_report(base.with_suffix(".txt"), info)
        _write_minidump(base.with_suffix(".dmp"), exception_pointers, thread_id)
        _logger.error("原生崩溃已落盘：%s", base)
    except Exception as error:  # noqa: BLE001 - 兜底回调本身不能再抛
        try:
            _logger.error("原生崩溃落盘失败：%s", error)
        except Exception:  # noqa: BLE001
            pass
    finally:
        _WRITING = False
    return _EXCEPTION_CONTINUE_SEARCH


def _faulting_module(address: int) -> str:  # pragma: no cover - 平台相关
    """异常地址所属模块与偏移（如 ``...\\Qt6Core.dll (+0x1C8D8)``）。"""
    if not address or _KERNEL32 is None:
        return ""
    try:
        from ctypes import wintypes

        module = wintypes.HMODULE()
        flags = (
            _GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
            | _GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT
        )
        if not _KERNEL32.GetModuleHandleExW(flags, ctypes.c_void_p(address), ctypes.byref(module)):
            return ""
        buffer = ctypes.create_unicode_buffer(1024)
        _KERNEL32.GetModuleFileNameW(module, buffer, 1024)
        base = int(module.value or 0)
        offset = address - base if base else 0
        path = buffer.value
        return f"{path} (+0x{offset:X})" if path else f"base=0x{base:X} offset=0x{offset:X}"
    except Exception:  # noqa: BLE001
        return ""


def _write_text_report(path: Path, info: dict) -> None:  # pragma: no cover - 崩溃路径
    params = ", ".join(f"0x{value:X}" for value in info["params"]) or "无"
    lines = [
        "Section 2.0 原生崩溃报告",
        f"时间：{info['time']}",
        f"进程：pid={info['pid']} tid={info['tid']}",
        f"异常代码：0x{info['code']:08X}  标志：0x{info['flags']:08X}",
        f"异常地址：0x{info['address']:X}",
        f"故障模块：{info['module'] or '未知'}",
        f"异常参数：{params}",
        "",
        "== 环境 ==",
    ]
    lines.extend(f"{key}: {value}" for key, value in info["env"].items())
    lines.extend(["", "== Python 线程栈（faulthandler）=="])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            if _faulthandler is not None:
                _faulthandler.dump_traceback(file=handle, all_threads=True)
            else:  # pragma: no cover
                handle.write("（faulthandler 不可用）\n")
    except Exception as error:  # noqa: BLE001
        _logger.warning("写原生崩溃文本失败：%s", error)


def _write_minidump(path: Path, exception_pointers, thread_id: int) -> None:  # pragma: no cover
    if _KERNEL32 is None or _DBGHELP is None:
        return
    handle = _INVALID_HANDLE_VALUE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = _KERNEL32.CreateFileW(
            str(path),
            _GENERIC_WRITE,
            0,
            None,
            _CREATE_ALWAYS,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle in (None, _INVALID_HANDLE_VALUE):
            _logger.warning("创建 minidump 文件失败：%s", path)
            return
        information = _MINIDUMP_EXCEPTION_INFORMATION()
        information.ThreadId = thread_id
        information.ExceptionPointers = exception_pointers
        information.ClientPointers = False
        ok = _DBGHELP.MiniDumpWriteDump(
            _KERNEL32.GetCurrentProcess(),
            _PID,
            handle,
            _MINI_DUMP_TYPE,
            ctypes.byref(information),
            None,
            None,
        )
        if not ok:
            # 异常上下文不可用（或已损坏）时退回普通进程 dump：
            # 至少保留线程栈、模块和内存信息，仍然比没有强。
            first_error = ctypes.get_last_error()
            # 第一次失败可能已经写了半截；关掉重新 CREATE_ALWAYS 截断，
            # 避免在残留数据后面追加出损坏的 dump。
            try:
                _KERNEL32.CloseHandle(handle)
            except Exception:  # noqa: BLE001
                pass
            handle = _INVALID_HANDLE_VALUE
            handle = _KERNEL32.CreateFileW(
                str(path),
                _GENERIC_WRITE,
                0,
                None,
                _CREATE_ALWAYS,
                _FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if handle in (None, _INVALID_HANDLE_VALUE):
                _logger.warning("重新创建 minidump 文件失败：%s", path)
                return
            ok = _DBGHELP.MiniDumpWriteDump(
                _KERNEL32.GetCurrentProcess(),
                _PID,
                handle,
                _MINI_DUMP_TYPE,
                None,
                None,
                None,
            )
            if not ok:
                _logger.warning(
                    "MiniDumpWriteDump 失败：error=%s（退回普通 dump 也失败：%s）path=%s",
                    first_error,
                    ctypes.get_last_error(),
                    path,
                )
    except Exception as error:  # noqa: BLE001
        _logger.warning("写 minidump 失败：%s", error)
    finally:
        if handle not in (None, _INVALID_HANDLE_VALUE):
            try:
                _KERNEL32.CloseHandle(handle)
            except Exception:  # noqa: BLE001
                pass
