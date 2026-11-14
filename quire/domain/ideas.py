"""Ideas: things that come to mind, caught in a second so they don't get lost (the notebook the user kept for them),
then looked at again in the morning and evening digest."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .errors import ValidationError

MAX_IDEA_CHARS = 2000


@dataclass
class Idea:
    text: str
    created: datetime
    done: bool = False  # acted on or let go: out of the way, kept for later
    id: int | None = None

    def validate(self):
        if not self.text.strip():
            raise ValidationError("Write the idea first.")
        if len(self.text) > MAX_IDEA_CHARS:
            raise ValidationError("That's long for an idea: make it a note instead.")


def new_on(ideas: list[Idea], first: date, last: date) -> list[Idea]:
    """Ideas caught between two days (both included), oldest first."""
    return sorted((i for i in ideas if first <= i.created.date() <= last), key=lambda i: i.created)
