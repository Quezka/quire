"""Work shifts: what's coming up, and hours and pay this week and month."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from ...application.bus import Topic
from ...application.dto import WorkSummary
from ...application.services import Services
from .. import theme
from ..bridge import ChangeRelay
from ..dialogs import JobsDialog, ShiftDialog
from ..formatting import fmt_duration, fmt_min, money, plural, relative_date
from ..widgets import TwoLineDelegate
from .common import Card, Page, button, label, primary_button


class SummaryCard(Card):
    def __init__(self, title: str):
        super().__init__(title)
        self.hours = QLabel(objectName="stat")
        self.detail = label()
        self.jobs = label()
        self.jobs.setWordWrap(True)
        self.add(self.hours)
        self.add(self.detail)
        self.add(self.jobs)
        self.body.addStretch()

    def show_summary(self, summary: WorkSummary):
        self.hours.setText(fmt_duration(summary.minutes) if summary.minutes else "0 h")
        parts = [plural(summary.shifts, "shift")]
        if summary.pay is not None:
            parts.append(f"≈ {money(summary.pay)}")
        self.detail.setText(" · ".join(parts))
        lines = []
        for total in summary.per_job:
            name = total.job.name if total.job else "Unknown job"
            line = f"{name}: {fmt_duration(total.minutes)}"
            if total.pay is not None:
                line += f" · {money(total.pay)}"
            lines.append(line)
        self.jobs.setText("\n".join(lines))
        self.jobs.setVisible(len(lines) > 1)


class WorkView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.work = services.work
        self.title.setText("Work")

        jobs = button("Jobs", "briefcase")
        jobs.clicked.connect(lambda: JobsDialog(self.services, self).exec())
        add = primary_button("Shift")
        add.clicked.connect(self.new_shift)
        self.add_actions(jobs, add)

        upcoming = Card("Upcoming shifts")
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.itemDoubleClicked.connect(self._open)
        self.empty = label("", "hint")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignCenter)
        upcoming.add(self.list, 1)
        upcoming.add(self.empty, 1)

        self.week = SummaryCard("This week")
        self.month = SummaryCard("This month")
        side = QVBoxLayout()
        side.setSpacing(16)
        side.addWidget(self.week)
        side.addWidget(self.month)
        side.addStretch()

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(upcoming, 3)
        body.addLayout(side, 2)
        self.root.addLayout(body, 1)

        relay.changed.connect(lambda topic: topic is Topic.WORK and self.refresh())
        theme.manager().changed.connect(lambda _t: self.refresh())
        self.refresh()

    def new_shift(self):
        ShiftDialog(self.services, parent=self).exec()

    def _open(self, item: QListWidgetItem):
        shift_id = item.data(Qt.UserRole)
        if shift_id is not None:
            ShiftDialog(self.services, shift_id, parent=self).exec()

    def refresh(self):
        week, month = self.work.week_summary(), self.work.month_summary()
        self.week.show_summary(week)
        self.month.show_summary(month)
        summary = f"This week: {fmt_duration(week.minutes)}" if week.minutes else "No shifts this week"
        if week.pay is not None:
            summary += f" · ≈ {money(week.pay)}"
        self.subtitle.setText(summary)

        today = self.services.planner.today()
        self.list.clear()
        for item in self.work.upcoming():
            shift, job = item.shift, item.job
            end = fmt_min(shift.end % (24 * 60)) + (" (+1)" if shift.ends_next_day else "")
            row = QListWidgetItem(f"{relative_date(shift.day, today)} · "
                                  f"{fmt_min(shift.start)}–{end}")
            meta = [job.name if job else "Shift", f"{fmt_duration(shift.paid_minutes)} paid"]
            if item.pay is not None:
                meta.append(money(item.pay))
            if shift.notes:
                meta.append(shift.notes.splitlines()[0])
            row.setData(Qt.UserRole, shift.id)
            row.setData(TwoLineDelegate.META, " · ".join(meta))
            row.setData(TwoLineDelegate.COLOR, job.color if job else None)
            self.list.addItem(row)
        has_jobs = bool(self.work.jobs())
        self.empty.setText("No upcoming shifts. Add one with the Shift button."
                           if has_jobs else
                           "Add your job under Jobs, then add your shifts. They'll show up in "
                           "Today and Week next to your classes.")
        self.list.setVisible(self.list.count() > 0)
        self.empty.setVisible(self.list.count() == 0)
