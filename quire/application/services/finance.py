from __future__ import annotations


from ...domain import NotFound, ValidationError
from ...domain.finance import (MAX_CENTS, Transaction, by_category, csv_lines, month_bounds, next_month, parse_cents,
                               previous_month)
from ..bus import ChangeBus, Topic
from ..inputs import TransactionInput
from ..ports import Clock, KeyValueStore, TransactionRepository
from ..records import MonthOverview, TransactionRecord


def _record(t: Transaction) -> TransactionRecord:
    return TransactionRecord(t.id, t.day, t.cents, t.income, t.category, t.note)


class FinanceService:
    """Use cases for personal finance: what came in and went out, by month and category. The monthly budget
    stays on each device; the entries sync like everything else."""

    BUDGET = "finance.budget"

    def __init__(self, repository: TransactionRepository, settings: KeyValueStore, clock: Clock, bus: ChangeBus):
        self._repo = repository
        self._settings = settings
        self._clock = clock
        self._bus = bus

    @staticmethod
    def _from(data: TransactionInput, transaction_id: int | None = None) -> Transaction:
        t = Transaction(data.day, parse_cents(data.amount), data.income, data.category.strip(), data.note.strip(),
                        transaction_id)
        t.validate()
        return t

    def add(self, data: TransactionInput) -> int:
        new_id = self._repo.add(self._from(data))
        self._bus.publish(Topic.FINANCE)
        return new_id

    def update(self, transaction_id: int, data: TransactionInput) -> None:
        self._repo.update(self._from(data, transaction_id))
        self._bus.publish(Topic.FINANCE)

    def delete(self, transaction_id: int) -> None:
        self._repo.delete(transaction_id)
        self._bus.publish(Topic.FINANCE)

    def transaction(self, transaction_id: int) -> TransactionRecord:
        t = self._repo.get(transaction_id)
        if t is None:
            raise NotFound("That entry no longer exists.")
        return _record(t)

    def categories(self) -> list[str]:
        return self._repo.categories()

    def budget(self) -> int | None:
        """The monthly spending budget, in cents."""
        try:
            value = int(self._settings.get(self.BUDGET) or 0)
        except ValueError:
            return None
        return value or None

    def set_budget(self, text: str) -> None:
        """As typed ("400,00"); empty: no budget."""
        cents = parse_cents(text) if text.strip() else 0
        if not 0 <= cents <= MAX_CENTS:
            raise ValidationError("Enter an amount greater than zero.")
        self._settings.set(self.BUDGET, str(cents))
        self._bus.publish(Topic.FINANCE)

    @staticmethod
    def previous_month(year: int, month: int) -> tuple[int, int]:
        return previous_month(year, month)

    @staticmethod
    def next_month(year: int, month: int) -> tuple[int, int]:
        return next_month(year, month)

    def month(self, year: int, month: int) -> MonthOverview:
        first, last = month_bounds(year, month)
        items = self._repo.between(first, last)
        income = sum(t.cents for t in items if t.income)
        spent = sum(t.cents for t in items if not t.income)
        return MonthOverview(year, month, income, spent, income - spent, tuple(by_category(items)),
                             tuple(_record(t) for t in reversed(items)), self.budget())

    def csv(self, year: int, month: int) -> list[list[str]]:
        first, last = month_bounds(year, month)
        return csv_lines(self._repo.between(first, last))


