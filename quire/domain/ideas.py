"""Ideas: things that come to mind, caught in a second so they don't get lost (the notebook the user kept for them),
then looked at again in the morning and evening digest."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .errors import ValidationError

MAX_IDEA_CHARS = 2000
RESURFACE_AFTER_DAYS = 7  # an open idea this old may come back in the digest
RESURFACE_GAP_DAYS = 14  # and not again sooner than this
_TAG = re.compile(r"(?<![\w#])#(\w[\w-]*)", re.UNICODE)


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


def tags(text: str) -> list[str]:
    """`#school`, `#game`: tags are words in the text, no separate field (same rule as the phone's Ideas.kt)."""
    seen: list[str] = []
    for t in _TAG.findall(text):
        t = t.lower()
        if t not in seen:
            seen.append(t)
    return seen


def matches(idea: Idea, query: str) -> bool:
    """Every word of the query is in the text (case-insensitive); `#tag` words must be tags."""
    text = idea.text.lower()
    own = tags(idea.text)
    for word in query.lower().split():
        if word.startswith("#"):
            if word[1:] not in own:
                return False
        elif word not in text:
            return False
    return True


def resurface(ideas: list[Idea], today: date, seen: dict[str, str]) -> Idea | None:
    """One open idea to look at again: older than a week, not shown in the last two, the longest unseen first.
    `seen` maps an idea's key (str(id) here, uid on the phone) to the ISO day it last came back."""
    def last(i: Idea) -> date | None:
        day = seen.get(str(i.id))
        return date.fromisoformat(day) if day else None

    candidates = [i for i in ideas if not i.done and i.created.date() <= today - timedelta(days=RESURFACE_AFTER_DAYS)
                  and (last(i) is None or last(i) <= today - timedelta(days=RESURFACE_GAP_DAYS))]
    if not candidates:
        return None
    return min(candidates, key=lambda i: (last(i) or date.min, i.created))


def first_line(text: str, limit: int = 120) -> str:
    """A task title from an idea: its first line without tags, cut at a word."""
    line = _TAG.sub("", text.strip().splitlines()[0] if text.strip() else "").strip()
    line = " ".join(line.split())
    if len(line) <= limit:
        return line
    cut = line[:limit].rsplit(" ", 1)[0]
    return cut + "…"
