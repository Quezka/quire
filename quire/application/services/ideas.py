from __future__ import annotations

from datetime import date

from ...domain.ideas import Idea, new_on
from ...domain.errors import NotFound
from ..bus import ChangeBus, Topic
from ..ports import Clock, IdeaRepository
from ..records import IdeaRecord


def _record(i: Idea) -> IdeaRecord:
    return IdeaRecord(i.id, i.text, i.created, i.done)


class IdeaService:
    """Catch an idea in a second; look at them again later (the Ideas page and the daily digest)."""

    def __init__(self, repo: IdeaRepository, clock: Clock, bus: ChangeBus):
        self._repo, self._clock, self._bus = repo, clock, bus

    def ideas(self, include_done: bool = True) -> list[IdeaRecord]:
        """Newest first; the open ones before the ones already dealt with."""
        items = [i for i in self._repo.list() if include_done or not i.done]
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
