"""Lucide glyphs as standalone SVG text (pure, no Qt).

The glyphs come from the vendored fleet icon sprite (``_vendored/icons``, copied
byte-for-byte from project-scaffolding, never edited here). The few drawing-tool
glyphs the shared sprite lacks sit in ``EXTRA`` until the sprite carries them.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

SPRITE = Path(__file__).parent / "_vendored" / "icons" / "icons-sprite.html"
STROKE_WIDTH = 2.0  # Lucide's outline weight on its 24x24 grid

# Lucide (ISC) glyphs, lucide-static v1.21.0, not yet in the shared sprite.
EXTRA = {
    "highlighter": '<path d="m9 11-6 6v3h9l3-3" />'
    '<path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4" />',
    "arrow-up-right": '<path d="M7 7h10v10" /><path d="M7 17 17 7" />',
    "type": '<path d="M12 4v16" /><path d="M4 7V5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v2" />'
    '<path d="M9 20h6" />',
}

_SYMBOL = re.compile(r'<symbol id="i-([a-z0-9-]+)"[^>]*>(.*?)</symbol>', re.S)


@cache
def library() -> dict[str, str]:
    """Every known glyph name mapped to its inner SVG markup."""
    glyphs = {name: body.strip() for name, body in _SYMBOL.findall(SPRITE.read_text("utf-8"))}
    glyphs.update(EXTRA)
    return glyphs


def svg(name: str, color: str, stroke_width: float = STROKE_WIDTH) -> str:
    """A standalone 24x24 SVG document drawing glyph ``name`` in ``color``."""
    try:
        body = library()[name]
    except KeyError:
        raise KeyError(f"unknown Lucide glyph {name!r}") from None
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="none" color="{color}" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
