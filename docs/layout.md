# Layout

| Path | Holds |
|---|---|
| `src/overmark/` | application code, below |
| `tests/` | pytest suite; invented fixtures only |
| `scripts/` | the verification gate and helper scripts |
| `docs/` | durable reference (this file, design records) |
| `config.sample.json` | committed settings template; the live `config.json` is git-ignored |

New code goes under `src/overmark/` in a subject subfolder as it grows; tests mirror it under `tests/`.

## Modules in `src/overmark/`

Pure (no Qt, unit-tested): `config.py` (load, validate, save settings), `keymap.py` (key combos, in-draw key map, global hotkey parsing), `strokes.py` (stroke model, board with undo, laser trail), `fade.py` (fade timing), `presets.py` (preset switching, preset to stroke style).

Qt and Win32: `render.py` is the renderer boundary (stroke model in, pixels out; a native renderer would replace only this file). `controller.py` holds the drawing state shared by all windows. `overlay.py` is one transparent window per monitor, `toolbar.py` the capture-excluded toolbar pill and cheat-sheet, `settings_dialog.py` the settings window, `theme.py` the fleet design tokens, `win32.py` the ctypes calls Qt lacks (hotkey, click-through, capture exclusion), and `app.py` the tray and entry point (`python -m overmark`, or `scripts/run.ps1`).
