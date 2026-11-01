
import logging
import os
import sqlite3
import time
import uuid

from waon import playlist_file
from waon.library import db, locations, paths, porting
from waon.library.all_libraries import AllLibraries
from waon.library.app_repo import ANY_OWNER, AppRepo
from waon.library.entities import (
    ALL_LIBRARIES_ID, METRIC_PLAYS, BrowseEntry, ImportedPlaylist, LibraryImportResult, LibraryStats,
    PlaylistImportResult, UnmatchedTrack)
from waon.library.library_repo import LibraryRepo, SONG_LIST_KINDS
from waon.library.resolver import Resolver, availability_pass
from waon.util import format_duration, format_listened

log = logging.getLogger(__name__)

RAIL_ARTISTS = "artists"
RAIL_ALBUMS = "albums"
RAIL_FOLDERS = "folders"
RAIL_PLAYLISTS = "playlists"
RAIL_SONGS = "songs"
RAIL_QUEUES = "queues"
RAIL_HOME = "home"

BROWSABLE_RAIL_ITEMS = (RAIL_ARTISTS, RAIL_ALBUMS, RAIL_FOLDERS, RAIL_SONGS,
                        RAIL_PLAYLISTS)
LIBRARY_RAIL_ITEMS = (RAIL_HOME,) + BROWSABLE_RAIL_ITEMS

ALL_MODE_RAIL_ITEMS = (RAIL_HOME, RAIL_SONGS, RAIL_QUEUES)

GRID_RAIL_ITEMS = (RAIL_ARTISTS, RAIL_ALBUMS, RAIL_PLAYLISTS)

TOP_FOLDER_LABEL = "(top level)"

UNKNOWN_ALBUM_LABEL = "(no album)"

LAST_ADDED_LIMIT = 20

SETUP_PENDING_META = "setup_pending"

SORT_FIELDS = {
    RAIL_ARTISTS: ("name", "songs", "albums", "duration"),
    RAIL_ALBUMS: ("name", "songs", "duration", "year", "artist"),
    RAIL_PLAYLISTS: ("name", "songs", "duration"),
}
DEFAULT_SORT = ("name", "asc")

DETAIL_GROUP_RAIL_ITEMS = (RAIL_ARTISTS, RAIL_PLAYLISTS)
DETAIL_GROUP_DEFAULT = {RAIL_ARTISTS: True, RAIL_PLAYLISTS: False}

DETAIL_SORT_FIELDS = {
    (RAIL_ARTISTS, True): ("year", "album"),
    (RAIL_ARTISTS, False): ("title", "album", "year", "duration"),
    (RAIL_ALBUMS, False): ("track_no", "title", "artist", "duration"),
    (RAIL_PLAYLISTS, True): ("album", "artist", "year"),
    (RAIL_PLAYLISTS, False):
        ("position", "title", "artist", "album", "year", "duration"),
}
DETAIL_DEFAULT_SORT = {
    (RAIL_ARTISTS, True): ("year", "asc"),
    (RAIL_ARTISTS, False): ("title", "asc"),
    (RAIL_ALBUMS, False): ("track_no", "asc"),
    (RAIL_PLAYLISTS, True): ("album", "asc"),
    (RAIL_PLAYLISTS, False): ("position", "asc"),
}
SONGS_LIST_LABELS = {
    "all": "All songs", "added": "Recently added", "played": "Recently played",
    "most": "Most played", "never": "Never played", "favorites": "Favorites",
}
_DAY = 86400
SONGS_PERIOD_SECONDS = {"7d": 7 * _DAY, "30d": 30 * _DAY, "90d": 90 * _DAY,
                        "365d": 365 * _DAY, "all": None}
SONGS_PERIOD_LABELS = {"7d": "Last 7 days", "30d": "Last 30 days",
                       "90d": "Last 90 days", "365d": "Last 12 months",
                       "all": "All time"}
_SONGS_PERIOD_PHRASES = {"7d": "7 days", "30d": "30 days", "90d": "90 days",
                         "365d": "12 months"}
SONGS_PERIODS = {
    "added": ("7d", "30d", "90d", "365d"),
    "played": ("7d", "30d", "90d", "365d"),
    "most": ("7d", "30d", "365d", "all"),
}
SONGS_DEFAULT_PERIOD = {"added": "30d", "played": "30d", "most": "all"}
_SONGS_BASE_SORT = ("title", "artist", "album", "year", "duration", "added")
SONGS_SORT_FIELDS = {
    "all": _SONGS_BASE_SORT, "added": _SONGS_BASE_SORT,
    "played": ("last_played",) + _SONGS_BASE_SORT,
    "most": ("plays",) + _SONGS_BASE_SORT,
    "never": _SONGS_BASE_SORT,
    "favorites": ("favorited",) + _SONGS_BASE_SORT,
}
SONGS_DEFAULT_SORT = {
    "all": ("title", "asc"), "added": ("added", "desc"),
    "played": ("last_played", "desc"), "most": ("plays", "desc"),
    "never": ("title", "asc"), "favorites": ("favorited", "desc"),
}


class LibraryNotOpenError(RuntimeError):
    pass


def _tracks(n):
    return "1 track" if n == 1 else "{} tracks".format(n)


def _albums(n):
    return "1 album" if n == 1 else "{} albums".format(n)


def _plays(n):
    return "1 play" if n == 1 else "{} plays".format(n)


def _songs(n):
    return "1 song" if n == 1 else "{} songs".format(n)


def _artist_sublabel(field, albums, songs, duration):
    if field == "name":
        return ""
    if field == "songs":
        return _songs(songs)
    if field == "albums":
        return _albums(albums)
    return format_duration(duration)


def _album_sublabel(field, songs, duration, year, artist):
    if field == "name":
        return ""
    if field == "songs":
        return _songs(songs)
    if field == "duration":
        return format_duration(duration)
    if field == "year":
        return year or "Unknown year"
    return artist


def _playlist_sublabel(field, songs, duration):
    if field == "name":
        return ""
    if field == "songs":
        return _songs(songs)
    return format_duration(duration)


class LibraryService:

    def __init__(self):
        locations.ensure_dirs()
        conn, recovered = db.open_app_db(locations.app_db_path())
        if recovered is not None:
            log.warning("app.db was unreadable; moved aside to %s", recovered)
        self.recovered_app_db = recovered
        self._app_conn = conn
        self.app_repo = AppRepo(conn)
        self.broken_ids = set()
        self.current = None
        self.repo = None
        self.resolver = None
        self._lib_conn = None
        self.all_libraries = None

    def close(self):
        self.close_all()
        self.close_current()
        self.current = None
        if self._app_conn is not None:
            self._app_conn.close()
            self._app_conn = None


    def libraries(self):
        return self.app_repo.libraries()

    def library_path(self, library):
        return locations.library_path(library.id)

    def create_library(self, name, color, root_paths, icon="", exclusions=(),
                       setup_pending=False):
        library_id = str(uuid.uuid4())
        path = locations.library_path(library_id)
        conn = db.open_library_db(path)
        try:
            repo = LibraryRepo(conn)
            repo.set_meta("name", name)
            repo.set_meta("color", color)
            repo.set_meta("icon", icon)
            repo.set_meta("created_at", int(time.time()))
            roots = [repo.add_root(root_path) for root_path in root_paths]
            for excluded in exclusions:
                owner = next((r for r in roots
                              if paths.to_rel(r.path, excluded) is not None), None)
                if owner is None:
                    raise ValueError("{} is not inside any of the library's "
                                     "folders".format(excluded))
                repo.add_exclusion(owner.id, paths.to_rel(owner.path, excluded))
            if setup_pending:
                repo.set_meta(SETUP_PENDING_META, "1")
            conn.close()
            conn = None
            library = self.app_repo.add_library(library_id, name, color, icon)
        except Exception:
            log.exception("creating library %r failed; cleaning up %s",
                          name, library_id)
            if conn is not None:
                conn.close()
            self._app_conn.rollback()
            self.app_repo.remove_library(library_id)
            self._remove_library_file(path)
            raise
        log.info("created library %r as %s", name, library_id)
        return library

    def rename_library(self, library_id, name, color, icon=""):
        if self.app_repo.library(library_id) is None:
            log.warning("cannot rename unknown library id %s", library_id)
            return
        self.app_repo.update_library(library_id, name, color, icon)
        if self.current is not None and self.current.id == library_id:
            if self.repo is None:
                log.warning(
                    "library %r (id %s) was renamed while its file was closed; "
                    "its meta will be reconciled on next open", name, library_id)
            else:
                self.repo.set_meta("name", name)
                self.repo.set_meta("color", color)
                self.repo.set_meta("icon", icon)
            self.current = self.app_repo.library(library_id)

    def _remove_library_file(self, path):
        try:
            os.remove(path)
        except OSError:
            log.exception("could not delete %s", path)

    def delete_library(self, library_id):
        library = self.app_repo.library(library_id)
        if library is None:
            return
        if self.current is not None and self.current.id == library_id:
            self.close_library()
        self.app_repo.remove_library(library_id)
        dropped = self.app_repo.delete_owned_queues(library_id)
        if dropped:
            log.info("deleted %d queue(s) owned by library %s",
                     len(dropped), library_id)
        self.broken_ids.discard(library_id)
        self._remove_library_file(self.library_path(library))

    def close_library(self):
        self.close_all()
        self.close_current()
        self.current = None


    def open_library(self, library_id):
        library = self.app_repo.library(library_id)
        if library is None:
            raise KeyError(library_id)
        self.close_all()
        self.close_current()
        self.current = None
        path = self.library_path(library)
        if not os.path.exists(path):
            log.error("library file %s is missing", path)
            self.broken_ids.add(library_id)
            raise db.LibraryCorruptError("{} is missing".format(path))
        try:
            conn = db.open_library_db(path)
        except (db.LibraryCorruptError, db.SchemaTooNewError):
            log.exception("could not open library %s", library.id)
            self.broken_ids.add(library_id)
            raise
        self.broken_ids.discard(library_id)
        self._lib_conn = conn
        self.repo = LibraryRepo(conn)
        self._reconcile_meta(library)
        self._refresh_resolver()
        self.current = library
        return library

    def _reconcile_meta(self, library):
        if self.repo is None:
            return
        stored_name = self.repo.get_meta("name")
        stored_color = self.repo.get_meta("color")
        stored_icon = self.repo.get_meta("icon")
        if (stored_name == library.name and stored_color == library.color
                and stored_icon == library.icon):
            return
        log.info("reconciling meta of %s: %r/%s/%r -> %r/%s/%r", library.id,
                 stored_name, stored_color, stored_icon,
                 library.name, library.color, library.icon)
        self.repo.set_meta("name", library.name)
        self.repo.set_meta("color", library.color)
        self.repo.set_meta("icon", library.icon)

    def _refresh_resolver(self):
        if self.repo is None:
            self.resolver = None
        else:
            self.resolver = Resolver(self.repo.roots())


    @property
    def all_mode(self):
        return self.all_libraries is not None

    def open_all(self):
        self.close_all()
        self.close_current()
        self.current = None
        self.all_libraries = AllLibraries()
        self.all_libraries.open(
            [lib for lib in self.libraries() if lib.id not in self.broken_ids],
            self.library_path)
        log.info("opened All libraries over %d libraries",
                 len(self.all_libraries.library_ids()))

    def close_all(self):
        if self.all_libraries is not None:
            self.all_libraries.close()
            self.all_libraries = None

    def all_favorite_tracks(self):
        reachable, result = {}, []
        for merged in self.all_libraries.favorites():
            track = self.all_libraries.best_track(merged.key, reachable)
            if track is not None:
                result.append((merged.key, track))
        return result

    def close_current(self):
        if self._lib_conn is not None:
            self._lib_conn.close()
            self._lib_conn = None
        self.repo = None
        self._refresh_resolver()

    def is_open(self):
        return self.repo is not None

    def reopen_current(self):
        if self.current is not None:
            self.open_library(self.current.id)


    def _check_rail_item(self, rail_item):
        if rail_item not in BROWSABLE_RAIL_ITEMS:
            raise ValueError("{} is not a library rail item".format(rail_item))

    def entries(self, rail_item, include_featured=False, sort=None):
        self._check_rail_item(rail_item)
        if self.all_mode:
            if rail_item != RAIL_SONGS:
                return []
            memo = {}
            return [BrowseEntry(key=kind, label=SONGS_LIST_LABELS[kind],
                                sublabel="{:,}".format(self.all_libraries.songs_count(
                                    kind, self._songs_since(kind), memo)))
                    for kind in SONG_LIST_KINDS]
        if not self.is_open():
            return []
        if rail_item == RAIL_ARTISTS:
            field, direction = sort or DEFAULT_SORT
            thumbnails = self.repo.artist_thumbnails()
            result = [BrowseEntry(
                          key=name, label=name,
                          sublabel=_artist_sublabel(field, albums, songs, duration),
                          art_ids=self._one_or_none(thumbnails.get(name.lower())))
                      for name, albums, songs, duration
                      in self.repo.artists_sorted(field, direction)]
            if include_featured:
                result += [BrowseEntry(key=name, label=name, sublabel=_tracks(n),
                                       art_ids=self._one_or_none(thumbnails.get(name.lower())))
                          for name, n in self.repo.featured_artists()]
            return result
        if rail_item == RAIL_ALBUMS:
            field, direction = sort or DEFAULT_SORT
            return [BrowseEntry(
                        key=album_id, label=album or UNKNOWN_ALBUM_LABEL,
                        sublabel=_album_sublabel(field, songs, duration, year, artist),
                        art_ids=(album_id,))
                    for album_id, album, artist, songs, duration, year
                    in self.repo.albums_sorted(field, direction)]
        if rail_item == RAIL_FOLDERS:
            return [BrowseEntry(key=path, label=name or TOP_FOLDER_LABEL,
                                sublabel="", depth=depth, has_children=has_children)
                    for path, name, depth, has_children in self.repo.folder_tree()]
        if rail_item == RAIL_SONGS:
            return [BrowseEntry(key=kind, label=SONGS_LIST_LABELS[kind],
                                sublabel="{:,}".format(self.repo.songs_count(
                                    kind, self._songs_since(kind))))
                    for kind in SONG_LIST_KINDS]
        field, direction = sort or DEFAULT_SORT
        return [BrowseEntry(
                    key=playlist.id, label=playlist.name,
                    sublabel=_playlist_sublabel(field, songs, duration),
                    art_ids=tuple(self.repo.playlist_collage(playlist.id)),
                    locked=playlist.locked)
                for playlist, songs, duration
                in self.repo.playlists_sorted(field, direction)]

    def _one_or_none(self, album_id):
        return (album_id,) if album_id else ()

    def tracks(self, rail_item, key, sort=None, group=None):
        self._check_rail_item(rail_item)
        if self.all_mode:
            if rail_item != RAIL_SONGS:
                return []
            field, direction = sort or self.songs_sort_state(key)
            merged = self.all_libraries.songs(key, self._songs_since(key),
                                              field, direction)
            reachable, result = {}, []
            for m in merged:
                track = self.all_libraries.best_track(m.key, reachable)
                if track is not None:
                    result.append(track)
            return result
        if not self.is_open():
            return []
        if rail_item == RAIL_ARTISTS:
            group = DETAIL_GROUP_DEFAULT[RAIL_ARTISTS] if group is None else group
            field, direction = sort or DETAIL_DEFAULT_SORT[(RAIL_ARTISTS, group)]
            return self.repo.tracks_by_artist(
                key, group=group, field=field, direction=direction)
        if rail_item == RAIL_ALBUMS:
            field, direction = sort or DETAIL_DEFAULT_SORT[(RAIL_ALBUMS, False)]
            return self.repo.tracks_by_album_id(
                key, field=field, direction=direction)
        if rail_item == RAIL_FOLDERS:
            return self.repo.tracks_in_folder(key)
        if rail_item == RAIL_SONGS:
            field, direction = sort or self.songs_sort_state(key)
            return self.repo.songs(key, self._songs_since(key), field, direction)
        group = DETAIL_GROUP_DEFAULT[RAIL_PLAYLISTS] if group is None else group
        field, direction = sort or DETAIL_DEFAULT_SORT[(RAIL_PLAYLISTS, group)]
        return self.repo.playlist_tracks(
            key, group=group, field=field, direction=direction)

    def album_year(self, key):
        if not self.is_open():
            return None
        return self.repo.album_release_date_for_id(key)

    def featured_tracks(self, artist):
        return [] if not self.is_open() else self.repo.tracks_featuring(artist)

    def track_count(self):
        return 0 if not self.is_open() else self.repo.track_count()

    def track_by_id(self, track_id):
        return None if not self.is_open() else self.repo.track_by_id(track_id)

    def play_stats(self, track_id):
        if not self.is_open():
            return (0, None, None)
        return self.repo.play_stats(track_id)

    def reset_plays(self, track_id):
        if not self.is_open():
            return 0
        return self.repo.delete_plays(track_id)

    def home_summary(self, since, until=None, metric=METRIC_PLAYS):
        def label(n, secs):
            return _plays(n) if metric == METRIC_PLAYS else format_listened(secs)

        if self.all_mode:
            return self._all_home_summary(since, until, metric, label)
        if not self.is_open():
            return 0.0, [], [], []

        total = self.repo.total_listened_seconds(since, until)
        thumbnails = self.repo.artist_thumbnails()
        track_entries = [
            BrowseEntry(key=row.id, label=row.title, sublabel=row.artist,
                       count_label=label(n, secs),
                       art_ids=self._one_or_none(row.album_id))
            for row, n, secs in self.repo.top_tracks(since, 10, until, metric)]
        album_entries = [
            BrowseEntry(key=album_id, label=album or UNKNOWN_ALBUM_LABEL,
                       sublabel=artist, count_label=label(n, secs),
                       art_ids=(album_id,))
            for album_id, album, artist, n, secs
            in self.repo.top_albums(since, 10, until, metric)]
        artist_entries = [
            BrowseEntry(key=name, label=name, sublabel="", count_label=label(n, secs),
                       art_ids=self._one_or_none(thumbnails.get(name.lower())))
            for name, n, secs in self.repo.top_artists(since, 10, until, metric)]
        return total, track_entries, album_entries, artist_entries

    def _all_home_summary(self, since, until, metric, label):
        total, tracks, albums, artists = self.all_libraries.home_summary(
            since, until, metric)
        track_entries = []
        for merged, n, secs in tracks:
            best = self.all_libraries.ordered(merged.copies)[0]
            track_entries.append(BrowseEntry(
                key=merged.key, label=best.row.title, sublabel=best.row.artist,
                count_label=label(n, secs),
                art_ids=self._one_or_none(best.row.album_id)))
        album_entries = [
            BrowseEntry(key=key, label=best.album or UNKNOWN_ALBUM_LABEL,
                        sublabel=best.album_artist, count_label=label(n, secs),
                        art_ids=(best.album_id,))
            for key, best, n, secs in albums]
        artist_entries = [
            BrowseEntry(key=key, label=name, sublabel="", count_label=label(n, secs),
                        art_ids=self._one_or_none(thumb))
            for key, name, n, secs, thumb in artists]
        return total, track_entries, album_entries, artist_entries

    def recent_additions(self):
        if self.all_mode:
            pairs = self.all_libraries.recent_additions(LAST_ADDED_LIMIT)
        elif self.is_open():
            pairs = [(a.row.id if a.row is not None else a.album_id, a)
                     for a in self.repo.recent_additions(LAST_ADDED_LIMIT)]
        else:
            return []
        return [self._addition_entry(key, a) for key, a in pairs]

    def _addition_entry(self, key, addition):
        if addition.kind == "album":
            return BrowseEntry(key=("album", key),
                               label=addition.album or UNKNOWN_ALBUM_LABEL,
                               sublabel=addition.album_artist,
                               art_ids=(addition.album_id,))
        return BrowseEntry(key=("track", key), label=addition.row.title,
                           sublabel=addition.row.artist,
                           art_ids=self._one_or_none(addition.album_id))


    def set_favorite(self, track_id, on):
        if not self.is_open():
            log.warning("no library is open: cannot change a favorite")
            return
        self.repo.set_favorite(track_id, on)

    def is_favorite_for(self, library_id, track_id):
        if self.current is not None and self.current.id == library_id and self.is_open():
            return self.repo.is_favorite(track_id)
        repo = self.all_libraries.repo(library_id) if self.all_mode else None
        if repo is None:
            return False
        try:
            return repo.is_favorite(track_id)
        except sqlite3.Error:
            log.exception("cannot read a favorite in library %s", library_id)
            return False

    def set_favorite_for(self, library_id, track_id, on):
        if self.current is not None and self.current.id == library_id and self.is_open():
            self.repo.set_favorite(track_id, on)
            return
        try:
            conn = db.open_library_db(locations.library_path(library_id))
        except (db.LibraryCorruptError, db.SchemaTooNewError):
            log.exception("cannot change a favorite in library %s", library_id)
            return
        try:
            LibraryRepo(conn).set_favorite(track_id, on)
        except sqlite3.Error:
            log.exception("cannot change a favorite in library %s", library_id)
        finally:
            conn.close()

    def is_favorite(self, track_id):
        return self.is_open() and self.repo.is_favorite(track_id)

    def favorite_tracks(self):
        return [] if not self.is_open() else self.repo.favorite_tracks()

    def favorite_entries(self):
        if self.all_mode:
            entries = []
            for merged in self.all_libraries.favorites():
                best = self.all_libraries.ordered(merged.copies)[0]
                entries.append(BrowseEntry(
                    key=merged.key, label=best.row.title, sublabel=best.row.artist,
                    art_ids=self._one_or_none(best.row.album_id)))
            return entries
        return [BrowseEntry(key=row.id, label=row.title, sublabel=row.artist,
                            art_ids=self._one_or_none(row.album_id))
                for row in self.favorite_tracks()]

    def earliest_play_at(self):
        if self.all_mode:
            return self.all_libraries.earliest_play_at()
        return None if not self.is_open() else self.repo.earliest_play_at()

    def library_stats(self):
        if not self.is_open():
            return LibraryStats(0, 0, 0, 0.0)
        return LibraryStats(
            artist_count=len(self.repo.artists()),
            album_count=len(self.repo.albums()),
            track_count=self.repo.track_count(),
            total_duration=self.repo.total_duration())



    def setup_pending(self):
        return self.is_open() and self.repo.get_meta(SETUP_PENDING_META) == "1"

    def finish_setup(self):
        if self.is_open():
            self.repo.set_meta(SETUP_PENDING_META, "0")

    def has_scanned(self):
        return self.is_open() and self.repo.get_meta("last_scan_at") is not None


    def export_library_data(self, dest_path):
        if not self.is_open():
            raise LibraryNotOpenError("no library is open: cannot export")
        return porting.export_library_data(self.repo, dest_path, self.current.name)

    def import_library_data(self, path):
        if not self.is_open():
            raise LibraryNotOpenError("no library is open: cannot import")
        data = porting.read_library_data(path)
        match = porting.match_tracks(data.tracks, self.repo.data_tracks())
        ids = match.matched
        plays = [(ids[ref], at) for ref, at in data.history if ref in ids]
        favorites = [(ids[ref], at) for ref, at in data.favorites if ref in ids]
        to_write, kept = [], []
        for playlist in data.playlists:
            track_ids = [ids[ref] for ref in playlist.refs if ref in ids]
            kept.append((playlist, len(track_ids)))
            if track_ids:
                to_write.append((playlist.name, playlist.created_at,
                                 playlist.locked, track_ids))
        added, names, favorites_added = self.repo.import_library_data(
            plays, to_write, favorites)
        names = iter(names)
        lines = []
        for playlist, matched in kept:
            if matched:
                lines.append(ImportedPlaylist(next(names), "created", matched,
                                              len(playlist.refs)))
            else:
                lines.append(ImportedPlaylist(playlist.name, "skipped_empty", 0,
                                              len(playlist.refs)))
        unmatched = tuple(UnmatchedTrack(t.artist, t.title, reason)
                          for t, reason in match.unmatched)
        log.info("imported library data from %s: %d/%d plays, %d playlists, "
                 "%d favorites, %d tracks unmatched", path, added,
                 len(data.history), len(to_write), favorites_added, len(unmatched))
        return LibraryImportResult(plays_imported=added,
                                   plays_total=len(data.history),
                                   playlists=tuple(lines), unmatched=unmatched,
                                   favorites_imported=favorites_added)



    def roots(self):
        return [] if not self.is_open() else self.repo.roots()

    def root_track_counts(self):
        return {} if not self.is_open() else self.repo.root_track_counts()

    def exclusions(self):
        return [] if not self.is_open() else self.repo.exclusions()

    def root_for_path(self, abs_path):
        if not self.is_open():
            return None, None
        norm_path = os.path.normcase(os.path.abspath(abs_path))
        for root in self.repo.roots():
            rel = paths.to_rel(root.path, abs_path)
            if rel is not None:
                return root, rel
            if os.path.normcase(os.path.abspath(root.path)) == norm_path:
                return root, ""
        return None, None

    def _require_root(self, root_id, what):
        if self.repo.root(root_id) is None:
            log.warning("cannot %s: this library has no root with id %s",
                        what, root_id)
            raise KeyError(root_id)

    def _edit_roots(self, what, mutate, root_id=None):
        if not self.is_open():
            log.warning("cannot %s: no library is open", what)
            raise LibraryNotOpenError(
                "no library is open: cannot {}".format(what))
        if root_id is not None:
            self._require_root(root_id, what)
        try:
            return mutate(self.repo)
        finally:
            try:
                self._refresh_resolver()
            except Exception:
                log.exception("could not rebuild the resolver after %s; "
                              "nothing will resolve until the library is "
                              "reopened", what)
                self.resolver = None

    def add_root(self, path):
        root = self._edit_roots("add the root {}".format(path),
                                lambda repo: repo.add_root(path))
        log.info("added root %s", path)
        return root

    def add_exclusion(self, root_id, rel_path):
        if not self.is_open():
            log.warning("cannot exclude %s: no library is open", rel_path)
            raise LibraryNotOpenError("no library is open: cannot add an exclusion")
        exclusion = self.repo.add_exclusion(root_id, rel_path)
        log.info("excluded %s under root %s", rel_path, root_id)
        return exclusion

    def remove_exclusion(self, exclusion_id):
        if not self.is_open():
            log.warning("cannot remove exclusion %s: no library is open", exclusion_id)
            raise LibraryNotOpenError("no library is open: cannot remove an exclusion")
        self.repo.remove_exclusion(exclusion_id)
        log.info("removed exclusion %s", exclusion_id)

    def rebase_root(self, root_id, new_path):
        old = self.repo.root(root_id) if self.is_open() else None
        self._edit_roots("rebase root {}".format(root_id),
                         lambda repo: repo.set_root_path(root_id, new_path),
                         root_id=root_id)
        if old is not None:
            self.app_repo.rewrite_queue_paths(old.path, new_path)
        found, missing = availability_pass(self.repo, self.resolver)
        log.info("rebased root %s -> %s (%s found, %s missing)",
                 root_id, new_path, found, missing)
        return found, missing

    def remove_root_impact(self, root_id):
        what = "report the impact of removing root {}".format(root_id)
        if not self.is_open():
            log.warning("cannot report the impact of removing root %s: "
                        "no library is open", root_id)
            raise LibraryNotOpenError("no library is open: cannot " + what)
        self._require_root(root_id, what)
        return self.repo.remove_root_impact(root_id)

    def remove_root(self, root_id):
        orphaned = self._edit_roots("remove root {}".format(root_id),
                                    lambda repo: repo.remove_root(root_id),
                                    root_id=root_id)
        for album_id in orphaned:
            self._remove_art_file(album_id)
        log.info("removed root %s", root_id)

    def _remove_art_file(self, album_id):
        try:
            os.remove(locations.art_path(album_id))
        except FileNotFoundError:
            pass
        except OSError:
            log.exception("could not delete artwork for album %s", album_id)


    def get_state(self, key, default=None):
        return self.app_repo.get_state(key, default)

    def set_state(self, key, value):
        self.app_repo.set_state(key, value)

    def sort_state(self, rail_item):
        fields = SORT_FIELDS.get(rail_item)
        if fields is None:
            return DEFAULT_SORT
        raw = self.get_state("sort_" + rail_item)
        if raw is None or ":" not in raw:
            return DEFAULT_SORT
        field, _, direction = raw.partition(":")
        if field not in fields or direction not in ("asc", "desc"):
            return DEFAULT_SORT
        return (field, direction)

    def set_sort_state(self, rail_item, field, direction):
        self.set_state("sort_" + rail_item, "{}:{}".format(field, direction))

    def filter_featured_artists(self):
        return self.get_state("filter_featured_artists") == "1"

    def set_filter_featured_artists(self, value):
        self.set_state("filter_featured_artists", "1" if value else "0")

    def detail_group_state(self, rail_item):
        if rail_item not in DETAIL_GROUP_RAIL_ITEMS:
            return False
        raw = self.get_state("detail_group_" + rail_item)
        if raw is None:
            return DETAIL_GROUP_DEFAULT[rail_item]
        return raw == "1"

    def set_detail_group_state(self, rail_item, grouped):
        self.set_state("detail_group_" + rail_item, "1" if grouped else "0")

    def _detail_sort_key(self, rail_item, grouped):
        if rail_item == RAIL_ALBUMS:
            return "detail_sort_albums"
        return "detail_sort_{}_{}".format(
            rail_item, "grouped" if grouped else "flat")

    def detail_sort_state(self, rail_item, grouped):
        key = (rail_item, grouped)
        if key not in DETAIL_SORT_FIELDS:
            raise ValueError(
                "no detail sort fields for rail_item={!r} grouped={!r}"
                .format(rail_item, grouped))
        fields = DETAIL_SORT_FIELDS[key]
        default = DETAIL_DEFAULT_SORT[key]
        raw = self.get_state(self._detail_sort_key(rail_item, grouped))
        if raw is None or ":" not in raw:
            return default
        field, _, direction = raw.partition(":")
        if field not in fields or direction not in ("asc", "desc"):
            return default
        return (field, direction)

    def set_detail_sort_state(self, rail_item, grouped, field, direction):
        self.set_state(self._detail_sort_key(rail_item, grouped),
                       "{}:{}".format(field, direction))

    def detail_filter_featured_tracks(self):
        raw = self.get_state("detail_filter_featured_tracks")
        return True if raw is None else raw == "1"

    def set_detail_filter_featured_tracks(self, value):
        self.set_state("detail_filter_featured_tracks", "1" if value else "0")


    def songs_period(self, key):
        choices = SONGS_PERIODS.get(key)
        if choices is None:
            return None
        raw = self.get_state("songs_period_" + key)
        return raw if raw in choices else SONGS_DEFAULT_PERIOD[key]

    def set_songs_period(self, key, period):
        if period not in SONGS_PERIODS.get(key, ()):
            raise ValueError("{!r} is not a period of song list {!r}"
                             .format(period, key))
        self.set_state("songs_period_" + key, period)

    def _songs_since(self, key):
        period = self.songs_period(key)
        seconds = SONGS_PERIOD_SECONDS.get(period) if period else None
        return None if seconds is None else int(time.time() - seconds)

    def songs_sort_state(self, key):
        raw = self.get_state("detail_sort_songs_" + key)
        if raw and ":" in raw:
            field, _, direction = raw.partition(":")
            if field in SONGS_SORT_FIELDS[key] and direction in ("asc", "desc"):
                return (field, direction)
        return SONGS_DEFAULT_SORT[key]

    def set_songs_sort_state(self, key, field, direction):
        self.set_state("detail_sort_songs_" + key,
                       "{}:{}".format(field, direction))

    def songs_empty_text(self, key):
        period = self.songs_period(key)
        phrase = _SONGS_PERIOD_PHRASES.get(period)
        if key == "added":
            return "Nothing added in the last {}".format(phrase)
        if key in ("played", "most"):
            if phrase is None:
                return "Nothing played yet"
            return "Nothing played in the last {}".format(phrase)
        return {"never": "You've played everything",
                "favorites": "No favorites yet",
                "all": ("No songs yet" if self.all_mode
                        else "No songs in this library yet")}[key]

    def create_queue(self, source_kind, source_label, source_library, tracks,
                     current_pos, dirty=False, owner_library_id=None):
        return self.app_repo.create_queue(source_kind, source_label,
                                          source_library, tracks, current_pos,
                                          dirty=dirty,
                                          owner_library_id=owner_library_id)

    def load_queue(self, queue_id):
        return self.app_repo.load_queue(queue_id)

    def queue_ref(self, queue_id):
        return self.app_repo.queue_ref(queue_id)

    def apply_relinks(self, library_id, relinks):
        if not relinks:
            return []
        if self.current is None or self.current.id != library_id or not self.is_open():
            log.warning("cannot update queues for %d relinked track(s): "
                        "library %s is not open", len(relinks), library_id)
            return []
        roots = {root.id: root.path for root in self.repo.roots()}
        moves = []
        for relink in relinks:
            root_path = roots.get(relink.root_id)
            if root_path is None:
                log.warning("relinked track %s has no known root %s",
                            relink.kept_id, relink.root_id)
                continue
            moves.append((relink.kept_id, relink.dropped_id,
                          paths.to_abs(root_path, relink.rel_path)))
        try:
            self.app_repo.relink_queue_items(library_id, moves)
        except sqlite3.Error:
            log.exception("cannot update queues for relinked tracks in %s",
                          library_id)
        return moves

    def list_queues(self, owner_library_id=ANY_OWNER):
        return self.app_repo.list_queues(owner_library_id)

    def queue_art_ids(self, queue_id, limit=4):
        return self.app_repo.queue_art_ids(queue_id, limit)

    def find_pristine_queue(self, source_kind, source_label, owner_library_id):
        return self.app_repo.find_pristine_queue(source_kind, source_label,
                                                  owner_library_id)

    def touch_queue(self, queue_id):
        self.app_repo.touch_queue(queue_id)

    def rename_queue(self, queue_id, label):
        self.app_repo.rename_queue(queue_id, label)

    def replace_queue_items(self, queue_id, tracks):
        self.app_repo.replace_queue_items(queue_id, tracks)

    def reorder_queue_items(self, queue_id, tracks):
        self.app_repo.reorder_queue_items(queue_id, tracks)

    def add_queue_items(self, queue_id, tracks):
        self.app_repo.add_queue_items(queue_id, tracks)

    def set_queue_position(self, queue_id, current_pos, position_seconds=0):
        self.app_repo.set_queue_position(queue_id, current_pos, position_seconds)

    def delete_queue(self, queue_id):
        self.app_repo.delete_queue(queue_id)

    def evict_excess_queues(self, keep, protect_id, owner_library_id=ANY_OWNER):
        self.app_repo.evict_excess_queues(keep, protect_id, owner_library_id)

    def queue_membership(self, queue_ids, tracks):
        return self.app_repo.queue_membership(queue_ids, tracks)

    def add_missing_queue_tracks(self, queue_id, tracks):
        return self.app_repo.add_missing_queue_tracks(queue_id, tracks)

    def remove_queue_tracks(self, queue_id, tracks):
        return self.app_repo.remove_queue_tracks(queue_id, tracks)

    def delete_owned_queues(self, library_id):
        return self.app_repo.delete_owned_queues(library_id)

    def record_play(self, library_id, track_id, played_at):
        if self.current is not None and self.current.id == library_id and self.is_open():
            try:
                self.repo.record_play(track_id, played_at)
            except sqlite3.Error:
                log.exception("cannot record a play in library %s", library_id)
            return
        path = locations.library_path(library_id)
        if not os.path.exists(path):
            log.warning("cannot record a play in library %s: its file is missing",
                       library_id)
            return
        try:
            conn = db.open_library_db(path)
        except (db.LibraryCorruptError, db.SchemaTooNewError):
            log.exception("cannot record a play in library %s: it will not open",
                          library_id)
            return
        try:
            LibraryRepo(conn).record_play(track_id, played_at)
        except sqlite3.Error:
            log.exception("cannot record a play in library %s", library_id)
        finally:
            conn.close()

    def album_artist_for(self, library_id, album_id):
        if self.current is not None and self.current.id == library_id and self.is_open():
            try:
                return self.repo.album_artist_for_id(album_id)
            except sqlite3.Error:
                log.exception("cannot resolve album artist in library %s", library_id)
                return None
        path = locations.library_path(library_id)
        if not os.path.exists(path):
            log.warning("cannot resolve album artist in library %s: its file is missing",
                       library_id)
            return None
        try:
            conn = db.open_library_db(path)
        except (db.LibraryCorruptError, db.SchemaTooNewError):
            log.exception("cannot resolve album artist in library %s: it will not open",
                          library_id)
            return None
        try:
            return LibraryRepo(conn).album_artist_for_id(album_id)
        except sqlite3.Error:
            log.exception("cannot resolve album artist in library %s", library_id)
            return None
        finally:
            conn.close()

    def find_track_by_path(self, abs_path):
        if self.is_open():
            try:
                found = self._find_in_repo(self.repo, abs_path)
            except sqlite3.Error:
                log.exception("cannot check the open library for %s", abs_path)
                found = None
            if found is not None:
                return self.current.id, found
        for library in self.libraries():
            if self.current is not None and library.id == self.current.id:
                continue
            path = self.library_path(library)
            if not os.path.exists(path):
                continue
            try:
                conn = db.open_library_db(path)
            except (db.LibraryCorruptError, db.SchemaTooNewError):
                continue
            try:
                found = self._find_in_repo(LibraryRepo(conn), abs_path)
            except sqlite3.Error:
                log.exception("cannot check library %s for %s", library.id, abs_path)
                found = None
            finally:
                conn.close()
            if found is not None:
                return library.id, found
        return None

    def _find_in_repo(self, repo, abs_path):
        for root in repo.roots():
            rel = paths.to_rel(root.path, abs_path)
            if rel is not None:
                row = repo.track_by_rel_path(rel)
                if row is not None:
                    return row.id
        return None

    def find_track_in_current_library(self, abs_path):
        if not self.is_open():
            return None
        try:
            return self._find_in_repo(self.repo, abs_path)
        except sqlite3.Error:
            log.exception("cannot check the open library for %s", abs_path)
            return None

    def import_playlists(self, file_paths):
        if not self.is_open():
            return []
        return [self._import_one_playlist(path) for path in file_paths]

    def _import_one_playlist(self, file_path):
        entries = playlist_file.parse_m3u(file_path)
        track_ids = [tid for tid in
                     (self.find_track_in_current_library(p) for p in entries)
                     if tid is not None]
        name = os.path.splitext(os.path.basename(file_path))[0]
        total = len(entries)
        matched = len(track_ids)
        if matched == 0:
            return PlaylistImportResult(file_path, name, "skipped_empty",
                                        matched, total)
        existing = self.repo.playlist_by_name(name)
        if existing is not None and existing.locked:
            return PlaylistImportResult(file_path, name, "skipped_locked",
                                        matched, total)
        if existing is not None:
            self.repo.replace_playlist_tracks(existing.id, track_ids)
            return PlaylistImportResult(file_path, name, "replaced",
                                        matched, total)
        playlist = self.repo.create_playlist(name)
        self.repo.add_to_playlist(playlist.id, track_ids)
        return PlaylistImportResult(file_path, name, "created",
                                    matched, total)
