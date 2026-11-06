# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建（在项目根目录、项目 .venv 里执行）：

    .venv\\Scripts\\pyinstaller section2.spec --noconfirm

或直接用发布脚本（自动生成带日期的 zip）：

    .venv\\Scripts\\python scripts\\make_release.py

产物：dist\\Section2\\Section2.exe（目录模式，随目录分发 app/resources）。

版本号单一来源是 src/app/core/version.py 的 APP_VERSION，本文件在构建时
执行该模块取版本（显示版本 + 四段数字版本），并生成 Windows 版本资源
（EXE 属性 → 详细信息里可见）。
"""

from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

_ROOT = Path(SPECPATH)


def _load_version_module() -> dict:
    """执行 version.py（纯常量模块，不依赖 app 包）取版本号，避免两处手改。"""
    path = _ROOT / "src" / "app" / "core" / "version.py"
    namespace: dict = {}
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
    except Exception as exc:  # noqa: BLE001 - 构建期直接失败并说清原因
        raise SystemExit(f"无法读取 {path} 中的版本号：{exc}") from exc
    return namespace


def _quad(header_version: str) -> tuple[int, int, int, int]:
    """'2.0.0.1' → (2, 0, 0, 1)。Windows 文件版本必须是四段数字。"""
    parts = [int(part) for part in header_version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return parts[0], parts[1], parts[2], parts[3]


def _version_info(version: str, header_version: str) -> VSVersionInfo:
    """EXE 属性里显示的版本资源（不落盘，直接交给 PyInstaller）。"""
    quad = _quad(header_version)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=quad,
            prodvers=quad,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "080404b0",  # 简体中文 + Unicode
                        [
                            StringStruct("CompanyName", "Section"),
                            StringStruct("FileDescription", "Section 2.0 线性工程工程量计算软件"),
                            StringStruct("FileVersion", version),
                            StringStruct("InternalName", "Section2"),
                            StringStruct("OriginalFilename", "Section2.exe"),
                            StringStruct("ProductName", "Section 2.0"),
                            StringStruct("ProductVersion", version),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [2052, 1200])]),
        ],
    )


_VERSION_NS = _load_version_module()
#: 显示版本（2.0.0-alpha.1）与四段数字版本（2.0.0.1）都取自 version.py
_VERSION = _VERSION_NS["APP_VERSION"]
_HEADER_VERSION = _VERSION_NS["STN_HEADER_VERSION"]

a = Analysis(
    ["src\\app\\main.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src\\app\\resources", "app\\resources")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Section2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="src\\app\\resources\\logo\\section2.ico",
    version=_version_info(_VERSION, _HEADER_VERSION),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Section2",
)
