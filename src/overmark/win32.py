"""Thin ctypes wrappers for the few Win32 calls Qt does not expose.

Every function returns False (or 0) off Windows, so importing this module never
fails; the app itself is Windows-only.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from overmark.recording.monitors import Monitor

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WDA_NONE = 0x00000000
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


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


class _OutputDesc(ctypes.Structure):
    """DXGI_OUTPUT_DESC."""

    _fields_ = [
        ("DeviceName", wintypes.WCHAR * 32),
        ("DesktopCoordinates", wintypes.RECT),
        ("AttachedToDesktop", wintypes.BOOL),
        ("Rotation", ctypes.c_uint),
        ("Monitor", wintypes.HMONITOR),
    ]


# IID_IDXGIFactory1 {770aae78-f26f-4dba-a829-253c83d1b387}
_IID_DXGI_FACTORY1 = _Guid(
    0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87)
)
# COM vtable slots: IUnknown::Release, then IDXGIFactory::EnumAdapters,
# IDXGIAdapter::EnumOutputs and IDXGIOutput::GetDesc, each the first method after
# IUnknown's 3 and IDXGIObject's 4.
_RELEASE, _ENUM_ADAPTERS, _ENUM_OUTPUTS, _OUTPUT_GET_DESC = 2, 7, 7, 7


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
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
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


def set_capture_excluded(hwnd: int, excluded: bool) -> bool:
    """Turn capture exclusion on or off for a window that is normally captured (the ink)."""
    if not IS_WINDOWS:
        return False
    affinity = WDA_EXCLUDEFROMCAPTURE if excluded else WDA_NONE
    if not _user32.SetWindowDisplayAffinity(hwnd, affinity):
        log.warning("⚠️ SetWindowDisplayAffinity(%#x) failed (error %d)", affinity, _last_error())
        return False
    value = wintypes.DWORD()
    _user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(value))
    return value.value == affinity


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


def cursor_position() -> tuple[int, int] | None:
    """The pointer in physical desktop pixels (the app is per-monitor DPI aware)."""
    if not IS_WINDOWS:
        return None
    point = wintypes.POINT()
    if not _user32.GetCursorPos(ctypes.byref(point)):
        return None
    return point.x, point.y


def _com_call(obj: ctypes.c_void_p, slot: int, *argtypes):
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[slot])


def _release(obj: ctypes.c_void_p) -> None:
    if obj:
        _com_call(obj, _RELEASE)(obj)


def _adapter_outputs(adapter: ctypes.c_void_p, adapter_no: int) -> list[Monitor]:
    out_ptr = ctypes.POINTER(ctypes.c_void_p)
    monitors = []
    output_no = 0
    while True:
        output = ctypes.c_void_p()
        enum_outputs = _com_call(adapter, _ENUM_OUTPUTS, ctypes.c_uint, out_ptr)
        if enum_outputs(adapter, output_no, ctypes.byref(output)) != 0:
            return monitors
        desc = _OutputDesc()
        get_desc = _com_call(output, _OUTPUT_GET_DESC, ctypes.POINTER(_OutputDesc))
        ok = get_desc(output, ctypes.byref(desc)) == 0
        _release(output)
        rect = desc.DesktopCoordinates
        if ok and desc.AttachedToDesktop:
            monitors.append(
                Monitor(
                    name=desc.DeviceName,
                    x=rect.left,
                    y=rect.top,
                    width=rect.right - rect.left,
                    height=rect.bottom - rect.top,
                    dda_index=output_no if adapter_no == 0 else None,
                )
            )
        output_no += 1


def display_outputs() -> list[Monitor]:
    """Every desktop output, in DXGI order, with its position in physical pixels.

    ffmpeg's ``ddagrab`` numbers the default adapter's outputs in this same order, so
    an output of adapter 0 gets its ``dda_index``; outputs on other adapters get None.
    """
    if not IS_WINDOWS:
        return []
    try:
        dxgi = ctypes.WinDLL("dxgi")
    except OSError:
        log.warning("⚠️ dxgi.dll not available; monitors unknown")
        return []
    factory = ctypes.c_void_p()
    if dxgi.CreateDXGIFactory1(ctypes.byref(_IID_DXGI_FACTORY1), ctypes.byref(factory)) != 0:
        log.warning("⚠️ CreateDXGIFactory1 failed; monitors unknown")
        return []
    monitors: list[Monitor] = []
    try:
        adapter_no = 0
        while True:
            adapter = ctypes.c_void_p()
            enum_adapters = _com_call(
                factory, _ENUM_ADAPTERS, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)
            )
            if enum_adapters(factory, adapter_no, ctypes.byref(adapter)) != 0:
                return monitors
            try:
                monitors += _adapter_outputs(adapter, adapter_no)
            finally:
                _release(adapter)
            adapter_no += 1
    finally:
        _release(factory)
