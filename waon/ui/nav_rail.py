
import logging

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QVBoxLayout, QWidget

from waon.library import service as svc
from waon.ui import theme
from waon.ui.icons import ICON_NAMES, render_icon

log = logging.getLogger(__name__)

RAIL_W = 80

_FALLBACK_GLYPH = "note"

_FILLED_GLYPH = {
    "home": "home-fill",
    "artist": "artist-fill",
    "album": "album-fill",
    "folder": "folder-fill",
    "playlist": "playlist-fill",
    "songs": "songs-fill",
    "queue": "queue-fill",
}

_ITEMS = (
    (svc.RAIL_HOME, "home", "Home"),
    (svc.RAIL_ARTISTS, "artist", "Artists"),
    (svc.RAIL_ALBUMS, "album", "Albums"),
    (svc.RAIL_FOLDERS, "folder", "Folders"),
    (svc.RAIL_SONGS, "songs", "Songs"),
    (svc.RAIL_PLAYLISTS, "playlist", "Playlists"),
)
_QUEUES_ITEM = (svc.RAIL_QUEUES, "queue", "Queues")
_HIDDEN_ITEMS = frozenset({svc.RAIL_FOLDERS})


class RailButton(QAbstractButton):

    HEIGHT = 62
    ICON_SIZE = 22
    ICON_TOP = 10
    _PILL_INSET_X = 0
    _PILL_INSET_Y = 0
    _PILL_RADIUS = 0
    _CAPTION_PT = 7.5
    _CAPTION_BOTTOM = 8
    _CAPTION_SIDE = 2

    def __init__(self, name, caption, parent=None):
        super().__init__(parent)
        if name not in ICON_NAMES:
            log.error("no glyph named %r for the %r rail item; drawing %r",
                      name, caption, _FALLBACK_GLYPH)
            name = _FALLBACK_GLYPH
        self._name = name
        self.caption = caption
        self._hover = False
        self._active = False
        self.setFixedSize(RAIL_W, self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setToolTip(caption)
        self.setAccessibleName(caption)
        self.setCheckable(True)
        self.setAutoExclusive(False)

    def set_active(self, active):
        active = bool(active)
        self.setChecked(active)
        if active != self._active:
            self._active = active
            self.update()

    def _glyph_name(self):
        if self._active:
            return _FILLED_GLYPH.get(self._name, self._name)
        return self._name

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pill = self.rect().adjusted(self._PILL_INSET_X, self._PILL_INSET_Y,
                                    -self._PILL_INSET_X, -self._PILL_INSET_Y)
        if self._active:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.BRAND_SOFT))
            painter.drawRoundedRect(pill, self._PILL_RADIUS, self._PILL_RADIUS)
        if not self.isEnabled():
            color = theme.DISABLED
        elif self._active or self._hover:
            color = theme.BRAND
        else:
            color = theme.ICON
        if not self.isEnabled():
            caption_color = theme.DISABLED
        elif self._active:
            caption_color = theme.TEXT
        else:
            caption_color = theme.ICON
        if self.hasFocus():
            painter.setPen(QPen(QColor(theme.BRAND), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                QRectF(pill).adjusted(0.5, 0.5, -0.5, -0.5),
                self._PILL_RADIUS, self._PILL_RADIUS)
        pixmap = render_icon(self._glyph_name(), color, self.ICON_SIZE)
        painter.drawPixmap((self.width() - self.ICON_SIZE) // 2, self.ICON_TOP,
                           pixmap)
        font = QFont(painter.font())
        font.setPointSizeF(self._CAPTION_PT)
        font.setBold(self._active)
        painter.setFont(font)
        painter.setPen(QColor(caption_color))
        painter.drawText(
            self.rect().adjusted(self._CAPTION_SIDE, 0, -self._CAPTION_SIDE,
                                 -self._CAPTION_BOTTOM),
            Qt.AlignHCenter | Qt.AlignBottom, self.caption)
        painter.end()


class NavRail(QWidget):

    itemSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavRail")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(RAIL_W)
        self.setAccessibleName("Library navigation")
        self._buttons = {}
        self._order = []
        self._current = svc.RAIL_ARTISTS
        self._build()
        self._sync_active()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        shown = 0
        for item, glyph, caption in _ITEMS:
            button = self._make(item, glyph, caption)
            if item in _HIDDEN_ITEMS:
                button.hide()
                continue
            if shown > 0:
                layout.addSpacing(2)
            layout.addWidget(button)
            shown += 1
        layout.addStretch(1)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet("background: {};".format(theme.BORDER))
        layout.addWidget(rule)
        item, glyph, caption = _QUEUES_ITEM
        layout.addWidget(self._make(item, glyph, caption))

    def _make(self, item, glyph, caption):
        button = RailButton(glyph, caption, self)
        button.clicked.connect(lambda _=False, key=item: self._on_click(key))
        self._buttons[item] = button
        self._order.append(item)
        return button

    def items(self):
        return tuple(self._order)

    def button(self, item):
        return self._buttons[item]

    def current(self):
        return self._current

    def set_current(self, item):
        if item not in self._buttons:
            log.warning("no rail item named %r; staying on %r", item,
                        self._current)
            return
        self._current = item
        self._sync_active()

    def set_library_available(self, available):
        for item in svc.LIBRARY_RAIL_ITEMS:
            self._buttons[item].setEnabled(bool(available))

    def set_all_mode(self, on):
        for item, button in self._buttons.items():
            if item in _HIDDEN_ITEMS:
                continue
            button.setVisible(not on or item in svc.ALL_MODE_RAIL_ITEMS)

    def _on_click(self, item):
        changed = item != self._current
        if changed:
            self._current = item
        self._sync_active()
        if changed:
            self.itemSelected.emit(item)

    def _sync_active(self):
        for item, button in self._buttons.items():
            button.set_active(item == self._current)
