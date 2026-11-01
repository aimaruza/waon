
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialogButtonBox, QLineEdit, QListWidgetItem,
)

from waon.ui.check_list import CheckBoxDelegate, CheckList
from waon.ui.overlay_dialog import OverlayDialog


class AddToQueueDialog(OverlayDialog):

    def __init__(self, queues, membership, track_count, parent=None):
        super().__init__("Add to queue", parent, min_width=360)
        self._queues = queues
        self._membership = membership
        self._track_count = track_count
        self._initial = []
        self._build()
        self._refresh_ok()

    def _build(self):
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter queues…")
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.list_widget = CheckList(self._toggle)
        self.list_widget.setObjectName("QueuePickList")
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.delegate = CheckBoxDelegate(self.list_widget)
        self.list_widget.setItemDelegate(self.delegate)
        for ref in self._queues:
            item = QListWidgetItem(ref.source_label or "Queue")
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            state = self._initial_state(ref)
            item.setCheckState(state)
            self._initial.append(state)
            self.list_widget.addItem(item)
        self.list_widget.itemClicked.connect(self._toggle)

        self.new_edit = QLineEdit()
        self.new_edit.setPlaceholderText("New queue…")
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
        for row, ref in enumerate(self._queues):
            state = self.list_widget.item(row).checkState()
            if state == self._initial[row]:
                continue
            (adds if state == Qt.Checked else removes).append(ref)
        return adds, removes, self.new_edit.text().strip() or None

    def _initial_state(self, ref):
        n = self._membership.get(ref.id, 0)
        if n == 0:
            return Qt.Unchecked
        return Qt.Checked if n >= self._track_count else Qt.PartiallyChecked

    def _toggle(self, item):
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
