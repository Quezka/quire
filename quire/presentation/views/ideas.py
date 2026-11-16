"""Ideas: catch one in a second (type, Enter), find it again (search, #tags), act on it (task, note, done)."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QWidget)

from quezka_ui.fit import exec_menu

from ...application.bus import Topic
from ...application.errors import ApplicationError
from ...application.services import Services
from ..bridge import ChangeRelay
from ..i18n import _
from .common import Card, Page, label, primary_button

MAX_TAG_CHIPS = 8  # most used first; more = clutter


class IdeasView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.ideas = services.ideas
        self.title.setText(_("Ideas"))
        self._deleted = None  # last deleted idea, for Undo

        self.entry = QLineEdit(placeholderText=_("Jot an idea… (#tag to sort it)"))
        self.entry.returnPressed.connect(self._add)
        add = primary_button(_("Add"), "plus")
        add.clicked.connect(self._add)
        row = QHBoxLayout()
        row.addWidget(self.entry, 1)
        row.addWidget(add)
        self.hint = label(_("Catch it now, look at it later: new ideas come back in the evening digest."), "hint")
        self.hint.setWordWrap(True)

        # one line: what happened + Undo (no confirm dialogs)
        self.notice = QLabel(objectName="muted")
        self.undo = QPushButton(_("Undo"))
        self.undo.clicked.connect(self._undo)
        notice = QHBoxLayout()
        notice.addWidget(self.notice, 1)
        notice.addWidget(self.undo)
        self._show_notice("")

        self.search = QLineEdit(placeholderText=_("Search ideas"), clearButtonEnabled=True)
        self.search.setObjectName("search")
        self.search.textChanged.connect(lambda _t: self.refresh())
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        chips_box = QWidget()
        chips_box.setLayout(self.chips)

        self.show_done = QCheckBox(_("Show the ones done"))
        self.show_done.toggled.connect(lambda _on: self.refresh())
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemChanged.connect(self._ticked)
        self.list.itemDoubleClicked.connect(lambda item: self._edit(item))
        self.empty = label(_("No ideas yet. The next one that comes to mind goes here."), "muted")
        self.empty.setWordWrap(True)

        card = Card()
        card.body.addLayout(row)
        card.add(self.hint)
        card.body.addLayout(notice)
        card.add(self.search)
        card.add(chips_box)
        card.add(self.show_done)
        card.add(self.empty)
        card.add(self.list, 1)
        self.root.addWidget(card, 1)
        relay.changed.connect(lambda topic: self.refresh() if topic is Topic.IDEAS else None)
        self.refresh()

    def focus_entry(self):
        """Ctrl+I / tray "New idea": straight to typing."""
        self.entry.setFocus()
        self.entry.selectAll()

    def _show_notice(self, text: str, undo: bool = False):
        self.notice.setText(text)
        self.notice.setVisible(bool(text))
        self.undo.setVisible(undo)

    def _add(self):
        text = self.entry.text()
        if not text.strip():
            return
        try:
            self.ideas.add(text)
        except ApplicationError as e:
            self.hint.setText(_(str(e)))
            return
        self.entry.clear()
        self._show_notice(_("Caught."))

    def _tag_chip(self, tag: str):
        chip = QPushButton(f"#{tag}")
        chip.setCheckable(True)
        chip.setChecked(f"#{tag}" in self.search.text().split())
        chip.toggled.connect(lambda on, t=tag: self._toggle_tag(t, on))
        self.chips.addWidget(chip)

    def _toggle_tag(self, tag: str, on: bool):
        words = [w for w in self.search.text().split() if w != f"#{tag}"]
        if on:
            words.append(f"#{tag}")
        self.search.setText(" ".join(words))

    def refresh(self):
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for tag in self.ideas.all_tags()[:MAX_TAG_CHIPS]:
            self._tag_chip(tag)
        self.chips.addStretch(1)

        self.list.blockSignals(True)
        self.list.clear()
        items = self.ideas.ideas(include_done=self.show_done.isChecked(), query=self.search.text())
        for idea in items:
            item = QListWidgetItem(idea.text)
            item.setData(Qt.UserRole, idea.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if idea.done else Qt.Unchecked)
            item.setToolTip(idea.created.strftime("%Y-%m-%d %H:%M"))
            self.list.addItem(item)
        self.list.blockSignals(False)
        searching = bool(self.search.text().strip())
        self.empty.setText(_("Nothing matches. Try fewer words.") if searching
                           else _("No ideas yet. The next one that comes to mind goes here."))
        self.empty.setVisible(not items)
        self.list.setVisible(bool(items))

    def _ticked(self, item: QListWidgetItem):
        self.ideas.set_done(item.data(Qt.UserRole), item.checkState() == Qt.Checked)

    def _edit(self, item: QListWidgetItem):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(self, _("Edit idea"), _("Idea"), item.text())
        if ok and text.strip():
            try:
                self.ideas.edit(item.data(Qt.UserRole), text)
            except ApplicationError as e:
                self._show_notice(_(str(e)))

    def _menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        idea_id = item.data(Qt.UserRole)
        menu = QMenu(self)
        task_today = menu.addAction(_("Make it a task for today"))
        task = menu.addAction(_("Make it a task"))
        note = menu.addAction(_("Make it a note"))
        menu.addSeparator()
        edit = menu.addAction(_("Edit"))
        done = item.checkState() == Qt.Checked
        toggle = menu.addAction(_("Bring back") if done else _("Mark as done"))
        delete = menu.addAction(_("Delete"))
        chosen = exec_menu(menu, self.list.viewport().mapToGlobal(pos))
        try:
            if chosen is task_today:
                self.ideas.to_task(idea_id, date.today())
                self._show_notice(_("Now a task for today."))
            elif chosen is task:
                self.ideas.to_task(idea_id)
                self._show_notice(_("Now a task."))
            elif chosen is note:
                self.ideas.to_note(idea_id)
                self._show_notice(_("Now a note."))
            elif chosen is edit:
                self._edit(item)
            elif chosen is toggle:
                self.ideas.set_done(idea_id, not done)
            elif chosen is delete:
                self._deleted = next((r for r in self.ideas.ideas() if r.id == idea_id), None)
                self.ideas.delete(idea_id)
                self._show_notice(_("Idea deleted."), undo=self._deleted is not None)
        except ApplicationError as e:
            self._show_notice(_(str(e)))

    def _undo(self):
        if self._deleted is not None:
            self.ideas.restore(self._deleted)
            self._deleted = None
        self._show_notice("")
