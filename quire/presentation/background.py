"""Running in the background: the tray icon, and making sure only one Quire runs at a time
(launching it again brings the running one back instead of opening the database twice)."""
from __future__ import annotations

import getpass
import hashlib

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import APP_ID
from .i18n import _
from .icons import APP_ICON


def instance_name(database: str) -> str:
    """One name per user and database, so a `--demo` copy can run next to the real one."""
    digest = hashlib.sha1(database.encode()).hexdigest()[:10]
    return f"{APP_ID}-{getpass.getuser()}-{digest}"


class SingleInstance(QObject):
    """The first Quire listens; later ones ask it to show its window, then exit."""

    activated = Signal()

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.server: QLocalServer | None = None

    def already_running(self) -> bool:
        """True if another Quire answered (and was asked to show itself)."""
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(300):
            socket.write(b"show\n")
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            return True
        return False

    def listen(self) -> None:
        QLocalServer.removeServer(self.name)  # left behind by a crash
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._connection)
        self.server.listen(self.name)

    def _connection(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            connection.readyRead.connect(
                lambda c=connection: (c.readAll(), self.activated.emit()))
            connection.disconnected.connect(connection.deleteLater)


class Tray(QObject):
    """The tray icon: click it to bring Quire back; its menu can quit."""

    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(QIcon(str(APP_ICON)), self)
        self.icon.setToolTip(_("Quire"))
        menu = QMenu()
        open_action = QAction(_("Open Quire"), menu)
        open_action.triggered.connect(self.show_requested)
        quit_action = QAction(_("Quit Quire"), menu)
        quit_action.triggered.connect(self.quit_requested)
        menu.addAction(open_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self):
        self.icon.show()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()

    def tell(self, title: str, text: str):
        self.icon.showMessage(title, text, QIcon(str(APP_ICON)), 6000)


def quit_app():
    QApplication.quit()
