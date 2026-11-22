"""Keep-awake: validation, the activity decision, the pause rules and the engine."""

import pytest

from overmark import keepawake
from overmark.config import Settings, settings_from_dict, settings_to_dict
from overmark.keepawake import (
    KeepAwake,
    KeepAwakeEngine,
    idle_ms,
    parse_distance,
    parse_interval,
    parse_mode,
    should_nudge,
)

# ----- validation ---------------------------------------------------------------------


@pytest.mark.parametrize("value", [30, 60, 5, 3600, "30", " 45 ", 90.0])
def test_interval_accepts_quick_and_free_values(value) -> None:
    assert parse_interval(value) == int(float(str(value).strip()))


@pytest.mark.parametrize("value", [0, -1, -30, 4, 3601, "", "abc", "1.5", 1.5, None, True, "٣٠"])
def test_interval_rejects_bad_values_with_a_message(value) -> None:
    with pytest.raises(ValueError, match="Interval"):
        parse_interval(value)


@pytest.mark.parametrize("value", [1, 2, 20, "5"])
def test_distance_accepts_small_whole_pixels(value) -> None:
    assert parse_distance(value) == int(value)


@pytest.mark.parametrize("value", [0, -1, 21, "x", 0.5, None, False])
def test_distance_rejects_bad_values(value) -> None:
    with pytest.raises(ValueError, match="Distance"):
        parse_distance(value)


def test_mode_must_be_known() -> None:
    assert parse_mode("nudge") == "nudge"
    with pytest.raises(ValueError):
        parse_mode("teleport")


# ----- the activity decision -------------------------------------------------------------


def test_idle_survives_the_tick_counter_wrapping() -> None:
    assert idle_ms(5_000, 2_000) == 3_000
    assert idle_ms(1_000, 0xFFFFFFFF - 999) == 2_000  # counter wrapped between the two reads


def test_no_nudge_while_the_user_was_recently_active() -> None:
    assert not should_nudge(idle=0, interval_s=60, busy=False)
    assert not should_nudge(idle=59_999, interval_s=60, busy=False)


def test_nudge_once_a_whole_interval_has_passed_idle() -> None:
    assert should_nudge(idle=60_000, interval_s=60, busy=False)
    assert should_nudge(idle=61_000, interval_s=30, busy=False)


def test_no_nudge_while_a_stroke_or_label_is_in_progress() -> None:
    assert not should_nudge(idle=10 * 60_000, interval_s=60, busy=True)


def test_unknown_idle_time_never_nudges() -> None:
    assert not should_nudge(idle=None, interval_s=5, busy=False)


# ----- the engine, with the OS calls faked ------------------------------------------------


class Fake:
    def __init__(self) -> None:
        self.idle: int | None = 0
        self.busy = False
        self.nudges: list[int] = []
        self.holds: list[bool] = []
        self.nudge_ok = True
        self.hold_ok = True

    def engine(self) -> KeepAwakeEngine:
        return KeepAwakeEngine(
            hold_display=self._hold,
            nudge=self._nudge,
            idle=lambda: self.idle,
            busy=lambda: self.busy,
        )

    def _hold(self, on: bool) -> bool:
        self.holds.append(on)
        return self.hold_ok

    def _nudge(self, distance: int) -> bool:
        self.nudges.append(distance)
        return self.nudge_ok


def nudging(**over) -> KeepAwake:
    return KeepAwake(**{"enabled": True, "mode": "nudge", "interval_seconds": 30, **over})


def test_off_by_default_never_touches_the_pointer_or_the_display() -> None:
    fake = Fake()
    engine = fake.engine()
    engine.configure(KeepAwake())
    fake.idle = 10**9
    assert engine.poll() is False
    assert fake.nudges == [] and fake.holds == []
    assert not engine.armed and not engine.needs_polling


def test_nudge_mode_sends_the_configured_distance_when_idle() -> None:
    fake = Fake()
    engine = fake.engine()
    engine.configure(nudging(distance_px=3))
    fake.idle = 29_999
    assert engine.poll() is False
    fake.idle = 30_000
    assert engine.poll() is True
    assert fake.nudges == [3]
    assert fake.holds == []  # nudge mode does not use the display request


def test_a_busy_stroke_pauses_the_nudge_then_it_resumes() -> None:
    fake = Fake()
    engine = fake.engine()
    engine.configure(nudging())
    fake.idle, fake.busy = 120_000, True
    assert engine.poll() is False
    fake.busy = False
    assert engine.poll() is True
    assert len(fake.nudges) == 1


def test_a_failed_nudge_is_reported_not_counted_as_sent() -> None:
    fake = Fake()
    fake.nudge_ok = False
    engine = fake.engine()
    engine.configure(nudging())
    fake.idle = 60_000
    assert engine.poll() is False
    assert engine.poll() is False
    assert fake.nudges == [1, 1]  # retried each poll


def test_execution_state_mode_holds_the_display_and_never_polls_a_nudge() -> None:
    fake = Fake()
    engine = fake.engine()
    engine.configure(KeepAwake(enabled=True, mode="execution_state"))
    assert fake.holds == [True]
    assert engine.armed and not engine.needs_polling
    fake.idle = 10**9
    assert engine.poll() is False and fake.nudges == []
    engine.configure(KeepAwake(enabled=True, mode="execution_state", interval_seconds=30))
    assert fake.holds == [True]  # unchanged request is not re-sent
    engine.configure(KeepAwake(enabled=False))
    assert fake.holds == [True, False]


def test_switching_from_execution_state_to_nudge_releases_the_display() -> None:
    fake = Fake()
    engine = fake.engine()
    engine.configure(KeepAwake(enabled=True, mode="execution_state"))
    engine.configure(nudging())
    assert fake.holds == [True, False]
    assert engine.needs_polling


def test_release_on_quit_only_when_held() -> None:
    fake = Fake()
    engine = fake.engine()
    engine.release()
    assert fake.holds == []
    engine.configure(KeepAwake(enabled=True, mode="execution_state"))
    engine.release()
    engine.release()
    assert fake.holds == [True, False]


def test_a_refused_display_request_is_retried_on_the_next_configure() -> None:
    fake = Fake()
    fake.hold_ok = False
    engine = fake.engine()
    cfg = KeepAwake(enabled=True, mode="execution_state")
    engine.configure(cfg)
    fake.hold_ok = True
    engine.configure(cfg)
    assert fake.holds == [True, True]


# ----- settings round trip -------------------------------------------------------------------


def test_keep_awake_defaults_to_off_with_documented_values() -> None:
    k = Settings().keep_awake
    assert k == KeepAwake(False, keepawake.DEFAULT_MODE, 60, 1)


def test_keep_awake_round_trips_through_the_settings_dict() -> None:
    s = Settings()
    s.keep_awake = KeepAwake(True, "nudge", 45, 2)
    assert settings_from_dict(settings_to_dict(s)).keep_awake == s.keep_awake


def test_invalid_keep_awake_values_fall_back_one_key_at_a_time() -> None:
    raw = settings_to_dict(Settings())
    raw["keep_awake"] = {
        "enabled": True,
        "mode": "teleport",
        "interval_seconds": 0,
        "distance_px": 3,
    }
    k = settings_from_dict(raw).keep_awake
    assert k == KeepAwake(True, keepawake.DEFAULT_MODE, 60, 3)


def test_non_object_keep_awake_section_uses_defaults() -> None:
    raw = settings_to_dict(Settings())
    raw["keep_awake"] = "on"
    assert settings_from_dict(raw).keep_awake == KeepAwake()
