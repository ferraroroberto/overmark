"""Thin ctypes wrappers for the few Win32 calls Qt does not expose.

Every function returns False (or 0) off Windows, so importing this module never
fails; the app itself is Windows-only.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010

ES_CONTINUOUS, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000002
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),  # ULONG_PTR
    ]


class _Input(ctypes.Structure):
    class _Union(ctypes.Union):
        _fields_ = [("mi", _MouseInput)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _Union)]


if IS_WINDOWS:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.SetThreadExecutionState.argtypes = [wintypes.DWORD]
    _kernel32.SetThreadExecutionState.restype = wintypes.DWORD
    _kernel32.GetTickCount.restype = wintypes.DWORD
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]


def _last_error() -> int:
    return ctypes.get_last_error() if IS_WINDOWS else 0


def register_hotkey(hotkey_id: int, modifiers: int, vk: int) -> bool:
    if not IS_WINDOWS:
        return False
    ok = bool(_user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk))
    if not ok:
        log.error("❌ RegisterHotKey failed (error %d): key already taken?", _last_error())
    return ok


def unregister_hotkey(hotkey_id: int) -> None:
    if IS_WINDOWS:
        _user32.UnregisterHotKey(None, hotkey_id)


def exclude_from_capture(hwnd: int) -> bool:
    """Hide a window from screen capture and recording; it stays visible on screen."""
    if not IS_WINDOWS:
        return False
    if not _user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
        log.warning("⚠️ SetWindowDisplayAffinity failed (error %d)", _last_error())
        return False
    value = wintypes.DWORD()
    _user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(value))
    return value.value == WDA_EXCLUDEFROMCAPTURE


def ex_style(hwnd: int) -> int:
    return int(_user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)) if IS_WINDOWS else 0


def set_click_through(hwnd: int, enabled: bool) -> bool:
    """Toggle mouse click-through without recreating the window (no flicker)."""
    if not IS_WINDOWS:
        return False
    style = ex_style(hwnd)
    new = (style | WS_EX_TRANSPARENT | WS_EX_LAYERED) if enabled else (style & ~WS_EX_TRANSPARENT)
    if new != style:
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new)
    return bool(ex_style(hwnd) & WS_EX_TRANSPARENT) == enabled


def set_no_activate(hwnd: int) -> None:
    """Clicking this window never steals keyboard focus from the drawing overlay."""
    if IS_WINDOWS:
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style(hwnd) | WS_EX_NOACTIVATE)


def foreground_window() -> int:
    return int(_user32.GetForegroundWindow() or 0) if IS_WINDOWS else 0


def set_foreground(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd or not _user32.IsWindow(hwnd):
        return False
    return bool(_user32.SetForegroundWindow(hwnd))


def bring_to_top(hwnd: int) -> None:
    """Raise a top-most window above other top-most windows without activating it."""
    if IS_WINDOWS:
        _user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        )


def hold_display_on(enabled: bool) -> bool:
    """Ask Windows to keep the display on (no screen saver, no display sleep), or release it.

    The request belongs to the calling thread, so call it from the Qt main thread only.
    """
    if not IS_WINDOWS:
        return False
    flags = ES_CONTINUOUS | ES_DISPLAY_REQUIRED if enabled else ES_CONTINUOUS
    return bool(_kernel32.SetThreadExecutionState(flags))


def idle_milliseconds() -> int | None:
    """Milliseconds since the last keyboard or mouse input, or None if it cannot be read."""
    if not IS_WINDOWS:
        return None
    info = _LastInputInfo(cbSize=ctypes.sizeof(_LastInputInfo))
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    return (int(_kernel32.GetTickCount()) - info.dwTime) & 0xFFFFFFFF


def move_pointer_by(dx: int, dy: int) -> bool:
    """Send one relative mouse move through the input queue, as a real mouse would."""
    if not IS_WINDOWS:
        return False
    event = _Input(type=INPUT_MOUSE)
    event.mi = _MouseInput(dx=dx, dy=dy, dwFlags=MOUSEEVENTF_MOVE)
    return _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_Input)) == 1


def nudge_pointer(distance_px: int) -> bool:
    """Move the pointer ``distance_px`` to the right and straight back."""
    return move_pointer_by(distance_px, 0) and move_pointer_by(-distance_px, 0)


def hotkey_id_from_msg(message: int) -> int:
    """Return the hotkey id if ``message`` points at a WM_HOTKEY MSG, else -1."""
    if not IS_WINDOWS or not message:
        return -1
    msg = wintypes.MSG.from_address(message)
    return int(msg.wParam) if msg.message == WM_HOTKEY else -1
