from __future__ import annotations

import json
from datetime import date

from ...domain.ideas import Idea, first_line, matches, new_on, resurface, tags
from ...domain.errors import NotFound
from ..bus import ChangeBus, Topic
from ..inputs import TaskInput
from ..ports import Clock, IdeaRepository, KeyValueStore
from ..records import IdeaRecord


def _record(i: Idea) -> IdeaRecord:
    return IdeaRecord(i.id, i.text, i.created, i.done, tuple(tags(i.text)))


class IdeaService:
    """Catch an idea in a second; look at them again later (the Ideas page and the daily digest)."""

    SEEN = "ideas.seen"  # per device: when each idea last came back in the digest

    def __init__(self, repo: IdeaRepository, clock: Clock, bus: ChangeBus, tasks=None, notes=None,
                 settings: KeyValueStore | None = None):
        self._repo, self._clock, self._bus = repo, clock, bus
        self._tasks, self._notes, self._settings = tasks, notes, settings

    def ideas(self, include_done: bool = True, query: str = "") -> list[IdeaRecord]:
        """Newest first; the open ones before the ones already dealt with. `query`: words and #tags."""
        items = [i for i in self._repo.list() if (include_done or not i.done) and matches(i, query)]
        items.sort(key=lambda i: (i.done, -i.created.timestamp()))
        return [_record(i) for i in items]

    def add(self, text: str) -> int:
        idea = Idea(" ".join(text.split()) if "\n" not in text else text.strip(), self._clock.now().replace(microsecond=0))
        idea.validate()
        idea.id = self._repo.add(idea)
        self._bus.publish(Topic.IDEAS)
        return idea.id

    def _get(self, idea_id: int) -> Idea:
        idea = self._repo.get(idea_id)
        if idea is None:
            raise NotFound("That idea no longer exists.")
        return idea

    def edit(self, idea_id: int, text: str):
        idea = self._get(idea_id)
        idea.text = text.strip()
        idea.validate()
        self._repo.update(idea)
        self._bus.publish(Topic.IDEAS)

    def set_done(self, idea_id: int, done: bool):
        idea = self._get(idea_id)
        idea.done = done
        self._repo.update(idea)
        self._bus.publish(Topic.IDEAS)

    def delete(self, idea_id: int):
        self._repo.delete(idea_id)
        self._bus.publish(Topic.IDEAS)

    def caught_between(self, first: date, last: date) -> list[IdeaRecord]:
        return [_record(i) for i in new_on(self._repo.list(), first, last)]

    def all_tags(self) -> list[str]:
        """Tags of the open ideas, most used first."""
        count: dict[str, int] = {}
        for i in self._repo.list():
            if not i.done:
                for t in tags(i.text):
                    count[t] = count.get(t, 0) + 1
        return sorted(count, key=lambda t: (-count[t], t))

    def to_task(self, idea_id: int, due: date | None = None) -> int:
        """Make the idea a task (title = its first line, the rest as details); the idea is then done."""
        idea = self._get(idea_id)
        rest = idea.text.strip().split("\n", 1)
        task_id = self._tasks.save(None, TaskInput(first_line(idea.text) or idea.text[:120], due=due,
                                                   details=rest[1].strip() if len(rest) > 1 else ""))
        self.set_done(idea_id, True)
        return task_id

    def to_note(self, idea_id: int) -> int:
        """Make the idea a note (first line as its heading); the idea is then done."""
        idea = self._get(idea_id)
        lines = idea.text.strip().split("\n", 1)
        body = f"# {lines[0].strip()}" + (f"\n\n{lines[1].strip()}" if len(lines) > 1 else "")
        note = self._notes.create(body)
        self.set_done(idea_id, True)
        return note.id

    def restore(self, record: IdeaRecord) -> int:
        """Undo a delete: the same text and time, back again."""
        idea = Idea(record.text, record.created, record.done)
        idea.id = self._repo.add(idea)
        self._bus.publish(Topic.IDEAS)
        return idea.id

    def resurfaced(self, mark: bool = False) -> IdeaRecord | None:
        """An older open idea worth another look (for the digest); `mark` remembers it was shown today."""
        seen = self._seen()
        today = self._clock.now().date()
        idea = resurface(self._repo.list(), today, seen)
        if idea is not None and mark and self._settings is not None:
            seen[str(idea.id)] = today.isoformat()
            self._settings.set(self.SEEN, json.dumps(seen))
        return _record(idea) if idea is not None else None

    def _seen(self) -> dict[str, str]:
        if self._settings is None:
            return {}
        try:
            value = json.loads(self._settings.get(self.SEEN) or "{}")
            return value if isinstance(value, dict) else {}
        except ValueError:
            return {}
