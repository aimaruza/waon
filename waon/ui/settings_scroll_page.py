
import logging

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

log = logging.getLogger(__name__)


class SettingsScrollPage(QScrollArea):
    MARGINS = (24, 18, 24, 24)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPageScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("SettingsPage")
        self.content_layout = QVBoxLayout(inner)
        self.content_layout.setContentsMargins(*self.MARGINS)
        self.content_layout.setSpacing(8)
        self.setWidget(inner)

        self.verticalScrollBar().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (watched is self.verticalScrollBar()
                and event.type() in (QEvent.Show, QEvent.Hide, QEvent.Resize)):
            self._fit_gutter()
        return super().eventFilter(watched, event)

    def _fit_gutter(self):
        left, top, right, bottom = self.MARGINS
        bar = self.verticalScrollBar()
        if bar.isVisible():
            right = max(0, right - bar.width())
        self.content_layout.setContentsMargins(left, top, right, bottom)
