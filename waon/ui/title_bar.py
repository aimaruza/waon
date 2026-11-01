
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QWidget

from waon.ui import theme
from waon.ui.icons import IconButton, render_icon, render_logo_mark
from waon.ui.library_bar import BAR_H, LibraryBar

CAPTION_W = 46
_GLYPH_SIZE = 14


class CaptionButton(QAbstractButton):

    def __init__(self, name, tooltip, danger=False, parent=None):
        super().__init__(parent)
        self._name = name
        self._danger = danger
        self._hover = False
        self.setFixedSize(CAPTION_W, BAR_H)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(tooltip)

    def set_name(self, name):
        if name != self._name:
            self._name = name
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._hover:
            painter.setPen(Qt.NoPen)
            color = theme.CLOSE_HOVER if self._danger else theme.BORDER
            painter.setBrush(QColor(color))
            painter.drawRect(self.rect())
        glyph_color = "#FFFFFF" if (self._hover and self._danger) else theme.ICON
        pm = render_icon(self._name, glyph_color, _GLYPH_SIZE)
        x = (self.width() - _GLYPH_SIZE) // 2
        y = (self.height() - _GLYPH_SIZE) // 2
        painter.drawPixmap(x, y, pm)
        painter.end()


class TitleBar(QWidget):

    minimizeRequested = Signal()
    maximizeRequested = Signal()
    closeRequested = Signal()
    settingsRequested = Signal()

    LOGO_HEIGHT = 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_H)
        self._build()

    def _build(self):
        self.app_icon = QLabel()
        self.app_icon.setObjectName("TitleBarLogo")
        logo = render_logo_mark(self.LOGO_HEIGHT)
        self.app_icon.setPixmap(logo)
        self.app_icon.setFixedSize(logo.deviceIndependentSize().toSize())

        self.settings_button = IconButton("gear", "Settings", icon_size=18, diameter=32)
        self.settings_button.clicked.connect(self.settingsRequested)

        self.minimize_button = CaptionButton("minimize", "Minimize")
        self.maximize_button = CaptionButton("maximize", "Maximize")
        self.close_button = CaptionButton("close", "Close", danger=True)
        self.minimize_button.clicked.connect(self.minimizeRequested)
        self.maximize_button.clicked.connect(self.maximizeRequested)
        self.close_button.clicked.connect(self.closeRequested)

        self.library_bar = LibraryBar()

        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addSpacing(8)
        right.addWidget(self.settings_button)
        right.addSpacing(8)
        right.addWidget(self.minimize_button)
        right.addWidget(self.maximize_button)
        right.addWidget(self.close_button)
        self._right_zone = QWidget()
        self._right_zone.setObjectName("TitleBarZone")
        self._right_zone.setLayout(right)

        left = QHBoxLayout()
        left.setContentsMargins(14, 0, 0, 0)
        left.addWidget(self.app_icon)
        left.addStretch(1)
        self._left_zone = QWidget()
        self._left_zone.setObjectName("TitleBarZone")
        self._left_zone.setLayout(left)

        side_w = max(self._left_zone.sizeHint().width(),
                     self._right_zone.sizeHint().width())
        self._left_zone.setFixedWidth(side_w)
        self._right_zone.setFixedWidth(side_w)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._left_zone)
        row.addStretch(1)
        row.addWidget(self.library_bar)
        row.addStretch(1)
        row.addWidget(self._right_zone)

    def set_maximized(self, is_maximized):
        self.maximize_button.set_name("restore" if is_maximized else "maximize")
        self.maximize_button.setToolTip("Restore" if is_maximized else "Maximize")

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.start_move(event.globalPosition().toPoint())

    def start_move(self, global_pos):
        window = self.window()
        handle = window.windowHandle()
        if handle is None:
            return
        if window.isMaximized():
            self._restore_under_cursor(window, global_pos)
        handle.startSystemMove()
        window.resync_hover_at_cursor()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.maximizeRequested.emit()

    def is_drag_area(self, global_pos):
        pos = self.mapFromGlobal(global_pos)
        if not self.rect().contains(pos):
            return False
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, QAbstractButton):
                return False
            child = child.parentWidget()
        return True

    def _restore_under_cursor(self, window, global_pos):
        maximized_x = window.x()
        maximized_width = window.width()
        restored_width = window.normalGeometry().width()
        ratio = (global_pos.x() - maximized_x) / max(1, maximized_width)
        window.showNormal()
        new_x = global_pos.x() - int(ratio * restored_width)
        window.move(new_x, global_pos.y() - 20)


def _bar_under_scrim_press(scrim, event):
    if event.button() != Qt.LeftButton:
        return None
    if scrim.childAt(event.position().toPoint()) is not None:
        return None
    title_bar = getattr(scrim.window(), "title_bar", None)
    if not isinstance(title_bar, TitleBar):
        return None
    if not title_bar.is_drag_area(event.globalPosition().toPoint()):
        return None
    return title_bar


def forward_scrim_press(scrim, event):
    title_bar = _bar_under_scrim_press(scrim, event)
    if title_bar is None:
        return False
    title_bar.start_move(event.globalPosition().toPoint())
    return True


def forward_scrim_double_click(scrim, event):
    title_bar = _bar_under_scrim_press(scrim, event)
    if title_bar is None:
        return False
    title_bar.maximizeRequested.emit()
    return True
