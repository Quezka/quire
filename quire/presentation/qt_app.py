"""Starts the Qt event loop around an already-wired set of services."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ..application.services import Services
from .main_window import MainWindow

ICON = Path(__file__).resolve().parent.parent / "assets" / "icon.svg"


def create_application(argv: list[str]) -> QApplication:
    QApplication.setApplicationName("Quire")
    QApplication.setOrganizationName("Quire")
    QApplication.setDesktopFileName("quire")
    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(ICON)))
    return app


def run(services: Services, argv: list[str]) -> int:
    app = create_application(argv)
    window = MainWindow(services)
    window.show()
    return app.exec()
