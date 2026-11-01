
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from waon.ui import cover_art
from waon.ui import motion
from waon.ui.browse_models import TrackListModel
from waon.ui.browse_panes import make_track_list_view
from waon.ui.elided_label import ElidedLabel
from waon.ui.icons import IconButton

ANIMATION_MS = 250
_MARGIN = 40
_GAP = 40
_MAX_ART = 900
_MIN_ART = 120
_QUEUE_MIN_W = 360
_ART_SHARE = 3 / 5


class NowPlayingPage(QWidget):
    closeRequested = Signal()
    trackActivated = Signal(int)
    orderChanged = Signal(list)
    trackContextMenuRequested = Signal(int, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NowPlayingPage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pixmap = None
        self._art_identity = None
        self._build()
        self._open = False
        self._rect = QRect()
        self._animation = QPropertyAnimation(self, b"pos", self)
        self._animation.finished.connect(self._on_animation_finished)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.closeRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _build(self):
        self.art_label = QLabel()
        self.art_label.setObjectName("NowPlayingArt")
        self.art_label.setAlignment(Qt.AlignCenter)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, _MARGIN // 2)
        left.addStretch(1)
        left.addWidget(self.art_label, 0, Qt.AlignHCenter)
        left.addStretch(1)

        self.queue_title = ElidedLabel("")
        self.queue_title.setObjectName("NowPlayingQueueTitle")
        self.queue_owner = QLabel("")
        self.queue_owner.setObjectName("NowPlayingQueueOwner")
        self.close_button = IconButton("close", "Close", icon_size=16, diameter=32,
                                       pill_hover=False)
        self.close_button.clicked.connect(self.closeRequested)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.queue_title)
        titles.addWidget(self.queue_owner)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(titles, 1)
        header.addWidget(self.close_button, 0, Qt.AlignTop)

        self.track_model = TrackListModel(self)
        self.track_model.set_reorderable(True)
        self.track_model.orderChanged.connect(
            lambda: self.orderChanged.emit(self.track_model.tracks()))
        self.queue_view = make_track_list_view("NowPlayingQueue")
        self.queue_view.setMinimumWidth(_QUEUE_MIN_W)
        self.queue_view.setModel(self.track_model)
        self.queue_view.activated.connect(
            lambda index: self.trackActivated.emit(index.row()))
        self.queue_view.customContextMenuRequested.connect(self._on_context_menu)
        right = QVBoxLayout()
        right.setSpacing(12)
        right.addLayout(header)
        right.addWidget(self.queue_view, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(_MARGIN, _MARGIN // 2, _MARGIN // 2, 0)
        root.setSpacing(_GAP)
        root.addLayout(left, 3)
        root.addLayout(right, 2)
        self._render_art()

    def set_queue(self, tracks, playing_row, now_playing):
        self.track_model.set_tracks(list(tracks))
        if now_playing is None:
            self.track_model.set_now_playing(None, None, None)
        else:
            self.track_model.set_now_playing(*now_playing)
        if 0 <= playing_row < self.track_model.rowCount():
            index = self.track_model.index(playing_row, 0)
            self.queue_view.setCurrentIndex(index)
            self.queue_view.scrollTo(index)

    def set_header(self, name, owner_text):
        self.queue_title.setText(name)
        self.queue_owner.setText(owner_text)

    def set_art(self, pixmap, identity=None):
        if identity != self._art_identity:
            motion.snapshot_fade(self.art_label, motion.TRACK_MS)
        self._art_identity = identity
        self._pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self._render_art()

    def is_open(self):
        return self._open

    def open_over(self, rect):
        self._rect = QRect(rect)
        self._open = True
        self.resize(rect.size())
        if self.isHidden():
            self.move(rect.x(), rect.bottom() + 1)
            self.show()
        self.raise_()
        self.setFocus()
        self._slide_to(rect.topLeft(), QEasingCurve.OutCubic)

    def close_down(self):
        if not self._open:
            return
        self._open = False
        self._slide_to(QPoint(self._rect.x(), self._rect.bottom() + 1),
                       QEasingCurve.InCubic)

    def snap_to(self, rect):
        self._rect = QRect(rect)
        self._animation.stop()
        self.resize(rect.size())
        if self._open:
            self.move(rect.topLeft())
        else:
            self.move(rect.x(), rect.bottom() + 1)
            self.hide()

    def _slide_to(self, target, curve):
        self._animation.stop()
        ms = motion.duration(ANIMATION_MS)
        if ms <= 0:
            self.move(target)
            self._on_animation_finished()
            return
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(target)
        self._animation.setEasingCurve(curve)
        self._animation.setDuration(ms)
        self._animation.start()

    def _on_animation_finished(self):
        if not self._open:
            self.hide()

    def _art_size(self):
        content = self.width() - _MARGIN - _MARGIN // 2 - _GAP
        width = min(int(content * _ART_SHARE), content - _QUEUE_MIN_W)
        height = self.height() - 2 * _MARGIN
        return max(_MIN_ART, min(_MAX_ART, width, height))

    def _render_art(self):
        size = self._art_size()
        pixmap = (cover_art.rounded(self._pixmap, size) if self._pixmap is not None
                  else cover_art.placeholder(size, glyph=size // 4))
        self.art_label.setFixedSize(size, size)
        self.art_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_art()

    def _on_context_menu(self, pos):
        index = self.queue_view.indexAt(pos)
        if index.isValid():
            self.trackContextMenuRequested.emit(
                index.row(), self.queue_view.viewport().mapToGlobal(pos))
