"""More → Settings: appearance, currency and your data."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget

from .. import __version__
from ..application.errors import ApplicationError
from ..application.services import QuietSettings, ReminderSettings, Services
from . import theme
from .dialogs import attempt
from .formatting import money
from .notify import play_chime
from . import uiscale
from .i18n import LANGUAGES, chosen_language, language, resolve, set_chosen_language
from .preferences import CURRENCIES, preferences
from .i18n import _
from quezka_ui.settings import SettingsWindow, Switch


def restart_app():
    """Start a fresh Quire and quit this one (the window saves on close)."""
    import os
    import sys

    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    from .qt_app import RESTARTING

    args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    os.environ[RESTARTING] = "1"  # the new copy waits for this one to go, rather than asking it to show itself
    if QProcess.startDetached(sys.executable, args):
        for window in QApplication.topLevelWidgets():
            window.close()
        QApplication.quit()


class SettingsDialog(SettingsWindow):
    """Sections on the left (Look, Money, Reminders, Sync, Startup, Your data), cards of rows on the right."""

    def __init__(self, services: Services, backup, parent=None, sync_runner=None, updater=None):
        super().__init__(_("Settings"), _("Close"), parent)
        self.services = services
        self.sync_runner = sync_runner
        self.updater = updater

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

        self.scale = QComboBox()
        for choice in uiscale.CHOICES:
            self.scale.addItem(_("Automatic") if choice == "auto" else f"{choice}%", choice)
        self.scale.setCurrentIndex(max(self.scale.findData(uiscale.chosen()), 0))
        self.scale.currentIndexChanged.connect(lambda _row: self._scale_picked())
        self.scale_hint = QLabel(objectName="hint")
        self.scale_hint.setWordWrap(True)
        self._language_changed = self._scale_changed = False

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
        self.chime = Switch(preferences().notification_sound())
        self.chime.toggled.connect(preferences().set_notification_sound)
        play = QPushButton(_("Play"))
        play.clicked.connect(play_chime)
        chime_row = QHBoxLayout()
        chime_row.setSpacing(10)
        chime_row.addWidget(play)
        chime_row.addWidget(self.chime)
        chime_box = QWidget()
        chime_box.setLayout(chime_row)
        remind_hint = QLabel(_("A desktop notification before things start, while Quire is open."),
                             objectName="hint")
        remind_hint.setWordWrap(True)
        self._reminders_changed(save=False)

        quiet = services.quiet.settings()
        self.calendar_on = Switch(services.calendar.enabled())
        self.calendar_on.toggled.connect(lambda on: attempt(self, lambda: services.calendar.set_enabled(on)))
        calendar_open = QPushButton(_("Open in the calendar app"))
        calendar_open.clicked.connect(lambda: attempt(self, services.calendar.open))
        calendar_row = QHBoxLayout()
        calendar_row.addWidget(calendar_open)
        calendar_row.addStretch()
        calendar_hint = QLabel(_("One way: classes, events, shifts and due dates appear there as Quire changes them. "
                                 "You keep editing them here.") if services.calendar.can_subscribe() else
                               _("Windows has no way to follow a file: each time you open it, your calendar app "
                                 "imports the agenda as it is then."), objectName="hint")
        calendar_hint.setWordWrap(True)
        self.quiet_on = Switch(quiet.enabled)
        self.quiet_classes = QCheckBox(_("Classes"), checked=quiet.classes)
        self.quiet_events = QCheckBox(_("Events"), checked=quiet.events)
        self.quiet_shifts = QCheckBox(_("Work shifts"), checked=quiet.shifts)
        quiet_kinds = QHBoxLayout()
        quiet_kinds.setSpacing(18)
        for box in (self.quiet_classes, self.quiet_events, self.quiet_shifts):
            quiet_kinds.addWidget(box)
            box.toggled.connect(lambda _on: self._quiet_changed())
        quiet_kinds.addStretch()
        self.quiet_on.toggled.connect(lambda _on: self._quiet_changed())
        supported = services.quiet.available()
        quiet_hint = QLabel(
            _("Turns Do Not Disturb on for {desktop} from the start to the end of each one, "
              "while Quire is open, and puts it back afterwards. Milestones and routines "
              "never silence anything.").format(desktop=services.quiet.method())
            if supported else
            _("Quire can't switch Do Not Disturb on this desktop yet (GNOME only for now)."),
            objectName="hint")
        quiet_hint.setWordWrap(True)
        self.quiet_on.setEnabled(supported)
        self._quiet_changed(save=False)

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
        self.background = Switch(startup.background_on_close())
        self.background.toggled.connect(startup.set_background_on_close)
        self.start_on_login = Switch(startup.start_on_login())
        self.start_on_login.setEnabled(startup.can_start_on_login())
        self.start_on_login.toggled.connect(self._start_on_login_toggled)
        startup_hint = QLabel(_("In the background, reminders, sync and school updates keep "
                                "working; Quire waits in the system tray."), objectName="hint")
        startup_hint.setWordWrap(True)

        self.auto_update = Switch(services.updates.auto_check())
        self.auto_update.toggled.connect(services.updates.set_auto_check)
        check_now = QPushButton(_("Check now"))
        check_now.clicked.connect(lambda: updater.check_now() if updater else None)
        check_now.setEnabled(updater is not None)

        backup_btn = QPushButton(_("Back up data…"))
        backup_btn.clicked.connect(backup)
        folder = QPushButton(_("Open data folder"))
        folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(services.storage.location.parent))))
        data_row = QHBoxLayout()
        data_row.addWidget(backup_btn)
        data_row.addWidget(folder)
        data_row.addStretch()

        manager = theme.manager()
        look = self.section(_("Look"), "palette")
        card = look.card()
        card.row(_("Appearance"), self.appearance, stretch_control=True)
        card.switch(_("Glass look"), manager.glass,
                    _("Frosted, see-through surfaces over a soft wash of colour."), manager.set_glass)
        self.contrast = card.switch(_("High contrast (black and white, thick lines)"), manager.contrast,
                                    on_toggled=manager.set_contrast)
        card = look.card()
        language_box = QWidget()
        language_box.setLayout(language_row)
        card.row(_("Language"), language_box, self.language_hint, stretch_control=True)
        card.row(_("Interface size"), self.scale, self.scale_hint, stretch_control=True)

        money_page = self.section(_("Money"), "wallet")
        money_page.card().row(_("Currency"), self.currency, self.sample, stretch_control=True)

        remind_page = self.section(_("Reminders"), "bell")
        card = remind_page.card()
        card.row(_("Remind me"), self.remind, remind_hint, stretch_control=True)
        card.wide(layout=self._labelled(_("For"), remind_kinds))
        card.row(_("Play Quire's chime with notifications"), chime_box)
        card = remind_page.card(_("Do Not Disturb"))
        card.row(_("Silence notifications while things are on"), self.quiet_on, quiet_hint)
        card.wide(layout=self._labelled(_("For"), quiet_kinds))

        sync_page = self.section(_("Sync"), "refresh")
        card = sync_page.card()
        card.wide(self.sync_status)
        card.wide(layout=sync_row)
        card = sync_page.card(_("Calendar"))
        card.row(_("Show my agenda in the computer's calendar"), self.calendar_on, calendar_hint)
        card.wide(layout=calendar_row)

        startup_page = self.section(_("Startup"), "play")
        card = startup_page.card()
        card.row(_("Keep running in the background when the window is closed"), self.background)
        card.row(_("Start Quire when I log in"), self.start_on_login, startup_hint)
        card = startup_page.card(_("Updates"))
        card.row(_("Check for updates automatically"), self.auto_update)
        card.wide(layout=self._end_aligned(check_now))

        data_page = self.section(_("Your data"), "database")
        card = data_page.card()
        location = QLabel(str(services.storage.location))
        card.row(_("Stored in"), None, location)
        card.wide(layout=data_row)
        data_page.add(QLabel(_("Quire {version}").format(version=__version__), objectName="hint"))

    @staticmethod
    def _labelled(text: str, row: QHBoxLayout) -> QHBoxLayout:
        line = QHBoxLayout()
        line.setSpacing(16)
        line.addWidget(QLabel(text, objectName="rowTitle"))
        line.addLayout(row, 1)
        return line

    @staticmethod
    def _end_aligned(widget) -> QHBoxLayout:
        line = QHBoxLayout()
        line.addWidget(widget)
        line.addStretch()
        return line

    def _language_picked(self):
        code = self.language.currentData()
        set_chosen_language(code)
        changed = self._language_changed = resolve(code) != language()
        self.language_hint.setText(_("Quire needs to restart to switch language.")
                                   if changed else "")
        self.restart.setVisible(changed or self._scale_changed)

    def _scale_picked(self):
        uiscale.set_chosen(self.scale.currentData())
        self._scale_changed = True
        self.scale_hint.setText(_("Applies after a restart. Automatic makes everything a little "
                                  "smaller on small screens."))
        self.restart.setVisible(True)

    def _reminders_changed(self, save: bool = True):
        on = self.remind.currentData() is not None
        for box in (self.remind_events, self.remind_classes, self.remind_shifts):
            box.setEnabled(on)
        if save:
            self.services.reminders.save_settings(ReminderSettings(
                self.remind.currentData(), self.remind_events.isChecked(),
                self.remind_classes.isChecked(), self.remind_shifts.isChecked()))

    def _quiet_changed(self, save: bool = True):
        on = self.quiet_on.isChecked() and self.quiet_on.isEnabled()
        for box in (self.quiet_classes, self.quiet_events, self.quiet_shifts):
            box.setEnabled(on)
        if save:
            self.services.quiet.save_settings(QuietSettings(
                self.quiet_on.isChecked(), self.quiet_classes.isChecked(),
                self.quiet_events.isChecked(), self.quiet_shifts.isChecked()))

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
