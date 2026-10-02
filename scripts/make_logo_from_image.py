"""Section 2.0 logo 生成器（图像源版）。

以设计稿 `ChatGPT Image 2026年10月2日 22_24_38.png`（玻璃管道 S）为唯一来源：
    1. 去除画布黑底（边界连通的近黑区域置透明）；
    2. 量测 squircle 外轮廓（包围盒 + 对角切入率 → 拟合 superellipse 指数）；
    3. 重排到苹果图标网格：1024 画布、824 主体（四周留白 100），烘焙极淡投影；
    4. 逐级平滑降采样生成全套尺寸，打包 .icns / .ico。

用法（项目根目录）：
    .venv/bin/python scripts/make_logo_from_image.py            # 生成全套资源
    .venv/bin/python scripts/make_logo_from_image.py --preview  # 额外生成对比预览图

输出：
    src/app/resources/logo/logo_1024.png   1024 母版
    src/app/resources/logo/Section2.icns   macOS 图标
    src/app/resources/logo/section2.ico    Windows 图标（PyInstaller spec 用）
    src/app/resources/logo/icon_512.png    运行时窗口图标
    build/logo/preview.png                 新旧对比预览（--preview）
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
from collections import deque
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PNG = PROJECT_ROOT / "ChatGPT Image 2026年10月2日 22_24_38.png"
OUT_DIR = PROJECT_ROOT / "src" / "app" / "resources" / "logo"
BUILD_DIR = PROJECT_ROOT / "build" / "logo"
ICONSET_DIR = BUILD_DIR / "Section2.iconset"
ORIGINAL_PNG = PROJECT_ROOT / "section" / "section-master" / "section" / "Resources" / "170530 S.png"

CANVAS = 1024
ARTWORK = 824     # 苹果图标网格：1024 画布、824 主体（四周留白 100）
BG_THRESHOLD = 16  # 近黑判定：max(r,g,b) 低于该值视为画布底色

app = QApplication.instance() or QApplication(["make_logo_from_image"])


def _qimage(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    return img


def extract_artwork(src: QImage) -> tuple[QImage, float]:
    """从设计稿中提取 squircle 主体并返回 (带透明度的原图区域, 拟合的 superellipse n)。

    背景为纯黑画布：从四边做连通域洪泛填充找出背景；再按包围盒与对角切入率
    拟合 superellipse 指数，生成几何掩膜（AA 边缘）抠出主体。
    """
    w, h = src.width(), src.height()
    bits = src.constBits()
    stride = src.bytesPerLine()

    def near_black(x: int, y: int) -> bool:
        o = y * stride + x * 4
        return max(bits[o], bits[o + 1], bits[o + 2]) < BG_THRESHOLD

    # 洪泛填充：与画布边缘连通的近黑像素 = 背景
    bg = bytearray(w * h)
    queue = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near_black(x, y) and not bg[y * w + x]:
                bg[y * w + x] = 1
                queue.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if near_black(x, y) and not bg[y * w + x]:
                bg[y * w + x] = 1
                queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg[ny * w + nx] and near_black(nx, ny):
                bg[ny * w + nx] = 1
                queue.append((nx, ny))

    # 包围盒
    xs, ys = [], []
    for y in range(h):
        row = y * w
        for x in range(w):
            if not bg[row + x]:
                xs.append(x)
                ys.append(y)
                break
    for y in range(h - 1, -1, -1):
        row = y * w
        for x in range(w - 1, -1, -1):
            if not bg[row + x]:
                xs.append(x)
                ys.append(y)
                break
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    size = max(x1 - x0, y1 - y0) + 1

    # 角部内缩轮廓 → 最小二乘拟合 superellipse 指数（对 AA 边缘的 1px 偏差稳健）
    profile = []
    for dy in range(0, int(size * 0.18)):
        y = y0 + dy
        if y >= h:
            break
        row = y * w
        xf = next((x for x in range(w) if not bg[row + x]), None)
        if xf is not None:
            profile.append((dy, xf - x0))
    a = size / 2

    def inset_err(n: float) -> float:
        err = 0.0
        for dy, inset in profile:
            t = (a - dy) / a
            if t <= 0:
                continue
            model = a - a * max(0.0, 1.0 - t ** n) ** (1.0 / n)
            err += (model - inset) ** 2
        return err

    n, best = 5.0, None
    for cand in [2.0 + i * 0.05 for i in range(121)]:
        e = inset_err(cand)
        if best is None or e < best:
            best, n = e, cand
    n = min(max(n, 2.0), 8.0)

    # 几何掩膜抠图：以拟合的 superellipse 覆盖包围盒
    art = _qimage(size, size)
    shape = _superellipse_path(size, n)
    shape.translate(size / 2, size / 2)
    painter = QPainter(art)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    # 源图裁到包围盒后贴入（掩膜外为透明）
    painter.setClipPath(shape)
    painter.drawImage(QRectF(0, 0, size, size), src,
                      QRectF(x0, y0, size, size))
    painter.end()
    return art, n


def _superellipse_path(size: float, n: float) -> QPainterPath:
    """|x/a|^n + |y/a|^n = 1 闭合路径，边长 size、中心在原点。"""
    a = size / 2.0
    steps = 1440
    path = QPainterPath()
    for i in range(steps + 1):
        t = i / steps * 2 * math.pi
        c, s = abs(math.cos(t)), abs(math.sin(t))
        r = (c**n + s**n) ** (-1.0 / n)
        x, y = r * a * math.cos(t), r * a * math.sin(t)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def build_master(art: QImage, n: float = 5.0) -> QImage:
    """重排到 1024 苹果图标网格：824 主体居中 + 极淡烘焙投影。"""
    img = _qimage(CANVAS, CANVAS)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = _superellipse_path(ARTWORK, n)
    shape.translate(CANVAS / 2, CANVAS / 2)

    # 烘焙投影（与系统图标一致：极淡、向下小偏移）
    mask = _qimage(CANVAS, CANVAS)
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(0, 0, 0, 255))
    mp.drawPath(shape)
    mp.end()
    shadow = _blurred(mask, CANVAS * 0.045)
    p.setOpacity(0.22)
    p.drawImage(0, round(CANVAS * 0.014), shadow)
    p.setOpacity(1.0)

    # 主体（掩膜已含 AA 边缘，随图缩放）
    p.drawImage(QRectF(100, 100, ARTWORK, ARTWORK), art)
    p.end()
    return img


def _blurred(image: QImage, radius: float) -> QImage:
    from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    out = _qimage(image.width(), image.height())
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    scene.render(painter, QRectF(0, 0, image.width(), image.height()),
                 QRectF(0, 0, image.width(), image.height()))
    painter.end()
    return out


def stepped_scale(master: QImage, px: int) -> QImage:
    """逐级减半平滑降采样（1024→16 的大倍率缩放一次到位会有锯齿）。"""
    img = master
    while img.width() > px * 2:
        img = img.scaled(img.width() // 2, img.height() // 2,
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return img.scaled(px, px, Qt.AspectRatioMode.IgnoreAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def write_png(img: QImage, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


def png_bytes(img: QImage) -> bytes:
    from PySide6.QtCore import QBuffer

    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(images: list[tuple[int, int, bytes]], path: Path) -> None:
    """多尺寸 PNG-in-ICO 容器（Vista+ 标准，PyInstaller 可用）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    body = b""
    for w, h, data in images:
        body += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + body + b"".join(d for _, _, d in images))


def build_iconset(master: QImage) -> None:
    if ICONSET_DIR.exists():
        shutil.rmtree(ICONSET_DIR)
    ICONSET_DIR.mkdir(parents=True)
    specs = [
        ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
    ]
    for name, px in specs:
        img = master if px == 1024 else stepped_scale(master, px)
        write_png(img, ICONSET_DIR / name)
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(OUT_DIR / "Section2.icns")],
                   check=True)


def build_ico(master: QImage) -> None:
    entries = []
    for px in (16, 24, 32, 48, 64, 128, 256):
        entries.append((px, px, png_bytes(stepped_scale(master, px))))
    write_ico(entries, OUT_DIR / "section2.ico")


def build_preview(master: QImage, original: QImage) -> None:
    W, H = 1560, 880
    img = QImage(W, H, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    original_128 = original.scaled(128, 128, Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)

    def tile(src: QImage, cx: float, cy: float, px: int, label: str, dark: bool) -> None:
        p.drawImage(QRectF(cx - px / 2, cy - px / 2, px, px), src)
        p.setPen(QColor("#D0D0D2" if dark else "#3C3C43"))
        f = p.font()
        f.setPixelSize(14)
        p.setFont(f)
        p.drawText(QRectF(cx - 90, cy + px / 2 + 6, 180, 22),
                   Qt.AlignmentFlag.AlignCenter, label)

    def panel(x0: float, dark: bool) -> None:
        p.fillRect(QRectF(x0, 0, W / 2, H), QColor("#1E1E20") if dark else QColor("#F5F5F7"))
        cx = x0 + W / 4
        p.setPen(QColor("#EDEDEF" if dark else "#6D6D72"))
        f = p.font()
        f.setPixelSize(18)
        p.setFont(f)
        p.drawText(QRectF(x0, 22, W / 2, 30), Qt.AlignmentFlag.AlignCenter, "Section 2.0")
        tile(stepped_scale(master, 256), cx, 240, 256, "256px", dark)
        tile(stepped_scale(master, 128), cx - 190, 470, 128, "128px", dark)
        tile(stepped_scale(master, 64), cx - 40, 470, 64, "64px", dark)
        tile(stepped_scale(master, 32), cx + 70, 470, 32, "32px", dark)
        tile(stepped_scale(master, 16), cx + 155, 470, 16, "16px", dark)
        tile(original_128, cx, 730, 128, "1.0 原版", dark)

    panel(0, False)
    panel(W / 2, True)
    p.end()
    write_png(img, BUILD_DIR / "preview.png")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    src = QImage(str(SOURCE_PNG))
    if src.isNull():
        raise SystemExit(f"无法读取设计稿：{SOURCE_PNG}")
    art, n = extract_artwork(src)
    print(f"squircle 拟合：superellipse n = {n:.2f}")
    master = build_master(art, n)
    write_png(master, OUT_DIR / "logo_1024.png")
    build_iconset(master)
    build_ico(master)
    write_png(stepped_scale(master, 512), OUT_DIR / "icon_512.png")

    if "--preview" in sys.argv:
        build_preview(master, QImage(str(ORIGINAL_PNG)))
    print("done ->", OUT_DIR)


if __name__ == "__main__":
    main()
