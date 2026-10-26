from __future__ import annotations

from datetime import timedelta

from ...domain import ValidationError, WaterLog, expected_ml, reminder_due, water_goal_ml
from ...domain.water import DEFAULT_END, DEFAULT_GLASS, DEFAULT_START
from ..bus import ChangeBus, Topic
from ..inputs import WaterProfileInput
from ..ports import Clock, KeyValueStore, WaterRepository
from ..records import WaterEntry, WaterOverview, WaterProfile


class WaterService:
    """Use cases for water tracking: the goal from height and weight, what you drank today,
    and a nudge when you fall behind. The profile stays on each device."""

    PREFIX = "water."

    def __init__(self, logs: WaterRepository, settings: KeyValueStore, clock: Clock, bus: ChangeBus):
        self._logs = logs
        self._settings = settings
        self._clock = clock
        self._bus = bus
        self._last_reminder: int | None = None  # minute of today; forgotten at midnight

    # ---- profile ----

    def profile(self) -> WaterProfile:
        def number(name):
            try:
                return float(self._settings.get(self.PREFIX + name) or "")
            except ValueError:
                return None

        def whole(name, default):
            value = number(name)
            return default if value is None else int(value)

        remind = self._settings.get(self.PREFIX + "remind")
        return WaterProfile(number("height"), number("weight"), whole("glass", DEFAULT_GLASS),
                            remind != "0", whole("start", DEFAULT_START), whole("end", DEFAULT_END))

    def save_profile(self, data: WaterProfileInput) -> int:
        goal = water_goal_ml(data.height_cm, data.weight_kg)  # checks the numbers
        if not 50 <= data.glass_ml <= 1000:
            raise ValidationError("Enter an amount between 50 and 1000 ml.")
        if not 0 <= data.start < data.end <= 24 * 60:
            raise ValidationError("Reminders must start before they end.")
        for name, value in (("height", data.height_cm), ("weight", data.weight_kg),
                            ("glass", data.glass_ml), ("start", data.start), ("end", data.end)):
            self._settings.set(self.PREFIX + name, str(value))
        self._settings.set(self.PREFIX + "remind", "1" if data.remind else "0")
        self._bus.publish(Topic.WATER)
        return goal

    # ---- the log ----

    def add(self, ml: int) -> None:
        now = self._clock.now()
        log = WaterLog(now.date(), now.hour * 60 + now.minute, int(ml))
        log.validate()
        self._logs.add(log)
        self._bus.publish(Topic.WATER)

    def undo_last(self) -> None:
        today = self._clock.today()
        entries = self._logs.between(today, today)
        if entries:
            self._logs.delete(entries[-1].id)
            self._bus.publish(Topic.WATER)

    def delete(self, entry_id: int) -> None:
        self._logs.delete(entry_id)
        self._bus.publish(Topic.WATER)

    def overview(self) -> WaterOverview:
        today = self._clock.today()
        profile = self.profile()
        goal = (water_goal_ml(profile.height_cm, profile.weight_kg)
                if profile.height_cm and profile.weight_kg else None)
        logs = self._logs.between(today - timedelta(days=6), today)
        mine = [log for log in logs if log.day == today]
        drunk = sum(log.ml for log in mine)
        now = self._clock.now()
        expected = (expected_ml(goal, now.hour * 60 + now.minute, profile.start, profile.end)
                    if goal else 0)
        week = tuple((today - timedelta(days=i), sum(log.ml for log in logs if log.day == today - timedelta(days=i)))
                     for i in range(6, -1, -1))
        return WaterOverview(profile, goal, drunk, expected,
                             tuple(WaterEntry(log.id, log.at, log.ml) for log in mine), week)

    # ---- reminders ----

    def reminder(self) -> str | None:
        """A line to show now if you're behind on water, else None. Call about every minute."""
        o = self.overview()
        if not o.profile.remind or o.goal is None:
            return None
        now = self._clock.now()
        minute = now.hour * 60 + now.minute
        if self._last_reminder is not None and self._last_reminder > minute:
            self._last_reminder = None  # a new day
        if not reminder_due(o.goal, o.drunk, minute, self._last_reminder, o.profile.start, o.profile.end):
            return None
        self._last_reminder = minute
        return f"{o.drunk}/{o.goal}"
