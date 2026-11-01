
from PySide6.QtWidgets import QDialogButtonBox, QLineEdit

from waon.ui.overlay_dialog import OverlayDialog


class RenamePlaylistDialog(OverlayDialog):
    def __init__(self, current_name, parent=None):
        super().__init__("Rename playlist", parent, min_width=340)
        self.name_edit = QLineEdit(current_name)
        self.name_edit.selectAll()
        self.name_edit.textChanged.connect(self._refresh_ok)

        self.box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)
        self.ok_button = self.box.button(QDialogButtonBox.Ok)

        layout = self.content_layout
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.box)
        self._refresh_ok()

    def name(self):
        return self.name_edit.text().strip()

    def _refresh_ok(self):
        self.ok_button.setEnabled(bool(self.name_edit.text().strip()))
