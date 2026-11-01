
import ctypes
import ctypes.wintypes as wintypes
import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger(__name__)

RESIZE_MARGIN = 6

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_CAPTION = 0x00C00000

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
SWP_FRAMECHANGED = 0x0020

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_GETMINMAXINFO = 0x0024

HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17

MONITOR_DEFAULTTONEAREST = 2


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", _POINT), ("ptMaxSize", _POINT),
                ("ptMaxPosition", _POINT), ("ptMinTrackSize", _POINT),
                ("ptMaxTrackSize", _POINT)]


class _MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def _prototyped_apis():
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.UINT]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
    dwmapi.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND,
                                                    ctypes.POINTER(_MARGINS)]
    return user32, dwmapi


class _Filter(QAbstractNativeEventFilter):

    def __init__(self, hwnd, user32):
        super().__init__()
        self._hwnd = hwnd
        self._user32 = user32

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.hWnd != self._hwnd:
            return False, 0
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            return True, 0
        if msg.message == WM_NCHITTEST:
            return self._hit_test(msg)
        if msg.message == WM_GETMINMAXINFO:
            self._fix_maximized_size(msg)
            return False, 0
        return False, 0

    def _hit_test(self, msg):
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        self._user32.GetWindowRect(self._hwnd, ctypes.byref(rect))
        left = x < rect.left + RESIZE_MARGIN
        right = x >= rect.right - RESIZE_MARGIN
        top = y < rect.top + RESIZE_MARGIN
        bottom = y >= rect.bottom - RESIZE_MARGIN
        if top and left:
            return True, HTTOPLEFT
        if top and right:
            return True, HTTOPRIGHT
        if bottom and left:
            return True, HTBOTTOMLEFT
        if bottom and right:
            return True, HTBOTTOMRIGHT
        if left:
            return True, HTLEFT
        if right:
            return True, HTRIGHT
        if top:
            return True, HTTOP
        if bottom:
            return True, HTBOTTOM
        return False, 0

    def _fix_maximized_size(self, msg):
        monitor = self._user32.MonitorFromWindow(self._hwnd, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            log.warning("MonitorFromWindow returned no monitor for hwnd %s; "
                        "a maximized window may cover the taskbar", self._hwnd)
            return
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not self._user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            log.warning("GetMonitorInfoW failed for hwnd %s; "
                        "a maximized window may cover the taskbar", self._hwnd)
            return
        work, mon = info.rcWork, info.rcMonitor
        mmi = _MINMAXINFO.from_address(msg.lParam)
        mmi.ptMaxPosition.x = work.left - mon.left
        mmi.ptMaxPosition.y = work.top - mon.top
        mmi.ptMaxSize.x = work.right - work.left
        mmi.ptMaxSize.y = work.bottom - work.top
        mmi.ptMaxTrackSize.x = work.right - work.left
        mmi.ptMaxTrackSize.y = work.bottom - work.top


def install(window):
    if sys.platform != "win32":
        return
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != "windows":
        return
    user32, dwmapi = _prototyped_apis()
    hwnd = int(window.winId())

    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_CAPTION)
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
                        | SWP_NOOWNERZORDER | SWP_FRAMECHANGED)

    margins = _MARGINS(1, 1, 1, 1)
    hresult = dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    if hresult != 0:
        log.warning("DwmExtendFrameIntoClientArea failed (HRESULT 0x%08X) for "
                    "hwnd %s; the window will have no native drop shadow",
                    hresult & 0xFFFFFFFF, hwnd)

    from PySide6.QtWidgets import QApplication
    filt = _Filter(hwnd, user32)
    QApplication.instance().installNativeEventFilter(filt)
    window._native_filter = filt
