
import json
import logging
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGlyphRun, QIcon,
                            QPainter, QPixmap, QRawFont)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QApplication

from waon.ui import motion
from waon.ui import theme

log = logging.getLogger(__name__)

_PHOSPHOR_ASSET_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "phosphor-icons")
_LOGO_SVG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "logo", "logo.svg")
_LOGO_MARK_SVG_PATH = os.path.join(os.path.dirname(_LOGO_SVG_PATH),
                                   "logo-mark.svg")
_PHOSPHOR_TTF_PATH = {
    "regular": os.path.join(_PHOSPHOR_ASSET_DIR, "phosphor.ttf"),
    "fill": os.path.join(_PHOSPHOR_ASSET_DIR, "phosphor-fill.ttf"),
    "bold": os.path.join(_PHOSPHOR_ASSET_DIR, "phosphor-bold.ttf"),
}
_PHOSPHOR_JSON_PATH = {
    "regular": os.path.join(_PHOSPHOR_ASSET_DIR, "phosphor.json"),
    "fill": os.path.join(_PHOSPHOR_ASSET_DIR, "phosphor-fill.json"),
    "bold": os.path.join(_PHOSPHOR_ASSET_DIR, "phosphor-bold.json"),
}

_PHOSPHOR_FONT_FAMILY = {"regular": None, "fill": None, "bold": None}
_PHOSPHOR_CODEPOINTS = {"regular": None, "fill": None, "bold": None}


def _ensure_phosphor_fonts_loaded():
    if _PHOSPHOR_FONT_FAMILY["regular"] is not None:
        return
    for weight in ("regular", "fill", "bold"):
        font_id = QFontDatabase.addApplicationFont(_PHOSPHOR_TTF_PATH[weight])
        if font_id == -1:
            raise RuntimeError(
                "could not load the bundled Phosphor Icons {} font at {}"
                .format(weight, _PHOSPHOR_TTF_PATH[weight]))
        families = QFontDatabase.applicationFontFamilies(font_id)
        family = families[-1]
        with open(_PHOSPHOR_JSON_PATH[weight], encoding="utf-8") as fh:
            codepoints = json.load(fh)
        _PHOSPHOR_FONT_FAMILY[weight] = family
        _PHOSPHOR_CODEPOINTS[weight] = codepoints


_GLYPH = {
    "play": ("fill", "play-fill"),
    "pause": ("fill", "pause-fill"),
    "prev": ("fill", "skip-back-fill"),
    "next": ("fill", "skip-forward-fill"),
    "repeat": ("regular", "repeat"),
    "repeat-one": ("regular", "repeat-once"),
    "shuffle": ("regular", "shuffle"),
    "speaker": ("regular", "speaker-high"),
    "muted": ("regular", "speaker-slash"),
    "artist": ("regular", "user"),
    "artist-fill": ("fill", "user-fill"),
    "album": ("regular", "disc"),
    "album-fill": ("fill", "disc-fill"),
    "folder": ("regular", "folder"),
    "folder-fill": ("fill", "folder-fill"),
    "folder-check": ("bold", "folder-simple-plus-bold"),
    "folder-x": ("bold", "folder-simple-minus-bold"),
    "home": ("regular", "house"),
    "home-fill": ("fill", "house-fill"),
    "playlist": ("regular", "playlist"),
    "playlist-fill": ("fill", "playlist-fill"),
    "songs": ("regular", "music-note"),
    "songs-fill": ("fill", "music-note-fill"),
    "calendar": ("regular", "calendar-blank"),
    "queue": ("regular", "queue"),
    "all-libraries": ("regular", "squares-four"),
    "queue-fill": ("fill", "queue-fill"),
    "close": ("regular", "x"),
    "minimize": ("regular", "minus"),
    "maximize": ("regular", "square"),
    "restore": ("regular", "cards"),
    "note": ("fill", "music-notes-fill"),
    "gear": ("regular", "gear"),
    "gear-wide-connected": ("bold", "gear-fine-bold"),
    "pencil-square": ("regular", "pencil-simple-line"),
    "plus": ("regular", "plus"),
    "refresh": ("bold", "arrows-clockwise-bold"),
    "reset": ("regular", "clock-counter-clockwise"),
    "trash": ("regular", "trash-simple"),
    "export": ("regular", "export"),
    "caret-right-bold": ("bold", "caret-right-bold"),
    "caret-left-bold": ("bold", "caret-left-bold"),
    "minus-circle": ("regular", "minus-circle"),
    "chevron-down": ("regular", "caret-down"),
    "chevron-right": ("regular", "caret-right"),
    "caret-circle-double-up": ("regular", "caret-circle-double-up"),
    "caret-circle-double-down": ("regular", "caret-circle-double-down"),
    "play-circle": ("regular", "play-circle"),
    "arrows-down-up": ("regular", "arrows-down-up"),
    "eye": ("regular", "eye"),
    "eye-slash": ("regular", "eye-slash"),
    "stack": ("regular", "stack"),
    "check": ("regular", "check"),
    "sort-ascending": ("regular", "sort-ascending"),
    "sort-descending": ("regular", "sort-descending"),
    "list-checks": ("regular", "list-checks"),
    "square": ("regular", "square"),
    "check-square": ("regular", "check-square"),
    "minus-square": ("regular", "minus-square"),
    "selection-all": ("regular", "selection-all"),
    "selection-slash": ("regular", "selection-slash"),
    "file-arrow-down": ("regular", "file-arrow-down"),
    "lock-simple": ("regular", "lock-simple"),
    "lock-simple-open": ("regular", "lock-simple-open"),
    "waveform": ("regular", "waveform"),
    "rows-plus-bottom": ("regular", "rows-plus-bottom"),
    "more-vertical": ("bold", "dots-three-vertical-bold"),
    "crosshair": ("regular", "crosshair-simple"),
    "folder-open": ("regular", "folder-open"),
    "info": ("regular", "info"),
    "fav": ("regular", "heart"),
    "fav-fill": ("fill", "heart-fill"),
    "fav-break": ("regular", "heart-break"),
    "headphones": ("fill", "headphones-fill"),
    "earbuds": ("fill", "headset-fill"),
    "disc": ("fill", "disc-fill"),
    "vinyl": ("fill", "vinyl-record-fill"),
    "mic": ("fill", "microphone-fill"),
    "star": ("fill", "star-fill"),
    "heart": ("fill", "heart-fill"),
    "soundwave": ("fill", "waveform-fill"),
    "cassette": ("fill", "cassette-tape-fill"),
    "broadcast": ("fill", "broadcast-fill"),
    "record": ("fill", "record-fill"),
    "sheet-music": ("fill", "file-audio-fill"),
    "spotify": ("fill", "spotify-logo-fill"),
    "youtube": ("fill", "youtube-logo-fill"),
    "apple-music": ("fill", "apple-logo-fill"),
    "tiktok": ("fill", "tiktok-logo-fill"),
    "twitch": ("fill", "twitch-logo-fill"),
    "discord": ("fill", "discord-logo-fill"),
}
ICON_NAMES = tuple(_GLYPH.keys())

LIBRARY_ICONS = (
    "note", "headphones", "earbuds", "disc", "vinyl", "mic", "star", "heart",
    "soundwave", "cassette", "broadcast", "record", "sheet-music", "spotify",
    "youtube", "apple-music", "tiktok", "twitch", "discord",
)


def screen_dpr():
    app = QApplication.instance()
    return app.primaryScreen().devicePixelRatio() if app is not None else 1.0


def _blank_pixmap(size):
    dpr = screen_dpr()
    pm = QPixmap(round(size * dpr), round(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    return pm


_RENDERED = {}


def render_icon(name, color, size=20):
    key = (name, color, size, screen_dpr())
    pm = _RENDERED.get(key)
    if pm is not None:
        return pm
    pm = _render_glyph(name, color, size)
    _RENDERED[key] = pm
    return pm


def _render_glyph(name, color, size):
    weight, glyph_name = _GLYPH[name]
    _ensure_phosphor_fonts_loaded()
    family = _PHOSPHOR_FONT_FAMILY[weight]
    codepoint = _PHOSPHOR_CODEPOINTS[weight][glyph_name]
    pm = _blank_pixmap(size)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    font = QFont(family)
    font.setPixelSize(size)
    raw_font = QRawFont.fromFont(font)
    glyph_index = raw_font.glyphIndexesForString(chr(codepoint))[0]
    run = QGlyphRun()
    run.setRawFont(raw_font)
    run.setGlyphIndexes([glyph_index])
    run.setPositions([QPointF(0, raw_font.ascent())])
    painter.setPen(QColor(color))
    painter.drawGlyphRun(QPointF(0, 0), run)
    painter.end()
    return pm


def render_swatch(color, size=16, icon=None):
    ink = QColor(color)
    if not ink.isValid():
        log.warning("library colour %r is not a colour; falling back to %s",
                    color, theme.BRAND)
        ink = QColor(theme.BRAND)
    pm = _blank_pixmap(size)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(ink)
    painter.drawRoundedRect(QRectF(0, 0, size, size), 3, 3)
    if icon:
        if icon not in _GLYPH:
            log.warning("library icon %r is not a known icon; skipping", icon)
        else:
            glyph_size = round(size * _SWATCH_GLYPH_RATIO)
            glyph = render_icon(icon, "#FFFFFF", glyph_size)
            offset = round((size - glyph_size) / 2)
            painter.drawPixmap(offset, offset, glyph)
    painter.end()
    return pm


_SWATCH_GLYPH_RATIO = 0.6


def render_app_icon(size=256):
    key = ("__app_icon__", size, screen_dpr())
    pm = _RENDERED.get(key)
    if pm is not None:
        return pm
    pm = _blank_pixmap(size)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer = QSvgRenderer(_LOGO_SVG_PATH)
    if renderer.isValid():
        renderer.render(painter, QRectF(0, 0, size, size))
    else:
        log.error("app logo %s could not be loaded; drawing a plain square",
                  _LOGO_SVG_PATH)
        painter.fillRect(QRectF(0, 0, size, size), QColor(theme.BRAND))
    painter.end()
    _RENDERED[key] = pm
    return pm


def render_logo_mark(height):
    key = ("__logo_mark__", height, screen_dpr())
    pm = _RENDERED.get(key)
    if pm is not None:
        return pm
    renderer = QSvgRenderer(_LOGO_MARK_SVG_PATH)
    view = renderer.viewBoxF()
    if renderer.isValid() and view.height() > 0:
        aspect = view.width() / view.height()
    else:
        log.error("logo mark %s could not be loaded; leaving it blank",
                  _LOGO_MARK_SVG_PATH)
        aspect = 1.0
    dpr = screen_dpr()
    physical_h = round(height * dpr)
    physical_w = round(physical_h * aspect)
    pm = QPixmap(physical_w, physical_h)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    if renderer.isValid():
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, physical_w / dpr, physical_h / dpr))
        painter.end()
    _RENDERED[key] = pm
    return pm


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render_app_icon(size))
    return icon


_BLEND_STEPS = 8


def _blend(a, b, t):
    step = round(max(0.0, min(1.0, t)) * _BLEND_STEPS)
    if step == 0:
        return a
    if step == _BLEND_STEPS:
        return b
    ca, cb, f = QColor(a), QColor(b), step / _BLEND_STEPS
    return QColor(round(ca.red() + (cb.red() - ca.red()) * f),
                  round(ca.green() + (cb.green() - ca.green()) * f),
                  round(ca.blue() + (cb.blue() - ca.blue()) * f)).name()


class IconButton(QAbstractButton):

    def __init__(self, name, tooltip="", icon_size=19, diameter=38,
                 pill_hover=True, parent=None):
        super().__init__(parent)
        self._name = name
        self._icon_size = icon_size
        self._hover = False
        self._active = False
        self._pill_hover = pill_hover
        self._hover_t = 0.0
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.valueChanged.connect(self._set_hover_t)
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        if tooltip:
            self.setToolTip(tooltip)

    def set_active(self, active):
        active = bool(active)
        if active != self._active:
            self._active = active
            self.update()

    def set_name(self, name):
        if name != self._name:
            self._name = name
            self.update()

    def enterEvent(self, event):
        self._hover = True
        motion.run_tween(self._hover_anim, self._hover_t, 1.0, motion.HOVER_MS,
                         self._set_hover_t)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        motion.run_tween(self._hover_anim, self._hover_t, 0.0, motion.HOVER_MS,
                         self._set_hover_t)
        super().leaveEvent(event)

    def _set_hover_t(self, t):
        self._hover_t = float(t)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        t = self._hover_t
        if self._pill_hover and t > 0:
            pill = QColor(theme.BRAND_SOFT)
            pill.setAlphaF(t)
            painter.setPen(Qt.NoPen)
            painter.setBrush(pill)
            painter.drawEllipse(self.rect())
        color = theme.BRAND if self._active else _blend(theme.ICON, theme.BRAND, t)
        pm = render_icon(self._name, color, self._icon_size)
        x = (self.width() - self._icon_size) // 2
        y = (self.height() - self._icon_size) // 2
        painter.drawPixmap(x, y, pm)
        painter.end()


class PlayButton(QAbstractButton):

    def __init__(self, diameter=44, parent=None):
        super().__init__(parent)
        self._playing = False
        self._hover = False
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._ctrl_click = False
        self._prev_playing = False
        self._glyph_t = 1.0
        self._glyph_anim = QVariantAnimation(self)
        self._glyph_anim.valueChanged.connect(self._set_glyph_t)

    def is_ctrl_click(self):
        return self._ctrl_click

    def mouseReleaseEvent(self, event):
        self._ctrl_click = bool(event.modifiers() & Qt.ControlModifier)
        try:
            super().mouseReleaseEvent(event)
        finally:
            self._ctrl_click = False

    def set_playing(self, playing):
        playing = bool(playing)
        if playing != self._playing:
            self._prev_playing = self._playing
            self._playing = playing
            motion.run_tween(self._glyph_anim, 0.0, 1.0, motion.HOVER_MS,
                             self._set_glyph_t)

    def _set_glyph_t(self, t):
        self._glyph_t = float(t)
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def _draw_glyph(self, painter, playing, opacity):
        d = self.width()
        glyph = "pause" if playing else "play"
        gsize = 18
        pm = render_icon(glyph, "#FFFFFF", gsize)
        painter.setOpacity(opacity)
        painter.drawPixmap((d - gsize) // 2, (d - gsize) // 2, pm)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        d = self.width()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.BRAND_HOVER if self._hover else theme.BRAND))
        painter.drawEllipse(2, 2, d - 4, d - 4)
        if self._glyph_t < 1.0:
            self._draw_glyph(painter, self._prev_playing, 1.0 - self._glyph_t)
        self._draw_glyph(painter, self._playing, self._glyph_t)
        painter.end()
