"""Display preferences that aren't part of your data: currency (and later language)."""
from __future__ import annotations

from PySide6.QtCore import QLocale, QObject, QSettings, Signal

from .i18n import N_

# (ISO code, name, symbol). An empty code means "use the system's".
CURRENCIES = [
    ("EUR", N_("Euro"), "€"),
    ("GBP", N_("Pound sterling"), "£"),
    ("USD", N_("US dollar"), "$"),
    ("CHF", N_("Swiss franc"), "CHF"),
    ("RUB", N_("Russian ruble"), "₽"),
]
SYMBOLS = {code: symbol for code, _name, symbol in CURRENCIES}


class Preferences(QObject):
    changed = Signal(str)  # which preference changed

    def currency(self) -> str:
        """The chosen currency code, or "" to follow the system."""
        return str(QSettings().value("currency", ""))

    def set_currency(self, code: str):
        QSettings().setValue("currency", code)
        self.changed.emit("currency")

    def currency_symbol(self) -> str:
        return SYMBOLS.get(self.currency()) or QLocale.system().currencySymbol()


_preferences: Preferences | None = None


def preferences() -> Preferences:
    global _preferences
    if _preferences is None:
        _preferences = Preferences()
    return _preferences
