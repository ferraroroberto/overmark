# Overmark

Screen annotation for live facilitation: draw on any screen (pen, highlighter, arrow, text, laser) while the toolbar stays out of the capture, so an audience sees only the ink.

> **Name.** "Overmark" is a working name. A trademark and store-name check is still pending; do not treat it as final.

**Status:** MVP. Python with PySide6, chosen by the step-0 probe ([docs/probe-results.md](docs/probe-results.md)); the on-screen latency, OBS Display Capture and pen checks listed there are still owed on real hardware. Later steps are issues in this repo's tracker.

## What it does

- A tray app with one global hotkey (`Ctrl+Alt+D` by default, rebindable in Settings) that toggles between drawing and click-through. Ink stays visible while you click through to the application underneath.
- Every monitor at once: one transparent overlay per screen, sharing one drawing in desktop coordinates, so a stroke can cross from one monitor to the next.
- Tools: pen, highlighter (translucent, drawn under other ink), arrow, text label (click, type, `Enter`; `Shift+Enter` for a new line), laser (hold `L`: a dot with a short fading trail, never stored or undone, system cursor hidden), undo, clear.
- Seven presets (colour, thickness, transparency on/off and amount, outline on/off and thickness): keys `1` to `7`, the mouse wheel over the toolbar, or a [global hotkey](#global-hotkeys) of your own per preset.
- Fading is a setting: on or off plus a delay in seconds; strokes then ease out over about 0.6 s. `F` pins the ink on screen so it stops fading.
- The toolbar (a pill that collapses to a small handle and expands on hover) can be moved: press anywhere on it and drag it to any screen. It stays where you drop it, remembered per screen layout, with the collapsed handle at the middle of where you left the pill; a click without a drag still works the button under the pointer.
- The toolbar and the cheat-sheet are excluded from screen capture.
- Compression-safe defaults: widths in capture pixels (pen 6, highlighter 28, text 32, laser dot 18 with a 6 px halo), a dark outline on every stroke (a light one on dark ink), and a brightness-first palette with no pure red or blue.
- Keep-awake, off by default, for presentations and long sessions: a tray item and the toolbar's sun button toggle it, and the tray icon gets a green badge while it is armed. The default method asks Windows to keep the display on, so the pointer never moves; the alternative nudges the pointer 1 px and back after a whole interval of inactivity, and never while a stroke is drawn, a label typed or the laser held.
- Screen recording through ffmpeg (see [Recording](#recording)): all screens in one video, or one screen, with the toolbar and the recording chip kept out of the video.
- Settings is a web page: Settings in the tray menu or on the toolbar opens `http://127.0.0.1:8467/` in the browser (see [Settings](#settings)).
- The toolbar, cheat-sheet, recording chip and tray menu follow the fleet design system in light and dark, switching with the Windows theme, with Lucide icons throughout ([docs/design-tokens.md](docs/design-tokens.md)); the settings page is built from the fleet's vendored web components.
- Mouse, touch and pen share one input path; pen pressure varies the width and the pen's eraser end (or barrel button) erases whole strokes.

## Global hotkeys

| Key | Action |
|---|---|
| `Ctrl+Alt+D` | draw on and off |
| `Ctrl+Alt+F9` | start and stop recording |
| `Ctrl+Alt+F10` | pause and resume recording |
| unset, one per preset | pick preset 1 to 7 and start drawing |

These work in any application, and each is set in Settings. A hotkey that clashes with another one or with an in-draw key is refused. One that Windows will not register (another program holds it) is refused when you save it, and named in a notification when Overmark starts.

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

Keys reach the app only while drawing, so they never collide with the application underneath. All of them are rebindable in `config.json` (`keys`).

## Settings

Settings in the tray menu or on the toolbar stops drawing and opens the settings page in the default browser. It is one page of grouped sections: Drawing (cover all screens, fading), Presets, Hotkeys (the draw and recording hotkeys, each set by pressing the combination, and the in-draw keys, shown read-only), Preset hotkeys (one optional hotkey per preset, with Clear), Recording, Recording file, Recording audio, Keep-awake, Display (text size) and About. A sun or moon button in the header switches the page between light and dark.

Every change is saved to `config.json` and applied to the running app at once; nothing needs a restart. A change the app refuses changes nothing and says why: a hotkey that clashes with another hotkey or an in-draw key, a hotkey another program already holds, an invalid keep-awake interval or file-name pattern, or the microphone on with no device. The folder row's Browse opens a folder picker on this PC.

The footer shows the running build. Tapping it opens the fleet restart sheet: check for an update, pull it when the checkout is only behind, and restart Overmark through `tray.bat --restart`.

The page is served by the tray itself (FastAPI on port 8467, bound to 127.0.0.1). It answers only requests from this PC that name a loopback host, refuses writes from another site's page, and has no sign-in.

## Configuration

`config.json` (git-ignored) is created from `config.sample.json` on first run. The settings page saves it; you can also edit it by hand while the app is closed.

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
| `hotkey.preset_1` to `hotkey.preset_7` | a global hotkey per preset that picks it and starts drawing; empty (default) for none |
| `recording` | recording settings; see [Recording](#recording) |
| `toolbar.positions` | where the toolbar was dragged: one `[x, y]` (its top centre) per screen layout, written by the app. Delete an entry to return to the default top centre; a point that is on no screen is ignored |

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
| `system_audio.enabled`, `system_audio.device` | record what the computer plays, through WASAPI loopback; an empty device means the default output |
| `backend` | `auto` (GPU desktop duplication, falling back to GDI), `ddagrab` or `gdigrab` |
| `ffmpeg_path` | ffmpeg's location if it is not on `PATH` |

H.264 uses the first hardware encoder that passes a one-frame test (NVIDIA, Intel, AMD), else `libx264`. Pause ends a segment and resume starts the next; about a second around each pause is not recorded, and stop joins the segments into one file without re-encoding the video. System audio is captured beside each segment as `.<name>.part<N>.wav` (ffmpeg on Windows cannot record it, so [PyAudioWPatch](https://pypi.org/project/PyAudioWPatch/) does) and mixed in on stop: with the microphone also on, the two become one track, and only the audio is re-encoded. While recording, the segments are `.<name>.part<N>.mkv` files (plus their WAVs) in the destination folder, so an interrupted recording never looks finished; they can still be played or joined by hand. ffmpeg runs in a kill-on-close Windows job object, so if Overmark itself dies mid-recording (a crash, a kill, a forced log-off) the OS ends ffmpeg too; the segments written so far stay on disk. Each saved recording writes one log line with the screen choice, duration, size and encoder. If a hotkey does nothing, another application may be intercepting it even though registration succeeded; pick another combo. The capture checks behind this are in [docs/recording-probe.md](docs/recording-probe.md).

## Install

Clone and run `setup.bat`. `setup.bat -InPlace` reinstalls a clone at the same path and `setup.bat -MigrateFrom <old folder>` moves an older copy into a fresh one. Fresh PC, update, migration and uninstall: [docs/install.md](docs/install.md).

## Run

```powershell
.\tray.bat             # start the tray app, no console; a second start does nothing
.\tray.bat --restart   # stop the running instance, start a fresh one, confirm the new build
.\tray.bat -r          # same
powershell -File scripts/run.ps1 -Console   # run in the console with the log, for debugging
```

`tray.bat` is the standard fleet tray launcher: it stops by process id (never a blanket kill) and needs the shared tray helper from `fleet-config`'s `install.ps1` for `--restart`; a plain start works without it. The tray holds a session-wide single-instance mutex, so a second copy exits at once. The tray's settings server also answers `GET http://127.0.0.1:8467/api/version` (loopback only: the commit it loaded, its start time and its process id); `--restart` reads that before and after and fails unless a new process serves the checkout's `HEAD`. `scripts/run.ps1` without `-Console` calls `tray.bat`. To start Overmark at log-on, point a Startup shortcut at `tray.bat`, or register it in the app launcher (a scan of this folder recognises `tray.bat` as a tray).

## Verify

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
powershell -File scripts/verify-before-ship.ps1
```

The gate prints `GATE-RESULT: PASS` or `GATE-RESULT: FAIL (<stage>)`. After byte-compile and ruff it runs `scripts/run_ratchets.py`: eleven baseline-and-ratchet checks (static, comment, docs, structure, instruction, doc refs, dead code, conventions, runtime write, request budget, install standard), then the tests and the runtime write probe. Each ratchet records today's debt in a committed `.ratchets/<name>.json` and fails only on new debt; the scripts are copied unedited from project-scaffolding (`.fleet.toml` `[vendored]`). Tests read the machine's identity only through the `synthetic_host` fixture.

## Notes

- Capture behaviour depends on the OBS source type: Display Capture records the ink; Window Capture of another application does not.
- This repository is public: no screenshots, hostnames, usernames or machine paths in code, docs, issues or pull requests.

## License

MIT, see `LICENSE`.
