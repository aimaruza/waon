
from PySide6.QtWidgets import QDialogButtonBox, QListWidget, QListWidgetItem

from waon.ui.overlay_dialog import OverlayDialog


class PlaylistImportResultsDialog(OverlayDialog):
    def __init__(self, results, parent=None):
        super().__init__("Playlists imported", parent, min_width=440)
        layout = self.content_layout
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)
        self.list_widget = QListWidget()
        for result in results:
            self.list_widget.addItem(QListWidgetItem(_line(result)))
        layout.addWidget(self.list_widget)
        self.box = QDialogButtonBox(QDialogButtonBox.Ok)
        self.box.accepted.connect(self.accept)
        layout.addWidget(self.box)


def _line(result):
    if result.status == "skipped_empty":
        return "{} — 0 of {} tracks matched, not created".format(
            result.name, result.total)
    if result.status == "skipped_locked":
        return "{} — locked, not changed (unlock it to replace it)".format(result.name)
    if result.status == "created":
        verb = "Created"
    elif result.status == "replaced":
        verb = "Replaced"
    else:
        raise ValueError("unknown playlist import status: {!r}".format(result.status))
    return "{} — {} ({} of {} tracks matched)".format(
        result.name, verb, result.matched, result.total)
