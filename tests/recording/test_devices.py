"""ffmpeg discovery: the configured path, encoder fallback, and the microphone list."""

from pathlib import Path

import pytest

from overmark.recording.devices import (
    EncoderPicker,
    encoder_candidates,
    find_ffmpeg,
    parse_audio_devices,
)

# Shape of `ffmpeg -list_devices true -f dshow -i dummy` output, with invented names.
DSHOW_LISTING = """\
[dshow @ 0000020000000000] "Studio Camera" (video)
[dshow @ 0000020000000000]   Alternative name "@device_pnp_\\\\?\\usb#vid_0000"
[dshow @ 0000020000000000] "Desk Mic (USB Audio)" (audio)
[dshow @ 0000020000000000]   Alternative name "@device_cm_{00000000}\\wave_{11111111}"
[dshow @ 0000020000000000] "Micrófono (Headset)" (audio)
[dshow @ 0000020000000000]   Alternative name "@device_cm_{00000000}\\wave_{22222222}"
dummy: Immediate exit requested
"""


def test_audio_devices_are_listed_without_video_or_alternative_names() -> None:
    assert parse_audio_devices(DSHOW_LISTING) == ["Desk Mic (USB Audio)", "Micrófono (Headset)"]


def test_no_devices_gives_an_empty_list() -> None:
    assert parse_audio_devices("Error opening input file dummy.") == []


def test_configured_ffmpeg_file_wins(tmp_path: Path) -> None:
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"")
    assert find_ffmpeg(str(exe), which=lambda _n: "elsewhere") == str(exe)


def test_configured_folder_finds_ffmpeg_inside(tmp_path: Path) -> None:
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    assert find_ffmpeg(str(tmp_path), which=lambda _n: None) == str(tmp_path / "ffmpeg.exe")


def test_missing_configured_ffmpeg_falls_back_to_path(tmp_path: Path) -> None:
    assert find_ffmpeg(str(tmp_path / "nope.exe"), which=lambda _n: "on-path") == "on-path"


def test_no_ffmpeg_anywhere_is_none() -> None:
    assert find_ffmpeg("", which=lambda _n: None) is None


def test_picker_takes_the_first_hardware_encoder_that_works() -> None:
    tried = []

    def works(encoder: str) -> bool:
        tried.append(encoder)
        return encoder == "h264_qsv"

    picker = EncoderPicker(works)
    assert picker.pick("mp4") == "h264_qsv"
    assert picker.pick("mkv") == "h264_qsv"
    assert tried == ["h264_nvenc", "h264_qsv"], "each encoder is tested once per run"


def test_picker_falls_back_to_software() -> None:
    picker = EncoderPicker(lambda encoder: encoder == "libx264")
    assert picker.pick("mp4") == "libx264"


def test_webm_uses_vp9() -> None:
    assert encoder_candidates("webm") == ("libvpx-vp9",)
    assert EncoderPicker(lambda _e: True).pick("webm") == "libvpx-vp9"


def test_no_working_encoder_is_an_error() -> None:
    with pytest.raises(RuntimeError, match="no working encoder"):
        EncoderPicker(lambda _e: False).pick("mp4")
