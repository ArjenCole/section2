# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

构建（在项目根目录、项目 .venv 里执行）：

    .venv\\Scripts\\pyinstaller section2.spec --noconfirm

产物：dist\\Section2\\Section2.exe（目录模式，随目录分发 app/resources）。
"""

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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Section2",
)
