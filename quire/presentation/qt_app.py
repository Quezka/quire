"""Starts the Qt event loop around an already-wired set of services."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication
from quezka_ui.app import create_application as _create

from .. import APP_ID, APP_NAME
from ..application.services import Services
from .i18n import _

ICON = Path(__file__).resolve().parent.parent / "assets" / "icon.svg"


def create_application(argv: list[str]) -> QApplication:
    return _create(argv, name=APP_NAME, app_id=APP_ID, icon=ICON, locale_package="quire.presentation.locales")


def run(services: Services, argv: list[str], background: bool = False,
        app: QApplication | None = None, splash=None) -> int:
    from .background import SingleInstance, Tray, instance_name
    from . import notify
    from .main_window import MainWindow

    app = app or create_application(argv)
    single = SingleInstance(instance_name(str(services.storage.location)), app)
    if single.already_running():
        if splash is not None:
            splash.close_now()
        return 0  # the running Quire shows its window instead
    single.listen()
    if splash is not None:
        splash.step(_("Building the interface…"), 0.7)

    tray = Tray(app) if Tray.available() else None
    window = MainWindow(services, tray)
    single.activated.connect(window.bring_back)
    notify.on_click(window.bring_back)  # clicking a notification opens Quire
    if tray is not None:
        notify.share_tray(tray.icon)
        tray.show()
        # Closing the window keeps Quire in the tray; quitting is explicit.
        app.setQuitOnLastWindowClosed(False)
    services.startup.refresh_login_item()
    # However Quire quits (Ctrl+Q, the tray, an update, logging out), a focus session
    # under way still adds the minutes spent so far.
    app.aboutToQuit.connect(services.focus.stop)
    # The same for Do Not Disturb: leaving Quire never leaves the desktop silenced.
    from .quiet import QuietRunner
    QuietRunner(services, app)
    services.quiet.release()  # a crash while quiet left it on
    app.aboutToQuit.connect(services.quiet.release)
    if splash is not None:
        splash.step(_("Ready"), 1.0)
    if not (background and tray is not None):
        window.show()
    if splash is not None:
        splash.finish()
    return app.exec()
