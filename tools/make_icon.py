# -*- coding: utf-8 -*-
"""生成「隐络」应用图标：半重叠的两个 A（上实下虚），暗示双层 PDF。
输出 assets/icon.png（256）与 assets/icon.ico（16/32/48/256 多尺寸）。
"""
import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
os.makedirs(ASSETS, exist_ok=True)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication,  # noqa: E402
                           QImage, QLinearGradient, QPainter, QPainterPath)

app = QGuiApplication(sys.argv)

# 离屏模式 Qt 找不到系统字体，显式加载 Arial Black
from PySide6.QtGui import QFontDatabase  # noqa: E402
_FONT_FAMILY = "Arial"
for _f in (r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\arialbd.ttf",
           r"C:\Windows\Fonts\arial.ttf"):
    if os.path.exists(_f):
        _fid = QFontDatabase.addApplicationFont(_f)
        _fams = QFontDatabase.applicationFontFamilies(_fid)
        if _fams and "black" in _fams[0].lower():
            _FONT_FAMILY = _fams[0]
            break
        if _fams:
            _FONT_FAMILY = _fams[0]


def render(size):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    s = size / 256.0

    def R(x, y, w, h):
        return QRectF(x * s, y * s, w * s, h * s)

    # 底板：圆角方块，绿色渐变
    tile = QPainterPath()
    tile.addRoundedRect(R(16, 16, 224, 224), 52 * s, 52 * s)
    grad = QLinearGradient(0, 16 * s, 0, 240 * s)
    grad.setColorAt(0, QColor("#22C55E"))
    grad.setColorAt(1, QColor("#15803D"))
    p.fillPath(tile, grad)

    font = QFont(_FONT_FAMILY)
    font.setPixelSize(int(118 * s))
    font.setBold(True)
    p.setFont(font)
    fm = QFontMetricsF(font)
    text_w = fm.horizontalAdvance("A")

    # 双 A 完全参考劳斯莱斯双 R 标志：同高同大、共享基线，
    # 仅水平错位交叠，左前（纯白实心，文字层）右后（浅蓝半透明，图像层）
    top = 62 * s

    # 后层 A：浅绿半透明，偏右，先画被遮挡
    lower = QColor("#BBF7D0")
    lower.setAlpha(200)
    p.setPen(lower)
    p.drawText(QRectF(154 * s - text_w / 2, top, text_w, 132 * s),
               Qt.AlignCenter, "A")

    # 前层 A：纯白实心，偏左，遮住后层重叠部分
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(102 * s - text_w / 2, top, text_w, 132 * s),
               Qt.AlignCenter, "A")

    p.end()
    return img


sizes = [16, 32, 48, 256]
pngs = []
for sz in sizes:
    img = render(sz)
    buf_path = os.path.join(ASSETS, f"icon-{sz}.png")
    img.save(buf_path)
    with open(buf_path, "rb") as fh:
        pngs.append((sz, fh.read()))
    os.remove(buf_path)

with open(os.path.join(ASSETS, "icon.png"), "wb") as fh:
    fh.write(pngs[-1][1])

entries = []
offset = 6 + 16 * len(pngs)
for sz, data in pngs:
    entry = struct.pack("<BBBBHHII",
                        0 if sz >= 256 else sz, 0 if sz >= 256 else sz,
                        0, 0, 1, 32, len(data), offset)
    entries.append(entry)
    offset += len(data)
with open(os.path.join(ASSETS, "icon.ico"), "wb") as fh:
    fh.write(struct.pack("<HHH", 0, 1, len(pngs)))
    for e in entries:
        fh.write(e)
    for _, data in pngs:
        fh.write(data)

print("icon ->", ASSETS)
