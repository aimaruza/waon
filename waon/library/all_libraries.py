
import logging
import os
import sqlite3
from dataclasses import dataclass, replace

from waon.library import db, paths
from waon.library.entities import METRIC_PLAYS, METRIC_TIME, RecentAddition
from waon.library.identity import (
    Copy, SongCopy, album_key, artist_key, fold, merge_tracks,
)
from waon.library.library_repo import MOST_PLAYED_LIMIT, SONG_LIST_KINDS, LibraryRepo
from waon.models import Track

log = logging.getLogger(__name__)

INNER_LIMIT = 200
RECAP_LIMIT = 10

_SONG_SORT_OWNER = {"last_played": "played", "plays": "most",
                    "favorited": "favorites"}
_SONG_SORT_FIELDS = ("title", "artist", "album", "year", "duration", "added",
                     "last_played", "plays", "favorited")


@dataclass(frozen=True)
class AlbumCopy:
    library_id: str
    album_id: str
    album: str
    album_artist: str
    plays: int = 0
    seconds: float = 0.0
    created_at: int = 0


@dataclass(frozen=True)
class _SongTotals:
    merged: object
    best: object
    plays: int
    seconds: float
    plays_ever: int
    last_played: object
    added: int
    favorited: object


def _rank_key(metric, plays, seconds, name, key):
    if metric == METRIC_PLAYS:
        return (-plays, -seconds, fold(name), key)
    if metric == METRIC_TIME:
        return (-seconds, -plays, fold(name), key)
    raise ValueError("unknown recap metric {!r}".format(metric))


def _max_or_none(values):
    values = [v for v in values if v is not None]
    return max(values) if values else None


class AllLibraries:
    def __init__(self):
        self._open = []
        self._order = {}
        self._roots = {}
        self._track_copies = {}
        self._key_of = {}
        self._album_copies = {}
        self._artist_copies = {}

    def open(self, libraries, path_for):
        for library in libraries:
            try:
                conn = db.open_library_db_readonly(path_for(library))
            except (db.LibraryCorruptError, db.SchemaTooNewError):
                log.warning("All libraries: skipping %s, it will not open",
                            library.id, exc_info=True)
                continue
            repo = LibraryRepo(conn)
            self._order[library.id] = len(self._open)
            self._open.append((library, repo, conn))
            self._roots[library.id] = {root.id: root.path for root in repo.roots()}

    def close(self):
        for _library, _repo, conn in self._open:
            conn.close()
        self._open = []

    def library_ids(self):
        return [library.id for library, _repo, _conn in self._open]

    def libraries(self):
        return [(library, repo) for library, repo, _conn in self._open]

    def repo(self, library_id):
        for library, repo, _conn in self._open:
            if library.id == library_id:
                return repo
        return None

    def _rank(self, library_id):
        return self._order.get(library_id, 1 << 30)

    def ordered(self, copies):
        return sorted(copies, key=lambda c: (-c.plays, self._rank(c.library_id)))

    def remember_tracks(self, merged):
        for item in merged:
            self._track_copies[item.key] = item.copies
            for copy in item.copies:
                self._key_of[(copy.library_id, copy.row.id)] = item.key

    def key_for(self, library_id, track_id):
        return self._key_of.get((library_id, track_id))

    def copies(self, key):
        return self._track_copies.get(key, ())

    def playable(self, copy, reachable):
        row = copy.row
        if not row.available:
            return None
        root_path = self._roots.get(copy.library_id, {}).get(row.root_hint_id)
        if root_path is None:
            return None
        if root_path not in reachable:
            reachable[root_path] = os.path.isdir(root_path)
        if not reachable[root_path]:
            return None
        return Track(path=paths.to_abs(root_path, row.rel_path), title=row.title,
                     artist=row.artist, album=row.album, duration=row.duration,
                     album_id=row.album_id, track_id=row.id,
                     library_id=copy.library_id)

    def best_track(self, key, reachable=None):
        reachable = {} if reachable is None else reachable
        for copy in self.ordered(self.copies(key)):
            track = self.playable(copy, reachable)
            if track is not None:
                return track
        return None

    def home_summary(self, since, until, metric):
        total = 0.0
        track_copies, albums, artists, thumbnails = [], {}, {}, {}
        for library, repo in self.libraries():
            try:
                total += repo.total_listened_seconds(since, until)
                dates = repo.album_release_dates()
                for row, n, secs in repo.top_tracks(since, INNER_LIMIT, until, metric):
                    track_copies.append(Copy(library.id, row, dates.get(row.album_id),
                                             plays=n, seconds=secs))
                for album_id, album, aa, n, secs in repo.top_albums(
                        since, INNER_LIMIT, until, metric):
                    albums.setdefault(album_key(aa, album), []).append(
                        AlbumCopy(library.id, album_id, album, aa, n, secs))
                for name, n, secs in repo.top_artists(since, INNER_LIMIT, until, metric):
                    artists.setdefault(artist_key(name), []).append(
                        (library.id, name, n, secs))
                for lower, album_id in repo.artist_thumbnails().items():
                    thumbnails.setdefault(lower, album_id)
            except sqlite3.Error:
                log.exception("All libraries: the recap skips library %s", library.id)
        merged = merge_tracks(track_copies)
        self.remember_tracks(merged)
        tracks = sorted(
            ((m, sum(c.plays for c in m.copies), sum(c.seconds for c in m.copies))
             for m in merged),
            key=lambda t: _rank_key(metric, t[1], t[2],
                                    self.ordered(t[0].copies)[0].row.title, t[0].key))
        album_rows = []
        for key, copies in albums.items():
            self._album_copies[key] = tuple(copies)
            album_rows.append((key, self._best_album(copies),
                               sum(c.plays for c in copies),
                               sum(c.seconds for c in copies)))
        album_rows.sort(key=lambda a: _rank_key(metric, a[2], a[3], a[1].album, a[0]))
        artist_rows = []
        for key, copies in artists.items():
            self._artist_copies[key] = tuple(copies)
            best = self._best_artist(copies)
            artist_rows.append((key, best[1], sum(c[2] for c in copies),
                                sum(c[3] for c in copies), thumbnails.get(key)))
        artist_rows.sort(key=lambda a: _rank_key(metric, a[2], a[3], a[1], a[0]))
        return (total, tracks[:RECAP_LIMIT], album_rows[:RECAP_LIMIT],
                artist_rows[:RECAP_LIMIT])

    def _best_album(self, copies):
        return min(copies, key=lambda c: (-c.plays, self._rank(c.library_id)))

    def _best_artist(self, copies):
        return min(copies, key=lambda c: (-c[2], self._rank(c[0])))

    def album_target(self, key):
        copies = self._album_copies.get(key)
        if not copies:
            return None
        best = self._best_album(copies)
        return best.library_id, best.album_id

    def artist_target(self, key):
        copies = self._artist_copies.get(key)
        if not copies:
            return None
        best = self._best_artist(copies)
        return best[0], best[1]

    def earliest_play_at(self):
        found = []
        for library, repo in self.libraries():
            try:
                at = repo.earliest_play_at()
            except sqlite3.Error:
                log.exception("All libraries: skipping library %s", library.id)
                continue
            if at is not None:
                found.append(at)
        return min(found) if found else None

    def recent_additions(self, limit=20):
        albums, songs, added = {}, [], {}
        for library, repo in self.libraries():
            try:
                album_plays = repo.album_play_counts()
                plays = repo.play_counts()
                dates = repo.album_release_dates()
                for a in repo.recent_additions():
                    if a.kind == "album":
                        copy = AlbumCopy(library.id, a.album_id, a.album, a.album_artist,
                                         album_plays.get(a.album_id, 0), 0.0, a.added_at)
                        albums.setdefault(album_key(a.album_artist, a.album), []).append(
                            (copy, a))
                    else:
                        songs.append(Copy(library.id, a.row, dates.get(a.album_id),
                                          plays=plays.get(a.row.id, 0)))
                        added[(library.id, a.row.id)] = a.added_at
            except sqlite3.Error:
                log.exception("All libraries: Last Added skips library %s", library.id)
        rows = []
        for key, pairs in albums.items():
            copies = [copy for copy, _a in pairs]
            self._album_copies[key] = tuple(copies)
            best = self._best_album(copies)
            shown = next(a for copy, a in pairs if copy is best)
            newest = max(copy.created_at for copy in copies)
            rows.append((newest, fold(best.album), key, replace(shown, added_at=newest)))
        merged = merge_tracks(songs)
        self.remember_tracks(merged)
        for m in merged:
            best = self.ordered(m.copies)[0]
            newest = max(added[(c.library_id, c.row.id)] for c in m.copies)
            rows.append((newest, fold(best.row.title), m.key, RecentAddition(
                kind="track", album_id=best.row.album_id, album=best.row.album,
                album_artist=best.row.album_artist, added_at=newest, row=best.row)))
        rows.sort(key=lambda r: (-r[0], r[1], r[2]))
        return [(key, addition) for _t, _n, key, addition in rows[:limit]]

    def track_target(self, key):
        copies = self.copies(key)
        if not copies:
            return None
        best = self.ordered(copies)[0]
        return best.library_id, best.row.album_id, best.row.id

    def album_tracks(self, library_id, album_id):
        repo = self.repo(library_id)
        if repo is None:
            log.warning("All libraries: library %s isn't open", library_id)
            return []
        try:
            rows = repo.tracks_by_album_id(album_id)
        except sqlite3.Error:
            log.exception("All libraries: cannot read album %s of library %s",
                          album_id, library_id)
            return []
        reachable = {}
        tracks = (self.playable(Copy(library_id, row), reachable) for row in rows)
        return [t for t in tracks if t is not None]

    def favorites(self):
        copies, favorited = [], {}
        for library, repo in self.libraries():
            try:
                plays = repo.play_counts()
                dates = repo.album_release_dates()
                stamps = dict(repo.favorites())
                for row in repo.favorite_tracks():
                    copies.append(Copy(library.id, row, dates.get(row.album_id),
                                       plays=plays.get(row.id, 0)))
                    favorited[(library.id, row.id)] = stamps.get(row.id) or 0
            except sqlite3.Error:
                log.exception("All libraries: Favorites skips library %s", library.id)
        merged = merge_tracks(copies)
        self.remember_tracks(merged)

        def newest(m):
            return max(favorited[(c.library_id, c.row.id)] for c in m.copies)
        merged.sort(key=lambda m: (-newest(m), fold(self.ordered(m.copies)[0].row.title),
                                   m.key))
        return merged

    def _song_totals(self, since, memo):
        if memo is not None and since in memo:
            return memo[since]
        copies = []
        for library, repo in self.libraries():
            try:
                for f in repo.song_facts(since):
                    copies.append(SongCopy(
                        library.id, f.row, f.release_date, plays=f.plays,
                        seconds=f.seconds, plays_ever=f.plays_ever,
                        last_played=f.last_played, favorited_at=f.favorited_at))
            except sqlite3.Error:
                log.exception("All libraries: Songs skips library %s", library.id)
        totals = []
        for m in merge_tracks(copies):
            totals.append(_SongTotals(
                merged=m, best=self.ordered(m.copies)[0],
                plays=sum(c.plays for c in m.copies),
                seconds=sum(c.seconds for c in m.copies),
                plays_ever=sum(c.plays_ever for c in m.copies),
                last_played=_max_or_none(c.last_played for c in m.copies),
                added=max(c.row.added_at for c in m.copies),
                favorited=_max_or_none(c.favorited_at for c in m.copies)))
        if memo is not None:
            memo[since] = totals
        return totals

    def _song_list(self, kind, since, memo):
        if kind not in SONG_LIST_KINDS:
            raise ValueError("unknown song list {!r}".format(kind))
        totals = self._song_totals(since if kind in ("played", "most") else None, memo)
        if kind == "added":
            return [t for t in totals if since is None or t.added >= since]
        if kind == "played":
            return [t for t in totals if t.last_played is not None]
        if kind == "most":
            played = [t for t in totals if t.plays > 0]
            played.sort(key=lambda t: (-t.plays, -t.seconds,
                                       fold(t.best.row.title), t.merged.key))
            return played[:MOST_PLAYED_LIMIT]
        if kind == "never":
            return [t for t in totals if t.plays_ever == 0]
        if kind == "favorites":
            return [t for t in totals if t.favorited is not None]
        return list(totals)

    def songs(self, kind, since, field, direction, memo=None):
        owner = _SONG_SORT_OWNER.get(field)
        if field not in _SONG_SORT_FIELDS or (owner is not None and owner != kind):
            raise ValueError("no sort field {!r} for song list {!r}".format(field, kind))
        rows = self._song_list(kind, since, memo)
        rows.sort(key=lambda t: (fold(t.best.row.title), t.merged.key))
        reverse = direction == "desc"
        if field == "year":
            dated = [t for t in rows if t.best.release_date]
            undated = [t for t in rows if not t.best.release_date]
            dated.sort(key=lambda t: fold(t.best.release_date), reverse=reverse)
            rows = dated + undated
        else:
            value = {
                "title": lambda t: fold(t.best.row.title),
                "artist": lambda t: fold(t.best.row.artist),
                "album": lambda t: fold(t.best.row.album),
                "duration": lambda t: t.best.row.duration or 0.0,
                "added": lambda t: t.added,
                "last_played": lambda t: t.last_played or 0,
                "plays": lambda t: (t.plays, t.seconds),
                "favorited": lambda t: t.favorited or 0,
            }[field]
            rows.sort(key=value, reverse=reverse)
        merged = [t.merged for t in rows]
        self.remember_tracks(merged)
        return merged

    def songs_count(self, kind, since, memo=None):
        return len(self._song_list(kind, since, memo))
