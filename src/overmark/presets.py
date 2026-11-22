"""Preset switching and turning a preset into a stroke style."""

from __future__ import annotations

from overmark.config import Preset, Sizes
from overmark.strokes import Style, Tool

HIGHLIGHTER_DEFAULT_ALPHA = 0.45  # translucent enough to read the text under it
DARK_OUTLINE = "#0B0B0B"
LIGHT_OUTLINE = "#F5F5F5"


class PresetCycler:
    """The active preset index; the wheel steps through and wraps around."""

    def __init__(self, count: int, index: int = 0) -> None:
        if count < 1:
            raise ValueError("need at least one preset")
        self.count = count
        self.index = min(max(index, 0), count - 1)

    def select(self, index: int) -> bool:
        """Select ``index``; return False (and keep the current one) if out of range."""
        if not 0 <= index < self.count:
            return False
        self.index = index
        return True

    def step(self, delta: int) -> int:
        self.index = (self.index + delta) % self.count
        return self.index


def relative_luminance(color: str) -> float:
    r, g, b = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def outline_color(color: str) -> str:
    """Dark outline for light ink; a light one for dark ink, which a dark rim would hide."""
    return LIGHT_OUTLINE if relative_luminance(color) < 0.18 else DARK_OUTLINE


def preset_alpha(preset: Preset) -> float:
    if not preset.transparency.enabled:
        return 1.0
    return 1.0 - preset.transparency.percent / 100.0


def style_for(tool: Tool, preset: Preset, sizes: Sizes) -> Style:
    outline_px = preset.outline.thickness_px if preset.outline.enabled else 0.0
    alpha = preset_alpha(preset)
    if tool is Tool.HIGHLIGHTER:
        return Style(
            color=preset.color,
            width_px=sizes.highlighter_px,
            alpha=alpha if preset.transparency.enabled else HIGHLIGHTER_DEFAULT_ALPHA,
            outline_px=0.0,
            outline_color=outline_color(preset.color),
        )
    width = sizes.text_px if tool is Tool.TEXT else preset.thickness_px
    return Style(
        color=preset.color,
        width_px=width,
        alpha=alpha,
        outline_px=outline_px,
        outline_color=outline_color(preset.color),
    )
