
from PySide6.QtCore import QObject, QPoint, QTimer
from PySide6.QtGui import QGuiApplication

from waon import settings as settings_mod
from waon.ui import notification
from waon.ui.notification import NotificationWindow


class NotificationController(QObject):

    MARGIN = 16
    DEBOUNCE_MS = 120

    def __init__(self, main_window, parent=None, settings=None):
        super().__init__(parent)
        self._mw = main_window
        self._settings = settings
        self._window = None
        self._pending = None
        self._closed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)
        if settings is not None:
            settings.changed.connect(self._on_setting_changed)

    def _get(self, key):
        if self._settings is None:
            return settings_mod.default(key)
        return self._settings.get(key)

    def should_notify(self):
        if not self._get("notifications.enabled"):
            return False
        if self._get("notifications.trigger") == "always":
            return True
        mw = self._mw
        return not (mw.isVisible() and not mw.isMinimized() and mw.isActiveWindow())

    def position_for(self, area, corner="bottom_right"):
        left = area.left() + self.MARGIN - notification.SHADOW
        right = (area.right() - self.MARGIN + notification.SHADOW
                 - notification.WINDOW_W + 1)
        top = area.top() + self.MARGIN - notification.SHADOW
        bottom = (area.bottom() - self.MARGIN + notification.SHADOW
                  - notification.WINDOW_H + 1)
        x = left if corner in ("top_left", "bottom_left") else right
        y = top if corner in ("top_left", "top_right") else bottom
        return QPoint(x, y)

    def _available_area(self):
        screen = self._mw.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return None
        return screen.availableGeometry()

    def notify(self, track, pixmap, display_artist):
        if self._closed:
            return
        self._pending = (track, pixmap, display_artist)
        if self.DEBOUNCE_MS <= 0:
            self._flush()
        else:
            self._timer.start(self.DEBOUNCE_MS)

    def cancel(self):
        self._timer.stop()
        self._pending = None

    def close(self):
        self._closed = True
        self._timer.stop()
        self._pending = None
        if self._window is not None:
            self._window.hide()
            self._window.deleteLater()
            self._window = None

    def _on_setting_changed(self, key, value):
        if key == "notifications.enabled" and not value:
            self.cancel()
            if self._window is not None:
                self._window.hide_now()

    def _flush(self):
        pending, self._pending = self._pending, None
        if pending is None or not self.should_notify():
            return
        self._show(pending[0], pending[1], pending[2])

    def _show(self, track, pixmap, display_artist):
        area = self._available_area()
        if area is None:
            return
        corner = self._get("notifications.corner")
        window = self._ensure_window()
        window.move(self.position_for(area, corner))
        window.show_track(track.title, display_artist, track.album, pixmap,
                          duration_ms=self._get("notifications.duration_ms"),
                          from_above=corner.startswith("top"))

    def _ensure_window(self):
        if self._window is None:
            self._window = NotificationWindow()
            self._window.clicked.connect(self._restore_main_window)
        return self._window

    def _restore_main_window(self):
        mw = self._mw
        if mw.isMinimized():
            mw.showNormal()
        else:
            mw.show()
        mw.raise_()
        mw.activateWindow()
        if self._window is not None:
            self._window.hide_now()
