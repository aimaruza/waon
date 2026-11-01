
import logging

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

import waon
from waon import logging_setup
from waon.library import locations
from waon.ui.changelog_dialog import ChangelogDialog, read_changelog
from waon.ui.elided_label import ElidedLabel
from waon.ui.icons import render_app_icon
from waon.ui.settings_scroll_page import SettingsScrollPage

log = logging.getLogger(__name__)

PROJECT_URL = "https://github.com/aimaruza/waon"
APP_LICENSE = "GPL-3.0"

LOGO_DESIGNER = "Amer Safi"
LOGO_DESIGNER_EMAIL = "mailto:amerosafi@gmail.com"
LOGO_DESIGNER_TELEGRAM = "https://t.me/aosafi"

FFMPEG_SOURCE_URL = "https://github.com/FFmpeg/FFmpeg/commit/ea3d24bbe3"

CREDITS = (
    ("Qt for Python (PySide6)", "LGPL-3.0", None),
    ("ffpyplayer", "LGPL-3.0", None),
    ("FFmpeg", "GPL-3.0", FFMPEG_SOURCE_URL),
    ("SDL2", "zlib", None),
    ("mutagen", "GPL-2.0-or-later", None),
    ("Phosphor Icons", "MIT", None),
)

_LOGO = 56


def _group_label(text):
    label = QLabel(text.upper())
    label.setObjectName("SettingsGroupLabel")
    return label


def _card(rows):
    card = QWidget()
    card.setObjectName("SettingsGroupCard")
    card.setAttribute(Qt.WA_StyledBackground, True)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for i, row in enumerate(rows):
        if i:
            divider = QWidget()
            divider.setObjectName("SettingsRowDivider")
            divider.setAttribute(Qt.WA_StyledBackground, True)
            divider.setFixedHeight(1)
            layout.addWidget(divider)
        layout.addWidget(row)
    return card


def _row(left, right=None):
    row = QWidget()
    row.setObjectName("SettingsRow")
    row.setAttribute(Qt.WA_StyledBackground, True)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(16, 10, 12, 10)
    layout.setSpacing(10)
    layout.addWidget(left, 1)
    if right is not None:
        layout.addWidget(right)
    return row


class AboutPage(SettingsScrollPage):

    def __init__(self, data_dir=None, logs_dir=None, open_url=None,
                 show_changelog=None, parent=None):
        super().__init__(parent)
        self._open_url = open_url or QDesktopServices.openUrl
        self._show_changelog = show_changelog or self._open_changelog
        data_dir = data_dir or locations.app_data_dir()
        logs_dir = logs_dir or logging_setup.log_dir()

        layout = self.content_layout

        logo = QLabel()
        logo.setPixmap(render_app_icon(_LOGO))
        logo.setFixedSize(_LOGO, _LOGO)
        self.name_label = QLabel("waon")
        self.name_label.setObjectName("AboutName")
        self.version_label = QLabel("Version {}".format(waon.__version__))
        self.version_label.setObjectName("AboutMeta")
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(self.name_label)
        names.addWidget(self.version_label)
        identity = QHBoxLayout()
        identity.setSpacing(14)
        identity.addWidget(logo, 0, Qt.AlignTop)
        identity.addLayout(names, 1)
        layout.addLayout(identity)
        layout.addSpacing(10)

        self.link_button = QPushButton(PROJECT_URL.replace("https://", ""))
        self.link_button.setObjectName("AboutLink")
        self.link_button.setCursor(Qt.PointingHandCursor)
        self.link_button.clicked.connect(lambda: self._open(QUrl(PROJECT_URL)))
        license_name = QLabel("License")
        license_name.setObjectName("SettingsRowLabel")
        self.license_label = QLabel(APP_LICENSE)
        self.license_label.setObjectName("AboutMeta")
        changelog_name = QLabel("Changelog")
        changelog_name.setObjectName("SettingsRowLabel")
        self.changelog_button = QPushButton("View")
        self.changelog_button.setObjectName("AboutOpenFolder")
        self.changelog_button.setCursor(Qt.PointingHandCursor)
        self.changelog_button.clicked.connect(lambda: self._show_changelog())
        logo_credit_name = QLabel("Logo design")
        logo_credit_name.setObjectName("SettingsRowLabel")
        self.logo_credit_label = QLabel(LOGO_DESIGNER)
        self.logo_credit_label.setObjectName("AboutMeta")
        self.logo_email_button = self._link_button("Email", LOGO_DESIGNER_EMAIL)
        self.logo_telegram_button = self._link_button("Telegram",
                                                      LOGO_DESIGNER_TELEGRAM)
        logo_credit_row = _row(logo_credit_name, self.logo_credit_label)
        logo_credit_row.layout().addWidget(self.logo_email_button)
        logo_credit_row.layout().addWidget(self.logo_telegram_button)
        layout.addWidget(_group_label("Project"))
        layout.addWidget(_card([_row(self.link_button),
                                _row(license_name, self.license_label),
                                _row(changelog_name, self.changelog_button),
                                logo_credit_row]))
        layout.addSpacing(10)

        data_row, self.data_path_label, self.open_data_button = \
            self._folder_row("Data", data_dir)
        logs_row, self.logs_path_label, self.open_logs_button = \
            self._folder_row("Logs", logs_dir)
        layout.addWidget(_group_label("Folders"))
        layout.addWidget(_card([data_row, logs_row]))
        layout.addSpacing(10)

        self.credit_rows = []
        self.source_buttons = {}
        for name, license_name, source_url in CREDITS:
            label = QLabel(name)
            label.setObjectName("SettingsRowLabel")
            license_label = QLabel(license_name)
            license_label.setObjectName("AboutMeta")
            row = _row(label, license_label)
            if source_url is not None:
                button = QPushButton("Source")
                button.setObjectName("AboutLink")
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(
                    lambda _=False, url=source_url: self._open(QUrl(url)))
                row.layout().addWidget(button)
                self.source_buttons[name] = button
            self.credit_rows.append(row)
        layout.addWidget(_group_label("Credits & licenses"))
        layout.addWidget(_card(self.credit_rows))
        layout.addStretch(1)

    def _link_button(self, text, url):
        button = QPushButton(text)
        button.setObjectName("AboutLink")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _=False: self._open(QUrl(url)))
        return button

    def _folder_row(self, title, path):
        name = QLabel(title)
        name.setObjectName("SettingsRowLabel")
        path_label = ElidedLabel(path)
        path_label.setObjectName("AboutPath")
        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        text_layout.addWidget(name)
        text_layout.addWidget(path_label)
        button = QPushButton("Open folder")
        button.setObjectName("AboutOpenFolder")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda: self._open(QUrl.fromLocalFile(path)))
        return _row(text, button), path_label, button

    def _open_changelog(self):
        dialog = ChangelogDialog(read_changelog(), self.window())
        dialog.exec()
        dialog.deleteLater()

    def _open(self, url):
        if not self._open_url(url):
            log.warning("could not open %s", url.toString())
