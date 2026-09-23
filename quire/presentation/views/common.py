"""Pieces shared by the day and week views."""
from __future__ import annotations

from PySide6.QtWidgets import QToolButton

from ...application.dto import AgendaItem, ItemKind
from ..formatting import fmt_range
from ..widgets import Block, scaled_font


def nav_button(text: str) -> QToolButton:
    button = QToolButton(text=text, autoRaise=True)
    button.setFont(scaled_font(button, 1.6))
    return button


def agenda_block(item: AgendaItem, column: int) -> Block:
    if item.kind is ItemKind.CLASS:
        details = [item.room, item.teacher]
    else:
        details = [item.details.splitlines()[0] if item.details else ""]
    subtitle = " · ".join([fmt_range(item.time), *filter(None, details)])
    return Block(column, item.time.start, item.time.end, item.title, subtitle, item.color, item)
