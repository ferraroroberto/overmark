# Overmark

Screen annotation for live facilitation: draw on any screen (pen, highlighter, arrow, text, laser) while the toolbar stays out of the capture, so an audience sees only the ink.

> **Name.** "Overmark" is a working name. A trademark and store-name check is still pending; do not treat it as final.

**Status:** seed only. There is no app code yet; the work is split into step issues in this repo's issue tracker (the step-0 probe chose the stack: [docs/probe-results.md](docs/probe-results.md)).

## What it is for

- Draw over any application on any monitor, with a global hotkey (rebindable; `Ctrl+Alt+D` is the default) toggling between drawing and click-through.
- Keep the controls (toolbar, settings, cheat-sheet) out of screen capture so participants never see them.
- Stay legible after video-call compression: capture-pixel widths, a dark outline on every stroke, a brightness-first palette.

## Planned behaviour

- **Fading ink** is a setting: on or off, plus a delay in seconds.
- **Presets** are saved sets of colour, thickness, transparency (on or off, and how much) and dark outline (on or off, and its thickness). Keys `1` to `7` select a preset; the mouse wheel over the toolbar switches between them.
- **Every screen at once:** drawing covers all monitors, as a region-screenshot overlay covers the whole desktop.
- **Toolbar:** a floating pill that collapses and expands.
- **Tools:** pen, highlighter, arrow, text label, outline, laser, undo, clear, and a region screenshot.
- **Stack:** Python with PySide6. The step-0 probe found the app-side drawing cost far inside the frame budget ([docs/probe-results.md](docs/probe-results.md)); the on-screen and OBS checks still owed are listed there.

## Configuration

Copy `config.sample.json` to `config.json` (git-ignored) and edit. Settings are documented where the code that reads them lands.

## Run

No runnable app yet.

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
