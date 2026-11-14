"""Medicines: what to take today, ticking it off, and the list of medicines with their times."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

from ...application.bus import Topic
from ...application.inputs import MedicineInput
from ...application.services import Services
from ...application.errors import ValidationError
from ..bridge import ChangeRelay
from ..dialogs import _buttons, attempt, confirm
from ..formatting import fmt_min
from ..i18n import _, weekday_names
from ..notify import notify
from ..widgets import TwoLineDelegate
from .common import Card, Page, label, primary_button, scrolling
from quezka_ui.fit import exec_menu


def parse_times(text: str) -> tuple[int, ...]:
    """"8:00, 20.30 13" -> minutes after midnight."""
    times = []
    for piece in re.split(r"[,;\s]+", text.strip()):
        if not piece:
            continue
        m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?", piece)
        if not m or int(m[1]) > 23 or int(m[2] or 0) > 59:
            raise ValidationError("Write the times like 8:00, 13:30.")
        times.append(int(m[1]) * 60 + int(m[2] or 0))
    return tuple(times)


class MedicineDialog(QDialog):
    def __init__(self, services: Services, medicine_id=None, parent=None):
        super().__init__(parent)
        self.medicine = services.medicine
        self.medicine_id = medicine_id
        self.setWindowTitle(_("Edit medicine") if medicine_id else _("New medicine"))
        self.setMinimumWidth(357)
        self.name = QLineEdit(placeholderText=_("e.g. Vitamin D"))
        self.dose = QLineEdit(placeholderText=_("e.g. 1 tablet"))
        self.times = QLineEdit(placeholderText=_("e.g. 8:00, 20:00"))
        self.days = []
        days = QHBoxLayout()
        for name in weekday_names():
            box = QCheckBox(name[:3])
            box.setChecked(True)
            self.days.append(box)
            days.addWidget(box)
        self.active = QCheckBox(_("Taking it now"))
        self.active.setChecked(True)
        self.notes = QPlainTextEdit(placeholderText=_("Notes (optional)"))
        self.notes.setFixedHeight(70)
        form = QFormLayout()
        form.addRow(_("Name"), self.name)
        form.addRow(_("Dose"), self.dose)
        form.addRow(_("Times"), self.times)
        form.addRow(_("Days"), days)
        form.addRow("", self.active)
        form.addRow(_("Notes"), self.notes)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, self._save, self._delete if medicine_id else None))
        if medicine_id:
            m = self.medicine.medicine(medicine_id)
            self.name.setText(m.name)
            self.dose.setText(m.dose)
            self.times.setText(", ".join(fmt_min(t) for t in m.times))
            for weekday, box in enumerate(self.days):
                box.setChecked(not m.weekdays or weekday in m.weekdays)
            self.active.setChecked(m.active)
            self.notes.setPlainText(m.notes)

    def _save(self):
        def save():
            chosen = tuple(d for d, box in enumerate(self.days) if box.isChecked())
            data = MedicineInput(self.name.text(), self.dose.text(), parse_times(self.times.text()),
                                 () if len(chosen) == 7 else chosen, self.active.isChecked(),
                                 self.notes.toPlainText())
            self.medicine.save(self.medicine_id, data)

        if attempt(self, save):
            self.accept()

    def _delete(self):
        if confirm(self, _("Delete medicine"), _("Delete this medicine and what you ticked for it?")):
            self.medicine.delete(self.medicine_id)
            self.accept()


class MedicineView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.medicine = services.medicine
        self.title.setText(_("Medicines"))
        add = primary_button(_("Add medicine"))
        add.clicked.connect(lambda: MedicineDialog(services, parent=self).exec())
        self.add_actions(add)

        today = Card(_("Today"))
        self.doses = QListWidget()
        self.doses.setItemDelegate(TwoLineDelegate(self.doses))
        self.doses.setMouseTracking(True)
        self.doses.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.doses.itemChanged.connect(self._ticked)
        self.doses.setContextMenuPolicy(Qt.CustomContextMenu)
        self.doses.customContextMenuRequested.connect(self._dose_menu)
        self.doses.setMinimumHeight(240)
        self.empty = label(_("Nothing to take today."), "hint")
        today.add(self.doses, 1)
        today.add(self.empty)

        mine = Card(_("Your medicines"))
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.itemActivated.connect(self._edit)
        self.list.itemDoubleClicked.connect(self._edit)
        self.list.setMinimumHeight(200)
        mine.add(self.list, 1)
        edit = QPushButton(_("Edit…"))
        edit.clicked.connect(lambda: self.list.currentItem() and self._edit(self.list.currentItem()))
        mine.add(edit)
        mine.add(label(_("Quire only remembers what you tell it: it isn't medical advice, and it doesn't check doses."), "hint"))

        row = QHBoxLayout()
        row.setSpacing(18)
        row.addWidget(today, 3)
        row.addWidget(mine, 2)
        self.root.addWidget(scrolling(row), 1)

        relay.changed.connect(self._changed)
        self.refresh()
        self._timer = QTimer(self, interval=60_000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _changed(self, topic):
        if topic is Topic.MEDICINE:
            self.refresh()

    def _tick(self):
        for dose in self.medicine.due():
            what = f"{dose.name} · {dose.dose}" if dose.dose else dose.name
            notify(_("Time for your medicine"), _("{what}, at {time}").format(what=what, time=fmt_min(dose.planned)))
        self.refresh()  # "late" appears by itself, and midnight starts a new list

    def refresh(self):
        doses = self.medicine.day()
        self.doses.blockSignals(True)
        self.doses.clear()
        for d in doses:
            item = QListWidgetItem(f"{fmt_min(d.planned)}  {d.name}" if d.planned >= 0 else d.name)
            bits = [d.dose] if d.dose else []
            if d.done and d.taken:
                bits.append(_("taken at {time}").format(time=fmt_min(d.at or 0)))
            elif d.done:
                bits.append(_("skipped"))
            elif d.late:
                bits.append(_("late"))
            item.setData(TwoLineDelegate.META, " · ".join(bits))
            item.setData(TwoLineDelegate.ALERT, d.late)
            item.setData(Qt.UserRole, (d.medicine_id, d.day, d.planned))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if d.done and d.taken else Qt.Unchecked)
            self.doses.addItem(item)
        self.doses.blockSignals(False)
        self.doses.setVisible(bool(doses))
        self.empty.setVisible(not doses)

        week = self.medicine.week()
        left = sum(1 for d in doses if not d.done)
        parts = [_("{n} still to take today").format(n=left)] if left else []
        if week.planned:
            parts.append(_("{taken} of {planned} taken this week").format(taken=week.taken, planned=week.planned))
        self.subtitle.setText(" · ".join(parts))

        self.list.clear()
        for m in self.medicine.medicines():
            item = QListWidgetItem(m.name)
            names = weekday_names()
            when = ", ".join(fmt_min(t) for t in m.times) or _("no set time")
            days = "" if not m.weekdays else " · " + ", ".join(names[d][:3] for d in m.weekdays)
            stopped = "" if m.active else " · " + _("not taking it now")
            item.setData(TwoLineDelegate.META, f"{m.dose + ' · ' if m.dose else ''}{when}{days}{stopped}")
            item.setData(Qt.UserRole, m.id)
            self.list.addItem(item)

    def _ticked(self, item: QListWidgetItem):
        medicine_id, day, planned = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.medicine.mark(medicine_id, day, planned, True)
        else:
            self.medicine.unmark(medicine_id, day, planned)

    def _dose_menu(self, pos):
        item = self.doses.itemAt(pos)
        if item is None:
            return
        medicine_id, day, planned = item.data(Qt.UserRole)
        menu = QMenu(self)
        taken = menu.addAction(_("Taken"))
        skipped = menu.addAction(_("Skipped"))
        clear = menu.addAction(_("Not yet"))
        chosen = exec_menu(menu, self.doses.viewport().mapToGlobal(pos))
        if chosen is taken:
            self.medicine.mark(medicine_id, day, planned, True)
        elif chosen is skipped:
            self.medicine.mark(medicine_id, day, planned, False)
        elif chosen is clear:
            self.medicine.unmark(medicine_id, day, planned)

    def _edit(self, item: QListWidgetItem):
        MedicineDialog(self.services, item.data(Qt.UserRole), parent=self).exec()
