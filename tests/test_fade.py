"""Fade timing."""

import pytest

from overmark.fade import FADE_OUT_SECONDS, is_expired, opacity


def test_opaque_until_the_delay_ends() -> None:
    assert opacity(14.9, 10.0, enabled=True, delay=5) == 1.0


def test_eases_out_over_the_fade_duration() -> None:
    start = 15.0
    early = opacity(start + 0.1, 10.0, enabled=True, delay=5)
    late = opacity(start + 0.5, 10.0, enabled=True, delay=5)
    assert 1.0 > early > late > 0.0
    assert early < 1 - 0.1 / FADE_OUT_SECONDS  # ease-out drops faster than linear early on
    assert opacity(start + FADE_OUT_SECONDS, 10.0, enabled=True, delay=5) == 0.0
    assert is_expired(start + FADE_OUT_SECONDS, 10.0, enabled=True, delay=5)


@pytest.mark.parametrize(
    ("enabled", "pinned", "finished"),
    [(False, False, 0.0), (True, True, 0.0), (True, False, None)],
)
def test_never_fades_when_off_pinned_or_in_progress(enabled, pinned, finished) -> None:
    assert opacity(1e6, finished, enabled=enabled, delay=1, pinned=pinned) == 1.0
    assert not is_expired(1e6, finished, enabled=enabled, delay=1, pinned=pinned)
