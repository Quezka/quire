"""Building blocks shared by the pages: header, cards, buttons, agenda blocks."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from ...application.dto import AgendaItem, ItemKind
from .. import theme
from ..formatting import fmt_min, fmt_range
from ..widgets import Block


class Page(QWidget):
    """A top-level page: padded, themed background, header row on top."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(28, 22, 28, 24)
        self.root.setSpacing(18)
        self.title = QLabel(objectName="pageTitle")
        self.subtitle = QLabel(objectName="pageSubtitle")
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.leading = QHBoxLayout()
        self.leading.setSpacing(2)
        self.header.addLayout(self.leading)
        self.header.addLayout(titles)
        self.header.addStretch()
        self.root.addLayout(self.header)

    def add_actions(self, *widgets):
        for w in widgets:
            self.header.addWidget(w, 0, Qt.AlignVCenter)


class Card(QFrame):
    """Rounded surface with an optional title row."""

    def __init__(self, title: str | None = None, padding: int = 16, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(10)
        self.title_row = QHBoxLayout()
        self.title_row.setSpacing(8)
        if title:
            self.title_label = QLabel(title, objectName="cardTitle")
            self.title_row.addWidget(self.title_label)
            self.title_row.addStretch()
            self.body.addLayout(self.title_row)

    def add(self, widget, stretch: int = 0):
        self.body.addWidget(widget, stretch)
        return widget


def badge(text: str = "") -> QLabel:
    label = QLabel(text, objectName="badge")
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return label


def icon_button(name: str, tooltip: str, checkable: bool = False,
                checked_role: str | None = "accent") -> QToolButton:
    button = QToolButton(objectName="icon", toolTip=tooltip, checkable=checkable)
    button.setCursor(Qt.PointingHandCursor)
    theme.set_icon(button, name, "muted", checked_role if checkable else None)
    return button


def menu_button(text: str, menu, icon_name: str | None = None,
                primary: bool = False) -> QPushButton:
    """A header button that opens a menu (e.g. "+ Add" → Event / Work shift)."""
    result = primary_button(text, icon_name or "plus") if primary else button(text, icon_name)
    result.setMenu(menu)
    return result


def primary_button(text: str, icon_name: str | None = "plus") -> QPushButton:
    button = QPushButton(text, objectName="primary")
    button.setCursor(Qt.PointingHandCursor)
    if icon_name:
        theme.set_icon(button, icon_name, "on_accent", size=16)
    return button


def button(text: str, icon_name: str | None = None) -> QPushButton:
    result = QPushButton(text)
    result.setCursor(Qt.PointingHandCursor)
    if icon_name:
        theme.set_icon(result, icon_name, "muted", size=16)
    return result


def label(text: str = "", role: str = "muted") -> QLabel:
    return QLabel(text, objectName=role)


def zoom_controls(page: QWidget, zoom) -> QWidget:
    """− / fit / + buttons for a TimelineZoom, plus Ctrl+= / Ctrl+- / Ctrl+0."""
    from PySide6.QtGui import QKeySequence, QShortcut

    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    out = icon_button("zoom-out", "Zoom out (Ctrl+-)")
    fit = icon_button("fit-day", "Fit the whole day (Ctrl+0)", checkable=True)
    zoom_in = icon_button("zoom-in", "Zoom in (Ctrl+=, or Ctrl+scroll)")
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
        label_ = "regular shift" if item.kind is ItemKind.WEEKLY_SHIFT else "work shift"
        details = [label_, item.details.splitlines()[0] if item.details else ""]
    else:
        details = [item.details.splitlines()[0] if item.details else ""]
    when = fmt_range(item.time)
    is_shift = item.kind in (ItemKind.SHIFT, ItemKind.WEEKLY_SHIFT)
    if is_shift and item.time.end == 24 * 60:
        when = f"{fmt_min(item.time.start)} → next day"
    elif is_shift and item.time.start == 0 and item.origin and item.origin[0] != item.day:
        when = f"until {fmt_min(item.time.end)}"
    subtitle = " · ".join([when, *filter(None, details)])
    carry_over = bool(item.origin and item.origin[0] != item.day)
    return Block(column, item.time.start, item.time.end, item.title, subtitle, item.color, item,
                 carry_over)
