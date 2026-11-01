
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal

from waon.util import format_time


class EntryModel(QAbstractListModel):

    KeyRole = Qt.UserRole + 1
    LabelRole = Qt.UserRole + 2
    SublabelRole = Qt.UserRole + 3
    ArtIdsRole = Qt.UserRole + 4
    CountRole = Qt.UserRole + 5
    DepthRole = Qt.UserRole + 6
    HasChildrenRole = Qt.UserRole + 7
    IsExpandedRole = Qt.UserRole + 8
    LockedRole = Qt.UserRole + 9
    ActiveRole = Qt.UserRole + 10
    CheckedRole = Qt.UserRole + 11
    PlayableRole = Qt.UserRole + 12

    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []
        self._expanded = set()
        self._checked = set()
        self._selection_mode = False
        self._playable = True

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None
        entry = self._entries[index.row()]
        if role in (Qt.DisplayRole, self.LabelRole):
            return entry.label
        if role == self.SublabelRole:
            return entry.sublabel
        if role == self.KeyRole:
            return entry.key
        if role == self.ArtIdsRole:
            return entry.art_ids
        if role == self.CountRole:
            return entry.count_label
        if role == self.DepthRole:
            return entry.depth
        if role == self.HasChildrenRole:
            return entry.has_children
        if role == self.IsExpandedRole:
            return entry.has_children and entry.key in self._expanded
        if role == self.LockedRole:
            return entry.locked
        if role == self.ActiveRole:
            return entry.active
        if role == self.CheckedRole:
            return entry.key in self._checked
        if role == self.PlayableRole:
            return self._playable
        return None

    def set_entries(self, entries):
        self.beginResetModel()
        self._entries = list(entries)
        self._expanded = set()
        keys = {e.key for e in self._entries}
        self._checked &= keys
        self.endResetModel()

    def entry_at(self, row):
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def row_of(self, key):
        for row, entry in enumerate(self._entries):
            if entry.key == key:
                return row
        return -1

    def has_tree_rows(self):
        return any(e.has_children for e in self._entries)

    def is_expanded(self, key):
        return key in self._expanded

    def set_expanded(self, key, expanded):
        if expanded:
            self._expanded.add(key)
        else:
            self._expanded.discard(key)
        row = self.row_of(key)
        if row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [self.IsExpandedRole])

    def is_selection_mode(self):
        return self._selection_mode

    def set_playable(self, playable):
        self._playable = bool(playable)

    def set_selection_mode(self, on):
        on = bool(on)
        if on == self._selection_mode:
            return
        self._selection_mode = on
        self._checked = set()
        self._repaint_checked()
        self.selectionChanged.emit()

    def checked_keys(self):
        return set(self._checked)

    def toggle_checked(self, key):
        if key in self._checked:
            self._checked.discard(key)
        else:
            self._checked.add(key)
        row = self.row_of(key)
        if row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [self.CheckedRole])
        self.selectionChanged.emit()

    def select_all(self):
        self._checked = {e.key for e in self._entries}
        self._repaint_checked()
        self.selectionChanged.emit()

    def clear_checked(self):
        self._checked = set()
        self._repaint_checked()
        self.selectionChanged.emit()

    def _repaint_checked(self):
        if not self._entries:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._entries) - 1, 0)
        self.dataChanged.emit(top_left, bottom_right, [self.CheckedRole])


def _album_header_label(name, year):
    if not year:
        return name
    return "{} ({})".format(name, str(year)[:4])


def _primary_artist(raw):
    return raw.split("/", 1)[0].strip()


def track_identity(track):
    track_id = getattr(track, "track_id", None)
    if track_id is not None:
        return ("tid", track_id, track.library_id)
    row_id = getattr(track, "id", None)
    if row_id is not None:
        return ("rid", row_id)
    return ("path", getattr(track, "path", None))


class TrackListModel(QAbstractListModel):

    TrackRole = Qt.UserRole + 1
    SubtitleRole = Qt.UserRole + 2
    DurationRole = Qt.UserRole + 3
    AvailableRole = Qt.UserRole + 4
    IsHeaderRole = Qt.UserRole + 5
    IsSectionRole = Qt.UserRole + 6
    AlbumIdRole = Qt.UserRole + 7
    IsCollapsedRole = Qt.UserRole + 8
    NowPlayingRole = Qt.UserRole + 9
    CheckedRole = Qt.UserRole + 10

    FEATURED_SECTION_LABEL = "Featured on"

    orderChanged = Signal()

    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._collapsed = set()
        self._reorderable = False
        self._np_track_id = None
        self._np_library_id = None
        self._np_path = None
        self._open_library_id = None
        self._checked = set()
        self._selection_mode = False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled if self._reorderable else Qt.NoItemFlags
        is_header, _track, _label, _is_section, _album_id = self._rows[index.row()]
        if is_header:
            return Qt.ItemIsEnabled
        result = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self._reorderable:
            result |= Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
        return result

    def set_reorderable(self, reorderable):
        self._reorderable = bool(reorderable)

    def supportedDropActions(self):
        return Qt.MoveAction

    def move_row(self, source_row, target_row):
        n = len(self._rows)
        if not (0 <= source_row < n):
            return source_row
        target_row = max(0, min(target_row, n - 1))
        if target_row == source_row:
            return source_row
        self.beginResetModel()
        row = self._rows.pop(source_row)
        self._rows.insert(target_row, row)
        self.endResetModel()
        self.orderChanged.emit()
        return target_row

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        is_header, track, label, is_section, album_id = self._rows[index.row()]
        if role == self.IsHeaderRole:
            return is_header
        if role == self.IsSectionRole:
            return is_section
        if role == self.AlbumIdRole:
            return album_id
        if role == self.IsCollapsedRole:
            return is_header and not is_section and album_id in self._collapsed
        if role == self.CheckedRole:
            return (not is_header) and track_identity(track) in self._checked
        if is_header:
            if role == Qt.DisplayRole:
                return label
            if role in (self.SubtitleRole, self.DurationRole):
                return ""
            return None
        if role == Qt.DisplayRole:
            return track.title
        if role == self.SubtitleRole:
            return track.artist
        if role == self.DurationRole:
            return format_time(track.duration) if track.duration else ""
        if role == self.AvailableRole:
            return bool(track.available)
        if role == self.TrackRole:
            return track
        if role == self.NowPlayingRole:
            return self._matches_now_playing(track)
        return None

    def set_tracks(self, tracks, grouped=False, featured_tracks=(), album_years=None):
        album_years = album_years or {}
        self.beginResetModel()
        self._rows = self._build_rows(tracks, grouped, album_years)
        if featured_tracks:
            self._rows.append(
                (True, None, self.FEATURED_SECTION_LABEL, True, None))
            self._rows.extend(self._build_rows(featured_tracks, True, album_years,
                                               with_artist=True))
        self._collapsed = set()
        self._checked &= {track_identity(t) for t in self.tracks()}
        self.endResetModel()

    def _build_rows(self, tracks, grouped, album_years, with_artist=False):
        if not grouped:
            return [(False, t, None, False, t.album_id) for t in tracks]
        rows = []
        last_album_id = object()
        for t in tracks:
            if t.album_id != last_album_id:
                label = _album_header_label(t.album, album_years.get(t.album_id))
                if with_artist:
                    label = "{} • {}".format(label, _primary_artist(t.artist))
                rows.append((True, None, label, False, t.album_id))
                last_album_id = t.album_id
            rows.append((False, t, None, False, t.album_id))
        return rows

    def set_open_library(self, library_id):
        if library_id == self._open_library_id:
            return
        old_rows = self._now_playing_rows()
        self._open_library_id = library_id
        self._repaint_now_playing(old_rows, self._now_playing_rows())

    def set_now_playing(self, track_id, library_id, path):
        old_rows = self._now_playing_rows()
        self._np_track_id = track_id
        self._np_library_id = library_id
        self._np_path = path
        self._repaint_now_playing(old_rows, self._now_playing_rows())

    def _now_playing_rows(self):
        return [row for row, (is_header, track, _l, _s, _a)
               in enumerate(self._rows)
               if not is_header and self._matches_now_playing(track)]

    def _repaint_now_playing(self, old_rows, new_rows):
        for row in set(old_rows) ^ set(new_rows):
            cell = self.index(row, 0)
            self.dataChanged.emit(cell, cell, [self.NowPlayingRole])

    def _matches_now_playing(self, track):
        if self._np_track_id is not None:
            row_track_id = getattr(track, "track_id", None)
            if row_track_id is not None:
                return (row_track_id == self._np_track_id
                        and track.library_id == self._np_library_id)
            row_id = getattr(track, "id", None)
            return (row_id == self._np_track_id
                    and self._open_library_id == self._np_library_id)
        if self._np_path is not None:
            return getattr(track, "path", None) == self._np_path
        return False

    def is_selection_mode(self):
        return self._selection_mode

    def set_selection_mode(self, on):
        on = bool(on)
        if on == self._selection_mode:
            return
        self._selection_mode = on
        self._checked = set()
        self._repaint_checked()
        self.selectionChanged.emit()

    def checked_tracks(self):
        return [t for t in self.tracks() if track_identity(t) in self._checked]

    def toggle_checked(self, row):
        if not (0 <= row < len(self._rows)):
            return
        is_header, track_obj, _label, _is_section, _album_id = self._rows[row]
        if is_header or track_obj is None:
            return
        identity = track_identity(track_obj)
        if identity in self._checked:
            self._checked.discard(identity)
        else:
            self._checked.add(identity)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [self.CheckedRole])
        self.selectionChanged.emit()

    def select_all(self):
        self._checked = {track_identity(t) for t in self.tracks()}
        self._repaint_checked()
        self.selectionChanged.emit()

    def clear_checked(self):
        self._checked = set()
        self._repaint_checked()
        self.selectionChanged.emit()

    def _repaint_checked(self):
        if not self._rows:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._rows) - 1, 0)
        self.dataChanged.emit(top_left, bottom_right, [self.CheckedRole])

    def track_at(self, row):
        if 0 <= row < len(self._rows):
            is_header, track, _label, _is_section, _album_id = self._rows[row]
            return None if is_header else track
        return None

    def tracks(self):
        return [track for is_header, track, _label, _is_section, _album_id
                in self._rows if not is_header]

    def is_header(self, row):
        if 0 <= row < len(self._rows):
            return self._rows[row][0]
        return False

    def is_section(self, row):
        if 0 <= row < len(self._rows):
            return self._rows[row][3]
        return False

    def tracks_for_header(self, row):
        if not self.is_header(row):
            return []
        result = []
        for is_header, track, _label, _is_section, _album_id in self._rows[row + 1:]:
            if is_header:
                break
            result.append(track)
        return result

    def track_index(self, row):
        if not (0 <= row < len(self._rows)):
            return None
        if self._rows[row][0]:
            return None
        return sum(1 for is_header, _t, _l, _s, _a in self._rows[:row]
                  if not is_header)

    def is_collapsed(self, album_id):
        return album_id in self._collapsed

    def set_collapsed(self, album_id, collapsed):
        if collapsed:
            self._collapsed.add(album_id)
        else:
            self._collapsed.discard(album_id)
        self._notify_header_changed(album_id)

    def collapse_all(self):
        self._collapsed = {album_id for is_header, _t, _l, is_section, album_id
                           in self._rows if is_header and not is_section}
        self._notify_all_headers_changed()

    def expand_all(self):
        self._collapsed = set()
        self._notify_all_headers_changed()

    def track_rows_for_header(self, row):
        if not self.is_header(row):
            return []
        result = []
        for r in range(row + 1, len(self._rows)):
            if self._rows[r][0]:
                break
            result.append(r)
        return result

    def _notify_header_changed(self, album_id):
        for row, stored in enumerate(self._rows):
            is_header, _t, _l, is_section, row_album_id = stored
            if is_header and not is_section and row_album_id == album_id:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [self.IsCollapsedRole])

    def _notify_all_headers_changed(self):
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, 0),
                [self.IsCollapsedRole])
