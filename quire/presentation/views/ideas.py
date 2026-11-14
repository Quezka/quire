"""Ideas: catch one in a second (type, Enter), look at them again later."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu

from quezka_ui.fit import exec_menu

from ...application.bus import Topic
from ...application.errors import ApplicationError
from ...application.services import Services
from ..bridge import ChangeRelay
from ..i18n import _
from .common import Card, Page, label, primary_button


class IdeasView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.ideas = services.ideas
        self.title.setText(_("Ideas"))

        self.entry = QLineEdit(placeholderText=_("Jot an idea…"))
        self.entry.returnPressed.connect(self._add)
        add = primary_button(_("Add"), "plus")
        add.clicked.connect(self._add)
        row = QHBoxLayout()
        row.addWidget(self.entry, 1)
        row.addWidget(add)
        self.hint = label(_("Catch it now, look at it later: new ideas come back in the evening digest."), "hint")
        self.hint.setWordWrap(True)

        self.show_done = QCheckBox(_("Show the ones done"))
        self.show_done.toggled.connect(lambda _on: self.refresh())
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemChanged.connect(self._ticked)
        self.empty = label(_("No ideas yet. The next one that comes to mind goes here."), "muted")
        self.empty.setWordWrap(True)

        card = Card()
        card.body.addLayout(row)
        card.add(self.hint)
        card.add(self.show_done)
        card.add(self.empty)
        card.add(self.list, 1)
        self.root.addWidget(card, 1)
        relay.changed.connect(lambda topic: self.refresh() if topic is Topic.IDEAS else None)
        self.refresh()

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

    def refresh(self):
        self.list.blockSignals(True)
        self.list.clear()
        items = self.ideas.ideas(include_done=self.show_done.isChecked())
        for idea in items:
            item = QListWidgetItem(idea.text)
            item.setData(Qt.UserRole, idea.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if idea.done else Qt.Unchecked)
            item.setToolTip(idea.created.strftime("%Y-%m-%d %H:%M"))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.empty.setVisible(not items)
        self.list.setVisible(bool(items))

    def _ticked(self, item: QListWidgetItem):
        self.ideas.set_done(item.data(Qt.UserRole), item.checkState() == Qt.Checked)

    def _menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        done = item.checkState() == Qt.Checked
        toggle = menu.addAction(_("Bring back") if done else _("Mark as done"))
        delete = menu.addAction(_("Delete"))
        chosen = exec_menu(menu, self.list.viewport().mapToGlobal(pos))
        if chosen is toggle:
            self.ideas.set_done(item.data(Qt.UserRole), not done)
        elif chosen is delete:
            self.ideas.delete(item.data(Qt.UserRole))
