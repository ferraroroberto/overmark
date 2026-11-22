"""Builds the ffmpeg command lines: one per segment, plus the join on stop."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from overmark.recording.monitors import Monitor, bounding_box

DDAGRAB = "ddagrab"
GDIGRAB = "gdigrab"

# Quality preset to each encoder's constant-quality value: lower is better. Picked so
# "medium" keeps slide text crisp after a video-call upload, "low" for long sessions.
_QUALITY = {
    "libx264": {"low": 28, "medium": 23, "high": 18},
    "h264_nvenc": {"low": 30, "medium": 25, "high": 19},
    "h264_qsv": {"low": 30, "medium": 25, "high": 20},
    "h264_amf": {"low": 30, "medium": 25, "high": 19},
    "libvpx-vp9": {"low": 40, "medium": 33, "high": 28},
}
AUDIO_BITRATE = "160k"
DSHOW_QUEUE = "1024"  # packets buffered from the microphone while the video input starts


@dataclass(frozen=True)
class CapturePlan:
    """Everything one segment needs; every segment of a recording uses the same plan."""

    monitors: tuple[Monitor, ...]
    backend: str  # DDAGRAB or GDIGRAB, already resolved from "auto"
    frame_rate: int
    cursor: bool
    encoder: str
    quality: str
    bitrate_kbps: int = 0
    microphone: str | None = None  # DirectShow device name, or None for no audio
    system_audio: str | None = None  # loopback device name ("" = default), None for off
    container: str = "mp4"  # the joined file's container; segments are always MKV


def capture_plans(
    monitors: list[Monitor],
    backend: str,
    *,
    frame_rate: int,
    cursor: bool,
    encoder: str,
    quality: str,
    bitrate_kbps: int,
    microphone: str | None,
    container: str,
    system_audio: str | None = None,
) -> list[CapturePlan]:
    """Plans to try in order for the ``backend`` setting (``auto``, ``ddagrab``, ``gdigrab``).

    ``auto`` prefers ddagrab (GPU duplication, light on the CPU) and falls back to
    gdigrab, also when a chosen monitor sits on an adapter ddagrab cannot reach.
    """

    def plan(kind: str) -> CapturePlan:
        return CapturePlan(
            monitors=tuple(monitors),
            backend=kind,
            frame_rate=frame_rate,
            cursor=cursor,
            encoder=encoder,
            quality=quality,
            bitrate_kbps=bitrate_kbps,
            microphone=microphone,
            system_audio=system_audio,
            container=container,
        )

    reachable = all(m.dda_index is not None for m in monitors)
    if backend == GDIGRAB:
        return [plan(GDIGRAB)]
    if backend == DDAGRAB:
        if not reachable:
            raise ValueError("a chosen screen is on a graphics adapter ddagrab cannot capture")
        return [plan(DDAGRAB)]
    return [plan(DDAGRAB), plan(GDIGRAB)] if reachable else [plan(GDIGRAB)]


def encoder_args(encoder: str, quality: str, bitrate_kbps: int) -> list[str]:
    """Rate control for ``encoder``: the quality preset, or a fixed bitrate when set."""
    if encoder not in _QUALITY:
        raise ValueError(f"unknown encoder {encoder!r}")
    rate = f"{bitrate_kbps}k"
    q = str(_QUALITY[encoder][quality])
    if encoder == "libx264":
        tail = ["-b:v", rate] if bitrate_kbps else ["-crf", q]
        return ["-preset", "veryfast", *tail]
    if encoder == "h264_nvenc":
        tail = ["-b:v", rate] if bitrate_kbps else ["-cq", q, "-b:v", "0"]
        return ["-preset", "p4", "-rc", "vbr", *tail]
    if encoder == "h264_qsv":
        tail = ["-b:v", rate] if bitrate_kbps else ["-global_quality", q]
        return ["-preset", "veryfast", *tail]
    if encoder == "h264_amf":
        tail = ["-b:v", rate] if bitrate_kbps else ["-rc", "cqp", "-qp_i", q, "-qp_p", q]
        return ["-quality", "balanced", *tail]
    tail = ["-b:v", rate] if bitrate_kbps else ["-crf", q, "-b:v", "0"]  # libvpx-vp9
    return ["-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1", *tail]


def audio_codec(container: str) -> str:
    return "libopus" if container == "webm" else "aac"


# Encoders need even dimensions; a black edge pixel beats a failed recording.
_FINISH = "pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p[vout]"
# Logs the wall-clock time (microseconds) of the segment's first frame, which is time 0
# of its video: the anchor that lines the system-audio WAV up with the picture.
_STAMP = "setpts='PTS+0*if(eq(N,0),print(RTCTIME,24),0)',"


def _finish(plan: CapturePlan) -> str:
    return (_STAMP if plan.system_audio is not None else "") + _FINISH


def _ddagrab_graph(plan: CapturePlan) -> str:
    mouse = 1 if plan.cursor else 0
    chains = []
    for i, m in enumerate(plan.monitors):
        if m.dda_index is None:
            raise ValueError(f"{m.name} cannot be captured with ddagrab")
        chains.append(
            f"ddagrab=output_idx={m.dda_index}:framerate={plan.frame_rate}:draw_mouse={mouse},"
            f"hwdownload,format=bgra[v{i}]"
        )
    if len(plan.monitors) == 1:
        chains.append(f"[v0]{_finish(plan)}")
    else:
        left, top, _w, _h = bounding_box(list(plan.monitors))
        layout = "|".join(f"{m.x - left}_{m.y - top}" for m in plan.monitors)
        inputs = "".join(f"[v{i}]" for i in range(len(plan.monitors)))
        chains.append(
            f"{inputs}xstack=inputs={len(plan.monitors)}:layout={layout}:fill=black,"
            + _finish(plan)
        )
    return ";".join(chains)


def segment_command(ffmpeg: str, plan: CapturePlan, out: Path) -> list[str]:
    """One recording segment into ``out`` (MKV). ffmpeg stops cleanly on ``q`` at stdin."""
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-n"]
    if plan.backend == GDIGRAB:
        x, y, w, h = bounding_box(list(plan.monitors))
        cmd += [
            "-f", "gdigrab", "-framerate", str(plan.frame_rate),
            "-draw_mouse", "1" if plan.cursor else "0",
            "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}",
            "-i", "desktop",
        ]  # fmt: skip
        graph = f"[0:v]{_finish(plan)}"
        audio_input = 1
    elif plan.backend == DDAGRAB:
        graph = _ddagrab_graph(plan)
        audio_input = 0  # ddagrab sources live inside the filter graph, not as inputs
    else:
        raise ValueError(f"unknown capture backend {plan.backend!r}")

    if plan.microphone:
        cmd += [
            "-thread_queue_size", DSHOW_QUEUE,
            "-f", "dshow", "-i", f"audio={plan.microphone}",
        ]  # fmt: skip
    cmd += ["-filter_complex", graph, "-map", "[vout]"]
    cmd += ["-c:v", plan.encoder, *encoder_args(plan.encoder, plan.quality, plan.bitrate_kbps)]
    cmd += ["-g", str(plan.frame_rate * 2)]  # a keyframe every 2 s keeps seeking quick
    if plan.microphone:
        cmd += [
            "-map", f"{audio_input}:a",
            "-c:a", audio_codec(plan.container), "-b:a", AUDIO_BITRATE,
        ]  # fmt: skip
    cmd += ["-f", "matroska", str(out)]
    return cmd


_MUXERS = {"mp4": "mp4", "mkv": "matroska", "webm": "webm"}
_ANCHOR = re.compile(r"\[Eval @ [^\]]+\] (?P<us>\d+(?:\.\d+)?)")
_DURATION = re.compile(r"Duration: (?P<h>\d+):(?P<m>\d\d):(?P<s>\d\d(?:\.\d+)?)")


def parse_anchor(log_text: str) -> float | None:
    """The first frame's wall-clock time in seconds, from the stamp in a segment log."""
    match = _ANCHOR.search(log_text)
    return float(match["us"]) / 1_000_000 if match else None


def probe_command(ffmpeg: str, path: Path) -> list[str]:
    """Prints the file's header, Duration included, then exits non-zero (no output)."""
    return [ffmpeg, "-hide_banner", "-i", str(path)]


def parse_duration(output: str) -> float | None:
    """Seconds from ffmpeg's ``Duration: HH:MM:SS.cc`` line: what the concat join uses."""
    match = _DURATION.search(output)
    if not match:
        return None
    return int(match["h"]) * 3600 + int(match["m"]) * 60 + float(match["s"])


def concat_list(segments: list[Path]) -> str:
    """The concat demuxer's list file; single quotes in a path are escaped its way."""
    lines = []
    for path in segments:
        quoted = str(path).replace("'", "'\\''")
        lines.append(f"file '{quoted}'")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class SystemPart:
    """One segment's system-audio WAV: ``offset_s`` is the segment's first video frame,
    measured from the WAV's first sample (negative if the WAV started after it), and
    ``duration_s`` the segment's video length, which the audio is cut or padded to.
    """

    wav: Path
    offset_s: float
    duration_s: float


def _system_chain(index: int, part: SystemPart) -> str:
    if part.offset_s >= 0:
        align = f"atrim=start={part.offset_s:.6f},asetpts=PTS-STARTPTS"
    else:
        align = f"adelay=delays={-part.offset_s * 1000:.3f}:all=1"
    length = f"{part.duration_s:.6f}"
    return f"[{index}:a]{align},apad=whole_dur={length},atrim=end={length}[s{index}]"


def system_audio_graph(parts: list[SystemPart], microphone: bool) -> str:
    """Each WAV lined up with its segment, the parts joined, then mixed with the mic."""
    chains = [_system_chain(i + 1, part) for i, part in enumerate(parts)]
    labels = "".join(f"[s{i + 1}]" for i in range(len(parts)))
    joined = "[aout]" if not microphone else "[sys]"
    chains.append(f"{labels}concat=n={len(parts)}:v=0:a=1{joined}")
    if microphone:
        # normalize=0 keeps both at full level; amix's default halves each input.
        chains.append("[0:a][sys]amix=inputs=2:duration=first:normalize=0[aout]")
    return ";".join(chains)


def join_command(
    ffmpeg: str,
    list_file: Path,
    container: str,
    out: Path,
    *,
    system_parts: list[SystemPart] | None = None,
    microphone: bool = False,
) -> list[str]:
    """Join the segments into the chosen container. Video is always copied; with system
    audio the audio is mixed and re-encoded, otherwise everything is copied.
    """
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-n",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
    ]  # fmt: skip
    if system_parts:
        for part in system_parts:
            cmd += ["-i", str(part.wav)]
        cmd += [
            "-filter_complex", system_audio_graph(system_parts, microphone),
            "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
            "-c:a", audio_codec(container), "-b:a", AUDIO_BITRATE,
        ]  # fmt: skip
    else:
        cmd += ["-map", "0", "-c", "copy"]
    if container == "mp4":
        cmd += ["-movflags", "+faststart"]
    return [*cmd, "-f", _MUXERS[container], str(out)]
