
import logging
import os
import time
import uuid

from waon.library import locations, paths, scanner
from waon.library.entities import ScanProgress, ScanResult
from waon.library.resolver import Resolver
from waon.player.artwork import extract_cover

log = logging.getLogger(__name__)


class ScanRunner:

    BATCH = 500

    PROGRESS_EVERY = 50

    def __init__(self, repo, on_progress=None, should_cancel=None):
        self._repo = repo
        self._on_progress = on_progress
        self._should_cancel = should_cancel
        self._files_seen = 0
        self._tracks_found = 0
        self._current_dir = ""
        self._since_progress = 0
        self._inserted_ids = set()

    def scan(self, root_ids=None):
        roots = self._repo.roots()
        partial = root_ids is not None
        if partial:
            wanted = set(root_ids)
            roots = [r for r in roots if r.id in wanted]

        excluded = {(e.root_id, paths.norm_key(e.rel_path))
                    for e in self._repo.exclusions()}

        index = self._repo.stat_index()
        seen = set()
        inserts = []
        updates = []
        touches = []
        added = updated = skipped = duplicates = 0
        cancelled = False

        for found in scanner.walk(roots, should_cancel=self._should_cancel,
                                  on_dir=self._note_dir, excluded=excluded):
            if self._should_cancel is not None and self._should_cancel():
                cancelled = True
                break

            key = paths.norm_key(found.rel_path)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            self._tracks_found += 1
            self._tick()

            existing = index.get(key)
            if existing is not None:
                track_id, mtime, size = existing
                if mtime == found.mtime and size == found.size:
                    touches.append((track_id, found.root_id))
                    skipped += 1
                else:
                    updates.append(self._update_record(track_id, found))
                    updated += 1
            else:
                record = self._insert_record(found)
                inserts.append(record)
                self._inserted_ids.add(record["id"])
                added += 1

            if len(inserts) >= self.BATCH:
                self._repo.insert_tracks(inserts)
                inserts = []
            if len(updates) >= self.BATCH:
                self._repo.update_tracks(updates)
                updates = []
            if len(touches) >= self.BATCH:
                self._repo.touch_tracks(touches)
                touches = []

        if not cancelled and self._should_cancel is not None and self._should_cancel():
            cancelled = True

        self._repo.insert_tracks(inserts)
        self._repo.update_tracks(updates)
        self._repo.touch_tracks(touches)

        missing = 0
        relinks = []
        if not cancelled and not partial:
            gone = [track_id for key, (track_id, _m, _s) in index.items()
                    if key not in seen]
            self._repo.mark_unavailable(gone)
            missing = len(gone)
            relinks = self._relink_moved()
            gone_ids = set(gone)
            missing -= sum(1 for r in relinks if r.kept_id in gone_ids)
            added -= sum(1 for r in relinks if r.dropped_id in self._inserted_ids)

        if not cancelled:
            cancelled = self._extract_art()
            self._cleanup_orphaned_albums()

        self._emit()

        self._repo.set_meta("last_scan_at", int(time.time()))
        return ScanResult(added=added, updated=updated, skipped=skipped,
                          missing=missing, duplicates=duplicates,
                          cancelled=cancelled, relinked=len(relinks),
                          relinks=tuple(relinks))


    def _relink_moved(self):
        try:
            relinks = self._repo.relink_moved_tracks(self._inserted_ids)
        except Exception:
            log.exception("could not relink moved tracks")
            return []
        if relinks:
            log.info("relinked %d moved track(s)", len(relinks))
        return relinks

    def _note_dir(self, dirpath, n_files):
        self._files_seen += n_files
        self._current_dir = dirpath
        self._emit()

    def _tick(self):
        self._since_progress += 1
        if self._since_progress >= self.PROGRESS_EVERY:
            self._emit()

    def _emit(self):
        self._since_progress = 0
        if self._on_progress is not None:
            self._on_progress(ScanProgress(files_seen=self._files_seen,
                                           tracks_found=self._tracks_found,
                                           current_dir=self._current_dir))

    def _insert_record(self, found):
        tags = scanner.read_tags(found.abs_path)
        return {
            "id": str(uuid.uuid4()), "rel_path": found.rel_path,
            "root_hint_id": found.root_id,
            "title": tags.title, "artist": tags.artist, "album": tags.album,
            "album_artist": tags.album_artist, "track_no": tags.track_no,
            "disc_no": tags.disc_no, "duration": tags.duration,
            "mtime": found.mtime, "size": found.size,
            "added_at": int(time.time()),
            "release_date": tags.date or None,
        }

    def _update_record(self, track_id, found):
        tags = scanner.read_tags(found.abs_path)
        return {
            "id": track_id, "root_hint_id": found.root_id, "title": tags.title,
            "artist": tags.artist, "album": tags.album,
            "album_artist": tags.album_artist, "track_no": tags.track_no,
            "disc_no": tags.disc_no, "duration": tags.duration,
            "mtime": found.mtime, "size": found.size,
            "release_date": tags.date or None,
        }

    def _extract_art(self):
        pending = self._repo.pending_album_ids()
        if not pending:
            return False
        os.makedirs(locations.artwork_dir(), exist_ok=True)
        resolver = Resolver(self._repo.roots())
        updates = []
        cancelled = False
        for album_id in pending:
            if self._should_cancel is not None and self._should_cancel():
                cancelled = True
                break
            updates.append((album_id, self._extract_one(album_id, resolver)))
            if len(updates) >= self.BATCH:
                self._repo.set_album_art_statuses(updates)
                updates = []
        self._repo.set_album_art_statuses(updates)
        return cancelled

    def _extract_one(self, album_id, resolver):
        resolved = False
        for track in self._repo.tracks_by_album_id(album_id):
            abs_path, _root_id = resolver.resolve(track.rel_path, track.root_hint_id)
            if abs_path is None:
                continue
            resolved = True
            data = extract_cover(abs_path)
            if not data:
                continue
            try:
                with open(locations.art_path(album_id), "wb") as fh:
                    fh.write(data)
            except OSError:
                log.exception("could not write artwork for album %s", album_id)
                return "pending"
            return "found"
        return "none" if resolved else "pending"

    def _cleanup_orphaned_albums(self):
        for album_id in self._repo.delete_orphaned_albums():
            try:
                os.remove(locations.art_path(album_id))
            except FileNotFoundError:
                pass
            except OSError:
                log.exception("could not delete artwork for album %s", album_id)
