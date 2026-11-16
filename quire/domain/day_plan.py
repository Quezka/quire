"""Plan my day: put the tasks that need doing into the free time between what's already on.
Pure rules, mirrored by the phone's `domain/DayPlan.kt`."""
from __future__ import annotations

from dataclasses import dataclass

BLOCK = 45  # minutes of work per task <- short enough to start (ADHD rules)
BREAK = 10  # room between blocks and around fixed things
MAX_BLOCKS = 4
DAY_START, DAY_END = 8 * 60, 22 * 60


@dataclass(frozen=True)
class Slot:
    start: int
    end: int
    title: str
    ref: object = None  # the task's id (desktop) or uid (phone)


def free_gaps(busy: list[tuple[int, int]], start: int = DAY_START, end: int = DAY_END,
              pad: int = BREAK) -> list[tuple[int, int]]:
    """Free (start, end) stretches inside [start, end], `pad` minutes kept clear around each busy one."""
    gaps, at = [], start
    for b_start, b_end in sorted(busy):
        b_start, b_end = b_start - pad, b_end + pad
        if b_end <= at:
            continue
        if b_start > at:
            gaps.append((at, min(b_start, end)))
        at = max(at, b_end)
        if at >= end:
            break
    if at < end:
        gaps.append((at, end))
    return [(a, b) for a, b in gaps if b > a]


def plan(tasks: list[tuple[object, str]], busy: list[tuple[int, int]], start: int = DAY_START,
         end: int = DAY_END, block: int = BLOCK, most: int = MAX_BLOCKS) -> list[Slot]:
    """One block per task, in order, in the first free stretch it fits; at most `most`."""
    slots: list[Slot] = []
    gaps = free_gaps(busy, start, end)
    for ref, title in tasks:
        if len(slots) >= most:
            break
        for i, (a, b) in enumerate(gaps):
            if b - a >= block:
                slots.append(Slot(a, a + block, title, ref))
                gaps[i] = (a + block + BREAK, b)
                break
    return slots


def round_up(minute: int, step: int = 15) -> int:
    return -(-minute // step) * step
