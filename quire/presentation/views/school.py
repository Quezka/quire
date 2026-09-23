"""School register (Classeviva): connect, sync, grades, lesson topics, what's new."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
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
from ..dialogs import TaskDialog
from ..widgets import SubjectDelegate, TwoLineDelegate, mark_color
from .common import Card, Page, button, icon_button, label, primary_button

AUTO_SYNC_MINUTES = 30


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


class StatTile(Card):
    """A number at the top of the School page with a caption underneath."""

    def __init__(self, caption: str):
        super().__init__(padding=16)
        self.body.setSpacing(4)
        self.caption = QLabel(caption, objectName="tileCaption")
        self.value = QLabel(objectName="tileValue")
        self.detail = label()
        self.detail.setWordWrap(True)
        for widget in (self.caption, self.value, self.detail):
            self.add(widget)
        self.body.addStretch()

    def show(self, value: str, detail: str = "", color: str | None = None):
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.detail.setText(detail)
        self.detail.setToolTip(detail)


class SchoolView(Page):
    newsChanged = Signal(int)  # number of unseen changes from the last sync
    openClassNote = Signal(int, object)  # course_id, date

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
        self._period: str | None = None
        self.periods = QFrame(objectName="segmented")
        self._periods_row = QHBoxLayout(self.periods)
        self._periods_row.setContentsMargins(3, 3, 3, 3)
        self._periods_row.setSpacing(2)
        self._period_buttons = QButtonGroup(self)
        self._period_buttons.setExclusive(True)
        self.add_actions(self.periods, self.sync_btn, self.account_btn)

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
        # ---- summary tiles ----
        self.tile_average = StatTile("AVERAGE")
        self.tile_test = StatTile("NEXT TEST")
        self.tile_homework = StatTile("HOMEWORK THIS WEEK")
        self.tile_attention = StatTile("BELOW 6")
        tiles = QHBoxLayout()
        tiles.setSpacing(16)
        for tile in (self.tile_average, self.tile_test, self.tile_homework,
                     self.tile_attention):
            tiles.addWidget(tile, 1)

        # ---- subjects ----
        subjects = Card("Subjects")
        self.subjects = QListWidget()
        self.subjects.setItemDelegate(SubjectDelegate(self.subjects))
        self.subjects.setMouseTracking(True)
        self.subjects.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.subjects.itemClicked.connect(self._subject_clicked)
        self.grades_empty = label("No grades yet. They'll appear here after a sync.", "hint")
        subjects.add(self.subjects, 1)
        subjects.add(self.grades_empty)
        self._expanded: set[str] = set()

        # ---- side ----
        coming = Card("Homework & tests")
        self.show_done = QPushButton("Show done", objectName="segment", checkable=True)
        self.show_done.setCursor(Qt.PointingHandCursor)
        self.show_done.toggled.connect(lambda _on: self._fill_agenda())
        coming.title_row.addWidget(self.show_done)
        self.coming = QListWidget()
        self.coming.setItemDelegate(TwoLineDelegate(self.coming))
        self.coming.setMouseTracking(True)
        self.coming.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.coming.itemDoubleClicked.connect(self._open_task)
        self.coming.itemChanged.connect(self._agenda_ticked)
        coming.add(self.coming, 1)

        lessons = Card("Lesson topics")
        self.lessons = QListWidget()
        self.lessons.setItemDelegate(TwoLineDelegate(self.lessons))
        self.lessons.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lessons.itemDoubleClicked.connect(self._open_lesson_note)
        self.lessons.setToolTip("Double-click a lesson to open its class notes")
        lessons.add(self.lessons, 1)

        self.news_card = Card("What's new")
        self.news = QListWidget()
        self.news.setWordWrap(True)
        self.news.setResizeMode(QListView.Adjust)
        self.news.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.news_card.add(self.news, 1)

        main = QVBoxLayout()
        main.setSpacing(16)
        main.addWidget(subjects, 3)
        main.addWidget(self.news_card, 1)

        side = QVBoxLayout()
        side.setSpacing(16)
        side.addWidget(coming, 3)
        side.addWidget(lessons, 2)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(main, 3)
        body.addLayout(side, 2)

        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(16)
        column.addLayout(tiles)
        column.addLayout(body, 1)
        return holder

    # ---- state ----------------------------------------------------------------

    def _changed(self, topic: Topic):
        if topic in (Topic.SCHOOL, Topic.COURSES, Topic.TASKS):
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
        for widget in (self.sync_btn, self.account_btn):
            widget.setVisible(status.connected)
        self.sync_btn.setEnabled(self._job is None)
        self._update_subtitle()
        if status.connected:
            self._fill_periods()
            self._fill_tiles()
            self._fill_subjects()
            self._fill_agenda()
            self._fill_lessons()
            self._fill_news()
        else:
            self.periods.setVisible(False)

    # ---- term switcher ----------------------------------------------------------

    def _fill_periods(self):
        periods = self.school.periods()
        if self._period not in periods:
            self._period = None
        for button in self._period_buttons.buttons():
            self._period_buttons.removeButton(button)
            button.deleteLater()
        for text, value in [("All year", None), *[(p, p) for p in periods]]:
            button = QPushButton(text, objectName="segment", checkable=True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(value == self._period)
            button.clicked.connect(lambda _on=False, v=value: self._pick_period(v))
            self._period_buttons.addButton(button)
            self._periods_row.addWidget(button)
        self.periods.setVisible(len(periods) > 1)

    def _pick_period(self, period):
        self._period = period
        self._fill_tiles()
        self._fill_subjects()

    # ---- content ----------------------------------------------------------------

    def _fill_tiles(self):
        t = theme.current()
        today = self.services.planner.today()
        o = self.school.overview(self._period)
        self.tile_average.show(f"{o.average:.2f}" if o.average is not None else "–",
                               plural(o.grade_count, "grade"),
                               mark_color(o.average, t) if o.average is not None else None)
        if o.next_test:
            test = o.next_test
            self.tile_test.show(relative_date(test.task.due, today),
                                (f"{test.course.name}: " if test.course else "") + test.task.title)
        else:
            self.tile_test.show("None", "No tests on the agenda")
        caption = "Nothing due"
        if o.next_homework:
            caption = (f"Next: {relative_date(o.next_homework.task.due, today)} · "
                       + (o.next_homework.course.name if o.next_homework.course
                          else o.next_homework.task.title))
        self.tile_homework.show(str(o.homework_due_this_week), caption)
        if o.below_pass:
            self.tile_attention.show(str(len(o.below_pass)),
                                     ", ".join(s.subject for s in o.below_pass), t.danger)
        else:
            self.tile_attention.show("0", "Every subject is at 6 or above",
                                     t.success if o.grade_count else None)

    def _fill_subjects(self):
        today = self.services.planner.today()
        subjects = self.school.grades_by_subject(self._period)
        scroll = self.subjects.verticalScrollBar().value()
        self.subjects.clear()
        for entry in subjects:
            counted = [g for g in entry.grades if g.counts]
            row = QListWidgetItem(entry.subject)
            row.setData(SubjectDelegate.KIND, "subject")
            row.setData(SubjectDelegate.COLOR, entry.course.color if entry.course else None)
            row.setData(SubjectDelegate.AVERAGE, entry.average)
            row.setData(SubjectDelegate.CHIPS,
                        [(g.display, g.value, g.cancelled) for g in entry.grades[:6]])
            row.setData(SubjectDelegate.TREND, [g.value for g in reversed(counted)])
            expanded = entry.subject in self._expanded
            row.setData(SubjectDelegate.EXPANDED, expanded)
            teachers = entry.course.teacher if entry.course and entry.course.teacher else ""
            row.setData(SubjectDelegate.META, " · ".join(filter(None, [
                plural(len(counted), "grade"), teachers])))
            row.setToolTip("Click to show every grade")
            self.subjects.addItem(row)
            if expanded:
                for g in entry.grades:
                    what = " · ".join(filter(None, [g.component, g.notes])) or "Grade"
                    if g.cancelled:
                        what += " (cancelled)"
                    child = QListWidgetItem(what)
                    child.setData(SubjectDelegate.KIND, "grade")
                    child.setData(SubjectDelegate.CHIPS, [(g.display, g.value, g.cancelled)])
                    child.setData(SubjectDelegate.META, relative_date(g.day, today))
                    child.setFlags(Qt.ItemIsEnabled)
                    if g.notes:
                        child.setToolTip(g.notes)
                    self.subjects.addItem(child)
        self.subjects.verticalScrollBar().setValue(scroll)
        self.subjects.setVisible(bool(subjects))
        self.grades_empty.setVisible(not subjects)

    def _subject_clicked(self, item: QListWidgetItem):
        if item.data(SubjectDelegate.KIND) != "subject":
            return
        self._expanded ^= {item.text()}
        self._fill_subjects()

    def _fill_agenda(self):
        """Homework and tests from the register: overdue first, then day by day."""
        today = self.services.planner.today()
        self.coming.blockSignals(True)
        self.coming.clear()
        last_heading = None
        for entry in self.school.agenda(include_done=self.show_done.isChecked()):
            task = entry.task
            heading = "Overdue" if entry.overdue else relative_date(task.due, today)
            if heading != last_heading:
                last_heading = heading
                header = QListWidgetItem(heading)
                header.setData(TwoLineDelegate.HEADER, 2)
                header.setFlags(Qt.ItemIsEnabled)
                self.coming.addItem(header)
            item = QListWidgetItem(task.title)
            kind = "Test" if task.kind is TaskKind.EXAM else KIND_LABELS[task.kind]
            meta = [entry.course.name if entry.course else "", kind]
            if entry.overdue:
                when = relative_date(task.due, today)
                meta.insert(0, "was due " + (when.lower() if when == "Yesterday" else when))
            item.setData(TwoLineDelegate.META, " · ".join(filter(None, meta)))
            item.setData(TwoLineDelegate.COLOR, entry.course.color if entry.course else None)
            item.setData(TwoLineDelegate.ALERT, entry.overdue)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if task.done else Qt.Unchecked)
            item.setData(Qt.UserRole, task.id)
            item.setToolTip(task.details)
            self.coming.addItem(item)
        if not self.coming.count():
            empty = QListWidgetItem("No homework or tests on the agenda")
            empty.setFlags(Qt.NoItemFlags)
            self.coming.addItem(empty)
        self.coming.blockSignals(False)

    def _agenda_ticked(self, item: QListWidgetItem):
        task_id = item.data(Qt.UserRole)
        if task_id is not None:
            done = item.checkState() == Qt.Checked
            # Deferred: the refresh this triggers rebuilds the list we're inside.
            QTimer.singleShot(0, lambda: self.services.tasks.set_done(task_id, done))

    def _fill_lessons(self):
        today = self.services.planner.today()
        courses = {c.id: c for c in self.services.timetable.courses()}
        self.lessons.clear()
        last_day = None
        for lesson in self.school.recent_lessons():
            if lesson.day != last_day:
                last_day = lesson.day
                header = QListWidgetItem(relative_date(lesson.day, today))
                header.setData(TwoLineDelegate.HEADER, 2)
                header.setFlags(Qt.ItemIsEnabled)
                self.lessons.addItem(header)
            item = QListWidgetItem(lesson.topic or "(no topic recorded)")
            hour = f"hour {lesson.hour}" if lesson.hour else ""
            item.setData(TwoLineDelegate.META, " · ".join(filter(None, [
                lesson.subject, hour, lesson.teacher])))
            course = courses.get(lesson.course_id)
            item.setData(TwoLineDelegate.COLOR, course.color if course else None)
            item.setData(Qt.UserRole, (lesson.course_id, lesson.day))
            item.setToolTip(lesson.topic)
            self.lessons.addItem(item)
        if not self.lessons.count():
            empty = QListWidgetItem("No lessons in the last two weeks")
            empty.setFlags(Qt.NoItemFlags)
            self.lessons.addItem(empty)

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
                    "If you already had one under another name, open it in Week → Timetable "
                    "and pick its subject to merge them.")
        for problem in (report.problems if report else ()):
            item = QListWidgetItem(f"Couldn't sync {problem[0].lower()}{problem[1:]}")
            item.setForeground(QColor(t.danger))
            self.news.addItem(item)
        for line in lines or ["Nothing new since the last sync."]:
            item = QListWidgetItem(line)
            if not lines:
                item.setForeground(QColor(t.faint))
            self.news.addItem(item)

    def _open_task(self, item: QListWidgetItem):
        if item.data(Qt.UserRole) is not None:
            TaskDialog(self.services, item.data(Qt.UserRole), parent=self).exec()

    def _open_lesson_note(self, item: QListWidgetItem):
        target = item.data(Qt.UserRole)
        if target and target[0] is not None:
            self.openClassNote.emit(*target)

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
