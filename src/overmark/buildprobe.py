"""Build identity: which commit this process loaded, for ``tray.bat --restart`` and the page.

The shared tray helper confirms a restart by reading ``GET /api/version`` on an owned port:
the served ``git_sha`` must match the repo ``HEAD`` and the answering process must be new.
The settings web server (``overmark.web.server``) serves that answer on loopback; these
pure helpers build it and are unit-tested.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Must equal OWNED_PORTS in tray.bat (a test pins the two together): the restart reclaims
# whatever holds this port before it starts the fresh tray.
VERSION_PORT = 8467
VERSION_PATH = "/api/version"
HOST = "127.0.0.1"  # never a network-reachable bind

_GIT_TIMEOUT_S = 5


def read_git_sha(root: Path) -> str:
    """The checkout's ``HEAD`` commit, or an empty string when git cannot say.

    Read once at start: the restart check compares this against ``HEAD`` afterwards, so a
    tray that loaded older code reports an older sha. Empty (never a guess) makes that
    check fail loudly instead of passing on a stale or unknown build.
    """
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            creationflags=flags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("⚠️ could not read the git HEAD for the build probe: %s", exc)
        return ""
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        log.warning("⚠️ git gave no HEAD for the build probe (exit %s)", result.returncode)
        return ""
    return sha


def started_at() -> str:
    """This process's start time as ISO text: it changes on every restart, even on one sha."""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def version_payload(git_sha: str, pid: int, built_at: str) -> dict[str, object]:
    """The JSON the restart check and the page footer read."""
    return {"app": "overmark", "git_sha": git_sha, "built_at": built_at, "pid": pid}
