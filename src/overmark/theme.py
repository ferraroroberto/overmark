"""The fleet design tokens (design.md light, design.dark.md dark) for the app's own chrome.

Every colour, size and radius the toolbar, cheat-sheet, recording chip, settings
window, tray menu and tray icon use comes from here; docs/design-tokens.md maps
each one back to its design-system token. Ink colours are not here: they are the
compression-safe preset palette, a function of the drawing, not chrome.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

# The design system's colour-mix tints, pre-mixed as rgba (16% = alpha 41 of 255).
LIGHT = {
    "canvas": "#ffffff",
    "canvas_subtle": "#f6f8fa",
    "card": "#ffffff",
    "border": "#d1d9e0",
    "border_muted": "#d8dee4",
    "fg": "#1f2328",
    "fg_muted": "#656d76",
    "accent": "#0969da",
    "accent_fg": "#ffffff",
    "accent_fill": "#0969da",
    "accent_text": "#0550ae",
    "accent_soft": "rgba(9, 105, 218, 41)",
    "accent_border_soft": "rgba(9, 105, 218, 61)",
    "accent_border_strong": "rgba(9, 105, 218, 71)",
    "success": "#1a7f37",
    "danger": "#cf222e",
    "attention": "#9a6700",
    "success_text": "#116329",
    "danger_text": "#a40e26",
    "attention_text": "#7d4e00",
    "control_border": "#818b98",
    "control_fill": "#f6f8fa",  # canvas-subtle: the light control fill
    "neutral_soft": "rgba(101, 109, 118, 41)",
    "settings_canvas": "#ededee",  # settings-group's sunk page: 8% fg over card
}

DARK = {
    "canvas": "#0d1117",
    "canvas_subtle": "#010409",
    "card": "#161b22",
    "border": "#30363d",
    "border_muted": "#21262d",
    "fg": "#e6edf3",
    "fg_muted": "#7d8590",
    "accent": "#2f81f7",
    "accent_fg": "#ffffff",
    "accent_fill": "#1f6feb",
    "accent_text": "#58a6ff",
    "accent_soft": "rgba(47, 129, 247, 41)",
    "accent_border_soft": "rgba(47, 129, 247, 61)",
    "accent_border_strong": "rgba(47, 129, 247, 71)",
    "success": "#3fb950",
    "danger": "#f85149",
    "attention": "#d29922",
    "success_text": "#56d364",
    "danger_text": "#ff7b72",
    "attention_text": "#e3b341",
    "control_border": "#6e7681",
    "control_fill": "#21262d",  # border-muted: the dark control fill
    "neutral_soft": "rgba(125, 133, 144, 41)",
    "settings_canvas": "#0d1117",  # dark's canvas already sits a step under its cards
}

FONT = '"Segoe UI", system-ui, sans-serif'  # Windows' system-ui face

# Type scale (px): body-sm / label, body, heading-md, heading-lg.
TEXT_SM = 14
TEXT_BODY = 16
TEXT_HEADING_MD = 20
TEXT_HEADING_LG = 24

# Spacing and radii (px).
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
GUTTER = 12
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_SETTINGS = 20
CONTROL_HEIGHT = 36
HIT_TARGET = 44

# icons.size steps (px): inline, title, nav-tab. The toolbar's glyph-only controls
# are standalone like a nav tab, so they take its step.
ICON_INLINE = 16
ICON_TITLE = 18
ICON_TOOLBAR = 20

# The fleet brand tile (project-scaffolding brand_gen): one Lucide master, stroked
# light on a dark square, the same in either theme so the identity never flips.
BRAND_GLYPH = "pencil"
BRAND_TILE = "#0A0A0A"
BRAND_STROKE = "#F0F0F0"
BRAND_STROKE_WIDTH = 2.6  # thicker than Lucide's 2px so it reads at tray size
BRAND_PAD = 0.12
# A state badge sits on the always-dark tile, so it takes the dark theme's hue.
BRAND_BADGE_ON = DARK["success"]


def is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def tokens() -> dict[str, str]:
    return DARK if is_dark() else LIGHT


def stylesheet(t: dict[str, str]) -> str:
    """Qt stylesheet for the settings window, toolbar, cheat-sheet and tray menu."""
    return f"""
    * {{ font-family: {FONT}; font-size: {TEXT_SM}px; color: {t["fg"]}; }}
    QDialog {{ background: {t["settings_canvas"]}; }}
    QWidget#cheatSheet {{ background: {t["card"]}; }}
    QGroupBox {{
        background: {t["card"]}; border: none; border-radius: {RADIUS_SETTINGS}px;
        margin-top: 30px; padding: {SPACE_MD}px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: {SPACE_XS}px; padding: 0 {SPACE_XS}px;
        font-size: {TEXT_BODY}px; font-weight: 700; color: {t["fg_muted"]};
    }}
    QLabel#muted, QLabel#note {{ color: {t["fg_muted"]}; font-size: {TEXT_SM}px; }}
    QLabel#error {{ color: {t["danger_text"]}; font-weight: 600; }}
    QLabel#heading {{ font-size: {TEXT_HEADING_MD}px; font-weight: 700; }}
    QLabel#key {{ font-weight: 600; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {{
        background: {t["control_fill"]}; border: 1px solid {t["control_border"]};
        border-radius: {RADIUS_MD}px; padding: 0 {SPACE_SM}px; min-height: {CONTROL_HEIGHT - 2}px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
    QKeySequenceEdit:focus {{
        border: 2px solid {t["accent"]};
    }}
    QComboBox QAbstractItemView {{
        background: {t["card"]}; border: 1px solid {t["border"]};
        selection-background-color: {t["accent_soft"]}; selection-color: {t["accent_text"]};
    }}
    QPushButton {{
        background: transparent; border: 1px solid {t["border"]}; border-radius: {RADIUS_MD}px;
        padding: 0 {SPACE_MD}px; min-height: {CONTROL_HEIGHT}px; font-weight: 600;
        color: {t["fg_muted"]};
    }}
    QPushButton:hover {{ color: {t["fg"]}; }}
    QPushButton:focus {{ border: 2px solid {t["accent"]}; }}
    QPushButton#primary {{
        background: {t["accent_fill"]}; color: {t["accent_fg"]};
        border-color: {t["accent_border_strong"]};
    }}
    QPushButton:disabled {{
        background: {t["canvas_subtle"]}; color: {t["fg_muted"]}; border-color: {t["border"]};
    }}
    QCheckBox {{ spacing: {SPACE_SM}px; }}
    QTabWidget::pane {{ border: none; background: {t["settings_canvas"]}; }}
    QTabBar::tab {{
        background: transparent; border: 1px solid transparent; border-radius: {RADIUS_MD}px;
        padding: {SPACE_SM}px {SPACE_MD}px; margin: {SPACE_XS}px; font-weight: 600;
        color: {t["fg_muted"]};
    }}
    QTabBar::tab:hover {{ color: {t["fg"]}; }}
    QTabBar::tab:selected {{
        background: {t["accent_soft"]}; border-color: {t["accent_border_soft"]};
        color: {t["accent_text"]};
    }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {t["control_border"]}; border-radius: 5px; min-height: 32px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{
        background: {t["control_border"]}; border-radius: 5px; min-width: 32px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    QToolButton {{
        background: transparent; border: none; border-radius: {HIT_TARGET // 2}px;
        min-width: {HIT_TARGET}px; min-height: {HIT_TARGET}px;
        font-weight: 600; color: {t["fg_muted"]};
    }}
    QToolButton:hover {{ color: {t["fg"]}; }}
    QToolButton:checked {{ background: {t["accent_soft"]}; color: {t["accent_text"]}; }}
    QToolButton#drawToggle {{ padding: 0 {SPACE_MD}px; }}
    QToolButton#drawToggle:checked {{ background: {t["accent_fill"]}; color: {t["accent_fg"]}; }}
    QToolTip {{
        background: {t["card"]}; color: {t["fg"]}; border: 1px solid {t["border"]};
        border-radius: {RADIUS_SM}px; padding: {SPACE_XS}px {SPACE_SM}px;
    }}
    QMenu {{
        background: {t["canvas_subtle"]}; border: 1px solid {t["border"]};
        padding: {SPACE_XS}px;
    }}
    QMenu::item {{
        min-height: {HIT_TARGET - 2 * SPACE_SM}px; padding: {SPACE_SM}px {SPACE_MD}px;
        padding-left: {SPACE_LG + ICON_INLINE}px; border-radius: {RADIUS_SM}px;
        color: {t["fg"]}; font-size: {TEXT_SM}px;
    }}
    QMenu::item:selected {{ background: {t["accent_soft"]}; color: {t["accent_text"]}; }}
    QMenu::item:disabled {{ color: {t["fg_muted"]}; }}
    QMenu::icon {{ padding-left: {SPACE_SM}px; }}
    QMenu::separator {{ height: 1px; background: {t["border_muted"]}; margin: {SPACE_XS}px 0; }}
    """
