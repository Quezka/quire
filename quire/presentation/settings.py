"""More → Settings: appearance, currency and your data."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from .. import __version__
from ..application.services import ReminderSettings, Services
from . import theme
from .formatting import money
from .i18n import LANGUAGES, chosen_language, language, resolve, set_chosen_language
from .preferences import CURRENCIES, preferences
from .i18n import _


def restart_app():
    """Start a fresh Quire and quit this one (the window saves on close)."""
    import sys

    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    if QProcess.startDetached(sys.executable, args):
        for window in QApplication.topLevelWidgets():
            window.close()
        QApplication.quit()


class SettingsDialog(QDialog):
    def __init__(self, services: Services, backup, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle(_("Settings"))
        self.setMinimumWidth(460)

        self.appearance = QComboBox()
        for mode, text in (("system", _("Match system")), ("light", _("Light")),
                           ("dark", _("Dark"))):
            self.appearance.addItem(text, mode)
        self.appearance.setCurrentIndex(max(self.appearance.findData(theme.manager().mode), 0))
        self.appearance.currentIndexChanged.connect(
            lambda: theme.manager().set_mode(self.appearance.currentData()))

        self.currency = QComboBox()
        from PySide6.QtCore import QLocale
        system = QLocale.system().currencySymbol()
        self.currency.addItem(_("System default ({system})").format(system=system), "")
        for code, name, symbol in CURRENCIES:
            self.currency.addItem(f"{_(name)} ({symbol})", code)
        self.currency.setCurrentIndex(max(self.currency.findData(preferences().currency()), 0))
        # currentIndexChanged passes the row number; don't let it land in `save`.
        self.currency.currentIndexChanged.connect(lambda _row: self._currency_picked())
        self.sample = QLabel(objectName="hint")
        self._show_sample()

        self.language = QComboBox()
        for code, name in LANGUAGES:
            self.language.addItem(_(name) if code == "" else name, code)
        self.language.setCurrentIndex(max(self.language.findData(chosen_language()), 0))
        self.language.currentIndexChanged.connect(lambda _row: self._language_picked())
        self.restart = QPushButton(_("Restart now"))
        self.restart.clicked.connect(restart_app)
        self.language_hint = QLabel(objectName="hint")
        self.language_hint.setWordWrap(True)
        language_row = QHBoxLayout()
        language_row.addWidget(self.language, 1)
        language_row.addWidget(self.restart)
        self.restart.setVisible(False)

        reminders = services.reminders.settings()
        self.remind = QComboBox()
        for minutes in services.reminders.CHOICES:
            self.remind.addItem(_("Off") if minutes is None else _("When it starts") if minutes == 0
                                else _("{minutes} min before").format(minutes=minutes), minutes)
        self.remind.setCurrentIndex(max(self.remind.findData(reminders.minutes_before), 0))
        self.remind_events = QCheckBox(_("Events"), checked=reminders.events)
        self.remind_classes = QCheckBox(_("Classes"), checked=reminders.classes)
        self.remind_shifts = QCheckBox(_("Work shifts"), checked=reminders.shifts)
        remind_kinds = QHBoxLayout()
        remind_kinds.setSpacing(18)
        for box in (self.remind_events, self.remind_classes, self.remind_shifts):
            remind_kinds.addWidget(box)
            box.toggled.connect(lambda _on: self._reminders_changed())
        remind_kinds.addStretch()
        self.remind.currentIndexChanged.connect(lambda _row: self._reminders_changed())
        remind_hint = QLabel(_("A desktop notification before things start, while Quire is open."),
                             objectName="hint")
        remind_hint.setWordWrap(True)
        self._reminders_changed(save=False)

        backup_btn = QPushButton(_("Back up data…"))
        backup_btn.clicked.connect(backup)
        folder = QPushButton(_("Open data folder"))
        folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(services.storage.location.parent))))
        data_row = QHBoxLayout()
        data_row.addWidget(backup_btn)
        data_row.addWidget(folder)
        data_row.addStretch()

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow(self._section(_("Look")))
        form.addRow(_("Appearance"), self.appearance)
        form.addRow(_("Language"), language_row)
        form.addRow("", self.language_hint)
        form.addRow(self._section(_("Money")))
        form.addRow(_("Currency"), self.currency)
        form.addRow("", self.sample)
        form.addRow(self._section(_("Reminders")))
        form.addRow(_("Remind me"), self.remind)
        form.addRow(_("For"), remind_kinds)
        form.addRow("", remind_hint)
        form.addRow(self._section(_("Your data")))
        form.addRow("", data_row)
        location = QLabel(str(services.storage.location), objectName="hint")
        location.setWordWrap(True)
        form.addRow(_("Stored in"), location)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel(_("Quire {version}").format(version=__version__), objectName="hint"))
        layout.addWidget(close)

    @staticmethod
    def _section(text: str) -> QLabel:
        return QLabel(_("<b>{text}</b>").format(text=text))

    def _language_picked(self):
        code = self.language.currentData()
        set_chosen_language(code)
        changed = resolve(code) != language()
        self.language_hint.setText(_("Quire needs to restart to switch language.")
                                   if changed else "")
        self.restart.setVisible(changed)

    def _reminders_changed(self, save: bool = True):
        on = self.remind.currentData() is not None
        for box in (self.remind_events, self.remind_classes, self.remind_shifts):
            box.setEnabled(on)
        if save:
            self.services.reminders.save_settings(ReminderSettings(
                self.remind.currentData(), self.remind_events.isChecked(),
                self.remind_classes.isChecked(), self.remind_shifts.isChecked()))

    def _currency_picked(self):
        preferences().set_currency(self.currency.currentData())
        self._show_sample()

    def _show_sample(self):
        self.sample.setText(_("Shows as {amount} per hour").format(amount=money(8.5)))
