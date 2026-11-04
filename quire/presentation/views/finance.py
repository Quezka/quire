"""Personal finance: a month at a glance, where the money went, and every entry."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.inputs import TransactionInput
from ...application.records import MonthOverview, TransactionRecord
from ...application.services import Services
from ...application.errors import DomainError
from .. import theme
from ..bridge import ChangeRelay
from ..dialogs import _buttons, attempt, confirm, to_qdate
from ..formatting import money, relative_date
from ..i18n import _, month_name
from quezka_ui.widgets import Segmented
from ..widgets import TwoLineDelegate
from .common import Card, Page, StatTile, button, icon_button, label, primary_button, scrolling


def cents_text(cents: int) -> str:
    return money(cents / 100)


class CategoryBars(QWidget):
    """Where the money went: a bar per category, the biggest filling the width."""

    ROW = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: tuple[tuple[str, int], ...] = ()

    def set_rows(self, rows):
        self.rows = rows
        self.setMinimumHeight(self.ROW * len(rows))
        self.setVisible(bool(rows))
        self.update()

    def paintEvent(self, _event):
        if not self.rows:
            return
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        top = self.rows[0][1] or 1
        for i, (name, cents) in enumerate(self.rows):
            y = i * self.ROW
            p.setPen(QColor(t.text))
            p.drawText(QRectF(0, y, self.width() * 0.34 - 8, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(name or _("No category"), Qt.ElideRight, int(self.width() * 0.34 - 8)))
            p.drawText(QRectF(self.width() * 0.72, y, self.width() * 0.28, 18), Qt.AlignRight | Qt.AlignVCenter,
                       cents_text(cents))
            left, width = self.width() * 0.34, self.width() * 0.36
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.hover))
            p.drawRoundedRect(QRectF(left, y + 4, width, 10), 5, 5)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRectF(left, y + 4, max(6.0, width * cents / top), 10), 5, 5)
        p.end()


class TransactionDialog(QDialog):
    def __init__(self, services: Services, record: TransactionRecord | None = None, day: date | None = None, parent=None):
        super().__init__(parent)
        self.finance = services.finance
        self.record = record
        self.setWindowTitle(_("Edit entry") if record else _("New entry"))
        self.setMinimumWidth(340)
        self.kind = Segmented([(False, _("Spent")), (True, _("Received"))])
        self.kind.set_value(record.income if record else False)
        self.amount = QLineEdit(placeholderText="12,50")
        self.day = QDateEdit(calendarPopup=True)
        self.day.setDisplayFormat("ddd d MMM yyyy")
        self.day.setDate(to_qdate(record.day if record else day or services.planner.today()))
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(self.finance.categories())
        self.category.setCurrentText(record.category if record else "")
        self.category.lineEdit().setPlaceholderText(_("e.g. Food"))
        self.note = QLineEdit(placeholderText=_("Note (optional)"))
        form = QFormLayout()
        form.addRow("", self.kind)
        form.addRow(_("Amount"), self.amount)
        form.addRow(_("Date"), self.day)
        form.addRow(_("Category"), self.category)
        form.addRow(_("Note"), self.note)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, self._save, self._delete if record else None))
        if record:
            self.amount.setText(f"{record.cents // 100},{record.cents % 100:02d}")
            self.note.setText(record.note)
        self.amount.setFocus()

    def _save(self):
        def save():
            data = TransactionInput(self.day.date().toPython(), self.amount.text(), bool(self.kind.value()),
                                    self.category.currentText(), self.note.text())
            if self.record:
                self.finance.update(self.record.id, data)
            else:
                self.finance.add(data)

        if attempt(self, save):
            self.accept()

    def _delete(self):
        if confirm(self, _("Delete entry"), _("Delete this entry?")):
            self.finance.delete(self.record.id)
            self.accept()


class FinanceView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.finance = services.finance
        today = services.planner.today()
        self.year, self.month = today.year, today.month
        self.title.setText(_("Money"))

        back = icon_button("chevron-left", _("Previous month"))
        back.clicked.connect(lambda: self.go(*self.finance.previous_month(self.year, self.month)))
        forward = icon_button("chevron-right", _("Next month"))
        forward.clicked.connect(lambda: self.go(*self.finance.next_month(self.year, self.month)))
        self.leading.addWidget(back)
        self.leading.addWidget(forward)
        add = primary_button(_("Add entry"))
        add.clicked.connect(lambda: TransactionDialog(services, day=self._default_day(), parent=self).exec())
        budget = button(_("Budget…"))
        budget.clicked.connect(self._set_budget)
        export = button(_("Export CSV…"), "download")
        export.clicked.connect(self._export)
        self.add_actions(budget, export, add)

        self.income = StatTile(_("Received"))
        self.spent = StatTile(_("Spent"))
        self.balance = StatTile(_("Balance"))
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        for tile in (self.income, self.spent, self.balance):
            tiles.addWidget(tile)

        where = Card(_("Where it went"))
        self.bars = CategoryBars()
        self.nothing = label(_("Nothing spent this month."), "hint")
        where.add(self.bars)
        where.add(self.nothing)
        where.body.addStretch()

        entries = Card(_("Entries"))
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMinimumHeight(260)
        self.list.itemDoubleClicked.connect(self._edit)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        entries.add(self.list, 1)

        row = QHBoxLayout()
        row.setSpacing(18)
        row.addWidget(where, 2)
        row.addWidget(entries, 3)
        column = QVBoxLayout()
        column.setSpacing(14)
        column.addLayout(tiles)
        column.addLayout(row, 1)
        self.root.addWidget(scrolling(column), 1)
        relay.changed.connect(lambda topic: self.refresh() if topic is Topic.FINANCE else None)
        self.refresh()

    def _default_day(self) -> date:
        today = self.services.planner.today()
        return today if (today.year, today.month) == (self.year, self.month) else date(self.year, self.month, 1)

    def go(self, year: int, month: int):
        self.year, self.month = year, month
        self.refresh()

    def refresh(self):
        o: MonthOverview = self.finance.month(self.year, self.month)
        t = theme.current()
        self.title.setText(f"{month_name(date(o.year, o.month, 1)).capitalize()} {o.year}")
        self.income.show(cents_text(o.income))
        over = o.budget is not None and o.spent > o.budget
        detail = ""
        if o.budget is not None:
            detail = (_("{amount} over budget").format(amount=cents_text(o.spent - o.budget)) if over
                      else _("{amount} left of the budget").format(amount=cents_text(o.budget - o.spent)))
        self.spent.show(cents_text(o.spent), detail, t.danger if over else None)
        self.balance.show(cents_text(o.balance), "", t.danger if o.balance < 0 else t.success if o.balance > 0 else None)
        self.subtitle.setText(_("Money in and out, by month"))
        self.bars.set_rows(o.categories)
        self.nothing.setVisible(not o.categories)
        self.list.clear()
        today = self.services.planner.today()
        for r in o.transactions:
            sign = "+" if r.income else "−"
            item = QListWidgetItem(f"{sign}{cents_text(r.cents)}  {r.category or _('No category')}")
            meta = [relative_date(r.day, today)] + ([r.note] if r.note else [])
            item.setData(TwoLineDelegate.META, " · ".join(meta))
            item.setData(TwoLineDelegate.COLOR, t.success if r.income else t.accent)
            item.setData(Qt.UserRole, r.id)
            self.list.addItem(item)

    def _edit(self, item: QListWidgetItem):
        TransactionDialog(self.services, self.finance.transaction(item.data(Qt.UserRole)), parent=self).exec()

    def _menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        edit = menu.addAction(_("Edit…"))
        delete = menu.addAction(_("Delete entry"))
        chosen = menu.exec(self.list.viewport().mapToGlobal(pos))
        if chosen is edit:
            self._edit(item)
        elif chosen is delete and confirm(self, _("Delete entry"), _("Delete this entry?")):
            self.finance.delete(item.data(Qt.UserRole))

    def _set_budget(self):
        current = self.finance.budget()
        text, ok = QInputDialog.getText(self, _("Monthly budget"), _("How much to spend in a month (empty: no budget)"),
                                        text=f"{current // 100},{current % 100:02d}" if current else "")
        if not ok:
            return
        try:
            self.finance.set_budget(text)
        except DomainError as e:
            QMessageBox.warning(self, _("Can't save"), _(str(e)))

    def _export(self):
        folder = QSettings().value("finance/folder", str(Path.home()))
        name = f"{self.year}-{self.month:02d}.csv"
        path, _filter = QFileDialog.getSaveFileName(self, _("Export CSV…"), str(Path(folder) / name), "CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        QSettings().setValue("finance/folder", str(Path(path).parent))
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(self.finance.csv(self.year, self.month))
        except OSError:
            QMessageBox.warning(self, _("Export CSV…"), _("Couldn't save the file there."))
