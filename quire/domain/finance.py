"""Personal finance rules. Pure Python. Amounts are whole cents, so they add up exactly."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .errors import ValidationError

MAX_CENTS = 100_000_000_00  # one entry; more is a typo
UNCATEGORISED = ""


@dataclass
class Transaction:
    day: date
    cents: int  # always positive; `income` says which way it went
    income: bool = False
    category: str = UNCATEGORISED
    note: str = ""
    id: int | None = None

    def validate(self):
        if not 0 < self.cents <= MAX_CENTS:
            raise ValidationError("Enter an amount greater than zero.")

    @property
    def signed(self) -> int:
        return self.cents if self.income else -self.cents


def parse_cents(text: str) -> int:
    """"12,50", "12.5", "1.234,56", "1,234.56" -> cents. The last separator followed by one or two digits is the
    decimal one; any other is only there to group thousands."""
    text = text.strip().replace(" ", "").replace("€", "").replace("$", "").replace("£", "")
    last = max(text.rfind(","), text.rfind("."))
    if last >= 0 and len(text) - last - 1 in (1, 2):
        whole, cents = text[:last], text[last + 1:].ljust(2, "0")
    else:
        whole, cents = text, "00"
    whole = whole.replace(",", "").replace(".", "")
    if not (whole or cents.strip("0")) or not (whole or "0").isdigit() or not cents.isdigit():
        raise ValidationError("Enter an amount like 12,50.")
    return int(whole or "0") * 100 + int(cents)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    return first, next_month - timedelta(days=1)


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def by_category(transactions: list[Transaction]) -> list[tuple[str, int]]:
    """What went out, per category, biggest first."""
    totals: dict[str, int] = {}
    for t in transactions:
        if not t.income:
            totals[t.category] = totals.get(t.category, 0) + t.cents
    return sorted(totals.items(), key=lambda item: (-item[1], item[0].lower()))


def csv_lines(transactions: list[Transaction]) -> list[list[str]]:
    rows = [["date", "amount", "category", "note"]]
    for t in transactions:
        sign = "-" if not t.income else ""
        rows.append([t.day.isoformat(), f"{sign}{t.cents // 100}.{t.cents % 100:02d}", t.category, t.note])
    return rows
