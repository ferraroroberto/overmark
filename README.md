# Overmark

Screen annotation for live facilitation: draw on any screen (pen, highlighter, arrow, text, laser) while the toolbar stays out of the capture, so an audience sees only the ink.

> **Name.** "Overmark" is a working name. A trademark and store-name check is still pending; do not treat it as final.

**Status:** MVP. Python with PySide6, chosen by the step-0 probe ([docs/probe-results.md](docs/probe-results.md)); the on-screen latency, OBS Display Capture and pen checks listed there are still owed on real hardware. Later steps are issues in this repo's tracker.

## What it does

- A tray app with one global hotkey (`Ctrl+Alt+D` by default, rebindable in Settings) that toggles between drawing and click-through. Ink stays visible while you click through to the application underneath.
- Every monitor at once: one transparent overlay per screen, sharing one drawing in desktop coordinates, so a stroke can cross from one monitor to the next.
- Tools: pen, highlighter (translucent, drawn under other ink), arrow, text label (click, type, `Enter`; `Shift+Enter` for a new line), laser (hold `L`: a dot with a short fading trail, never stored or undone, system cursor hidden), undo, clear.
- Seven presets (colour, thickness, transparency on/off and amount, outline on/off and thickness): keys `1` to `7`, or the mouse wheel over the toolbar.
- Fading is a setting: on or off plus a delay in seconds; strokes then ease out over about 0.6 s. `F` pins the ink on screen so it stops fading.
- The toolbar (a pill that collapses to a small handle and expands on hover), the cheat-sheet and the settings window are excluded from screen capture.
- Compression-safe defaults: widths in capture pixels (pen 6, highlighter 28, text 32, laser dot 18 with a 6 px halo), a dark outline on every stroke (a light one on dark ink), and a brightness-first palette with no pure red or blue.
- Keep-awake, off by default, for presentations and long sessions: a tray item and a toolbar button (☀) toggle it, the tray icon gets a green badge while it is armed. The default method asks Windows to keep the display on, so the pointer never moves; the alternative nudges the pointer 1 px and back after a whole interval of inactivity, and never while a stroke is drawn, a label typed or the laser held.
- Screen recording through ffmpeg (see [Recording](#recording)): all screens in one video, or one screen, with the toolbar, the recording chip and settings kept out of the video.
- Mouse, touch and pen share one input path; pen pressure varies the width and the pen's eraser end (or barrel button) erases whole strokes.

## Keys while drawing

| Key | Action |
|---|---|
| `P` / `H` / `A` / `T` | pen / highlighter / arrow / text |
| hold `L` | laser |
| `1` to `7` | preset |
| `Ctrl+Z` | undo |
| `E` | clear |
| `F` | pin ink (stop fading) |
| `?` | cheat-sheet |
| `Esc` | stop drawing (ink stays); a second `Esc` within a second clears |

Keys reach the app only while drawing, so they never collide with the application underneath. All of them are rebindable in `config.json` (`keys`); the draw hotkey is also rebindable in Settings.

## Configuration

`config.json` (git-ignored) is created from `config.sample.json` on first run. Settings saves it; you can also edit it by hand while the app is closed.

| Key | Meaning |
|---|---|
| `hotkey.toggle_draw` | global draw hotkey; needs `ctrl`, `alt` or `win` |
| `screens.cover_all` | `true`: draw on every monitor; `false`: primary monitor only |
| `fade.enabled`, `fade.delay_seconds` | fading on or off, and the delay before a stroke fades |
| `presets` | the seven presets: `color` (`#RRGGBB`), `thickness_px`, `transparency` (`enabled`, `percent`), `outline` (`enabled`, `thickness_px`) |
| `sizes` | highlighter, text and laser sizes in capture pixels |
| `keep_awake.enabled` | keep the display awake (default `false`) |
| `keep_awake.mode` | `execution_state` (ask Windows, pointer untouched; default) or `nudge` (move the pointer and back) |
| `keep_awake.interval_seconds` | nudge mode: idle seconds before a nudge, 5 to 3600 (default 60; Settings offers 30 and 60 or a free value) |
| `keep_awake.distance_px` | nudge mode: pixels moved out and back, 1 to 20 (default 1) |
| `keys` | the in-draw key for each action |
| `hotkey.record_toggle`, `hotkey.record_pause` | global recording hotkeys (default `ctrl+alt+f9`, `ctrl+alt+f10`) |
| `recording` | recording settings; see [Recording](#recording) |

Invalid values fall back to the default for that key, with a warning in the log. The log is `overmark.log` in the app's local data folder (`%LOCALAPPDATA%\Overmark\Overmark`), one line per drawing session.

## Recording

Recording needs [ffmpeg](https://ffmpeg.org/download.html) on `PATH` (or `recording.ffmpeg_path`); without it the tray says so. `Ctrl+Alt+F9` starts and stops, `Ctrl+Alt+F10` pauses and resumes; both are rebindable in Settings, which refuses a combo that clashes with another hotkey or an in-draw key. The tray menu has the same two items. While recording, a chip with a red dot and the elapsed time sits in the top-right corner of the recorded screen; like the toolbar, it never appears in the video.

| `recording` key | Meaning |
|---|---|
| `screen` | `all` (every monitor in one video, placed as on the desktop), `active` (the screen under the pointer at start) or a number from 1, counting screens left to right, then top to bottom |
| `folder` | destination; empty means the Videos folder plus `Overmark` |
| `name_pattern` | file name with `{date}`, `{time}`, `{screen}`; a taken name gets `-2`, `-3` and so on, never overwritten |
| `container` | `mp4` (H.264), `mkv` (H.264) or `webm` (VP9) |
| `quality`, `bitrate_kbps` | `low`, `medium` or `high`; a bitrate above 0 overrides the preset |
| `frame_rate` | 15, 24, 30 or 60 |
| `cursor`, `include_ink` | show the pointer; keep the ink in the video (off hides it for the length of the recording) |
| `microphone.enabled`, `microphone.device` | record one DirectShow microphone (picked in Settings) |
| `backend` | `auto` (GPU desktop duplication, falling back to GDI), `ddagrab` or `gdigrab` |
| `ffmpeg_path` | ffmpeg's location if it is not on `PATH` |

H.264 uses the first hardware encoder that passes a one-frame test (NVIDIA, Intel, AMD), else `libx264`. Pause ends a segment and resume starts the next; about a second around each pause is not recorded, and stop joins the segments into one file without re-encoding. While recording, the segments are `.<name>.part<N>.mkv` files in the destination folder, so an interrupted recording never looks finished; they can still be played or joined by hand. Each saved recording writes one log line with the screen choice, duration, size and encoder. If a hotkey does nothing, another application may be intercepting it even though registration succeeded; pick another combo. The capture checks behind this are in [docs/recording-probe.md](docs/recording-probe.md).

## Run

```powershell
powershell -File scripts/run.ps1            # tray app, no console
powershell -File scripts/run.ps1 -Console   # with the log in the console
```

## Verify

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
powershell -File scripts/verify-before-ship.ps1
```

The gate prints `GATE-RESULT: PASS` or `GATE-RESULT: FAIL (<stage>)`.

## Notes

- Capture behaviour depends on the OBS source type: Display Capture records the ink; Window Capture of another application does not.
- This repository is public: no screenshots, hostnames, usernames or machine paths in code, docs, issues or pull requests.

## License

MIT, see `LICENSE`.
