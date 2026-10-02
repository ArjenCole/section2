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

#: s 形管道参数（骨架参照粗黑体 S：上碗 + 斜脊线 + 下碗，直管 + 弯头拼接，扁平风）
S_HEIGHT_FRAC = 0.52   # 管道整体高（含管径）/ 画布（折线 S 偏窄，放大保证存在感）
TUBE_FRAC = 0.26        # 管外径 / 管道整体高（粗黑体感的粗管）
BEND_R_FRAC = 0.55      # 弯头弯曲半径 / 管外径
VERT_FRAC = 0.10        # 两侧立管直段长 / 管外径（短立管，弯头链更流畅）
SPINE_ANGLE = 25        # 中间斜脊与水平的夹角（度）——越小说脊线越舒展
TUCK_FRAC = 0.35        # 端部相对立管轴线的内收量 / 管外径（弯头是最左/最右点）
ARC_STEPS = 48          # 每个 90° 弯头圆弧的采样点数
#: 扁平化圆柱光影：少量同轴色带 + 一条柔和受光带，无镜面高光
TUBE_BANDS = (
    (1.00, "#33454E"),
    (0.82, "#485D67"),
    (0.60, "#647A85"),
    (0.36, "#8CA1AB"),
)
TUBE_LIT_BAND = (0.30, "#9FB3BC")   # 偏左上的柔和受光带
WELD_COLOR = QColor(30, 42, 50, 150)   # 直管与弯头的对接焊缝
#: 剖切端面（扁平、有透视主次）：上端开口朝东正视（环 + 腔），下端开口朝西
#: 背向视者，只看到接近侧切的窄椭圆——两端不再一样
BORE_MINOR_FRAC = 0.34     # 正视端面短轴 / 管径
BORE_EDGE_FRAC = 0.16      # 背向端面（侧切窄椭圆）短轴 / 管径
BORE_RING = QColor("#9FB2BA")       # 端面（哑光金属，压暗以平衡右上视觉重量）
BORE_HOLE = QColor("#2C3840")       # 内腔
BORE_EDGE = QColor("#A7B8C0")       # 背向端窄椭圆（略提亮，补左下质量）
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


def pipe_centerline(dia: float) -> tuple[QPainterPath, QPointF, QPointF, list[tuple[float, float, float]]]:
    """粗黑体 S 骨架的管道中心线（点对称）。

    走向：上横管（东端开口内收，向西）→ 90° 弯 → 左立管 → (90°−θ) 弯 → 斜脊
    （与水平成 θ 角，穿中心）→ (90°−θ) 弯 → 右立管 → 90° 弯 → 下横管（西端
    开口内收，向西）。左右弯头是全字的最左/最右点，开口端面不超出弯头。
    返回 (路径, 上端点, 下端点, 焊缝列表)；焊缝为 (x, y, 缝线方向角°)。
    坐标以管道包围盒中心为原点（y 向下为正）。
    """
    R = dia * BEND_R_FRAC
    full_h = dia / TUBE_FRAC
    yt = (full_h - dia) / 2
    th = math.radians(SPINE_ANGLE)
    # 立管直段 VERT_FRAC·dia，脊线斜率 tanθ 定出立管位置 xv：
    #   m = xv·tanθ + R(1−sinθ)/cosθ 且 m = yt − R − vert
    xv = (yt - R - dia * VERT_FRAC - R * (1 - math.sin(th)) / math.cos(th)) / math.tan(th)
    m = xv * math.tan(th) + R * (1 - math.sin(th)) / math.cos(th)
    xt = xv - dia * TUCK_FRAC

    pts: list[tuple[float, float]] = [(xt, -yt), (-xv + R, -yt)]   # 上横管向西

    def arc(cx: float, cy: float, a0: float, a1: float) -> None:
        for i in range(1, ARC_STEPS + 1):
            a = math.radians(a0 + (a1 - a0) * i / ARC_STEPS)
            pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))

    arc(-xv + R, -yt + R, -90, -180)             # 90° 弯：西→南
    pts.append((-xv, -m))                        # 左立管向南
    arc(-xv + R, -m, 180, 90 + SPINE_ANGLE)      # (90°−θ) 弯：南→斜脊
    pts.append((xv - R * (1 - math.sin(th)), m - R * math.cos(th)))  # 斜脊穿中心
    arc(xv - R, m, SPINE_ANGLE - 90, 0)          # (90°−θ) 弯：斜脊→南
    pts.append((xv, yt - R))                     # 右立管向南
    arc(xv - R, yt - R, 0, 90)                   # 90° 弯：南→西
    pts.append((-xt, yt))                        # 下横管向西（开口向西）

    path = QPainterPath()
    path.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(x, y)

    weld_dir = 90 + SPINE_ANGLE                  # 斜脊焊缝：垂直于脊线
    welds = [
        (-xv + R, -yt, 90.0),                    # 上横管 | 90° 弯
        (-xv, -yt + R, 0.0),                     # 90° 弯 | 左立管
        (-xv, -m, 0.0),                          # 左立管 | θ 弯
        (-xv + R * (1 - math.sin(th)), -m + R * math.cos(th), weld_dir),
        (xv - R * (1 - math.sin(th)), m - R * math.cos(th), weld_dir),
        (xv, m, 0.0),                            # θ 弯 | 右立管
        (xv, yt - R, 0.0),                       # 右立管 | 90° 弯
        (xv - R, yt, 90.0),                      # 90° 弯 | 下横管
    ]
    return path, QPointF(xt, -yt), QPointF(-xt, yt), welds


def tube_stroke(p: QPainter, centerline: QPainterPath, dia: float) -> None:
    """沿中心线画管体（扁平风）：少量同轴色带 + 一条柔和受光带，无镜面高光。"""
    pen = QPen()
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for w_frac, hex_color in TUBE_BANDS:
        pen.setWidthF(max(1.0, dia * w_frac))
        pen.setColor(QColor(hex_color))
        p.setPen(pen)
        p.drawPath(centerline)
    # 偏左上的柔和受光带（保留一点体积，不抢扁平感）
    w_frac, hex_color = TUBE_LIT_BAND
    pen.setWidthF(max(1.0, dia * w_frac))
    pen.setColor(QColor(hex_color))
    p.setPen(pen)
    p.save()
    p.setOpacity(0.55)
    p.translate(-dia * 0.035, -dia * 0.09)
    p.drawPath(centerline)
    p.restore()


def bore_face(p: QPainter, tip: QPointF, dia: float, outward_left: bool) -> None:
    """剖开的管端（管轴水平，上端开口朝东、下端开口朝西），扁平且有透视主次：

    - 上端开口朝东（朝向视者一侧）：能看到端面环 + 内腔，端面中心略向管内收，
      内腔再向管内偏——读作"斜看进管口"；
    - 下端开口朝西（背向视者）：只看到接近侧切的窄椭圆，无内腔——两个端口
      不一样才符合透视。
    """
    major = dia                               # 长轴（竖直，⊥管轴）
    p.setPen(Qt.PenStyle.NoPen)
    if not outward_left:
        # 正视端：端面椭圆完全收在管口轮廓内（中心内收短轴之半 -2%），
        # 内腔再向管内偏 2%——读作"斜看进管口"，不外凸
        minor = dia * BORE_MINOR_FRAC
        face_c = QPointF(tip.x() - (minor / 2 - dia * 0.02), tip.y())
        p.setBrush(BORE_RING)
        p.drawEllipse(face_c, minor / 2, major / 2)
        hole_c = QPointF(face_c.x() - dia * 0.02, face_c.y())
        p.setBrush(BORE_HOLE)
        p.drawEllipse(hole_c, minor / 2 * 0.52, major / 2 * 0.52)
    else:
        # 背向端：接近侧切的窄椭圆，无内腔
        edge_c = QPointF(tip.x() + dia * 0.02, tip.y())
        p.setBrush(BORE_EDGE)
        p.drawEllipse(edge_c, dia * BORE_EDGE_FRAC / 2, major / 2)


def weld_seams(p: QPainter, welds: list[tuple[float, float, float]], dia: float,
               dxy: QPointF) -> None:
    """直管与弯头的对接焊缝：垂直于管轴的细缝，表达"拼接"。"""
    half = dia * 0.47
    pen = QPen()
    pen.setWidthF(max(1.0, dia * 0.035))
    pen.setColor(WELD_COLOR)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    for x, y, angle in welds:
        a = math.radians(angle)
        dx, dy = math.cos(a) * half, math.sin(a) * half
        p.drawLine(QPointF(x + dxy.x() - dx, y + dxy.y() - dy),
                   QPointF(x + dxy.x() + dx, y + dxy.y() + dy))


def draw_mark(p: QPainter, size: int, *, small: bool) -> None:
    """在已铺好玻璃底的画布上绘制工业管道折线 S 主标记。"""
    full_h = size * S_HEIGHT_FRAC
    dia = full_h * TUBE_FRAC
    centerline, tip_top, tip_bot, welds = pipe_centerline(dia)
    # 光学修正：右上端面明度偏高使字形看似顺时针倾倒，整体逆时针微旋回正
    opt = QTransform().rotate(-2.0)
    centerline = opt.map(centerline)
    tip_top = opt.map(tip_top)
    tip_bot = opt.map(tip_bot)
    welds = [(opt.map(QPointF(x, y)).x(), opt.map(QPointF(x, y)).y(), a - 2.0)
             for x, y, a in welds]
    # 居中：略向左上让出右下投影的量
    dxy = QPointF(size / 2 - size * 0.014, size / 2 - size * 0.004)
    centerline.translate(dxy.x(), dxy.y())
    tip_top += dxy
    tip_bot += dxy

    # 悬浮投影：扁平化——更淡更近
    lift = _qimage(size, size)
    lp = QPainter(lift)
    lp.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(16, 28, 34, 255), dia, Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.RoundJoin)
    lp.setPen(pen)
    lp.drawPath(centerline)
    lp.end()
    lift_blur = blurred(lift, max(1.5, size * 0.016))
    p.setOpacity(0.16)
    p.drawImage(0, max(1, round(size * 0.010)), lift_blur)
    p.setOpacity(1.0)

    # 管体（扁平色带 + 柔和受光带）
    tube_stroke(p, centerline, dia)

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
