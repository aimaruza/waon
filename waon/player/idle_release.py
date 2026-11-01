
import logging
import time

from PySide6.QtCore import QObject, QTimer

from waon import power
from waon.settings import NEVER, RELEASE_ON_BATTERY, RELEASE_PLUGGED_IN

log = logging.getLogger(__name__)


class IdleRelease(QObject):
    def __init__(self, engine, settings, on_battery=power.on_battery,
                 clock=time.monotonic, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._settings = settings
        self._on_battery = on_battery
        self._clock = clock
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        self._idle_since = None
        self._stopped = False
        engine.stateChanged.connect(self._on_state)
        settings.changed.connect(self._on_setting)
        if engine.state() != "playing":
            self._idle_since = clock()
            self.rearm()

    def power_changed(self):
        self.rearm()

    def stop(self):
        self._stopped = True
        self._idle_since = None
        self._timer.stop()

    def rearm(self):
        self._timer.stop()
        if self._stopped or self._idle_since is None:
            return
        key = RELEASE_ON_BATTERY if self._on_battery() else RELEASE_PLUGGED_IN
        delay = self._settings.get(key)
        if delay == NEVER:
            return
        remaining = max(0.0, delay - (self._clock() - self._idle_since))
        self._timer.start(int(remaining * 1000))

    def _on_state(self, state):
        if state == "playing":
            self._idle_since = None
            self._timer.stop()
            return
        if self._idle_since is None:
            self._idle_since = self._clock()
        self.rearm()

    def _on_setting(self, key, _value):
        if key in (RELEASE_ON_BATTERY, RELEASE_PLUGGED_IN):
            self.rearm()

    def _fire(self):
        if self._engine.state() == "playing":
            return
        self._engine.release()
