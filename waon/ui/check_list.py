
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QListWidget, QStyledItemDelegate, QStyleOptionViewItem

from waon.ui import theme
from waon.ui.icons import render_icon

_BOX_SIZE = 18
_LOCK_SIZE = 16
_LOCK_GAP = 6
_BOX_GLYPH = {Qt.Checked: "check-square", Qt.PartiallyChecked: "minus-square",
              Qt.Unchecked: "square"}


class CheckBoxDelegate(QStyledItemDelegate):

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.features &= ~QStyleOptionViewItem.HasCheckIndicator
        pixmap = self.decoration(index)
        option.icon = QIcon(pixmap)
        option.decorationSize = QSize(
            round(pixmap.width() / pixmap.devicePixelRatio()), _BOX_SIZE)
        option.features |= QStyleOptionViewItem.HasDecoration

    def decoration(self, index):
        state = Qt.CheckState(index.data(Qt.CheckStateRole))
        if index.flags() & Qt.ItemIsEnabled:
            return render_icon(_BOX_GLYPH[state], theme.ICON, _BOX_SIZE)
        box = render_icon(_BOX_GLYPH[state], theme.DISABLED, _BOX_SIZE)
        lock = render_icon("lock-simple", theme.DISABLED, _LOCK_SIZE)
        dpr = box.devicePixelRatio()
        width = _BOX_SIZE + _LOCK_GAP + _LOCK_SIZE
        pixmap = QPixmap(round(width * dpr), round(_BOX_SIZE * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.drawPixmap(0, 0, box)
        painter.drawPixmap(_BOX_SIZE + _LOCK_GAP, (_BOX_SIZE - _LOCK_SIZE) // 2, lock)
        painter.end()
        return pixmap


class CheckList(QListWidget):

    def __init__(self, toggle, parent=None):
        super().__init__(parent)
        self._toggle = toggle

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and self.currentItem() is not None:
            self._toggle(self.currentItem())
            return
        super().keyPressEvent(event)
