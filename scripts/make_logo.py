"""Section 2.0 logo 生成器。

继承 1.0 logo（section/section-master/section/Resources/170530 S.png）的配色与版式基因：
    底色 Material Blue Grey 700 #455A64、白色居中主字形、正方形圆角构图。
2.0 造型按苹果现代 macOS 图标设计语言重绘（Big Sur → Tahoe 同一形状体系）：
    - 1024 画布上 824 的 superellipse(n=5) squircle（对系统图标实测拟合）；
    - 顶亮底深的纵向渐变 + 液态玻璃柔光/沿边反光/底部内阴影；
    - 主标记：Futura Bold 无衬线 "S" + 右下角同风格小 "2"（S2 = Section 2.0），
      整体向右下轻微挤出成 3D 层（前面白渐变、侧面深蓝灰），不再用衬线体；
    - 画布内烘焙极淡投影；≤64px 只保留 S 保证小尺寸识别度。

用法（项目根目录）：
    .venv/bin/python scripts/make_logo.py            # 生成全套资源
    .venv/bin/python scripts/make_logo.py --preview  # 额外生成新旧对比预览图

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
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTransform,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "src" / "app" / "resources" / "logo"
BUILD_DIR = PROJECT_ROOT / "build" / "logo"
ICONSET_DIR = BUILD_DIR / "Section2.iconset"
ORIGINAL_PNG = PROJECT_ROOT / "section" / "section-master" / "section" / "Resources" / "170530 S.png"
FUTURA_TTC = Path("/System/Library/Fonts/Supplemental/Futura.ttc")

#: 1.0 的身份色（Material Blue Grey 700）与其顶亮/底深衍生
BG_TOP = QColor("#5B7280")
BG_MID = QColor("#455A64")
BG_BOTTOM = QColor("#384A54")

CANVAS = 1024
ARTWORK = 824  # 苹果图标网格：1024 画布、824 主体（四周留白 100）
SQUIRCLE_N = 5  # superellipse 指数（对系统图标实测：对角切入点 6.9% ≈ 实测 7.0%）

#: 主标记版式
S_HEIGHT_FRAC = 0.473   # S 高 / 画布，沿用 1.0 比例
TWO_FRAC = 0.55         # "2" 高 = S 高 × 0.55
TWO_OVERLAP = 0.055     # "2" 与 S 的重叠量（× S 高）
UNIT_MAX_W = 0.42       # S+2 组合最大宽（× 画布），超限整体等比缩小
EXTRUDE_FRAC = 0.060    # 挤出深度（× S 高）
EXTRUDE_DIR = (0.30, 1.0)  # 挤出方向：向右下（光从左上来）
EXTRUDE_LAYERS = 12
SIDE_NEAR = QColor("#4A5E68")  # 挤出侧面近前脸色
SIDE_FAR = QColor("#1F2B33")   # 挤出侧面最深色
FRONT_TOP, FRONT_BOTTOM = "#FFFFFF", "#DFE8EC"      # S 前面
TWO_TOP, TWO_BOTTOM = "#F4F8FA", "#D5E1E7"          # "2" 前面（略暗，让 S 为主）
#: 小尺寸收缩边距（苹果小尺寸图标主体占比更大）
SMALL_MARGIN = {16: 0.039, 24: 0.047, 32: 0.055, 48: 0.066, 64: 0.075}

app = QApplication.instance() or QApplication(["make_logo"])


def squircle_path(size: float, n: int = SQUIRCLE_N) -> QPainterPath:
    """superellipse |x/a|^n + |y/a|^n = 1 的闭合路径，边长 size、中心在原点。"""
    a = size / 2.0
    steps = 720
    path = QPainterPath()
    for i in range(steps + 1):
        t = i / steps * 2 * math.pi
        r = (abs(math.cos(t)) ** n + abs(math.sin(t)) ** n) ** (-1.0 / n)
        x, y = r * a * math.cos(t), r * a * math.sin(t)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def _qimage(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    return img


def blurred(image: QImage, radius: float) -> QImage:
    """QGraphicsBlurEffect 高斯模糊。"""
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


def make_glyph(text: str, px_height: float, weight: QFont.Weight = QFont.Weight.Bold) -> QPainterPath:
    """Futura 无衬线字形，缩放到指定像素高、包围盒左上角在原点。"""
    font = QFont("Futura")
    font.setWeight(weight)
    raw = QPainterPath()
    raw.addText(0, 0, font, text)
    br = raw.boundingRect()
    scale = px_height / br.height()
    mapped = QTransform().scale(scale, scale).map(raw)
    mapped.translate(-mapped.boundingRect().left(), -mapped.boundingRect().top())
    return mapped


def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def mark_paths(size: int, *, small: bool) -> tuple[list[tuple[QPainterPath, str, str]], float, float]:
    """布局主标记，返回 [(路径, 前面顶色, 前面底色), ...] 与挤出偏移 (dx, dy)。

    small=True 时只保留 S（小尺寸下 "2" 会糊）。组合过宽时整体等比缩小。
    """
    s_px = size * S_HEIGHT_FRAC
    s_path = make_glyph("S", s_px)
    sb = s_path.boundingRect()
    entries: list[tuple[QPainterPath, str, str]] = [(s_path, FRONT_TOP, FRONT_BOTTOM)]
    if not small:
        h2 = s_px * TWO_FRAC
        two = make_glyph("2", h2)
        tb = two.boundingRect()
        two.translate(sb.right() - s_px * TWO_OVERLAP - tb.left(), sb.bottom() - tb.bottom())
        entries.append((two, TWO_TOP, TWO_BOTTOM))
    union = entries[0][0].boundingRect()
    for path, _, _ in entries[1:]:
        union = union.united(path.boundingRect())
    max_w = size * UNIT_MAX_W
    fit = min(1.0, max_w / union.width())

    ex_dx = s_px * EXTRUDE_FRAC * EXTRUDE_DIR[0]
    ex_dy = s_px * EXTRUDE_FRAC * EXTRUDE_DIR[1]
    transform = QTransform().scale(fit, fit)
    scaled = [(transform.map(path), top, bottom) for path, top, bottom in entries]
    union = scaled[0][0].boundingRect()
    for path, _, _ in scaled[1:]:
        union = union.united(path.boundingRect())
    # 前脸组合中心略向左上让出右下挤出体的量，整标视觉居中
    dx = size / 2 - ex_dx / 2 - union.center().x()
    dy = size / 2 - ex_dy / 2 - size * 0.004 - union.center().y()
    scaled = [(path.translated(dx, dy), top, bottom) for path, top, bottom in scaled]
    return scaled, ex_dx * fit, ex_dy * fit


def draw_logo(size: int, *, small: bool = False) -> QImage:
    """绘制一枚 logo。small=True 时收缩边距并去掉 "2"（苹果小尺寸规则）。"""
    margin_frac = SMALL_MARGIN.get(size, 0.0977) if small else 0.0977
    art = size * (1 - 2 * margin_frac)
    off = (size - art) / 2

    img = _qimage(size, size)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = squircle_path(art)
    shape.translate(off + art / 2, off + art / 2)

    # 1) 烘焙投影（与系统图标一致：极淡、向下小偏移）
    mask = _qimage(size, size)
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(0, 0, 0, 255))
    mp.drawPath(shape)
    mp.end()
    shadow = blurred(mask, max(2.0, size * 0.045))
    p.setOpacity(0.22)
    p.drawImage(0, max(1, round(size * 0.014)), shadow)
    p.setOpacity(1.0)

    # 2) squircle 底：顶亮底深纵向渐变，#455A64 为主
    p.setPen(Qt.PenStyle.NoPen)
    grad = QLinearGradient(0, off, 0, off + art)
    grad.setColorAt(0.0, BG_TOP)
    grad.setColorAt(0.45, BG_MID)
    grad.setColorAt(1.0, BG_BOTTOM)
    p.setBrush(grad)
    p.drawPath(shape)

    # 3) 液态玻璃质感：左上柔光 + 底部内阴影 + 沿边反光
    p.save()
    p.setClipPath(shape)
    sheen = QRadialGradient(off + art * 0.30, off + art * 0.06, art * 0.85)
    sheen.setColorAt(0.0, QColor(255, 255, 255, 34))
    sheen.setColorAt(0.55, QColor(255, 255, 255, 8))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(sheen)
    p.drawRect(QRectF(off, off, art, art))
    bottom = QLinearGradient(0, off + art * 0.90, 0, off + art)
    bottom.setColorAt(0.0, QColor(0, 0, 0, 0))
    bottom.setColorAt(1.0, QColor(0, 0, 0, 28))
    p.setBrush(bottom)
    p.drawRect(QRectF(off, off, art, art))
    rim = QLinearGradient(0, off, 0, off + art)
    rim.setColorAt(0.0, QColor(255, 255, 255, 64))
    rim.setColorAt(0.5, QColor(255, 255, 255, 6))
    rim.setColorAt(1.0, QColor(255, 255, 255, 18))
    pen = QPen()
    pen.setWidthF(max(1.5, size * 0.003))
    pen.setBrush(rim)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(shape)
    p.restore()

    # 4) 主标记：立体挤出 + 白色前面 + 悬浮投影
    marks, ex_dx, ex_dy = mark_paths(size, small=small)
    union = marks[0][0].boundingRect()
    for path, _, _ in marks[1:]:
        union = union.united(path.boundingRect())

    lift = _qimage(size, size)
    lp = QPainter(lift)
    lp.setRenderHint(QPainter.RenderHint.Antialiasing)
    lp.setPen(Qt.PenStyle.NoPen)
    lp.setBrush(QColor(16, 28, 34, 255))
    for path, _, _ in marks:
        lp.drawPath(path)
    lp.end()
    lift_blur = blurred(lift, max(1.5, size * 0.014))
    p.setOpacity(0.32)
    p.drawImage(0, max(1, round(size * 0.007)), lift_blur)
    p.setOpacity(1.0)

    p.setPen(Qt.PenStyle.NoPen)
    for i in range(EXTRUDE_LAYERS, 0, -1):
        t = i / EXTRUDE_LAYERS
        p.setBrush(lerp_color(SIDE_NEAR, SIDE_FAR, t))
        for path, _, _ in marks:
            p.save()
            p.translate(ex_dx * t, ex_dy * t)
            p.drawPath(path)
            p.restore()
    for path, top, bottom in marks:
        g = QLinearGradient(0, path.boundingRect().top(), 0, path.boundingRect().bottom())
        g.setColorAt(0.0, QColor(top))
        g.setColorAt(1.0, QColor(bottom))
        p.setBrush(g)
        p.drawPath(path)

    p.end()
    return img


def write_png(img: QImage, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


def png_bytes(img: QImage) -> bytes:
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
    """生成 iconset 并用 iconutil 打包 .icns。"""
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
        if px <= 64:
            img = draw_logo(px, small=True)
        else:
            img = master.scaled(px, px, Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        write_png(img, ICONSET_DIR / name)
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(OUT_DIR / "Section2.icns")],
                   check=True)


def build_ico(master: QImage) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    entries = []
    for px in sizes:
        img = (draw_logo(px, small=True) if px <= 32
               else master.scaled(px, px, Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))
        entries.append((px, px, png_bytes(img)))
    write_ico(entries, OUT_DIR / "section2.ico")


def build_preview(master: QImage, original: QImage) -> None:
    """新旧对比预览：亮/暗两种底色，各放 256/128/64/32/16 与 1.0 原版。"""
    W, H = 1560, 880
    img = QImage(W, H, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

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
        tile(master, cx, 240, 256, "256px", dark)
        tile(master, cx - 190, 470, 128, "128px", dark)
        tile(master, cx - 40, 470, 64, "64px", dark)
        tile(master, cx + 70, 470, 32, "32px", dark)
        tile(master, cx + 155, 470, 16, "16px", dark)
        tile(original, cx, 730, 128, "1.0 原版", dark)

    panel(0, False)
    panel(W / 2, True)
    p.end()
    write_png(img, BUILD_DIR / "preview.png")


def main() -> None:
    QFontDatabase.addApplicationFont(str(FUTURA_TTC))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    master = draw_logo(CANVAS)
    write_png(master, OUT_DIR / "logo_1024.png")
    build_iconset(master)
    build_ico(master)
    write_png(master.scaled(512, 512, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation),
              OUT_DIR / "icon_512.png")

    if "--preview" in sys.argv:
        original = QImage(str(ORIGINAL_PNG))
        build_preview(master, original)
    print("done ->", OUT_DIR)


if __name__ == "__main__":
    main()
