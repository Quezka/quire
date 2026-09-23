"""Markdown notes with search, course filing, pinning and autosave."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QStackedWidget, QTextBrowser,
)

from ...application.bus import Topic
from ...application.dto import NoteSummary
from ...application.services import Services
from ...domain import Note
from .. import icons, theme
from ..bridge import ChangeRelay
from ..dialogs import confirm, fill_course_combo, select_data
from ..formatting import relative_timestamp
from ..widgets import TwoLineDelegate, scaled_font
from .common import Card, Page, icon_button, label, primary_button

PLACEHOLDER = (
    "Start typing. The first line becomes the title.\n\n"
    "Markdown works: # headings, **bold**, *italic*, - lists, - [ ] checklists, `code`.\n"
    "Press Ctrl+E to switch between editing and preview."
)


class NotesView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.notes = services.notes
        self.note: Note | None = None
        self._dirty = False
        self._loading = False
        self.title.setText("Notes")

        new = primary_button("Note")
        new.clicked.connect(lambda: self.new_note())
        self.add_actions(new)

        # ---- left: list ----
        self.search = QLineEdit(placeholderText="Search notes", clearButtonEnabled=True)
        self.search.setObjectName("search")
        self._search_action = self.search.addAction(
            icons.icon("search", theme.current().faint, size=16), QLineEdit.LeadingPosition)
        theme.themed(lambda t: self._search_action.setIcon(icons.icon("search", t.faint, size=16)))
        self.search.textChanged.connect(lambda: self.reload_list())
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(lambda: self.reload_list())
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(self._selected)
        QShortcut(QKeySequence.Delete, self.list, activated=self.delete_current,
                  context=Qt.WidgetShortcut)

        left = Card(padding=12)
        left.setFixedWidth(300)
        left.add(self.search)
        left.add(self.filter)
        left.add(self.list, 1)

        # ---- right: editor ----
        self.course = QComboBox()
        self.course.setMinimumWidth(170)
        self.course.currentIndexChanged.connect(self._meta_changed)
        self.pin = icon_button("pin", "Pin to top", checkable=True)
        self.pin.toggled.connect(self._meta_changed)
        self.status = label("", "hint")
        self.preview_btn = icon_button("eye", "Preview (Ctrl+E)", checkable=True)
        self.preview_btn.toggled.connect(self._toggle_preview)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.preview_btn.toggle,
                  context=Qt.WidgetWithChildrenShortcut)
        delete = icon_button("trash", "Delete note")
        delete.clicked.connect(self.delete_current)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(self.course)
        bar.addWidget(self.pin)
        bar.addStretch()
        bar.addWidget(self.status)
        bar.addWidget(self.preview_btn)
        bar.addWidget(delete)

        font = scaled_font(self, 1.1)
        self.editor = QPlainTextEdit(placeholderText=PLACEHOLDER)
        self.editor.setObjectName("bare")
        self.editor.setFont(font)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.editor.textChanged.connect(self._edited)
        self.viewer = QTextBrowser(openExternalLinks=True)
        self.viewer.setObjectName("bare")
        self.viewer.setFont(font)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.editor)
        self.stack.addWidget(self.viewer)

        self.right = Card(padding=14)
        self.right.body.addLayout(bar)
        self.right.add(self.stack, 1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(left)
        body.addWidget(self.right, 1)
        self.root.addLayout(body, 1)

        self._timer = QTimer(self, singleShot=True, interval=700, timeout=self.flush)
        relay.changed.connect(self._changed)

        self._fill_course_combos()
        self.reload_list()
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._show(None)

    # ---- list -----------------------------------------------------------

    def _fill_course_combos(self):
        courses = self.services.timetable.courses()
        fill_course_combo(self.filter, courses, "All notes")
        self._loading = True
        fill_course_combo(self.course, courses, "No course")
        self._loading = False

    def _changed(self, topic: Topic):
        # Our own saves publish NOTES too; the list is already up to date for those.
        if topic is Topic.COURSES:
            self._fill_course_combos()
            self.reload_list()

    def reload_list(self, select_id=None):
        select_id = select_id or (self.note.id if self.note else None)
        today = self.services.planner.today()
        self.list.blockSignals(True)
        self.list.clear()
        for summary in self.notes.search(self.search.text(), self.filter.currentData()):
            item = QListWidgetItem(summary.title)
            item.setData(Qt.UserRole, summary.id)
            item.setData(TwoLineDelegate.META, self._meta(summary, today))
            item.setData(TwoLineDelegate.COLOR, summary.course.color if summary.course else None)
            item.setData(TwoLineDelegate.PINNED, summary.pinned)
            self.list.addItem(item)
            if summary.id == select_id:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        count = self.list.count()
        self.subtitle.setText(f"{count} note{'s' if count != 1 else ''}"
                              + (" found" if self.search.text().strip() else ""))

    @staticmethod
    def _meta(summary: NoteSummary, today: date) -> str:
        meta = relative_timestamp(summary.updated, today)
        return f"{meta} · {summary.course.name}" if summary.course else meta

    def _selected(self, item, _previous):
        if item is not None and (self.note is None or item.data(Qt.UserRole) != self.note.id):
            self.flush()
            self._show(self.notes.note(item.data(Qt.UserRole)))

    # ---- editing --------------------------------------------------------

    def _show(self, note: Note | None):
        self._loading = True
        self.note = note
        self.editor.setPlainText(note.body if note else "")
        select_data(self.course, note.course_id if note else None)
        self.pin.setChecked(note.pinned if note else False)
        self._loading = False
        self._dirty = False
        self.right.setEnabled(note is not None)
        self.status.setText("")
        self.editor.setPlaceholderText(
            PLACEHOLDER if note else "Select a note, or press Ctrl+N to start one.")
        if self.preview_btn.isChecked():
            self.viewer.setMarkdown(self.editor.toPlainText())

    def _edited(self):
        if self._loading or self.note is None:
            return
        self._dirty = True
        self.status.setText("Editing…")
        self._timer.start()

    def _meta_changed(self):
        if self._loading or self.note is None:
            return
        self._dirty = True
        self.flush()
        self.reload_list()

    def flush(self):
        self._timer.stop()
        if not self._dirty or self.note is None:
            return
        self.note.body = self.editor.toPlainText()
        self.note.course_id = self.course.currentData()
        self.note.pinned = self.pin.isChecked()
        self.notes.save(self.note)
        self._dirty = False
        self.status.setText("Saved")
        item = self.list.currentItem()
        if item and item.data(Qt.UserRole) == self.note.id:
            item.setText(self.note.title)
            item.setData(TwoLineDelegate.PINNED, self.note.pinned)

    def _toggle_preview(self, on: bool):
        if on:
            self.viewer.setMarkdown(self.editor.toPlainText())
        self.stack.setCurrentIndex(1 if on else 0)
        if not on:
            self.editor.setFocus()

    def _open(self, note: Note):
        self.flush()
        for widget in (self.search, self.filter):
            widget.blockSignals(True)
        self.search.clear()
        if note.course_id is not None and self.filter.currentData() not in (None, note.course_id):
            self.filter.setCurrentIndex(0)
        for widget in (self.search, self.filter):
            widget.blockSignals(False)
        self._show(note)
        self.reload_list(note.id)
        self.preview_btn.setChecked(False)
        self.editor.setFocus()
        self.editor.moveCursor(QTextCursor.End)

    # ---- actions --------------------------------------------------------

    def new_note(self):
        self._open(self.notes.create("", self.filter.currentData()))

    def open_class_note(self, course_id: int, day: date):
        self._open(self.notes.class_note(course_id, day))

    def delete_current(self):
        if self.note is None:
            return
        if not confirm(self, "Delete note",
                       f"Delete “{self.note.title}”? This can't be undone."):
            return
        self._timer.stop()
        self.notes.delete(self.note.id)
        row = self.list.currentRow()
        self._show(None)
        self.reload_list()
        if self.list.count():
            self.list.setCurrentRow(min(max(row, 0), self.list.count() - 1))
