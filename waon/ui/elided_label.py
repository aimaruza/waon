
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


LEFT_ALIGNED = Qt.AlignLeft | Qt.AlignVCenter | Qt.AlignAbsolute


class ElidedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text or ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setAlignment(LEFT_ALIGNED)
        self._apply()

    def full_text(self):
        return self._full

    def setText(self, text):
        self._full = text or ""
        self._apply()

    def resizeEvent(self, event):
        self._apply()
        super().resizeEvent(event)

    _FIT_SAFETY_MARGIN = 3

    def _apply(self):
        fm = self.fontMetrics()
        width = max(0, self.contentsRect().width())
        fit_width = max(0, width - self._FIT_SAFETY_MARGIN)
        elided = fm.elidedText(self._full, Qt.ElideRight, fit_width)
        super().setText(elided)
        self.setToolTip(self._full if elided != self._full else "")

    def sizeHint(self):
        return QSize(0, super().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())
