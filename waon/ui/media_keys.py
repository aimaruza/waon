
import ctypes
import ctypes.wintypes as wintypes
import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000

_KEYS = {
    1: (0xB3, "Play/Pause", "playPause"),
    2: (0xB0, "Next", "next"),
    3: (0xB1, "Previous", "previous"),
    4: (0xB2, "Stop", "stop"),
}


def _prototyped_user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                      wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    return user32


class _Filter(QAbstractNativeEventFilter):

    def __init__(self, hwnd, on_hotkey):
        super().__init__()
        self._hwnd = hwnd
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.hWnd != self._hwnd or msg.message != WM_HOTKEY:
            return False, 0
        return self._on_hotkey(msg.wParam), 0


class MediaKeys(QObject):
    playPause = Signal()
    next = Signal()
    previous = Signal()
    stop = Signal()

    def __init__(self, parent=None, user32=None, last_error=None):
        super().__init__(parent)
        self._user32 = user32
        self._last_error = last_error or ctypes.get_last_error
        self._hwnd = None
        self._registered = []
        self._filter = None

    def install(self, window):
        if self._hwnd is not None:
            return
        if self._user32 is None:
            if sys.platform != "win32":
                log.debug("media keys: not on Windows, nothing to claim")
                return
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.platformName() != "windows":
                log.debug("media keys: %s platform has no real HWND, "
                          "nothing to claim", QGuiApplication.platformName())
                return
            self._user32 = _prototyped_user32()
        self._hwnd = int(window.winId())
        for hotkey_id, (vk, name, _signal) in _KEYS.items():
            if self._user32.RegisterHotKey(self._hwnd, hotkey_id,
                                           MOD_NOREPEAT, vk):
                self._registered.append(hotkey_id)
            else:
                log.warning("could not claim the %s media key (error %s); "
                            "another app probably owns it", name,
                            self._last_error())
        if not self._registered:
            return
        from PySide6.QtWidgets import QApplication
        self._filter = _Filter(self._hwnd, self._on_hotkey)
        QApplication.instance().installNativeEventFilter(self._filter)
        log.debug("media keys claimed: %s", ", ".join(
            _KEYS[i][1] for i in self._registered))

    def uninstall(self):
        if self._filter is not None:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
            self._filter = None
        for hotkey_id in self._registered:
            if not self._user32.UnregisterHotKey(self._hwnd, hotkey_id):
                log.warning("could not release the %s media key (error %s)",
                            _KEYS[hotkey_id][1], self._last_error())
        self._registered = []

    def _on_hotkey(self, hotkey_id):
        if hotkey_id not in self._registered:
            return False
        getattr(self, _KEYS[hotkey_id][2]).emit()
        return True
