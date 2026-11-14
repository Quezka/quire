"""The main page's quick log: drank water, going to sleep / woke up, medicine taken, an expense. One click each,
with an Undo for the last one. Everything goes through the same use cases as the Water, Sleep, Medicines and
Money pages."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSizePolicy,
    QToolButton, QVBoxLayout,
)

from ...application.errors import ApplicationError
from ...application.inputs import TransactionInput
from ...application.services import Services
from .. import theme
from ..formatting import money
from ..i18n import _
from .common import Card
from quezka_ui.fit import exec_menu


def _litres(ml: int) -> str:
    from PySide6.QtCore import QLocale
    return QLocale().toString(ml / 1000, "f", 1)


class ExpenseDialog(QDialog):
    """Just what an expense needs right now: how much, and what for."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Add an expense"))
        self.amount = QLineEdit(placeholderText=_("e.g. 4,50"))
        self.what = QLineEdit(placeholderText=_("What for (optional)"))
        form = QFormLayout()
        form.addRow(_("Amount"), self.amount)
        form.addRow(_("What"), self.what)
        self.error = QLabel(objectName="danger")
        self.error.setWordWrap(True)
        self.error.hide()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def show_error(self, text: str):
        self.error.setText(text)
        self.error.show()


class QuickLog(Card):
    """Four big buttons in a row, and a line saying what was just logged, with Undo."""

    logged = Signal(str)

    def __init__(self, services: Services, parent=None):
        super().__init__(_("Quick log"), parent=parent)
        self.services = services
        self._undo = None
        row = QHBoxLayout()
        row.setSpacing(8)
        self.water = self._tool("drop")
        self.water.clicked.connect(lambda: self._drink(self.services.water.profile().glass_ml))
        water_menu = QMenu(self.water)
        for ml in (150, 250, 500):
            water_menu.addAction(_("{ml} ml").format(ml=ml), lambda ml=ml: self._drink(ml))
        self._menu_on_right_click(self.water, lambda: water_menu)
        self.sleep = self._tool("moon")
        self.sleep.clicked.connect(self._sleep)
        self.medicine = self._tool("pill")
        self.medicine.clicked.connect(self._medicine_clicked)
        self._pending = []
        self._menu_on_right_click(self.medicine, self._medicine_menu)
        self.expense = self._tool("wallet")
        self.expense.setText(_("Money\nadd an expense"))
        self.expense.clicked.connect(self._expense)
        for b in (self.water, self.sleep, self.medicine, self.expense):
            row.addWidget(b, 1)
        self.body.addLayout(row)
        status = QHBoxLayout()
        self.status = QLabel(objectName="hint")
        self.status.setWordWrap(True)
        self.undo = QPushButton(_("Undo"))
        self.undo.setCursor(Qt.PointingHandCursor)
        self.undo.clicked.connect(self._undo_last)
        status.addWidget(self.status, 1)
        status.addWidget(self.undo)
        self.body.addLayout(status)
        self._clear_status()
        self._fade = QTimer(self, singleShot=True, interval=20_000, timeout=self._clear_status)
        self.refresh()

    @staticmethod
    def _tool(icon: str) -> QToolButton:
        b = QToolButton(objectName="quickLog")
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(64)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        theme.set_icon(b, icon, "accent", size=24)
        return b

    @staticmethod
    def _menu_on_right_click(button: QToolButton, menu):
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos: (m := menu()) and exec_menu(m, button.mapToGlobal(pos)))

    def _medicine_menu(self) -> QMenu | None:
        if len(self._pending) < 2:
            return None
        menu = QMenu(self.medicine)
        for d in self._pending:
            menu.addAction(f"{d.name} · {d.planned // 60:02d}:{d.planned % 60:02d}", lambda d=d: self._take(d))
        return menu

    # ---- what the buttons say ----

    def refresh(self):
        water = self.services.water.overview()
        self.water.setText(_("Water\n{drunk} / {goal} l").format(drunk=_litres(water.drunk), goal=_litres(water.goal))
                           if water.goal else _("Water\n{drunk} l").format(drunk=_litres(water.drunk)))
        self.water.setToolTip(_("Add a glass ({ml} ml). Right-click for other amounts.")
                              .format(ml=self.services.water.profile().glass_ml))
        since = self.services.sleep.asleep_since()
        if since is None:
            self.sleep.setText(_("Sleep\ngoing to bed"))
            self.sleep.setToolTip(_("Starts tonight's sleep now; press again when you wake up."))
        else:
            self.sleep.setText(_("Sleep\nwoke up"))
            self.sleep.setToolTip(_("Asleep since {time}").format(time=f"{since.hour:02d}:{since.minute:02d}"))
        pending = self.services.medicine.pending()
        self.medicine.setEnabled(bool(pending))
        if pending:
            first = pending[0]
            self.medicine.setText(_("Took\n{name}").format(name=first.name))
            self.medicine.setToolTip(_("{name} {dose}, due at {time}").format(
                name=first.name, dose=first.dose, time=f"{first.planned // 60:02d}:{first.planned % 60:02d}").strip())
        else:
            self.medicine.setText(_("Medicines\nnone due"))
            self.medicine.setToolTip("")
        self._pending = pending

    # ---- actions ----

    def _attempt(self, action, message: str, undo) -> bool:
        try:
            action()
        except ApplicationError as e:
            self._say(_(str(e)), None)
            return False
        self._say(message, undo)
        return True

    def _drink(self, ml: int):
        self._attempt(lambda: self.services.water.add(ml), _("Logged {ml} ml of water.").format(ml=ml),
                      self.services.water.undo_last)

    def _sleep(self):
        if self.services.sleep.asleep_since() is None:
            self._attempt(self.services.sleep.go_to_sleep, _("Good night. Press Woke up in the morning."),
                          self.services.sleep.cancel_going_to_sleep)
        else:
            def wake():
                record = self.services.sleep.wake_up()
                self._woke = record
            self._attempt(wake, _("Good morning. Your night is in the Sleep page."),
                          lambda: self.services.sleep.delete(self._woke.day))

    def _medicine_clicked(self):
        pending = self.services.medicine.pending()
        if pending:
            self._take(pending[0])

    def _take(self, dose):
        day = dose.day
        self._attempt(lambda: self.services.medicine.mark(dose.medicine_id, day, dose.planned),
                      _("{name} ticked as taken.").format(name=dose.name),
                      lambda: self.services.medicine.unmark(dose.medicine_id, day, dose.planned))

    def _expense(self):
        dialog = ExpenseDialog(self)
        while dialog.exec():
            try:
                new_id = self.services.finance.add(TransactionInput(
                    self.services.planner.today(), dialog.amount.text(), False, "", dialog.what.text()))
            except ApplicationError as e:
                dialog.show_error(_(str(e)))
                continue
            what = dialog.what.text().strip()
            self._say((_("Spent {amount} on {what}.") if what else _("Spent {amount}."))
                      .format(amount=money(self.services.finance.transaction(new_id).cents / 100), what=what),
                      lambda: self.services.finance.delete(new_id))
            break

    # ---- the status line ----

    def _say(self, text: str, undo):
        self._undo = undo
        self.status.setText(text)
        self.status.show()
        self.undo.setVisible(undo is not None)
        self._fade.start()
        self.refresh()
        self.logged.emit(text)

    def _undo_last(self):
        undo, self._undo = self._undo, None
        if undo is not None:
            try:
                undo()
            except ApplicationError:
                pass
        self._say(_("Undone."), None)

    def _clear_status(self):
        self.status.setText(_("One click logs it; you can undo it here."))
        self.undo.hide()
