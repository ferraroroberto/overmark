"""The settings web app: one page and its JSON API, served on loopback inside the tray.

Clicking Settings (tray or toolbar) opens ``http://127.0.0.1:8467/`` in the browser. The
page reads and saves the same ``config.json`` the app uses, through a ``Backend`` that
applies each save live; a save the app refuses (a hotkey another program holds) changes
nothing and says why. The same server answers ``/api/version`` for ``tray.bat --restart``
and the page footer, and ``/api/restart`` for the footer's restart and update sheet.

Reachable from this PC only: the socket binds 127.0.0.1, every request must come from
loopback and name a loopback ``Host`` (a DNS-rebinding page cannot reach it), and a write
from another site's page is refused by its ``Origin``. There is no sign-in.
"""

from __future__ import annotations

import logging
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from src.request_timing import RequestTimingMiddleware
from src.self_restart import TRAY_RESTART, RestartTarget, restart_router

from overmark.buildprobe import HOST, VERSION_PATH, VERSION_PORT, version_payload
from overmark.config import Settings, settings_to_dict
from overmark.glyphs import SPRITE
from overmark.web.settings_api import CHOICES, SettingsError, checked_update

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
SPRITE_MARK = "<!-- icons-sprite -->"  # where the page takes the inline icon sprite
LOOPBACK_CLIENTS = frozenset({"127.0.0.1", "::1"})
LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})
READ_METHODS = frozenset({"GET", "HEAD"})
STOP_TIMEOUT_S = 5.0


class Backend(Protocol):
    """What the server needs from the running app; the tray's lives in ``app.py``."""

    def settings(self) -> Settings: ...

    def apply(self, settings: Settings) -> str | None:
        """Apply and persist; return a message (and change nothing) when refused."""

    def microphones(self, ffmpeg_path: str) -> list[str]: ...

    def system_audio(self) -> list[str]: ...

    def screens(self) -> list[str]: ...

    def pick_folder(self, start: str) -> str | None:
        """A folder chosen in a dialog on this PC, or None when cancelled."""


def _host_name(host_header: str) -> str:
    return (urlsplit("//" + host_header).hostname or "").lower()


def is_loopback(request: Request) -> bool:
    client = request.client.host if request.client else ""
    return client in LOOPBACK_CLIENTS and _host_name(request.headers.get("host", "")) in (
        LOOPBACK_NAMES
    )


def loopback_guard(request: Request) -> None:
    """The restart routes' guard: the same loopback rule as every other route."""
    if not is_loopback(request):
        raise HTTPException(status_code=403, detail="this PC only")


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def create_app(backend: Backend, *, git_sha: str, built_at: str, pid: int, restart_dir: Path):
    """The FastAPI app; ``restart_dir`` holds the restart run's record (runtime data)."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sprite = SPRITE.read_text(encoding="utf-8")
    version = version_payload(git_sha, pid, built_at)
    # Logs a slow request with where its time went (a stuck Qt thread, a slow ffmpeg listing).
    app.add_middleware(RequestTimingMiddleware)

    @app.middleware("http")
    async def this_pc_only(request: Request, call_next):
        if not is_loopback(request):
            return _error(403, "Overmark's settings open on this PC only")
        origin = request.headers.get("origin")
        if request.method not in READ_METHODS and origin is not None:
            if urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
                return _error(403, "a write must come from this page")
        return await call_next(request)

    @app.exception_handler(TimeoutError)
    async def app_stuck(_request: Request, exc: TimeoutError) -> JSONResponse:
        return _error(503, f"Overmark did not answer: {exc}")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        page = page.replace(SPRITE_MARK, sprite)
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    @app.get(VERSION_PATH)
    def version_route() -> dict[str, object]:
        return version

    @app.get("/api/settings")
    def read_settings() -> dict[str, Any]:
        return {"settings": settings_to_dict(backend.settings()), "choices": CHOICES}

    @app.put("/api/settings")
    def save_settings(body: Any = Body(...)) -> Any:  # noqa: B008 (FastAPI's own idiom)
        try:
            updated = checked_update(backend.settings(), body)
        except SettingsError as exc:
            return _error(422, f"{exc}.")
        problem = backend.apply(updated)
        if problem:
            return _error(409, problem)
        return {"settings": settings_to_dict(backend.settings())}

    @app.get("/api/devices")
    def devices(ffmpeg_path: str = "") -> dict[str, list[str]]:
        return {
            "microphones": backend.microphones(ffmpeg_path),
            "system_audio": backend.system_audio(),
            "screens": backend.screens(),
        }

    @app.post("/api/pick-folder")
    def pick_folder(body: Any = Body(default=None)) -> dict[str, str | None]:  # noqa: B008
        start = body.get("start") if isinstance(body, dict) else None
        return {"folder": backend.pick_folder(start if isinstance(start, str) else "")}

    app.include_router(
        restart_router(
            targets=[RestartTarget("app", "Restart Overmark", TRAY_RESTART)],
            status_dir=restart_dir,
            guard=loopback_guard,
        )
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _bind(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        # Windows lets a second process bind a listening port unless the first holds it
        # exclusively, so a stale tray could keep answering the build check.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind((HOST, port))
    except OSError:
        sock.close()
        raise
    return sock


class WebServer:
    """Serves the app on loopback for the lifetime of the tray, on a daemon thread."""

    def __init__(self, app: FastAPI, port: int = VERSION_PORT) -> None:
        self._app = app
        self._port = port
        self._socket: socket.socket | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The bound port (differs from the requested one when that was 0)."""
        return self._socket.getsockname()[1] if self._socket else self._port

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    def start(self) -> bool:
        """Bind and serve; False (logged) when the port is taken, the tray carries on."""
        try:
            self._socket = _bind(self._port)
        except OSError as exc:
            log.warning(
                "⚠️ settings server not serving on %s:%s (%s); Settings and tray.bat --restart "
                "need it free",
                HOST,
                self._port,
                exc,
            )
            return False
        # log_config=None: the tray's own logging (a file under pythonw) keeps every record.
        config = uvicorn.Config(
            self._app, log_config=None, access_log=False, lifespan="off", log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            kwargs={"sockets": [self._socket]},
            name="settings-server",
            daemon=True,
        )
        self._thread.start()
        log.info("ℹ️ settings server on %s", self.url)
        return True

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(STOP_TIMEOUT_S)
        if self._socket is not None:
            self._socket.close()
        self._server = self._thread = self._socket = None
