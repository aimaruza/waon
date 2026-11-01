
from PySide6.QtCore import QEvent, QEventLoop, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from waon.ui import motion
from waon.ui.icons import IconButton
from waon.ui.title_bar import forward_scrim_double_click, forward_scrim_press


class OverlayDialog(QWidget):
    accepted = Signal()
    rejected = Signal()

    def __init__(self, title, parent=None, min_width=0, flat_icons=False):
        super().__init__(parent)
        self.setObjectName("DialogScrim")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._result = QDialog.Rejected
        self._loop = None
        self._build_shell(title, flat_icons)
        if min_width:
            self.card.setMinimumWidth(min_width)
        self.hide()
        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())

    def _build_shell(self, title, flat_icons=False):
        title_label = QLabel(title)
        title_label.setObjectName("DialogHeaderTitle")
        self.close_button = IconButton("close", "Close", icon_size=14, diameter=28,
                                        pill_hover=not flat_icons)
        self.close_button.clicked.connect(self.reject)

        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(18, 14, 14, 14)
        self.header_layout.addWidget(title_label)
        self.header_layout.addStretch(1)
        self.header_layout.addWidget(self.close_button)

        self.content_layout = QVBoxLayout()

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        card_layout.addLayout(self.header_layout)
        card_layout.addLayout(self.content_layout, 1)

        self.card = QWidget()
        self.card.setObjectName("DialogCard")
        self.card.setLayout(card_layout)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def eventFilter(self, watched, event):
        if watched is self.parent() and event.type() == QEvent.Resize:
            self.setGeometry(watched.rect())
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        if not event.spontaneous():
            motion.fade_in(self, motion.ENTRANCE_MS, rise=motion.ENTRANCE_RISE,
                           rise_widget=self.card)

    def mousePressEvent(self, event):
        if not forward_scrim_press(self, event):
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not forward_scrim_double_click(self, event):
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def exec(self):
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self._loop = QEventLoop()
        self._loop.exec()
        return self._result

    def accept(self):
        self._result = QDialog.Accepted
        self._finish()
        self.accepted.emit()

    def reject(self):
        self._result = QDialog.Rejected
        self._finish()
        self.rejected.emit()

    def _finish(self):
        self.hide()
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
