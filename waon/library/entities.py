
from dataclasses import dataclass
from typing import Optional, Tuple

METRIC_PLAYS = "plays"
METRIC_TIME = "time"

ALL_LIBRARIES_ID = "__all__"
ALL_LIBRARIES_NAME = "All libraries"
RECAP_METRICS = (METRIC_PLAYS, METRIC_TIME)

VARIOUS_ARTISTS = "Various Artists"


@dataclass(frozen=True)
class Library:
    id: str
    name: str
    color: str
    position: int
    icon: str = ""


@dataclass(frozen=True)
class Root:
    id: str
    path: str
    position: int


@dataclass(frozen=True)
class ExcludedFolder:
    id: str
    root_id: str
    rel_path: str


@dataclass(frozen=True)
class LibraryStats:
    artist_count: int
    album_count: int
    track_count: int
    total_duration: float


@dataclass(frozen=True)
class TrackRow:
    id: str
    rel_path: str
    root_hint_id: Optional[str]
    title: str
    artist: str
    album: str
    added_at: int
    album_artist: str = ""
    track_no: Optional[int] = None
    disc_no: Optional[int] = None
    duration: float = 0.0
    mtime: int = 0
    size: int = 0
    available: int = 1
    album_id: Optional[str] = None


@dataclass(frozen=True)
class RecentAddition:
    kind: str
    album_id: str
    album: str
    album_artist: str
    added_at: int
    row: Optional[TrackRow] = None


@dataclass(frozen=True)
class SongFacts:
    row: TrackRow
    release_date: Optional[str]
    favorited_at: Optional[int]
    plays_ever: int
    plays: int
    seconds: float
    last_played: Optional[int]


@dataclass(frozen=True)
class Playlist:
    id: str
    name: str
    created_at: int
    locked: bool = False
    updated_at: int = 0


@dataclass(frozen=True)
class PlaylistImportResult:
    file_path: str
    name: str
    status: str
    matched: int
    total: int


@dataclass(frozen=True)
class QueueRef:
    id: str
    source_kind: Optional[str]
    source_label: str
    source_library: str
    current_pos: int
    created_at: int
    last_played_at: Optional[int]
    dirty: bool = False
    position_seconds: float = 0.0
    owner_library_id: Optional[str] = None


@dataclass(frozen=True)
class TagData:
    title: str
    artist: str
    album: str
    album_artist: str = ""
    track_no: Optional[int] = None
    disc_no: Optional[int] = None
    duration: float = 0.0
    date: str = ""


@dataclass(frozen=True)
class FoundFile:
    root_id: str
    rel_path: str
    abs_path: str
    mtime: int
    size: int


@dataclass(frozen=True)
class ScanProgress:
    files_seen: int
    tracks_found: int
    current_dir: str


@dataclass(frozen=True)
class Relink:
    kept_id: str
    dropped_id: str
    root_id: Optional[str]
    rel_path: str


@dataclass(frozen=True)
class ScanResult:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    missing: int = 0
    duplicates: int = 0
    cancelled: bool = False
    relinked: int = 0
    relinks: Tuple[Relink, ...] = ()


@dataclass(frozen=True)
class BrowseEntry:
    key: object
    label: str
    sublabel: str
    art_ids: tuple = ()
    count_label: str = ""
    depth: int = 0
    has_children: bool = False
    locked: bool = False
    active: bool = False


@dataclass(frozen=True)
class DataTrack:
    id: str
    album_artist: str
    artist: str
    album: str
    title: str
    release_date: Optional[str]
    disc_no: Optional[int]
    track_no: Optional[int]
    duration: float
    rel_path: str


@dataclass(frozen=True)
class ImportedPlaylist:
    name: str
    status: str
    matched: int
    total: int


@dataclass(frozen=True)
class UnmatchedTrack:
    artist: str
    title: str
    reason: str


@dataclass(frozen=True)
class LibraryImportResult:
    plays_imported: int
    plays_total: int
    playlists: Tuple[ImportedPlaylist, ...]
    unmatched: Tuple[UnmatchedTrack, ...]
    favorites_imported: int = 0
