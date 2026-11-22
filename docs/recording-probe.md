# Recording probe: ddagrab and gdigrab

Recording drives ffmpeg as a child process. This page records the capture probe behind that choice: what each capture path does with the capture-excluded windows, the cursor switch, the ink switch and a multi-monitor layout. The probe scripts were throwaway and are not in the repository; the method below is enough to rebuild them.

**Verdict: keep ffmpeg `ddagrab` as the main path and `gdigrab` as the fallback.** Both passed every check that could be run here. `ddagrab` stays first because it duplicates the desktop on the GPU and leaves the CPU to the presentation.

## Test machine

- Windows 11, three 1080p monitors at 100 % scale: two side by side and one above the left one (so the desktop has negative coordinates and a gap).
- One discrete GPU. Its hardware H.264 encoder works; two other hardware encoders that ffmpeg lists (`h264_qsv`, `h264_amf`) fail at the first frame because their hardware is absent. A listed encoder is therefore test-encoded before use.
- ffmpeg 8.0 (a full build with `ddagrab`, `xstack`, NVENC, QSV, AMF, `libx264`, `libvpx-vp9`, `aac`, `libopus`).
- Unlocked desktop. PySide6 6.12 on Python 3.14.
- No mixed-DPI pair and no second graphics adapter.

## Method

- **Monitor map.** `ddagrab` names an output only by index and reports its size, not its position. The app enumerates DXGI outputs itself (`CreateDXGIFactory1`, `EnumAdapters`, `EnumOutputs`, `GetDesc`) in the same order ffmpeg uses, which gives each index its desktop rectangle in physical pixels. The three outputs here came back in an order different from left-to-right, so this mapping is needed.
- **Test windows.** Solid-colour, frameless, top-most windows: a magenta one with `WDA_EXCLUDEFROMCAPTURE` (standing in for the toolbar and the recording chip) and a green one without it (standing in for the ink).
- **Recording.** The app's own `Recorder` with each backend, 3 s at 30 fps, encoded with the hardware H.264 encoder, then joined into MP4.
- **Checks.** One frame extracted from the middle of each video; single pixels read with ffmpeg `crop` and compared with the window colours (tolerance 24 per channel for compression).

## Results

| Check | ddagrab | gdigrab |
|---|---|---|
| Capture-excluded window absent (desktop colour where it sits) | yes | yes |
| Normal window present (green read back as 0, 255, 0) | yes | yes |
| Cursor on: pixels beside the pointer's hotspot differ from the window under it | 8 of 9 | 8 of 9 |
| Cursor off: the same pixels | 0 of 9 | 0 of 9 |
| "Include ink: no" (exclusion flag set on the green window for the recording): green absent | yes | yes |
| All screens in one video: a coloured block on each monitor lands at its desktop position in the 3840×2160 frame | 3 of 3 | 3 of 3 |

Also checked:

- **Pause.** Two `ddagrab` segments joined without re-encoding into one MP4; no part files left.
- **Containers.** MP4 (H.264 + AAC), MKV (H.264), WebM (VP9 + Opus) each carry an audio track only when the microphone is on; frame rate 15 read back as 15.
- **Fallback.** A `ddagrab` output index that does not exist fails within the start check; `auto` then records with `gdigrab`.
- **Missing microphone.** ffmpeg exits at start on both backends; the user sees "the microphone was not found".
- **The app itself, driven by its global hotkeys.** Start, pause, resume and stop produced one MP4 of screen 1. The ink was excluded for the recording and restored afterwards, and the pixel where the recording chip's red dot sits was the desktop's colour, not red.

## Findings that changed the build

- **`Ctrl+Alt+R` is a poor default.** On the test machine another application already owned it; `RegisterHotKey` failed. `Ctrl+Alt+Shift+R` registered but was never delivered, because the other application's keyboard hook also swallows the shifted combo. A successful registration therefore does not prove a hotkey works. The defaults are `Ctrl+Alt+F9` (start/stop) and `Ctrl+Alt+F10` (pause/resume), which were delivered.
- **Segments are always MKV.** An MP4 whose encoder is killed has no index and does not play; an MKV segment does. Segments are joined into the chosen container only on a clean stop, so an interrupted recording leaves `.<name>.part<N>.mkv` files: plainly unfinished, still recoverable.

## Still unmeasured

- **Mixed DPI.** Positions come from DXGI in physical pixels and the app is per-monitor DPI aware, so `ddagrab` should line up; `gdigrab` scales with the desktop DPI and may not. Needs a pair of monitors at different scales.
- **A second graphics adapter.** `ddagrab` only reaches the default adapter's outputs; a screen on another adapter is routed to `gdigrab`. Not exercised.
- **Long recordings and 60 fps on all screens.** Only short runs were made; CPU and disk load over an hour at 3840×2160 is the owner's check.
- **System audio over 30 minutes.** Drift was measured over 5 minutes only (below); the 30-minute figure is an extrapolation, not a measurement.

## System audio

PyAudioWPatch captures the default output's WASAPI loopback into one WAV per segment; the join lines each WAV up with its segment and mixes it in. Measured with a harness that flashes a small on-screen square and plays a 1 kHz beep at the same moment, recorded through the real recorder (`ddagrab`, NVENC, 60 fps), then compared beep onsets with flash frames:

| Check | Result |
|---|---|
| Two pauses, three parts, a cue every second | 23 cues matched; audio 7 to 54 ms ahead of the picture (mean 26 ms) in every part |
| 5 minutes, a cue every 10 s | 30 of 30 matched; 17 to 57 ms ahead (mean 34 ms); fitted drift -1.3 ms per minute, so about -73 ms at 30 minutes if it stays linear (not measured) |
| Tracks (`ffprobe`) | system audio only: one AAC track; with the microphone: one mixed AAC track; both off: video only |

Findings that shaped the build:

- **WASAPI loopback delivers nothing while nothing plays.** An idle output gave zero callbacks, so chunks are placed on `perf_counter` rather than appended: a gap becomes silence, and audio more than 30 ms ahead of the clock is dropped. A WAV therefore always spans the wall-clock time it covers.
- **ffmpeg resets segment timestamps to zero**, also with `-copyts` for `ddagrab`, and its first frame lands 0.3 to 1.5 s after launch (longer with a DirectShow microphone). Each segment's filter graph therefore logs the wall-clock time of its first frame (`setpts` with `print(RTCTIME)`), which is the anchor the WAV is trimmed to.
- **Audio leads the picture by 20 to 40 ms.** That is the display path (render, present, capture) against the audio path; it is well inside the 100 ms budget, so no fixed correction is applied.
