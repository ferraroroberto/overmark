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

`tray.bat` starts the tray with no console (a second start is a no-op: single-instance mutex in `app.py`); `.\.venv\Scripts\python.exe -m src.restart_check restart --port 8467` (the same from any shell, run from the repo root) runs `tray.bat --restart` by absolute path, which stops the running tray by pid, reclaims the build-probe port 8467 and starts a fresh one, and exits non-zero unless a new process serves `HEAD`; by hand only `.\tray.bat --restart` (PowerShell) or `./tray.bat --restart` (Git Bash) work, the bare name is found by no shell here (the tray's settings server answers `GET http://127.0.0.1:8467/api/version`, see `src/overmark/web/server.py`). Run it from PowerShell or a real Windows shell, never `cmd.exe /c` from Git Bash. `--restart` needs `~/.claude/tray/tray_lifecycle.ps1` (fleet-config's `install.ps1`). Restart after any change under `src/`; `config.json` edits take effect on restart too. `scripts/run.ps1 -Console` is for debugging only.

## Verification gate

```
powershell -File scripts/verify-before-ship.ps1
```

Byte-compile, ruff, then `scripts/run_ratchets.py`, which runs every enabled ratchet, the tests and the runtime write probe, using this repo's `.venv`. `/issue-finish` runs the command through the evidence helper (`gate_evidence.py run --label gate`) so the pass is bound to the tree it ran on.

Ratchets in force (vendored byte-for-byte from project-scaffolding, listed in `.fleet.toml` `[vendored]`; each holds debt in a committed `.ratchets/<name>.json` and fails only on new debt): static, comment, docs, structure, instruction, doc refs, dead code, conventions (rules `no-window`, `logging-not-print`, `no-drive-path`, `no-pwsh-stub`, `subprocess-timeout`, `host-identity`, `state-literal`, `state-set-repeat`, `state-write`), runtime write, request budget and install standard. A baseline only shrinks: `--update-baseline` refuses additions, and `--allow-additions` is for a reviewed new hit, never to get green. Exit 3 means "not confirmed" and fails the gate. Never edit a vendored file; re-run `adopt_ratchets.py` from a newer scaffold checkout instead.

Not adopted, and why: usage track and ux surface are not adopted yet for the settings page (`src/overmark/static/`), the app's only web UI; the conventions rules `secret-compare`, `git-wrapper`, `password-input-vendored`, `nav-standalone-head`, `login-lockout` and `browser-per-iteration` need a login, a git wrapper, a web page or a browser, none of which exist here; the test value ratchet needs the scaffold's weekly burst job and gate ledger, which this repo does not run. There is no e2e suite and no CI workflow: report CI as **unknown**, never green.

Tests read host identity only through the `synthetic_host` fixture (`tests/host/_synthetic_host.py`, registered in `tests/conftest.py`); the `host-identity` rule fails a test that calls `getpass.getuser()` or `Path.home()` directly.

## Layout

See `docs/layout.md`.
