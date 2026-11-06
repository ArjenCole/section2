"""打内测/正式发布包：PyInstaller 构建 + 版本校验 + 带日期 zip。

用法（在项目根目录、项目 .venv 里执行）::

    .venv\\Scripts\\python scripts\\make_release.py                # 完整构建并打包
    .venv\\Scripts\\python scripts\\make_release.py --dry-run      # 只校验版本号，不构建
    .venv\\Scripts\\python scripts\\make_release.py --skip-build   # 复用 dist\\Section2，只打包

版本号唯一来源是 ``src/app/core/version.py`` 的 ``APP_VERSION``；``pyproject.toml``
里的 version 必须与之等价（PEP 440 归一化后比较），否则脚本直接报错退出。

产物：``dist\\Section2_<版本>_<日期>.zip``，解压后是 ``Section2\\`` 目录。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP_DIR = DIST / "Section2"
VERSION_PY = ROOT / "src" / "app" / "core" / "version.py"
PYPROJECT = ROOT / "pyproject.toml"


def fail(message: str) -> None:
    print(f"[错误] {message}", file=sys.stderr)
    raise SystemExit(1)


def read_version_module() -> dict:
    """执行 version.py（纯常量模块，不依赖 app 包）取版本号。"""
    namespace: dict = {}
    try:
        exec(compile(VERSION_PY.read_text(encoding="utf-8"), str(VERSION_PY), "exec"), namespace)
    except Exception as exc:  # noqa: BLE001 - 打包脚本直接报错退出
        fail(f"无法读取 {VERSION_PY} 中的版本号：{exc}")
    return namespace


def read_pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        fail(f"无法从 {PYPROJECT} 读取 version")
    return match.group(1)


def normalize(version: str) -> str:
    """按 PEP 440 归一化后比较（2.0.0-alpha.1 与 2.0.0a1 视为同一版本）。"""
    try:
        from packaging.version import Version
    except ImportError:  # pragma: no cover - packaging 随 setuptools 安装
        return version
    return str(Version(version))


def check_versions(version: str, header_version: str) -> None:
    pyproject_version = read_pyproject_version()
    if normalize(version) != normalize(pyproject_version):
        fail(
            "版本号不一致：\n"
            f"  src/app/core/version.py  APP_VERSION = {version!r}\n"
            f"  pyproject.toml           version     = {pyproject_version!r}\n"
            "请先把两处改成同一个版本再打包。"
        )
    parts = header_version.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        fail(f"四段数字版本号不合法：{header_version!r}（应形如 2.0.0.1）")
    print(f"[版本] 显示 {version} | EXE 与 .stn 头 {header_version}")


def check_git_clean() -> None:
    """发布包应来自已提交的代码，否则同事报的问题对不上任何提交。"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return  # 没有 git 就跳过
    if result.returncode != 0:
        return
    if result.stdout.strip():
        print("[提醒] 工作区有未提交的改动，建议先提交并打 tag 再打包。")


def build() -> None:
    print("[构建] pyinstaller section2.spec --noconfirm")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "section2.spec", "--noconfirm"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        fail(f"PyInstaller 构建失败（退出码 {result.returncode}）")


def make_zip(version: str) -> Path:
    if not APP_DIR.is_dir():
        fail(f"找不到构建产物目录：{APP_DIR}")
    exe = APP_DIR / "Section2.exe"
    if not exe.is_file():
        fail(f"找不到可执行文件：{exe}")

    stamp = date.today().strftime("%Y%m%d")
    target = DIST / f"Section2_{version}_{stamp}.zip"
    if target.exists():
        target.unlink()

    print(f"[打包] {target.name}")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(APP_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, Path("Section2") / path.relative_to(APP_DIR))
    return target


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打 Section2 发布包")
    parser.add_argument("--dry-run", action="store_true", help="只校验版本号，不构建也不打包")
    parser.add_argument("--skip-build", action="store_true", help="复用 dist\\Section2，只打 zip")
    parser.add_argument("--no-zip", action="store_true", help="只构建，不生成 zip")
    args = parser.parse_args(argv)

    version_module = read_version_module()
    version = version_module["APP_VERSION"]
    header_version = version_module["STN_HEADER_VERSION"]
    check_versions(version, header_version)
    check_git_clean()

    if args.dry_run:
        print("[dry-run] 版本号校验通过，未构建、未打包。")
        return 0

    if not args.skip_build:
        build()

    if args.no_zip:
        print(f"[完成] 构建产物：{APP_DIR}")
        return 0

    target = make_zip(version)
    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"[完成] {target}")
    print(f"       版本 {version}（EXE 属性里显示 {header_version}）")
    print(f"       大小 {size_mb:.1f} MB")
    print(f"       SHA256 {sha256(target)}")
    print("       分发时建议一并告知版本号与 SHA256，便于同事核对包是否完整。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
