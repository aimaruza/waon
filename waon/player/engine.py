
import logging
import os
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal
from ffpyplayer.player import MediaPlayer

try:
    from ffpyplayer.tools import set_loglevel
    set_loglevel("error")
except Exception:
    pass

log = logging.getLogger(__name__)

_keepalive_player = None
_keepalive_attempted = False


def _ensure_shared_audio_device():
    global _keepalive_player, _keepalive_attempted
    if _keepalive_attempted:
        return
    _keepalive_attempted = True
    try:
        _keepalive_player = MediaPlayer(
            "anullsrc=r=44100:cl=stereo",
            ff_opts={"f": "lavfi", "paused": True, "volume": 0.0, "loop": 0,
                     "vn": True})
    except Exception:
        log.exception("could not start keepalive audio device")


def _release_shared_audio_device():
    global _keepalive_player, _keepalive_attempted
    player = _keepalive_player
    _keepalive_player = None
    _keepalive_attempted = False
    return player


def shutdown():
    global _keepalive_player
    if _keepalive_player is not None:
        try:
            _keepalive_player.close_player()
        except Exception:
            log.exception("could not close keepalive audio device")
        _keepalive_player = None


class PlayerEngine(QObject):
    positionChanged = Signal(float)
    durationChanged = Signal(float)
    stateChanged = Signal(str)
    trackFinished = Signal()
    errorOccurred = Signal(str)

    POLL_MS = 200
    VOLUME_DELAY_MS = 250

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = None
        self._duration = 0.0
        self._volume = 0.8
        self._state = "stopped"
        self._audio_started = False
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self._on_tick)
        self._closing_threads = []
        self._path = None
        self._position = 0.0
        self._pending = None

    _SLOW_LOAD_S = 0.15
    _REOPEN_WAIT_S = 10.0

    def load(self, path):
        self._pending = None
        _ensure_shared_audio_device()
        t0 = time.time()
        self._teardown(async_close=True)
        t1 = time.time()
        if not os.path.isfile(path):
            self.errorOccurred.emit("File not found: {}".format(path))
            return False
        try:
            self._player = MediaPlayer(
                str(path),
                ff_opts={"paused": True, "sync": "audio", "vn": True},
            )
        except Exception as exc:
            self._player = None
            self.errorOccurred.emit("Could not open file: {}".format(exc))
            return False
        t2 = time.time()
        self._duration = self._resolve_duration()
        t3 = time.time()
        self._path = path
        self._position = 0.0
        self.durationChanged.emit(self._duration)
        self._set_state("paused")
        self.positionChanged.emit(0.0)
        total = t3 - t0
        log.debug(
            "load(%r): teardown=%.1fms open=%.1fms resolve_duration=%.1fms "
            "total=%.1fms", path, (t1 - t0) * 1000, (t2 - t1) * 1000,
            (t3 - t2) * 1000, total * 1000)
        if total > self._SLOW_LOAD_S:
            log.warning(
                "slow load(%r): teardown=%.1fms open=%.1fms "
                "resolve_duration=%.1fms total=%.1fms", path,
                (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000,
                total * 1000)
        return True

    def _resolve_duration(self, timeout=1.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            meta = self._player.get_metadata()
            dur = meta.get("duration") or 0.0
            if dur:
                try:
                    return float(dur)
                except (TypeError, ValueError):
                    return 0.0
            time.sleep(0.02)
        return 0.0

    def defer_load(self, path, position, duration):
        self._teardown(async_close=True)
        self._pending = (path, max(0.0, float(position)))
        self._path = path
        self._position = self._pending[1]
        self._duration = float(duration or 0.0)
        self.durationChanged.emit(self._duration)
        self._set_state("paused")
        self.positionChanged.emit(self._position)

    def release(self):
        if self._state == "playing":
            return False
        track = self._player
        keepalive = _release_shared_audio_device()
        if track is None and keepalive is None:
            return False
        if track is not None:
            self._pending = (self._path, self._position)
        self._timer.stop()
        self._player = None
        self._audio_started = False
        players = [p for p in (track, keepalive) if p is not None]
        self._closing_threads = [t for t in self._closing_threads if t.is_alive()]
        thread = threading.Thread(target=self._close_in_order, args=(players,),
                                  daemon=True)
        self._closing_threads.append(thread)
        thread.start()
        log.info("released the audio device while idle (%d player(s))", len(players))
        return True

    def _close_in_order(self, players):
        for player in players:
            self._safe_close(player)

    def _reopen_pending(self):
        path, position = self._pending
        self._pending = None
        self.shutdown_wait(timeout=self._REOPEN_WAIT_S)
        if any(t.is_alive() for t in self._closing_threads):
            log.warning("an audio player is still closing after %.0fs; "
                        "reopening anyway", self._REOPEN_WAIT_S)
        if not self.load(path):
            log.warning("could not reopen %s to resume it", path)
            self._set_state("stopped")
            return False
        if position > 0:
            self.seek(position)
        return True

    def play(self):
        if self._pending is not None and not self._reopen_pending():
            return
        if self._player is None:
            return
        self._set_state("playing")
        self._timer.start()
        if self._audio_started:
            self._player.set_pause(False)
            return
        player = self._player
        QTimer.singleShot(self.VOLUME_DELAY_MS, self,
                          lambda: self._start_audio(player))

    def pause(self):
        if self._player is None:
            return
        self._player.set_pause(True)
        self._set_state("paused")
        self._timer.stop()

    def toggle(self):
        self.pause() if self._state == "playing" else self.play()

    def seek(self, seconds):
        seconds = max(0.0, float(seconds))
        if self._pending is not None:
            self._pending = (self._pending[0], seconds)
            self._position = seconds
            self.positionChanged.emit(seconds)
            return
        if self._player is None:
            return
        try:
            self._player.seek(seconds, relative=False, accurate=False)
            self._position = seconds
            self.positionChanged.emit(seconds)
        except Exception as exc:
            self.errorOccurred.emit("Seek failed: {}".format(exc))

    def set_volume(self, level):
        self._volume = max(0.0, min(1.0, float(level)))
        if self._player is not None and self._audio_started:
            try:
                self._player.set_volume(self._volume)
            except Exception:
                pass

    def _start_audio(self, player):
        if player is not self._player or self._state != "playing":
            return
        try:
            player.set_volume(self._volume)
        except Exception:
            pass
        player.set_pause(False)
        self._audio_started = True

    def volume(self):
        return self._volume

    def state(self):
        return self._state

    def duration(self):
        return self._duration

    def stop(self):
        self._pending = None
        self._teardown()
        self._position = 0.0
        self._set_state("stopped")
        self.positionChanged.emit(0.0)

    def _on_tick(self):
        if self._player is None:
            return
        try:
            pts = float(self._player.get_pts())
        except Exception:
            return
        self._position = pts
        self.positionChanged.emit(pts)
        finished = self._duration > 0 and pts >= self._duration - 0.25
        if not finished:
            try:
                _frame, val = self._player.get_frame()
                if val == "eof":
                    finished = True
            except Exception:
                pass
        if finished:
            self._timer.stop()
            self.trackFinished.emit()

    def _set_state(self, state):
        self._state = state
        self.stateChanged.emit(state)

    def _teardown(self, async_close=False):
        self._timer.stop()
        if self._player is not None:
            player = self._player
            self._player = None
            try:
                player.set_pause(True)
            except Exception:
                pass
            if async_close:
                self._closing_threads = [t for t in self._closing_threads
                                         if t.is_alive()]
                t = threading.Thread(target=self._safe_close, args=(player,),
                                     daemon=True)
                self._closing_threads.append(t)
                t.start()
            else:
                self._safe_close(player)
        self._duration = 0.0
        self._audio_started = False

    @staticmethod
    def _safe_close(player):
        try:
            player.close_player()
        except Exception:
            log.exception("could not close a previous player")

    def shutdown_wait(self, timeout=2.0):
        for t in self._closing_threads:
            t.join(timeout)
