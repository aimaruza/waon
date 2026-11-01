
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from waon.ui.icons import render_app_icon

_BRAND_PANEL_W = 240
_ICON_SIZE = 96


class WelcomePage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomePage")
        self._build()

    def _build(self):
        brand_panel = QWidget()
        brand_panel.setObjectName("WelcomeBrandPanel")
        brand_panel.setAttribute(Qt.WA_StyledBackground, True)
        brand_panel.setFixedWidth(_BRAND_PANEL_W)

        icon_label = QLabel()
        icon_label.setPixmap(render_app_icon(_ICON_SIZE))
        icon_label.setAlignment(Qt.AlignCenter)
        wordmark = QLabel("waon")
        wordmark.setObjectName("WelcomeWordmark")
        wordmark.setAlignment(Qt.AlignCenter)

        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setAlignment(Qt.AlignCenter)
        brand_layout.setSpacing(12)
        brand_layout.addWidget(icon_label)
        brand_layout.addWidget(wordmark)

        headline = QLabel("Welcome to waon")
        headline.setObjectName("WelcomeHeadline")
        self.subtext = QLabel("waon is a music organizer and player.")
        self.subtext.setObjectName("WelcomeSubtext")
        self.subtext.setWordWrap(True)


        content = QVBoxLayout()
        content.setContentsMargins(48, 0, 48, 0)
        content.setSpacing(10)
        content.addStretch(1)
        content.addWidget(headline)
        content.addWidget(self.subtext)
        content.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(brand_panel)
        layout.addLayout(content, 1)
