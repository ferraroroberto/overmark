"""The setup.bat checklist items that need this app's own rules (``.fleet.toml`` ``[install]``).

``python -B scripts/install_check.py <name>`` exits 0 for ok, 1 for missing and 2 for unknown.
``setup.bat -WhatIf`` runs these too, so they only read (``-B``: no bytecode either), and
they print no config value.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, MISSING, UNKNOWN = 0, 1, 2


def ffmpeg(root: Path) -> int:
    """ffmpeg where recording would look for it: ``recording.ffmpeg_path``, else ``PATH``."""
    # The package is not pip-installed. Never config.load: it creates a missing config.json.
    sys.path.insert(0, str(ROOT / "src"))
    from overmark.recording.devices import find_ffmpeg
    from overmark.recording.options import options_from_dict

    config = root / "config.json"
    raw = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {}
    options = options_from_dict(raw.get("recording"))
    return OK if find_ffmpeg(options.ffmpeg_path) else MISSING


def restart_helper(root: Path) -> int:
    """The shared tray helper ``tray.bat --restart`` calls, at the path tray.bat reads."""
    home = os.environ.get("USERPROFILE")
    if not home:
        return UNKNOWN
    return OK if (Path(home) / ".claude" / "tray" / "tray_lifecycle.ps1").is_file() else MISSING


CHECKS: dict[str, Callable[[Path], int]] = {"ffmpeg": ffmpeg, "restart-helper": restart_helper}


def main(argv: list[str], root: Path = ROOT) -> int:
    """Run the named check; a check that cannot establish its fact is unknown, never missing."""
    if len(argv) != 1 or argv[0] not in CHECKS:
        return UNKNOWN
    try:
        return CHECKS[argv[0]](root)
    except Exception:  # an escaping error would exit 1, which the checklist reads as "missing"
        return UNKNOWN


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
