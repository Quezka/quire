"""Markdown notes with search, course filing, pinning and autosave."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QStackedWidget, QTextBrowser, QToolButton,
)

from ...application.bus import Topic
from ...application.errors import NotFound
from ...application.dto import NoteSummary
from ...application.services import Services
from ...application.inputs import NoteInput
from ...application.records import NoteRecord
from .. import icons, theme
from ..bridge import ChangeRelay
from ..dialogs import confirm, fill_course_combo, select_data
from ..formatting import plural, relative_timestamp
from ..markdown_editor import SHORTCUTS, MarkdownEdit
from ..widgets import TwoLineDelegate, scaled_font
from .common import Card, Page, icon_button, label, primary_button
from ..i18n import N_, _

PLACEHOLDER = N_(
    "Start typing. The first line becomes the title.\n\n"
    "Markdown works: # headings, **bold**, *italic*, - lists, - [ ] checklists, `code`.\n"
    "Enter continues a list; click a checkbox to tick it. Ctrl+E shows the preview."
)


class NotesView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.notes = services.notes
        self._saving = False  # our own autosave is publishing NOTES
        self.note: NoteRecord | None = None
        self._dirty = False
        self._loading = False
        self.title.setText(_("Notes"))

        new = primary_button(_("Note"))
        new.clicked.connect(lambda: self.new_note())
        self.add_actions(new)

        # ---- left: list ----
        self.search = QLineEdit(placeholderText=_("Search notes"), clearButtonEnabled=True)
        self.search.setObjectName("search")
        self._search_action = self.search.addAction(
            icons.icon("search", theme.current().faint, size=16), QLineEdit.LeadingPosition)
        theme.themed(lambda t: self._search_action.setIcon(icons.icon("search", t.faint, size=16)))
        self.search.textChanged.connect(lambda: self.reload_list())
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(lambda: self.reload_list())
        self.group_btn = icon_button("layers", _("Group by class and topic"), checkable=True)
        self.group_btn.setChecked(QSettings().value("notes/grouped", False, type=bool))
        self.group_btn.toggled.connect(self._grouping_toggled)
        self._collapsed: set[tuple] = set()
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(self._selected)
        self.list.itemClicked.connect(self._header_clicked)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        QShortcut(QKeySequence.Delete, self.list, activated=self.delete_current,
                  context=Qt.WidgetShortcut)

        filters = QHBoxLayout()
        filters.setSpacing(6)
        filters.addWidget(self.filter, 1)
        filters.addWidget(self.group_btn)
        left = Card(padding=12)
        left.setFixedWidth(310)
        left.add(self.search)
        left.body.addLayout(filters)
        left.add(self.list, 1)

        # ---- right: editor ----
        self.course = QComboBox()
        self.course.setMinimumWidth(170)
        self.course.currentIndexChanged.connect(self._meta_changed)
        self.topic = QComboBox(editable=True)
        self.topic.setMinimumWidth(170)
        self.topic.setInsertPolicy(QComboBox.NoInsert)
        self.topic.lineEdit().setPlaceholderText(_("No topic"))
        self.topic.setToolTip(_("Topic within the class, e.g. a chapter or unit"))
        self.topic.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.topic.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.topic.activated.connect(lambda _i: self._topic_changed())
        self.topic.lineEdit().editingFinished.connect(self._topic_changed)
        self._topic_action = self.topic.lineEdit().addAction(
            icons.icon("tag", theme.current().faint, size=14), QLineEdit.LeadingPosition)
        theme.themed(lambda t: self._topic_action.setIcon(icons.icon("tag", t.faint, size=14)))
        self.pin = icon_button("pin", _("Pin to top"), checkable=True)
        self.pin.toggled.connect(self._meta_changed)
        self.status = label("", "hint")
        self.preview_btn = icon_button("eye", _("Preview (Ctrl+E)"), checkable=True)
        self.preview_btn.toggled.connect(self._toggle_preview)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self.preview_btn.toggle,
                  context=Qt.WidgetWithChildrenShortcut)
        delete = icon_button("trash", _("Delete note"))
        delete.clicked.connect(self.delete_current)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(self.course)
        bar.addWidget(self.topic)
        bar.addWidget(self.pin)
        bar.addStretch()
        bar.addWidget(self.status)
        bar.addWidget(self.preview_btn)
        bar.addWidget(delete)

        font = scaled_font(self, 1.1)
        self.editor = MarkdownEdit(placeholderText=_(PLACEHOLDER))
        self.editor.setObjectName("bare")
        self.editor.setFont(font)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.editor.textChanged.connect(self._edited)
        self.editor.textChanged.connect(lambda: self._count_words())
        self.viewer = QTextBrowser(openExternalLinks=True)
        self.viewer.setObjectName("bare")
        self.viewer.setFont(font)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.editor)
        self.stack.addWidget(self.viewer)

        self.right = Card(padding=14)
        self.right.body.addLayout(bar)
        self.right.body.addLayout(self._format_bar())
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
        if not self._select_first_note():
            self._show(None)

    def _format_bar(self) -> QHBoxLayout:
        """Buttons for the Markdown the editor understands, with their shortcuts."""
        e = self.editor
        heading = icon_button("heading", _("Heading"))
        heading.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(heading)
        for level, text in ((1, _("Title")), (2, _("Heading")), (3, _("Subheading")),
                            (0, _("Plain text"))):
            menu.addAction(text, lambda level=level: e.set_heading(level))
        heading.setMenu(menu)
        buttons = [heading]
        for name, tip, action in (
                ("bold", _("Bold"), lambda: e.wrap("**", _("bold"))),
                ("italic", _("Italic"), lambda: e.wrap("*", _("italic"))),
                ("list", _("Bulleted list"), lambda: e.toggle_prefix("- ")),
                ("checklist", _("Checklist"), lambda: e.toggle_prefix("- [ ] ")),
                ("quote", _("Quote"), lambda: e.toggle_prefix("> ")),
                ("code", _("Code"), lambda: e.wrap("`", _("code")))):
            shortcut = SHORTCUTS.get(name)
            if shortcut is not None:
                tip += f" ({shortcut.toString(QKeySequence.NativeText)})"
            button = icon_button(name, tip)
            button.clicked.connect(action)
            button.clicked.connect(e.setFocus)
            buttons.append(button)
        self.format_buttons = buttons
        self.words = label("", "hint")
        row = QHBoxLayout()
        row.setSpacing(2)
        for button in buttons:
            row.addWidget(button)
        row.addStretch()
        row.addWidget(self.words)
        return row

    def _count_words(self):
        words = len(self.editor.toPlainText().split())
        self.words.setText(plural(words, "word") if words else "")

    # ---- list -----------------------------------------------------------

    def _fill_course_combos(self):
        courses = self.services.timetable.courses()
        fill_course_combo(self.filter, courses, _("All notes"))
        self._loading = True
        fill_course_combo(self.course, courses, _("No course"))
        self._loading = False

    def _changed(self, topic: Topic):
        if topic is Topic.COURSES:
            self._fill_course_combos()
            self.reload_list()
        elif topic is Topic.NOTES and not self._saving:
            # Someone else changed notes (e.g. a sync); our own autosaves are skipped.
            self._refresh_open_note()
            self.reload_list()

    def _refresh_open_note(self):
        """Show the open note as it is now, unless there are unsaved edits (they win)."""
        if self.note is None or self._dirty:
            return
        try:
            fresh = self.notes.note(self.note.id)
        except NotFound:  # deleted elsewhere
            self._show(None)
            return
        shown = (self.note.body, self.note.course_id, self.note.pinned, self.note.topic)
        if (fresh.body, fresh.course_id, fresh.pinned, fresh.topic) != shown:
            position = self.editor.textCursor().position()
            self._show(fresh)
            cursor = self.editor.textCursor()
            cursor.setPosition(min(position, len(fresh.body)))
            self.editor.setTextCursor(cursor)

    def reload_list(self, select_id=None):
        select_id = select_id or (self.note.id if self.note else None)
        text, course_id = self.search.text(), self.filter.currentData()
        today = self.services.planner.today()
        self.list.blockSignals(True)
        self.list.clear()
        count = 0
        if self.group_btn.isChecked():
            groups = self.notes.grouped(text, course_id)
            per_course: dict = {}
            for g in groups:
                key = g.course.id if g.course else None
                per_course.setdefault(key, []).append(g)
            for key, course_groups in per_course.items():
                course = course_groups[0].course
                course_hidden = False
                if course_id is None:  # a single filtered course needs no heading
                    course_hidden = ("course", key) in self._collapsed
                    self._add_header(1, course.name if course else _("No class"), ("course", key),
                                     sum(len(g.notes) for g in course_groups),
                                     course.color if course else None, course_hidden)
                indent = 12 if course_id is None else 0
                only_loose = len(course_groups) == 1 and not course_groups[0].topic
                for g in course_groups:
                    topic_hidden = course_hidden
                    if not only_loose:
                        topic_key = ("topic", key, g.topic)
                        collapsed = topic_key in self._collapsed
                        if not course_hidden:
                            self._add_header(2, g.topic or _("No topic"), topic_key, len(g.notes),
                                             None, collapsed, indent)
                        topic_hidden = course_hidden or collapsed
                        indent_notes = indent + 16
                    else:
                        indent_notes = indent
                    for summary in g.notes:
                        count += 1
                        if not topic_hidden:
                            self._add_note(summary, today, select_id, indent_notes)
        else:
            for summary in self.notes.search(text, course_id):
                count += 1
                self._add_note(summary, today, select_id, 0)
        self.list.blockSignals(False)
        self.subtitle.setText(_("{notes} found").format(notes=plural(count, "note"))
                              if text.strip() else plural(count, "note"))

    def _add_note(self, summary: NoteSummary, today: date, select_id, indent: int):
        item = QListWidgetItem(summary.title)
        item.setData(Qt.UserRole, summary.id)
        grouped = self.group_btn.isChecked()
        item.setData(TwoLineDelegate.META, self._meta(summary, today, with_course=not grouped))
        item.setData(TwoLineDelegate.COLOR, summary.course.color if summary.course else None)
        item.setData(TwoLineDelegate.PINNED, summary.pinned)
        item.setData(TwoLineDelegate.INDENT, indent)
        self.list.addItem(item)
        if summary.id == select_id:
            self.list.setCurrentItem(item)

    def _add_header(self, level: int, text: str, key: tuple, count: int, color, collapsed: bool,
                    indent: int = 0):
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)
        item.setData(TwoLineDelegate.HEADER, level)
        item.setData(TwoLineDelegate.COUNT, count)
        item.setData(TwoLineDelegate.COLOR, color)
        item.setData(TwoLineDelegate.COLLAPSED, collapsed)
        item.setData(TwoLineDelegate.INDENT, indent)
        item.setData(Qt.UserRole + 20, key)
        self.list.addItem(item)

    def _select_first_note(self) -> bool:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) is not None:
                self.list.setCurrentRow(row)
                return True
        return False

    def _grouping_toggled(self, on: bool):
        QSettings().setValue("notes/grouped", on)
        self.reload_list()

    def _header_clicked(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole + 20)
        if key is None:
            return
        self._collapsed ^= {key}
        self.reload_list()

    def _list_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        key = item.data(Qt.UserRole + 20)
        menu = QMenu(self)
        if key and key[0] == "topic":
            _kind, course_id, topic = key
            new = menu.addAction(_("New note in this topic"))
            rename = menu.addAction(_("Rename topic…")) if topic else None
            chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
            if chosen is new:
                self._open(self.notes.create("", course_id, topic))
            elif chosen is not None and chosen is rename:
                self._rename_topic(course_id, topic)
        elif key and key[0] == "course":
            new = menu.addAction(_("New note in this class"))
            if menu.exec(self.list.viewport().mapToGlobal(pos)) is new:
                self._open(self.notes.create("", key[1]))
        elif item.data(Qt.UserRole) is not None:
            delete = menu.addAction(_("Delete note"))
            if menu.exec(self.list.viewport().mapToGlobal(pos)) is delete:
                self.list.setCurrentItem(item)
                self.delete_current()

    def _rename_topic(self, course_id, topic: str):
        new, ok = QInputDialog.getText(self, _("Rename topic"),
                                       _("New name (use an existing name to merge):"), text=topic)
        if not ok:
            return
        self.flush()
        self.notes.rename_topic(course_id, topic, new)
        if self.note is not None:
            self.note = self.notes.note(self.note.id)
            self._fill_topics(self.note)
        self.reload_list()

    @staticmethod
    def _meta(summary: NoteSummary, today: date, with_course: bool = True) -> str:
        meta = relative_timestamp(summary.updated, today)
        if with_course and summary.course:
            meta += f" · {summary.course.name}"
        if with_course and summary.topic:
            meta += f" · {summary.topic}"
        if summary.snippet:
            meta += f" · {summary.snippet}"
        return meta

    def _selected(self, item, _previous):
        if item is None or item.data(Qt.UserRole) is None:  # section headings
            return
        if self.note is None or item.data(Qt.UserRole) != self.note.id:
            self.flush()
            self._show(self.notes.note(item.data(Qt.UserRole)))

    # ---- editing --------------------------------------------------------

    def _show(self, note: NoteRecord | None):
        self._loading = True
        self.note = note
        self.editor.setPlainText(note.body if note else "")
        select_data(self.course, note.course_id if note else None)
        self._fill_topics(note)
        self.pin.setChecked(note.pinned if note else False)
        self._loading = False
        self._dirty = False
        self.right.setEnabled(note is not None)
        self.status.setText("")
        self.editor.setPlaceholderText(
            _(PLACEHOLDER) if note else _("Select a note, or press Ctrl+N to start one."))
        if self.preview_btn.isChecked():
            self.viewer.setMarkdown(self.editor.toPlainText())

    def _fill_topics(self, note: NoteRecord | None, course_id=None):
        """Offer the topics already used in the note's class."""
        was_loading, self._loading = self._loading, True
        course = course_id if course_id is not None or note is None else note.course_id
        self.topic.clear()
        self.topic.addItems(self.notes.topics(course))
        self.topic.setEditText(note.topic if note else "")
        self._loading = was_loading

    def _topic_changed(self):
        if self._loading or self.note is None:
            return
        if " ".join(self.topic.currentText().split()) != self.note.topic:
            self._dirty = True
            self.flush()
            self.topic.setEditText(self.note.topic)  # show the canonical spelling
            self.reload_list()

    def _edited(self):
        if self._loading or self.note is None:
            return
        self._dirty = True
        self.status.setText(_("Editing…"))
        self._timer.start()

    def _meta_changed(self):
        if self._loading or self.note is None:
            return
        self._dirty = True
        course_changed = self.course.currentData() != self.note.course_id
        self.flush()
        if course_changed:
            self._fill_topics(self.note)
        self.reload_list()

    def flush(self):
        self._timer.stop()
        if not self._dirty or self.note is None:
            return
        body, course_id, topic = (self.editor.toPlainText(), self.course.currentData(),
                                  self.topic.currentText())
        self._saving = True
        try:
            self.note = self.notes.update(self.note.id, NoteInput(
                body, course_id, self.pin.isChecked(), topic))
        except NotFound:
            # Deleted on another computer while being edited here: keep the text.
            self.note = self.notes.create(body, course_id, topic)
            self.reload_list(self.note.id)
        finally:
            self._saving = False
        self._dirty = False
        self.status.setText(_("Saved"))
        item = self.list.currentItem()
        if item and item.data(Qt.UserRole) == self.note.id:
            item.setText(self.note.title)
            item.setData(TwoLineDelegate.PINNED, self.note.pinned)

    def _toggle_preview(self, on: bool):
        if on:
            self.viewer.setMarkdown(self.editor.toPlainText())
        self.stack.setCurrentIndex(1 if on else 0)
        for button in self.format_buttons:
            button.setEnabled(not on)
        if not on:
            self.editor.setFocus()

    def _open(self, note: NoteRecord):
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
        if not confirm(self, _("Delete note"),
                       _("Delete “{title}”? This can't be undone.").format(title=self.note.title)):
            return
        self._timer.stop()
        self.notes.delete(self.note.id)
        row = self.list.currentRow()
        self._show(None)
        self.reload_list()
        for r in [*range(max(row, 0), self.list.count()), *range(min(row, self.list.count()) - 1, -1, -1)]:
            if self.list.item(r).data(Qt.UserRole) is not None:
                self.list.setCurrentRow(r)
                break
