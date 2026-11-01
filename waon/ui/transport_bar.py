
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from waon.util import format_time
from waon.ui import cover_art
from waon.ui import motion
from waon.ui import dnd
from waon.ui.click_slider import ClickSlider
from waon.ui.elided_label import ElidedLabel
from waon.ui.icons import IconButton, PlayButton
from waon import playlist_file


class _ClickableLabel(QLabel):

    clicked = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


_BAR_H = 84
_SEEK_H = 12
_GROOVE_H = 4
_CONTENT_TOP = _GROOVE_H
_ART = _BAR_H - _CONTENT_TOP


class TransportBar(QWidget):
    playPauseClicked = Signal()
    stopClicked = Signal()
    nextClicked = Signal()
    prevClicked = Signal()
    repeatClicked = Signal()
    shuffleClicked = Signal()
    seekRequested = Signal(float)
    volumeChanged = Signal(float)
    filesDropped = Signal(list)
    moreClicked = Signal()
    favoriteClicked = Signal()
    artClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TransportBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(_BAR_H)
        self.setAcceptDrops(True)
        self._duration = 0.0
        self._position = 0.0
        self._show_remaining = False
        self._muted = False
        self._volume_before_mute = 80
        self._shown = ("", "")
        self._build()

    def _build(self):
        self.seek_slider = ClickSlider(Qt.Horizontal, self)
        self.seek_slider.setObjectName("SeekSlider")
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setFixedHeight(_SEEK_H)
        self.seek_slider.sliderMoved.connect(self._on_seek_preview)
        self.seek_slider.sliderReleased.connect(self._on_seek_release)

        self.art_label = _ClickableLabel()
        self.art_label.clicked.connect(self.artClicked)
        self.art_label.setFixedSize(_ART, _ART)
        self.set_artwork(None)
        self.title_label = ElidedLabel("Nothing playing")
        self.title_label.setObjectName("NowTitle")
        self.artist_label = ElidedLabel("")
        self.artist_label.setObjectName("NowArtist")
        meta = QVBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(1)
        meta.addStretch(1)
        meta.addWidget(self.title_label)
        meta.addWidget(self.artist_label)
        meta.addStretch(1)
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(14)
        left.addWidget(self.art_label)
        left.addLayout(meta, 1)
        self.now_zone = QWidget()
        self.now_zone.setLayout(left)
        self.now_zone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.repeat_button = IconButton("repeat", "Repeat", icon_size=20, diameter=40)
        self.prev_button = IconButton("prev", "Previous", icon_size=23, diameter=40)
        self.play_button = PlayButton(diameter=50)
        self.next_button = IconButton("next", "Next", icon_size=23, diameter=40)
        self.shuffle_button = IconButton("shuffle", "Shuffle", icon_size=20, diameter=40)
        self.repeat_button.clicked.connect(self.repeatClicked)
        self.prev_button.clicked.connect(self.prevClicked)
        self.play_button.setToolTip("Play/Pause (Ctrl+click or Ctrl+Space to stop)")
        self.play_button.clicked.connect(self._on_play_clicked)
        self.next_button.clicked.connect(self.nextClicked)
        self.shuffle_button.clicked.connect(self.shuffleClicked)
        center = QHBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(6)
        for w in (self.repeat_button, self.prev_button, self.play_button,
                  self.next_button, self.shuffle_button):
            center.addWidget(w)
        center_w = QWidget()
        center_w.setLayout(center)

        self.elapsed_label = _ClickableLabel("0:00")
        self.elapsed_label.setObjectName("TimeElapsed")
        self.elapsed_label.setToolTip("Show remaining time")
        self.elapsed_label.clicked.connect(self._toggle_time_mode)
        self.slash_label = QLabel("/")
        self.slash_label.setObjectName("TimeLabel")
        self.total_label = QLabel("0:00")
        self.total_label.setObjectName("TimeLabel")
        self.favorite_button = IconButton("fav", "Add to favorites",
                                          icon_size=18, diameter=30)
        self.favorite_button.clicked.connect(self.favoriteClicked)
        self.favorite_button.setEnabled(False)
        self.speaker_button = IconButton("speaker", "Mute", icon_size=18, diameter=30)
        self.speaker_button.clicked.connect(self._toggle_mute)
        self.volume_slider = ClickSlider(Qt.Horizontal)
        self.volume_slider.setObjectName("VolumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(92)
        self.volume_slider.setFixedHeight(12)
        self.volume_slider.sliderMoved.connect(self._on_volume_moved)
        self.more_button = IconButton("more-vertical", "More options",
                                      icon_size=18, diameter=30)
        self.more_button.clicked.connect(self.moreClicked)
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 18, 0)
        right.setSpacing(8)
        right.addStretch(1)
        right.addWidget(self.elapsed_label)
        right.addWidget(self.slash_label)
        right.addWidget(self.total_label)
        right.addSpacing(6)
        right.addWidget(self.favorite_button)
        right.addWidget(self.speaker_button)
        right.addWidget(self.volume_slider)
        right.addWidget(self.more_button)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        row = QGridLayout()
        row.setContentsMargins(0, _CONTENT_TOP, 0, 0)
        row.setHorizontalSpacing(14)
        row.addWidget(self.now_zone, 0, 0)
        row.addWidget(center_w, 0, 1)
        row.addWidget(right_w, 0, 2)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 0)
        row.setColumnStretch(2, 1)
        row.setRowStretch(0, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(row)

        self.set_now_playing("")

    def dragEnterEvent(self, event):
        if self._has_droppable_files(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._has_droppable_files(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self._handle_drop(event.mimeData()):
            event.acceptProposedAction()

    def _has_droppable_files(self, mime):
        return any(playlist_file.is_droppable(p)
                  for p in dnd.local_paths_from_mime(mime))

    def _handle_drop(self, mime):
        paths = playlist_file.expand_paths(dnd.local_paths_from_mime(mime))
        if paths:
            self.filesDropped.emit(paths)
        return bool(paths)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.seek_slider.setGeometry(0, 0, self.width(), _SEEK_H)
        self.seek_slider.raise_()

    def _on_seek_preview(self, value):
        self._position = value
        self._update_elapsed_label()

    def _on_seek_release(self):
        self.seekRequested.emit(float(self.seek_slider.value()))

    def set_duration(self, seconds):
        self._duration = max(0.0, float(seconds))
        self.seek_slider.setRange(0, int(self._duration))
        self.total_label.setText(format_time(self._duration))
        self._update_elapsed_label()

    def set_position(self, seconds):
        if self.seek_slider.isSliderDown():
            return
        self._position = seconds
        self.seek_slider.setValue(int(seconds))
        self._update_elapsed_label()

    def _update_elapsed_label(self):
        if self._show_remaining and self._duration > 0:
            remaining = max(0.0, self._duration - self._position)
            self.elapsed_label.setText("-" + format_time(remaining))
        else:
            self.elapsed_label.setText(format_time(self._position))

    def _toggle_time_mode(self):
        self._show_remaining = not self._show_remaining
        self.elapsed_label.setToolTip(
            "Show elapsed time" if self._show_remaining else "Show remaining time")
        self._update_elapsed_label()

    def set_volume(self, fraction):
        self.volume_slider.setValue(int(round(max(0.0, min(1.0, fraction)) * 100)))

    def unmuted_volume(self):
        value = self._volume_before_mute if self._muted else self.volume_slider.value()
        return value / 100.0

    def _on_volume_moved(self, value):
        if value > 0 and self._muted:
            self._muted = False
            self.speaker_button.set_name("speaker")
        self.volumeChanged.emit(value / 100.0)

    def _toggle_mute(self):
        if not self._muted:
            self._muted = True
            self._volume_before_mute = self.volume_slider.value()
            self.volume_slider.setValue(0)
            self.speaker_button.set_name("muted")
            self.volumeChanged.emit(0.0)
        else:
            self._muted = False
            self.volume_slider.setValue(self._volume_before_mute)
            self.speaker_button.set_name("speaker")
            self.volumeChanged.emit(self._volume_before_mute / 100.0)

    @staticmethod
    def _second_line(title, artist, album):
        if not title:
            return ""
        line = artist or ""
        if album:
            line = "{} • {}".format(line, album) if line else album
        return line

    def set_now_playing(self, title, artist="", album=""):
        idle = not title
        self.title_label.setText(title or "Nothing playing")
        self.title_label.setProperty("idle", idle)
        self.title_label.style().unpolish(self.title_label)
        self.title_label.style().polish(self.title_label)
        line = self._second_line(title, artist, album)
        self.artist_label.setText(line)
        self.artist_label.setVisible(bool(line))
        self._shown = (title or "", line)

    def show_track(self, title, artist="", album="", pixmap=None):
        if (title or "", self._second_line(title, artist, album)) != self._shown:
            motion.snapshot_fade(self.now_zone, motion.TRACK_MS)
        self.set_now_playing(title, artist, album)
        self.set_artwork(pixmap)

    def set_artwork(self, pixmap):
        if pixmap is not None and not pixmap.isNull():
            self.art_label.setPixmap(cover_art.rounded(pixmap, _ART))
        else:
            self.art_label.setPixmap(cover_art.placeholder(_ART))

    def _on_play_clicked(self):
        if self.play_button.is_ctrl_click():
            self.stopClicked.emit()
        else:
            self.playPauseClicked.emit()

    def set_playing(self, is_playing):
        self.play_button.set_playing(is_playing)

    def set_repeat_mode(self, mode):
        self.repeat_button.set_active(mode != "off")
        self.repeat_button.set_name("repeat-one" if mode == "one" else "repeat")

    def set_shuffle(self, on):
        self.shuffle_button.set_active(on)

    def set_favorite(self, on):
        self.favorite_button.set_name("fav-fill" if on else "fav")
        self.favorite_button.set_active(on)
        self.favorite_button.setToolTip(
            "Remove from favorites" if on else "Add to favorites")

    def set_favorite_enabled(self, enabled):
        self.favorite_button.setEnabled(enabled)

    def set_enabled_controls(self, enabled):
        for w in (self.repeat_button, self.prev_button, self.play_button,
                  self.next_button, self.shuffle_button, self.seek_slider,
                  self.more_button):
            w.setEnabled(enabled)
