
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

MARGIN_BOTTOM = 24
HIDE_MS = 2500


class Toast(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._label = QLabel("")
        self._label.setObjectName("ToastLabel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.addWidget(self._label)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()
        parent.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.parent() and event.type() == QEvent.Resize:
            self._reposition()
        return super().eventFilter(watched, event)

    def show_message(self, text):
        self._label.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(HIDE_MS)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.move((parent.width() - self.width()) // 2,
                  parent.height() - self.height() - MARGIN_BOTTOM)
