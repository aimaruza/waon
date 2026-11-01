
import os
import pathlib
import shutil
import sqlite3
import time
import uuid

from waon.library.entities import VARIOUS_ARTISTS

APP_SCHEMA_VERSION = 9
LIBRARY_SCHEMA_VERSION = 11


class SchemaTooNewError(Exception):
    pass


class LibraryCorruptError(Exception):
    pass


_APP_SCHEMA_V1 = """
CREATE TABLE library (
    id       INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    color    TEXT    NOT NULL,
    filename TEXT    NOT NULL UNIQUE,
    position INTEGER NOT NULL
);

CREATE TABLE queue (
    id             INTEGER PRIMARY KEY,
    source_kind    TEXT    NOT NULL,
    source_label   TEXT    NOT NULL,
    source_library TEXT    NOT NULL,
    current_pos    INTEGER NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL,
    last_played_at INTEGER
);

CREATE TABLE queue_item (
    queue_id INTEGER NOT NULL REFERENCES queue(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    path     TEXT    NOT NULL,
    title    TEXT    NOT NULL,
    artist   TEXT    NOT NULL,
    album    TEXT    NOT NULL,
    duration REAL    NOT NULL,
    PRIMARY KEY (queue_id, position)
);

CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_APP_SCHEMA_V2 = """
DROP TABLE IF EXISTS queue_item;
DROP TABLE IF EXISTS queue;
DROP TABLE IF EXISTS library;

CREATE TABLE library (
    id       TEXT    NOT NULL PRIMARY KEY,
    name     TEXT    NOT NULL,
    color    TEXT    NOT NULL,
    position INTEGER NOT NULL
);

CREATE TABLE queue (
    id             TEXT    NOT NULL PRIMARY KEY,
    source_kind    TEXT    NOT NULL,
    source_label   TEXT    NOT NULL,
    source_library TEXT    NOT NULL,
    current_pos    INTEGER NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL,
    last_played_at INTEGER
);

CREATE TABLE queue_item (
    queue_id TEXT    NOT NULL REFERENCES queue(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    path     TEXT    NOT NULL,
    title    TEXT    NOT NULL,
    artist   TEXT    NOT NULL,
    album    TEXT    NOT NULL,
    duration REAL    NOT NULL,
    PRIMARY KEY (queue_id, position)
);
"""


def _migrate_app_v3(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(queue_item)")]
    if "track_id" not in cols:
        conn.execute("ALTER TABLE queue_item ADD COLUMN track_id TEXT")
    if "library_id" not in cols:
        conn.execute("ALTER TABLE queue_item ADD COLUMN library_id TEXT")


def _migrate_app_v4(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(library)")]
    if "icon" not in cols:
        conn.execute(
            "ALTER TABLE library ADD COLUMN icon TEXT NOT NULL DEFAULT ''")


def _migrate_app_v5(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(queue_item)")]
    if "album_id" not in cols:
        conn.execute("ALTER TABLE queue_item ADD COLUMN album_id TEXT")


def _migrate_app_v6(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(queue)")]
    if "dirty" not in cols:
        conn.execute(
            "ALTER TABLE queue ADD COLUMN dirty INTEGER NOT NULL DEFAULT 0")


def _migrate_app_v7(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(queue)")]
    if "position_seconds" not in cols:
        conn.execute(
            "ALTER TABLE queue ADD COLUMN position_seconds REAL NOT NULL DEFAULT 0")


def _migrate_app_v8(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(queue)")]
    if "owner_library_id" not in cols:
        conn.execute("ALTER TABLE queue ADD COLUMN owner_library_id TEXT")
    conn.execute(
        "UPDATE queue SET owner_library_id = ("
        "  SELECT MIN(qi.library_id) FROM queue_item qi WHERE qi.queue_id = queue.id) "
        "WHERE owner_library_id IS NULL"
        "  AND NOT EXISTS (SELECT 1 FROM queue_item qi"
        "                  WHERE qi.queue_id = queue.id AND qi.library_id IS NULL)"
        "  AND (SELECT COUNT(DISTINCT qi.library_id) FROM queue_item qi"
        "       WHERE qi.queue_id = queue.id) = 1"
        "  AND (SELECT MIN(qi.library_id) FROM queue_item qi"
        "       WHERE qi.queue_id = queue.id) IN (SELECT id FROM library)")


_V9_COLOUR_REMAP = {
    "#1d095b": "#417BFF",
    "#854d0e": "#E6540B",
    "#0e7490": "#198AA6",
    "#be185d": "#BF0A6A",
    "#075e54": "#369950",
    "#4338ca": "#7543BF",
    "#450a0a": "#BF0A16",
    "#111827": "#626673",
}


def _migrate_app_v9(conn):
    for old, new in _V9_COLOUR_REMAP.items():
        conn.execute("UPDATE library SET color = ? WHERE lower(color) = ?",
                     (new, old))


_LIBRARY_SCHEMA_V1 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE root (
    id       INTEGER PRIMARY KEY,
    path     TEXT    NOT NULL UNIQUE,
    position INTEGER NOT NULL
);

CREATE TABLE track (
    id           INTEGER PRIMARY KEY,
    rel_path     TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    root_hint_id INTEGER REFERENCES root(id) ON DELETE SET NULL,
    title        TEXT    NOT NULL,
    artist       TEXT    NOT NULL,
    album        TEXT    NOT NULL,
    album_artist TEXT    NOT NULL DEFAULT '',
    track_no     INTEGER,
    disc_no      INTEGER,
    duration     REAL    NOT NULL DEFAULT 0,
    mtime        INTEGER NOT NULL DEFAULT 0,
    size         INTEGER NOT NULL DEFAULT 0,
    available    INTEGER NOT NULL DEFAULT 1,
    added_at     INTEGER NOT NULL
);
CREATE INDEX idx_track_artist       ON track(artist);
CREATE INDEX idx_track_album        ON track(album);
CREATE INDEX idx_track_album_artist ON track(album_artist);

CREATE TABLE playlist (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE playlist_item (
    playlist_id INTEGER NOT NULL REFERENCES playlist(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    track_id    INTEGER NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    PRIMARY KEY (playlist_id, position)
);
"""

_LIBRARY_SCHEMA_V2 = """
DROP TABLE IF EXISTS playlist_item;
DROP TABLE IF EXISTS playlist;
DROP TABLE IF EXISTS track;
DROP TABLE IF EXISTS root;

CREATE TABLE root (
    id       TEXT    NOT NULL PRIMARY KEY,
    path     TEXT    NOT NULL UNIQUE,
    position INTEGER NOT NULL
);

CREATE TABLE track (
    id           TEXT    NOT NULL PRIMARY KEY,
    rel_path     TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    root_hint_id TEXT    REFERENCES root(id) ON DELETE SET NULL,
    title        TEXT    NOT NULL,
    artist       TEXT    NOT NULL,
    album        TEXT    NOT NULL,
    album_artist TEXT    NOT NULL DEFAULT '',
    track_no     INTEGER,
    disc_no      INTEGER,
    duration     REAL    NOT NULL DEFAULT 0,
    mtime        INTEGER NOT NULL DEFAULT 0,
    size         INTEGER NOT NULL DEFAULT 0,
    available    INTEGER NOT NULL DEFAULT 1,
    added_at     INTEGER NOT NULL
);
CREATE INDEX idx_track_artist       ON track(artist);
CREATE INDEX idx_track_album        ON track(album);
CREATE INDEX idx_track_album_artist ON track(album_artist);

CREATE TABLE playlist (
    id         TEXT    NOT NULL PRIMARY KEY,
    name       TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE playlist_item (
    playlist_id TEXT    NOT NULL REFERENCES playlist(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    track_id    TEXT    NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    PRIMARY KEY (playlist_id, position)
);
"""

_LIBRARY_SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS album (
    id            TEXT    NOT NULL PRIMARY KEY,
    name          TEXT    NOT NULL,
    album_artist  TEXT    NOT NULL,
    release_date  TEXT,
    art_status    TEXT    NOT NULL DEFAULT 'pending',
    created_at    INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_album_identity
    ON album(name COLLATE NOCASE, album_artist COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_album_artist ON album(album_artist);
"""


def _migrate_library_v3(conn):
    conn.executescript(_LIBRARY_SCHEMA_V3)
    if "album_id" not in [r["name"] for r in conn.execute("PRAGMA table_info(track)")]:
        conn.execute(
            "ALTER TABLE track ADD COLUMN album_id TEXT "
            "REFERENCES album(id) ON DELETE SET NULL")

    now = int(time.time())
    resolved = {}
    track_updates = []
    rows = conn.execute(
        "SELECT id, album, COALESCE(NULLIF(album_artist, ''), ?) AS aa "
        "FROM track", (VARIOUS_ARTISTS,)).fetchall()
    for row in rows:
        track_id, name, album_artist = row["id"], row["album"], row["aa"]
        key = (name.lower(), album_artist.lower())
        album_id = resolved.get(key)
        if album_id is None:
            new_id = str(uuid.uuid4())
            conn.execute(
                "INSERT OR IGNORE INTO album (id, name, album_artist, "
                "release_date, art_status, created_at) "
                "VALUES (?, ?, ?, NULL, 'pending', ?)",
                (new_id, name, album_artist, now))
            album_id = conn.execute(
                "SELECT id FROM album WHERE name = ? COLLATE NOCASE "
                "AND album_artist = ? COLLATE NOCASE",
                (name, album_artist)).fetchone()["id"]
            resolved[key] = album_id
        track_updates.append((album_id, track_id))
    conn.executemany("UPDATE track SET album_id = ? WHERE id = ?", track_updates)


_LIBRARY_SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS play_event (
    id        TEXT    NOT NULL PRIMARY KEY,
    track_id  TEXT    NOT NULL REFERENCES track(id) ON DELETE CASCADE,
    played_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_play_event_track ON play_event(track_id);
CREATE INDEX IF NOT EXISTS idx_play_event_played_at ON play_event(played_at);
"""


_LIBRARY_SCHEMA_V5 = """
CREATE TABLE IF NOT EXISTS excluded_folder (
    id         TEXT    NOT NULL PRIMARY KEY,
    root_id    TEXT    NOT NULL REFERENCES root(id) ON DELETE CASCADE,
    rel_path   TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_excluded_folder_root ON excluded_folder(root_id);
"""


def _migrate_library_v6(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(playlist)")]
    if "locked" not in cols:
        conn.execute(
            "ALTER TABLE playlist ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")


_LIBRARY_SCHEMA_V7 = """
CREATE INDEX IF NOT EXISTS idx_album_created_at ON album(created_at);
"""

_LIBRARY_SCHEMA_V8 = """
DROP INDEX IF EXISTS idx_album_identity;
CREATE UNIQUE INDEX IF NOT EXISTS idx_album_identity
    ON album(name COLLATE NOCASE, album_artist COLLATE NOCASE, release_date);
"""


def _migrate_library_v9(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(track)")]
    if "favorited_at" not in cols:
        conn.execute("ALTER TABLE track ADD COLUMN favorited_at INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_favorited_at "
        "ON track(favorited_at)")


_LIBRARY_SCHEMA_V10 = """
CREATE INDEX IF NOT EXISTS idx_track_album_id ON track(album_id);
CREATE INDEX IF NOT EXISTS idx_playlist_item_track ON playlist_item(track_id);
"""


def _migrate_library_v11(conn):
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(playlist)")]
    if "updated_at" not in cols:
        conn.execute(
            "ALTER TABLE playlist ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        "UPDATE playlist SET updated_at = created_at WHERE updated_at = 0")


_APP_MIGRATIONS = [(1, _APP_SCHEMA_V1), (2, _APP_SCHEMA_V2), (3, _migrate_app_v3),
                   (4, _migrate_app_v4), (5, _migrate_app_v5), (6, _migrate_app_v6),
                   (7, _migrate_app_v7), (8, _migrate_app_v8), (9, _migrate_app_v9)]
_LIBRARY_MIGRATIONS = [(1, _LIBRARY_SCHEMA_V1), (2, _LIBRARY_SCHEMA_V2),
                       (3, _migrate_library_v3), (4, _LIBRARY_SCHEMA_V4),
                       (5, _LIBRARY_SCHEMA_V5), (6, _migrate_library_v6),
                       (7, _LIBRARY_SCHEMA_V7), (8, _LIBRARY_SCHEMA_V8),
                       (9, _migrate_library_v9), (10, _LIBRARY_SCHEMA_V10),
                       (11, _migrate_library_v11)]


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _migrate(conn, migrations, target, kind):
    current = _version(conn)
    if current > target:
        raise SchemaTooNewError(
            "This {} was written by a newer version of waon "
            "(schema {}, this build understands {}).".format(kind, current, target))
    for version, step in migrations:
        if current < version:
            if callable(step):
                step(conn)
            else:
                conn.executescript(step)
            conn.execute("PRAGMA user_version = {}".format(version))
            current = version
    conn.commit()


def open_app_db(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = None
    try:
        conn = connect(path)
        _migrate(conn, _APP_MIGRATIONS, APP_SCHEMA_VERSION, "app database")
        return conn, None
    except SchemaTooNewError:
        if conn is not None:
            conn.close()
        raise
    except sqlite3.DatabaseError:
        if conn is not None:
            conn.close()
        recovered = _move_aside(path)
        conn = connect(path)
        _migrate(conn, _APP_MIGRATIONS, APP_SCHEMA_VERSION, "app database")
        return conn, recovered


def open_library_db(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = None
    try:
        conn = connect(path)
        _migrate(conn, _LIBRARY_MIGRATIONS, LIBRARY_SCHEMA_VERSION, "library")
        return conn
    except SchemaTooNewError:
        if conn is not None:
            conn.close()
        raise
    except sqlite3.DatabaseError as exc:
        if conn is not None:
            conn.close()
        raise LibraryCorruptError(str(exc))


def open_library_db_readonly(path):
    if not os.path.exists(path):
        raise LibraryCorruptError("{} is missing".format(path))
    open_library_db(path).close()
    uri = pathlib.Path(os.path.abspath(path)).as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise LibraryCorruptError(str(exc))
    conn.row_factory = sqlite3.Row
    return conn


def _move_aside(path):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = "{}.corrupt-{}".format(path, stamp)
    shutil.move(path, target)
    return target
