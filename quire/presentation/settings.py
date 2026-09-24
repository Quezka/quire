"""More → Settings: appearance, currency and your data."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from .. import __version__
from ..application.services import Services
from . import theme
from .formatting import money
from .preferences import CURRENCIES, preferences


class SettingsDialog(QDialog):
    def __init__(self, services: Services, backup, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)

        self.appearance = QComboBox()
        for mode, text in (("system", "Match system"), ("light", "Light"), ("dark", "Dark")):
            self.appearance.addItem(text, mode)
        self.appearance.setCurrentIndex(max(self.appearance.findData(theme.manager().mode), 0))
        self.appearance.currentIndexChanged.connect(
            lambda: theme.manager().set_mode(self.appearance.currentData()))

        self.currency = QComboBox()
        from PySide6.QtCore import QLocale
        system = QLocale.system().currencySymbol()
        self.currency.addItem(f"System default ({system})", "")
        for code, name, symbol in CURRENCIES:
            self.currency.addItem(f"{name} ({symbol})", code)
        self.currency.setCurrentIndex(max(self.currency.findData(preferences().currency()), 0))
        # currentIndexChanged passes the row number; don't let it land in `save`.
        self.currency.currentIndexChanged.connect(lambda _row: self._currency_picked())
        self.sample = QLabel(objectName="hint")
        self._show_sample()

        backup_btn = QPushButton("Back up data…")
        backup_btn.clicked.connect(backup)
        folder = QPushButton("Open data folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(services.storage.location.parent))))
        data_row = QHBoxLayout()
        data_row.addWidget(backup_btn)
        data_row.addWidget(folder)
        data_row.addStretch()

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow(self._section("Look"))
        form.addRow("Appearance", self.appearance)
        form.addRow(self._section("Money"))
        form.addRow("Currency", self.currency)
        form.addRow("", self.sample)
        form.addRow(self._section("Your data"))
        form.addRow("", data_row)
        location = QLabel(str(services.storage.location), objectName="hint")
        location.setWordWrap(True)
        form.addRow("Stored in", location)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel(f"Quire {__version__}", objectName="hint"))
        layout.addWidget(close)

    @staticmethod
    def _section(text: str) -> QLabel:
        return QLabel(f"<b>{text}</b>")

    def _currency_picked(self):
        preferences().set_currency(self.currency.currentData())
        self._show_sample()

    def _show_sample(self):
        self.sample.setText(f"Shows as {money(8.5)} per hour")
