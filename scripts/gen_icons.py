"""Regenerate the settings page's icons through project-scaffolding's ``brand_gen``.

The master is the Lucide ``pencil`` glyph from the vendored icon sprite (the tray draws
the same glyph on the same tile at run time, so the tray needs no file of its own).
``brand_gen.render_set`` writes the favicon, the Apple touch icon, the manifest icons and
the maskable icon into ``src/overmark/static``; they are committed, so nothing at run time
imports this script. It needs a project-scaffolding checkout beside this repo (or
``FLEET_SCAFFOLD_DIR``) and ``resvg-py`` plus ``Pillow`` (``requirements-dev.txt``):

    .venv\\Scripts\\python.exe scripts\\gen_icons.py
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = Path(os.environ.get("FLEET_SCAFFOLD_DIR") or PROJECT_ROOT.parent / "project-scaffolding")
STATIC = PROJECT_ROOT / "src" / "overmark" / "static"

log = logging.getLogger("gen_icons")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    sys.path.insert(0, str(SCAFFOLD / "scripts"))
    from brand_gen import render_set

    from overmark import glyphs, theme

    with tempfile.TemporaryDirectory() as scratch:
        master = Path(scratch) / f"{theme.BRAND_GLYPH}.svg"
        # runtime-write-exempt: a throwaway master in the system temp folder
        master.write_text(glyphs.svg(theme.BRAND_GLYPH, "currentColor"), encoding="utf-8")
        # The Stream Deck tile goes to the scratch folder: Overmark has no deck button.
        render_set(
            master=master,
            out_dir=STATIC,
            tray_out_dir=None,
            stream_deck_out_dir=Path(scratch),
            project_slug="overmark",
            emit_tray=False,
        )
    log.info("✅ icons written to %s", STATIC.relative_to(PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
