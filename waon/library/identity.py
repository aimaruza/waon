
from dataclasses import dataclass
from typing import Optional, Tuple

DURATION_TOLERANCE = 2.0


def fold(text):
    return (text or "").lower()


def identity(track):
    return (fold(track.album_artist), fold(track.album), fold(track.title))


NARROWING = (
    lambda e, c: e.release_date == c.release_date,
    lambda e, c: (e.disc_no, e.track_no) == (c.disc_no, c.track_no),
    lambda e, c: abs(e.duration - c.duration) <= DURATION_TOLERANCE,
)


def album_key(album_artist, album):
    return "a:{}\x1f{}".format(fold(album_artist), fold(album))


def artist_key(name):
    return fold(name)


@dataclass(frozen=True)
class Copy:
    library_id: str
    row: object
    release_date: Optional[str] = None
    plays: int = 0
    seconds: float = 0.0

    @property
    def album_artist(self):
        return self.row.album_artist

    @property
    def album(self):
        return self.row.album

    @property
    def title(self):
        return self.row.title

    @property
    def disc_no(self):
        return self.row.disc_no

    @property
    def track_no(self):
        return self.row.track_no

    @property
    def duration(self):
        return self.row.duration or 0.0


@dataclass(frozen=True)
class SongCopy(Copy):
    plays_ever: int = 0
    last_played: Optional[int] = None
    favorited_at: Optional[int] = None


@dataclass(frozen=True)
class MergedTrack:
    key: str
    copies: Tuple[Copy, ...]


def _same_or_missing(a, b):
    return a is None or b is None or a == b


def compatible(a, b):
    return (_same_or_missing(a.release_date or None, b.release_date or None)
            and _same_or_missing(a.disc_no, b.disc_no)
            and _same_or_missing(a.track_no, b.track_no)
            and (not a.duration or not b.duration
                 or abs(a.duration - b.duration) <= DURATION_TOLERANCE))


def merge_tracks(copies):
    groups = []
    by_identity = {}
    for copy in copies:
        ident = identity(copy)
        candidates = [
            g for g in by_identity.get(ident, ())
            if all(c.library_id != copy.library_id for c in groups[g])
            and all(compatible(c, copy) for c in groups[g])]
        if len(candidates) == 1:
            groups[candidates[0]].append(copy)
        else:
            by_identity.setdefault(ident, []).append(len(groups))
            groups.append([copy])
    return [MergedTrack(key="t:{}:{}".format(g[0].library_id, g[0].row.id),
                        copies=tuple(g))
            for g in groups]
