"""More → Settings: appearance, currency and your data."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QMessageBox, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from .. import __version__
from ..application.errors import ApplicationError
from ..application.services import ReminderSettings, Services
from . import theme
from .formatting import money
from .notify import play_chime
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
    def __init__(self, services: Services, backup, parent=None, sync_runner=None, updater=None):
        super().__init__(parent)
        self.services = services
        self.sync_runner = sync_runner
        self.updater = updater
        self.setWindowTitle(_("Settings"))
        self.setMinimumWidth(900)

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
        self.chime = QCheckBox(_("Play Quire's chime with notifications"),
                               checked=preferences().notification_sound())
        self.chime.toggled.connect(preferences().set_notification_sound)
        play = QPushButton(_("Play"))
        play.clicked.connect(play_chime)
        chime_row = QHBoxLayout()
        chime_row.addWidget(self.chime)
        chime_row.addWidget(play)
        chime_row.addStretch()
        remind_hint = QLabel(_("A desktop notification before things start, while Quire is open."),
                             objectName="hint")
        remind_hint.setWordWrap(True)
        self._reminders_changed(save=False)

        self.sync_status = QLabel(objectName="hint")
        self.sync_status.setWordWrap(True)
        self.sync_setup = QPushButton()
        self.sync_setup.clicked.connect(self._set_up_sync)
        self.sync_now = QPushButton(_("Sync now"))
        self.sync_now.clicked.connect(self._sync_now)
        self.sync_off = QPushButton(_("Sign out"))
        self.sync_off.clicked.connect(self._sign_out)
        self.sync_phone = QPushButton(_("Set up your phone…"))
        self.sync_phone.clicked.connect(self._set_up_phone)
        sync_row = QHBoxLayout()
        for widget in (self.sync_setup, self.sync_now, self.sync_phone, self.sync_off):
            sync_row.addWidget(widget)
        sync_row.addStretch()
        if sync_runner is not None:
            sync_runner.changed.connect(self._show_sync)
        self._show_sync()

        startup = services.startup
        self.background = QCheckBox(_("Keep running in the background when the window is "
                                      "closed"), checked=startup.background_on_close())
        self.background.toggled.connect(startup.set_background_on_close)
        self.start_on_login = QCheckBox(_("Start Quire when I log in"),
                                        checked=startup.start_on_login())
        self.start_on_login.setEnabled(startup.can_start_on_login())
        self.start_on_login.toggled.connect(self._start_on_login_toggled)
        startup_hint = QLabel(_("In the background, reminders, sync and school updates keep "
                                "working; Quire waits in the system tray."), objectName="hint")
        startup_hint.setWordWrap(True)
        self._startup_rows = (self.background, self.start_on_login, startup_hint)

        self.auto_update = QCheckBox(_("Check for updates automatically"),
                                     checked=services.updates.auto_check())
        self.auto_update.toggled.connect(services.updates.set_auto_check)
        check_now = QPushButton(_("Check now"))
        check_now.clicked.connect(lambda: updater.check_now() if updater else None)
        check_now.setEnabled(updater is not None)
        update_row = QHBoxLayout()
        update_row.addWidget(self.auto_update)
        update_row.addStretch()
        update_row.addWidget(check_now)

        backup_btn = QPushButton(_("Back up data…"))
        backup_btn.clicked.connect(backup)
        folder = QPushButton(_("Open data folder"))
        folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(services.storage.location.parent))))
        data_row = QHBoxLayout()
        data_row.addWidget(backup_btn)
        data_row.addWidget(folder)
        data_row.addStretch()

        # Two columns, so the dialog is wide rather than tall: preferences on the left,
        # sync, updates and data on the right.
        form = QFormLayout()
        form.setVerticalSpacing(12)
        right = QFormLayout()
        right.setVerticalSpacing(12)
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
        form.addRow(_("Sound"), chime_row)

        right.addRow(self._section(_("Sync")))
        right.addRow(self.sync_status)
        right.addRow(sync_row)
        right.addRow(self._section(_("Updates")))
        right.addRow(update_row)
        right.addRow(self._section(_("Startup")))
        for widget in self._startup_rows:
            right.addRow(widget)
        right.addRow(self._section(_("Your data")))
        right.addRow(data_row)
        location = QLabel(str(services.storage.location), objectName="hint")
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addRow(_("Stored in"), location)

        columns = QHBoxLayout()
        columns.setSpacing(36)
        columns.addLayout(form, 1)
        columns.addLayout(right, 1)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel(_("Quire {version}").format(version=__version__),
                                objectName="hint"))
        bottom.addStretch()
        bottom.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.addLayout(columns)
        layout.addStretch()
        layout.addLayout(bottom)

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

    def _show_sync(self):
        from .sync_ui import status_text

        status = self.services.sync.status()
        self.sync_status.setText(status_text(status, self.services.planner.today()))
        self.sync_status.setObjectName("danger" if status.problem else "hint")
        self.sync_status.style().polish(self.sync_status)
        self.sync_setup.setText(_("Set up again…") if status.email else _("Set up sync…"))
        busy = self.sync_runner is not None and self.sync_runner.running
        self.sync_now.setVisible(status.set_up)
        self.sync_now.setEnabled(not busy)
        self.sync_now.setText(_("Syncing…") if busy else _("Sync now"))
        self.sync_off.setVisible(bool(status.email))
        self.sync_phone.setVisible(status.set_up)

    def _set_up_sync(self):
        from .sync_ui import SyncSetupDialog

        if SyncSetupDialog(self.services, self).exec() and self.sync_runner is not None:
            self.sync_runner.sync_now()
        self._show_sync()

    def _set_up_phone(self):
        from .sync_ui import PhoneSetupDialog

        PhoneSetupDialog(self.services, self).exec()

    def _sync_now(self):
        if self.sync_runner is not None:
            self.sync_runner.sync_now()
        self._show_sync()

    def _sign_out(self):
        from .dialogs import confirm

        if confirm(self, _("Sign out of sync"), _("Stop syncing this computer? Its data stays "
                                                    "here, and the cloud copy isn't deleted.")):
            self.services.sync.disconnect()
            self._show_sync()

    def _start_on_login_toggled(self, on: bool):
        try:
            self.services.startup.set_start_on_login(on)
            if on and not self.background.isChecked():
                self.background.setChecked(True)  # it starts in the tray, so it must stay there
        except ApplicationError as e:
            self.start_on_login.blockSignals(True)
            self.start_on_login.setChecked(not on)
            self.start_on_login.blockSignals(False)
            QMessageBox.warning(self, _("Startup"), _(str(e)))

    def _currency_picked(self):
        preferences().set_currency(self.currency.currentData())
        self._show_sample()

    def _show_sample(self):
        self.sample.setText(_("Shows as {amount} per hour").format(amount=money(8.5)))
