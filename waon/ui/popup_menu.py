
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from waon.ui import motion
from waon.ui import theme
from waon.ui.icons import render_icon

_ROW_MARGINS = (14, 8, 26, 8)
_ROW_ICON_GAP = 12
_BORDER_W = 1
_CARD_INSET = 6
_MIN_WIDTH = 220
_DIVIDER_INSET = 14
_DIVIDER_GAP = 4


class PopupMenuRow(QWidget):

    clicked = Signal()

    def __init__(self, icon_pixmap, text, icon_gutter_width, enabled=True,
                danger=False, parent=None):
        super().__init__(parent)
        self.setObjectName("PopupMenuRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._text = text
        self._icon_pixmap = icon_pixmap
        self.setEnabled(enabled)
        if enabled:
            self.setCursor(Qt.PointingHandCursor)

        self.icon_label = QLabel()
        self.icon_label.setFixedWidth(icon_gutter_width)
        self.icon_label.setStyleSheet("background: transparent;")
        if icon_pixmap is not None:
            self.icon_label.setPixmap(icon_pixmap)
        self.text_label = QLabel(text)
        if not enabled:
            color = theme.DISABLED
        elif danger:
            color = theme.DANGER
        else:
            color = theme.TEXT
        self.text_label.setStyleSheet(
            "background: transparent; color: {};".format(color))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(*_ROW_MARGINS)
        layout.setSpacing(_ROW_ICON_GAP)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label, 1)

    def text(self):
        return self._text

    def icon_pixmap(self):
        return self._icon_pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if self.isEnabled():
            self._set_hovering(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hovering(False)
        super().leaveEvent(event)

    def _set_hovering(self, value):
        self.setProperty("hovering", value)
        self.style().unpolish(self)
        self.style().polish(self)


class PopupMenu(QWidget):

    def __init__(self, icon_size=18, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("PopupMenu")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(_MIN_WIDTH)
        self._icon_size = icon_size
        self._layout = QVBoxLayout(self)
        inset = _BORDER_W + _CARD_INSET
        self._layout.setContentsMargins(_BORDER_W, inset, _BORDER_W, inset)
        self._layout.setSpacing(0)
        self._rows = []

    def rows(self):
        return list(self._rows)

    def structure(self):
        out = []
        for i in range(self._layout.count()):
            widget = self._layout.itemAt(i).widget()
            if isinstance(widget, PopupMenuRow):
                out.append(widget.text())
            elif (widget is not None
                  and widget.objectName() == "PopupMenuDividerHolder"):
                out.append(None)
        return out

    def add_action(self, icon, text, callback, checked=False, enabled=True,
                   danger=False):
        icon_name = "check" if checked else icon
        pixmap = (render_icon(icon_name, self._icon_color(danger, enabled),
                              self._icon_size)
                  if icon_name else None)
        row = PopupMenuRow(pixmap, text, self._icon_size, enabled=enabled,
                           danger=danger, parent=self)
        row.clicked.connect(lambda: self._activate(callback))
        self._layout.addWidget(row)
        self._rows.append(row)
        return row

    def add_separator(self):
        holder = QWidget()
        holder.setObjectName("PopupMenuDividerHolder")
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(_DIVIDER_INSET, _DIVIDER_GAP,
                                         _DIVIDER_INSET, _DIVIDER_GAP)
        divider = QWidget()
        divider.setObjectName("PopupMenuDivider")
        divider.setFixedHeight(1)
        divider.setAttribute(Qt.WA_StyledBackground, True)
        holder_layout.addWidget(divider)
        self._layout.addWidget(holder)

    def popup_at(self, global_pos):
        self._show_clamped(global_pos, self._popup_size())

    def popup_above(self, anchor):
        size = self._popup_size()
        top_right = anchor.mapToGlobal(QPoint(anchor.width(), 0))
        self._show_clamped(
            QPoint(top_right.x() - size.width(), top_right.y() - size.height()),
            size)

    def _popup_size(self):
        self._layout.activate()
        return self.sizeHint().expandedTo(self.minimumSize())

    def _show_clamped(self, global_pos, size):
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        available = screen.availableGeometry()
        x = min(global_pos.x(), available.x() + available.width() - size.width())
        y = min(global_pos.y(), available.y() + available.height() - size.height())
        x = max(x, available.x())
        y = max(y, available.y())
        self.setGeometry(x, y, size.width(), size.height())
        self.show()
        motion.fade_in(self, motion.ENTRANCE_MS, rise=motion.ENTRANCE_RISE)

    def _icon_color(self, danger, enabled):
        if not enabled:
            return theme.DISABLED
        return theme.DANGER if danger else theme.ICON

    def _activate(self, callback):
        self.close()
        callback()
