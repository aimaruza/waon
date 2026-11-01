
import logging
import time

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class PlayTracker(QObject):
    playCredited = Signal()

    THRESHOLD_FRACTION = 0.9

    def __init__(self, queue, engine, service, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.engine = engine
        self.service = service
        self._track_id = None
        self._library_id = None
        self._threshold = None
        self._accumulated = 0.0
        self._credited = False
        self._playing_since = None
        self.queue.currentChanged.connect(self._on_current_changed)
        self.engine.stateChanged.connect(self._on_state_changed)
        self.engine.positionChanged.connect(self._on_position_changed)

    def serialize(self):
        if self._track_id is None:
            return None
        return (self._track_id, self._library_id, self._live_accumulated(),
                self._credited)

    def restore_progress(self, track_id, library_id, accumulated, credited):
        if track_id is None:
            return
        if track_id != self._track_id or library_id != self._library_id:
            log.warning(
                "saved play progress was for track %s, not the resumed "
                "track %s; starting this instance fresh", track_id, self._track_id)
            return
        self._accumulated = accumulated
        self._credited = credited

    def _on_current_changed(self, row):
        track = self.queue.track_at(row)
        if self.queue.is_rebuilding() and self._is_current_instance(track):
            return
        self._commit_playing_segment()
        self._maybe_credit()
        if track is None or track.track_id is None or track.duration <= 0:
            self._track_id = None
            self._library_id = None
            self._threshold = None
        else:
            self._track_id = track.track_id
            self._library_id = track.library_id
            self._threshold = track.duration * self.THRESHOLD_FRACTION
        self._accumulated = 0.0
        self._credited = False
        self._playing_since = None

    def _is_current_instance(self, track):
        return (track is not None and self._track_id is not None
                and track.track_id == self._track_id
                and track.library_id == self._library_id)

    def _on_state_changed(self, state):
        if state == "playing":
            self._playing_since = time.monotonic()
        else:
            self._commit_playing_segment()
            self._maybe_credit()

    def _on_position_changed(self, _seconds):
        self._maybe_credit()

    def _commit_playing_segment(self):
        if self._playing_since is not None:
            self._accumulated += time.monotonic() - self._playing_since
            self._playing_since = None

    def _live_accumulated(self):
        if self._playing_since is None:
            return self._accumulated
        return self._accumulated + (time.monotonic() - self._playing_since)

    _SLOW_RECORD_S = 0.15

    def _maybe_credit(self):
        if self._credited or self._track_id is None:
            return
        if self._live_accumulated() >= self._threshold:
            self._credited = True
            t0 = time.monotonic()
            self.service.record_play(
                self._library_id, self._track_id, int(time.time()))
            elapsed = time.monotonic() - t0
            if elapsed > self._SLOW_RECORD_S:
                log.warning("slow record_play for track %s: %.1fms",
                           self._track_id, elapsed * 1000)
            self.playCredited.emit()
