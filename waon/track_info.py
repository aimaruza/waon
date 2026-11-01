
import datetime
import logging
import os
from dataclasses import dataclass
from typing import Optional

try:
    import mutagen
except ImportError:
    mutagen = None

log = logging.getLogger(__name__)

_CODEC_NAMES = {
    "FLAC": "FLAC", "MP3": "MP3", "EasyMP3": "MP3",
    "OggVorbis": "Ogg Vorbis", "OggOpus": "Opus", "OggFLAC": "FLAC",
    "WAVE": "WAV", "AIFF": "AIFF", "ASF": "WMA",
    "MonkeysAudio": "APE", "WavPack": "WavPack",
}


@dataclass(frozen=True)
class FileDetails:
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track_no: str = ""
    disc_no: str = ""
    year: str = ""
    genre: str = ""
    composer: str = ""
    codec: str = ""
    bits_per_sample: int = 0
    sample_rate: int = 0
    channels: int = 0
    bitrate: int = 0
    duration: float = 0.0
    size: int = 0


def _first(mf, key):
    try:
        val = mf.get(key)
    except Exception:
        return ""
    if not val:
        return ""
    if isinstance(val, (list, tuple)):
        val = val[0]
    return str(val).strip()


def _of(raw):
    if "/" not in raw:
        return raw
    number, total = (part.strip() for part in raw.split("/", 1))
    if number and total:
        return "{} of {}".format(number, total)
    return number


def _extension_codec(path):
    return os.path.splitext(path)[1].lstrip(".").upper()


def _codec_name(mf, info, path):
    kind = type(mf).__name__
    if kind in ("MP4", "EasyMP4"):
        return "ALAC" if getattr(info, "codec", "") == "alac" else "AAC"
    return _CODEC_NAMES.get(kind) or _extension_codec(path)


def _int(info, name):
    try:
        return int(getattr(info, name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def read_file_details(path):
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        log.warning("track info: cannot read %s: %s", path, exc)
        return FileDetails()
    if mutagen is None:
        return FileDetails(codec=_extension_codec(path), size=size)
    try:
        mf = mutagen.File(path, easy=True)
    except Exception as exc:
        log.warning("track info: cannot parse %s: %s", path, exc)
        mf = None
    if mf is None:
        return FileDetails(codec=_extension_codec(path), size=size)
    info = getattr(mf, "info", None)
    date = _first(mf, "date")
    try:
        duration = float(getattr(info, "length", 0.0) or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return FileDetails(
        title=_first(mf, "title"),
        artist=_first(mf, "artist"),
        album=_first(mf, "album"),
        album_artist=_first(mf, "albumartist"),
        track_no=_of(_first(mf, "tracknumber")),
        disc_no=_of(_first(mf, "discnumber")),
        year=date[:4] if date[:4].isdigit() else "",
        genre=_first(mf, "genre"),
        composer=_first(mf, "composer"),
        codec=_codec_name(mf, info, path),
        bits_per_sample=_int(info, "bits_per_sample"),
        sample_rate=_int(info, "sample_rate"),
        channels=_int(info, "channels"),
        bitrate=_int(info, "bitrate"),
        duration=duration,
        size=size,
    )



def location_breadcrumb(path):
    folder = os.path.dirname(os.path.normpath(path))
    drive, rest = os.path.splitdrive(folder)
    parts = [p for p in rest.split(os.sep) if p]
    if drive:
        parts.insert(0, drive)
    return " > ".join(parts)


def format_audio(details):
    parts = []
    if details.codec:
        parts.append(details.codec)
    if details.bits_per_sample:
        parts.append("{}-bit".format(details.bits_per_sample))
    if details.sample_rate:
        parts.append("{:g} kHz".format(details.sample_rate / 1000.0))
    if details.channels == 1:
        parts.append("Mono")
    elif details.channels == 2:
        parts.append("Stereo")
    elif details.channels > 2:
        parts.append("{} ch".format(details.channels))
    return " • ".join(parts)


def format_bitrate(bps):
    return "{} kbps".format(int(round(bps / 1000.0))) if bps else ""


def format_size(size):
    if not size:
        return ""
    if size < 1024:
        return "{} B".format(size)
    value = float(size)
    for unit in ("KB", "MB", "GB"):
        value /= 1024.0
        if value < 1024 or unit == "GB":
            return "{:.1f} {}".format(value, unit)


def format_duration(seconds):
    total = int(round(seconds or 0))
    if total <= 0:
        return ""
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{}:{:02d}".format(minutes, secs)


def format_date(ts):
    dt = datetime.datetime.fromtimestamp(ts)
    return "{} {}".format(dt.day, dt.strftime("%b %Y"))


def format_datetime(ts):
    dt = datetime.datetime.fromtimestamp(ts)
    return "{}, {}".format(format_date(ts), dt.strftime("%H:%M"))



@dataclass(frozen=True)
class TrackInfo:
    title: str
    file_name: str
    location: str
    tags: tuple
    audio: tuple
    listening: Optional[tuple]
    play_count: int = 0


def _rows(pairs):
    return tuple((label, value) for label, value in pairs if value)


def _track_text(track_no, disc_no):
    if track_no and disc_no:
        return "{} • Disc {}".format(track_no, disc_no)
    if disc_no:
        return "Disc {}".format(disc_no)
    return track_no


def listening_rows(row, stats):
    count, first, last = stats
    pairs = [("Plays", str(count))]
    if count:
        pairs.append(("First played", format_date(first)))
        pairs.append(("Last played", format_datetime(last)))
    if row.added_at:
        pairs.append(("Added", format_date(row.added_at)))
    return _rows(pairs)


def build_track_info(track, details, row=None, stats=None):
    fallback = row if row is not None else track
    stored_track = str(row.track_no) if row is not None and row.track_no else ""
    stored_disc = str(row.disc_no) if row is not None and row.disc_no else ""
    tags = _rows([
        ("Artist", details.artist or fallback.artist),
        ("Album", details.album or fallback.album),
        ("Album artist", details.album_artist
         or (row.album_artist if row is not None else "")),
        ("Track", _track_text(details.track_no or stored_track,
                              details.disc_no or stored_disc)),
        ("Year", details.year),
        ("Genre", details.genre),
        ("Composer", details.composer),
    ])
    audio = _rows([
        ("Format", format_audio(details)),
        ("Bitrate", format_bitrate(details.bitrate)),
        ("Duration", format_duration(details.duration or fallback.duration)),
        ("Size", format_size(details.size)),
    ])
    in_library = row is not None and stats is not None
    title = details.title or fallback.title or os.path.basename(track.path)
    return TrackInfo(
        title=title,
        file_name=os.path.basename(track.path),
        location=location_breadcrumb(track.path),
        tags=tags,
        audio=audio,
        listening=listening_rows(row, stats) if in_library else None,
        play_count=stats[0] if in_library else 0,
    )
