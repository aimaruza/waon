
from PySide6.QtCore import (
    QEvent, QParallelAnimationGroup, QPoint, QPropertyAnimation, QTimer, Qt, Signal,
)
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from waon.ui import cover_art
from waon.ui import motion
from waon.ui.elided_label import ElidedLabel
from waon.ui.icons import IconButton

CARD_W = 340
CARD_H = 84
SHADOW = 24
RADIUS = 10
WINDOW_W = CARD_W + 2 * SHADOW
WINDOW_H = CARD_H + 2 * SHADOW

_ART = CARD_H
_GAP = 14
_RIGHT_INSET = 30
_CLOSE_D = 24
_CLOSE_INSET = 6


class NotificationWindow(QWidget):

    HIDE_MS = 5000
    FADE_IN_MS = 160
    FADE_OUT_MS = 200
    RISE_PX = 8

    clicked = Signal()

    def __init__(self):
        super().__init__(None)
        self.setObjectName("TrackNotification")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool
            | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(WINDOW_W, WINDOW_H)
        self._hovered = False
        self._hide_ms = self.HIDE_MS
        self._from_above = False
        self._anim = None
        self._build()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_now)

    def _build(self):
        self.card = QFrame(self)
        self.card.setObjectName("NotifCard")
        self.card.setFixedSize(CARD_W, CARD_H)

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 46))
        self.card.setGraphicsEffect(shadow)

        self.art_label = QLabel()
        self.art_label.setObjectName("NotifArt")
        self.art_label.setFixedSize(_ART, _ART)

        self.title_label = ElidedLabel("")
        self.title_label.setObjectName("NotifTitle")
        self.artist_label = ElidedLabel("")
        self.artist_label.setObjectName("NotifArtist")

        meta = QVBoxLayout()
        meta.setContentsMargins(0, 0, _RIGHT_INSET, 0)
        meta.setSpacing(1)
        meta.addStretch(1)
        meta.addWidget(self.title_label)
        meta.addWidget(self.artist_label)
        meta.addStretch(1)

        row = QHBoxLayout(self.card)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_GAP)
        row.addWidget(self.art_label)
        row.addLayout(meta, 1)

        self.close_button = IconButton("close", "Dismiss", icon_size=14,
                                       diameter=_CLOSE_D, parent=self.card)
        self.close_button.clicked.connect(self.hide_now)
        self.close_button.setVisible(False)
        self.close_button.move(CARD_W - _CLOSE_D - _CLOSE_INSET, _CLOSE_INSET)

        root = QHBoxLayout(self)
        root.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        root.setSpacing(0)
        root.addWidget(self.card)

        self.card.installEventFilter(self)
        self.set_artwork(None)

    def show_track(self, title, artist, album="", pixmap=None,
                   duration_ms=None, from_above=False):
        self._hide_ms = duration_ms or self.HIDE_MS
        self._from_above = from_above
        self.title_label.setText(title or "")
        line = artist or ""
        if album:
            line = "{} • {}".format(line, album) if line else album
        self.artist_label.setText(line)
        self.artist_label.setVisible(bool(line))
        self.set_artwork(pixmap)
        self._hovered = False
        self.close_button.setVisible(False)
        self._fade_in()
        self._hide_timer.start(self._hide_ms)

    def set_artwork(self, pixmap):
        if pixmap is not None and not pixmap.isNull():
            self.art_label.setPixmap(cover_art.rounded(pixmap, _ART, RADIUS, "left"))
        else:
            self.art_label.setPixmap(cover_art.placeholder(_ART, RADIUS, "left"))

    def _set_hovered(self, hovered):
        hovered = bool(hovered)
        if hovered == self._hovered:
            return
        self._hovered = hovered
        self.close_button.setVisible(hovered)
        if hovered:
            self._hide_timer.stop()
        else:
            self._hide_timer.start(self._hide_ms)

    def _cursor_over_card(self):
        return self.card.rect().contains(self.card.mapFromGlobal(QCursor.pos()))

    def eventFilter(self, obj, event):
        if obj is self.card:
            if event.type() == QEvent.Enter:
                self._set_hovered(True)
            elif event.type() == QEvent.Leave:
                if not self._cursor_over_card():
                    self._set_hovered(False)
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton
                and self.card.geometry().contains(event.position().toPoint())):
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def hide_now(self):
        self._hide_timer.stop()
        self._hovered = False
        self.close_button.setVisible(False)
        self._stop_anim()
        ms = motion.duration(self.FADE_OUT_MS)
        if ms <= 0 or not self.isVisible():
            self._finish_hide()
            return
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(ms)
        fade.setStartValue(self.windowOpacity())
        fade.setEndValue(0.0)
        fade.finished.connect(self._finish_hide)
        self._anim = fade
        fade.start()

    def entrance_start(self, target):
        offset = -self.RISE_PX if self._from_above else self.RISE_PX
        return QPoint(target.x(), target.y() + offset)

    def _fade_in(self):
        self._stop_anim()
        target = self.pos()
        ms = motion.duration(self.FADE_IN_MS)
        if ms <= 0:
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
            return
        start = self.entrance_start(target)
        self.setWindowOpacity(0.0)
        self.move(start)
        self.show()
        self.raise_()
        fade = QPropertyAnimation(self, b"windowOpacity", self)
        fade.setDuration(ms)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        rise = QPropertyAnimation(self, b"pos", self)
        rise.setDuration(ms)
        rise.setStartValue(start)
        rise.setEndValue(target)
        group = QParallelAnimationGroup(self)
        group.addAnimation(fade)
        group.addAnimation(rise)
        self._anim = group
        group.start()

    def _finish_hide(self):
        self.hide()
        self.setWindowOpacity(1.0)
        self._stop_anim()

    def _stop_anim(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
