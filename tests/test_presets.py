"""Preset switching and preset-to-style rules."""

import pytest

from overmark.config import Settings
from overmark.presets import (
    DARK_OUTLINE,
    HIGHLIGHTER_DEFAULT_ALPHA,
    LIGHT_OUTLINE,
    PresetCycler,
    style_for,
)
from overmark.strokes import Tool


def test_select_keeps_current_when_out_of_range() -> None:
    cycler = PresetCycler(7)
    assert cycler.select(6) and cycler.index == 6
    assert not cycler.select(7) and cycler.index == 6
    assert not cycler.select(-1) and cycler.index == 6


def test_wheel_steps_wrap_both_ways() -> None:
    cycler = PresetCycler(7)
    assert cycler.step(-1) == 6
    assert cycler.step(1) == 0
    assert cycler.step(3) == 3


def test_needs_a_preset() -> None:
    with pytest.raises(ValueError):
        PresetCycler(0)


def test_pen_style_follows_the_preset() -> None:
    s = Settings()
    style = style_for(Tool.PEN, s.presets[0], s.sizes)
    assert (style.color, style.width_px, style.alpha, style.outline_px) == ("#FFE600", 6, 1.0, 2)
    assert style.outline_color == DARK_OUTLINE


def test_dark_ink_gets_a_light_outline() -> None:
    s = Settings()
    assert style_for(Tool.PEN, s.presets[5], s.sizes).outline_color == LIGHT_OUTLINE


def test_transparency_and_outline_off() -> None:
    s = Settings()
    marker = style_for(Tool.PEN, s.presets[6], s.sizes)
    assert marker.alpha == pytest.approx(0.45)
    assert marker.outline_px == 0


def test_highlighter_and_text_use_tool_sizes() -> None:
    s = Settings()
    hl = style_for(Tool.HIGHLIGHTER, s.presets[0], s.sizes)
    assert hl.width_px == 28 and hl.alpha == HIGHLIGHTER_DEFAULT_ALPHA and hl.outline_px == 0
    assert style_for(Tool.TEXT, s.presets[0], s.sizes).width_px == 32
