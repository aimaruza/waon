
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialogButtonBox, QLineEdit, QListWidgetItem,
)

from waon.ui.check_list import CheckBoxDelegate, CheckList
from waon.ui.overlay_dialog import OverlayDialog


class AddToPlaylistDialog(OverlayDialog):

    def __init__(self, playlists, membership, track_count, parent=None):
        super().__init__("Add to playlist", parent, min_width=360)
        self._playlists = playlists
        self._membership = membership
        self._track_count = track_count
        self._initial = []
        self._build()
        self._refresh_ok()

    def _build(self):
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter playlists…")
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.list_widget = CheckList(self._toggle)
        self.list_widget.setObjectName("PlaylistPickList")
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.delegate = CheckBoxDelegate(self.list_widget)
        self.list_widget.setItemDelegate(self.delegate)
        for playlist in self._playlists:
            if playlist.locked:
                item = QListWidgetItem(playlist.name + "  (Locked)")
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            else:
                item = QListWidgetItem(playlist.name)
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            state = self._initial_state(playlist)
            item.setCheckState(state)
            self._initial.append(state)
            self.list_widget.addItem(item)
        self.list_widget.itemClicked.connect(self._toggle)

        self.new_edit = QLineEdit()
        self.new_edit.setPlaceholderText("New playlist…")
        self.new_edit.textChanged.connect(self._refresh_ok)

        self.box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)
        self.ok_button = self.box.button(QDialogButtonBox.Ok)

        layout = self.content_layout
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.new_edit)
        layout.addWidget(self.box)

    def changes(self):
        adds, removes = [], []
        for row, playlist in enumerate(self._playlists):
            state = self.list_widget.item(row).checkState()
            if state == self._initial[row]:
                continue
            (adds if state == Qt.Checked else removes).append(playlist)
        return adds, removes, self.new_edit.text().strip() or None

    def _initial_state(self, playlist):
        n = self._membership.get(playlist.id, 0)
        if n == 0:
            return Qt.Unchecked
        return Qt.Checked if n >= self._track_count else Qt.PartiallyChecked

    def _toggle(self, item):
        if not item.flags() & Qt.ItemIsEnabled:
            return
        item.setCheckState(
            Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self._refresh_ok()

    def _apply_filter(self, text):
        text = text.lower()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            item.setHidden(text not in item.text().lower())

    def _refresh_ok(self, *_):
        adds, removes, new_name = self.changes()
        self.ok_button.setEnabled(bool(adds or removes or new_name))
