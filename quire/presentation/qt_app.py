"""Starts the Qt event loop around an already-wired set of services."""
from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import APP_ID
from ..application.services import Services
from . import fit, i18n, theme, uiscale
from .icons import APP_ICON


def create_application(argv: list[str]) -> QApplication:
    QApplication.setApplicationName("Quire")
    QApplication.setOrganizationName("Quire")
    QApplication.setDesktopFileName(APP_ID)
    if QApplication.instance() is None:
        uiscale.apply_before_app()  # Qt reads the scale factor once, as the app is created
    app = QApplication.instance() or QApplication(argv)
    fit.install(app)  # any dialog taller than the screen scrolls
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    i18n.install(app=app)  # before any window is built: texts are translated as they're made
    theme.install(app)
    return app


def run(services: Services, argv: list[str], background: bool = False) -> int:
    from .background import SingleInstance, Tray, instance_name
    from .main_window import MainWindow

    app = create_application(argv)
    single = SingleInstance(instance_name(str(services.storage.location)), app)
    if single.already_running():
        return 0  # the running Quire shows its window instead
    single.listen()

    tray = Tray(app) if Tray.available() else None
    window = MainWindow(services, tray)
    single.activated.connect(window.bring_back)
    if tray is not None:
        tray.show()
        # Closing the window keeps Quire in the tray; quitting is explicit.
        app.setQuitOnLastWindowClosed(False)
    services.startup.refresh_login_item()
    # However Quire quits (Ctrl+Q, the tray, an update, logging out), a focus session
    # under way still adds the minutes spent so far.
    app.aboutToQuit.connect(services.focus.stop)
    if not (background and tray is not None):
        window.show()
    return app.exec()
