# Project Instructions

## This repository

Overmark: a public Windows screen-annotation app for live facilitation. Python + PySide6 overlay and tray first; a Rust renderer only if the step-0 probe fails. Currently a seed with no app code.

- Public repo: invented names only. No screenshots, hostnames, usernames, machine paths or personal data in code, docs, issues, PRs or commit messages.
- Never name or copy the branding of an existing commercial annotation tool in any public text.
- "Overmark" is a working name; a trademark check is pending (README says so).
- The app's own UI (toolbar, settings) follows the fleet design system (`~/.claude/design.md` and `design.dark.md`). Ink colours are the compression-safe palette, a separate concern.
- Settings live in `config.json` (git-ignored); `config.sample.json` is the committed template. Secrets go in `.env`.
- Scratch and runtime output go outside the code folders (never beside `src/`).

## Verification gate

```
powershell -File scripts/verify-before-ship.ps1
```

Byte-compile, ruff, pytest, using this repo's `.venv`. No other gate exists (no ratchets, no e2e, no CI workflow): report CI as **unknown**, never green.

## Layout

See `docs/layout.md`.
