"""Water tracking rules. Pure Python.

The daily goal comes from body surface area (Mosteller: sqrt(height cm x weight kg / 3600)
square metres), 1200 ml per square metre, rounded to 50 ml: about 2.2 L for 175 cm and 70 kg.
A rough guide, not medical advice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .errors import ValidationError

ML_PER_SQUARE_METRE = 1200
MIN_GOAL, MAX_GOAL = 1200, 4500
MAX_SIP = 2000  # one entry; more is a typo
DEFAULT_GLASS = 250
DEFAULT_START = 8 * 60  # reminders run between these times of day
DEFAULT_END = 22 * 60
BEHIND_ML = 250  # remind when this far behind the pace
REMIND_EVERY = 90  # minutes between reminders at the least


def water_goal_ml(height_cm: float, weight_kg: float) -> int:
    if not (80 <= height_cm <= 250 and 20 <= weight_kg <= 300):
        raise ValidationError("Enter a height in cm and a weight in kg.")
    area = math.sqrt(height_cm * weight_kg / 3600)
    goal = round(area * ML_PER_SQUARE_METRE / 50) * 50
    return max(MIN_GOAL, min(MAX_GOAL, goal))


@dataclass
class WaterLog:
    day: date
    at: int  # minutes after midnight
    ml: int
    id: int | None = None

    def validate(self):
        if not 0 <= self.at < 24 * 60:
            raise ValidationError("Times must fall within a single day.")
        if not 1 <= self.ml <= MAX_SIP:
            raise ValidationError("Enter an amount between 1 and 2000 ml.")


def expected_ml(goal: int, minute: int, start: int = DEFAULT_START, end: int = DEFAULT_END) -> int:
    """How much should have been drunk by `minute`, spread evenly across the waking day."""
    if minute <= start:
        return 0
    if minute >= end:
        return goal
    return round(goal * (minute - start) / (end - start))


def reminder_due(goal: int, drunk: int, minute: int, last_reminder: int | None,
                 start: int = DEFAULT_START, end: int = DEFAULT_END) -> bool:
    """Remind while you're awake, behind the pace, below the goal, and not just reminded."""
    if not start <= minute < end or drunk >= goal:
        return False
    if last_reminder is not None and 0 <= minute - last_reminder < REMIND_EVERY:
        return False
    return expected_ml(goal, minute, start, end) - drunk >= BEHIND_ML
