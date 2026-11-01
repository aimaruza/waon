
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

from waon.library.entities import ALL_LIBRARIES_ID, ALL_LIBRARIES_NAME
from waon.ui import theme
from waon.ui.icons import render_icon, render_swatch
from waon.ui.popup_menu import PopupMenu, PopupMenuRow

BAR_H = 48
LIBRARY_BUTTON_W = 270
_SWATCH_SIZE = 24
_GEAR_D = 32
_GEAR_ICON = 18
_ROW_ICON_SIZE = 26
_ALL_COLOR = theme.TEXT_MUTED


class _GearButton(QAbstractButton):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("Library settings")
        self.setFixedSize(_GEAR_D, _GEAR_D)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False

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
        if self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.BORDER))
            painter.drawRect(self.rect())
        pm = render_icon("gear-wide-connected", theme.ICON, _GEAR_ICON)
        x = (self.width() - _GEAR_ICON) // 2
        y = (self.height() - _GEAR_ICON) // 2
        painter.drawPixmap(x, y, pm)
        painter.end()


class _LibraryButton(QAbstractButton):

    _TEXT_PAD = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_pixmap = None
        self._name = "No library"
        self._hover = False
        self.setFixedSize(LIBRARY_BUTTON_W, _GEAR_D)
        self.setCursor(Qt.PointingHandCursor)

    def set_icon_pixmap(self, pixmap):
        self._icon_pixmap = pixmap
        self.update()

    def icon_pixmap(self):
        return self._icon_pixmap

    def set_display_name(self, name):
        self._name = name
        self.update()

    def text(self):
        return self._name

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
            painter.setBrush(QColor(theme.BORDER))
            painter.drawRect(self.rect().adjusted(_GEAR_D, 0, 0, 0))
        if self._icon_pixmap is not None:
            dpr = self._icon_pixmap.devicePixelRatio()
            w = round(self._icon_pixmap.width() / dpr)
            h = round(self._icon_pixmap.height() / dpr)
            x = (_GEAR_D - w) // 2
            y = (self.height() - h) // 2
            painter.drawPixmap(x, y, self._icon_pixmap)
        color = theme.DISABLED if not self.isEnabled() else theme.TEXT
        font = QFont(painter.font())
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        text_rect = self.rect().adjusted(_GEAR_D + self._TEXT_PAD, 0,
                                         -self._TEXT_PAD, 0)
        elided = painter.fontMetrics().elidedText(
            self._name, Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.end()


class _DropdownRow(PopupMenuRow):

    def __init__(self, icon_pixmap, text, current=False, enabled=True, parent=None):
        super().__init__(icon_pixmap, text, _ROW_ICON_SIZE, enabled=enabled,
                         parent=parent)
        self._current = current
        if enabled and current:
            self.text_label.setStyleSheet(
                "background: transparent; color: {}; font-weight: 600;"
                .format(theme.TEXT))

    def is_current(self):
        return self._current


class _LibraryDropdown(PopupMenu):

    librarySelected = Signal(str)
    addLibraryRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(icon_size=_ROW_ICON_SIZE, parent=parent)
        self.setFixedWidth(LIBRARY_BUTTON_W)
        self.add_row = None

    def set_libraries(self, libraries, current_id, broken_ids, show_all=False):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []

        if show_all:
            pixmap = render_swatch(_ALL_COLOR, _ROW_ICON_SIZE, "all-libraries")
            row = _DropdownRow(pixmap, ALL_LIBRARIES_NAME,
                               current=current_id == ALL_LIBRARIES_ID, parent=self)
            row.library_id = ALL_LIBRARIES_ID
            row.clicked.connect(lambda _=False: self._choose(ALL_LIBRARIES_ID))
            self._layout.addWidget(row)
            self._rows.append(row)

        for library in libraries:
            broken = library.id in broken_ids
            text = library.name if not broken else "{} (unreadable)".format(library.name)
            pixmap = render_swatch(library.color, _ROW_ICON_SIZE, library.icon)
            row = _DropdownRow(pixmap, text, current=library.id == current_id,
                               enabled=not broken, parent=self)
            row.library_id = library.id
            row.clicked.connect(
                lambda _=False, lib_id=library.id: self._choose(lib_id))
            self._layout.addWidget(row)
            self._rows.append(row)

        if libraries:
            self.add_separator()

        add_pixmap = render_icon("plus", theme.ICON, _ROW_ICON_SIZE)
        self.add_row = _DropdownRow(add_pixmap, "New library…", parent=self)
        self.add_row.clicked.connect(self._choose_add)
        self._layout.addWidget(self.add_row)

    def _choose(self, library_id):
        self.close()
        self.librarySelected.emit(library_id)

    def _choose_add(self):
        self.close()
        self.addLibraryRequested.emit()


class LibraryBar(QWidget):

    librarySelected = Signal(str)
    addLibraryRequested = Signal()
    librarySettingsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(BAR_H)
        self._current_id = None
        self._build()

    def _build(self):
        self.library_button = _LibraryButton()
        self.library_button.clicked.connect(self._show_dropdown)

        self.dropdown = _LibraryDropdown(self)
        self.dropdown.librarySelected.connect(self._choose)
        self.dropdown.addLibraryRequested.connect(self.addLibraryRequested)

        self.gear_button = _GearButton()
        self.gear_button.clicked.connect(self.librarySettingsRequested)

        self.split_frame = QWidget()
        self.split_frame.setObjectName("LibrarySplitButton")
        self.split_frame.setAttribute(Qt.WA_StyledBackground, True)
        divider = QWidget()
        divider.setObjectName("LibrarySplitDivider")
        divider.setFixedWidth(1)
        split_layout = QHBoxLayout(self.split_frame)
        split_layout.setContentsMargins(1, 1, 1, 1)
        split_layout.setSpacing(0)
        split_layout.addWidget(self.library_button)
        split_layout.addWidget(divider)
        split_layout.addWidget(self.gear_button)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(6)
        layout.addWidget(self.split_frame, 0, Qt.AlignVCenter)
        layout.addStretch(1)

        self.set_libraries([], None)

    def set_libraries(self, libraries, current_id, broken_ids=(), show_all=False):
        broken_ids = set(broken_ids)
        self._current_id = current_id
        self.dropdown.set_libraries(libraries, current_id, broken_ids, show_all)

        if current_id == ALL_LIBRARIES_ID:
            self.library_button.set_display_name(ALL_LIBRARIES_NAME)
            self.library_button.setToolTip(ALL_LIBRARIES_NAME)
            self.library_button.set_icon_pixmap(
                render_swatch(_ALL_COLOR, _SWATCH_SIZE, "all-libraries"))
            self.gear_button.setEnabled(False)
            return

        current = next((l for l in libraries if l.id == current_id), None)
        if current is None:
            self.library_button.set_display_name("No library")
            self.library_button.set_icon_pixmap(render_icon("note", theme.ICON, _SWATCH_SIZE))
            self.library_button.setToolTip("")
        else:
            self.library_button.set_display_name(current.name)
            self.library_button.setToolTip(current.name)
            self.library_button.set_icon_pixmap(
                render_swatch(current.color, _SWATCH_SIZE, current.icon))
        usable = current is not None and current.id not in broken_ids
        self.gear_button.setEnabled(usable)

    def current_library_id(self):
        return self._current_id

    def library_actions(self):
        return self.dropdown.rows()

    def _show_dropdown(self):
        pos = self.library_button.mapToGlobal(QPoint(0, self.library_button.height()))
        self.dropdown.popup_at(pos)

    def _choose(self, library_id):
        if library_id == self._current_id:
            return
        self.librarySelected.emit(library_id)
