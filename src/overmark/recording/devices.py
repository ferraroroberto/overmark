"""What this machine's ffmpeg offers: where it is, which encoder works, which microphones.

Pure: the ffmpeg runs are injected, so the choices are unit-testable.
"""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"

# Hardware first: they leave the CPU to the presentation. A listed hardware encoder
# can still fail (no such GPU, old driver), so each one is test-encoded before use.
H264_ENCODERS = ("h264_nvenc", "h264_qsv", "h264_amf", "libx264")
VP9_ENCODERS = ("libvpx-vp9",)

_DSHOW_DEVICE = re.compile(r'"(?P<name>[^"]+)"\s+\((?P<kind>audio|video)\)')


def find_ffmpeg(configured: str, which: Callable[[str], str | None] = shutil.which) -> str | None:
    """The configured ffmpeg if it exists, else ffmpeg on PATH, else None."""
    if configured:
        path = Path(configured)
        if path.is_dir():
            path = path / "ffmpeg.exe"
        if path.is_file():
            return str(path)
        log.warning("⚠️ recording.ffmpeg_path does not point at ffmpeg; trying PATH")
    return which("ffmpeg")


def encoder_candidates(container: str) -> tuple[str, ...]:
    return VP9_ENCODERS if container == "webm" else H264_ENCODERS


def encoder_test_command(ffmpeg: str, encoder: str) -> list[str]:
    """Encode one synthetic frame; exit code 0 means the encoder really runs here."""
    return [
        ffmpeg, "-hide_banner", "-v", "error",
        "-f", "lavfi", "-i", "color=black:s=256x256:r=30",
        "-frames:v", "1", "-c:v", encoder, "-f", "null", "-",
    ]  # fmt: skip


class EncoderPicker:
    """Picks the first working encoder per container, testing each one once per run."""

    def __init__(self, works: Callable[[str], bool]) -> None:
        self._works = works
        self._tested: dict[str, bool] = {}

    def pick(self, container: str) -> str:
        for encoder in encoder_candidates(container):
            if encoder not in self._tested:
                self._tested[encoder] = self._works(encoder)
                log.info(
                    "ℹ️ encoder %s %s", encoder, "works" if self._tested[encoder] else "unavailable"
                )
            if self._tested[encoder]:
                return encoder
        raise RuntimeError(f"no working encoder for {container} in this ffmpeg build")


def list_devices_command(ffmpeg: str) -> list[str]:
    return [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]


def parse_audio_devices(output: str) -> list[str]:
    """Audio device names from ``ffmpeg -list_devices true -f dshow`` (it exits non-zero)."""
    names = []
    for line in output.splitlines():
        if "Alternative name" in line:
            continue
        match = _DSHOW_DEVICE.search(line)
        if match and match["kind"] == "audio" and match["name"] not in names:
            names.append(match["name"])
    return names
