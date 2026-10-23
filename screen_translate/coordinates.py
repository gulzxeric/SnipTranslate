"""Translate UI Automation's physical coordinates into Qt screen coordinates."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD),
                ("device", wintypes.WCHAR * 32)]


def physical_to_logical(point: QPoint) -> QPoint:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    monitor = user32.MonitorFromPoint(wintypes.POINT(point.x(), point.y()), 2)
    info = _MonitorInfo()
    info.size = ctypes.sizeof(info)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise RuntimeError("无法读取工具栏所在显示器。")
    screen = next((s for s in QApplication.screens() if s.name().lower() == info.device.lower()), None)
    if screen is None:
        raise RuntimeError("无法匹配工具栏所在显示器。")
    geometry = screen.geometry()
    width = info.monitor.right - info.monitor.left
    height = info.monitor.bottom - info.monitor.top
    return QPoint(round(geometry.x() + (point.x() - info.monitor.left) * geometry.width() / width),
                  round(geometry.y() + (point.y() - info.monitor.top) * geometry.height() / height))
