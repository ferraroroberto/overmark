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

Invalid values fall back to the default for that key, with a warning in the log. The log is `overmark.log` in the app's local data folder (`%LOCALAPPDATA%\Overmark\Overmark`), one line per drawing session.

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
