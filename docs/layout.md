# Layout

| Path | Holds |
|---|---|
| `src/overmark/` | application code, below |
| `src/build_info.py`, `src/restart_check.py` | project-scaffolding's one-command tray restart (`python -m src.restart_check restart --port 8467`) and the git-identity helper it imports; byte-for-byte copies that import each other as `src.build_info`, so they sit directly in `src/` beside the package (a namespace package, no `__init__.py`), never inside it |
| `tests/` | pytest suite; invented fixtures only |
| `scripts/` | the verification gate and helper scripts |
| `docs/` | durable reference (this file, design records) |
| `config.sample.json` | committed settings template; the live `config.json` is git-ignored |

`_vendored/icons/icons-sprite.html` is the Lucide sprite from project-scaffolding's icon component, and `_vendored/single_instance.py` its Windows single-instance primitive, both copied byte-for-byte (pinned in `.fleet.toml` `[vendored]`); never edit them here. The same holds for the ratchet scripts and their `run_ratchets.py` runner in `scripts/` (each with its `.<name>-ratchet-baseline.json` at the root) and for `tests/host/_synthetic_host.py`, the fixture that fakes the account name, home folder and interpreter path for tests; ruff skips these copies and the two in `src/` (`extend-exclude` in `pyproject.toml`). `tray.bat` at the root is project-scaffolding's `tray.bat.template` with its four tokens filled (plus one `PYTHONPATH` line, because the package is not pip-installed).

New code goes under `src/overmark/` in a subject subfolder as it grows; tests mirror it under `tests/`.

## Modules in `src/overmark/`

Pure (no Qt, unit-tested): `config.py` (load, validate, save settings), `keymap.py` (key combos, in-draw key map, global hotkey parsing), `strokes.py` (stroke model, board with undo, laser trail), `fade.py` (fade timing), `presets.py` (preset switching, preset to stroke style), `keepawake.py` (keep-awake settings validation, the idle and pause decision, and the engine that drives the injected Win32 calls).

`recording/` is screen recording through ffmpeg. Pure (no Qt, unit-tested): `options.py` (the `recording` settings block), `naming.py` (file-name template, never-overwrite rule, in-progress names), `monitors.py` (screen numbering, the screen choice, the composed canvas), `devices.py` (finding ffmpeg, picking a working encoder, listing microphones), `command.py` (the ffmpeg command for each setting, the backend fallback plans, the join), `segments.py` (pause bookkeeping). `loopback.py` captures system audio through WASAPI loopback into one WAV per segment, placing each chunk on the clock (its placement rule is pure and tested). `containment.py` puts each ffmpeg in a kill-on-close job object so it ends with the app. `session.py` runs ffmpeg for one recording (segments, bounded stop, join and rename); `controls.py` (Qt) starts, pauses and stops it off the UI thread; `indicator.py` (Qt) is the capture-excluded elapsed-time chip. The capture probe behind it is [recording-probe.md](recording-probe.md).

Qt and Win32: `render.py` is the renderer boundary (stroke model in, pixels out; a native renderer would replace only this file). `controller.py` holds the drawing state shared by all windows. `overlay.py` is one transparent window per monitor, `toolbar.py` the capture-excluded toolbar pill and cheat-sheet, `settings_dialog.py` the settings window, `theme.py` the fleet design tokens (mapped in [design-tokens.md](design-tokens.md)), `glyphs.py` (pure) the Lucide glyphs as SVG text, `icons.py` their Qt rendering, `win32.py` the ctypes calls Qt lacks (hotkeys, click-through, capture exclusion, display request, idle time, pointer nudge, pointer position, DXGI output enumeration), and `app.py` the tray and entry point (`python -m overmark`, started through the root `tray.bat`), `buildprobe.py` the loopback `/api/version` answer that lets `tray.bat --restart` confirm the new build.
