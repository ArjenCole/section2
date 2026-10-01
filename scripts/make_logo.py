"""Section 2.0 logo 生成器。

继承 1.0 logo（section/section-master/section/Resources/170530 S.png）的配色与版式基因：
    底色 Material Blue Grey 700 #455A64、白色居中主字形、正方形圆角构图。
2.0 造型按苹果现代 macOS 图标设计语言重绘（Big Sur → Tahoe 同一形状体系）：
    - 1024 画布上 824 的 superellipse(n=5) squircle（对系统图标实测拟合）；
    - 明显的液态玻璃光感：左上柔光 + 顶部受光带 + 沿边反光 + 底部内阴影；
    - 主标记：拟物化 s 形管道——圆管沿 S 中心线（两段相切圆弧，相切处平滑过渡）
      扫掠而成，多层同轴描边模拟圆柱高光，两端剖开露出管壁与内腔（呼应"断面"），
      靠近两端各有一道管箍；
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

from PySide6.QtCore import QBuffer, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
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

#: 1.0 的身份色（Material Blue Grey 700）与其顶亮/底深衍生
BG_TOP = QColor("#61798A")
BG_MID = QColor("#455A64")
BG_BOTTOM = QColor("#344450")

CANVAS = 1024
ARTWORK = 824  # 苹果图标网格：1024 画布、824 主体（四周留白 100）
SQUIRCLE_N = 5  # superellipse 指数（对系统图标实测：对角切入点 6.9% ≈ 实测 7.0%）

#: s 形管道参数（工业管道：直管 + 弯头拼接的折线 S）
S_HEIGHT_FRAC = 0.473   # 管道整体高（含管径）/ 画布，沿用 1.0 比例
TUBE_FRAC = 0.217       # 管外径 / 管道整体高
ELBOW_R_FRAC = 0.65     # 弯头弯曲半径 / 管外径
OVERHANG_FRAC = 0.35    # 上下直管端部伸出立管 x 的长度 / 管外径
WIDTH_FRAC = 1.03       # 管道整体宽 / 管道整体高
ARC_STEPS = 48          # 每个弯头圆弧的采样点数
#: 圆柱光影：同轴描边带（宽度占管径比例，颜色由管缘深色到芯部）
TUBE_EDGE = QColor("#26363F")
TUBE_CORE = QColor("#D9E4E9")
GLINT = QColor("#F7FBFC")
WELD_COLOR = QColor(30, 42, 50, 170)   # 直管与弯头的对接焊缝
#: 剖切端面（三层椭圆：切口环 → 内壁 → 内腔，孔洞沿管轴外移形成透视）
BORE_MINOR_FRAC = 0.44  # 端面椭圆短轴 / 管径（长轴 = 管径）
BORE_RING_TOP = QColor("#DCE5EA")   # 切口环亮部（上缘）
BORE_RING_BOT = QColor("#93A5AF")   # 切口环暗部（下缘）
BORE_WALL_IN = QColor("#2C3B44")    # 内壁深侧
BORE_WALL_OUT = QColor("#44565F")   # 内壁浅侧
BORE_HOLE_DEEP = QColor("#131C22")  # 内腔最深
BORE_HOLE_NEAR = QColor("#3F515A")  # 内腔近口部
#: 小尺寸收缩边距（苹果小尺寸图标主体占比更大）
SMALL_MARGIN = {16: 0.039, 24: 0.047, 32: 0.055, 48: 0.066, 64: 0.075}
#: 超采样倍率（边缘抗锯齿的关键：大画布绘制后平滑降采样）
SS = {16: 8, 24: 8, 32: 6, 48: 5, 64: 4, 128: 4, 256: 3, 512: 3, 1024: 3}

app = QApplication.instance() or QApplication(["make_logo"])


def squircle_path(size: float, n: int = SQUIRCLE_N) -> QPainterPath:
    """superellipse |x/a|^n + |y/a|^n = 1 的闭合路径，边长 size、中心在原点。"""
    a = size / 2.0
    steps = 2160
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


def pipe_centerline(dia: float) -> tuple[QPainterPath, QPointF, QPointF, list[tuple[float, float, bool]]]:
    """工业管道折线 S 中心线：5 段直管 + 4 个 90° 弯头，上下点对称。

    走向：上直管（东端开口，向西）→ 弯头 → 左立管（向下）→ 弯头 → 中直管（向东）
    → 弯头 → 右立管（向下）→ 弯头 → 下直管（西端开口，向西）。
    返回 (路径, 上端点, 下端点, 焊缝列表)；焊缝为 (x, y, 是否横缝)：
    横缝表示管轴水平（焊缝竖直），否则管轴竖直（焊缝水平）。
    坐标以管道包围盒中心为原点（y 向下为正）。
    """
    R = dia * ELBOW_R_FRAC
    full_h = dia / TUBE_FRAC
    yt = (full_h - dia) / 2
    xt = (full_h * WIDTH_FRAC - dia) / 2
    xv = xt - dia * OVERHANG_FRAC

    pts: list[tuple[float, float]] = []

    def arc(cx: float, cy: float, a0: float, a1: float) -> None:
        for i in range(1, ARC_STEPS + 1):
            a = math.radians(a0 + (a1 - a0) * i / ARC_STEPS)
            pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))

    pts.append((xt, -yt))                       # 上直管东端（开口向东）
    pts.append((-xv + R, -yt))                  # 上直管向西
    arc(-xv + R, -yt + R, -90, -180)            # 弯头1：西→南
    pts.append((-xv, -R))                       # 左立管向南
    arc(-xv + R, -R, 180, 90)                   # 弯头2：南→东
    pts.append((xv - R, 0))                     # 中直管向东
    arc(xv - R, R, -90, 0)                      # 弯头3：东→南
    pts.append((xv, yt - R))                    # 右立管向南
    arc(xv - R, yt - R, 0, 90)                  # 弯头4：南→西
    pts.append((-xt, yt))                       # 下直管向西（开口向西）

    path = QPainterPath()
    path.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(x, y)

    # 焊缝位置：每个弯头与直管的 8 个对接点
    welds = [
        (-xv + R, -yt, True),      # 上直管 | 弯头1（管轴水平 → 竖缝）
        (-xv, -yt + R, False),     # 弯头1 | 左立管（管轴竖直 → 横缝）
        (-xv, -R, False),          # 左立管 | 弯头2
        (-xv + R, 0, True),        # 弯头2 | 中直管
        (xv - R, 0, True),         # 中直管 | 弯头3
        (xv, R, False),            # 弯头3 | 右立管
        (xv, yt - R, False),       # 右立管 | 弯头4
        (xv - R, yt, True),        # 弯头4 | 下直管
    ]
    return path, QPointF(xt, -yt), QPointF(-xt, yt), welds


def tube_stroke(p: QPainter, centerline: QPainterPath, dia: float,
                *, offset: tuple[float, float] = (0.0, 0.0), t_from: float = 0.0) -> None:
    """沿中心线画圆管：多层同轴描边从管缘深色过渡到芯部。

    t_from 可只画较亮的芯部带（配合 offset 做偏心高光，避免重复压暗管缘）。
    """
    pen = QPen()
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    bands = 14
    for i in range(bands):
        t = i / (bands - 1)          # 0=管缘 1=芯部
        if t < t_from:
            continue
        w = dia * (1.0 - 0.92 * t)
        shade = t ** 1.6             # 管身偏暗，亮部收在芯部
        color = QColor(
            round(TUBE_EDGE.red() + (TUBE_CORE.red() - TUBE_EDGE.red()) * shade),
            round(TUBE_EDGE.green() + (TUBE_CORE.green() - TUBE_EDGE.green()) * shade),
            round(TUBE_EDGE.blue() + (TUBE_CORE.blue() - TUBE_EDGE.blue()) * shade),
        )
        pen.setWidthF(max(1.0, w))
        pen.setColor(color)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if offset != (0.0, 0.0):
            p.save()
            p.translate(offset[0], offset[1])
            p.drawPath(centerline)
            p.restore()
        else:
            p.drawPath(centerline)


def bore_face(p: QPainter, tip: QPointF, dia: float, outward_left: bool) -> None:
    """剖开的管端面（管轴水平：上端开口向东、下端开口向西）。

    三层椭圆做透视：切口环（贴着切口）→ 内壁（向管内退）→ 内腔（孔洞沿管轴
    向开口方向偏移），形成"斜着看进管口"的纵深。
    """
    sign = -1.0 if outward_left else 1.0     # 开口方向：西端 -x，东端 +x
    major = dia                               # 长轴（竖直，⊥管轴）
    minor = dia * BORE_MINOR_FRAC             # 短轴（沿管轴）
    p.setPen(Qt.PenStyle.NoPen)

    # 1) 切口环：金属端面，上亮下暗（全局光从左上来，两端一致用屏幕竖直渐变）
    ring = QLinearGradient(0, tip.y() - major / 2, 0, tip.y() + major / 2)
    ring.setColorAt(0.0, BORE_RING_TOP)
    ring.setColorAt(1.0, BORE_RING_BOT)
    p.setBrush(ring)
    p.drawEllipse(tip, minor / 2, major / 2)

    # 2) 内壁：椭圆中心向管内（开口反向）退一点，露出外侧一圈切口环
    wall_c = QPointF(tip.x() - sign * dia * 0.05, tip.y())
    wall = QLinearGradient(wall_c.x() - minor / 2, 0, wall_c.x() + minor / 2, 0)
    wall.setColorAt(0.0, BORE_WALL_IN if sign > 0 else BORE_WALL_OUT)
    wall.setColorAt(1.0, BORE_WALL_OUT if sign > 0 else BORE_WALL_IN)
    p.setBrush(wall)
    p.drawEllipse(wall_c, minor / 2 * 0.86, major / 2 * 0.86)

    # 3) 内腔：孔洞沿开口方向偏移——远侧内壁呈月牙，近口部略亮
    hole_c = QPointF(tip.x() + sign * dia * 0.10, tip.y())
    hole = QLinearGradient(hole_c.x() - minor / 2, 0, hole_c.x() + minor / 2, 0)
    hole.setColorAt(0.0, BORE_HOLE_DEEP if sign > 0 else BORE_HOLE_NEAR)
    hole.setColorAt(1.0, BORE_HOLE_NEAR if sign > 0 else BORE_HOLE_DEEP)
    p.setBrush(hole)
    p.drawEllipse(hole_c, minor / 2 * 0.60, major / 2 * 0.60)


def weld_seams(p: QPainter, welds: list[tuple[float, float, bool]], dia: float,
               dxy: QPointF) -> None:
    """直管与弯头的对接焊缝：垂直于管轴的细缝，表达"拼接"。"""
    half = dia * 0.47
    pen = QPen()
    pen.setWidthF(max(1.0, dia * 0.035))
    pen.setColor(WELD_COLOR)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    for x, y, horizontal_tube in welds:
        if horizontal_tube:   # 管轴水平 → 焊缝竖直
            p.drawLine(QPointF(x + dxy.x(), y + dxy.y() - half),
                       QPointF(x + dxy.x(), y + dxy.y() + half))
        else:                 # 管轴竖直 → 焊缝水平
            p.drawLine(QPointF(x + dxy.x() - half, y + dxy.y()),
                       QPointF(x + dxy.x() + half, y + dxy.y()))


def draw_mark(p: QPainter, size: int, *, small: bool) -> None:
    """在已铺好玻璃底的画布上绘制工业管道折线 S 主标记。"""
    full_h = size * S_HEIGHT_FRAC
    dia = full_h * TUBE_FRAC
    centerline, tip_top, tip_bot, welds = pipe_centerline(dia)
    # 居中：略向左上让出右下投影的量
    dxy = QPointF(size / 2 - size * 0.006, size / 2 - size * 0.004)
    centerline.translate(dxy.x(), dxy.y())
    tip_top += dxy
    tip_bot += dxy

    # 悬浮投影：更柔、更远，避免暗晕贴住管壁
    lift = _qimage(size, size)
    lp = QPainter(lift)
    lp.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(16, 28, 34, 255), dia, Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.RoundJoin)
    lp.setPen(pen)
    lp.drawPath(centerline)
    lp.end()
    lift_blur = blurred(lift, max(1.5, size * 0.020))
    p.setOpacity(0.26)
    p.drawImage(0, max(1, round(size * 0.013)), lift_blur)
    p.setOpacity(1.0)

    # 管体圆柱光影 + 偏左上的芯部高光 + 细高光棱线
    tube_stroke(p, centerline, dia)
    tube_stroke(p, centerline, dia, offset=(-dia * 0.035, -dia * 0.09), t_from=0.45)
    pen = QPen()
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setWidthF(max(1.0, dia * 0.055))
    pen.setColor(GLINT)
    p.setPen(pen)
    p.save()
    p.translate(-dia * 0.035, -dia * 0.10)
    p.drawPath(centerline)
    p.restore()

    # 直管与弯头的对接焊缝（画在管体之上）
    weld_seams(p, welds, dia, dxy)

    # 两端剖开的管端面（上端开口向东、下端开口向西）
    bore_face(p, tip_top, dia, outward_left=False)
    bore_face(p, tip_bot, dia, outward_left=True)


def draw_logo(size: int, *, small: bool = False) -> QImage:
    """绘制一枚 logo。small=True 时收缩边距（苹果小尺寸规则）。

    内部按 SS 倍超采样绘制后平滑降采样到目标尺寸，保证边缘光滑。
    """
    ss = SS.get(size, 3)
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

    # 4) 主标记：s 形管道
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


def build_preview(original: QImage) -> None:
    """新旧对比预览：亮/暗两种底色，各放 256/128/64/32/16 与 1.0 原版。

    每个尺寸的图块直接用该尺寸的超采样渲染（绝不从母版缩小），避免预览图自身出锯齿。
    """
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
        tile(render_logo(256), cx, 240, 256, "256px", dark)
        tile(render_logo(128), cx - 190, 470, 128, "128px", dark)
        tile(render_logo(64, small=True), cx - 40, 470, 64, "64px", dark)
        tile(render_logo(32, small=True), cx + 70, 470, 32, "32px", dark)
        tile(render_logo(16, small=True), cx + 155, 470, 16, "16px", dark)
        tile(original_128, cx, 730, 128, "1.0 原版", dark)

    panel(0, False)
    panel(W / 2, True)
    p.end()
    write_png(img, BUILD_DIR / "preview.png")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    master = render_logo(CANVAS)
    write_png(master, OUT_DIR / "logo_1024.png")
    build_iconset(master)
    build_ico()
    write_png(render_logo(512), OUT_DIR / "icon_512.png")

    if "--preview" in sys.argv:
        build_preview(QImage(str(ORIGINAL_PNG)))
    print("done ->", OUT_DIR)


if __name__ == "__main__":
    main()
