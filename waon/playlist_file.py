
import locale
import logging
import os

from waon.util import AUDIO_EXTENSIONS

log = logging.getLogger(__name__)

PLAYLIST_EXTENSIONS = (".m3u", ".m3u8")
DROPPABLE_EXTENSIONS = AUDIO_EXTENSIONS + PLAYLIST_EXTENSIONS


def is_droppable(path):
    return path.lower().endswith(DROPPABLE_EXTENSIONS)


def parse_m3u(path):
    text = _read_text(path)
    if text is None:
        return []
    base_dir = os.path.dirname(path)
    tracks = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "://" in line:
            continue
        entry = line if os.path.isabs(line) else os.path.join(base_dir, line)
        entry = os.path.normpath(entry)
        if entry.lower().endswith(AUDIO_EXTENSIONS):
            tracks.append(entry)
    return tracks


def _read_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        log.exception("could not read playlist file %s", path)
        return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode(locale.getpreferredencoding(False))
    except UnicodeDecodeError:
        log.exception("could not decode playlist file %s", path)
        return None


def expand_paths(paths):
    out = []
    for path in paths:
        lower = path.lower()
        if lower.endswith(AUDIO_EXTENSIONS):
            out.append(path)
        elif lower.endswith(PLAYLIST_EXTENSIONS):
            out.extend(parse_m3u(path))
    return out
