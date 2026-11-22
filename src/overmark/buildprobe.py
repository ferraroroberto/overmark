"""A loopback build probe, so ``tray.bat --restart`` can prove which build is running.

The shared tray helper confirms a restart by reading ``GET /api/version`` on an owned port:
the served ``git_sha`` must match the repo ``HEAD`` and the answering process must be new.
Overmark has no web app, so the tray serves just that one read-only answer, bound to
127.0.0.1 only. Pure helpers (``version_payload``, ``read_git_sha``) are unit-tested; the
server is a stdlib ``ThreadingHTTPServer`` on a daemon thread.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def version_payload(git_sha: str, pid: int) -> dict[str, object]:
    """The JSON the restart check reads: the build this process loaded and its own pid."""
    return {"app": "overmark", "git_sha": git_sha, "pid": pid}


class _Handler(BaseHTTPRequestHandler):
    payload: bytes = b"{}"

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != VERSION_PATH:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (stdlib signature)
        """Stay quiet: a restart polls this once a second."""


class _LoopbackServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind a port that is already listening,
    # so a stale tray could keep answering the build check next to a fresh one.
    allow_reuse_address = False


class VersionServer:
    """Serves ``VERSION_PATH`` on loopback for the lifetime of the tray."""

    def __init__(self, git_sha: str, port: int = VERSION_PORT) -> None:
        body = json.dumps(version_payload(git_sha, os.getpid())).encode("utf-8")
        handler = type("VersionHandler", (_Handler,), {"payload": body})
        self._handler = handler
        self._port = port
        self._server: _LoopbackServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The bound port (differs from the requested one when that was 0)."""
        return self._server.server_address[1] if self._server else self._port

    def start(self) -> bool:
        """Bind and serve; False (logged) when the port is taken, the tray carries on."""
        try:
            self._server = _LoopbackServer((HOST, self._port), self._handler)
        except OSError as exc:
            log.warning(
                "⚠️ build probe not serving on %s:%s (%s); tray.bat --restart cannot confirm "
                "the build until it is free",
                HOST,
                self._port,
                exc,
            )
            return False
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="build-probe", daemon=True
        )
        self._thread.start()
        log.info("ℹ️ build probe on %s:%s", HOST, self.port)
        return True

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
