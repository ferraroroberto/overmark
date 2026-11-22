"""Ties ffmpeg's lifetime to the app's through a Windows job object.

Windows does not end a child when its parent dies, so an app that crashes or is killed
mid-recording would leave ffmpeg capturing for ever. One job object with kill-on-close
holds every ffmpeg the app starts; the OS closes its handle when the app's process ends
for any reason and ends everything inside. The clean "q" stop stays the normal path.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Any

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9  # JobObjectExtendedLimitInformation
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]  # fmt: skip


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32() -> Any:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
    ]  # fmt: skip
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel32


_job: int | None = None  # held until the process exits: closing it is what ends the children


def _job_handle(kernel32: Any) -> int | None:
    global _job
    if _job is not None:
        return _job
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        log.warning("⚠️ no job object (error %d)", ctypes.get_last_error())
        return None
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)
    )
    if not ok:
        log.warning("⚠️ job object limits not set (error %d)", ctypes.get_last_error())
        kernel32.CloseHandle(handle)
        return None
    _job = handle
    return _job


def contain(proc: Any) -> bool:
    """Put ``proc`` in the app's kill-on-close job; True if the OS now ends it with the app.

    Best effort: a failure is logged and the recording goes on, since the clean stop does
    not depend on it. A process without a real pid (a test double) is skipped.
    """
    pid = getattr(proc, "pid", None)
    if not IS_WINDOWS or not isinstance(pid, int):
        return False
    kernel32 = _kernel32()
    job = _job_handle(kernel32)
    if job is None:
        return False
    handle = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        log.warning("⚠️ ffmpeg (pid %d) not opened for the job (error %d)", pid, error)
        return False
    try:
        if not kernel32.AssignProcessToJobObject(job, handle):
            error = ctypes.get_last_error()
            log.warning("⚠️ ffmpeg (pid %d) not added to the job (error %d)", pid, error)
            return False
    finally:
        kernel32.CloseHandle(handle)
    log.info("ℹ️ ffmpeg (pid %d) will end with the app", pid)
    return True
