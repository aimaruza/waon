
from PySide6.QtWidgets import QDialogButtonBox, QLabel, QListWidget, QListWidgetItem

from waon.ui.overlay_dialog import OverlayDialog

_REASONS = {"not_found": "not found", "ambiguous": "ambiguous"}


def _plural(n, noun):
    return "{:,} {}{}".format(n, noun, "" if n == 1 else "s")


def import_summary(result):
    created = sum(1 for p in result.playlists if p.status == "created")
    return "Restored {:,} of {}, {} and {}.".format(
        result.plays_imported, _plural(result.plays_total, "play"),
        _plural(created, "playlist"),
        _plural(result.favorites_imported, "favorite"))


def _playlist_line(line):
    if line.status == "skipped_empty":
        return "{} — 0 of {} tracks matched, not created".format(line.name, line.total)
    return "{} — created ({} of {} tracks matched)".format(
        line.name, line.matched, line.total)


class LibraryImportResultsDialog(OverlayDialog):
    def __init__(self, result, parent=None):
        super().__init__("Backup restored", parent, min_width=480)
        layout = self.content_layout
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        summary = QLabel(import_summary(result))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.playlist_list = QListWidget()
        for line in result.playlists:
            self.playlist_list.addItem(QListWidgetItem(_playlist_line(line)))
        self.playlist_list.setVisible(bool(result.playlists))
        layout.addWidget(self.playlist_list)

        self.unmatched_label = QLabel("{} couldn't be matched:".format(
            _plural(len(result.unmatched), "track")))
        self.unmatched_label.setObjectName("DialogHint")
        self.unmatched_list = QListWidget()
        for track in result.unmatched:
            self.unmatched_list.addItem(QListWidgetItem("{} – {} ({})".format(
                track.artist, track.title, _REASONS.get(track.reason, track.reason))))
        self.unmatched_label.setVisible(bool(result.unmatched))
        self.unmatched_list.setVisible(bool(result.unmatched))
        layout.addWidget(self.unmatched_label)
        layout.addWidget(self.unmatched_list)

        self.box = QDialogButtonBox(QDialogButtonBox.Ok)
        self.box.accepted.connect(self.accept)
        layout.addWidget(self.box)
