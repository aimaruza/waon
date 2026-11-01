
import logging
import os

from PySide6.QtWidgets import QTextBrowser

import waon
from waon.ui.overlay_dialog import OverlayDialog

log = logging.getLogger(__name__)

CHANGELOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(waon.__file__))),
    "CHANGELOG.md")

MISSING_TEXT = "The changelog couldn't be loaded."


def read_changelog(path=CHANGELOG_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        log.warning("could not read the changelog at %s", path, exc_info=True)
        return None


class ChangelogDialog(OverlayDialog):
    def __init__(self, markdown, parent=None):
        super().__init__("Changelog", parent, min_width=560, flat_icons=True)
        self.browser = QTextBrowser()
        self.browser.setObjectName("ChangelogText")
        self.browser.setOpenExternalLinks(True)
        self.browser.setMinimumHeight(420)
        if markdown is None:
            self.browser.setPlainText(MISSING_TEXT)
        else:
            lines = markdown.lstrip().splitlines()
            if lines and lines[0].startswith("# "):
                lines = lines[1:]
            self.browser.setMarkdown("\n".join(lines))
        self.content_layout.setContentsMargins(18, 0, 6, 18)
        self.content_layout.addWidget(self.browser)
