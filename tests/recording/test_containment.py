"""ffmpeg must not outlive the app: kill the parent mid-recording and the child must go."""

import ctypes
import os
import subprocess
import sys
import textwrap
from ctypes import wintypes
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="job objects are Windows-only")

SYNCHRONIZE = 0x00100000
PROCESS_TERMINATE = 0x0001
WAIT_OBJECT_0 = 0
GONE_WITHIN_MS = 5000

# The parent drives the real Recorder with a real Popen, swapping only the command for a
# long sleep, so the spawn and its containment are exactly the session's own.
PARENT = textwrap.dedent(
    """
    import subprocess, sys, time
    from pathlib import Path
    from overmark.recording.command import DDAGRAB, CapturePlan
    from overmark.recording.monitors import Monitor
    from overmark.recording.session import Recorder

    def popen(cmd, **kwargs):
        return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], **kwargs)

    screen = Monitor("screen", 0, 0, 1280, 720, dda_index=0)
    plan = CapturePlan(
        monitors=(screen,), backend=DDAGRAB, frame_rate=30, cursor=True,
        encoder="libx264", quality="medium", container="mp4",
    )
    rec = Recorder("ffmpeg", [plan], Path(sys.argv[1]) / "talk.mp4", popen=popen,
                   startup_grace_s=0.2)
    rec.start()
    print(rec._proc.pid, flush=True)
    time.sleep(600)
    """
)


def _kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel32


def test_child_ends_when_the_parent_is_killed_mid_recording(tmp_path: Path) -> None:
    kernel32 = _kernel32()
    script = tmp_path / "parent.py"
    script.write_text(PARENT, encoding="utf-8")
    src = str(Path(__file__).resolve().parents[2] / "src")
    parent = subprocess.Popen(
        [sys.executable, str(script), str(tmp_path)],
        stdout=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env={**os.environ, "PYTHONPATH": src},
    )
    child = None
    try:
        line = parent.stdout.readline()
        assert line, "the parent never reported its child"
        child_pid = int(line)
        # Held before the kill, so the wait cannot be fooled by a reused pid.
        child = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_TERMINATE, False, child_pid)
        assert child, "the child was not running"
        assert kernel32.WaitForSingleObject(child, 0) != WAIT_OBJECT_0

        parent.kill()
        parent.wait(timeout=10)

        assert kernel32.WaitForSingleObject(child, GONE_WITHIN_MS) == WAIT_OBJECT_0
    finally:
        if child:
            kernel32.TerminateProcess(child, 1)  # only the child this test started
            kernel32.CloseHandle(child)
        if parent.poll() is None:
            parent.kill()
        parent.stdout.close()
        parent.wait(timeout=10)
