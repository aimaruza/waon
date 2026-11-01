
from dataclasses import replace

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Signal


class QueueModel(QAbstractListModel):

    currentChanged = Signal(int)

    TitleRole = Qt.UserRole + 1
    ArtistRole = Qt.UserRole + 2
    DurationRole = Qt.UserRole + 3
    IsCurrentRole = Qt.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks = []
        self._current = -1
        self._rebuilding = False
        self._detached = None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._tracks)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None
        track = self._tracks[index.row()]
        if role in (Qt.DisplayRole, self.TitleRole):
            return track.title
        if role == self.ArtistRole:
            return track.artist
        if role == self.DurationRole:
            return track.duration
        if role == self.IsCurrentRole:
            return index.row() == self.playing_row()
        return None

    def add(self, tracks):
        tracks = list(tracks)
        if not tracks:
            return
        start = len(self._tracks)
        self.beginInsertRows(QModelIndex(), start, start + len(tracks) - 1)
        self._tracks.extend(tracks)
        self.endInsertRows()

    def insert_after(self, index, tracks):
        tracks = list(tracks)
        if not tracks:
            return
        start = index + 1
        self.beginInsertRows(QModelIndex(), start, start + len(tracks) - 1)
        self._tracks[start:start] = tracks
        self.endInsertRows()

    def set_tracks(self, tracks, current=-1):
        self.beginResetModel()
        self._tracks = list(tracks)
        self._detached = None
        self._current = current if 0 <= current < len(self._tracks) else -1
        self.endResetModel()
        self._emit_rebuilt_current()

    def is_rebuilding(self):
        return self._rebuilding

    def _emit_rebuilt_current(self):
        self._rebuilding = True
        try:
            self.currentChanged.emit(self._current)
        finally:
            self._rebuilding = False

    def remove(self, index):
        if not (0 <= index < len(self._tracks)):
            return False
        self.beginRemoveRows(QModelIndex(), index, index)
        del self._tracks[index]
        self.endRemoveRows()
        if index < self._current:
            self._current -= 1
        elif index == self._current:
            self._current = min(self._current, len(self._tracks) - 1)
            self.currentChanged.emit(self._current)
        return True

    def relink(self, library_id, moves):
        targets = {}
        for kept, dropped, path in moves:
            targets[kept] = targets[dropped] = (kept, path)
        for row, track in enumerate(self._tracks):
            if track.library_id != library_id or track.track_id not in targets:
                continue
            kept, path = targets[track.track_id]
            self._tracks[row] = replace(track, track_id=kept, path=path)
            cell = self.index(row, 0)
            self.dataChanged.emit(cell, cell)

    def track_at(self, index):
        if 0 <= index < len(self._tracks):
            return self._tracks[index]
        return None

    def tracks(self):
        return list(self._tracks)

    def current_index(self):
        return self._current

    def current_track(self):
        if self._detached is not None:
            return self._detached
        return self.track_at(self._current)

    def is_detached(self):
        return self._detached is not None

    def playing_row(self):
        return -1 if self._detached is not None else self._current

    def resume_index(self):
        if self._detached is None:
            return self._current
        if not self._tracks:
            return -1
        return min(self._current + 1, len(self._tracks) - 1)

    def clear_detached(self):
        if self._detached is None:
            return
        self._detached = None
        self._current = -1
        self.currentChanged.emit(-1)

    def remove_rows(self, rows):
        rows = sorted({r for r in rows if 0 <= r < len(self._tracks)}, reverse=True)
        if not rows:
            return
        if self._detached is None and self._current in rows:
            self._detached = self._tracks[self._current]
        for row in rows:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._tracks[row]
            self.endRemoveRows()
            if self._detached is not None and row <= self._current:
                self._current -= 1
            elif row < self._current:
                self._current -= 1

    def reorder(self, tracks):
        if self._detached is not None:
            anchor = self.track_at(self._current)
            self.beginResetModel()
            self._tracks = list(tracks)
            self._current = (_index_of(self._tracks, anchor)
                             if anchor is not None else -1)
            self.endResetModel()
            return
        current = self.current_track()
        self.beginResetModel()
        self._tracks = list(tracks)
        self.endResetModel()
        new_current = _index_of(self._tracks, current) if current is not None else -1
        if new_current != self._current:
            self._current = new_current
            self._emit_rebuilt_current()

    def set_current(self, index):
        if not (0 <= index < len(self._tracks)):
            return False
        previous = self.playing_row()
        self._detached = None
        self._current = index
        self._repaint_rows(previous, index)
        self.currentChanged.emit(index)
        return True

    def _repaint_rows(self, *rows):
        for row in rows:
            if 0 <= row < len(self._tracks):
                cell = self.index(row, 0)
                self.dataChanged.emit(cell, cell, [self.IsCurrentRole])

    def next(self):
        if self._current + 1 < len(self._tracks):
            return self.set_current(self._current + 1)
        return False

    def prev(self):
        target = self._current if self._detached is not None else self._current - 1
        if target >= 0:
            return self.set_current(target)
        return False

    def move_row(self, source_row, target_row):
        n = len(self._tracks)
        if not (0 <= source_row < n):
            return source_row
        target_row = max(0, min(target_row, n - 1))
        if target_row == source_row:
            return source_row
        tracks = list(self._tracks)
        tracks.insert(target_row, tracks.pop(source_row))
        self.reorder(tracks)
        return target_row


def _index_of(tracks, track):
    for i, t in enumerate(tracks):
        if t is track:
            return i
    return -1
