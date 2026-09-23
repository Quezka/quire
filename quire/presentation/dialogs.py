"""Edit dialogs for courses, events and tasks."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTimeEdit, QVBoxLayout,
)

from ..application.services import Services
from ..domain import (
    EVERY_DAY, WORK_DAYS, ClassSlot, Course, DomainError, Event, Job, Shift, ShiftPattern, Task,
    TaskKind, TimeRange, net_pay,
)
from .formatting import (
    KIND_LABELS, WEEKDAYS, fmt_days, fmt_duration, fmt_min, fmt_range, money, pay_text,
)
from .widgets import (
    PALETTE, AmountEdit, ColorButton, DaysPicker, SpinBox, color_icon, min_to_qtime,
    qtime_to_min,
)


def to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def fill_course_combo(combo: QComboBox, courses: list[Course], none_label: str):
    """(Re)populate a course picker, keeping the current selection if it still exists."""
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(none_label, None)
    for c in courses:
        combo.addItem(color_icon(c.color), c.name, c.id)
    select_data(combo, current)
    combo.blockSignals(False)


def select_data(combo: QComboBox, value):
    idx = combo.findData(value) if value is not None else 0
    combo.setCurrentIndex(max(idx, 0))


def confirm(parent, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.Yes


def attempt(parent, action: Callable[[], object]) -> bool:
    """Run a use case, showing rule violations to the user instead of raising."""
    try:
        action()
    except DomainError as e:
        QMessageBox.warning(parent, "Can't save", str(e))
        return False
    return True


def _time_edit(minutes: int) -> QTimeEdit:
    edit = QTimeEdit(min_to_qtime(minutes))
    edit.setDisplayFormat("HH:mm")
    return edit


def _buttons(dialog: QDialog, on_save, on_delete=None, delete_label="Delete") -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(on_save)
    buttons.rejected.connect(dialog.reject)
    buttons.button(QDialogButtonBox.Save).setObjectName("primary")
    if on_delete:
        delete = buttons.addButton(delete_label, QDialogButtonBox.DestructiveRole)
        delete.setObjectName("danger")
        delete.clicked.connect(on_delete)
    return buttons


class CourseDialog(QDialog):
    def __init__(self, services: Services, course_id=None, parent=None):
        super().__init__(parent)
        self.timetable = services.timetable
        self.school = services.school
        self.course_id = course_id
        self._external_id = None
        self.setWindowTitle("Edit course" if course_id else "New course")
        self.setMinimumWidth(600)

        self.name = QLineEdit(placeholderText="e.g. Biology")
        self.teacher = QLineEdit(placeholderText="optional")
        self.room = QLineEdit(placeholderText="default room, optional")
        used = {c.color for c in self.timetable.courses()}
        self.color = ColorButton(next((c for c in PALETTE if c not in used),
                                      PALETTE[len(used) % len(PALETTE)]))

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Teacher", self.teacher)
        form.addRow("Room", self.room)
        form.addRow("Colour", self.color)

        # Which register subject feeds homework and grades into this course.
        self.subject = None
        links = self.school.subject_links()
        if links:
            register = self.school.status().register
            self.subject = QComboBox()
            self.subject.addItem("Not linked", None)
            for link in links:
                text = link.subject.name
                if link.course and link.course.id != course_id:
                    text += f"   (now in {link.course.name})"
                self.subject.addItem(text, link.subject.external_id)
            self.subject.currentIndexChanged.connect(self._subject_picked)
            hint = QLabel(f"Homework, tests and grades for this {register} subject go into this "
                          "course. Linking merges any course the sync created for it.")
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            form.addRow(f"{register} subject", self.subject)
            form.addRow("", hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Day", "Start", "End", "Room (if different)"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 130)
        self.table.setMinimumHeight(180)

        add = QPushButton("Add class time")
        add.clicked.connect(lambda: self._add_row())
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_rows)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add)
        row_buttons.addWidget(remove)
        row_buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addWidget(QLabel("<b>Weekly timetable</b>"))
        layout.addWidget(self.table)
        layout.addLayout(row_buttons)
        layout.addWidget(_buttons(self, self._save, self._delete if course_id else None,
                                  "Delete course"))

        if course_id:
            c = self.timetable.course(course_id)
            self.name.setText(c.name)
            self.teacher.setText(c.teacher)
            self.room.setText(c.room)
            self.color.setColor(c.color)
            self._external_id = c.external_id
            for s in c.slots:
                self._add_row(s.weekday, s.time.start, s.time.end, s.room)
        if self.subject is not None:
            self.subject.blockSignals(True)
            select_data(self.subject, self._external_id)
            self.subject.blockSignals(False)

    def _subject_picked(self):
        # Naming a new course after its subject saves typing.
        if not self.name.text().strip() and self.subject.currentData():
            self.name.setText(self.subject.currentText().split("   (")[0])

    def _add_row(self, weekday=None, start=None, end=None, room=""):
        row = self.table.rowCount()
        if weekday is None:
            if row:  # Same times as the previous row, on the next day.
                prev_day, start, end, _ = self._row_values(row - 1)
                weekday = (prev_day + 1) % 7
            else:
                weekday, start, end = 0, 9 * 60, 10 * 60
        self.table.insertRow(row)
        day = QComboBox()
        day.addItems(WEEKDAYS)
        day.setCurrentIndex(weekday)
        self.table.setCellWidget(row, 0, day)
        self.table.setCellWidget(row, 1, _time_edit(start))
        self.table.setCellWidget(row, 2, _time_edit(end))
        self.table.setCellWidget(row, 3, QLineEdit(room))

    def _row_values(self, row):
        return (
            self.table.cellWidget(row, 0).currentIndex(),
            qtime_to_min(self.table.cellWidget(row, 1).time()),
            qtime_to_min(self.table.cellWidget(row, 2).time()),
            self.table.cellWidget(row, 3).text().strip(),
        )

    def _remove_rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        for r in rows:
            self.table.removeRow(r)

    def _save(self):
        slots = []
        for r in range(self.table.rowCount()):
            weekday, start, end, room = self._row_values(r)
            try:
                slots.append(ClassSlot(weekday, TimeRange(start, end), room))
            except DomainError as e:
                QMessageBox.warning(self, "Check class times", f"Class time {r + 1}: {e}")
                return
        # Carry the existing link through the save; relinking is a separate use case.
        course = Course(self.name.text().strip(), self.teacher.text().strip(),
                        self.room.text().strip(), self.color.color(), slots, self.course_id,
                        self._external_id)
        if not attempt(self, lambda: self.timetable.save_course(course)):
            return
        chosen = self.subject.currentData() if self.subject is not None else self._external_id
        if chosen != self._external_id and not attempt(
                self, lambda: self.school.link_course(course.id, chosen)):
            return
        self.accept()

    def _delete(self):
        if confirm(self, "Delete course", "Delete this course and its timetable?\n"
                                          "Its notes and tasks are kept, just unlinked."):
            self.timetable.delete_course(self.course_id)
            self.accept()


class CoursesDialog(QDialog):
    """List of courses with add / edit."""

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle("Courses & timetable")
        self.setMinimumSize(480, 380)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._edit)
        add = QPushButton("Add course…")
        add.clicked.connect(self._add)
        edit = QPushButton("Edit…")
        edit.clicked.connect(lambda: self._edit(self.list.currentItem()))
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.accept)

        side = QVBoxLayout()
        side.addWidget(add)
        side.addWidget(edit)
        side.addStretch()
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        body.addLayout(side)
        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addWidget(close)
        self._reload()

    def _reload(self):
        self.list.clear()
        for c in self.services.timetable.courses():
            when = ", ".join(f"{WEEKDAYS[s.weekday][:3]} {fmt_min(s.time.start)}"
                             for s in c.slots) or "no class times yet"
            item = QListWidgetItem(color_icon(c.color, 14), f"{c.name}\n{when}")
            item.setData(Qt.UserRole, c.id)
            self.list.addItem(item)

    def _add(self):
        if CourseDialog(self.services, parent=self).exec():
            self._reload()

    def _edit(self, item):
        if item and CourseDialog(self.services, item.data(Qt.UserRole), self).exec():
            self._reload()


class EventDialog(QDialog):
    def __init__(self, services: Services, event_id=None, day: date | None = None,
                 start: int = 9 * 60, parent=None):
        super().__init__(parent)
        self.planner = services.planner
        self.event_id = event_id
        self.setWindowTitle("Edit event" if event_id else "New event")
        self.setMinimumWidth(420)

        self.title = QLineEdit(placeholderText="What's happening?")
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.start = _time_edit(start)
        self.end = _time_edit(min(start + 60, 24 * 60 - 1))
        self.color = ColorButton("#8a8f98")
        self.details = QPlainTextEdit(placeholderText="Details (optional)")
        self.details.setFixedHeight(90)

        times = QHBoxLayout()
        times.addWidget(self.start)
        times.addWidget(QLabel("to"))
        times.addWidget(self.end)
        times.addStretch()

        form = QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("Date", self.date)
        form.addRow("Time", times)
        form.addRow("Colour", self.color)
        form.addRow("Details", self.details)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, self._save, self._delete if event_id else None))

        if event_id:
            e = self.planner.event(event_id)
            self.title.setText(e.title)
            self.date.setDate(to_qdate(e.day))
            self.start.setTime(min_to_qtime(e.time.start))
            self.end.setTime(min_to_qtime(e.time.end))
            self.color.setColor(e.color)
            self.details.setPlainText(e.details)
        else:
            self.date.setDate(to_qdate(day or self.planner.today()))

    def _save(self):
        def save():
            event = Event(self.date.date().toPython(),
                          TimeRange(qtime_to_min(self.start.time()), qtime_to_min(self.end.time())),
                          self.title.text().strip(), self.details.toPlainText(),
                          self.color.color(), self.event_id)
            self.planner.save_event(event)

        if attempt(self, save):
            self.accept()

    def _delete(self):
        if confirm(self, "Delete event", "Delete this event?"):
            self.planner.delete_event(self.event_id)
            self.accept()


class TaskDialog(QDialog):
    def __init__(self, services: Services, task_id=None, due: date | None = None,
                 course_id=None, kind: TaskKind = TaskKind.TASK, parent=None):
        super().__init__(parent)
        self.tasks = services.tasks
        self.task_id = task_id
        self.setWindowTitle("Edit task" if task_id else "New task")
        self.setMinimumWidth(440)

        self.title = QLineEdit(placeholderText="e.g. Chapter 4 questions")
        self.kind = QComboBox()
        for k, label in KIND_LABELS.items():
            self.kind.addItem(label, k)
        self.course = QComboBox()
        fill_course_combo(self.course, services.timetable.courses(), "No course")
        self.has_due = QCheckBox("Due")
        self.due = QDateEdit(calendarPopup=True)
        self.due.setDisplayFormat("ddd d MMM yyyy")
        self.has_due.toggled.connect(self.due.setEnabled)
        self.completed = QCheckBox("Completed")
        self.details = QPlainTextEdit(placeholderText="Details (optional)")
        self.details.setFixedHeight(90)

        due_row = QHBoxLayout()
        due_row.addWidget(self.has_due)
        due_row.addWidget(self.due, 1)

        form = QFormLayout()
        form.addRow("Title", self.title)
        form.addRow("Type", self.kind)
        form.addRow("Course", self.course)
        form.addRow("Date", due_row)
        form.addRow("Details", self.details)
        form.addRow("", self.completed)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, self._save, self._delete if task_id else None))

        if task_id:
            t = self.tasks.task(task_id)
            self.title.setText(t.title)
            kind, course_id, due = t.kind, t.course_id, t.due
            self.details.setPlainText(t.details)
            self.completed.setChecked(t.done)
        else:
            self.completed.hide()
        select_data(self.kind, kind)
        select_data(self.course, course_id)
        self.has_due.setChecked(due is not None)
        self.due.setEnabled(due is not None)
        self.due.setDate(to_qdate(due or services.planner.today()))

    def _save(self):
        task = Task(self.title.text(), self.kind.currentData(), self.course.currentData(),
                    self.due.date().toPython() if self.has_due.isChecked() else None,
                    self.completed.isChecked(), self.details.toPlainText(), self.task_id)
        if attempt(self, lambda: self.tasks.save(task)):
            self.accept()

    def _delete(self):
        if confirm(self, "Delete task", "Delete this task?"):
            self.tasks.delete(self.task_id)
            self.accept()


def class_menu(parent, services: Services, course_id: int, day: date, pos,
               open_note: Callable[[int, date], None]):
    """Menu shown when a class block is activated in the day or week view."""
    menu = QMenu(parent)
    note = menu.addAction("Open class notes")
    homework = menu.addAction("Add homework…")
    edit = menu.addAction("Edit course…")
    chosen = menu.exec(pos)
    if chosen is note:
        open_note(course_id, day)
    elif chosen is homework:
        due = services.timetable.next_meeting(course_id, day) or day
        TaskDialog(services, due=due, course_id=course_id, kind=TaskKind.HOMEWORK,
                   parent=parent).exec()
    elif chosen is edit:
        CourseDialog(services, course_id, parent).exec()


# Common withholding on student jobs (Italy). Estimates only: the real figure
# depends on the contract and on total yearly income.
DEDUCTION_PRESETS = [
    ("No deductions", 0.0),
    ("Occasional work: ritenuta d'acconto (20%)", 20.0),
    ("Employee: INPS contributions (9.19%)", 9.19),
    ("Custom…", None),
]


class JobDialog(QDialog):
    def __init__(self, services: Services, job_id=None, parent=None):
        super().__init__(parent)
        self.services = services
        self.work = services.work
        self.job_id = job_id
        self.setWindowTitle("Edit job" if job_id else "New job")
        self.setMinimumWidth(620)

        self.name = QLineEdit(placeholderText="e.g. Pizzeria Da Mario")
        used = {j.color for j in self.work.jobs()}
        self.color = ColorButton(next((c for c in reversed(PALETTE) if c not in used), PALETTE[-2]))
        currency = QLocale.system().currencySymbol()
        self.rate = AmountEdit(placeholderText="e.g. 8.50 (optional)")
        rate_row = QHBoxLayout()
        rate_row.addWidget(self.rate, 1)
        rate_row.addWidget(QLabel(f"{currency} per hour, before tax"))

        self.preset = QComboBox()
        for text, value in DEDUCTION_PRESETS:
            self.preset.addItem(text, value)
        self.deductions = AmountEdit(placeholderText="0")
        self.deductions.setMaximumWidth(90)
        deduction_row = QHBoxLayout()
        deduction_row.addWidget(self.preset, 1)
        deduction_row.addWidget(self.deductions)
        deduction_row.addWidget(QLabel("%"))
        self.preset.currentIndexChanged.connect(self._preset_picked)
        self.deductions.textEdited.connect(self._deductions_typed)

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Colour", self.color)
        form.addRow("Hourly pay", rate_row)
        form.addRow("Tax & deductions", deduction_row)
        hint = QLabel("Take-home pay is an estimate: what's really withheld depends on your "
                      "contract and your total income for the year.", objectName="hint")
        hint.setWordWrap(True)
        form.addRow("", hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Days", "Start", "End", "Unpaid break"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setMinimumHeight(160)
        add = QPushButton("Add regular shift")
        add.clicked.connect(lambda: self._add_row())
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_rows)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add)
        row_buttons.addWidget(remove)
        row_buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addWidget(QLabel("<b>Weekly schedule</b>"))
        schedule_hint = QLabel("Shifts you work every week. They show up in Week next to your "
                               "classes. Changes apply from this week on.", objectName="hint")
        schedule_hint.setWordWrap(True)
        layout.addWidget(schedule_hint)
        layout.addWidget(self.table)
        layout.addLayout(row_buttons)
        layout.addWidget(_buttons(self, self._save, self._delete if job_id else None,
                                  "Delete job"))

        if job_id:
            job = self.work.job(job_id)
            self.name.setText(job.name)
            self.color.setColor(job.color)
            self.rate.setAmount(job.hourly_rate)
            self._set_deductions(job.deductions)
            # One row per time slot, with every day it repeats on.
            rows: dict[tuple, list[int]] = {}
            for p in job.active_schedule(services.planner.today()):
                rows.setdefault((p.start, p.duration, p.break_minutes), []).append(p.weekday)
            for (start, duration, pause), days in rows.items():
                self._add_row(days, start, (start + duration) % (24 * 60), pause)
        else:
            self._set_deductions(0.0)

    # ---- deductions ---------------------------------------------------------------

    def _set_deductions(self, value: float):
        self.deductions.setText(f"{value:g}")
        self._deductions_typed()

    def _preset_picked(self):
        value = self.preset.currentData()
        if value is not None:
            self.deductions.setText(f"{value:g}")
        else:
            self.deductions.setFocus()
            self.deductions.selectAll()

    def _deductions_typed(self):
        try:
            value = self.deductions.amount() or 0.0
        except ValueError:
            return
        index = next((i for i, (_, v) in enumerate(DEDUCTION_PRESETS) if v == value),
                     len(DEDUCTION_PRESETS) - 1)
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(index)
        self.preset.blockSignals(False)

    # ---- weekly schedule ------------------------------------------------------------

    def _add_row(self, days=None, start=17 * 60, end=21 * 60, pause=0):
        row = self.table.rowCount()
        if days is None:
            days = WORK_DAYS if not row else []
        self.table.insertRow(row)
        self.table.setCellWidget(row, 0, DaysPicker(days))
        self.table.setCellWidget(row, 1, _time_edit(start))
        self.table.setCellWidget(row, 2, _time_edit(end))
        pause_box = SpinBox(maximum=240, singleStep=5, suffix=" min")
        pause_box.setSpecialValueText("None")
        pause_box.setValue(pause)
        self.table.setCellWidget(row, 3, pause_box)

    def _remove_rows(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.rowCount():
            rows = [self.table.rowCount() - 1]
        for r in rows:
            self.table.removeRow(r)

    def _schedule(self) -> list[ShiftPattern] | None:
        patterns = []
        for r in range(self.table.rowCount()):
            days = self.table.cellWidget(r, 0).days()
            if not days:
                QMessageBox.warning(self, "Pick the days",
                                    f"Regular shift {r + 1} has no days selected.")
                return None
            start = qtime_to_min(self.table.cellWidget(r, 1).time())
            end = qtime_to_min(self.table.cellWidget(r, 2).time())
            pause = self.table.cellWidget(r, 3).value()
            patterns += [ShiftPattern.between(d, start, end, pause) for d in days]
        return patterns

    # ---- save -------------------------------------------------------------------------

    def _save(self):
        try:
            rate = self.rate.amount()
            deductions = self.deductions.amount() or 0.0
        except ValueError:
            QMessageBox.warning(self, "Check the numbers",
                                "Type the hourly pay and deductions as numbers, like 8.50 or "
                                "8,50. Leave the pay empty if you don't want to track it.")
            return
        weekly = self._schedule()
        if weekly is None:
            return
        job = Job(self.name.text(), self.color.color(), rate, self.job_id,
                  deductions=deductions)
        if attempt(self, lambda: self.work.save_job(job, weekly=weekly)):
            self.job_id = job.id
            self.accept()

    def _delete(self):
        if confirm(self, "Delete job", "Delete this job, its weekly schedule and all of its "
                                       "shifts?"):
            self.work.delete_job(self.job_id)
            self.accept()


class JobsDialog(QDialog):
    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle("Jobs & work schedule")
        self.setMinimumSize(460, 340)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._edit)
        add = QPushButton("Add job…")
        add.clicked.connect(self._add)
        edit = QPushButton("Edit…")
        edit.clicked.connect(lambda: self._edit(self.list.currentItem()))
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.accept)
        side = QVBoxLayout()
        side.addWidget(add)
        side.addWidget(edit)
        side.addStretch()
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        body.addLayout(side)
        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addWidget(close)
        self._reload()

    def _reload(self):
        self.list.clear()
        today = self.services.planner.today()
        for job in self.services.work.jobs():
            details = []
            if job.hourly_rate:
                rate = f"{money(job.hourly_rate)} / hour"
                if job.deductions:
                    rate += f" (−{job.deductions:g}%)"
                details.append(rate)
            slots: dict[tuple, list[int]] = {}
            for p in job.active_schedule(today):
                slots.setdefault((p.start, p.duration), []).append(p.weekday)
            details += [f"{fmt_days(days)} {fmt_min(start)}–{fmt_min((start + dur) % 1440)}"
                        for (start, dur), days in slots.items()]
            item = QListWidgetItem(color_icon(job.color, 14),
                                   job.name + "\n" + (" · ".join(details) or "no schedule yet"))
            item.setData(Qt.UserRole, job.id)
            self.list.addItem(item)

    def _add(self):
        if JobDialog(self.services, parent=self).exec():
            self._reload()

    def _edit(self, item):
        if item and JobDialog(self.services, item.data(Qt.UserRole), self).exec():
            self._reload()


class ShiftDialog(QDialog):
    """A one-off shift, a repeating one, or this week's change to a regular shift."""

    REPEAT_NONE, REPEAT_WEEKLY, REPEAT_WORKDAYS, REPEAT_DAILY, REPEAT_CUSTOM = range(5)

    def __init__(self, services: Services, shift_id=None, day: date | None = None,
                 start: int = 17 * 60, parent=None, job_id=None, end: int | None = None,
                 break_minutes: int = 0, replaces: tuple[int, date, int] | None = None):
        super().__init__(parent)
        self.services = services
        self.work = services.work
        self.shift_id = shift_id
        self.replaces = replaces
        self.setWindowTitle("Edit shift" if shift_id else
                            "Change this week's shift" if replaces else "New shift")
        self.setMinimumWidth(480)

        self.job = QComboBox()
        new_job = QPushButton("New job…")
        new_job.clicked.connect(self._new_job)
        job_row = QHBoxLayout()
        job_row.addWidget(self.job, 1)
        job_row.addWidget(new_job)

        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.start = _time_edit(start)
        self.end = _time_edit(end if end is not None else min(start + 4 * 60, 24 * 60 - 1))
        self.next_day = QLabel("", objectName="hint")
        times = QHBoxLayout()
        times.addWidget(self.start)
        times.addWidget(QLabel("to"))
        times.addWidget(self.end)
        times.addWidget(self.next_day)
        times.addStretch()

        self.break_min = SpinBox(maximum=240, singleStep=5, suffix=" min")
        self.break_min.setSpecialValueText("No break")
        self.break_min.setValue(break_minutes)

        self.repeat = QComboBox()
        self.days = DaysPicker()
        self.has_until = QCheckBox("Ends on")
        self.until = QDateEdit(calendarPopup=True)
        self.until.setDisplayFormat("ddd d MMM yyyy")
        self.has_until.toggled.connect(self.until.setEnabled)
        self.until.setEnabled(False)
        until_row = QHBoxLayout()
        until_row.addWidget(self.has_until)
        until_row.addWidget(self.until, 1)

        self.notes = QPlainTextEdit(placeholderText="Notes (optional)")
        self.notes.setFixedHeight(64)
        self.summary = QLabel("", objectName="muted")
        self.clash = QLabel("", objectName="danger")
        self.clash.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Job", job_row)
        form.addRow("Date", self.date)
        form.addRow("Time", times)
        form.addRow("Unpaid break", self.break_min)
        can_repeat = shift_id is None and replaces is None
        if can_repeat:
            form.addRow("Repeat", self.repeat)
            form.addRow("", self.days)
            form.addRow("", until_row)
        form.addRow("Notes", self.notes)
        form.addRow("", self.summary)
        form.addRow("", self.clash)
        self._repeat_rows = [self.days, self.has_until, self.until]

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, self._save, self._delete if shift_id else None))

        self._fill_jobs(select=job_id)
        if shift_id:
            shift = self.work.shift(shift_id)
            select_data(self.job, shift.job_id)
            self.date.setDate(to_qdate(shift.day))
            self.start.setTime(min_to_qtime(shift.start))
            self.end.setTime(min_to_qtime(shift.end % (24 * 60)))
            self.break_min.setValue(shift.break_minutes)
            self.notes.setPlainText(shift.notes)
        else:
            self.date.setDate(to_qdate(day or services.planner.today()))
        self.until.setDate(self.date.date().addDays(7 * 12))
        self._fill_repeat()
        self.repeat.currentIndexChanged.connect(self._repeat_changed)
        self.date.dateChanged.connect(self._fill_repeat)
        for signal in (self.job.currentIndexChanged, self.date.dateChanged,
                       self.start.timeChanged, self.end.timeChanged,
                       self.break_min.valueChanged, self.repeat.currentIndexChanged,
                       self.days.changed, self.has_until.toggled, self.until.dateChanged):
            signal.connect(self._update_preview)
        self._repeat_changed()
        self._update_preview()

    # ---- repeat -----------------------------------------------------------------

    def _fill_repeat(self):
        index = max(self.repeat.currentIndex(), 0)
        weekday = self.date.date().toPython().strftime("%A")
        self.repeat.blockSignals(True)
        self.repeat.clear()
        self.repeat.addItems(["Doesn't repeat", f"Every week on {weekday}",
                              "Every work day (Mon–Fri)", "Every day", "Custom days…"])
        self.repeat.setCurrentIndex(index)
        self.repeat.blockSignals(False)
        self._repeat_changed()

    def _repeat_days(self) -> list[int]:
        choice = self.repeat.currentIndex()
        if choice == self.REPEAT_WEEKLY:
            return [self.date.date().toPython().weekday()]
        if choice == self.REPEAT_WORKDAYS:
            return list(WORK_DAYS)
        if choice == self.REPEAT_DAILY:
            return list(EVERY_DAY)
        if choice == self.REPEAT_CUSTOM:
            return self.days.days()
        return []

    def _repeating(self) -> bool:
        return (self.shift_id is None and self.replaces is None
                and self.repeat.currentIndex() > self.REPEAT_NONE)

    def _repeat_changed(self):
        repeating = self._repeating()
        custom = self.repeat.currentIndex() == self.REPEAT_CUSTOM
        self.days.setVisible(repeating and custom)
        if custom and not self.days.days():
            self.days.setDays([self.date.date().toPython().weekday()])
        self.has_until.setVisible(repeating)
        self.until.setVisible(repeating)

    # ---- jobs -------------------------------------------------------------------

    def _fill_jobs(self, select=None):
        current = select if select is not None else self.job.currentData()
        self.job.blockSignals(True)
        self.job.clear()
        for job in self.work.jobs():
            self.job.addItem(color_icon(job.color), job.name, job.id)
        if current is not None:
            select_data(self.job, current)
        self.job.blockSignals(False)

    def _new_job(self):
        dialog = JobDialog(self.services, parent=self)
        if dialog.exec():
            self._fill_jobs(select=dialog.job_id)
            self._update_preview()

    # ---- preview ----------------------------------------------------------------

    def _shift(self) -> Shift:
        return Shift.between(self.job.currentData() or 0, self.date.date().toPython(),
                             qtime_to_min(self.start.time()), qtime_to_min(self.end.time()),
                             break_minutes=self.break_min.value(),
                             notes=self.notes.toPlainText().strip(), id=self.shift_id)

    def _update_preview(self):
        shift = self._shift()
        self.next_day.setText("ends next day" if shift.ends_next_day else "")
        job = next((j for j in self.work.jobs() if j.id == shift.job_id), None)
        gross = shift.pay(job.hourly_rate if job else None)
        net = net_pay(gross, job.deductions if job else 0.0)
        text = f"{fmt_duration(max(shift.paid_minutes, 0))} paid"
        if gross is not None and shift.paid_minutes > 0:
            text += "  ·  ≈ " + pay_text(gross, net)
        if self._repeating():
            days = self._repeat_days()
            text += (f"  ·  each {fmt_days(days)}" if days else "  ·  pick the days")
        self.summary.setText(text)
        try:
            items = self.services.planner.items_between(shift.day, shift.day + timedelta(days=1))
            clashes = self.work.clashes(shift, items, self.replaces)
        except DomainError:
            clashes = []
        self.clash.setText("Overlaps " + ", ".join(
            f"{c.title} ({fmt_range(c.time)})" for c in clashes) if clashes else "")
        self.clash.setVisible(bool(clashes))

    # ---- save -------------------------------------------------------------------

    def _save(self):
        if self.job.currentData() is None:
            QMessageBox.information(self, "Add a job first",
                                    "Create the job this shift is for with “New job…”.")
            return
        shift = self._shift()
        if self._repeating():
            until = self.until.date().toPython() if self.has_until.isChecked() else None
            action = lambda: self.work.add_weekly(  # noqa: E731
                shift.job_id, self._repeat_days(), shift.start, shift.end % (24 * 60),
                shift.break_minutes, since=shift.day, until=until)
        else:
            action = lambda: self.work.save_shift(shift, replaces=self.replaces)  # noqa: E731
        if attempt(self, action):
            self.accept()

    def _delete(self):
        if confirm(self, "Delete shift", "Delete this shift?"):
            self.work.delete_shift(self.shift_id)
            self.accept()


def weekly_shift_menu(parent, services: Services, job_id: int, origin: tuple[date, int], pos):
    """Menu for one week's occurrence of a regular shift."""
    day, start = origin
    job = services.work.job(job_id)
    pattern = next((p for p in job.schedule if p.occurs_on(day) and p.start == start), None)
    menu = QMenu(parent)
    change = menu.addAction("Change just this week…")
    skip = menu.addAction("Skip this week")
    menu.addSeparator()
    edit = menu.addAction(f"Edit {job.name}'s weekly schedule…")
    chosen = menu.exec(pos)
    if chosen is skip:
        services.work.skip_occurrence(job_id, day, start)
    elif chosen is change and pattern is not None:
        ShiftDialog(services, day=day, start=start, job_id=job_id,
                    end=(start + pattern.duration) % (24 * 60),
                    break_minutes=pattern.break_minutes, replaces=(job_id, day, start),
                    parent=parent).exec()
    elif chosen is edit:
        JobDialog(services, job_id, parent).exec()


def add_menu(parent, services: Services, day_provider) -> QMenu:
    """The "+ Add" button's menu: an event or a work shift on the shown day."""
    menu = QMenu(parent)
    menu.addAction("Event…", lambda: EventDialog(services, day=day_provider(),
                                                 parent=parent).exec())
    menu.addAction("Work shift…", lambda: ShiftDialog(services, day=day_provider(),
                                                      parent=parent).exec())
    return menu


def new_item_menu(parent, services: Services, day: date, minute: int, pos=None):
    """Double-clicking empty time asks what to add there."""
    from PySide6.QtGui import QCursor

    menu = QMenu(parent)
    event = menu.addAction("Event…")
    shift = menu.addAction("Work shift…")
    chosen = menu.exec(pos or QCursor.pos())
    if chosen is event:
        EventDialog(services, day=day, start=minute, parent=parent).exec()
    elif chosen is shift:
        ShiftDialog(services, day=day, start=minute, parent=parent).exec()
