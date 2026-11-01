
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSlider


class ClickSlider(QSlider):
    def _value_from_pos(self, x):
        lo, hi = self.minimum(), self.maximum()
        if hi == lo:
            return lo
        width = max(1, self.width())
        ratio = min(1.0, max(0.0, x / width))
        return int(round(lo + ratio * (hi - lo)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setSliderDown(True)
            value = self._value_from_pos(event.position().x())
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            value = self._value_from_pos(event.position().x())
            self.setValue(value)
            self.sliderMoved.emit(value)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.isSliderDown():
            value = self._value_from_pos(event.position().x())
            self.setValue(value)
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)
