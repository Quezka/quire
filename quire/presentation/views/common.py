"""Building blocks shared by the pages: header, cards, buttons, agenda blocks."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from quezka_ui.widgets import Card, button, icon_button, label, primary_button, scrolling  # noqa: F401
from quezka_ui.widgets import Page as _Page

from ...application.dto import AgendaItem, ItemKind
from .. import theme
from ..formatting import fmt_min, fmt_range
from ..widgets import Block
from ..i18n import _


class Page(_Page):
    """The suite's page, with Quire's looser spacing."""

    def __init__(self, parent=None):
        super().__init__(parent, spacing=18)


def badge(text: str = "") -> QLabel:
    label = QLabel(text, objectName="badge")
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return label


def menu_button(text: str, menu, icon_name: str | None = None,
                primary: bool = False) -> QPushButton:
    """A header button that opens a menu (e.g. "+ Add" → Event / Work shift)."""
    result = primary_button(text, icon_name or "plus") if primary else button(text, icon_name)
    result.setMenu(menu)
    return result


def zoom_controls(page: QWidget, zoom) -> QWidget:
    """− / fit / + buttons for a TimelineZoom, plus Ctrl+= / Ctrl+- / Ctrl+0."""
    from PySide6.QtGui import QKeySequence, QShortcut

    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    out = icon_button("zoom-out", _("Zoom out (Ctrl+-)"))
    fit = icon_button("fit-day", _("Fit the whole day (Ctrl+0)"), checkable=True)
    zoom_in = icon_button("zoom-in", _("Zoom in (Ctrl+=, or Ctrl+scroll)"))
    out.clicked.connect(zoom.zoom_out)
    zoom_in.clicked.connect(zoom.zoom_in)
    fit.clicked.connect(lambda on: zoom.set_fit(on))

    def sync():
        fit.blockSignals(True)
        fit.setChecked(zoom.fit)
        fit.blockSignals(False)

    zoom.changed.connect(sync)
    sync()
    for widget in (out, fit, zoom_in):
        row.addWidget(widget)
    for keys, slot in (("Ctrl+=", zoom.zoom_in), ("Ctrl++", zoom.zoom_in),
                       ("Ctrl+-", zoom.zoom_out), ("Ctrl+0", lambda: zoom.set_fit(True))):
        QShortcut(QKeySequence(keys), page, activated=slot,
                  context=Qt.WidgetWithChildrenShortcut)
    box.fit_button = fit
    return box


def agenda_block(item: AgendaItem, column: int) -> Block:
    if item.kind is ItemKind.CLASS:
        details = [item.room, item.teacher]
    elif item.kind in (ItemKind.SHIFT, ItemKind.WEEKLY_SHIFT):
        label_ = _("regular shift") if item.kind is ItemKind.WEEKLY_SHIFT else _("work shift")
        details = [label_, item.details.splitlines()[0] if item.details else ""]
    else:
        details = [item.details.splitlines()[0] if item.details else ""]
    if item.is_milestone:
        return Block(column, item.time.start, item.time.end, item.title, fmt_min(item.time.start),
                     item.color, item, milestone=True)
    when = fmt_range(item.time)
    is_shift = item.kind in (ItemKind.SHIFT, ItemKind.WEEKLY_SHIFT)
    if is_shift and item.time.end == 24 * 60:
        when = _("{start} → next day").format(start=fmt_min(item.time.start))
    elif is_shift and item.time.start == 0 and item.origin and item.origin[0] != item.day:
        when = _("until {end}").format(end=fmt_min(item.time.end))
    subtitle = " · ".join([when, *filter(None, details)])
    carry_over = bool(item.origin and item.origin[0] != item.day)
    return Block(column, item.time.start, item.time.end, item.title, subtitle, item.color, item,
                 carry_over)


class StatTile(Card):
    """A number at the top of the School page with a caption underneath."""

    def __init__(self, caption: str):
        super().__init__(padding=16)
        self.body.setSpacing(4)
        self.caption = QLabel(caption, objectName="tileCaption")
        self.value = QLabel(objectName="tileValue")
        self.detail = label()
        self.detail.setWordWrap(True)
        for widget in (self.caption, self.value, self.detail):
            self.add(widget)
        self.body.addStretch()

    def show(self, value: str, detail: str = "", color: str | None = None):
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.detail.setText(detail)
        self.detail.setToolTip(detail)
