"""Markdown notes with search, course filing, pinning and autosave."""
from __future__ import annotations

from datetime import date

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QMimeData, QSettings, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QFileDialog, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QToolButton,
)

from ...application.bus import Topic
from ...application.errors import ApplicationError, NotFound
from ...application.dto import NoteSummary
from ...application.services import Services
from ...application.inputs import NoteInput
from ...application.records import CourseRecord, NotebookRecord, NoteRecord
from .. import icons, theme
from ..bridge import ChangeRelay
from ..dialogs import NotebookDialog, confirm, select_data
from ..formatting import plural, relative_timestamp
from ..note_editor import SHORTCUTS, NoteEditor
from ..note_images import OPENABLE, load_picture, note_pdf, picture_from_file, picture_from_mime
from ..widgets import TwoLineDelegate, color_icon, scaled_font
from .common import Card, Page, icon_button, label, primary_button
from ..i18n import N_, _

PLACEHOLDER = N_(
    "Start typing. The first line becomes the title.\n\n"
    "Type # and a space for a heading, - for a list, [ ] for a checklist, > for a quote; "
    "**bold**, *italic* and `code` format as you close them. Paste or drop pictures in."
)


NEW_NOTEBOOK = "new-notebook"


def home_data(course_id: int | None, notebook_id: int | None = None) -> str | None:
    """What a picker stores for "filed in this class / notebook" (None: nowhere)."""
    if course_id is not None:
        return f"c:{course_id}"
    return f"n:{notebook_id}" if notebook_id is not None else None


def split_home(data) -> tuple[int | None, int | None]:
    """(course_id, notebook_id) from a picker's data."""
    if isinstance(data, str) and data[:2] == "c:":
        return int(data[2:]), None
    if isinstance(data, str) and data[:2] == "n:":
        return None, int(data[2:])
    return None, None


def fill_home_combo(combo: QComboBox, courses: list[CourseRecord],
                    notebooks: list[NotebookRecord], none_label: str, new_label: str | None = None):
    """(Re)populate a class-or-notebook picker, keeping the current choice if it still exists."""
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(none_label, None)
    for c in courses:
        combo.addItem(color_icon(c.color), c.name, home_data(c.id))
    if notebooks:
        combo.insertSeparator(combo.count())
        for n in notebooks:
            combo.addItem(color_icon(n.color), n.name, home_data(None, n.id))
    if new_label:
        combo.insertSeparator(combo.count())
        combo.addItem(new_label, NEW_NOTEBOOK)
    select_data(combo, current if current != NEW_NOTEBOOK else None)
    combo.blockSignals(False)


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
        self.notebook_btn = icon_button("book", _("New notebook…"))
        self.notebook_btn.clicked.connect(lambda: self.new_notebook())
        self.edit_notebook_btn = icon_button("edit", _("Edit notebook…"))
        self.edit_notebook_btn.clicked.connect(self._edit_scoped_notebook)
        self.edit_notebook_btn.setVisible(False)  # only while a notebook is selected
        self.group_btn = icon_button("layers", _("Group by class, notebook and topic"),
                                     checkable=True)
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
        filters.addWidget(self.edit_notebook_btn)
        filters.addWidget(self.notebook_btn)
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
        self.topic.setToolTip(_("Topic within the class or notebook, e.g. a chapter or unit"))
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
        delete = icon_button("trash", _("Delete note"))
        delete.clicked.connect(self.delete_current)
        export = icon_button("download", _("Export as PDF…"))
        export.clicked.connect(self.export_pdf)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(self.course)
        bar.addWidget(self.topic)
        bar.addWidget(self.pin)
        bar.addStretch()
        bar.addWidget(self.status)
        bar.addWidget(export)
        bar.addWidget(delete)

        font = scaled_font(self, 1.1)
        self.editor = NoteEditor()
        self.editor.setPlaceholderText(_(PLACEHOLDER))
        self.editor.setObjectName("bare")
        self.editor.setFont(font)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.editor.textChanged.connect(self._edited)
        self.editor.textChanged.connect(lambda: self._count_words())
        self.editor.picture_handler = self._keep_picture
        self.editor.picture_loader = lambda url, width: load_picture(services, url, width)
        self.editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._editor_menu)
        # Diagrams open in Ligature: their files, to take in what Ligature saves.
        self._diagram_files: dict[str, str] = {}  # path -> picture uid
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(lambda _p: self._diagrams_changed())
        self._watcher.directoryChanged.connect(lambda _p: self._diagrams_changed())

        self.right = Card(padding=14)
        self.right.body.addLayout(bar)
        self.right.body.addLayout(self._format_bar())
        self.right.add(self.editor, 1)

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
                ("bold", _("Bold"), e.toggle_bold),
                ("italic", _("Italic"), e.toggle_italic),
                ("list", _("Bulleted list"), lambda: e.toggle_list()),
                ("checklist", _("Checklist"), lambda: e.toggle_list(checklist=True)),
                ("quote", _("Quote"), e.toggle_quote),
                ("code", _("Code"), e.toggle_code),
                ("image", _("Insert a picture (or paste one, or drop it in)"),
                 self.insert_picture)):
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
        words = len(self.editor.toPlainText().replace("\ufffc", " ").split())
        self.words.setText(plural(words, "word") if words else "")

    # ---- list -----------------------------------------------------------

    def _fill_course_combos(self):
        courses = self.services.timetable.courses()
        notebooks = self.notes.notebooks()
        fill_home_combo(self.filter, courses, notebooks, _("All notes"))
        self._loading = True
        fill_home_combo(self.course, courses, notebooks, _("No class or notebook"),
                        _("New notebook…"))
        self._loading = False

    def _scope(self) -> tuple[int | None, int | None]:
        """(course_id, notebook_id) the list is filtered to; both None shows everything."""
        return split_home(self.filter.currentData())

    def _edit_scoped_notebook(self):
        notebook_id = self._scope()[1]
        if notebook_id is not None:
            self.edit_notebook(notebook_id)

    def _changed(self, topic: Topic):
        if topic is Topic.COURSES:
            self._fill_course_combos()
            self.reload_list()
        elif topic is Topic.NOTES and not self._saving:
            # Someone else changed notes (e.g. a sync); our own autosaves are skipped.
            self._fill_course_combos()  # notebooks may have come or gone
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
        shown = (self.note.body, self.note.course_id, self.note.pinned, self.note.topic,
                 self.note.notebook_id)
        if (fresh.body, fresh.course_id, fresh.pinned, fresh.topic, fresh.notebook_id) != shown:
            position = self.editor.textCursor().position()
            self._show(fresh)
            cursor = self.editor.textCursor()
            cursor.setPosition(min(position, self.editor.document().characterCount() - 1))
            self.editor.setTextCursor(cursor)

    def reload_list(self, select_id=None):
        select_id = select_id or (self.note.id if self.note else None)
        text = self.search.text()
        course_id, notebook_id = self._scope()
        filtered = course_id is not None or notebook_id is not None
        self.edit_notebook_btn.setVisible(notebook_id is not None)
        today = self.services.planner.today()
        self.list.blockSignals(True)
        self.list.clear()
        count = 0
        if self.group_btn.isChecked():
            per_home: dict = {}
            for g in self.notes.grouped(text, course_id, notebook_id):
                per_home.setdefault(self._home_of(g), []).append(g)
            for home, home_groups in per_home.items():
                first = home_groups[0]
                home_hidden = False
                if not filtered:  # a single filtered class or notebook needs no heading
                    home_hidden = ("home", home) in self._collapsed
                    owner = first.course or first.notebook
                    self._add_header(1, owner.name if owner else _("Not filed"), ("home", home),
                                     sum(len(g.notes) for g in home_groups),
                                     owner.color if owner else None, home_hidden)
                indent = 0 if filtered else 12
                only_loose = len(home_groups) == 1 and not home_groups[0].topic
                for g in home_groups:
                    topic_hidden = home_hidden
                    if not only_loose:
                        topic_key = ("topic", home, g.topic)
                        collapsed = topic_key in self._collapsed
                        if not home_hidden:
                            self._add_header(2, g.topic or _("No topic"), topic_key, len(g.notes),
                                             None, collapsed, indent)
                        topic_hidden = home_hidden or collapsed
                        indent_notes = indent + 16
                    else:
                        indent_notes = indent
                    for summary in g.notes:
                        count += 1
                        if not topic_hidden:
                            self._add_note(summary, today, select_id, indent_notes)
        else:
            for summary in self.notes.search(text, course_id, notebook_id):
                count += 1
                self._add_note(summary, today, select_id, 0)
        self.list.blockSignals(False)
        self.subtitle.setText(_("{notes} found").format(notes=plural(count, "note"))
                              if text.strip() else plural(count, "note"))

    @staticmethod
    def _home_of(group) -> tuple:
        """("course", id), ("notebook", id), or ("course", None) for notes filed nowhere."""
        if group.notebook is not None:
            return ("notebook", group.notebook.id)
        return ("course", group.course.id if group.course else None)

    def _add_note(self, summary: NoteSummary, today: date, select_id, indent: int):
        item = QListWidgetItem(summary.title)
        item.setData(Qt.UserRole, summary.id)
        grouped = self.group_btn.isChecked()
        item.setData(TwoLineDelegate.META, self._meta(summary, today, with_course=not grouped))
        owner = summary.course or summary.notebook
        item.setData(TwoLineDelegate.COLOR, owner.color if owner else None)
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
            _kind, home, topic = key
            new = menu.addAction(_("New note in this topic"))
            rename = menu.addAction(_("Rename topic…")) if topic else None
            chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
            course_id, notebook_id = self._ids_of(home)
            if chosen is new:
                self._open(self.notes.create("", course_id, topic, notebook_id))
            elif chosen is not None and chosen is rename:
                self._rename_topic(course_id, notebook_id, topic)
        elif key and key[0] == "home":
            home = key[1]
            course_id, notebook_id = self._ids_of(home)
            new = menu.addAction(_("New note in this notebook") if notebook_id is not None
                                 else _("New note in this class"))
            edit = menu.addAction(_("Edit notebook…")) if notebook_id is not None else None
            chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
            if chosen is new:
                self._open(self.notes.create("", course_id, "", notebook_id))
            elif chosen is not None and chosen is edit:
                self.edit_notebook(notebook_id)
        elif item.data(Qt.UserRole) is not None:
            delete = menu.addAction(_("Delete note"))
            if menu.exec(self.list.viewport().mapToGlobal(pos)) is delete:
                self.list.setCurrentItem(item)
                self.delete_current()

    @staticmethod
    def _ids_of(home: tuple) -> tuple[int | None, int | None]:
        kind, ident = home
        return (ident, None) if kind == "course" else (None, ident)

    def _rename_topic(self, course_id, notebook_id, topic: str):
        new, ok = QInputDialog.getText(self, _("Rename topic"),
                                       _("New name (use an existing name to merge):"), text=topic)
        if not ok:
            return
        self.flush()
        self.notes.rename_topic(course_id, topic, new, notebook_id)
        if self.note is not None:
            self.note = self.notes.note(self.note.id)
            self._fill_topics(self.note)
        self.reload_list()

    # ---- notebooks ------------------------------------------------------

    def new_notebook(self, show: bool = True) -> NotebookRecord | None:
        """Ask for a new notebook. `show` switches the list to it, so the next note goes in."""
        dialog = NotebookDialog(self.services, parent=self)
        if not dialog.exec() or dialog.result is None:
            return None
        self._fill_course_combos()
        if show:
            select_data(self.filter, home_data(None, dialog.result.id))
        return dialog.result

    def edit_notebook(self, notebook_id: int):
        book = next((n for n in self.notes.notebooks() if n.id == notebook_id), None)
        if book is None:
            return
        self.flush()
        dialog = NotebookDialog(self.services, book, self)
        if not dialog.exec():
            return
        if dialog.deleted:
            if self.filter.currentData() == home_data(None, notebook_id):
                self.filter.setCurrentIndex(0)
            if self.note is not None:
                self.note = self.notes.note(self.note.id)
        self._fill_course_combos()
        if self.note is not None:
            select_data(self.course, home_data(self.note.course_id, self.note.notebook_id))
        self.reload_list()

    @staticmethod
    def _meta(summary: NoteSummary, today: date, with_course: bool = True) -> str:
        meta = relative_timestamp(summary.updated, today)
        if with_course and summary.course:
            meta += f" · {summary.course.name}"
        elif with_course and summary.notebook:
            meta += f" · {summary.notebook.name}"
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
        self.editor.set_markdown(note.body if note else "")
        select_data(self.course, home_data(note.course_id, note.notebook_id) if note else None)
        self._fill_topics(note)
        self.pin.setChecked(note.pinned if note else False)
        self._loading = False
        self._dirty = False
        self.right.setEnabled(note is not None)
        self.status.setText("")
        self.editor.setPlaceholderText(
            _(PLACEHOLDER) if note else _("Select a note, or press Ctrl+N to start one."))

    def _fill_topics(self, note: NoteRecord | None, home=None):
        """Offer the topics already used in the note's class or notebook."""
        was_loading, self._loading = self._loading, True
        if home is not None:
            course_id, notebook_id = split_home(home)
        else:
            course_id, notebook_id = (note.course_id, note.notebook_id) if note else (None, None)
        self.topic.clear()
        self.topic.addItems(self.notes.topics(course_id, notebook_id))
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
        if self.course.currentData() == NEW_NOTEBOOK:  # "New notebook…" at the end of the list
            book = self.new_notebook(show=False)
            self._loading = True
            select_data(self.course, home_data(self.note.course_id, self.note.notebook_id)
                        if book is None else home_data(None, book.id))
            self._loading = False
            if book is None:
                return
        self._dirty = True
        home_before = home_data(self.note.course_id, self.note.notebook_id)
        home_changed = self.course.currentData() != home_before
        self.flush()
        if home_changed:
            self._fill_topics(self.note)
        self.reload_list()

    def flush(self):
        self._timer.stop()
        if not self._dirty or self.note is None:
            return
        body, topic = self.editor.markdown(), self.topic.currentText()
        course_id, notebook_id = split_home(self.course.currentData())
        self._saving = True
        try:
            self.note = self.notes.update(self.note.id, NoteInput(
                body, course_id, self.pin.isChecked(), topic, notebook_id))
        except NotFound:
            # Deleted on another computer while being edited here: keep the text.
            self.note = self.notes.create(body, course_id, topic, notebook_id)
            self.reload_list(self.note.id)
        finally:
            self._saving = False
        self._dirty = False
        self.status.setText(_("Saved"))
        item = self.list.currentItem()
        if item and item.data(Qt.UserRole) == self.note.id:
            item.setText(self.note.title)
            item.setData(TwoLineDelegate.PINNED, self.note.pinned)

    def _open(self, note: NoteRecord):
        self.flush()
        for widget in (self.search, self.filter):
            widget.blockSignals(True)
        self.search.clear()
        if self.filter.currentData() not in (None, home_data(note.course_id, note.notebook_id)):
            self.filter.setCurrentIndex(0)
        for widget in (self.search, self.filter):
            widget.blockSignals(False)
        self._show(note)
        self.reload_list(note.id)
        self.editor.setFocus()
        self.editor.moveCursor(QTextCursor.End)

    # ---- actions --------------------------------------------------------

    def new_note(self):
        course_id, notebook_id = self._scope()
        self._open(self.notes.create("", course_id, "", notebook_id))

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

    # ---- pictures -------------------------------------------------------

    def _keep(self, picture: tuple[bytes, str] | None, alt: str = "") -> str | None:
        if picture is None:
            QMessageBox.warning(self, _("Can't add the picture"),
                                _("Quire couldn't read that picture."))
            return None
        try:
            return self.notes.add_image(picture[0], picture[1], alt)
        except ApplicationError as e:
            QMessageBox.warning(self, _("Can't add the picture"), _(str(e)))
            return None

    def _keep_picture(self, mime: QMimeData) -> str | None:
        if self.note is None:
            return None
        return self._keep(picture_from_mime(mime), _("Picture"))

    def insert_picture(self):
        if self.note is None:
            return
        folder = QSettings().value("notes/picture_folder", str(Path.home()))
        path, _chosen = QFileDialog.getOpenFileName(
            self, _("Insert a picture"), folder, f"{_('Pictures')} ({OPENABLE})")
        if not path:
            return
        QSettings().setValue("notes/picture_folder", str(Path(path).parent))
        markdown = self._keep(picture_from_file(path), Path(path).stem)
        if markdown:
            self.editor.insert_picture(markdown)
            self.editor.setFocus()

    def _picture_actions(self, menu: QMenu, uid: str):
        record = self.notes.image(uid)
        if record is None:
            return
        if record.diagram:
            edit = menu.addAction(_("Edit in Ligature"), lambda: self.edit_diagram(uid))
            if not self.notes.can_edit_diagrams():
                edit.setEnabled(False)
                edit.setText(_("Edit in Ligature (install Ligature first)"))
        menu.addAction(_("Copy picture"), lambda: self._copy_picture(uid))
        menu.addAction(_("Save picture as…"), lambda: self._save_picture(uid))
        menu.addSeparator()

    def _editor_menu(self, pos):
        menu = QMenu(self)
        uid = self.editor.picture_at(pos)
        if uid:
            self._picture_actions(menu, uid)
        standard = self.editor.createStandardContextMenu(pos)
        for action in standard.actions():
            menu.addAction(action)
        menu.exec(self.editor.viewport().mapToGlobal(pos))

    def _copy_picture(self, uid: str):
        record = self.notes.image(uid)
        if record is None:
            return
        mime = QMimeData()
        if record.mime == "image/png":
            mime.setData("image/png", record.data)  # keeps a diagram inside it
        mime.setImageData(QImage.fromData(record.data))
        QGuiApplication.clipboard().setMimeData(mime)

    def _save_picture(self, uid: str):
        record = self.notes.image(uid)
        if record is None:
            return
        suffix = {"image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(
            record.mime, ".png")
        path, _chosen = QFileDialog.getSaveFileName(
            self, _("Save picture"), str(Path.home() / f"{_('picture')}{suffix}"),
            f"{_('Pictures')} (*{suffix})")
        if path:
            try:
                Path(path).write_bytes(record.data)
            except OSError:
                QMessageBox.warning(self, _("Save picture"), _("Couldn't save the picture there."))

    def edit_diagram(self, uid: str):
        self.flush()
        try:
            path = self.notes.edit_diagram(uid)
        except (ApplicationError, OSError) as e:
            QMessageBox.warning(self, _("Edit in Ligature"), _(str(e)) if isinstance(
                e, ApplicationError) else _("Ligature couldn't be started."))
            return
        self._diagram_files[path] = uid
        self._watcher.addPath(path)
        self._watcher.addPath(str(Path(path).parent))  # Ligature replaces the whole file
        self.status.setText(_("Editing the diagram in Ligature: save there to update it here."))

    def _diagrams_changed(self):
        for path, uid in list(self._diagram_files.items()):
            try:
                if self.notes.diagram_saved(uid, path):
                    self.editor.refresh_picture(uid)
                    self.status.setText(_("Diagram updated from Ligature."))
            except ApplicationError as e:
                self.status.setText(_(str(e)))
            if Path(path).exists() and path not in self._watcher.files():
                self._watcher.addPath(path)

    def export_pdf(self):
        if self.note is None:
            return
        self.flush()
        name = "".join(ch for ch in self.note.title if ch not in '\\/:*?"<>|').strip() or _("Note")
        folder = QSettings().value("notes/pdf_folder", str(Path.home()))
        path, _chosen = QFileDialog.getSaveFileName(
            self, _("Export as PDF"), str(Path(folder) / f"{name}.pdf"), "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        QSettings().setValue("notes/pdf_folder", str(Path(path).parent))
        note_pdf(self.services, self.note.title, self.editor.markdown(), path)
        self.status.setText(_("Exported to {name}").format(name=Path(path).name))
