
import time
import uuid

from waon.library import paths
from waon.library.entities import (
    METRIC_PLAYS, METRIC_TIME, DataTrack, ExcludedFolder, Playlist, Relink, Root,
    RecentAddition, SongFacts, TrackRow, VARIOUS_ARTISTS)


class NestedRootError(Exception):
    pass


class InvalidExclusionError(Exception):
    pass


def _root(row):
    return Root(id=row["id"], path=row["path"], position=row["position"])


def _artist_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "name":
        return "aa COLLATE NOCASE {}".format(d)
    if field == "songs":
        return "songs {}".format(d)
    if field == "albums":
        return "albums {}".format(d)
    if field == "duration":
        return "duration {}".format(d)
    raise ValueError("unknown artist sort field: {!r}".format(field))


def _album_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "name":
        return "a.name COLLATE NOCASE {}".format(d)
    if field == "songs":
        return "songs {}".format(d)
    if field == "duration":
        return "duration {}".format(d)
    if field == "year":
        return "a.release_date IS NULL, a.release_date COLLATE NOCASE {}".format(d)
    if field == "artist":
        return "a.album_artist COLLATE NOCASE {}".format(d)
    raise ValueError("unknown album sort field: {!r}".format(field))


def _playlist_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "name":
        return "p.name COLLATE NOCASE {}".format(d)
    if field == "songs":
        return "songs {}".format(d)
    if field == "duration":
        return "duration {}".format(d)
    raise ValueError("unknown playlist sort field: {!r}".format(field))


def _album_track_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "track_no":
        return ("disc_no IS NULL, disc_no {d}, track_no IS NULL, track_no {d}, "
                "title COLLATE NOCASE").format(d=d)
    if field == "title":
        return "title COLLATE NOCASE {}".format(d)
    if field == "artist":
        return "artist COLLATE NOCASE {}".format(d)
    if field == "duration":
        return "duration {}".format(d)
    raise ValueError("unknown album-detail track sort field: {!r}".format(field))


def _artist_track_major_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "year":
        return ("a.release_date IS NULL, a.release_date COLLATE NOCASE {d}, "
                "a.name COLLATE NOCASE").format(d=d)
    if field == "album":
        return "a.name COLLATE NOCASE {}".format(d)
    raise ValueError("unknown artist-detail group sort field: {!r}".format(field))


def _artist_track_flat_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "title":
        return "t.title COLLATE NOCASE {}".format(d)
    if field == "album":
        return "a.name COLLATE NOCASE {}".format(d)
    if field == "year":
        return "a.release_date IS NULL, a.release_date COLLATE NOCASE {}".format(d)
    if field == "duration":
        return "t.duration {}".format(d)
    raise ValueError("unknown artist-detail sort field: {!r}".format(field))


def _playlist_track_major_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "album":
        return "a.name COLLATE NOCASE {d}, a.album_artist COLLATE NOCASE".format(d=d)
    if field == "artist":
        return "a.album_artist COLLATE NOCASE {d}, a.name COLLATE NOCASE".format(d=d)
    if field == "year":
        return ("a.release_date IS NULL, a.release_date COLLATE NOCASE {d}, "
                "a.name COLLATE NOCASE, a.album_artist COLLATE NOCASE").format(d=d)
    raise ValueError("unknown playlist-detail group sort field: {!r}".format(field))


def _playlist_track_flat_order_by(field, direction):
    d = "ASC" if direction == "asc" else "DESC"
    if field == "position":
        return "pi.position {}".format(d)
    if field == "title":
        return "t.title COLLATE NOCASE {}".format(d)
    if field == "artist":
        return "t.artist COLLATE NOCASE {}".format(d)
    if field == "album":
        return "t.album COLLATE NOCASE {}".format(d)
    if field == "year":
        return "a.release_date IS NULL, a.release_date COLLATE NOCASE {}".format(d)
    if field == "duration":
        return "t.duration {}".format(d)
    raise ValueError("unknown playlist-detail sort field: {!r}".format(field))


def _exclusion(row):
    return ExcludedFolder(id=row["id"], root_id=row["root_id"], rel_path=row["rel_path"])


def _playlist(r):
    return Playlist(id=r["id"], name=r["name"], created_at=r["created_at"],
                    locked=bool(r["locked"]), updated_at=r["updated_at"])


def _track(row):
    return TrackRow(
        id=row["id"], rel_path=row["rel_path"], root_hint_id=row["root_hint_id"],
        title=row["title"], artist=row["artist"], album=row["album"],
        added_at=row["added_at"], album_artist=row["album_artist"],
        track_no=row["track_no"], disc_no=row["disc_no"],
        duration=row["duration"], mtime=row["mtime"], size=row["size"],
        available=row["available"], album_id=row["album_id"],
    )


RECENT_BATCH_GAP = 3600


def _addition(batch):
    first = batch[0]
    single = len(batch) == 1
    return RecentAddition(
        kind="track" if single else "album", album_id=first["album_id"],
        album=first["album_name"], album_artist=first["album_aa"],
        added_at=batch[-1]["added_at"] or 0, row=_track(first) if single else None)


def _addition_order(addition):
    if addition.row is not None:
        return (-addition.added_at, (addition.row.title or "").lower(), addition.row.id)
    return (-addition.added_at, (addition.album or "").lower(), addition.album_id)
def _recap_order(metric, name_sql, id_sql):
    if metric == METRIC_PLAYS:
        keys = "n DESC, secs DESC"
    elif metric == METRIC_TIME:
        keys = "secs DESC, n DESC"
    else:
        raise ValueError("unknown recap metric {!r}".format(metric))
    return " ORDER BY {}, {} COLLATE NOCASE, {}".format(keys, name_sql, id_sql)


def _split_artist(raw):
    return [p.strip() for p in raw.split("/") if p.strip()]


SONG_LIST_KINDS = ("all", "added", "played", "most", "never", "favorites")

MOST_PLAYED_LIMIT = 100


class LibraryRepo:

    def __init__(self, conn):
        self._conn = conn
        self._album_cache = None


    def get_meta(self, key, default=None):
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else default

    def set_meta(self, key, value):
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)))
        self._conn.commit()


    def add_root(self, path):
        existing = self.roots()
        conflict = paths.nested_conflict(path, [r.path for r in existing])
        if conflict is not None:
            raise NestedRootError(
                "{} overlaps the existing root {}".format(path, conflict))
        position = len(existing)
        root_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO root (id, path, position) VALUES (?, ?, ?)",
            (root_id, path, position))
        self._conn.commit()
        return Root(id=root_id, path=path, position=position)

    def roots(self):
        rows = self._conn.execute("SELECT * FROM root ORDER BY position").fetchall()
        return [_root(r) for r in rows]

    def root(self, root_id):
        row = self._conn.execute(
            "SELECT * FROM root WHERE id = ?", (root_id,)).fetchone()
        return _root(row) if row is not None else None

    def set_root_path(self, root_id, new_path):
        self._conn.execute("UPDATE root SET path = ? WHERE id = ?",
                           (new_path, root_id))
        self._conn.commit()

    def add_exclusion(self, root_id, rel_path):
        if rel_path == "":
            raise InvalidExclusionError(
                "That's the whole folder -- remove it instead of excluding it.")
        key = (root_id, paths.norm_key(rel_path))
        if any((e.root_id, paths.norm_key(e.rel_path)) == key
               for e in self.exclusions()):
            raise InvalidExclusionError("That folder is already excluded.")
        exclusion_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO excluded_folder (id, root_id, rel_path, created_at) "
            "VALUES (?, ?, ?, ?)",
            (exclusion_id, root_id, rel_path, int(time.time())))
        self._conn.commit()
        return ExcludedFolder(id=exclusion_id, root_id=root_id, rel_path=rel_path)

    def exclusions(self):
        rows = self._conn.execute(
            "SELECT * FROM excluded_folder ORDER BY rel_path COLLATE NOCASE").fetchall()
        return [_exclusion(r) for r in rows]

    def remove_exclusion(self, exclusion_id):
        self._conn.execute("DELETE FROM excluded_folder WHERE id = ?", (exclusion_id,))
        self._conn.commit()


    def _album_cache_map(self):
        if self._album_cache is None:
            rows = self._conn.execute(
                "SELECT id, name, album_artist, release_date FROM album").fetchall()
            cache = {}
            for r in rows:
                name_key = (r["name"].lower(), r["album_artist"].lower())
                cache.setdefault(name_key, {})[r["release_date"]] = r["id"]
            self._album_cache = cache
        return self._album_cache

    def _resolve_album_id(self, name, album_artist, release_date=None):
        cache = self._album_cache_map()
        name_key = (name.lower(), album_artist.lower())
        bucket = cache.setdefault(name_key, {})
        if release_date in bucket:
            return bucket[release_date]
        if release_date is None and bucket:
            return next(iter(bucket.values()))
        if release_date is not None and list(bucket) == [None]:
            return bucket[None]
        new_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT OR IGNORE INTO album (id, name, album_artist, "
            "release_date, art_status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (new_id, name, album_artist, release_date, int(time.time())))
        row = self._conn.execute(
            "SELECT id FROM album WHERE name = ? COLLATE NOCASE "
            "AND album_artist = ? COLLATE NOCASE AND release_date IS ?",
            (name, album_artist, release_date)).fetchone()
        bucket[release_date] = row["id"]
        return row["id"]

    _INSERT_SQL = (
        "INSERT OR IGNORE INTO track "
        "(id, rel_path, root_hint_id, title, artist, album, album_artist, "
        " album_id, track_no, disc_no, duration, mtime, size, available, added_at) "
        "VALUES (:id, :rel_path, :root_hint_id, :title, :artist, :album, "
        "        :album_artist, :album_id, :track_no, :disc_no, :duration, :mtime, "
        "        :size, 1, :added_at)"
    )

    _UPDATE_SQL = (
        "UPDATE track SET root_hint_id = :root_hint_id, title = :title, "
        "artist = :artist, album = :album, album_artist = :album_artist, "
        "album_id = :album_id, "
        "track_no = :track_no, disc_no = :disc_no, duration = :duration, "
        "mtime = :mtime, size = :size, available = 1 WHERE id = :id"
    )

    def insert_tracks(self, records):
        if not records:
            return 0
        for record in records:
            effective = record["album_artist"] or VARIOUS_ARTISTS
            record["album_id"] = self._resolve_album_id(
                record["album"], effective, record.get("release_date"))
        before = self.track_count(available_only=False)
        self._conn.executemany(self._INSERT_SQL, records)
        self._conn.commit()
        return self.track_count(available_only=False) - before

    def update_tracks(self, records):
        if not records:
            return
        for record in records:
            effective = record["album_artist"] or VARIOUS_ARTISTS
            record["album_id"] = self._resolve_album_id(
                record["album"], effective, record.get("release_date"))
        self._conn.executemany(self._UPDATE_SQL, records)
        self._conn.commit()

    def touch_tracks(self, pairs):
        if not pairs:
            return
        self._conn.executemany(
            "UPDATE track SET available = 1, root_hint_id = ? WHERE id = ?",
            [(root_id, track_id) for track_id, root_id in pairs])
        self._conn.commit()

    def mark_unavailable(self, track_ids):
        if not track_ids:
            return
        self._conn.executemany(
            "UPDATE track SET available = 0 WHERE id = ?",
            [(track_id,) for track_id in track_ids])
        self._conn.commit()

    _RELINK_COLUMNS = ("rel_path", "root_hint_id", "title", "artist", "album",
                       "album_artist", "album_id", "track_no", "disc_no",
                       "duration", "mtime", "size")

    def relink_moved_tracks(self, new_ids=()):
        cols = "id, size, mtime, title, artist, album, added_at"
        gone = self._conn.execute(
            "SELECT " + cols + " FROM track WHERE available = 0 "
            "AND size > 0 AND mtime > 0").fetchall()
        if not gone:
            return []
        live = self._conn.execute(
            "SELECT " + cols + " FROM track WHERE available = 1 "
            "AND size > 0 AND mtime > 0").fetchall()

        def key(row):
            return (row["size"], row["mtime"], row["title"], row["artist"],
                    row["album"])

        new_ids = set(new_ids)
        gone_by_key, live_by_key = {}, {}
        for row in gone:
            gone_by_key.setdefault(key(row), []).append(row)
        for row in live:
            live_by_key.setdefault(key(row), []).append(row)
        pairs = []
        for k, gone_rows in gone_by_key.items():
            live_rows = live_by_key.get(k, ())
            if len(gone_rows) != 1 or len(live_rows) != 1:
                continue
            old, new = gone_rows[0], live_rows[0]
            if new["id"] in new_ids or new["added_at"] > old["added_at"]:
                pairs.append((old["id"], new["id"]))
        if not pairs:
            return []

        assignments = ", ".join("{} = ?".format(c) for c in self._RELINK_COLUMNS)
        relinks = []
        try:
            for kept_id, dropped_id in pairs:
                source = self._conn.execute(
                    "SELECT * FROM track WHERE id = ?", (dropped_id,)).fetchone()
                self._conn.execute(
                    "UPDATE play_event SET track_id = ? WHERE track_id = ?",
                    (kept_id, dropped_id))
                self._conn.execute(
                    "UPDATE playlist_item SET track_id = ? WHERE track_id = ?",
                    (kept_id, dropped_id))
                self._conn.execute("DELETE FROM track WHERE id = ?", (dropped_id,))
                self._conn.execute(
                    "UPDATE track SET " + assignments + ", available = 1 "
                    "WHERE id = ?",
                    tuple(source[c] for c in self._RELINK_COLUMNS) + (kept_id,))
                self._conn.execute(
                    "UPDATE track SET favorited_at = COALESCE(favorited_at, ?) "
                    "WHERE id = ?", (source["favorited_at"], kept_id))
                relinks.append(Relink(kept_id=kept_id, dropped_id=dropped_id,
                                      root_id=source["root_hint_id"],
                                      rel_path=source["rel_path"]))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return relinks


    def data_tracks(self, referenced_only=False):
        sql = (
            "SELECT t.id AS id, "
            "COALESCE(a.album_artist, NULLIF(t.album_artist, ''), ?) AS album_artist, "
            "t.artist AS artist, t.album AS album, t.title AS title, "
            "a.release_date AS release_date, t.disc_no AS disc_no, "
            "t.track_no AS track_no, t.duration AS duration, "
            "t.rel_path AS rel_path "
            "FROM track t LEFT JOIN album a ON a.id = t.album_id")
        if referenced_only:
            sql += (" WHERE t.id IN (SELECT track_id FROM play_event) "
                    "OR t.id IN (SELECT track_id FROM playlist_item) "
                    "OR t.favorited_at IS NOT NULL")
        rows = self._conn.execute(sql, (VARIOUS_ARTISTS,)).fetchall()
        return [DataTrack(id=r["id"], album_artist=r["album_artist"],
                          artist=r["artist"], album=r["album"], title=r["title"],
                          release_date=r["release_date"], disc_no=r["disc_no"],
                          track_no=r["track_no"], duration=r["duration"],
                          rel_path=r["rel_path"])
                for r in rows]

    def play_history(self):
        rows = self._conn.execute(
            "SELECT track_id, played_at FROM play_event "
            "ORDER BY played_at, id").fetchall()
        return [(r["track_id"], r["played_at"]) for r in rows]

    def playlist_contents(self):
        playlists = self._conn.execute(
            "SELECT * FROM playlist ORDER BY created_at, name COLLATE NOCASE"
        ).fetchall()
        result = []
        for row in playlists:
            items = self._conn.execute(
                "SELECT track_id FROM playlist_item WHERE playlist_id = ? "
                "ORDER BY position", (row["id"],)).fetchall()
            result.append((_playlist(row), [i["track_id"] for i in items]))
        return result

    def import_library_data(self, plays, playlists, favorites=()):
        try:
            seen = set((r["track_id"], r["played_at"]) for r in self._conn.execute(
                "SELECT track_id, played_at FROM play_event"))
            added = 0
            for track_id, played_at in plays:
                if (track_id, played_at) in seen:
                    continue
                seen.add((track_id, played_at))
                self._conn.execute(
                    "INSERT INTO play_event (id, track_id, played_at) "
                    "VALUES (?, ?, ?)", (str(uuid.uuid4()), track_id, played_at))
                added += 1

            taken = set(r["name"].lower() for r in self._conn.execute(
                "SELECT name FROM playlist"))
            names = []
            for name, created_at, locked, track_ids in playlists:
                final = name
                n = 1
                while final.lower() in taken:
                    final = ("{} (imported)".format(name) if n == 1
                             else "{} (imported {})".format(name, n))
                    n += 1
                taken.add(final.lower())
                playlist_id = str(uuid.uuid4())
                self._conn.execute(
                    "INSERT INTO playlist (id, name, created_at, locked, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (playlist_id, final, created_at, 1 if locked else 0, created_at))
                self._conn.executemany(
                    "INSERT INTO playlist_item (playlist_id, position, track_id) "
                    "VALUES (?, ?, ?)",
                    [(playlist_id, i, tid) for i, tid in enumerate(track_ids)])
                names.append(final)
            favorites_added = 0
            for track_id, favorited_at in favorites:
                cur = self._conn.execute(
                    "UPDATE track SET favorited_at = ? "
                    "WHERE id = ? AND favorited_at IS NULL",
                    (favorited_at, track_id))
                favorites_added += cur.rowcount
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return added, names, favorites_added

    def record_play(self, track_id, played_at):
        self._conn.execute(
            "INSERT INTO play_event (id, track_id, played_at) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), track_id, played_at))
        self._conn.commit()

    def play_stats(self, track_id):
        row = self._conn.execute(
            "SELECT COUNT(*) AS n, MIN(played_at) AS first, "
            "MAX(played_at) AS last FROM play_event WHERE track_id = ?",
            (track_id,)).fetchone()
        return (row["n"], row["first"], row["last"])

    def delete_plays(self, track_id):
        cur = self._conn.execute(
            "DELETE FROM play_event WHERE track_id = ?", (track_id,))
        self._conn.commit()
        return cur.rowcount


    def set_favorite(self, track_id, on):
        if on:
            self._conn.execute(
                "UPDATE track SET favorited_at = ? "
                "WHERE id = ? AND favorited_at IS NULL",
                (int(time.time()), track_id))
        else:
            self._conn.execute(
                "UPDATE track SET favorited_at = NULL WHERE id = ?", (track_id,))
        self._conn.commit()

    def is_favorite(self, track_id):
        row = self._conn.execute(
            "SELECT favorited_at FROM track WHERE id = ?", (track_id,)).fetchone()
        return row is not None and row["favorited_at"] is not None

    def favorite_tracks(self):
        rows = self._conn.execute(
            "SELECT * FROM track WHERE favorited_at IS NOT NULL AND available = 1 "
            "ORDER BY favorited_at DESC, title COLLATE NOCASE, id").fetchall()
        return [_track(r) for r in rows]

    def favorites(self):
        rows = self._conn.execute(
            "SELECT id, favorited_at FROM track WHERE favorited_at IS NOT NULL "
            "ORDER BY favorited_at, id").fetchall()
        return [(r["id"], r["favorited_at"]) for r in rows]


    _SONG_SORT = {
        "title": "t.title COLLATE NOCASE {d}",
        "artist": "t.artist COLLATE NOCASE {d}",
        "album": "t.album COLLATE NOCASE {d}",
        "year": "a.release_date IS NULL, a.release_date COLLATE NOCASE {d}",
        "duration": "t.duration {d}",
        "added": "t.added_at {d}",
        "last_played": "s.last_played {d}",
        "plays": "s.plays {d}, s.secs {d}",
        "favorited": "t.favorited_at {d}",
    }
    _SONG_SORT_OWNER = {"last_played": "played", "plays": "most",
                        "favorited": "favorites"}

    def _songs_from(self, kind, since):
        if kind not in SONG_LIST_KINDS:
            raise ValueError("unknown song list {!r}".format(kind))
        sql = "FROM track t LEFT JOIN album a ON a.id = t.album_id "
        params = []
        where = ["t.available = 1"]
        if kind == "played":
            sub = ("SELECT track_id, MAX(played_at) AS last_played "
                   "FROM play_event")
            if since is not None:
                sub += " WHERE played_at >= ?"
                params.append(since)
            sql += "JOIN (" + sub + " GROUP BY track_id) s ON s.track_id = t.id "
        elif kind == "most":
            sub = ("SELECT p.track_id AS track_id, COUNT(*) AS plays, "
                   "SUM(t2.duration) AS secs FROM play_event p "
                   "JOIN track t2 ON t2.id = p.track_id WHERE t2.available = 1")
            if since is not None:
                sub += " AND p.played_at >= ?"
                params.append(since)
            sub += (" GROUP BY p.track_id ORDER BY plays DESC, secs DESC, "
                    "t2.title COLLATE NOCASE, p.track_id LIMIT ?")
            params.append(MOST_PLAYED_LIMIT)
            sql += "JOIN (" + sub + ") s ON s.track_id = t.id "
        elif kind == "added":
            if since is not None:
                where.append("t.added_at >= ?")
                params.append(since)
        elif kind == "never":
            where.append("NOT EXISTS (SELECT 1 FROM play_event p "
                         "WHERE p.track_id = t.id)")
        elif kind == "favorites":
            where.append("t.favorited_at IS NOT NULL")
        return sql + "WHERE " + " AND ".join(where), params

    def songs(self, kind, since=None, field="title", direction="asc"):
        template = self._SONG_SORT.get(field)
        owner = self._SONG_SORT_OWNER.get(field)
        if template is None or (owner is not None and owner != kind):
            raise ValueError("no sort field {!r} for song list {!r}"
                             .format(field, kind))
        d = "ASC" if direction == "asc" else "DESC"
        from_sql, params = self._songs_from(kind, since)
        rows = self._conn.execute(
            "SELECT t.* " + from_sql + " ORDER BY " + template.format(d=d) +
            ", t.title COLLATE NOCASE, t.id", params).fetchall()
        return [_track(r) for r in rows]

    def songs_count(self, kind, since=None):
        from_sql, params = self._songs_from(kind, since)
        return self._conn.execute(
            "SELECT COUNT(*) AS n " + from_sql, params).fetchone()["n"]


    def stat_index(self):
        rows = self._conn.execute(
            "SELECT id, rel_path, mtime, size FROM track").fetchall()
        return dict(
            (paths.norm_key(r["rel_path"]), (r["id"], r["mtime"], r["size"]))
            for r in rows)

    def track_by_rel_path(self, rel_path):
        row = self._conn.execute(
            "SELECT * FROM track WHERE rel_path = ? COLLATE NOCASE",
            (rel_path,)).fetchone()
        return _track(row) if row is not None else None

    def track_count(self, available_only=True):
        sql = "SELECT COUNT(*) AS n FROM track"
        if available_only:
            sql += " WHERE available = 1"
        return self._conn.execute(sql).fetchone()["n"]

    def total_duration(self):
        row = self._conn.execute(
            "SELECT COALESCE(SUM(duration), 0) AS total FROM track "
            "WHERE available = 1").fetchone()
        return float(row["total"])

    def all_tracks(self):
        rows = self._conn.execute(
            "SELECT * FROM track ORDER BY rel_path COLLATE NOCASE").fetchall()
        return [_track(r) for r in rows]

    def track_by_id(self, track_id):
        row = self._conn.execute(
            "SELECT * FROM track WHERE id = ?", (track_id,)).fetchone()
        return _track(row) if row is not None else None


    def create_playlist(self, name):
        created_at = int(time.time())
        playlist_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO playlist (id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (playlist_id, name, created_at, created_at))
        self._conn.commit()
        return Playlist(id=playlist_id, name=name, created_at=created_at,
                        updated_at=created_at)

    def playlists(self):
        rows = self._conn.execute(
            "SELECT * FROM playlist ORDER BY name COLLATE NOCASE").fetchall()
        return [_playlist(r) for r in rows]

    def playlists_by_updated(self):
        rows = self._conn.execute(
            "SELECT * FROM playlist "
            "ORDER BY updated_at DESC, name COLLATE NOCASE").fetchall()
        return [_playlist(r) for r in rows]

    def _touch_playlist(self, playlist_id):
        self._conn.execute(
            "UPDATE playlist SET updated_at = ? WHERE id = ?",
            (int(time.time()), playlist_id))

    def playlists_sorted(self, field="name", direction="asc"):
        order_by = _playlist_order_by(field, direction)
        rows = self._conn.execute(
            "SELECT p.id AS id, p.name AS name, p.created_at AS created_at, "
            "       p.locked AS locked, p.updated_at AS updated_at, "
            "       COUNT(pi.track_id) AS songs, "
            "       COALESCE(SUM(t.duration), 0) AS duration "
            "FROM playlist p "
            "LEFT JOIN playlist_item pi ON pi.playlist_id = p.id "
            "LEFT JOIN track t ON t.id = pi.track_id "
            "GROUP BY p.id "
            "ORDER BY {}, p.name COLLATE NOCASE".format(order_by)
        ).fetchall()
        return [(_playlist(r), r["songs"], r["duration"]) for r in rows]

    def rename_playlist(self, playlist_id, name):
        self._conn.execute(
            "UPDATE playlist SET name = ? WHERE id = ?", (name, playlist_id))
        self._conn.commit()

    def set_playlist_locked(self, playlist_id, locked):
        self._conn.execute(
            "UPDATE playlist SET locked = ? WHERE id = ?",
            (1 if locked else 0, playlist_id))
        self._conn.commit()

    def remove_from_playlist(self, playlist_id, track_id):
        self._conn.execute(
            "DELETE FROM playlist_item WHERE playlist_id = ? AND position = ("
            "  SELECT MIN(position) FROM playlist_item"
            "  WHERE playlist_id = ? AND track_id = ?)",
            (playlist_id, playlist_id, track_id))
        self._touch_playlist(playlist_id)
        self._conn.commit()

    def remove_tracks_from_playlist(self, playlist_id, track_ids):
        if not track_ids:
            return
        self._conn.executemany(
            "DELETE FROM playlist_item WHERE playlist_id = ? AND track_id = ?",
            [(playlist_id, track_id) for track_id in track_ids])
        self._touch_playlist(playlist_id)
        self._conn.commit()

    def playlist_track_ids(self, playlist_id):
        rows = self._conn.execute(
            "SELECT track_id FROM playlist_item WHERE playlist_id = ? "
            "ORDER BY position", (playlist_id,)).fetchall()
        return [r["track_id"] for r in rows]

    def playlist_membership(self, track_ids):
        ids = list(dict.fromkeys(track_ids))
        counts = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            rows = self._conn.execute(
                "SELECT playlist_id AS pid, COUNT(DISTINCT track_id) AS n "
                "FROM playlist_item WHERE track_id IN ({}) "
                "GROUP BY playlist_id".format(",".join("?" * len(chunk))),
                chunk).fetchall()
            for r in rows:
                counts[r["pid"]] = counts.get(r["pid"], 0) + r["n"]
        return counts

    def delete_playlist(self, playlist_id):
        self._conn.execute("DELETE FROM playlist WHERE id = ?", (playlist_id,))
        self._conn.commit()

    def add_to_playlist(self, playlist_id, track_ids):
        if not track_ids:
            return
        row = self._conn.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) AS next FROM playlist_item "
            "WHERE playlist_id = ?", (playlist_id,)).fetchone()
        start = row["next"]
        self._conn.executemany(
            "INSERT INTO playlist_item (playlist_id, position, track_id) "
            "VALUES (?, ?, ?)",
            [(playlist_id, start + i, track_id)
             for i, track_id in enumerate(track_ids)])
        self._touch_playlist(playlist_id)
        self._conn.commit()

    def playlist_by_name(self, name):
        row = self._conn.execute(
            "SELECT * FROM playlist WHERE name = ? COLLATE NOCASE",
            (name,)).fetchone()
        return None if row is None else _playlist(row)

    def replace_playlist_tracks(self, playlist_id, track_ids):
        self._conn.execute(
            "DELETE FROM playlist_item WHERE playlist_id = ?", (playlist_id,))
        self._touch_playlist(playlist_id)
        self._conn.commit()
        self.add_to_playlist(playlist_id, track_ids)

    def playlist_track_counts(self):
        rows = self._conn.execute(
            "SELECT playlist_id AS pid, COUNT(*) AS n FROM playlist_item "
            "GROUP BY playlist_id").fetchall()
        return dict((r["pid"], r["n"]) for r in rows)

    def playlist_tracks(self, playlist_id, group=False, field="position", direction="asc"):
        if group:
            order = (_playlist_track_major_order_by(field, direction) +
                     ", t.disc_no IS NULL, t.disc_no, t.track_no IS NULL, "
                     "t.track_no, t.title COLLATE NOCASE")
        else:
            order = _playlist_track_flat_order_by(field, direction)
        rows = self._conn.execute(
            "SELECT t.* FROM playlist_item pi JOIN track t ON t.id = pi.track_id "
            "LEFT JOIN album a ON a.id = t.album_id "
            "WHERE pi.playlist_id = ? ORDER BY " + order,
            (playlist_id,)).fetchall()
        return [_track(r) for r in rows]


    def root_track_counts(self):
        rows = self._conn.execute(
            "SELECT root_hint_id AS rid, COUNT(*) AS n FROM track "
            "WHERE root_hint_id IS NOT NULL GROUP BY root_hint_id").fetchall()
        return dict((r["rid"], r["n"]) for r in rows)

    def remove_root_impact(self, root_id):
        tracks = self._conn.execute(
            "SELECT COUNT(*) AS n FROM track WHERE root_hint_id = ?",
            (root_id,)).fetchone()["n"]
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT pi.track_id) AS tracks, "
            "       COUNT(DISTINCT pi.playlist_id) AS playlists "
            "FROM playlist_item pi JOIN track t ON t.id = pi.track_id "
            "WHERE t.root_hint_id = ?", (root_id,)).fetchone()
        plays = self._conn.execute(
            "SELECT COUNT(*) AS n FROM play_event p JOIN track t ON t.id = p.track_id "
            "WHERE t.root_hint_id = ?", (root_id,)).fetchone()["n"]
        favorites = self._conn.execute(
            "SELECT COUNT(*) AS n FROM track WHERE root_hint_id = ? "
            "AND favorited_at IS NOT NULL", (root_id,)).fetchone()["n"]
        return {"tracks": tracks, "playlist_tracks": row["tracks"],
                "playlists": row["playlists"], "plays": plays,
                "favorites": favorites}

    def delete_orphaned_albums(self):
        rows = self._conn.execute(
            "SELECT id FROM album WHERE id NOT IN "
            "(SELECT DISTINCT album_id FROM track WHERE album_id IS NOT NULL)"
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            self._conn.executemany(
                "DELETE FROM album WHERE id = ?", [(i,) for i in ids])
            self._conn.commit()
            self._album_cache = None
        return ids

    def remove_root(self, root_id):
        self._conn.execute("DELETE FROM track WHERE root_hint_id = ?", (root_id,))
        orphaned = self.delete_orphaned_albums()
        self._conn.execute("DELETE FROM root WHERE id = ?", (root_id,))
        self._conn.commit()
        return orphaned


    def artists(self):
        rows = self._conn.execute(
            "SELECT a.album_artist AS aa, COUNT(DISTINCT a.id) AS n "
            "FROM album a JOIN track t ON t.album_id = a.id AND t.available = 1 "
            "GROUP BY a.album_artist COLLATE NOCASE "
            "ORDER BY aa COLLATE NOCASE").fetchall()
        return [(r["aa"], r["n"]) for r in rows]

    def artists_sorted(self, field="name", direction="asc"):
        order_by = _artist_order_by(field, direction)
        rows = self._conn.execute(
            "SELECT a.album_artist AS aa, COUNT(DISTINCT a.id) AS albums, "
            "       COUNT(t.id) AS songs, COALESCE(SUM(t.duration), 0) AS duration "
            "FROM album a JOIN track t ON t.album_id = a.id AND t.available = 1 "
            "GROUP BY a.album_artist COLLATE NOCASE "
            "ORDER BY {}, aa COLLATE NOCASE".format(order_by)
        ).fetchall()
        return [(r["aa"], r["albums"], r["songs"], r["duration"]) for r in rows]

    _ALBUM_MAJOR_ORDER = (
        "ORDER BY a.release_date IS NULL, a.release_date COLLATE NOCASE, "
        "         a.name COLLATE NOCASE, "
        "         t.disc_no IS NULL, t.disc_no, t.track_no IS NULL, t.track_no, "
        "         t.title COLLATE NOCASE"
    )

    def tracks_by_artist(self, artist, group=True, field="year", direction="asc"):
        if group:
            order = (_artist_track_major_order_by(field, direction) +
                     ", t.disc_no IS NULL, t.disc_no, t.track_no IS NULL, "
                     "t.track_no, t.title COLLATE NOCASE")
        else:
            order = _artist_track_flat_order_by(field, direction)
        rows = self._conn.execute(
            "SELECT t.* FROM track t JOIN album a ON a.id = t.album_id "
            "WHERE t.available = 1 AND a.album_artist = ? COLLATE NOCASE "
            "ORDER BY " + order, (artist,)).fetchall()
        return [_track(r) for r in rows]

    def featured_artists(self):
        primary = {name.lower() for name, _n in self.artists()}
        rows = self._conn.execute(
            "SELECT artist FROM track WHERE available = 1 AND artist LIKE '%/%' "
            "ORDER BY artist"
        ).fetchall()
        counts = {}
        for row in rows:
            raw = row["artist"]
            if raw.strip().lower() in primary:
                continue
            seen = set()
            for token in _split_artist(raw)[1:]:
                key = token.lower()
                if key in primary or key in seen:
                    continue
                seen.add(key)
                entry = counts.setdefault(key, [token, 0])
                entry[1] += 1
        return sorted(((name, n) for name, n in counts.values()),
                      key=lambda pair: pair[0].lower())

    def tracks_featuring(self, artist):
        target = artist.strip().lower()
        primary = {name.lower() for name, _n in self.artists()}
        rows = self._conn.execute(
            "SELECT t.* FROM track t JOIN album a ON a.id = t.album_id "
            "WHERE t.available = 1 AND t.artist LIKE '%/%' " +
            self._ALBUM_MAJOR_ORDER
        ).fetchall()
        result = []
        for r in rows:
            raw = r["artist"]
            if raw.strip().lower() in primary:
                continue
            if target in (tok.lower() for tok in _split_artist(raw)[1:]):
                result.append(_track(r))
        return result

    def albums(self):
        rows = self._conn.execute(
            "SELECT a.id AS album_id, a.name AS album, a.album_artist AS aa, "
            "       COUNT(t.id) AS n "
            "FROM album a JOIN track t ON t.album_id = a.id AND t.available = 1 "
            "GROUP BY a.id "
            "ORDER BY a.name COLLATE NOCASE, a.album_artist COLLATE NOCASE"
        ).fetchall()
        return [(r["album_id"], r["album"], r["aa"], r["n"]) for r in rows]

    def albums_sorted(self, field="name", direction="asc"):
        order_by = _album_order_by(field, direction)
        rows = self._conn.execute(
            "SELECT a.id AS album_id, a.name AS album, a.album_artist AS aa, "
            "       COUNT(t.id) AS songs, COALESCE(SUM(t.duration), 0) AS duration, "
            "       a.release_date AS release_date "
            "FROM album a JOIN track t ON t.album_id = a.id AND t.available = 1 "
            "GROUP BY a.id "
            "ORDER BY {}, a.name COLLATE NOCASE, a.album_artist COLLATE NOCASE"
            .format(order_by)
        ).fetchall()
        return [(r["album_id"], r["album"], r["aa"], r["songs"], r["duration"],
                r["release_date"]) for r in rows]

    def recent_additions(self, limit=None):
        rows = self._conn.execute(
            "SELECT t.*, a.name AS album_name, a.album_artist AS album_aa "
            "FROM track t JOIN album a ON a.id = t.album_id "
            "WHERE t.available = 1 "
            "ORDER BY t.album_id, t.added_at, t.id").fetchall()
        batches, current = [], []
        for row in rows:
            if current and (row["album_id"] != current[-1]["album_id"]
                            or (row["added_at"] or 0) - (current[-1]["added_at"] or 0)
                            > RECENT_BATCH_GAP):
                batches.append(current)
                current = []
            current.append(row)
        if current:
            batches.append(current)
        additions = sorted((_addition(b) for b in batches), key=_addition_order)
        return additions if limit is None else additions[:limit]

    def album_artist_for_id(self, album_id):
        row = self._conn.execute(
            "SELECT album_artist FROM album WHERE id = ?", (album_id,)).fetchone()
        return row["album_artist"] if row is not None else None

    def album_release_date_for_id(self, album_id):
        row = self._conn.execute(
            "SELECT release_date FROM album WHERE id = ?", (album_id,)).fetchone()
        return row["release_date"] if row is not None else None

    def folder_tree(self):
        rows = self._conn.execute(
            "SELECT rel_path FROM track WHERE available = 1").fetchall()
        children = {}
        has_top_level = False
        for row in rows:
            parts = row["rel_path"].split("/")[:-1]
            if not parts:
                has_top_level = True
                continue
            parent_path = ""
            for part in parts:
                path = part if not parent_path else parent_path + "/" + part
                children.setdefault(paths.norm_key(parent_path), {})[
                    paths.norm_key(part)] = (part, path)
                parent_path = path

        result = [("", "", 0, False)] if has_top_level else []

        def walk(parent_path, depth):
            for _sort_key, (name, path) in sorted(
                    children.get(paths.norm_key(parent_path), {}).items()):
                result.append((path, name, depth, paths.norm_key(path) in children))
                walk(path, depth + 1)

        walk("", 0)
        return result

    def tracks_in_folder(self, folder):
        prefix = folder + "/" if folder else ""
        rows = self._conn.execute(
            "SELECT * FROM track WHERE available = 1 "
            "AND substr(rel_path, 1, ?) = ? COLLATE NOCASE "
            "AND instr(substr(rel_path, ?), '/') = 0 "
            "ORDER BY rel_path COLLATE NOCASE",
            (len(prefix), prefix, len(prefix) + 1)).fetchall()
        return [_track(r) for r in rows]


    def _period_clause(self, since, until):
        conditions, params = [], []
        if since is not None:
            conditions.append("p.played_at >= ?")
            params.append(since)
        if until is not None:
            conditions.append("p.played_at < ?")
            params.append(until)
        if not conditions:
            return "", ()
        return " WHERE " + " AND ".join(conditions), tuple(params)

    def top_tracks(self, since, limit, until=None, metric=METRIC_PLAYS):
        order = _recap_order(metric, "t.title", "t.id")
        clause, params = self._period_clause(since, until)
        rows = self._conn.execute(
            "SELECT t.*, COUNT(*) AS n, COALESCE(SUM(t.duration), 0) AS secs "
            "FROM play_event p JOIN track t ON t.id = p.track_id" + clause +
            " GROUP BY t.id" + order + " LIMIT ?",
            params + (limit,)).fetchall()
        return [(_track(r), r["n"], float(r["secs"])) for r in rows]

    def top_albums(self, since, limit, until=None, metric=METRIC_PLAYS):
        order = _recap_order(metric, "a.name", "a.id")
        clause, params = self._period_clause(since, until)
        rows = self._conn.execute(
            "SELECT a.id AS album_id, a.name AS album, a.album_artist AS aa, "
            "COUNT(*) AS n, COALESCE(SUM(t.duration), 0) AS secs "
            "FROM play_event p "
            "JOIN track t ON t.id = p.track_id "
            "JOIN album a ON a.id = t.album_id" + clause +
            " GROUP BY a.id" + order + " LIMIT ?",
            params + (limit,)).fetchall()
        return [(r["album_id"], r["album"], r["aa"], r["n"], float(r["secs"]))
                for r in rows]

    def total_listened_seconds(self, since, until=None):
        clause, params = self._period_clause(since, until)
        row = self._conn.execute(
            "SELECT COALESCE(SUM(t.duration), 0) AS total FROM play_event p "
            "JOIN track t ON t.id = p.track_id" + clause, params).fetchone()
        return float(row["total"])

    def top_artists(self, since, limit, until=None, metric=METRIC_PLAYS):
        if metric not in (METRIC_PLAYS, METRIC_TIME):
            raise ValueError("unknown recap metric {!r}".format(metric))
        primary = {name.lower() for name, _n in self.artists()}
        clause, params = self._period_clause(since, until)
        rows = self._conn.execute(
            "SELECT t.artist AS artist, t.duration AS duration FROM play_event p "
            "JOIN track t ON t.id = p.track_id" + clause +
            " ORDER BY t.artist", params).fetchall()
        totals = {}
        for row in rows:
            raw = row["artist"]
            tokens = [raw] if raw.strip().lower() in primary else _split_artist(raw)
            for token in tokens:
                entry = totals.setdefault(token.lower(), [token, 0, 0.0])
                entry[1] += 1
                entry[2] += float(row["duration"] or 0.0)
        if metric == METRIC_PLAYS:
            key = lambda e: (-e[1], -e[2], e[0].lower())
        else:
            key = lambda e: (-e[2], -e[1], e[0].lower())
        ranked = sorted(totals.values(), key=key)
        return [(name, n, secs) for name, n, secs in ranked[:limit]]

    def earliest_play_at(self):
        row = self._conn.execute(
            "SELECT MIN(played_at) AS earliest FROM play_event").fetchone()
        return row["earliest"]


    def album_release_dates(self):
        return {r["id"]: r["release_date"] for r in self._conn.execute(
            "SELECT id, release_date FROM album")}

    def play_counts(self):
        return {r["track_id"]: r["n"] for r in self._conn.execute(
            "SELECT track_id, COUNT(*) AS n FROM play_event GROUP BY track_id")}

    def album_play_counts(self):
        return {r["album_id"]: r["n"] for r in self._conn.execute(
            "SELECT t.album_id AS album_id, COUNT(*) AS n FROM play_event p "
            "JOIN track t ON t.id = p.track_id WHERE t.album_id IS NOT NULL "
            "GROUP BY t.album_id")}

    def song_facts(self, since=None):
        where, params = "", []
        if since is not None:
            where, params = " WHERE p.played_at >= ?", [since]
        rows = self._conn.execute(
            "SELECT t.*, a.release_date AS release_date, "
            "COALESCE(e.n, 0) AS plays_ever, COALESCE(w.n, 0) AS plays, "
            "COALESCE(w.secs, 0) AS secs, w.last AS last_played "
            "FROM track t LEFT JOIN album a ON a.id = t.album_id "
            "LEFT JOIN (SELECT track_id, COUNT(*) AS n FROM play_event "
            "           GROUP BY track_id) e ON e.track_id = t.id "
            "LEFT JOIN (SELECT p.track_id AS track_id, COUNT(*) AS n, "
            "                  SUM(t2.duration) AS secs, MAX(p.played_at) AS last "
            "           FROM play_event p JOIN track t2 ON t2.id = p.track_id" + where +
            "           GROUP BY p.track_id) w ON w.track_id = t.id "
            "WHERE t.available = 1", params).fetchall()
        return [SongFacts(row=_track(r), release_date=r["release_date"],
                          favorited_at=r["favorited_at"], plays_ever=r["plays_ever"],
                          plays=r["plays"], seconds=float(r["secs"]),
                          last_played=r["last_played"])
                for r in rows]


    def pending_album_ids(self):
        rows = self._conn.execute(
            "SELECT id FROM album WHERE art_status = 'pending'").fetchall()
        return [r["id"] for r in rows]

    def tracks_by_album_id(self, album_id, field="track_no", direction="asc"):
        order = _album_track_order_by(field, direction)
        rows = self._conn.execute(
            "SELECT * FROM track WHERE album_id = ? AND available = 1 "
            "ORDER BY " + order, (album_id,)).fetchall()
        return [_track(r) for r in rows]

    def set_album_art_statuses(self, pairs):
        if not pairs:
            return
        self._conn.executemany(
            "UPDATE album SET art_status = ? WHERE id = ?",
            [(status, album_id) for album_id, status in pairs])
        self._conn.commit()

    def artist_thumbnails(self):
        rows = self._conn.execute(
            "SELECT album_artist AS artist, id FROM album "
            "WHERE art_status = 'found' "
            "ORDER BY album_artist COLLATE NOCASE, "
            "release_date IS NULL, release_date DESC, created_at DESC"
        ).fetchall()
        result = {}
        for row in rows:
            result.setdefault(row["artist"].lower(), row["id"])
        return result

    def playlist_collage(self, playlist_id, limit=4):
        rows = self._conn.execute(
            "SELECT t.album_id AS aid FROM playlist_item pi "
            "JOIN track t ON t.id = pi.track_id "
            "JOIN album a ON a.id = t.album_id "
            "WHERE pi.playlist_id = ? AND a.art_status = 'found' "
            "ORDER BY pi.position", (playlist_id,)).fetchall()
        seen = []
        for row in rows:
            aid = row["aid"]
            if aid not in seen:
                seen.append(aid)
            if len(seen) >= limit:
                break
        return seen
