
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap

from waon.ui import theme
from waon.ui.icons import render_icon, screen_dpr


def corner_path(size, radius, corners="all"):
    if corners not in ("all", "left"):
        raise ValueError("corners must be 'all' or 'left', got {!r}".format(corners))
    path = QPainterPath()
    if radius <= 0:
        path.addRect(0, 0, size, size)
        return path
    if corners == "all":
        path.addRoundedRect(0, 0, size, size, radius, radius)
        return path
    r = min(radius, size / 2)
    path.moveTo(size, 0)
    path.lineTo(r, 0)
    path.arcTo(0, 0, 2 * r, 2 * r, 90, 90)
    path.lineTo(0, size - r)
    path.arcTo(0, size - 2 * r, 2 * r, 2 * r, 180, 90)
    path.lineTo(size, size)
    path.closeSubpath()
    return path


def rounded(pixmap, size, radius=0, corners="all"):
    path = corner_path(size, radius, corners)
    dpr = screen_dpr()
    px = round(size * dpr)
    scaled = pixmap.scaled(px, px, Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
    scaled.setDevicePixelRatio(dpr)
    out = QPixmap(px, px)
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return out


def placeholder(size, radius=0, corners="all", glyph=30):
    path = corner_path(size, radius, corners)
    note = render_icon("note", theme.BRAND, glyph)
    dpr = screen_dpr()
    px = round(size * dpr)
    out = QPixmap(px, px)
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.fillPath(path, QColor(theme.BRAND_SOFT))
    painter.drawPixmap((size - glyph) // 2, (size - glyph) // 2, note)
    painter.end()
    return out
