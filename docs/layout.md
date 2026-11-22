# Layout

| Path | Holds |
|---|---|
| `src/overmark/` | application code, below |
| `tests/` | pytest suite; invented fixtures only |
| `scripts/` | the verification gate and helper scripts |
| `docs/` | durable reference (this file, design records) |
| `config.sample.json` | committed settings template; the live `config.json` is git-ignored |

`_vendored/icons/icons-sprite.html` is the Lucide sprite from project-scaffolding's icon component, copied byte-for-byte (pinned in `.fleet.toml` `[vendored]`); never edit it here.

New code goes under `src/overmark/` in a subject subfolder as it grows; tests mirror it under `tests/`.

## Modules in `src/overmark/`

Pure (no Qt, unit-tested): `config.py` (load, validate, save settings), `keymap.py` (key combos, in-draw key map, global hotkey parsing), `strokes.py` (stroke model, board with undo, laser trail), `fade.py` (fade timing), `presets.py` (preset switching, preset to stroke style), `keepawake.py` (keep-awake settings validation, the idle and pause decision, and the engine that drives the injected Win32 calls).

`recording/` is screen recording through ffmpeg. Pure (no Qt, unit-tested): `options.py` (the `recording` settings block), `naming.py` (file-name template, never-overwrite rule, in-progress names), `monitors.py` (screen numbering, the screen choice, the composed canvas), `devices.py` (finding ffmpeg, picking a working encoder, listing microphones), `command.py` (the ffmpeg command for each setting, the backend fallback plans, the join), `segments.py` (pause bookkeeping). `session.py` runs ffmpeg for one recording (segments, bounded stop, join and rename); `controls.py` (Qt) starts, pauses and stops it off the UI thread; `indicator.py` (Qt) is the capture-excluded elapsed-time chip. The capture probe behind it is [recording-probe.md](recording-probe.md).

Qt and Win32: `render.py` is the renderer boundary (stroke model in, pixels out; a native renderer would replace only this file). `controller.py` holds the drawing state shared by all windows. `overlay.py` is one transparent window per monitor, `toolbar.py` the capture-excluded toolbar pill and cheat-sheet, `settings_dialog.py` the settings window, `theme.py` the fleet design tokens (mapped in [design-tokens.md](design-tokens.md)), `glyphs.py` (pure) the Lucide glyphs as SVG text, `icons.py` their Qt rendering, `win32.py` the ctypes calls Qt lacks (hotkeys, click-through, capture exclusion, display request, idle time, pointer nudge, pointer position, DXGI output enumeration), and `app.py` the tray and entry point (`python -m overmark`, or `scripts/run.ps1`).
