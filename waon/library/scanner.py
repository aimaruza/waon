
import os

from waon.library import paths
from waon.library.entities import FoundFile, TagData
from waon.util import AUDIO_EXTENSIONS

_EXTENSIONS = tuple(ext.lower() for ext in AUDIO_EXTENSIONS)


def is_audio(filename):
    return filename.lower().endswith(_EXTENSIONS)


def walk(roots, should_cancel=None, on_dir=None, excluded=None):
    excluded = excluded or frozenset()
    for root in roots:
        if not os.path.isdir(root.path):
            continue
        for found in _walk_root(root, should_cancel, on_dir, excluded):
            yield found


def _walk_root(root, should_cancel, on_dir, excluded):
    stack = [root.path]
    while stack:
        current = stack.pop()
        if should_cancel is not None and should_cancel():
            return
        try:
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        subdirs = []
        files = []
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    rel = paths.to_rel(root.path, entry.path)
                    if rel is not None and (root.id, paths.norm_key(rel)) in excluded:
                        continue
                    subdirs.append(entry.path)
                    continue
            except OSError:
                continue
            files.append(entry)
        if on_dir is not None:
            on_dir(current, len(files))
        for entry in files:
            if not is_audio(entry.name):
                continue
            rel_path = paths.to_rel(root.path, entry.path)
            if rel_path is None:
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            yield FoundFile(root_id=root.id, rel_path=rel_path,
                            abs_path=entry.path, mtime=int(stat.st_mtime),
                            size=stat.st_size)
        stack.extend(reversed(subdirs))


try:
    import mutagen
except ImportError:
    mutagen = None

_TAG_KEYS = ("title", "artist", "album", "albumartist", "tracknumber",
             "discnumber", "date")


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _text(value):
    return str(_first(value) or "").strip()


def _number(value):
    raw = _first(value)
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    try:
        return int(text)
    except ValueError:
        return None


def tags_from_mapping(path, meta, duration):
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        dur = float(duration) if duration else 0.0
    except (TypeError, ValueError):
        dur = 0.0
    return TagData(
        title=_text(meta.get("title")) or stem,
        artist=_text(meta.get("artist")) or "Unknown Artist",
        album=_text(meta.get("album")),
        album_artist=_text(meta.get("albumartist")),
        track_no=_number(meta.get("tracknumber")),
        disc_no=_number(meta.get("discnumber")),
        duration=dur,
        date=_text(meta.get("date")),
    )


def read_tags(path):
    meta = {}
    duration = 0.0
    if mutagen is not None:
        try:
            handle = mutagen.File(path, easy=True)
        except Exception:
            handle = None
        if handle is not None:
            info = getattr(handle, "info", None)
            if info is not None:
                duration = getattr(info, "length", 0.0) or 0.0
            for key in _TAG_KEYS:
                try:
                    value = handle.get(key)
                except Exception:
                    value = None
                if value:
                    meta[key] = value
    return tags_from_mapping(path, meta, duration)
