
import logging

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from waon.library import paths
from waon.library.library_repo import InvalidExclusionError, NestedRootError
from waon.ui import theme
from waon.ui.elided_label import ElidedLabel
from waon.ui.home_page import format_listened
from waon.ui.icons import IconButton, LIBRARY_ICONS, render_icon, render_swatch
from waon.ui.overlay_dialog import OverlayDialog

log = logging.getLogger(__name__)

MAX_NAME = 80
_SWATCH = 22


def _counted(n, noun):
    return "1 {}".format(noun) if n == 1 else "{} {}s".format(n, noun)


class _ColorRow(QWidget):

    def __init__(self, parent=None, swatch=_SWATCH, spacing=6):
        super().__init__(parent)
        self._swatch = swatch
        self._color = theme.LIBRARY_COLORS[0]
        self._buttons = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for color in theme.LIBRARY_COLORS:
            button = QPushButton()
            button.setFixedSize(swatch, swatch)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, value=color: self.set_color(value))
            self._buttons[color] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.set_color(self._color)

    def color(self):
        return self._color

    def set_color(self, color):
        if color not in self._buttons:
            log.warning("unknown library color %r; ignoring", color)
            return
        self._color = color
        for value, button in self._buttons.items():
            chosen = value == color
            button.setChecked(chosen)
            button.setStyleSheet(
                "border-radius: {}px; background: {}; border: 2px solid {};"
                .format(self._swatch // 2, value,
                        theme.TEXT if chosen else "transparent"))


class _IconRow(QWidget):

    _COLUMNS = 8
    _ICON_SIZE = 18

    def __init__(self, parent=None, swatch=_SWATCH, spacing=6, icon_size=None):
        super().__init__(parent)
        icon_size = icon_size or self._ICON_SIZE
        self._icon = ""
        self._buttons = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for index, choice in enumerate(("",) + LIBRARY_ICONS):
            button = QPushButton()
            button.setFixedSize(swatch, swatch)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            if choice:
                button.setIcon(QIcon(render_icon(choice, theme.ICON, icon_size)))
                button.setToolTip(choice.replace("-", " ").title())
            else:
                button.setIcon(QIcon(render_icon("minimize", theme.DISABLED, icon_size)))
                button.setToolTip("No icon")
            button.setIconSize(QSize(icon_size, icon_size))
            button.clicked.connect(
                lambda _=False, value=choice: self.set_icon(value))
            self._buttons[choice] = button
            layout.addWidget(button, index // self._COLUMNS, index % self._COLUMNS)
        self.set_icon(self._icon)

    def icon(self):
        return self._icon

    def set_icon(self, icon):
        if icon not in self._buttons:
            log.warning("unknown library icon %r; ignoring", icon)
            return
        self._icon = icon
        for value, button in self._buttons.items():
            chosen = value == icon
            button.setChecked(chosen)
            button.setStyleSheet(
                "border-radius: 0px; border: 2px solid {};"
                .format(theme.TEXT if chosen else "transparent"))


class _RootListMixin:

    def pick_folder(self):
        return QFileDialog.getExistingDirectory(self, "Choose a music folder")

    def confirm(self, title, text):
        answer = QMessageBox.question(self, title, text,
                                      QMessageBox.Yes | QMessageBox.No)
        return answer == QMessageBox.Yes


class RootRow(QWidget):

    removeRequested = Signal(str)

    def __init__(self, root, track_count, parent=None):
        super().__init__(parent)
        self.root_id = root.id
        self.path_label = ElidedLabel(root.path)
        self.path_label.setObjectName("RootPath")
        self.count_label = QLabel(
            "1 track" if track_count == 1 else "{} tracks".format(track_count))
        self.count_label.setObjectName("RootCount")
        self.remove_button = IconButton("trash", "Remove folder",
                                         icon_size=14, diameter=28, pill_hover=False)
        self.remove_button.clicked.connect(
            lambda: self.removeRequested.emit(self.root_id))

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        text.addWidget(self.path_label)
        text.addWidget(self.count_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        layout.addLayout(text, 1)
        layout.addWidget(self.remove_button)


class IncludedFoldersDialog(OverlayDialog, _RootListMixin):

    libraryChanged = Signal()

    def __init__(self, service, parent=None):
        super().__init__("Folders to include", parent, min_width=520, flat_icons=True)
        self._service = service
        self.added_root_ids = []
        self._build()
        self._reload_roots()

    def _build(self):
        self.root_list = QListWidget()
        self.root_list.setObjectName("RootList")
        self.root_list.setMinimumHeight(200)
        self.root_list.setSelectionMode(QListWidget.NoSelection)
        self.add_button = QPushButton("+ Add folder…")
        self.add_button.clicked.connect(self._on_add)

        self.error_label = QLabel("")
        self.error_label.setObjectName("DialogError")
        self.error_label.setWordWrap(True)

        layout = self.content_layout
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(self.root_list)
        layout.addWidget(self.add_button, alignment=Qt.AlignLeft)
        layout.addWidget(self.error_label)

    def root_widget(self, row):
        return self.root_list.itemWidget(self.root_list.item(row))

    def _reload_roots(self):
        for i in range(self.root_list.count()):
            widget = self.root_list.itemWidget(self.root_list.item(i))
            if widget is not None:
                widget.setParent(None)
        self.root_list.clear()
        counts = self._service.root_track_counts()
        for root in self._service.roots():
            widget = RootRow(root, counts.get(root.id, 0))
            widget.removeRequested.connect(self._on_remove)
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.root_list.addItem(item)
            self.root_list.setItemWidget(item, widget)

    def _on_add(self):
        path = self.pick_folder()
        if not path:
            return
        try:
            root = self._service.add_root(path)
        except NestedRootError as exc:
            log.warning("refused nested root %s: %s", path, exc)
            self.error_label.setText(str(exc))
            return
        self.error_label.setText("")
        self.added_root_ids.append(root.id)
        self._reload_roots()
        self.libraryChanged.emit()

    def _on_remove(self, root_id):
        root = [r for r in self._service.roots() if r.id == root_id]
        if not root:
            log.warning("remove requested for unknown root id %s", root_id)
            return
        impact = self._service.remove_root_impact(root_id)
        message = _remove_root_message(root[0].path, impact)
        if not self.confirm("Remove folder", message):
            return
        self.error_label.setText("")
        self._service.remove_root(root_id)
        if root_id in self.added_root_ids:
            self.added_root_ids.remove(root_id)
        self._reload_roots()
        self.libraryChanged.emit()


def _remove_root_message(path, impact):
    parts = ["Removing {} deletes {} from this library".format(
        path, _counted(impact["tracks"], "track"))]
    lost = [_counted(impact[key], noun)
            for key, noun in (("plays", "play"), ("favorites", "favorite"))
            if impact[key]]
    if lost:
        parts.append(", along with their {}".format(" and ".join(lost)))
    parts.append(".")
    if impact["playlist_tracks"]:
        parts.append(" {} of them will also be removed from {}.".format(
            impact["playlist_tracks"], _counted(impact["playlists"], "playlist")))
    parts.append(" The folder on disk is untouched.")
    return "".join(parts)


class ExclusionRow(QWidget):

    removeRequested = Signal(str)

    def __init__(self, exclusion, root, parent=None):
        super().__init__(parent)
        self.exclusion_id = exclusion.id
        display_path = paths.to_abs(root.path, exclusion.rel_path)
        self.path_label = ElidedLabel(display_path)
        self.path_label.setObjectName("RootPath")
        self.remove_button = IconButton("trash", "Remove exclusion",
                                         icon_size=14, diameter=28, pill_hover=False)
        self.remove_button.clicked.connect(
            lambda: self.removeRequested.emit(self.exclusion_id))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        layout.addWidget(self.path_label, 1)
        layout.addWidget(self.remove_button)


class ExcludedFoldersDialog(OverlayDialog, _RootListMixin):

    libraryChanged = Signal()

    def __init__(self, service, parent=None):
        super().__init__("Folders to exclude", parent, min_width=520, flat_icons=True)
        self._service = service
        self.exclusions_changed = False
        self._build()
        self._reload_exclusions()

    def _build(self):
        self.exclusion_list = QListWidget()
        self.exclusion_list.setObjectName("RootList")
        self.exclusion_list.setMinimumHeight(200)
        self.exclusion_list.setSelectionMode(QListWidget.NoSelection)
        self.exclude_button = QPushButton("+ Exclude a subfolder…")
        self.exclude_button.clicked.connect(self._on_exclude)
        hint = QLabel("Files inside these folders are skipped on the next scan.")
        hint.setObjectName("DialogHint")

        self.error_label = QLabel("")
        self.error_label.setObjectName("DialogError")
        self.error_label.setWordWrap(True)

        layout = self.content_layout
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(self.exclusion_list)
        layout.addWidget(self.exclude_button, alignment=Qt.AlignLeft)
        layout.addWidget(hint)
        layout.addWidget(self.error_label)

    def _reload_exclusions(self):
        for i in range(self.exclusion_list.count()):
            widget = self.exclusion_list.itemWidget(self.exclusion_list.item(i))
            if widget is not None:
                widget.setParent(None)
        self.exclusion_list.clear()
        roots_by_id = {r.id: r for r in self._service.roots()}
        for exclusion in self._service.exclusions():
            root = roots_by_id.get(exclusion.root_id)
            if root is None:
                continue
            widget = ExclusionRow(exclusion, root)
            widget.removeRequested.connect(self._on_remove_exclusion)
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.exclusion_list.addItem(item)
            self.exclusion_list.setItemWidget(item, widget)

    def _on_exclude(self):
        path = self.pick_folder()
        if not path:
            return
        root, rel_path = self._service.root_for_path(path)
        if root is None:
            self.error_label.setText(
                "{} is not inside any of this library's folders.".format(path))
            return
        try:
            self._service.add_exclusion(root.id, rel_path)
        except InvalidExclusionError as exc:
            log.warning("refused exclusion %s: %s", path, exc)
            self.error_label.setText(str(exc))
            return
        self.error_label.setText("")
        self.exclusions_changed = True
        self._reload_exclusions()
        self.libraryChanged.emit()

    def _on_remove_exclusion(self, exclusion_id):
        self._service.remove_exclusion(exclusion_id)
        self.exclusions_changed = True
        self._reload_exclusions()
        self.libraryChanged.emit()


class _SettingsRow(QWidget):

    clicked = Signal()

    def __init__(self, icon_name, text, danger=False, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        ink = theme.DANGER if danger else theme.ICON
        self.icon_label = QLabel()
        self.icon_label.setStyleSheet("background: transparent;")
        self.icon_label.setPixmap(render_icon(icon_name, ink, 20))
        text_label = QLabel(text)
        text_label.setStyleSheet(
            "background: transparent; color: {};".format(
                theme.DANGER if danger else theme.TEXT))
        self.count_label = QLabel("")
        self.count_label.setObjectName("SettingsRowCount")
        self.chevron_label = QLabel()
        self.chevron_label.setStyleSheet("background: transparent;")
        self.chevron_label.setPixmap(render_icon("chevron-right", theme.DISABLED, 12))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(self.icon_label)
        layout.addWidget(text_label, 1)
        layout.addWidget(self.count_label)
        layout.addWidget(self.chevron_label)

    def set_count(self, n):
        self.count_label.setText(str(n))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._set_hovering(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hovering(False)
        super().leaveEvent(event)

    def _set_hovering(self, value):
        self.setProperty("hovering", value)
        self.style().unpolish(self)
        self.style().polish(self)


class _ScanButton(QAbstractButton):

    _WIDTH = 48
    _HEIGHT = 38
    _ICON_SIZE = 18
    _CAPTION_PT = 7.5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("Scan now")
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if not self.isEnabled():
            color = theme.DISABLED
        elif self._hover:
            color = theme.BRAND
        else:
            color = theme.ICON
        pixmap = render_icon("refresh", color, self._ICON_SIZE)
        painter.drawPixmap((self.width() - self._ICON_SIZE) // 2, 1, pixmap)
        font = QFont(painter.font())
        font.setPointSizeF(self._CAPTION_PT)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(self.rect().adjusted(0, 0, 0, -2),
                         Qt.AlignHCenter | Qt.AlignBottom, "Scan")
        painter.end()


class LibraryInfoForm(QWidget):

    validityChanged = Signal(bool)

    def __init__(self, parent=None, relaxed=False):
        super().__init__(parent)
        self._valid = False
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_NAME)
        self.name_edit.textChanged.connect(self._on_text_changed)
        if relaxed:
            self.name_edit.setMinimumHeight(38)
            self.color_row = _ColorRow(swatch=28, spacing=10)
            self.icon_row = _IconRow(swatch=28, spacing=10, icon_size=20)
        else:
            self.color_row = _ColorRow()
            self.icon_row = _IconRow()
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        if relaxed:
            form.setVerticalSpacing(22)
            form.setHorizontalSpacing(28)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow("Name", self.name_edit)
        form.addRow("Colour", self.color_row)
        form.addRow("Icon", self.icon_row)

    def values(self):
        return {"name": self.name_edit.text().strip(),
                "color": self.color_row.color(),
                "icon": self.icon_row.icon()}

    def set_values(self, name, color=None, icon=""):
        self.name_edit.setText(name)
        self.color_row.set_color(color or theme.LIBRARY_COLORS[0])
        self.icon_row.set_icon(icon)

    def is_valid(self):
        return bool(self.name_edit.text().strip())

    def _on_text_changed(self, _text):
        valid = self.is_valid()
        if valid != self._valid:
            self._valid = valid
            self.validityChanged.emit(valid)


class EditInfoDialog(OverlayDialog):

    def __init__(self, library, parent=None):
        super().__init__("Edit info", parent, min_width=460, flat_icons=True)
        self._build()
        self.form.set_values(library.name, library.color, library.icon)
        self._refresh_ok()

    def _build(self):
        self.form = LibraryInfoForm()
        self.form.validityChanged.connect(self._refresh_ok)
        self.name_edit = self.form.name_edit
        self.color_row = self.form.color_row
        self.icon_row = self.form.icon_row

        self.box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.box.accepted.connect(self.accept)
        self.box.rejected.connect(self.reject)
        self.ok_button = self.box.button(QDialogButtonBox.Ok)

        layout = self.content_layout
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(self.form)
        layout.addWidget(self.box)

    def values(self):
        return self.form.values()

    def _refresh_ok(self, *_):
        self.ok_button.setEnabled(self.form.is_valid())


class LibrarySettingsDialog(OverlayDialog, _RootListMixin):

    libraryChanged = Signal()
    scanRequested = Signal()
    exportRequested = Signal()

    def __init__(self, service, parent=None):
        super().__init__("Library settings", parent, min_width=560, flat_icons=True)
        self._service = service
        self.delete_requested = False
        self.added_root_ids = []
        self.exclusions_changed = False
        self.included_dialog_factory = IncludedFoldersDialog
        self.excluded_dialog_factory = ExcludedFoldersDialog
        self.edit_info_dialog_factory = EditInfoDialog
        self._build()
        self.refresh_info()

    def _build(self):
        self.swatch_label = QLabel()
        self.swatch_label.setFixedSize(38, 38)
        self.name_label = QLabel()
        self.name_label.setObjectName("DialogHeaderTitle")
        self.stats_label = QLabel()
        self.stats_label.setObjectName("DialogHint")

        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(2)
        name_col.addWidget(self.name_label)
        name_col.addWidget(self.stats_label)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(14)
        info_row.addWidget(self.swatch_label)
        info_row.addLayout(name_col, 1)

        info_divider = QWidget()
        info_divider.setObjectName("LibrarySplitDivider")
        info_divider.setFixedWidth(1)
        info_row.addWidget(info_divider)
        self.scan_button = _ScanButton()
        self.scan_button.clicked.connect(self._on_scan)
        info_row.addWidget(self.scan_button)

        info_card = QWidget()
        info_card.setObjectName("SettingsInfoCard")
        info_card.setAttribute(Qt.WA_StyledBackground, True)
        info_card_layout = QVBoxLayout(info_card)
        info_card_layout.setContentsMargins(18, 16, 18, 16)
        info_card_layout.addLayout(info_row)

        self.edit_info_row = _SettingsRow("pencil-square", "Edit info")
        self.edit_info_row.clicked.connect(self._on_edit_info_clicked)
        self.include_row = _SettingsRow("folder-check", "Folders to include")
        self.include_row.clicked.connect(self._on_include_clicked)
        self.exclude_row = _SettingsRow("folder-x", "Folders to exclude")
        self.exclude_row.clicked.connect(self._on_exclude_clicked)

        def _row_divider():
            widget = QWidget()
            widget.setObjectName("SettingsRowDivider")
            widget.setFixedHeight(1)
            widget.setAttribute(Qt.WA_StyledBackground, True)
            return widget

        settings_card = QWidget()
        settings_card.setObjectName("SettingsGroupCard")
        settings_card.setAttribute(Qt.WA_StyledBackground, True)
        settings_card_layout = QVBoxLayout(settings_card)
        settings_card_layout.setContentsMargins(1, 1, 1, 1)
        settings_card_layout.setSpacing(0)
        settings_card_layout.addWidget(self.edit_info_row)
        settings_card_layout.addWidget(_row_divider())
        settings_card_layout.addWidget(self.include_row)
        settings_card_layout.addWidget(_row_divider())
        settings_card_layout.addWidget(self.exclude_row)

        self.export_row = _SettingsRow("export", "Back up play history & playlists")
        self.export_row.clicked.connect(self.exportRequested)
        export_card = QWidget()
        export_card.setObjectName("SettingsGroupCard")
        export_card.setAttribute(Qt.WA_StyledBackground, True)
        export_card_layout = QVBoxLayout(export_card)
        export_card_layout.setContentsMargins(1, 1, 1, 1)
        export_card_layout.addWidget(self.export_row)

        self.delete_row = _SettingsRow("trash", "Delete library", danger=True)
        self.delete_row.clicked.connect(self._on_delete)
        delete_card = QWidget()
        delete_card.setObjectName("SettingsDangerCard")
        delete_card.setAttribute(Qt.WA_StyledBackground, True)
        delete_card_layout = QVBoxLayout(delete_card)
        delete_card_layout.setContentsMargins(1, 1, 1, 1)
        delete_card_layout.addWidget(self.delete_row)

        layout = self.content_layout
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(info_card)
        layout.addWidget(settings_card)
        layout.addWidget(export_card)
        layout.addWidget(delete_card)

    def refresh_info(self):
        library = self._service.current
        stats = self._service.library_stats()
        self.swatch_label.setPixmap(render_swatch(library.color, 38, library.icon))
        self.name_label.setText(library.name)
        self.stats_label.setText(
            "{} • {} • {} • {}".format(
                _counted(stats.artist_count, "artist"),
                _counted(stats.album_count, "album"),
                _counted(stats.track_count, "track"),
                format_listened(stats.total_duration)))
        self.include_row.set_count(len(self._service.roots()))
        self.exclude_row.set_count(len(self._service.exclusions()))

    def _on_edit_info_clicked(self):
        library = self._service.current
        dialog = self.edit_info_dialog_factory(library, self.parent())
        if dialog.exec() == QDialog.Accepted:
            values = dialog.values()
            self._service.rename_library(
                library.id, values["name"], values["color"], values["icon"])
            self.libraryChanged.emit()
        self.refresh_info()

    def _on_include_clicked(self):
        dialog = self.included_dialog_factory(self._service, self.parent())
        dialog.libraryChanged.connect(self.libraryChanged)
        dialog.exec()
        self.added_root_ids.extend(dialog.added_root_ids)
        self.refresh_info()

    def _on_exclude_clicked(self):
        dialog = self.excluded_dialog_factory(self._service, self.parent())
        dialog.libraryChanged.connect(self.libraryChanged)
        dialog.exec()
        self.exclusions_changed = self.exclusions_changed or dialog.exclusions_changed
        self.refresh_info()

    def _on_scan(self):
        self.added_root_ids = []
        self.exclusions_changed = False
        self.scanRequested.emit()

    def set_scanning(self, active):
        self.edit_info_row.setEnabled(not active)
        self.include_row.setEnabled(not active)
        self.exclude_row.setEnabled(not active)
        self.export_row.setEnabled(not active)
        self.delete_row.setEnabled(not active)
        self.scan_button.setEnabled(not active)

    def _on_delete(self):
        library = self._service.current
        if not self.confirm(
                "Delete library",
                "Delete the library “{}”? The music files on disk are not "
                "touched.".format(library.name)):
            return
        self.delete_requested = True
        self.reject()
