
import os
from dataclasses import dataclass
from typing import Optional

try:
    import mutagen
except ImportError:
    mutagen = None


@dataclass(frozen=True)
class Track:
    path: str
    title: str
    artist: str
    album: str
    duration: float
    available: bool = True
    album_id: Optional[str] = None
    track_id: Optional[str] = None
    library_id: Optional[str] = None

    @classmethod
    def from_path(cls, path):
        meta, duration = _read_metadata(path)
        return track_from_metadata(path, meta, duration)


def track_from_metadata(path, meta, duration):
    stem = os.path.splitext(os.path.basename(path))[0]
    title = (str(meta.get("title") or "")).strip() or stem
    artist = (str(meta.get("artist") or "")).strip() or "Unknown Artist"
    album = (str(meta.get("album") or "")).strip()
    try:
        dur = float(duration) if duration else 0.0
    except (TypeError, ValueError):
        dur = 0.0
    return Track(path=path, title=title, artist=artist, album=album, duration=dur)


def _read_metadata(path):
    meta = {}
    duration = 0.0
    if mutagen is None:
        return meta, duration
    try:
        mf = mutagen.File(path, easy=True)
    except Exception:
        mf = None
    if mf is not None:
        info = getattr(mf, "info", None)
        if info is not None:
            duration = getattr(info, "length", 0.0) or 0.0
        for key in ("title", "artist", "album"):
            try:
                val = mf.get(key)
            except Exception:
                val = None
            if val:
                meta[key] = val[0] if isinstance(val, (list, tuple)) else val
    return meta, duration
