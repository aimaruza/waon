
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from waon.ui import cover_art
from waon.ui.elided_label import LEFT_ALIGNED
from waon.ui.overlay_dialog import OverlayDialog

COVER = 200
_KEY_W = 110


def _fill_grid(grid, rows):
    while grid.count():
        item = grid.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
    for r, (label, value) in enumerate(rows):
        key = QLabel(label)
        key.setObjectName("TrackInfoKey")
        key.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        val = QLabel(value)
        val.setObjectName("TrackInfoValue")
        val.setAlignment(LEFT_ALIGNED)
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(key, r, 0)
        grid.addWidget(val, r, 1)


def _grid(rows, key_width=_KEY_W):
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(6)
    grid.setColumnMinimumWidth(0, key_width)
    grid.setColumnStretch(1, 1)
    _fill_grid(grid, rows)
    return box, grid


def _divider():
    line = QWidget()
    line.setObjectName("TrackInfoDivider")
    line.setFixedHeight(1)
    line.setAttribute(Qt.WA_StyledBackground, True)
    return line


class TrackInfoDialog(OverlayDialog):
    resetRequested = Signal()

    def __init__(self, info, pixmap, parent=None):
        super().__init__("Track info", parent, min_width=640, flat_icons=True)
        self._group_grids = []
        self._listening_grid = None
        self.reset_button = None

        cover = QLabel()
        cover.setFixedSize(COVER, COVER)
        if pixmap is not None and not pixmap.isNull():
            cover.setPixmap(cover_art.rounded(pixmap, COVER))
        else:
            cover.setPixmap(cover_art.placeholder(COVER, glyph=64))
        title = QLabel(info.title)
        title.setObjectName("TrackInfoTitle")
        title.setAlignment(LEFT_ALIGNED)
        title.setWordWrap(True)
        meta_box, _meta = _grid((("File name", info.file_name),
                                 ("Location", info.location)), key_width=70)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        left.addWidget(cover)
        left.addWidget(title)
        left.addWidget(meta_box)
        left.addStretch(1)
        if info.listening is not None:
            self.reset_button = QPushButton("Reset play stats")
            self.reset_button.setObjectName("TrackInfoReset")
            self.reset_button.setCursor(Qt.PointingHandCursor)
            self.reset_button.setEnabled(info.play_count > 0)
            self.reset_button.clicked.connect(self.resetRequested)
            left.addWidget(self.reset_button, 0, Qt.AlignLeft)
        left_w = QWidget()
        left_w.setFixedWidth(COVER)
        left_w.setLayout(left)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        groups = [g for g in (info.tags, info.audio) if g]
        if info.listening is not None:
            groups.append(info.listening)
        for i, rows in enumerate(groups):
            if i:
                right.addWidget(_divider())
            box, grid = _grid(rows)
            right.addWidget(box)
            self._group_grids.append(grid)
            if rows is info.listening:
                self._listening_grid = grid
        right.addStretch(1)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(24)
        body.addWidget(left_w, 0, Qt.AlignTop)
        body.addLayout(right, 1)
        self.content_layout.setContentsMargins(18, 4, 18, 18)
        self.content_layout.addLayout(body)

    def groups(self):
        out = []
        for grid in self._group_grids:
            rows = []
            for r in range(grid.rowCount()):
                key = grid.itemAtPosition(r, 0)
                val = grid.itemAtPosition(r, 1)
                if key is None or val is None:
                    continue
                rows.append((key.widget().text(), val.widget().text()))
            out.append(tuple(rows))
        return out

    def set_listening(self, rows, play_count):
        if self._listening_grid is None:
            return
        _fill_grid(self._listening_grid, rows)
        if self.reset_button is not None:
            self.reset_button.setEnabled(play_count > 0)
