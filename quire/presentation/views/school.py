"""School register (Classeviva): connect, sync, grades, lesson topics, what's new."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QStackedWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.errors import ApplicationError
from ...application.services import Services
from ...application.services.school import SyncReport
from ...domain import TaskKind
from .. import theme
from ..bridge import ChangeRelay
from ..formatting import KIND_LABELS, plural, relative_date, relative_timestamp
from ..notify import notify
from ..widgets import TwoLineDelegate, color_icon
from .common import Card, Page, button, icon_button, label, primary_button

AUTO_SYNC_MINUTES = 30


def grade_color(value: float | None, t) -> str:
    if value is None:
        return t.muted
    if value < 6:
        return t.danger
    if value < 7:
        return "#f5a524"
    return t.success


def describe(report: SyncReport) -> list[str]:
    """One line per change, newest kinds first."""
    lines = []
    for task in report.new_tasks:
        lines.append(f"New {KIND_LABELS[task.kind].lower()}: {task.title}")
    for task in report.updated_tasks:
        lines.append(f"Changed: {task.title}")
    for grade in report.new_grades:
        lines.append(f"New grade in {grade.subject}: {grade.display}")
    return lines


class _SyncSignals(QObject):
    done = Signal(object)  # RegisterSnapshot
    failed = Signal(str)


class _FetchJob(QRunnable):
    """Network half of a sync, off the UI thread. Touches no local storage."""

    def __init__(self, services: Services):
        super().__init__()
        self.services = services
        self.signals = _SyncSignals()

    def run(self):
        try:
            self.signals.done.emit(self.services.school.fetch())
        except ApplicationError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:  # never let a worker crash the app
            self.signals.failed.emit(f"Sync failed unexpectedly: {e}")


class SchoolView(Page):
    newsChanged = Signal(int)  # number of unseen changes from the last sync

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.school = services.school
        self.title.setText("School")
        self._job: _FetchJob | None = None
        self._error = ""

        self.sync_btn = button("Sync now", "refresh")
        self.sync_btn.clicked.connect(self.sync)
        self.account_btn = icon_button("more", "Account")
        self.account_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.account_btn)
        menu.addAction("Disconnect account", self._disconnect)
        self.account_btn.setMenu(menu)
        self.add_actions(self.sync_btn, self.account_btn)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_connect())
        self.pages.addWidget(self._build_dashboard())
        self.root.addWidget(self.pages, 1)

        relay.changed.connect(self._changed)
        theme.manager().changed.connect(lambda _t: self.refresh())
        self._auto = QTimer(self, interval=AUTO_SYNC_MINUTES * 60_000, timeout=self._auto_sync)
        self._auto.start()
        self._ticker = QTimer(self, interval=60_000, timeout=self._update_subtitle)
        self._ticker.start()
        self.refresh()
        if self.school.status().connected:
            QTimer.singleShot(2500, self._auto_sync)

    # ---- layout ---------------------------------------------------------------

    def _build_connect(self) -> QWidget:
        name = self.school.status().register
        card = Card(f"Connect {name}", padding=22)
        card.setFixedWidth(460)
        card.body.setSpacing(14)
        intro = label(f"Sign in with your {name} student account. Quire will pull in homework, "
                      "tests, grades and lesson topics, and check for updates every "
                      f"{AUTO_SYNC_MINUTES} minutes while it's open.")
        intro.setWordWrap(True)
        card.add(intro)
        self.username = QLineEdit(placeholderText="e.g. S1234567X or email")
        self.password = QLineEdit(placeholderText="Password", echoMode=QLineEdit.Password)
        self.password.returnPressed.connect(self._connect)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        card.body.addLayout(form)
        self.connect_error = label("", "hint")
        self.connect_error.setWordWrap(True)
        card.add(self.connect_error)
        connect = primary_button("Connect", None)
        connect.clicked.connect(self._connect)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(connect)
        card.body.addLayout(row)
        privacy = label("Your password is kept in your system keyring, not in Quire's data "
                        "file. Quire only talks to web.spaggiari.eu.", "hint")
        privacy.setWordWrap(True)
        card.add(privacy)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()
        holder = QWidget()
        outer = QVBoxLayout(holder)
        outer.addSpacing(30)
        outer.addLayout(row)
        outer.addStretch()
        return holder

    def _build_dashboard(self) -> QWidget:
        grades = Card("Grades")
        self.average = QLabel(objectName="badge")
        grades.title_row.insertWidget(1, self.average)
        self.grades = QTreeWidget()
        self.grades.setHeaderLabels(["SUBJECT", "DATE", "MARK"])
        self.grades.setIndentation(14)
        self.grades.setUniformRowHeights(True)
        head = self.grades.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.grades_empty = label("No grades yet.", "hint")
        grades.add(self.grades, 1)
        grades.add(self.grades_empty)

        news = Card("What's new")
        self.news = QListWidget()
        self.news.setWordWrap(True)
        news.add(self.news, 1)

        lessons = Card("Recent lessons")
        self.lessons = QListWidget()
        self.lessons.setItemDelegate(TwoLineDelegate(self.lessons))
        self.lessons.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lessons.add(self.lessons, 1)

        side = QVBoxLayout()
        side.setSpacing(16)
        side.addWidget(news, 2)
        side.addWidget(lessons, 3)
        holder = QWidget()
        body = QHBoxLayout(holder)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        body.addWidget(grades, 5)
        body.addLayout(side, 4)
        return holder

    # ---- state ----------------------------------------------------------------

    def _changed(self, topic: Topic):
        if topic in (Topic.SCHOOL, Topic.COURSES):
            self.refresh()

    def _update_subtitle(self):
        status = self.school.status()
        if not status.connected:
            self.subtitle.setText(f"Not connected to {status.register}")
            return
        if self._job is not None:
            when = "syncing…"
        elif self._error:
            when = self._error
        elif status.last_sync and self.school.last_report and self.school.last_report.problems:
            when = "synced, but some parts failed (see What's new)"
        elif status.last_sync:
            delta = datetime.now() - status.last_sync
            minutes = int(delta.total_seconds() // 60)
            when = ("synced just now" if minutes < 1 else
                    f"synced {plural(minutes, 'minute')} ago" if minutes < 60 else
                    "synced " + relative_timestamp(status.last_sync,
                                                   self.services.planner.today()).lower())
        else:
            when = "not synced yet"
        who = status.student_name or status.username
        self.subtitle.setText(f"{status.register} · {who} · {when}")

    def refresh(self):
        status = self.school.status()
        self.pages.setCurrentIndex(1 if status.connected else 0)
        self.sync_btn.setVisible(status.connected)
        self.account_btn.setVisible(status.connected)
        self.sync_btn.setEnabled(self._job is None)
        self._update_subtitle()
        if status.connected:
            self._fill_grades()
            self._fill_lessons()
            self._fill_news()

    def _fill_grades(self):
        t = theme.current()
        subjects = self.school.grades_by_subject()
        overall = self.school.overall_average()
        self.average.setText(f"average {overall:.2f}" if overall is not None else "")
        self.average.setVisible(overall is not None)
        today = self.services.planner.today()
        self.grades.clear()
        for entry in subjects:
            avg = f"{entry.average:.2f}" if entry.average is not None else "–"
            parent = QTreeWidgetItem([entry.subject, "", avg])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFont(2, font)
            parent.setForeground(2, QColor(grade_color(entry.average, t)))
            if entry.course:
                parent.setIcon(0, color_icon(entry.course.color, 10))
            self.grades.addTopLevelItem(parent)
            for g in entry.grades:
                what = " · ".join(filter(None, [g.component, g.notes]))
                child = QTreeWidgetItem([what or "Grade", relative_date(g.day, today), g.display])
                child.setForeground(1, QColor(t.muted))
                child.setForeground(2, QColor(t.faint if g.cancelled
                                              else grade_color(g.value, t)))
                if g.cancelled:
                    f = child.font(2)
                    f.setStrikeOut(True)
                    child.setFont(2, f)
                if g.notes:
                    child.setToolTip(0, g.notes)
                parent.addChild(child)
            parent.setExpanded(True)
        self.grades.setVisible(bool(subjects))
        self.grades_empty.setVisible(not subjects)

    def _fill_lessons(self):
        today = self.services.planner.today()
        courses = {c.id: c for c in self.services.timetable.courses()}
        self.lessons.clear()
        for lesson in self.school.recent_lessons():
            item = QListWidgetItem(lesson.topic or "(no topic recorded)")
            hour = f"hour {lesson.hour}" if lesson.hour else ""
            meta = " · ".join(filter(None, [relative_date(lesson.day, today), lesson.subject,
                                            hour]))
            item.setData(TwoLineDelegate.META, meta)
            course = courses.get(lesson.course_id)
            item.setData(TwoLineDelegate.COLOR, course.color if course else None)
            item.setToolTip(lesson.topic)
            self.lessons.addItem(item)
        if not self.lessons.count():
            self.lessons.addItem(QListWidgetItem("No lessons in the last two weeks"))

    def _fill_news(self):
        t = theme.current()
        self.news.clear()
        report = self.school.last_report
        lines = describe(report) if report else []
        if report and report.first_sync:
            lines = [f"Imported {plural(len(report.new_tasks), 'assignment')}, "
                     f"{plural(len(report.new_grades), 'grade')} and "
                     f"{plural(report.lessons, 'lesson')}."]
            if report.courses_created:
                lines.append(
                    f"Added {plural(report.courses_created, 'course')} for your subjects. "
                    "If you already had one under another name, open it in Week → Courses and "
                    "pick its subject to merge them.")
        for problem in (report.problems if report else ()):
            item = QListWidgetItem(f"Couldn't sync {problem[0].lower()}{problem[1:]}")
            item.setForeground(QColor(t.danger))
            self.news.addItem(item)
        for line in lines or ["Nothing new since the last sync."]:
            item = QListWidgetItem(line)
            if not lines:
                item.setForeground(QColor(t.faint))
            self.news.addItem(item)

    # ---- actions ----------------------------------------------------------------

    def _connect(self):
        username, password = self.username.text().strip(), self.password.text()
        if not username or not password:
            self.connect_error.setText("Enter your username and password.")
            return
        self.connect_error.setText("Connecting…")
        QGuiApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        QGuiApplication.processEvents()
        try:
            self.school.connect(username, password)
        except ApplicationError as e:
            self.connect_error.setText(str(e))
            return
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.password.clear()
        self.connect_error.setText("")
        self.sync()

    def _disconnect(self):
        self.school.disconnect()
        self.newsChanged.emit(0)

    def _auto_sync(self):
        if self.school.status().connected:
            self.sync(quiet=True)

    def sync(self, quiet: bool = False):
        if self._job is not None or not self.school.status().connected:
            return
        self._error = ""
        self._quiet = quiet
        self._job = _FetchJob(self.services)
        self._job.signals.done.connect(self._fetched)
        self._job.signals.failed.connect(self._failed)
        self.sync_btn.setEnabled(False)
        self._update_subtitle()
        QThreadPool.globalInstance().start(self._job)

    def _fetched(self, snapshot):
        self._job = None
        try:
            report = self.school.apply(snapshot)
        except ApplicationError as e:
            self._failed(str(e))
            return
        self.refresh()
        lines = describe(report)
        if lines and not report.first_sync:
            self.newsChanged.emit(len(lines))
            title = f"{self.school.status().register}: {plural(len(lines), 'update')}"
            notify(title, "\n".join(lines[:4]) + ("\n…" if len(lines) > 4 else ""))

    def _failed(self, message: str):
        self._job = None
        self._error = message
        self.refresh()
