"""Edit dialogs for courses, events and tasks."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget,
    QTimeEdit, QVBoxLayout,
)

from ..application.services import Services
from ..domain import (
    ClassSlot, Course, DomainError, Event, Job, Shift, Task, TaskKind, TimeRange,
)
from .formatting import KIND_LABELS, WEEKDAYS, fmt_duration, fmt_min, fmt_range, money
from .widgets import PALETTE, ColorButton, color_icon, min_to_qtime, qtime_to_min


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


class JobDialog(QDialog):
    def __init__(self, services: Services, job_id=None, parent=None):
        super().__init__(parent)
        self.work = services.work
        self.job_id = job_id
        self.setWindowTitle("Edit job" if job_id else "New job")
        self.setMinimumWidth(400)

        self.name = QLineEdit(placeholderText="e.g. Pizzeria Da Mario")
        used = {j.color for j in self.work.jobs()}
        self.color = ColorButton(next((c for c in reversed(PALETTE) if c not in used), PALETTE[-2]))
        self.rate = QDoubleSpinBox(decimals=2, maximum=1000, singleStep=0.5)
        self.rate.setSpecialValueText("Not set")
        self.rate.setSuffix(" / hour")

        form = QFormLayout()
        form.addRow("Name", self.name)
        form.addRow("Colour", self.color)
        form.addRow("Hourly pay", self.rate)
        hint = QLabel("Set the hourly pay to see what each shift earns.", objectName="hint")
        form.addRow("", hint)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, self._save, self._delete if job_id else None,
                                  "Delete job"))

        if job_id:
            job = self.work.job(job_id)
            self.name.setText(job.name)
            self.color.setColor(job.color)
            self.rate.setValue(job.hourly_rate or 0)

    def _save(self):
        job = Job(self.name.text(), self.color.color(), self.rate.value() or None, self.job_id)
        if attempt(self, lambda: self.work.save_job(job)):
            self.job_id = job.id
            self.accept()

    def _delete(self):
        if confirm(self, "Delete job", "Delete this job and all of its shifts?"):
            self.work.delete_job(self.job_id)
            self.accept()


class JobsDialog(QDialog):
    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        self.setWindowTitle("Jobs")
        self.setMinimumSize(420, 320)
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
        for job in self.services.work.jobs():
            rate = f"{money(job.hourly_rate)} / hour" if job.hourly_rate else "no pay rate"
            item = QListWidgetItem(color_icon(job.color, 14), f"{job.name}\n{rate}")
            item.setData(Qt.UserRole, job.id)
            self.list.addItem(item)

    def _add(self):
        if JobDialog(self.services, parent=self).exec():
            self._reload()

    def _edit(self, item):
        if item and JobDialog(self.services, item.data(Qt.UserRole), self).exec():
            self._reload()


class ShiftDialog(QDialog):
    def __init__(self, services: Services, shift_id=None, day: date | None = None,
                 start: int = 17 * 60, parent=None):
        super().__init__(parent)
        self.services = services
        self.work = services.work
        self.shift_id = shift_id
        self.setWindowTitle("Edit shift" if shift_id else "New shift")
        self.setMinimumWidth(460)

        self.job = QComboBox()
        new_job = QPushButton("New job…")
        new_job.clicked.connect(self._new_job)
        job_row = QHBoxLayout()
        job_row.addWidget(self.job, 1)
        job_row.addWidget(new_job)

        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.start = _time_edit(start)
        self.end = _time_edit(min(start + 4 * 60, 24 * 60 - 1))
        self.next_day = QLabel("", objectName="hint")
        times = QHBoxLayout()
        times.addWidget(self.start)
        times.addWidget(QLabel("to"))
        times.addWidget(self.end)
        times.addWidget(self.next_day)
        times.addStretch()

        self.break_min = QSpinBox(maximum=240, singleStep=5, suffix=" min")
        self.break_min.setSpecialValueText("No break")
        self.repeat = QSpinBox(maximum=52, suffix=" more weeks")
        self.repeat.setSpecialValueText("Just this once")
        self.notes = QPlainTextEdit(placeholderText="Notes (optional)")
        self.notes.setFixedHeight(70)
        self.summary = QLabel("", objectName="muted")
        self.clash = QLabel("", objectName="danger")
        self.clash.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Job", job_row)
        form.addRow("Date", self.date)
        form.addRow("Time", times)
        form.addRow("Unpaid break", self.break_min)
        if not shift_id:
            form.addRow("Repeat weekly", self.repeat)
        form.addRow("Notes", self.notes)
        form.addRow("", self.summary)
        form.addRow("", self.clash)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(_buttons(self, self._save, self._delete if shift_id else None))

        self._fill_jobs()
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
        for signal in (self.job.currentIndexChanged, self.date.dateChanged,
                       self.start.timeChanged, self.end.timeChanged,
                       self.break_min.valueChanged, self.repeat.valueChanged):
            signal.connect(self._update_preview)
        self._update_preview()

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

    def _shift(self) -> Shift:
        return Shift.between(self.job.currentData() or 0, self.date.date().toPython(),
                             qtime_to_min(self.start.time()), qtime_to_min(self.end.time()),
                             break_minutes=self.break_min.value(),
                             notes=self.notes.toPlainText().strip(), id=self.shift_id)

    def _update_preview(self):
        shift = self._shift()
        self.next_day.setText("ends next day" if shift.ends_next_day else "")
        job = next((j for j in self.work.jobs() if j.id == shift.job_id), None)
        pay = shift.pay(job.hourly_rate if job else None)
        text = f"{fmt_duration(max(shift.paid_minutes, 0))} paid"
        if pay is not None and shift.paid_minutes > 0:
            text += f"  ·  ≈ {money(pay)}"
        if self.repeat.value():
            text += f"  ·  {self.repeat.value() + 1} shifts in total"
        self.summary.setText(text)
        try:
            items = self.services.planner.items_between(shift.day, shift.day + timedelta(days=1))
            clashes = self.work.clashes(shift, items)
        except DomainError:
            clashes = []
        self.clash.setText("Overlaps " + ", ".join(
            f"{c.title} ({fmt_range(c.time)})" for c in clashes) if clashes else "")
        self.clash.setVisible(bool(clashes))

    def _save(self):
        if self.job.currentData() is None:
            QMessageBox.information(self, "Add a job first",
                                    "Create the job this shift is for with “New job…”.")
            return
        shift = self._shift()
        repeat = self.repeat.value() if not self.shift_id else 0
        if attempt(self, lambda: self.work.save_shift(shift, repeat)):
            self.accept()

    def _delete(self):
        if confirm(self, "Delete shift", "Delete this shift?"):
            self.work.delete_shift(self.shift_id)
            self.accept()


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
