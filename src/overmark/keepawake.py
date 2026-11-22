"""Keep-awake: stop the screen saver and display sleep during a long presentation.

Pure Python, no Qt and no Win32: the OS calls are injected, so validation, the
"user is active" decision and the pause rules are unit-testable.

Two mechanisms, chosen by ``mode``:

* ``execution_state``: ask Windows to keep the display on. The pointer never moves.
* ``nudge``: move the pointer a pixel or two and straight back whenever the machine
  has been idle for a whole interval. A relative input event is the only thing the
  idle timers reliably count as the user.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

MODE_NUDGE = "nudge"
MODE_EXECUTION_STATE = "execution_state"
MODES = (MODE_EXECUTION_STATE, MODE_NUDGE)
DEFAULT_MODE = MODE_EXECUTION_STATE

QUICK_INTERVALS = (30, 60)
DEFAULT_INTERVAL_S = 60
MIN_INTERVAL_S = 5  # a typo must not flood the input queue
MAX_INTERVAL_S = 3600
DEFAULT_DISTANCE_PX = 1
MAX_DISTANCE_PX = 20

POLL_MS = 1000  # how often the nudge decision is re-evaluated
TICK_MASK = 0xFFFFFFFF  # GetTickCount wraps every ~49.7 days


@dataclass
class KeepAwake:
    enabled: bool = False
    mode: str = DEFAULT_MODE
    interval_seconds: int = DEFAULT_INTERVAL_S
    distance_px: int = DEFAULT_DISTANCE_PX


def _whole_number(value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a whole number")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit():
            return int(text)
        if text.startswith("-") and text[1:].isascii() and text[1:].isdigit():
            return int(text)
    raise ValueError(f"{what} must be a whole number")


def parse_interval(value: Any) -> int:
    """The nudge interval in whole seconds, or ``ValueError`` with a user-facing message."""
    seconds = _whole_number(value, "Interval")
    if not MIN_INTERVAL_S <= seconds <= MAX_INTERVAL_S:
        raise ValueError(f"Interval must be between {MIN_INTERVAL_S} and {MAX_INTERVAL_S} seconds")
    return seconds


def parse_distance(value: Any) -> int:
    """The nudge distance in whole pixels, or ``ValueError`` with a user-facing message."""
    pixels = _whole_number(value, "Distance")
    if not 1 <= pixels <= MAX_DISTANCE_PX:
        raise ValueError(f"Distance must be between 1 and {MAX_DISTANCE_PX} pixels")
    return pixels


def parse_mode(value: Any) -> str:
    if value in MODES:
        return str(value)
    raise ValueError(f"Mode must be one of: {', '.join(MODES)}")


def idle_ms(now_tick: int, last_input_tick: int) -> int:
    """Milliseconds since the last input, from two 32-bit tick counts (wrap-safe)."""
    return (now_tick - last_input_tick) & TICK_MASK


def should_nudge(*, idle: int | None, interval_s: int, busy: bool) -> bool:
    """Whether to send a nudge now.

    ``idle`` is milliseconds since the last input of any kind, our own nudge included, so
    a nudge is due once per interval of real inactivity and never while the user is
    active. ``None`` means the idle time could not be read: without it we cannot tell
    that the user is away, so we do not nudge. ``busy`` is a stroke being drawn or a
    label being typed, when the pointer must stay untouched whatever the idle time.
    """
    if busy or idle is None:
        return False
    return idle >= interval_s * 1000


class KeepAwakeEngine:
    """Applies a ``KeepAwake`` setting through injected OS calls.

    ``hold_display(True)`` asks the OS to keep the display on until ``hold_display(False)``;
    ``nudge(distance)`` moves the pointer by that many pixels and back; ``idle()`` reads the
    idle time in ms (``None`` if unknown); ``busy()`` says a stroke or label is in progress.
    """

    def __init__(
        self,
        *,
        hold_display: Callable[[bool], bool],
        nudge: Callable[[int], bool],
        idle: Callable[[], int | None],
        busy: Callable[[], bool],
    ) -> None:
        self._hold_display = hold_display
        self._nudge = nudge
        self._idle = idle
        self._busy = busy
        self.config = KeepAwake()
        self._holding = False
        self._warned_idle = False
        self._warned_nudge = False

    @property
    def armed(self) -> bool:
        return self.config.enabled

    @property
    def needs_polling(self) -> bool:
        return self.config.enabled and self.config.mode == MODE_NUDGE

    def configure(self, config: KeepAwake) -> None:
        self.config = KeepAwake(
            config.enabled, config.mode, config.interval_seconds, config.distance_px
        )
        want_hold = config.enabled and config.mode == MODE_EXECUTION_STATE
        if want_hold != self._holding:
            if self._hold_display(want_hold):
                self._holding = want_hold
                log.info("ℹ️ keep-awake display request %s", "on" if want_hold else "off")
            else:
                log.warning("⚠️ keep-awake display request could not be changed")
        log.info(
            "ℹ️ keep-awake %s (mode %s, every %d s, %d px)",
            "armed" if config.enabled else "off",
            config.mode,
            config.interval_seconds,
            config.distance_px,
        )

    def poll(self) -> bool:
        """One decision step; return True when a nudge was sent."""
        if not self.needs_polling:
            return False
        idle = self._idle()
        if idle is None and not self._warned_idle:
            self._warned_idle = True
            log.warning("⚠️ keep-awake cannot read the idle time; no nudge is sent")
        if not should_nudge(idle=idle, interval_s=self.config.interval_seconds, busy=self._busy()):
            return False
        if not self._nudge(self.config.distance_px):
            if not self._warned_nudge:  # it is retried every poll; log it once
                self._warned_nudge = True
                log.warning("⚠️ keep-awake nudge was not delivered")
            return False
        self._warned_nudge = False
        return True

    def release(self) -> None:
        """Hand the display back to the OS (on quit)."""
        if self._holding and self._hold_display(False):
            self._holding = False
