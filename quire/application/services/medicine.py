from __future__ import annotations

from datetime import date, timedelta

from ...domain import NotFound
from ...domain.medicine import DoseLog, Medicine, due_now, is_late, plan_for
from ..bus import ChangeBus, Topic
from ..inputs import MedicineInput
from ..ports import Clock, MedicineRepository
from ..records import DoseRecord, MedicineRecord, MedicineWeek

WEEK = 7


def _record(m: Medicine) -> MedicineRecord:
    return MedicineRecord(m.id, m.name, m.dose, m.times, m.weekdays, m.active, m.notes)


class MedicineService:
    """Use cases for medicines: what to take and when, what was taken, and a nudge when one is due."""

    def __init__(self, repository: MedicineRepository, clock: Clock, bus: ChangeBus):
        self._repo = repository
        self._clock = clock
        self._bus = bus
        self._reminded: set[tuple] = set()  # (medicine, day, planned) already nudged while Quire is open

    def medicines(self) -> list[MedicineRecord]:
        return [_record(m) for m in self._repo.all()]

    def medicine(self, medicine_id: int) -> MedicineRecord:
        m = self._repo.get(medicine_id)
        if m is None:
            raise NotFound("That medicine no longer exists.")
        return _record(m)

    def save(self, medicine_id: int | None, data: MedicineInput) -> int:
        m = Medicine(data.name.strip(), data.dose.strip(), tuple(sorted(data.times)), tuple(sorted(data.weekdays)),
                     data.active, data.notes, medicine_id)
        m.validate()
        if medicine_id is None:
            m.id = self._repo.add(m)
        else:
            self._repo.update(m)
        self._bus.publish(Topic.MEDICINE)
        return m.id

    def delete(self, medicine_id: int) -> None:
        self._repo.delete(medicine_id)
        self._bus.publish(Topic.MEDICINE)

    def _plan(self, day: date):
        return plan_for(day, self._repo.all(), self._repo.logs_between(day, day))

    def day(self, day: date | None = None) -> list[DoseRecord]:
        day = day or self._clock.today()
        now = self._clock.now()
        minute = now.hour * 60 + now.minute if day == now.date() else (24 * 60 if day < now.date() else -1)
        return [DoseRecord(d.medicine.id, d.medicine.name, d.medicine.dose, d.day, d.planned, d.done,
                           d.log.taken if d.log else False, d.log.at if d.log else None, is_late(d, minute))
                for d in self._plan(day)]

    def pending(self) -> list[DoseRecord]:
        """Today's doses not ticked yet, the next one due first: what "Medicine taken" on the main page offers.
        Extras taken as needed (planned -1) are left out."""
        return sorted((d for d in self.day() if not d.done and d.planned >= 0), key=lambda d: d.planned)

    def mark(self, medicine_id: int, day: date, planned: int, taken: bool = True) -> None:
        """Tick a dose as taken (or as skipped). Doing it again changes it, never adds a second one."""
        now = self._clock.now()
        at = now.hour * 60 + now.minute if day == now.date() else (planned if planned >= 0 else 0)
        existing = next((log for log in self._repo.logs_between(day, day)
                         if log.medicine_id == medicine_id and log.planned == planned), None)
        if existing is not None:
            self._repo.delete_log(existing.id)
        self._repo.add_log(DoseLog(medicine_id, day, planned, taken, at))
        self._bus.publish(Topic.MEDICINE)

    def unmark(self, medicine_id: int, day: date, planned: int) -> None:
        for log in self._repo.logs_between(day, day):
            if log.medicine_id == medicine_id and log.planned == planned:
                self._repo.delete_log(log.id)
        self._bus.publish(Topic.MEDICINE)

    def week(self) -> MedicineWeek:
        """Over the last seven days, today included: how many planned doses were taken."""
        today = self._clock.today()
        planned = taken = 0
        medicines = self._repo.all()
        first = today - timedelta(days=WEEK - 1)
        logs = self._repo.logs_between(first, today)
        now = self._clock.now()
        minute = now.hour * 60 + now.minute
        for i in range(WEEK):
            day = first + timedelta(days=i)
            for dose in plan_for(day, medicines, logs):
                if day == today and not dose.done and dose.planned > minute:
                    continue  # not time for it yet
                if dose.planned >= 0:
                    planned += 1
                    taken += bool(dose.log and dose.log.taken)
        return MedicineWeek(planned, taken)

    def due(self) -> list[DoseRecord]:
        """Doses to nudge about now, each only once. Call about every minute."""
        now = self._clock.now()
        minute = now.hour * 60 + now.minute
        fresh = []
        for d in self._plan(now.date()):
            key = (d.medicine.id, d.day, d.planned)
            if due_now(d, minute) and key not in self._reminded:
                self._reminded.add(key)
                fresh.append(DoseRecord(d.medicine.id, d.medicine.name, d.medicine.dose, d.day, d.planned,
                                        False, False, None, False))
        return fresh
