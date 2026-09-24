"""Desktop notifications shortly before the next event, class or shift starts."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from ..application.dto import ItemKind
from ..application.services import Reminder, ReminderService
from .formatting import fmt_min, fmt_range
from .i18n import N_, Translated, _
from .notify import notify

KIND_NAMES = Translated({ItemKind.CLASS: N_("Class"), ItemKind.EVENT: N_("Event"),
                         ItemKind.SHIFT: N_("Work shift"), ItemKind.WEEKLY_SHIFT: N_("Work shift")})


def reminder_title(r: Reminder) -> str:
    if r.minutes_left <= 0:
        return _("{title} starts now").format(title=r.item.title)
    return _("{title} in {minutes} min").format(title=r.item.title, minutes=r.minutes_left)


def reminder_body(r: Reminder) -> str:
    item = r.item
    # A shift past midnight comes as its first part, which ends at 24:00: show the start only.
    when = (_("from {time}").format(time=fmt_min(item.time.start))
            if item.time.end >= 24 * 60 else fmt_range(item.time))
    parts = [KIND_NAMES[item.kind], when] + ([item.room] if item.room else [])
    text = " · ".join(parts)
    if item.details.strip():
        text += "\n" + item.details.strip().splitlines()[0]
    return text


class Reminders(QObject):
    """Checks every half minute while Quire is open."""

    INTERVAL_MS = 30_000

    def __init__(self, service: ReminderService, parent=None):
        super().__init__(parent)
        self.service = service
        self.timer = QTimer(self, interval=self.INTERVAL_MS)
        self.timer.timeout.connect(self.check)
        self.timer.start()
        QTimer.singleShot(2000, self.check)

    def check(self):
        for reminder in self.service.due():
            notify(reminder_title(reminder), reminder_body(reminder))
