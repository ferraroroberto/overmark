"""The fleet design system's colour tokens for the app's own UI (toolbar, settings).

Ink colours are not here: they are the compression-safe preset palette.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

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
    "control_border": "#818b98",
    "control_fill": "#ffffff",
    "danger": "#cf222e",
    "attention_text": "#7d4e00",
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
    "control_border": "#6e7681",
    "control_fill": "#21262d",
    "danger": "#f85149",
    "attention_text": "#e3b341",
}

FONT = '"Segoe UI", system-ui, sans-serif'


def is_dark() -> bool:
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def tokens() -> dict[str, str]:
    return DARK if is_dark() else LIGHT


def stylesheet(t: dict[str, str]) -> str:
    """Qt stylesheet for the settings dialog, toolbar buttons and cheat-sheet."""
    return f"""
    * {{ font-family: {FONT}; font-size: 14px; color: {t["fg"]}; }}
    QDialog, QWidget#cheatSheet {{ background: {t["canvas"]}; }}
    QGroupBox {{
        background: {t["card"]}; border: 1px solid {t["border"]}; border-radius: 16px;
        margin-top: 22px; padding: 16px 12px 12px 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: 4px; padding: 0 4px;
        font-size: 14px; font-weight: 600; color: {t["fg_muted"]};
    }}
    QLabel#muted, QLabel#note {{ color: {t["fg_muted"]}; font-size: 14px; }}
    QLabel#error {{ color: {t["danger"]}; font-weight: 600; }}
    QLabel#heading {{ font-size: 20px; font-weight: 700; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {{
        background: {t["control_fill"]}; border: 1px solid {t["control_border"]};
        border-radius: 8px; padding: 6px 8px; min-height: 28px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 2px solid {t["accent"]};
    }}
    QComboBox QAbstractItemView {{
        background: {t["card"]}; border: 1px solid {t["border"]};
        selection-background-color: {t["accent_soft"]}; selection-color: {t["accent_text"]};
    }}
    QPushButton {{
        background: transparent; border: 1px solid {t["border"]}; border-radius: 12px;
        padding: 8px 16px; min-height: 28px; font-weight: 600; color: {t["fg_muted"]};
    }}
    QPushButton:hover {{ background: {t["accent_soft"]}; color: {t["accent_text"]}; }}
    QPushButton#primary {{
        background: {t["accent_fill"]}; color: {t["accent_fg"]}; border-color: {t["accent_fill"]};
    }}
    QCheckBox {{ spacing: 8px; }}
    QTabWidget::pane {{ border: none; background: {t["canvas"]}; }}
    QTabBar::tab {{
        background: transparent; border: none; border-bottom: 2px solid transparent;
        padding: 8px 16px; font-weight: 600; color: {t["fg_muted"]};
    }}
    QTabBar::tab:hover {{ color: {t["fg"]}; }}
    QTabBar::tab:selected {{ color: {t["accent_text"]}; border-bottom-color: {t["accent"]}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {t["control_border"]}; border-radius: 5px; min-height: 32px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QToolButton {{
        background: transparent; border: none; border-radius: 18px;
        min-width: 36px; min-height: 36px; font-size: 16px; color: {t["fg"]};
    }}
    QToolButton:hover {{ background: {t["accent_soft"]}; }}
    QToolButton:checked {{ background: {t["accent_soft"]}; color: {t["accent_text"]}; }}
    QToolButton#drawToggle:checked {{ background: {t["accent_fill"]}; color: {t["accent_fg"]}; }}
    QToolTip {{
        background: {t["card"]}; color: {t["fg"]}; border: 1px solid {t["border"]};
        border-radius: 8px; padding: 4px 8px;
    }}
    """
