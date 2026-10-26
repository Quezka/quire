"""Enterprise business rules: entities and invariants, free of any framework."""
from .errors import DomainError, NotFound, ValidationError
from .focus import FocusSession, FocusSettings, Phase, PhaseEnded, PomodoroTimer
from .model import (
    COURSE_COLORS, EVERY_DAY, MILESTONE_MINUTES, IMAGE_SCHEME, MAX_IMAGE_BYTES, PASS_MARK, UPCOMING_DAYS, WORK_DAYS, ClassSlot, Course, DueBucket, Event, Grade, Job, Lesson, Note,
    NoteImage, Notebook, Routine, Shift, ShiftPattern, Subject, Task, TaskKind, TimeRange, average, derive_note_title,
    image_markdown, image_uids, milestone_time, net_pay, normalize_topic, note_snippet, reschedule, work_shifts,
)
from .water import WaterLog, expected_ml, reminder_due, water_goal_ml
from .sleep import SleepLog, SleepStats, bedtime_for, regularity, should_wind_down, sleep_stats
from .payroll import PayTerms, Payslip, monthly_gross, monthly_share, take_home, year_payslips
from .register import (
    ABSENCE_LIMIT, GRADE_MAX, GRADE_MIN, Absence, AbsenceKind, Book, DocumentKind, Notice,
    NoticeAttachment, SchoolDocument, lesson_hours, needed_grade, running_average,
)

__all__ = [
    "WaterLog", "expected_ml", "reminder_due", "water_goal_ml",
    "SleepLog", "SleepStats", "bedtime_for", "regularity", "should_wind_down", "sleep_stats",
    "FocusSession", "FocusSettings", "Phase", "PhaseEnded", "PomodoroTimer",
    "DomainError", "NotFound", "ValidationError", "COURSE_COLORS", "EVERY_DAY", "MILESTONE_MINUTES", "PASS_MARK", "UPCOMING_DAYS", "WORK_DAYS", "ClassSlot", "Course",
    "DueBucket", "Event", "Grade", "Job", "Lesson", "Note", "Notebook", "Routine", "Shift", "ShiftPattern", "Subject", "Task", "TaskKind", "TimeRange", "average",
    "derive_note_title", "note_snippet", "IMAGE_SCHEME", "MAX_IMAGE_BYTES", "NoteImage",
    "PayTerms", "Payslip", "monthly_gross", "monthly_share", "take_home", "year_payslips",
    "image_markdown", "image_uids", "milestone_time", "net_pay", "normalize_topic", "reschedule", "work_shifts",
    "ABSENCE_LIMIT", "GRADE_MAX", "GRADE_MIN", "Absence", "AbsenceKind", "Book", "DocumentKind",
    "Notice", "NoticeAttachment", "SchoolDocument", "lesson_hours", "needed_grade",
    "running_average",
]
