"""Section 2.0 logo 生成器。

继承 1.0 logo（section/section-master/section/Resources/170530 S.png）的配色与版式基因：
    底色 Material Blue Grey 700 #455A64、白色居中主字形、正方形圆角构图。
2.0 造型按苹果现代 macOS 图标设计语言重绘（Big Sur → Tahoe 同一形状体系）：
    - 1024 画布上 824 的 superellipse(n=5) squircle（对系统图标实测拟合）；
    - 明显的液态玻璃光感：左上柔光 + 顶部受光带 + 沿边反光 + 底部内阴影；
    - 主标记：Futura Bold 无衬线 "S"（不用衬线体），字面本身做鼓起光影——
      左上穹面高光、上内缘裹光、下内缘形体阴影，配合向右下轻微挤出成 3D 层；
    - 全流程超采样渲染（大画布绘制后平滑降采样），边缘无锯齿；
    - 画布内烘焙极淡投影；≤64px 收缩边距保证小尺寸识别度。

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
BG_TOP = QColor("#61798A")
BG_MID = QColor("#455A64")
BG_BOTTOM = QColor("#344450")

CANVAS = 1024
ARTWORK = 824  # 苹果图标网格：1024 画布、824 主体（四周留白 100）
SQUIRCLE_N = 5  # superellipse 指数（对系统图标实测：对角切入点 6.9% ≈ 实测 7.0%）

#: 主标记版式（S 单字母）
S_HEIGHT_FRAC = 0.473   # S 高 / 画布，沿用 1.0 比例
EXTRUDE_FRAC = 0.052    # 挤出深度（× S 高）
EXTRUDE_DIR = (0.30, 1.0)  # 挤出方向：向右下（光从左上来）
EXTRUDE_LAYERS = 18
SIDE_NEAR = QColor("#4A5E68")  # 挤出侧面近前脸色
SIDE_FAR = QColor("#1F2B33")   # 挤出侧面最深色
FRONT_TOP, FRONT_BOTTOM = "#FFFFFF", "#DEE7EC"  # S 前面基础渐变
#: 鼓起光影
DOME_ALPHA = 105        # 左上穹面高光峰值
RIMLIGHT_ALPHA = 120    # 上内缘裹光峰值
INSHADOW_ALPHA = 120    # 下内缘形体阴影峰值
#: 小尺寸收缩边距（苹果小尺寸图标主体占比更大）
SMALL_MARGIN = {16: 0.039, 24: 0.047, 32: 0.055, 48: 0.066, 64: 0.075}
#: 超采样倍率（边缘抗锯齿的关键：大画布绘制后平滑降采样）
SS = {16: 6, 24: 6, 32: 5, 48: 4, 64: 4, 128: 3, 256: 3, 512: 2, 1024: 2}

app = QApplication.instance() or QApplication(["make_logo"])
_font_ready = False


def _ensure_font() -> None:
    global _font_ready
    if not _font_ready:
        QFontDatabase.addApplicationFont(str(FUTURA_TTC))
        _font_ready = True


def squircle_path(size: float, n: int = SQUIRCLE_N) -> QPainterPath:
    """superellipse |x/a|^n + |y/a|^n = 1 的闭合路径，边长 size、中心在原点。"""
    a = size / 2.0
    steps = 1440
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


def make_glyph(text: str, px_height: float) -> QPainterPath:
    """Futura Bold 无衬线字形，缩放到指定像素高、包围盒左上角在原点。"""
    font = QFont("Futura")
    font.setWeight(QFont.Weight.Bold)
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


def _inner_edge(mask: QImage, dx: float, dy: float) -> QImage:
    """字形内缘条带：mask 减去平移 (dx, dy) 后的 mask，剩下的内缘月牙。"""
    sliver = _qimage(mask.width(), mask.height())
    p = QPainter(sliver)
    p.drawImage(0, 0, mask)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    p.drawImage(int(round(dx)), int(round(dy)), mask)
    p.end()
    return sliver


def draw_mark(p: QPainter, size: int, *, small: bool) -> None:
    """在已铺好玻璃底的画布上绘制主标记（含挤出与鼓起光影）。"""
    s_px = size * S_HEIGHT_FRAC
    glyph = make_glyph("S", s_px)
    gb = glyph.boundingRect()
    ex_dx = s_px * EXTRUDE_FRAC * EXTRUDE_DIR[0]
    ex_dy = s_px * EXTRUDE_FRAC * EXTRUDE_DIR[1]
    # 前脸中心略向左上让出右下挤出体的量，整标视觉居中
    glyph.translate(size / 2 - ex_dx / 2 - gb.center().x(),
                    size / 2 - ex_dy / 2 - size * 0.004 - gb.center().y())
    gb = glyph.boundingRect()

    # 悬浮投影：更柔、更远，避免暗晕贴住字形边缘
    lift = _qimage(size, size)
    lp = QPainter(lift)
    lp.setRenderHint(QPainter.RenderHint.Antialiasing)
    lp.setPen(Qt.PenStyle.NoPen)
    lp.setBrush(QColor(16, 28, 34, 255))
    lp.drawPath(glyph)
    lp.end()
    lift_blur = blurred(lift, max(1.5, size * 0.020))
    p.setOpacity(0.26)
    p.drawImage(0, max(1, round(size * 0.013)), lift_blur)
    p.setOpacity(1.0)

    # 挤出侧面：多层渐变模拟实体厚度
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(EXTRUDE_LAYERS, 0, -1):
        t = i / EXTRUDE_LAYERS
        p.setBrush(lerp_color(SIDE_NEAR, SIDE_FAR, t))
        p.save()
        p.translate(ex_dx * t, ex_dy * t)
        p.drawPath(glyph)
        p.restore()

    # 前面基础渐变
    base = QLinearGradient(0, gb.top(), 0, gb.bottom())
    base.setColorAt(0.0, QColor(FRONT_TOP))
    base.setColorAt(1.0, QColor(FRONT_BOTTOM))
    p.setBrush(base)
    p.drawPath(glyph)

    # 鼓起光影（全部裁剪在字面内）
    p.save()
    p.setClipPath(glyph)

    # 1) 左上穹面高光：字面像充气鼓起的弧面
    dome = QRadialGradient(gb.left() + gb.width() * 0.34, gb.top() + gb.height() * 0.16,
                           gb.height() * 0.85)
    dome.setColorAt(0.0, QColor(255, 255, 255, DOME_ALPHA))
    dome.setColorAt(0.45, QColor(255, 255, 255, DOME_ALPHA // 3))
    dome.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(dome)
    p.drawRect(gb)

    # 2) 上内缘裹光：光绕过肩部在内缘留下一线亮
    mask = _qimage(size, size)
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(255, 255, 255, 255))
    mp.drawPath(glyph)
    mp.end()
    d1 = max(2, round(s_px * 0.030))
    rim_inner = blurred(_inner_edge(mask, d1, d1), d1 * 1.4)
    p.setOpacity(RIMLIGHT_ALPHA / 255)
    p.drawImage(0, 0, rim_inner)
    p.setOpacity(1.0)

    # 3) 下内缘形体阴影：内缘向下渐沉，强调体积
    d2 = max(2, round(s_px * 0.052))
    body_shadow = blurred(_inner_edge(mask, -d2, -d2), d2 * 1.2)
    tinted = _qimage(size, size)
    tp = QPainter(tinted)
    tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    sh = QLinearGradient(0, gb.top() + gb.height() * 0.45, 0, gb.bottom())
    sh.setColorAt(0.0, QColor(46, 63, 74, 0))
    sh.setColorAt(1.0, QColor(46, 63, 74, INSHADOW_ALPHA))
    tp.fillRect(QRectF(0, 0, size, size), sh)
    tp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    tp.drawImage(0, 0, body_shadow)
    tp.end()
    p.drawImage(0, 0, tinted)

    p.restore()


def draw_logo(size: int, *, small: bool = False) -> QImage:
    """绘制一枚 logo。small=True 时收缩边距（苹果小尺寸规则）。

    内部按 SS 倍超采样绘制后平滑降采样到目标尺寸，保证边缘光滑。
    """
    ss = SS.get(size, 2)
    big = size * ss
    margin_frac = SMALL_MARGIN.get(size, 0.0977) if small else 0.0977
    art = big * (1 - 2 * margin_frac)
    off = (big - art) / 2

    img = _qimage(big, big)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = squircle_path(art)
    shape.translate(off + art / 2, off + art / 2)

    # 1) 烘焙投影（与系统图标一致：极淡、向下小偏移）
    mask = _qimage(big, big)
    mp = QPainter(mask)
    mp.setRenderHint(QPainter.RenderHint.Antialiasing)
    mp.setPen(Qt.PenStyle.NoPen)
    mp.setBrush(QColor(0, 0, 0, 255))
    mp.drawPath(shape)
    mp.end()
    shadow = blurred(mask, max(2.0, big * 0.045))
    p.setOpacity(0.22)
    p.drawImage(0, max(1, round(big * 0.014)), shadow)
    p.setOpacity(1.0)

    # 2) squircle 底：顶亮底深纵向渐变，#455A64 为主
    p.setPen(Qt.PenStyle.NoPen)
    grad = QLinearGradient(0, off, 0, off + art)
    grad.setColorAt(0.0, BG_TOP)
    grad.setColorAt(0.45, BG_MID)
    grad.setColorAt(1.0, BG_BOTTOM)
    p.setBrush(grad)
    p.drawPath(shape)

    # 3) 液态玻璃质感：左上柔光 + 顶部受光带 + 底部内阴影 + 沿边反光
    p.save()
    p.setClipPath(shape)
    sheen = QRadialGradient(off + art * 0.28, off + art * 0.05, art * 0.95)
    sheen.setColorAt(0.0, QColor(255, 255, 255, 72))
    sheen.setColorAt(0.5, QColor(255, 255, 255, 22))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(sheen)
    p.drawRect(QRectF(off, off, art, art))
    band = QLinearGradient(0, off, 0, off + art * 0.20)
    band.setColorAt(0.0, QColor(255, 255, 255, 58))
    band.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(band)
    p.drawRect(QRectF(off, off, art, art * 0.20))
    bottom = QLinearGradient(0, off + art * 0.86, 0, off + art)
    bottom.setColorAt(0.0, QColor(0, 0, 0, 0))
    bottom.setColorAt(1.0, QColor(8, 16, 20, 52))
    p.setBrush(bottom)
    p.drawRect(QRectF(off, off, art, art))
    rim = QLinearGradient(0, off, 0, off + art)
    rim.setColorAt(0.0, QColor(255, 255, 255, 125))
    rim.setColorAt(0.5, QColor(255, 255, 255, 10))
    rim.setColorAt(1.0, QColor(255, 255, 255, 34))
    pen = QPen()
    pen.setWidthF(max(1.5, big * 0.004))
    pen.setBrush(rim)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(shape)
    p.restore()

    # 4) 主标记：挤出 + 白色前面 + 鼓起光影
    draw_mark(p, big, small=small)

    p.end()

    if ss > 1:
        return img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    return img


_render_cache: dict[tuple[int, bool], QImage] = {}


def render_logo(size: int, *, small: bool = False) -> QImage:
    key = (size, small)
    if key not in _render_cache:
        _ensure_font()
        _render_cache[key] = draw_logo(size, small=small)
    return _render_cache[key]


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
            img = render_logo(px, small=True)
        elif px == 1024:
            img = master
        else:
            img = render_logo(px)
        write_png(img, ICONSET_DIR / name)
    subprocess.run(["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(OUT_DIR / "Section2.icns")],
                   check=True)


def build_ico() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    entries = []
    for px in sizes:
        img = render_logo(px, small=px <= 64)
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
    _ensure_font()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    master = render_logo(CANVAS)
    write_png(master, OUT_DIR / "logo_1024.png")
    build_iconset(master)
    build_ico()
    write_png(render_logo(512), OUT_DIR / "icon_512.png")

    if "--preview" in sys.argv:
        original = QImage(str(ORIGINAL_PNG))
        build_preview(master, original)
    print("done ->", OUT_DIR)


if __name__ == "__main__":
    main()
