# Project Instructions

## This repository

Overmark: a public Windows screen-annotation app for live facilitation. Python + PySide6 overlay and tray first; the step-0 probe kept PySide6 (`docs/probe-results.md`). The MVP (tray, overlays, toolbar, settings) is in `src/overmark/`.

- Public repo: invented names only. No screenshots, hostnames, usernames, machine paths or personal data in code, docs, issues, PRs or commit messages.
- Never name or copy the branding of an existing commercial annotation tool in any public text.
- "Overmark" is a working name; a trademark check is pending (README says so).
- The app's own UI (toolbar, settings) follows the fleet design system (`~/.claude/design.md` and `design.dark.md`). Ink colours are the compression-safe palette, a separate concern.
- Settings live in `config.json` (git-ignored); `config.sample.json` is the committed template. Secrets go in `.env`.
- Scratch and runtime output go outside the code folders (never beside `src/`).

## Start and restart

`tray.bat` starts the tray with no console (a second start is a no-op: single-instance mutex in `app.py`); `tray.bat --restart` stops the running tray by pid, reclaims the build-probe port 8467, starts a fresh one and fails unless a new process serves `HEAD` (the tray answers `GET http://127.0.0.1:8467/api/version`, see `src/overmark/buildprobe.py`). Run it from PowerShell or a real Windows shell, never `cmd.exe /c` from Git Bash. `--restart` needs `~/.claude/tray/tray_lifecycle.ps1` (fleet-config's `install.ps1`). Restart after any change under `src/`; `config.json` edits take effect on restart too. `scripts/run.ps1 -Console` is for debugging only.

## Verification gate

```
powershell -File scripts/verify-before-ship.ps1
```

Byte-compile, ruff, pytest, using this repo's `.venv`. No other gate exists (no ratchets, no e2e, no CI workflow): report CI as **unknown**, never green.

## Layout

See `docs/layout.md`.
