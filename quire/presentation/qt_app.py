"""Starts the Qt event loop around an already-wired set of services."""
from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import APP_ID
from ..application.services import Services
from . import i18n, theme
from .icons import APP_ICON


def create_application(argv: list[str]) -> QApplication:
    QApplication.setApplicationName("Quire")
    QApplication.setOrganizationName("Quire")
    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    i18n.install(app=app)  # before any window is built: texts are translated as they're made
    theme.install(app)
    return app


def run(services: Services, argv: list[str]) -> int:
    from .main_window import MainWindow

    app = create_application(argv)
    window = MainWindow(services)
    window.show()
    return app.exec()
