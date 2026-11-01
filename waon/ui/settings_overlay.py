
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from waon.ui import motion
from waon.ui.icons import IconButton
from waon.ui.title_bar import forward_scrim_double_click, forward_scrim_press

WIDTH_RATIO = 0.65
HEIGHT_RATIO = 0.80
MIN_W, MAX_W = 640, 1000
MIN_H, MAX_H = 420, 760
EDGE = 16
SIDEBAR_W = 180
_PAGE_INDEX = Qt.UserRole


def card_size_for(width, height):
    w = min(max(round(width * WIDTH_RATIO), MIN_W), MAX_W, width - 2 * EDGE)
    h = min(max(round(height * HEIGHT_RATIO), MIN_H), MAX_H, height - 2 * EDGE)
    return QSize(max(w, 0), max(h, 0))


def _rule(name):
    rule = QWidget()
    rule.setObjectName(name)
    rule.setAttribute(Qt.WA_StyledBackground, True)
    rule.setFixedHeight(1)
    return rule


class _FitListWidget(QListWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def sizeHint(self):
        rows = sum(self.sizeHintForRow(i) for i in range(self.count()))
        return QSize(super().sizeHint().width(), rows + 2 * self.frameWidth())

    def minimumSizeHint(self):
        return self.sizeHint()


class SettingsOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsScrim")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._build()
        self.hide()
        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())
            self._fit_card()

    def _build(self):
        title = QLabel("Settings")
        title.setObjectName("SettingsHeaderTitle")
        self.reset_all_button = IconButton("reset", "Reset all settings",
                                           icon_size=14, diameter=28)
        self.reset_all_button.hide()
        self.close_button = IconButton("close", "Close", icon_size=14, diameter=28)
        self.close_button.clicked.connect(self.hide)

        header = QHBoxLayout()
        header.setContentsMargins(18, 14, 14, 14)
        header.setSpacing(4)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.reset_all_button)
        header.addWidget(self.close_button)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("SettingsSidebar")
        self.sidebar.currentRowChanged.connect(
            lambda row: self._on_row_changed(self.sidebar, row))
        self.sidebar.hide()

        self.sidebar_rule = _rule("SettingsSidebarRule")
        self.sidebar_rule.hide()
        self.pinned_sidebar = _FitListWidget()
        self.pinned_sidebar.setObjectName("SettingsPinnedSidebar")
        self.pinned_sidebar.currentRowChanged.connect(
            lambda row: self._on_row_changed(self.pinned_sidebar, row))
        self.pinned_sidebar.hide()

        self.sidebar_panel = QWidget()
        self.sidebar_panel.setObjectName("SettingsSidebarPanel")
        self.sidebar_panel.setAttribute(Qt.WA_StyledBackground, True)
        self.sidebar_panel.setFixedWidth(SIDEBAR_W)
        panel = QVBoxLayout(self.sidebar_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(0)
        panel.addWidget(self.sidebar, 1)
        panel.addWidget(self.sidebar_rule)
        panel.addWidget(self.pinned_sidebar)
        self.sidebar_panel.hide()

        self.placeholder = QLabel("Nothing to configure yet.")
        self.placeholder.setObjectName("SettingsPlaceholder")
        self.placeholder.setAlignment(Qt.AlignCenter)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.placeholder)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.sidebar_panel)
        body.addWidget(self.pages, 1)

        self.card = QWidget()
        self.card.setObjectName("SettingsCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(1, 1, 1, 1)
        card_layout.setSpacing(0)
        card_layout.addLayout(header)
        card_layout.addWidget(_rule("SettingsHeaderRule"))
        card_layout.addLayout(body, 1)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.card)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def _fit_card(self):
        self.card.setFixedSize(card_size_for(self.width(), self.height()))

    def eventFilter(self, watched, event):
        if watched is self.parent() and event.type() == QEvent.Resize:
            self.setGeometry(watched.rect())
            self._fit_card()
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

    def is_active(self):
        return not self.isHidden()

    def open(self):
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
            self._fit_card()
        self.show()
        self.raise_()

    def add_page(self, name, widget, pinned=False):
        first = not self.page_names()
        if first:
            self.sidebar.show()
            self.sidebar_panel.show()
            self.pages.removeWidget(self.placeholder)
        if pinned:
            self.sidebar_rule.show()
            self.pinned_sidebar.show()
        target = self.pinned_sidebar if pinned else self.sidebar
        index = self.pages.addWidget(widget)
        item = QListWidgetItem(name)
        item.setData(_PAGE_INDEX, index)
        target.addItem(item)
        if pinned:
            self.pinned_sidebar.updateGeometry()
        if first:
            target.setCurrentItem(item)

    def _lists(self):
        return (self.sidebar, self.pinned_sidebar)

    def page_names(self):
        return [lst.item(row).text()
                for lst in self._lists() for row in range(lst.count())]

    def select_page(self, name):
        for lst in self._lists():
            for row in range(lst.count()):
                if lst.item(row).text() == name:
                    lst.setCurrentRow(row)
                    return
        raise KeyError(name)

    def set_reset_all_handler(self, callback):
        self.reset_all_button.clicked.connect(callback)
        self.reset_all_button.show()

    def _on_row_changed(self, source, row):
        if row < 0:
            return
        for other in self._lists():
            if other is not source:
                other.blockSignals(True)
                other.setCurrentRow(-1)
                other.clearSelection()
                other.blockSignals(False)
        self.pages.setCurrentIndex(source.item(row).data(_PAGE_INDEX))
