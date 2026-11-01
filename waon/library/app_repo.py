
import time
import uuid

from waon.library import paths
from waon.library.entities import Library, QueueRef
from waon.models import Track


def _library(row):
    return Library(id=row["id"], name=row["name"], color=row["color"],
                   position=row["position"], icon=row["icon"])


def _queue_ref(row):
    return QueueRef(id=row["id"],
                    source_kind=row["source_kind"] or None,
                    source_label=row["source_label"],
                    source_library=row["source_library"],
                    current_pos=row["current_pos"],
                    created_at=row["created_at"],
                    last_played_at=row["last_played_at"],
                    dirty=bool(row["dirty"]),
                    position_seconds=row["position_seconds"],
                    owner_library_id=row["owner_library_id"])


def queue_track_key(track):
    if track.track_id is not None:
        return ("tid", track.track_id, track.library_id)
    return ("path", track.path)


def _item_key(row):
    if row["track_id"] is not None:
        return ("tid", row["track_id"], row["library_id"])
    return ("path", row["path"])


ANY_OWNER = object()


class AppRepo:

    def __init__(self, conn):
        self._conn = conn


    def add_library(self, library_id, name, color, icon=""):
        row = self._conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS next FROM library").fetchone()
        position = row["next"]
        self._conn.execute(
            "INSERT INTO library (id, name, color, position, icon) "
            "VALUES (?, ?, ?, ?, ?)", (library_id, name, color, position, icon))
        self._conn.commit()
        return Library(id=library_id, name=name, color=color, position=position,
                       icon=icon)

    def libraries(self):
        rows = self._conn.execute(
            "SELECT * FROM library ORDER BY position").fetchall()
        return [_library(r) for r in rows]

    def library(self, library_id):
        row = self._conn.execute(
            "SELECT * FROM library WHERE id = ?", (library_id,)).fetchone()
        return _library(row) if row is not None else None

    def update_library(self, library_id, name, color, icon=""):
        self._conn.execute(
            "UPDATE library SET name = ?, color = ?, icon = ? WHERE id = ?",
            (name, color, icon, library_id))
        self._conn.commit()

    def remove_library(self, library_id):
        self._conn.execute("DELETE FROM library WHERE id = ?", (library_id,))
        self._conn.commit()

    def reorder_libraries(self, library_ids):
        self._conn.executemany(
            "UPDATE library SET position = ? WHERE id = ?",
            [(i, lib_id) for i, lib_id in enumerate(library_ids)])
        self._conn.commit()


    def get_state(self, key, default=None):
        row = self._conn.execute(
            "SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default

    def set_state(self, key, value):
        self._conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)))
        self._conn.commit()


    def create_queue(self, source_kind, source_label, source_library, tracks,
                     current_pos, dirty=False, owner_library_id=None):
        now = int(time.time())
        queue_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO queue (id, source_kind, source_label, source_library, "
            "current_pos, created_at, last_played_at, dirty, owner_library_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (queue_id, source_kind or "", source_label, source_library,
             current_pos, now, now, 1 if dirty else 0, owner_library_id))
        self._insert_queue_items(queue_id, tracks)
        self._conn.commit()
        return QueueRef(id=queue_id, source_kind=source_kind or None,
                        source_label=source_label, source_library=source_library,
                        current_pos=current_pos, created_at=now,
                        last_played_at=now, dirty=dirty,
                        owner_library_id=owner_library_id)

    def _insert_queue_items(self, queue_id, tracks):
        self._conn.executemany(
            "INSERT INTO queue_item (queue_id, position, path, title, artist, "
            "album, duration, track_id, library_id, album_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(queue_id, i, t.path, t.title, t.artist, t.album, t.duration,
              t.track_id, t.library_id, t.album_id)
             for i, t in enumerate(tracks)])

    def load_queue(self, queue_id):
        row = self._conn.execute(
            "SELECT * FROM queue WHERE id = ?", (queue_id,)).fetchone()
        if row is None:
            return None
        items = self._conn.execute(
            "SELECT * FROM queue_item WHERE queue_id = ? ORDER BY position",
            (queue_id,)).fetchall()
        tracks = [Track(path=i["path"], title=i["title"], artist=i["artist"],
                        album=i["album"], duration=i["duration"],
                        track_id=i["track_id"], library_id=i["library_id"],
                        album_id=i["album_id"])
                 for i in items]
        return _queue_ref(row), tracks

    def queue_ref(self, queue_id):
        row = self._conn.execute(
            "SELECT * FROM queue WHERE id = ?", (queue_id,)).fetchone()
        return _queue_ref(row) if row is not None else None

    def replace_queue_items(self, queue_id, tracks):
        self._conn.execute("DELETE FROM queue_item WHERE queue_id = ?", (queue_id,))
        self._insert_queue_items(queue_id, tracks)
        self._conn.commit()

    def reorder_queue_items(self, queue_id, tracks):
        self._conn.execute("DELETE FROM queue_item WHERE queue_id = ?", (queue_id,))
        self._insert_queue_items(queue_id, tracks)
        self._conn.execute(
            "UPDATE queue SET dirty = 1, last_played_at = ? WHERE id = ?",
            (int(time.time()), queue_id))
        self._conn.commit()

    def add_queue_items(self, queue_id, tracks):
        row = self._conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS next FROM queue_item "
            "WHERE queue_id = ?", (queue_id,)).fetchone()
        start = row["next"]
        self._conn.executemany(
            "INSERT INTO queue_item (queue_id, position, path, title, artist, "
            "album, duration, track_id, library_id, album_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(queue_id, start + i, t.path, t.title, t.artist, t.album, t.duration,
              t.track_id, t.library_id, t.album_id)
             for i, t in enumerate(tracks)])
        self._conn.execute(
            "UPDATE queue SET dirty = 1, last_played_at = ? WHERE id = ?",
            (int(time.time()), queue_id))
        self._conn.commit()

    def queue_membership(self, queue_ids, tracks):
        if not queue_ids:
            return {}
        wanted = {queue_track_key(t) for t in tracks}
        marks = ",".join("?" * len(queue_ids))
        rows = self._conn.execute(
            "SELECT queue_id, track_id, library_id, path FROM queue_item "
            "WHERE queue_id IN ({})".format(marks), list(queue_ids)).fetchall()
        found = {}
        for row in rows:
            key = _item_key(row)
            if key in wanted:
                found.setdefault(row["queue_id"], set()).add(key)
        return {qid: len(keys) for qid, keys in found.items()}

    def add_missing_queue_tracks(self, queue_id, tracks):
        present = {_item_key(r) for r in self._conn.execute(
            "SELECT track_id, library_id, path FROM queue_item WHERE queue_id = ?",
            (queue_id,))}
        missing = []
        for track in tracks:
            key = queue_track_key(track)
            if key not in present:
                present.add(key)
                missing.append(track)
        if missing:
            self.add_queue_items(queue_id, missing)
        return len(missing)

    def remove_queue_tracks(self, queue_id, tracks):
        loaded = self.load_queue(queue_id)
        if loaded is None:
            return 0
        ref, items = loaded
        gone = {queue_track_key(t) for t in tracks}
        kept, new_pos, seconds = [], None, ref.position_seconds
        for i, item in enumerate(items):
            if queue_track_key(item) in gone:
                if i == ref.current_pos:
                    seconds = 0
                continue
            if new_pos is None and i >= ref.current_pos:
                new_pos = len(kept)
            kept.append(item)
        removed = len(items) - len(kept)
        if not removed:
            return 0
        if new_pos is None:
            new_pos = len(kept) - 1
        self._conn.execute("DELETE FROM queue_item WHERE queue_id = ?", (queue_id,))
        self._insert_queue_items(queue_id, kept)
        self._conn.execute(
            "UPDATE queue SET current_pos = ?, position_seconds = ?, dirty = 1, "
            "last_played_at = ? WHERE id = ?",
            (new_pos, seconds, int(time.time()), queue_id))
        self._conn.commit()
        return removed

    def rename_queue(self, queue_id, label):
        self._conn.execute(
            "UPDATE queue SET source_label = ?, dirty = 1, last_played_at = ? "
            "WHERE id = ?",
            (label, int(time.time()), queue_id))
        self._conn.commit()

    def touch_queue(self, queue_id):
        self._conn.execute(
            "UPDATE queue SET last_played_at = ? WHERE id = ?",
            (int(time.time()), queue_id))
        self._conn.commit()

    def find_pristine_queue(self, source_kind, source_label, owner_library_id):
        row = self._conn.execute(
            "SELECT id FROM queue WHERE source_kind = ? AND source_label = ? "
            "AND owner_library_id IS ? AND dirty = 0 LIMIT 1",
            (source_kind or "", source_label, owner_library_id)).fetchone()
        return row["id"] if row is not None else None

    def set_queue_position(self, queue_id, current_pos, position_seconds=0):
        self._conn.execute(
            "UPDATE queue SET current_pos = ?, position_seconds = ?, "
            "last_played_at = ? WHERE id = ?",
            (current_pos, position_seconds, int(time.time()), queue_id))
        self._conn.commit()

    def delete_queue(self, queue_id):
        self._conn.execute("DELETE FROM queue WHERE id = ?", (queue_id,))
        self._conn.commit()

    def delete_owned_queues(self, library_id):
        ids = [r["id"] for r in self._conn.execute(
            "SELECT id FROM queue WHERE owner_library_id = ?", (library_id,))]
        self._conn.execute("DELETE FROM queue WHERE owner_library_id = ?",
                           (library_id,))
        self._conn.commit()
        return ids

    def evict_excess_queues(self, keep, protect_id, owner_library_id=ANY_OWNER):
        if owner_library_id is ANY_OWNER:
            self._conn.execute(
                "DELETE FROM queue WHERE id != ? AND id NOT IN ("
                "  SELECT id FROM queue ORDER BY last_played_at DESC LIMIT ?)",
                (protect_id, keep))
        else:
            self._conn.execute(
                "DELETE FROM queue WHERE id != ? AND owner_library_id IS ? "
                "AND id NOT IN (SELECT id FROM queue WHERE owner_library_id IS ? "
                "               ORDER BY last_played_at DESC LIMIT ?)",
                (protect_id, owner_library_id, owner_library_id, keep))
        self._conn.commit()

    def list_queues(self, owner_library_id=ANY_OWNER):
        where, args = "", ()
        if owner_library_id is not ANY_OWNER:
            where, args = "WHERE q.owner_library_id IS ? ", (owner_library_id,)
        rows = self._conn.execute(
            "SELECT q.*, COUNT(qi.position) AS track_count FROM queue q "
            "LEFT JOIN queue_item qi ON qi.queue_id = q.id " + where +
            "GROUP BY q.id ORDER BY q.last_played_at DESC", args).fetchall()
        return [(_queue_ref(r), r["track_count"]) for r in rows]

    def queue_art_ids(self, queue_id, limit=4):
        rows = self._conn.execute(
            "SELECT album_id FROM queue_item WHERE queue_id = ? "
            "AND album_id IS NOT NULL ORDER BY position",
            (queue_id,)).fetchall()
        seen = []
        for row in rows:
            album_id = row["album_id"]
            if album_id not in seen:
                seen.append(album_id)
            if len(seen) == limit:
                break
        return seen

    def relink_queue_items(self, library_id, moves):
        if not moves:
            return
        self._conn.executemany(
            "UPDATE queue_item SET track_id = ?, path = ? "
            "WHERE library_id = ? AND track_id IN (?, ?)",
            [(kept, path, library_id, kept, dropped)
             for kept, dropped, path in moves])
        self._conn.commit()

    def rewrite_queue_paths(self, old_root, new_root):
        rows = self._conn.execute("SELECT rowid, path FROM queue_item").fetchall()
        updates = []
        for row in rows:
            rel = paths.to_rel(old_root, row["path"])
            if rel is not None:
                updates.append((paths.to_abs(new_root, rel), row["rowid"]))
        if updates:
            self._conn.executemany(
                "UPDATE queue_item SET path = ? WHERE rowid = ?", updates)
            self._conn.commit()
