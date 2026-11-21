# Layout

| Path | Holds |
|---|---|
| `src/overmark/` | application code (stroke model, overlay, tray, settings); none yet |
| `tests/` | pytest suite; invented fixtures only |
| `scripts/` | the verification gate and helper scripts |
| `docs/` | durable reference (this file, design records) |
| `config.sample.json` | committed settings template; the live `config.json` is git-ignored |

New code goes under `src/overmark/` in a subject subfolder as it grows; tests mirror it under `tests/`.
