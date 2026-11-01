
import logging

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from waon.settings import CHOICE, TOGGLE
from waon.ui import theme
from waon.ui.icons import render_icon
from waon.ui.popup_menu import PopupMenu

log = logging.getLogger(__name__)


class ToggleSwitch(QAbstractButton):

    _W = 34
    _H = 18
    _INSET = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(self._W, self._H)

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        track = theme.BRAND if self.isChecked() else theme.TOGGLE_OFF
        painter.fillRect(self.rect(), QColor(track))
        knob = self._H - 2 * self._INSET
        x = self._W - self._INSET - knob if self.isChecked() else self._INSET
        painter.fillRect(x, self._INSET, knob, knob, QColor("#FFFFFF"))
        painter.end()


class _SettingRow(QWidget):
    def __init__(self, settings, setting, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setting = setting
        self.setObjectName("SettingsRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.label = QLabel(setting.label)
        self.label.setObjectName("SettingsRowLabel")
        self.label.setWordWrap(True)
        self.hint_label = QLabel(setting.hint)
        self.hint_label.setObjectName("SettingsRowHint")
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(setting.hint))

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        text.addWidget(self.label)
        text.addWidget(self.hint_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(10)
        layout.addLayout(text, 1)
        layout.addWidget(self._build_control())

        settings.changed.connect(self._on_changed)
        self.refresh()
        self._apply_enabled()

    def _build_control(self):
        raise NotImplementedError

    def _show_value(self, value):
        raise NotImplementedError

    def refresh(self):
        self._show_value(self.settings.get(self.setting.key))

    def _set(self, value):
        self.settings.set(self.setting.key, value)
        self.refresh()

    def _on_changed(self, key, value):
        if key == self.setting.key:
            self.refresh()
        elif key == self.setting.enabled_by:
            self._apply_enabled()

    def _apply_enabled(self):
        if self.setting.enabled_by is not None:
            self.setEnabled(bool(self.settings.get(self.setting.enabled_by)))
            if not self.isEnabled():
                self._set_hovering(False)

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


class ToggleRow(_SettingRow):
    def _build_control(self):
        self.switch = ToggleSwitch()
        self.switch.clicked.connect(lambda _checked: self._toggle())
        return self.switch

    def _show_value(self, value):
        self.switch.setChecked(bool(value))

    def _toggle(self):
        self._set(not self.settings.get(self.setting.key))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._toggle()
            event.accept()
            return
        super().mousePressEvent(event)


class ChoiceRow(_SettingRow):
    def _build_control(self):
        self.button = QPushButton()
        self.button.setObjectName("SettingsChoiceButton")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setIcon(QIcon(render_icon("chevron-down", theme.ICON, 12)))
        self.button.setIconSize(QSize(12, 12))
        self.button.setLayoutDirection(Qt.RightToLeft)
        self.button.clicked.connect(self.open_menu)
        return self.button

    def _show_value(self, value):
        self.button.setText(self.setting.value_label(value))

    def build_menu(self):
        menu = PopupMenu(parent=self)
        current = self.settings.get(self.setting.key)
        for value, label in self.setting.choices:
            menu.add_action(None, label, lambda v=value: self._set(v),
                            checked=(value == current))
        return menu

    def open_menu(self):
        menu = self.build_menu()
        menu.setAttribute(Qt.WA_DeleteOnClose, True)
        menu.popup_at(self.button.mapToGlobal(QPoint(0, self.button.height())))


def make_row(settings, setting):
    if setting.kind == TOGGLE:
        return ToggleRow(settings, setting)
    if setting.kind == CHOICE:
        return ChoiceRow(settings, setting)
    raise ValueError("no row for setting kind {!r}".format(setting.kind))
