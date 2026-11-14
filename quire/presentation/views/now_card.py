"""The one thing now (ADHD-friendly, the suite's concept C inside the tonal look): what's on or next, or else the one
task to do, with one button that starts focusing on it. Done moves straight on to the next step."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from ...application.bus import Topic
from ...application.services import Services
from ..bridge import ChangeRelay
from .. import theme
from ..formatting import fmt_min
from ..i18n import _
from .common import Card, primary_button


def now_next(items, minute: int):
    """The item on at `minute` (if any) and the next one to start."""
    timed = sorted((i for i in items if i.time.end > i.time.start), key=lambda i: i.time.start)
    now = next((i for i in reversed(timed) if i.time.start <= minute < i.time.end), None)
    later = next((i for i in timed if i.time.start > minute and i is not now), None)
    return now, later


class NowCard(Card):
    focusRequested = Signal()  # the user wants to see the focus page

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("nowCard")
        self.services = services
        self.kicker = QLabel(objectName="nowKicker")
        self.headline = QLabel(objectName="nowTitle")
        self.headline.setWordWrap(True)
        self.detail = QLabel(objectName="muted")
        self.focus_btn = primary_button(_("Start focusing"), "play")
        self.focus_btn.clicked.connect(self._focus)
        self.done_btn = QPushButton(_("Done, what's next?"))
        self.done_btn.clicked.connect(self._done)
        row = QHBoxLayout()
        row.addWidget(self.focus_btn)
        row.addWidget(self.done_btn)
        row.addStretch()
        for w in (self.kicker, self.headline, self.detail):
            self.add(w)
        self.body.addLayout(row)
        self._step = None
        # tonal primary container: the card that matters most on the page, calm colours, big words
        theme.themed(lambda t: self.setStyleSheet(
            f"#nowCard {{ background: {t.accent_soft}; border: none; border-radius: {theme.OUTER_RADIUS}px; }}"
            f"#nowCard QLabel {{ color: {getattr(t, 'on_accent_soft', t.text)}; }}"
            f"#nowKicker {{ font-weight: 700; }}"
            f"#nowTitle {{ font-size: 16.5pt; font-weight: 800; }}"))
        relay.changed.connect(lambda topic: self.refresh() if topic in (Topic.TASKS, Topic.EVENTS, Topic.FOCUS) else None)
        self._minute = QTimer(self, interval=60_000, timeout=self.refresh)
        self._minute.start()
        self.refresh()

    def refresh(self):
        planner = self.services.planner
        now_dt = datetime.now()
        agenda = planner.day_agenda(planner.today())
        now, later = now_next(agenda.items, now_dt.hour * 60 + now_dt.minute)
        self._step = self.services.tasks.next_step()
        step = self._step
        self.kicker.setText(_("Now") if now else _("The one thing now"))
        if now:
            self.headline.setText(now.title)
            self.detail.setText(_("until {time}").format(time=fmt_min(now.time.end)))
        elif step:
            self.headline.setText(step.title)
            self.detail.setText(_("Next: {what} at {time}").format(what=later.title, time=fmt_min(later.time.start))
                                if later else "")
        elif later:
            self.headline.setText(later.title)
            self.detail.setText(_("at {time}").format(time=fmt_min(later.time.start)))
        else:
            self.headline.setText(_("Nothing to do right now. Breathe."))
            self.detail.setText("")
        self.detail.setVisible(bool(self.detail.text()))
        show = step is not None and now is None
        self.focus_btn.setVisible(show)
        self.done_btn.setVisible(show)

    def _focus(self):
        if self._step is None:
            return
        focus = self.services.focus
        focus.set_focus_task(self._step.id)
        if not focus.state().running:
            focus.toggle()
        self.focusRequested.emit()

    def _done(self):
        if self._step is not None:
            self.services.tasks.set_done(self._step.id, True)
        self.refresh()
