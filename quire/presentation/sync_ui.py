"""Sync between devices: the background runner, the setup dialog and the status line."""
from __future__ import annotations

import io

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout,
)

from ..application.errors import ApplicationError, DomainError, SyncNotSetUp
from ..application.services import Services, SyncStatus
from .bridge import ChangeRelay
from .formatting import relative_timestamp
from .i18n import _, plural

FIREBASE_CONSOLE = "https://console.firebase.google.com/"
# Each account may read and write only its own folder.
SECURITY_RULES = """rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}"""


def status_text(status: SyncStatus, today) -> str:
    if not status.set_up:
        return _("Off. Sync keeps your timetable, tasks, notes, journal and work shifts the same "
                 "on all your computers.")
    if status.problem:
        return _(status.problem)
    parts = [_("Signed in as {email}").format(email=status.email)]
    if status.last_sync:
        parts.append(_("last synced {when}").format(
            when=relative_timestamp(status.last_sync, today)))
    if status.pending:
        parts.append(_("{changes} waiting").format(changes=plural(status.pending, "change")))
    return " · ".join(parts)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)  # the exception


class _Worker(QRunnable):
    """Runs a network-only call off the UI thread."""

    def __init__(self, call):
        super().__init__()
        self.call = call
        self.signals = _Signals()

    def run(self):
        try:
            self.signals.done.emit(self.call())
        except Exception as e:  # reported on the UI thread; never crash the app
            self.signals.failed.emit(e)


def run_in_background(call, on_done, on_failed) -> _Worker:
    worker = _Worker(call)
    worker.signals.done.connect(on_done)
    worker.signals.failed.connect(on_failed)
    QThreadPool.globalInstance().start(worker)
    return worker


class SyncRunner(QObject):
    """Syncs in the background: at start-up, every few minutes, and shortly after you change
    something. The network part runs on a worker thread; reading and writing the database
    stays on the UI thread."""

    changed = Signal()  # the status line should be redrawn
    INTERVAL_MS = 5 * 60_000
    AFTER_EDIT_MS = 15_000

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self._worker = None
        self._applying = False
        self.timer = QTimer(self, interval=self.INTERVAL_MS)
        self.timer.timeout.connect(self.sync_now)
        self.timer.start()
        self.soon = QTimer(self, singleShot=True, interval=self.AFTER_EDIT_MS)
        self.soon.timeout.connect(self.sync_now)
        relay.changed.connect(self._local_change)
        QTimer.singleShot(3000, self.sync_now)

    @property
    def running(self) -> bool:
        return self._worker is not None

    def _local_change(self, _topic):
        if not self._applying and self.services.sync.status().set_up:
            self.soon.start()

    def sync_now(self):
        if self.running:
            return
        try:
            job = self.services.sync.prepare()
        except SyncNotSetUp:
            return
        self.soon.stop()
        self._worker = run_in_background(lambda: self.services.sync.exchange(job),
                                         self._exchanged, self._failed)
        self.changed.emit()

    def _exchanged(self, exchange):
        self._worker = None
        self._applying = True  # the refreshes this causes aren't new local edits
        try:
            self.services.sync.finish(exchange)
        except ApplicationError as e:
            self.services.sync.failed(e)
        finally:
            self._applying = False
        self.changed.emit()

    def _failed(self, error: Exception):
        self._worker = None
        if not isinstance(error, ApplicationError):
            error = ApplicationError(f"Sync failed unexpectedly: {error}")
        self.services.sync.failed(error)
        self.changed.emit()


class SyncSetupDialog(QDialog):
    """Connect this computer to your Firebase project and account."""

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        self._worker = None
        self.setWindowTitle(_("Set up sync"))
        self.setMinimumWidth(560)

        title = QLabel(_("Sync your computers"), objectName="sheetTitle")
        steps = QLabel(_(
            "Quire syncs through your own free Firebase project. Do this once:"
            "<ol>"
            "<li>In the <a href=\"{console}\">Firebase console</a>, create a project.</li>"
            "<li><b>Authentication</b> → Get started → turn on <b>Email/Password</b>.</li>"
            "<li><b>Firestore Database</b> → Create database (production mode, a location "
            "near you).</li>"
            "<li>In Firestore → <b>Rules</b>, replace the rules with the ones from "
            "<b>Copy security rules</b> below, then Publish.</li>"
            "<li>Project settings → <b>Your apps</b> → add a Web app, then copy its "
            "<b>projectId</b> and <b>apiKey</b> here.</li>"
            "</ol>"
            "On your other computers, use the same project and sign in with the same account."
        ).format(console=FIREBASE_CONSOLE))
        steps.setWordWrap(True)
        steps.setOpenExternalLinks(True)
        steps.setTextFormat(Qt.RichText)
        copy_rules = QPushButton(_("Copy security rules"))
        copy_rules.clicked.connect(self._copy_rules)

        self.project = QLineEdit(placeholderText="quire-sync-1a2b3")
        self.api_key = QLineEdit(placeholderText="AIza…")
        self.email = QLineEdit(placeholderText=_("you@example.com"))
        self.password = QLineEdit(echoMode=QLineEdit.Password)
        status = services.sync.status()
        if status.project_id:
            self.project.setText(status.project_id)
        if status.email:
            self.email.setText(status.email)

        self.create = QPushButton(_("New account"), objectName="segment", checkable=True)
        self.sign_in = QPushButton(_("I already have one"), objectName="segment", checkable=True)
        mode = QFrame(objectName="segmented")
        mode_row = QHBoxLayout(mode)
        mode_row.setContentsMargins(3, 3, 3, 3)
        mode_row.setSpacing(2)
        for choice in (self.create, self.sign_in):
            choice.setAutoExclusive(True)
            choice.setCursor(Qt.PointingHandCursor)
            choice.toggled.connect(self._mode_changed)
            mode_row.addWidget(choice)
        self.take_cloud = QCheckBox(_("Replace this computer's data with the cloud copy"))
        self.take_cloud_hint = QLabel(_("For a second computer: its own timetable, tasks and notes "
                                        "are removed first, so nothing ends up twice."),
                                      objectName="hint")
        self.take_cloud_hint.setWordWrap(True)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow(_("Project ID"), self.project)
        form.addRow(_("Web API key"), self.api_key)
        form.addRow(_("Account"), mode)
        form.addRow(_("Email"), self.email)
        form.addRow(_("Password"), self.password)
        form.addRow("", self.take_cloud)
        form.addRow("", self.take_cloud_hint)

        self.error = QLabel("", objectName="danger")
        self.error.setWordWrap(True)
        self.error.hide()
        cancel = QPushButton(_("Cancel"))
        cancel.clicked.connect(self.reject)
        self.connect_btn = QPushButton(_("Connect"), objectName="primary")
        self.connect_btn.setDefault(True)
        self.connect_btn.clicked.connect(self._connect)
        buttons = QHBoxLayout()
        buttons.addWidget(copy_rules)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.connect_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(steps)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addLayout(buttons)
        (self.sign_in if status.email else self.create).setChecked(True)
        self._mode_changed()

    def _mode_changed(self, *_args):
        signing_in = self.sign_in.isChecked()
        self.take_cloud.setVisible(signing_in)
        self.take_cloud_hint.setVisible(signing_in)
        self.password.setPlaceholderText(_("at least 6 characters") if not signing_in else "")

    def _copy_rules(self):
        QApplication.clipboard().setText(SECURITY_RULES)
        self._show_error("")

    def _show_error(self, text: str):
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def _connect(self):
        if self._worker is not None:
            return
        try:
            config = self.services.sync.check(self.project.text(), self.api_key.text(),
                                              self.email.text(), self.password.text())
        except (ApplicationError, DomainError) as e:
            self._show_error(_(str(e)))
            return
        self._show_error("")
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText(_("Connecting…"))
        email, password, create = self.email.text(), self.password.text(), self.create.isChecked()
        self._config = config
        self._worker = run_in_background(
            lambda: self.services.sync.authenticate(config, email, password, create),
            self._signed_in, self._sign_in_failed)

    def _signed_in(self, session):
        self._worker = None
        self.services.sync.connect(self._config, session,
                                   self.sign_in.isChecked() and self.take_cloud.isChecked())
        self.accept()

    def _sign_in_failed(self, error: Exception):
        self._worker = None
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText(_("Connect"))
        self._show_error(_(str(error)) if isinstance(error, ApplicationError)
                         else _("Sync failed unexpectedly: {error}").format(error=error))


class PhoneSetupDialog(QDialog):
    """Shows the setup code for the phone app as a QR code."""

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle(_("Set up your phone"))
        intro = QLabel(_("Install Quire on your Android phone, open More → Settings → Sync and "
                         "tap “Scan the code”. The phone signs in to the same sync account "
                         "and takes a copy of your data."))
        intro.setWordWrap(True)
        self.include_school = QCheckBox(_("Also set up Classeviva on the phone"))
        has_school = services.school_sync.login_for_phone() is not None
        self.include_school.setChecked(has_school)
        self.include_school.setVisible(has_school)
        self.include_school.toggled.connect(self._show_code)
        self.code = QLabel(alignment=Qt.AlignCenter)
        self.code.setMinimumSize(320, 320)
        warning = QLabel(_("This code signs in to your account: don't share a photo of it."))
        warning.setObjectName("hint")
        warning.setWordWrap(True)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        for widget in (intro, self.include_school, self.code, warning, close):
            layout.addWidget(widget)
        self._show_code()

    def _show_code(self, *_args):
        import segno

        register = (self.services.school_sync.login_for_phone()
                    if self.include_school.isChecked() else None)
        try:
            link = self.services.sync.phone_link(register)
        except ApplicationError as e:
            self.code.setText(_(str(e)))
            return
        # Dark modules on white, whatever the theme: cameras read that best.
        qr = segno.make(link, error="m")
        buffer = io.BytesIO()
        qr.save(buffer, kind="png", scale=8, border=3, dark="#000000", light="#ffffff")
        image = QImage.fromData(buffer.getvalue(), "PNG")
        self.code.setPixmap(QPixmap.fromImage(image).scaled(
            320, 320, Qt.KeepAspectRatio, Qt.FastTransformation))
