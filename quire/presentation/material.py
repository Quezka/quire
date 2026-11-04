"""Quire's Material You touches, on top of the suite's look: tonal surfaces tinted by the accent, a pill for the
current page, fully round buttons and softer corners. Only Quire's own colours and rules: the kit stays as it is."""
from __future__ import annotations

from . import theme

LIGHT = {"bg": "#f6f5fc", "surface": "#ffffff", "raised": "#e9e8f6", "sidebar": "#eeedf8", "accent_soft": "#dddcfb"}
DARK = {"bg": "#111119", "surface": "#1b1b25", "raised": "#28283a", "sidebar": "#16161f", "accent_soft": "#35366b"}


def _css(t) -> str:
    if t in (theme.HIGH_LIGHT, theme.HIGH_DARK):  # high contrast keeps its stark lines and borders
        return ""
    return f"""
    #sidebar {{ border-right: none; }}
    QToolButton#nav {{ border-radius: 16px; padding: 7px 12px; }}
    QToolButton#nav:checked {{ color: {t.text}; font-weight: 700; }}
    #card {{ border-radius: 16px; border: none; }}
    QPushButton {{ border-radius: 12px; padding-left: 14px; padding-right: 14px; }}
    QPushButton#primary {{ border-radius: 12px; font-weight: 700; }}
    QPushButton#segment {{ border-radius: 10px; }}
    QToolButton#icon, QPushButton#icon {{ border-radius: 12px; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit {{ border-radius: 10px; }}
    QMenu {{ border-radius: 12px; }}
    QMenu::item {{ border-radius: 8px; }}
    QListWidget {{ border: none; background: transparent; }}
    """


def install() -> None:
    """Before the theme is installed. High contrast keeps its own stark look."""
    theme.set_brand(light=LIGHT, dark=DARK, css=_css)
