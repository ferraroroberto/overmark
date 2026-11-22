"""Builds the ffmpeg command lines: one per segment, plus the join on stop."""

from __future__ import annotations

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
        chains.append(f"[v0]{_FINISH}")
    else:
        left, top, _w, _h = bounding_box(list(plan.monitors))
        layout = "|".join(f"{m.x - left}_{m.y - top}" for m in plan.monitors)
        inputs = "".join(f"[v{i}]" for i in range(len(plan.monitors)))
        chains.append(
            f"{inputs}xstack=inputs={len(plan.monitors)}:layout={layout}:fill=black,{_FINISH}"
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
        graph = f"[0:v]{_FINISH}"
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


def concat_list(segments: list[Path]) -> str:
    """The concat demuxer's list file; single quotes in a path are escaped its way."""
    lines = []
    for path in segments:
        quoted = str(path).replace("'", "'\\''")
        lines.append(f"file '{quoted}'")
    return "\n".join(lines) + "\n"


def join_command(ffmpeg: str, list_file: Path, container: str, out: Path) -> list[str]:
    """Join the segments without re-encoding into the chosen container."""
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-n",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-map", "0", "-c", "copy",
    ]  # fmt: skip
    if container == "mp4":
        cmd += ["-movflags", "+faststart"]
    return [*cmd, "-f", _MUXERS[container], str(out)]
