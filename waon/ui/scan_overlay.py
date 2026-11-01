
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from waon.ui.elided_label import ElidedLabel

CARD_W = 420


def result_summary(result):
    parts = []
    if result.added:
        parts.append("{:,} added".format(result.added))
    if result.updated:
        parts.append("{:,} updated".format(result.updated))
    if result.skipped:
        parts.append("{:,} unchanged".format(result.skipped))
    if result.relinked:
        parts.append("{:,} moved".format(result.relinked))
    if result.missing:
        parts.append("{:,} missing".format(result.missing))
    if result.duplicates:
        parts.append("{:,} duplicate relative path{}".format(
            result.duplicates, "" if result.duplicates == 1 else "s"))
    return u" • ".join(parts) if parts else "Nothing changed"


class ScanOverlay(QWidget):

    cancelRequested = Signal()
    dismissed = Signal()

    def __init__(self, parent=None, cover=None):
        super().__init__(parent)
        self.setObjectName("ScanScrim")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._finished = False
        self._cover = cover if cover is not None else parent
        self._build()
        self.hide()
        if self._cover is not None:
            self._cover.installEventFilter(self)
            self._sync_geometry()

    def _sync_geometry(self):
        if self._cover is None:
            return
        if self._cover is self.parent():
            self.setGeometry(self._cover.rect())
        else:
            top_left = self._cover.mapTo(self.parent(), self._cover.rect().topLeft())
            self.setGeometry(top_left.x(), top_left.y(),
                             self._cover.width(), self._cover.height())

    def _build(self):
        self.title_label = QLabel("")
        self.title_label.setObjectName("ScanTitle")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("ScanDetail")
        self.dir_label = ElidedLabel("")
        self.dir_label.setObjectName("ScanDetail")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ScanBar")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.action_button = QPushButton("Cancel")
        self.action_button.setCursor(Qt.PointingHandCursor)
        self.action_button.clicked.connect(self._on_action)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        buttons.addWidget(self.action_button)

        card = QWidget()
        card.setObjectName("ScanCard")
        card.setFixedWidth(CARD_W)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 16)
        card_layout.setSpacing(8)
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.detail_label)
        card_layout.addWidget(self.dir_label)
        card_layout.addWidget(self.progress_bar)
        card_layout.addLayout(buttons)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def eventFilter(self, watched, event):
        if watched is self._cover and event.type() == QEvent.Resize:
            self._sync_geometry()
        return super().eventFilter(watched, event)

    def is_active(self):
        return not self.isHidden()

    def start(self, library_name):
        self._finished = False
        self.title_label.setText(u"Scanning {}…".format(library_name))
        self.detail_label.setText("0 files seen • 0 tracks found")
        self.dir_label.setText("")
        self.progress_bar.show()
        self.action_button.setText("Cancel")
        self.action_button.setEnabled(True)
        self._sync_geometry()
        self.show()
        self.raise_()

    def set_progress(self, progress):
        self.detail_label.setText(u"{:,} files seen • {:,} tracks found".format(
            progress.files_seen, progress.tracks_found))
        self.dir_label.setText(progress.current_dir)

    def show_result(self, result):
        self.title_label.setText(
            "Scan stopped" if result.cancelled else "Scan complete")
        self.detail_label.setText(result_summary(result))
        self._finish()

    def show_failure(self, message):
        self.title_label.setText("Scan failed")
        self.detail_label.setText(message)
        self._finish()

    def _finish(self):
        self._finished = True
        self.dir_label.setText("")
        self.progress_bar.hide()
        self.action_button.setText("Done")
        self.action_button.setEnabled(True)
        self.show()
        self.raise_()

    def _on_action(self):
        if self._finished:
            self.hide()
            self.dismissed.emit()
            return
        self.action_button.setEnabled(False)
        self.cancelRequested.emit()
