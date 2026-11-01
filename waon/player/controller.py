
import logging
import random
import time

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class PlaybackController(QObject):

    PREV_WINDOW_S = 3.0

    repeatChanged = Signal(str)
    shuffleChanged = Signal(bool)
    falseStart = Signal()

    def __init__(self, queue, engine, parent=None):
        super().__init__(parent)
        self.queue = queue
        self.engine = engine
        self.history = []
        self._pass_played = set()
        self._repeat = "off"
        self._shuffle = False
        self._last_prev_time = None
        self._rng = random.Random()
        self.engine.trackFinished.connect(self.on_track_finished)
        self.queue.modelReset.connect(self._on_queue_reset)
        self.queue.rowsInserted.connect(self._on_rows_inserted)
        self.queue.rowsRemoved.connect(self._on_rows_removed)

    @property
    def repeat(self):
        return self._repeat

    @property
    def shuffle(self):
        return self._shuffle

    def set_repeat(self, mode):
        self._repeat = mode
        self.repeatChanged.emit(mode)

    def cycle_repeat(self):
        self.set_repeat({"off": "all", "all": "one", "one": "off"}[self._repeat])

    def set_shuffle(self, on):
        self._shuffle = bool(on)
        self._pass_played.clear()
        self.shuffleChanged.emit(self._shuffle)

    def toggle_shuffle(self):
        self.set_shuffle(not self._shuffle)

    def seed(self, value):
        self._rng.seed(value)

    def toggle_play(self):
        if self.engine.state() == "stopped":
            if self.queue.rowCount() == 0:
                log.debug("play with an empty queue: nothing to play")
                return
            row = self.queue.resume_index()
            self.play_index(row if row >= 0 else 0)
        else:
            self.engine.toggle()

    def stop(self):
        self.engine.stop()

    _SLOW_SWITCH_S = 0.15

    def play_index(self, row):
        t0 = time.monotonic()
        if not self.queue.set_current(row):
            log.warning("cannot play row %s: the queue holds %d tracks",
                        row, self.queue.rowCount())
            return
        t1 = time.monotonic()
        while not self._play_current(t0, t1):
            track = self.queue.current_track()
            if not self.queue.next():
                log.warning("could not load %s and nothing follows it", track.path)
                self.engine.stop()
                return
            log.warning("could not load %s; skipping", track.path)
            t0 = t1 = time.monotonic()

    def _play_current(self, t0, t1):
        track = self.queue.current_track()
        if self.engine.load(track.path):
            t2 = time.monotonic()
            self.engine.play()
            t3 = time.monotonic()
            total = t3 - t0
            log.debug(
                "play_index(%r): set_current(+signal chain)=%.1fms "
                "engine.load=%.1fms engine.play=%.1fms total=%.1fms",
                track.title, (t1 - t0) * 1000, (t2 - t1) * 1000,
                (t3 - t2) * 1000, total * 1000)
            if total > self._SLOW_SWITCH_S:
                log.warning(
                    "SLOW track switch to %r: set_current(+signal chain)="
                    "%.1fms engine.load=%.1fms engine.play=%.1fms "
                    "total=%.1fms", track.title, (t1 - t0) * 1000,
                    (t2 - t1) * 1000, (t3 - t2) * 1000, total * 1000)
            return True
        return False

    def play_next(self):
        self.advance()

    def play_prev(self):
        now = time.monotonic()
        double_press = (
            self._last_prev_time is not None
            and (now - self._last_prev_time) < self.PREV_WINDOW_S
        )
        self._last_prev_time = now
        if not double_press:
            self.engine.seek(0)
            return
        if self._shuffle and self.history:
            self.play_index(self.history.pop())
        elif self.queue.prev():
            self.play_index(self.queue.current_index())
        else:
            self.engine.seek(0)

    def advance(self):
        target = self._next_index()
        if target is None:
            self.engine.stop()
            if not self.queue.set_current(0):
                self.queue.clear_detached()
            self.falseStart.emit()
            return
        current = self.queue.current_index()
        if current >= 0 and not self.queue.is_detached():
            self.history.append(current)
        self.play_index(target)

    def on_track_finished(self):
        if (self._repeat == "one" and self.queue.current_index() >= 0
                and not self.queue.is_detached()):
            row = self.queue.current_index()
            self.play_index(row)
            if self.queue.current_index() == row:
                self.falseStart.emit()
        else:
            self.advance()

    def _on_queue_reset(self):
        del self.history[:]
        self._pass_played.clear()
        self._last_prev_time = None

    def _on_rows_inserted(self, _parent, first, last):
        n = last - first + 1
        self._pass_played = {i + n if i >= first else i for i in self._pass_played}

    def _on_rows_removed(self, _parent, first, last):
        n = last - first + 1
        self._pass_played = {i - n if i > last else i for i in self._pass_played
                             if not first <= i <= last}

    def _next_index(self):
        count = self.queue.rowCount()
        if count == 0:
            return None
        current = self.queue.current_index()
        if self._shuffle:
            if count == 1:
                return current if self._repeat != "off" else None
            if current >= 0 and not self.queue.is_detached():
                self._pass_played.add(current)
            choices = [i for i in range(count) if i not in self._pass_played]
            if not choices:
                if self._repeat == "off":
                    self._pass_played.clear()
                    return None
                self._pass_played.clear()
                choices = [i for i in range(count) if i != current]
            return self._rng.choice(choices)
        if current + 1 < count:
            return current + 1
        return 0 if self._repeat == "all" else None
