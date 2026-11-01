
import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

log = logging.getLogger(__name__)

WM_POWERBROADCAST = 0x0218
PBT_APMPOWERSTATUSCHANGE = 0x000A


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte),
                ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD)]


def on_battery(get_status=None):
    if get_status is None:
        if sys.platform != "win32":
            return False
        get_status = ctypes.windll.kernel32.GetSystemPowerStatus
    status = SYSTEM_POWER_STATUS()
    try:
        ok = get_status(ctypes.byref(status))
    except Exception:
        log.exception("could not read the power status")
        return False
    if not ok:
        log.warning("GetSystemPowerStatus failed; treating the PC as plugged in")
        return False
    return status.ACLineStatus == 0


class _PowerFilter(QAbstractNativeEventFilter):

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if (msg.message == WM_POWERBROADCAST
                and msg.wParam == PBT_APMPOWERSTATUSCHANGE):
            self._callback()
        return False, 0


class PowerWatcher(QObject):

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter = _PowerFilter(self.changed.emit)

    def install(self, app):
        from PySide6.QtGui import QGuiApplication
        if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
            return False
        app.installNativeEventFilter(self.filter)
        return True
