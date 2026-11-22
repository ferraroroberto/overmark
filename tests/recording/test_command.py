"""ffmpeg command lines for each setting combination, and the backend plans."""

from pathlib import Path

import pytest

from overmark.recording.command import (
    DDAGRAB,
    GDIGRAB,
    CapturePlan,
    SystemPart,
    capture_plans,
    concat_list,
    encoder_args,
    join_command,
    parse_anchor,
    parse_duration,
    segment_command,
)
from overmark.recording.monitors import Monitor

LEFT = Monitor("left", 0, 0, 1920, 1080, dda_index=0)
RIGHT = Monitor("right", 1920, 0, 2560, 1440, dda_index=1)
ABOVE = Monitor("above", 0, -1080, 1920, 1080, dda_index=2)
OTHER_GPU = Monitor("other", -1280, 0, 1280, 1024, dda_index=None)
OUT = Path("rec") / ".talk.part1.mkv"


def plan(**overrides) -> CapturePlan:
    values = dict(
        monitors=(LEFT,),
        backend=DDAGRAB,
        frame_rate=30,
        cursor=True,
        encoder="libx264",
        quality="medium",
    )
    values.update(overrides)
    return CapturePlan(**values)


def graph(cmd: list[str]) -> str:
    return cmd[cmd.index("-filter_complex") + 1]


def test_single_screen_ddagrab_uses_its_output_and_settings() -> None:
    cmd = segment_command("ffmpeg", plan(cursor=False, frame_rate=24), OUT)
    g = graph(cmd)
    assert g.startswith("ddagrab=output_idx=0:framerate=24:draw_mouse=0,hwdownload,format=bgra")
    assert "xstack" not in g
    assert cmd[-3:] == ["-f", "matroska", str(OUT)]
    assert "-n" in cmd, "ffmpeg must refuse to overwrite"
    assert ["-g", "48"] == cmd[cmd.index("-g") : cmd.index("-g") + 2]


def test_all_screens_are_stacked_at_their_desktop_positions() -> None:
    g = graph(segment_command("ffmpeg", plan(monitors=(LEFT, RIGHT, ABOVE)), OUT))
    for i, index in enumerate((0, 1, 2)):
        assert f"ddagrab=output_idx={index}:framerate=30:draw_mouse=1" in g
        assert f"[v{i}]" in g
    # The bounding box starts at the monitor above (y=-1080), so everything shifts down.
    assert "xstack=inputs=3:layout=0_1080|1920_1080|0_0:fill=black" in g


def test_odd_sizes_are_padded_to_even_and_converted_for_encoders() -> None:
    g = graph(segment_command("ffmpeg", plan(), OUT))
    assert g.endswith("pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p[vout]")


def test_gdigrab_crops_the_desktop_to_the_chosen_screens() -> None:
    cmd = segment_command("ffmpeg", plan(backend=GDIGRAB, monitors=(RIGHT,), cursor=False), OUT)
    joined = " ".join(cmd)
    assert "-f gdigrab -framerate 30 -draw_mouse 0" in joined
    assert "-offset_x 1920 -offset_y 0 -video_size 2560x1440 -i desktop" in joined
    assert graph(cmd).startswith("[0:v]")


def test_gdigrab_all_screens_covers_the_bounding_box() -> None:
    joined = " ".join(segment_command("ffmpeg", plan(backend=GDIGRAB, monitors=(LEFT, ABOVE)), OUT))
    assert "-offset_x 0 -offset_y -1080 -video_size 1920x2160" in joined


def test_no_microphone_means_no_audio_track() -> None:
    cmd = segment_command("ffmpeg", plan(), OUT)
    assert "dshow" not in cmd
    assert "-c:a" not in cmd


@pytest.mark.parametrize(
    ("backend", "audio_input"),
    [(DDAGRAB, "0:a"), (GDIGRAB, "1:a")],
)
def test_microphone_adds_one_audio_track(backend: str, audio_input: str) -> None:
    cmd = segment_command("ffmpeg", plan(backend=backend, microphone="Desk Mic (USB)"), OUT)
    assert "audio=Desk Mic (USB)" in cmd
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    maps = [cmd[i + 1] for i, part in enumerate(cmd) if part == "-map"]
    assert maps == ["[vout]", audio_input]


def test_webm_audio_is_opus() -> None:
    cmd = segment_command(
        "ffmpeg", plan(encoder="libvpx-vp9", microphone="Mic", container="webm"), OUT
    )
    assert cmd[cmd.index("-c:a") + 1] == "libopus"


def test_ddagrab_refuses_a_screen_it_cannot_reach() -> None:
    with pytest.raises(ValueError, match="ddagrab"):
        segment_command("ffmpeg", plan(monitors=(OTHER_GPU,)), OUT)


def test_unknown_backend_is_an_error() -> None:
    with pytest.raises(ValueError, match="backend"):
        segment_command("ffmpeg", plan(backend="dshow"), OUT)


@pytest.mark.parametrize(
    ("encoder", "medium_args"),
    [
        ("libx264", ["-preset", "veryfast", "-crf", "23"]),
        ("h264_nvenc", ["-preset", "p4", "-rc", "vbr", "-cq", "25", "-b:v", "0"]),
        ("h264_qsv", ["-preset", "veryfast", "-global_quality", "25"]),
        ("h264_amf", ["-quality", "balanced", "-rc", "cqp", "-qp_i", "25", "-qp_p", "25"]),
        ("libvpx-vp9", ["-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", "-crf", "33",
                        "-b:v", "0"]),
    ],
)  # fmt: skip
def test_quality_preset_per_encoder(encoder: str, medium_args: list[str]) -> None:
    assert encoder_args(encoder, "medium", 0) == medium_args


@pytest.mark.parametrize("encoder", ["libx264", "h264_nvenc", "h264_qsv", "h264_amf", "libvpx-vp9"])
def test_bitrate_overrides_the_quality_preset(encoder: str) -> None:
    args = encoder_args(encoder, "high", 6000)
    assert args[-2:] == ["-b:v", "6000k"]
    assert not {"-crf", "-cq", "-global_quality", "-qp_i"} & set(args)


def test_higher_quality_means_a_lower_quality_number() -> None:
    def value(q: str) -> int:
        return int(encoder_args("libx264", q, 0)[-1])

    assert value("high") < value("medium") < value("low")


def test_unknown_encoder_is_an_error() -> None:
    with pytest.raises(ValueError, match="encoder"):
        encoder_args("h265_magic", "medium", 0)


COMMON = dict(
    frame_rate=30,
    cursor=True,
    encoder="libx264",
    quality="medium",
    bitrate_kbps=0,
    microphone=None,
    container="mp4",
)


def test_auto_tries_ddagrab_then_gdigrab() -> None:
    plans = capture_plans([LEFT], "auto", **COMMON)
    assert [p.backend for p in plans] == [DDAGRAB, GDIGRAB]


def test_auto_goes_straight_to_gdigrab_for_a_screen_on_another_adapter() -> None:
    plans = capture_plans([LEFT, OTHER_GPU], "auto", **COMMON)
    assert [p.backend for p in plans] == [GDIGRAB]


def test_forced_backends() -> None:
    assert [p.backend for p in capture_plans([LEFT], "gdigrab", **COMMON)] == [GDIGRAB]
    assert [p.backend for p in capture_plans([LEFT], "ddagrab", **COMMON)] == [DDAGRAB]
    with pytest.raises(ValueError, match="adapter"):
        capture_plans([OTHER_GPU], "ddagrab", **COMMON)


def test_concat_list_quotes_paths_the_demuxer_way() -> None:
    plain, quoted = Path("a") / "one.mkv", Path("b") / "it's.mkv"
    escaped = str(quoted).replace("it's", "it'\\''s")
    assert concat_list([plain, quoted]).splitlines() == [
        f"file '{plain}'",
        f"file '{escaped}'",
    ]


@pytest.mark.parametrize(
    ("container", "muxer", "faststart"),
    [("mp4", "mp4", True), ("mkv", "matroska", False), ("webm", "webm", False)],
)
def test_join_copies_streams_into_the_chosen_container(
    container: str, muxer: str, faststart: bool
) -> None:
    cmd = join_command("ffmpeg", Path("list.txt"), container, Path(f".t.part.{container}"))
    assert ["-c", "copy"] == cmd[cmd.index("-c") : cmd.index("-c") + 2]
    assert cmd[-3:-1] == ["-f", muxer]
    assert ("-movflags" in cmd) is faststart
    assert "-n" in cmd


STAMP = "print(RTCTIME,24)"


@pytest.mark.parametrize("backend", [DDAGRAB, GDIGRAB])
def test_system_audio_stamps_the_first_frame_time_in_the_log(backend: str) -> None:
    on = graph(segment_command("ffmpeg", plan(backend=backend, system_audio=""), OUT))
    off = graph(segment_command("ffmpeg", plan(backend=backend), OUT))
    assert STAMP in on
    assert STAMP not in off


def test_system_audio_adds_no_input_to_the_segment() -> None:
    cmd = segment_command("ffmpeg", plan(system_audio=""), OUT)
    assert "-i" not in cmd
    assert "-c:a" not in cmd


def test_parse_anchor_reads_the_stamp_in_seconds() -> None:
    log = "[warn] noise\n[Eval @ 000000ab12] 1700000000250000.000000\n"
    assert parse_anchor(log) == pytest.approx(1_700_000_000.25)
    assert parse_anchor("nothing here") is None


def test_parse_duration_reads_the_header_line() -> None:
    header = "Input #0, matroska,webm, from 'x.mkv':\n  Duration: 01:02:03.45, start: 0.0\n"
    assert parse_duration(header) == pytest.approx(3723.45)
    assert parse_duration("no header") is None


PARTS = [
    SystemPart(Path("a.wav"), 0.4, 10.0),
    SystemPart(Path("b.wav"), -0.05, 5.5),
]


def audio_streams(cmd: list[str]) -> list[str]:
    """The output's audio sources: a copied input stream or the mixed filter output."""
    maps = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-map"]
    return [m for m in maps if m != "0:v"]


def test_join_with_neither_source_has_no_audio_to_mix() -> None:
    cmd = join_command("ffmpeg", Path("list.txt"), "mp4", Path(".t.part.mp4"))
    assert "-filter_complex" not in cmd
    assert audio_streams(cmd) == ["0"]  # copies what the segments hold: video only


def test_join_with_only_system_audio_has_one_track_from_the_wavs() -> None:
    cmd = join_command("ffmpeg", Path("list.txt"), "mp4", Path(".t.part.mp4"), system_parts=PARTS)
    g = graph(cmd)
    assert audio_streams(cmd) == ["[aout]"]
    assert ["-i", "a.wav", "-i", "b.wav"] == cmd[cmd.index("a.wav") - 1 : cmd.index("b.wav") + 1]
    assert "[1:a]atrim=start=0.400000,asetpts=PTS-STARTPTS," in g
    assert "[2:a]adelay=delays=50.000:all=1," in g
    assert "apad=whole_dur=10.000000,atrim=end=10.000000[s1]" in g
    assert "[s1][s2]concat=n=2:v=0:a=1[aout]" in g
    assert "amix" not in g
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-c:a") + 1] == "aac"


def test_join_with_microphone_and_system_audio_mixes_one_track() -> None:
    cmd = join_command(
        "ffmpeg",
        Path("list.txt"),
        "webm",
        Path(".t.part.webm"),
        system_parts=PARTS,
        microphone=True,
    )
    g = graph(cmd)
    assert audio_streams(cmd) == ["[aout]"]
    assert "[0:a][sys]amix=inputs=2:duration=first:normalize=0[aout]" in g
    assert cmd[cmd.index("-c:a") + 1] == "libopus"
