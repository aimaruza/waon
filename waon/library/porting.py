
import json
import logging
import os
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass
from typing import Tuple

import waon
from waon.library.entities import DataTrack
from waon.library.identity import (
    DURATION_TOLERANCE, NARROWING as _NARROWING, fold as _fold, identity as _identity,
)

log = logging.getLogger(__name__)

FORMAT = "library-data"
VERSION = 1
MANIFEST, TRACKS, HISTORY, PLAYLISTS, FAVORITES = (
    "manifest.json", "tracks.json", "history.json", "playlists.json",
    "favorites.json")
ENTRIES = (MANIFEST, TRACKS, HISTORY, PLAYLISTS, FAVORITES)
FILE_FILTER = "{} backup (*.zip)".format(waon.APP_NAME)

NOT_AN_EXPORT = "This file isn't a {} backup.".format(waon.APP_NAME)
TOO_NEW = "This backup was made by a newer version of the app."


class LibraryDataError(Exception):
    pass


@dataclass(frozen=True)
class ExportedPlaylist:
    name: str
    created_at: int
    locked: bool
    refs: Tuple[str, ...]


@dataclass(frozen=True)
class LibraryData:
    manifest: dict
    tracks: Tuple[DataTrack, ...]
    history: Tuple[Tuple[str, int], ...]
    playlists: Tuple[ExportedPlaylist, ...]
    favorites: Tuple[Tuple[str, int], ...] = ()


def export_file_name(library_name):
    safe = re.sub(r'[\\/:*?"<>|]', "_", library_name).strip() or "Library"
    return "{} - backup.zip".format(safe)



def export_library_data(repo, dest_path, library_name):
    history = repo.play_history()
    playlists = repo.playlist_contents()
    favorites = repo.favorites()
    if not history and not playlists and not favorites:
        return None
    tracks = repo.data_tracks(referenced_only=True)
    ref_of = {track.id: i for i, track in enumerate(tracks)}
    counts = {"tracks": len(tracks), "plays": len(history),
              "playlists": len(playlists), "favorites": len(favorites)}
    payload = {
        MANIFEST: {"format": FORMAT, "version": VERSION,
                   "library_name": library_name,
                   "exported_at": int(time.time()),
                   "app_version": waon.__version__, "counts": counts},
        TRACKS: [{"ref": ref_of[t.id], "album_artist": t.album_artist,
                  "artist": t.artist, "album": t.album, "title": t.title,
                  "release_date": t.release_date, "disc_no": t.disc_no,
                  "track_no": t.track_no, "duration": t.duration,
                  "rel_path": t.rel_path} for t in tracks],
        HISTORY: [{"track": ref_of[tid], "played_at": at} for tid, at in history],
        PLAYLISTS: [{"name": p.name, "created_at": p.created_at,
                     "locked": p.locked, "tracks": [ref_of[tid] for tid in items]}
                    for p, items in playlists],
        FAVORITES: [{"track": ref_of[tid], "favorited_at": at}
                    for tid, at in favorites],
    }
    directory = os.path.dirname(os.path.abspath(dest_path))
    fd, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ENTRIES:
                zf.writestr(name, json.dumps(payload[name], ensure_ascii=False))
        os.replace(temp_path, dest_path)
    except BaseException:
        try:
            os.remove(temp_path)
        except OSError:
            log.exception("could not remove the temporary export %s", temp_path)
        raise
    log.info("exported %s to %s", counts, dest_path)
    return counts



def _damaged(detail):
    return LibraryDataError("This backup is damaged ({}).".format(detail))


def _load(zf, name):
    try:
        raw = zf.read(name)
    except KeyError:
        raise _damaged("{} is missing".format(name))
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _damaged("{} is unreadable".format(name))


def _optional_int(value, what):
    if value is None or isinstance(value, int):
        return value
    raise _damaged("bad {}".format(what))


def _parse_track(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("ref"), int):
        raise _damaged("a track has no ref")
    try:
        return DataTrack(
            id=str(raw["ref"]), album_artist=str(raw["album_artist"]),
            artist=str(raw["artist"]), album=str(raw["album"]),
            title=str(raw["title"]),
            release_date=(None if raw["release_date"] is None
                          else str(raw["release_date"])),
            disc_no=_optional_int(raw["disc_no"], "disc number"),
            track_no=_optional_int(raw["track_no"], "track number"),
            duration=float(raw["duration"]), rel_path=str(raw["rel_path"]))
    except (KeyError, TypeError, ValueError):
        raise _damaged("track {} is incomplete".format(raw["ref"]))


def _ref(value, refs):
    if not isinstance(value, int) or str(value) not in refs:
        raise _damaged("a reference points at no track")
    return str(value)


def read_library_data(path):
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise LibraryDataError(NOT_AN_EXPORT)
    with zf:
        if MANIFEST not in zf.namelist():
            raise LibraryDataError(NOT_AN_EXPORT)
        manifest = _load(zf, MANIFEST)
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise LibraryDataError(NOT_AN_EXPORT)
        version = manifest.get("version")
        if not isinstance(version, int):
            raise LibraryDataError(NOT_AN_EXPORT)
        if version > VERSION:
            raise LibraryDataError(TOO_NEW)
        raw_tracks = _load(zf, TRACKS)
        raw_history = _load(zf, HISTORY)
        raw_playlists = _load(zf, PLAYLISTS)
        raw_favorites = (_load(zf, FAVORITES) if FAVORITES in zf.namelist()
                         else [])
    if not all(isinstance(v, list)
               for v in (raw_tracks, raw_history, raw_playlists, raw_favorites)):
        raise _damaged("an entry is not a list")

    tracks = tuple(_parse_track(raw) for raw in raw_tracks)
    refs = set(t.id for t in tracks)
    history = []
    for raw in raw_history:
        if not isinstance(raw, dict) or not isinstance(raw.get("played_at"), int):
            raise _damaged("a play has no time")
        history.append((_ref(raw.get("track"), refs), raw["played_at"]))
    playlists = []
    for raw in raw_playlists:
        if (not isinstance(raw, dict) or not isinstance(raw.get("name"), str)
                or not isinstance(raw.get("created_at"), int)
                or not isinstance(raw.get("tracks"), list)):
            raise _damaged("a playlist is incomplete")
        playlists.append(ExportedPlaylist(
            name=raw["name"], created_at=raw["created_at"],
            locked=bool(raw.get("locked", False)),
            refs=tuple(_ref(r, refs) for r in raw["tracks"])))
    favorites = []
    for raw in raw_favorites:
        if not isinstance(raw, dict) or not isinstance(raw.get("favorited_at"), int):
            raise _damaged("a favorite has no time")
        favorites.append((_ref(raw.get("track"), refs), raw["favorited_at"]))
    return LibraryData(manifest=manifest, tracks=tracks, history=tuple(history),
                       playlists=tuple(playlists), favorites=tuple(favorites))



NOT_FOUND = "not_found"
AMBIGUOUS = "ambiguous"
RECORDING_TOLERANCE = 0.5


@dataclass(frozen=True)
class MatchResult:
    matched: dict
    unmatched: list


def _path_parts(rel_path):
    return [p.lower() for p in rel_path.replace("\\", "/").split("/") if p]


def _shared_suffix(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _longest_suffix(parts, candidates):
    scored = [(_shared_suffix(parts, _path_parts(c.rel_path)), c) for c in candidates]
    if not scored:
        return 0, []
    best = max(score for score, _c in scored)
    return best, [c for score, c in scored if score == best]


def _narrow(exported, candidates):
    for keep in _NARROWING:
        if len(candidates) == 1:
            return candidates
        kept = [c for c in candidates if keep(exported, c)]
        if kept:
            candidates = kept
    if len(candidates) > 1:
        best, winners = _longest_suffix(_path_parts(exported.rel_path), candidates)
        if best > 0 and len(winners) == 1:
            candidates = winners
    return candidates


def _recording(track):
    if not track.release_date:
        return None
    return (_fold(track.album_artist), _fold(track.title), track.release_date,
            track.disc_no, track.track_no)


def match_tracks(export_tracks, library_tracks):
    by_identity, by_filename, by_recording = {}, {}, {}
    for track in library_tracks:
        by_identity.setdefault(_identity(track), []).append(track)
        parts = _path_parts(track.rel_path)
        if parts:
            by_filename.setdefault(parts[-1], []).append(track)
        recording = _recording(track)
        if recording is not None:
            by_recording.setdefault(recording, []).append(track)

    matched, unmatched = {}, []
    for exported in export_tracks:
        candidates = by_identity.get(_identity(exported))
        if candidates:
            candidates = _narrow(exported, list(candidates))
            if len(candidates) == 1:
                matched[exported.id] = candidates[0].id
            else:
                unmatched.append((exported, AMBIGUOUS))
            continue
        parts = _path_parts(exported.rel_path)
        pool = by_filename.get(parts[-1], []) if len(parts) >= 2 else []
        best, by_path = _longest_suffix(parts, pool)
        if best >= 2 and len(by_path) == 1:
            matched[exported.id] = by_path[0].id
            continue
        recording = _recording(exported)
        same = [t for t in by_recording.get(recording, ())
                if abs(t.duration - exported.duration) <= RECORDING_TOLERANCE]
        if len(same) == 1:
            matched[exported.id] = same[0].id
        elif len(same) > 1 or (best >= 2 and by_path):
            unmatched.append((exported, AMBIGUOUS))
        else:
            unmatched.append((exported, NOT_FOUND))
    return MatchResult(matched=matched, unmatched=unmatched)
