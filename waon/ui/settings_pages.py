
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from waon.settings import categories, groups
from waon.ui.settings_about import AboutPage
from waon.ui.settings_rows import make_row
from waon.ui.settings_scroll_page import SettingsScrollPage

log = logging.getLogger(__name__)

RESET_ALL_TITLE = "Reset all settings"
RESET_ALL_TEXT = "Reset all settings to their defaults? This can't be undone."


def build_category_page(settings, category):
    scroll = SettingsScrollPage()
    layout = scroll.content_layout

    title = QLabel(category)
    title.setObjectName("SettingsPageTitle")
    layout.addWidget(title)
    layout.addSpacing(6)

    for group, members in groups(category, settings.registry):
        if group is not None:
            label = QLabel(group.upper())
            label.setObjectName("SettingsGroupLabel")
            layout.addWidget(label)
        card = QWidget()
        card.setObjectName("SettingsGroupCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        for i, setting in enumerate(members):
            if i:
                divider = QWidget()
                divider.setObjectName("SettingsRowDivider")
                divider.setAttribute(Qt.WA_StyledBackground, True)
                divider.setFixedHeight(1)
                card_layout.addWidget(divider)
            card_layout.addWidget(make_row(settings, setting))
        layout.addWidget(card)
        layout.addSpacing(10)

    layout.addStretch(1)
    return scroll


def install(overlay, settings, confirm):
    for category in categories(settings.registry):
        overlay.add_page(category, build_category_page(settings, category))
    overlay.add_page("About", AboutPage(), pinned=True)

    def reset_all():
        if confirm(RESET_ALL_TITLE, RESET_ALL_TEXT):
            settings.reset_all()

    overlay.set_reset_all_handler(reset_all)
