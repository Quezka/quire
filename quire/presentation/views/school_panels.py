"""School page sections beyond the overview: absences, the noticeboard, textbooks and
documents, and the per-subject grade dialog (trend chart and "what do I need?")."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ...application.errors import ApplicationError
from ...application.records import DocumentRecord, NoticeRecord
from ...application.services import Services
from ...application.types import GRADE_MAX, GRADE_MIN, PASS_MARK, AbsenceKind, DocumentKind
from .. import theme
from ..dialogs import _buttons, attempt
from ..formatting import long_date, money, relative_date
from ..i18n import C_, _, month_short, plural
from ..sync_ui import run_in_background
from ..widgets import TwoLineDelegate
from .common import Card, StatTile, button, label

AMBER = "#f5a524"


def fmt_mark(value: float) -> str:
    """Italian marks: 7.5 -> "7½", 6.25 -> "6+", 6.75 -> "7-"."""
    quarters = round(value * 4)
    whole, rest = divmod(quarters, 4)
    return {0: f"{whole}", 1: f"{whole}+", 2: f"{whole}½", 3: f"{whole + 1}-"}[rest]


def open_file(data: bytes, file_name: str) -> Path:
    """Save a downloaded file in Quire's cache and open it with the system's viewer."""
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)) / "school"
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.\- ]+", "_", file_name).strip() or "document.pdf"
    target = folder / safe
    target.write_bytes(data)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
    return target


def _error_text(error: Exception) -> str:
    return _(str(error)) if isinstance(error, ApplicationError) else _(
        "Something went wrong: {error}").format(error=error)


# ---- absences ---------------------------------------------------------------------

def absence_title(a) -> str:
    if a.kind is AbsenceKind.ABSENT:
        return _("Absent")
    if a.kind is AbsenceKind.SHORT_LATE:
        return _("A few minutes late")
    late = a.kind is AbsenceKind.LATE
    if a.hour is None:
        return _("Late entry, hour not recorded") if late else _("Left early, hour not recorded")
    return (_("Late entry, hour {hour}") if late else _("Left early, hour {hour}")).format(
        hour=a.hour)


class AbsenceHourDialog(QDialog):
    """Enter the hour of a late entry or early exit that the school left blank."""

    FORGET = 2

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Lesson hour"))
        late = record.kind is AbsenceKind.LATE
        text = label(_("The school didn't record the hour you came in. Which lesson hour was "
                       "it?") if late else _("The school didn't record the hour you left. "
                                             "Which lesson hour was it?"))
        text.setWordWrap(True)
        self.hour = QSpinBox(minimum=1, maximum=10, value=record.hour or (2 if late else 5))
        forget = (lambda: self.done(self.FORGET)) if record.hour_is_yours else None
        buttons = _buttons(self, self.accept, forget, _("Forget"))
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(self.hour)
        layout.addWidget(buttons)


class AbsencesPanel(QWidget):
    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        self.tile_hours = StatTile(_("HOURS MISSED"))
        self.tile_days = StatTile(_("DAYS ABSENT"))
        self.tile_late = StatTile(_("LATE ENTRIES"))
        self.tile_exits = StatTile(_("EARLY EXITS"))
        tiles = QHBoxLayout()
        tiles.setSpacing(16)
        for tile in (self.tile_hours, self.tile_days, self.tile_late, self.tile_exits):
            tiles.addWidget(tile, 1)

        limit = Card(_("Towards the 25% limit"))
        self.bar = QProgressBar(textVisible=False)
        self.bar.setFixedHeight(10)
        self.limit_text = label("", "muted")
        self.limit_text.setWordWrap(True)
        self.limit_hint = label(_("Missing more than a quarter of the year's lesson hours can "
                                  "mean repeating the year, unless the school grants an "
                                  "exception. The year's hours are estimated from the school "
                                  "calendar and your timetable."), "hint")
        self.limit_hint.setWordWrap(True)
        for widget in (self.bar, self.limit_text, self.limit_hint):
            limit.add(widget)

        records = Card(_("This year"))
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.empty = label(_("No absences this year."), "hint")
        self.list.itemActivated.connect(self._edit_hour)
        self.hours_hint = label(_("Double-click a late entry or early exit to enter an hour "
                                  "the school didn't record."), "hint")
        self.hours_hint.setWordWrap(True)
        records.add(self.list, 1)
        records.add(self.empty)
        records.add(self.hours_hint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addLayout(tiles)
        layout.addWidget(limit)
        layout.addWidget(records, 1)

    def refresh(self):
        t = theme.current()
        s = self.services.school.absence_summary()
        today = self.services.planner.today()
        share = s.share
        if share is None:
            color, detail = None, _("add your timetable to see the limit")
        else:
            used = s.hours_missed / s.limit_hours if s.limit_hours else 1
            color = t.danger if used >= 0.8 else AMBER if used >= 0.5 else t.success
            detail = _("of about {limit} allowed").format(limit=s.limit_hours)
        self.tile_hours.show(str(s.hours_missed), detail, color)
        self.tile_days.show(str(s.absent_days), _("{count} not justified").format(
            count=s.unjustified) if s.unjustified else "")
        self.tile_late.show(str(s.late_entries))
        self.tile_exits.show(str(s.early_exits))

        if share is None:
            self.bar.setValue(0)
            self.limit_text.setText(_("Add your timetable in Week → Courses so Quire can "
                                      "estimate the year's lesson hours."))
        else:
            self.bar.setRange(0, max(s.limit_hours, 1))
            self.bar.setValue(min(s.hours_missed, s.limit_hours))
            self.bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; "
                                   "border-radius: 4px; }")
            self.limit_text.setText(_(
                "{missed} of about {limit} hours ({percent}% of the year so far). "
                "About {left} hours left before the limit.").format(
                    missed=s.hours_missed, limit=s.limit_hours,
                    percent=f"{share * 100:.1f}", left=s.hours_left))

        self.list.clear()
        for a in s.items:
            row = QListWidgetItem(absence_title(a))
            row.setData(Qt.UserRole, a)
            meta = [relative_date(a.day, today)]
            if a.hour_is_yours:
                meta.append(_("hour entered by you"))
            if a.hours_missed:
                meta.append(plural(a.hours_missed, "hour"))
            meta.append(_("justified") if a.justified else _("not justified"))
            if a.reason:
                meta.append(a.reason)
            row.setData(TwoLineDelegate.META, " · ".join(meta))
            row.setData(TwoLineDelegate.COLOR, t.success if a.justified else t.danger)
            row.setToolTip(long_date(a.day))
            self.list.addItem(row)
        self.list.setVisible(bool(s.items))
        self.empty.setVisible(not s.items)
        self.hours_hint.setVisible(any(a.needs_hour for a in s.items))

    def _edit_hour(self, item: QListWidgetItem):
        record = item.data(Qt.UserRole)
        if record is None or not record.needs_hour:
            return
        dialog = AbsenceHourDialog(record, self)
        result = dialog.exec()
        if result == QDialog.Rejected:
            return
        hour = None if result == AbsenceHourDialog.FORGET else dialog.hour.value()
        attempt(self, lambda: self.services.school.set_absence_hour(record.id, hour))
        self.refresh()


# ---- noticeboard ------------------------------------------------------------------------

class NoticesPanel(QWidget):
    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        card = Card(_("Noticeboard"))
        self.unread_only = QPushButton(_("Unread only"), objectName="segment", checkable=True)
        self.unread_only.setCursor(Qt.PointingHandCursor)
        self.unread_only.toggled.connect(lambda _on: self.refresh())
        card.title_row.addWidget(self.unread_only)
        self.list = QListWidget()
        self.list.setItemDelegate(TwoLineDelegate(self.list))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.itemActivated.connect(self._open)
        self.list.setToolTip(_("Double-click a notice to open it"))
        self.empty = label(_("Nothing on the noticeboard."), "hint")
        card.add(self.list, 1)
        card.add(self.empty)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card, 1)
        self._notices: dict[str, NoticeRecord] = {}

    def refresh(self):
        t = theme.current()
        today = self.services.planner.today()
        notices = self.services.school.notices()
        self._notices = {n.id: n for n in notices}
        shown = [n for n in notices if not (self.unread_only.isChecked() and n.read)]
        self.list.clear()
        for n in shown:
            row = QListWidgetItem(n.title)
            meta = [relative_date(n.published, today)]
            if n.category:
                meta.append(n.category)
            if n.attachments:
                meta.append(plural(len(n.attachments), "attachment"))
            if not n.read:
                meta.insert(0, _("New"))
            row.setData(TwoLineDelegate.META, " · ".join(meta))
            row.setData(TwoLineDelegate.COLOR, t.accent if not n.read else t.faint)
            row.setData(Qt.UserRole, n.id)
            self.list.addItem(row)
        self.list.setVisible(bool(shown))
        self.empty.setVisible(not shown)

    def _open(self, item: QListWidgetItem):
        notice = self._notices.get(item.data(Qt.UserRole))
        if notice is not None:
            NoticeDialog(self.services, notice, self).exec()


class NoticeDialog(QDialog):
    def __init__(self, services: Services, notice: NoticeRecord, parent=None):
        super().__init__(parent)
        self.services = services
        self.notice = notice
        self._workers = []
        self.setWindowTitle(_("Notice"))
        self.setMinimumWidth(520)

        title = QLabel(notice.title, objectName="sheetTitle", wordWrap=True)
        title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        facts = [long_date(notice.published)]
        if notice.category:
            facts.append(notice.category)
        if notice.valid_until:
            facts.append(_("until {day}").format(day=long_date(notice.valid_until)))
        info = label(" · ".join(facts), "hint")
        info.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(info)
        if notice.attachments:
            layout.addWidget(label(_("Attachments"), "muted"))
            for attachment in notice.attachments:
                open_btn = button(attachment.file_name or _("Attachment {number}").format(
                    number=attachment.number), "notes")
                open_btn.clicked.connect(
                    lambda _on=False, a=attachment, b=open_btn: self._download(a, b))
                layout.addWidget(open_btn)
        else:
            layout.addWidget(label(_("This notice has no attachments."), "hint"))
        self.status = label("", "hint")
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)
        close = QPushButton(_("Close"))
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)

        if not notice.read:
            services.school_sync.mark_notice_read(notice.id)
            # Tell the school it was read, like its own app does; a failure doesn't matter.
            self._workers.append(run_in_background(
                lambda: services.school_sync.tell_notice_read(notice),
                lambda _r: None, lambda _e: None))

    def _download(self, attachment, source: QPushButton):
        source.setEnabled(False)
        self.status.setText(_("Downloading…"))
        self.status.show()

        def done(data: bytes):
            source.setEnabled(True)
            self.status.hide()
            open_file(data, attachment.file_name or f"notice-{attachment.number}.pdf")

        def failed(error: Exception):
            source.setEnabled(True)
            self.status.setText(_error_text(error))

        self._workers.append(run_in_background(
            lambda: self.services.school_sync.notice_attachment(self.notice, attachment.number),
            done, failed))


# ---- textbooks and documents ------------------------------------------------------------

class BooksPanel(QWidget):
    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services
        self._workers = []
        books = Card(_("Textbooks"))
        self.books_total = label("", "hint")
        books.title_row.addWidget(self.books_total)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_("TITLE"), _("AUTHOR"), _("ISBN"), _("PRICE"), _("STATUS")])
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(True)
        head = self.tree.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(1, QHeaderView.Interactive)
        head.resizeSection(1, 150)
        for col in range(2, 5):
            head.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        head.setMinimumSectionSize(60)
        self.tree.itemDoubleClicked.connect(self._copy_isbn)
        self.books_empty = label(_("No textbook list yet."), "hint")
        books.add(self.tree, 1)
        books.add(self.books_empty)

        documents = Card(_("Report cards & documents"))
        self.documents = QListWidget()
        self.documents.setItemDelegate(TwoLineDelegate(self.documents))
        self.documents.itemActivated.connect(self._open_document)
        self.documents_empty = label(_("No documents yet. Report cards appear here at the end "
                                       "of each term."), "hint")
        self.documents_empty.setWordWrap(True)
        self.documents_status = label("", "hint")
        self.documents_status.hide()
        documents.add(self.documents, 1)
        documents.add(self.documents_empty)
        documents.add(self.documents_status)
        documents.body.addStretch()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(books, 5)
        layout.addWidget(documents, 2)
        self._documents: dict[str, DocumentRecord] = {}

    def refresh(self):
        t = theme.current()
        books = self.services.school.books()
        self.tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for b in books:
            subject = b.subject.capitalize() if b.subject.isupper() else b.subject
            parent = groups.get(subject)
            if parent is None:
                parent = QTreeWidgetItem([subject])
                font = parent.font(0)
                font.setBold(True)
                parent.setFont(0, font)
                parent.setFlags(Qt.ItemIsEnabled)
                self.tree.addTopLevelItem(parent)
                parent.setFirstColumnSpanned(True)
                groups[subject] = parent
            status = (_("Owned") if b.owned else _("To buy") if b.to_buy
                      else _("Recommended"))
            if b.new_adoption:
                status += " · " + _("new")
            title = f"{b.title} ({b.volume})" if b.volume else b.title
            child = QTreeWidgetItem([title, b.author, b.isbn,
                                     money(b.price) if b.price is not None else "", status])
            child.setForeground(4, QColor(t.accent if b.to_buy and not b.owned else t.muted))
            child.setToolTip(0, " · ".join(filter(None, [b.title, b.author, b.publisher])))
            child.setToolTip(1, " · ".join(filter(None, [b.author, b.publisher])))
            child.setToolTip(2, _("Double-click to copy the ISBN"))
            parent.addChild(child)
        self.tree.expandAll()
        to_buy = [b for b in books if b.to_buy and not b.owned]
        cost = sum(b.price or 0 for b in to_buy)
        self.books_total.setText(_("{books} to buy, {cost}").format(
            books=plural(len(to_buy), "book"), cost=money(cost)) if to_buy else "")
        self.tree.setVisible(bool(books))
        self.books_empty.setVisible(not books)

        self.documents.clear()
        documents = self.services.school.documents()
        self._documents = {d.id: d for d in documents}
        for d in documents:
            row = QListWidgetItem(d.title or _("Document"))
            row.setData(TwoLineDelegate.META, _("Report card") if d.kind is DocumentKind.REPORT
                        else C_("school", "Document"))
            row.setData(TwoLineDelegate.COLOR, t.accent)
            row.setData(Qt.UserRole, d.id)
            self.documents.addItem(row)
        self.documents.setVisible(bool(documents))
        self.documents_empty.setVisible(not documents)

    def _copy_isbn(self, item: QTreeWidgetItem, _column: int):
        from PySide6.QtWidgets import QApplication

        if item.text(2):
            QApplication.clipboard().setText(item.text(2))

    def _open_document(self, item: QListWidgetItem):
        document = self._documents.get(item.data(Qt.UserRole))
        if document is None:
            return
        if document.kind is DocumentKind.REPORT:
            QDesktopServices.openUrl(QUrl(document.link))  # report cards open on the web
            return
        self.documents_status.setText(_("Downloading…"))
        self.documents_status.show()

        def done(data: bytes):
            self.documents_status.hide()
            open_file(data, f"{document.title or 'document'}.pdf")

        def failed(error: Exception):
            self.documents_status.setText(_error_text(error))

        self._workers.append(run_in_background(
            lambda: self.services.school_sync.document_file(document), done, failed))


# ---- per-subject grades ---------------------------------------------------------------

class TrendChart(QWidget):
    """Marks as dots and the running average as a line, with the pass mark dashed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.marks: list[tuple[date, float]] = []
        self.average: list[tuple[date, float]] = []

    def set_data(self, marks, average):
        self.marks, self.average = list(marks), list(average)
        self.update()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.rect()).adjusted(28, 10, -10, -22)
        if len(self.marks) < 2:
            p.setPen(QColor(t.muted))
            p.drawText(self.rect(), Qt.AlignCenter, _("A chart appears after two grades."))
            return
        low = min([v for _d, v in self.marks] + [PASS_MARK]) - 0.5
        high = GRADE_MAX
        first = self.marks[0][0]
        span = max((self.marks[-1][0] - first).days, 1)

        def point(day: date, value: float) -> QPointF:
            x = area.left() + area.width() * (day - first).days / span
            y = area.bottom() - area.height() * (value - low) / (high - low)
            return QPointF(x, y)

        p.setPen(QColor(t.faint))
        for value in range(int(low) + 1, int(high) + 1):
            y = point(first, value).y()
            p.drawText(QRectF(0, y - 8, 22, 16), Qt.AlignRight | Qt.AlignVCenter, str(value))
        last = self.marks[-1][0]
        p.drawText(QRectF(area.left(), area.bottom() + 4, 120, 16), Qt.AlignLeft,
                   f"{first.day} {month_short(first)}")
        p.drawText(QRectF(area.right() - 120, area.bottom() + 4, 120, 16), Qt.AlignRight,
                   f"{last.day} {month_short(last)}")

        pass_y = point(first, PASS_MARK).y()
        p.setPen(QPen(QColor(t.danger), 1, Qt.DashLine))
        p.drawLine(QPointF(area.left(), pass_y), QPointF(area.right(), pass_y))

        path = QPainterPath()
        for i, (day, value) in enumerate(self.average):
            path.moveTo(point(day, value)) if i == 0 else path.lineTo(point(day, value))
        p.setPen(QPen(QColor(t.accent), 2.5))
        p.drawPath(path)

        for day, value in self.marks:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.danger if value < PASS_MARK else t.text))
            p.drawEllipse(point(day, value), 3.5, 3.5)


class SubjectDialog(QDialog):
    """One subject: how its average moved, and what the next test needs."""

    def __init__(self, services: Services, subject: str, period: str | None, parent=None):
        super().__init__(parent)
        self.services = services
        self.subject = subject
        self.period = period
        self.setWindowTitle(subject)
        self.setMinimumWidth(560)

        title = QLabel(subject, objectName="sheetTitle")
        self.summary = label("", "muted")
        self.chart = TrendChart()
        legend = label(_("Line: your average over time · dots: each mark · dashed: the pass "
                         "mark"), "hint")

        needed = Card(_("What do I need?"))
        self.target = QDoubleSpinBox(minimum=GRADE_MIN, maximum=GRADE_MAX, singleStep=0.25,
                                     decimals=2, value=PASS_MARK)
        self.tests = QSpinBox(minimum=1, maximum=6, value=1)
        row = QHBoxLayout()
        row.addWidget(label(_("To average"), "muted"))
        row.addWidget(self.target)
        row.addWidget(label(_("over the next"), "muted"))
        row.addWidget(self.tests)
        self.tests_word = label("", "muted")
        row.addWidget(self.tests_word)
        row.addStretch()
        needed.body.addLayout(row)
        self.answer = QLabel(objectName="tileValue", wordWrap=True)
        self.answer_detail = label("", "hint")
        self.answer_detail.setWordWrap(True)
        needed.add(self.answer)
        needed.add(self.answer_detail)
        self.target.valueChanged.connect(self._update_needed)
        self.tests.valueChanged.connect(self._update_needed)

        close = QPushButton(_("Close"))
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(self.summary)
        layout.addWidget(self.chart, 1)
        layout.addWidget(legend)
        layout.addWidget(needed)
        layout.addLayout(buttons)

        subjects = {s.subject: s for s in services.school.grades_by_subject(period)}
        entry = subjects.get(subject)
        marks = sorted((g.day, g.value) for g in entry.grades if g.counts) if entry else []
        self.chart.set_data(marks, services.school.trend(subject, period))
        if entry and entry.average is not None:
            self.summary.setText(_("Average {average} from {marks}").format(
                average=f"{entry.average:.2f}", marks=plural(len(marks), "mark")))
        else:
            self.summary.setText(_("No marks yet."))
        self._update_needed()

    def _update_needed(self):
        tests = self.tests.value()
        self.tests_word.setText(_("test") if tests == 1 else _("tests"))
        result = self.services.school.needed(self.subject, self.target.value(), tests,
                                             self.period)
        target = fmt_mark(result.target)
        if result.already_safe:
            self.answer.setText(_("You're safe"))
            self.answer_detail.setText(_("Even a {low} keeps your average at {target} or "
                                         "above.").format(low=fmt_mark(GRADE_MIN), target=target))
        elif not result.reachable:
            self.answer.setText(_("Not reachable yet"))
            self.answer_detail.setText(_("You'd need {mark} on each test: try over more "
                                         "tests.").format(mark=f"{result.mark:.2f}"))
        else:
            self.answer.setText(fmt_mark(result.mark))
            self.answer_detail.setText(
                (_("on the next test, to reach an average of {target}.") if tests == 1 else
                 _("on each of the next {count} tests, to reach an average of {target}.")
                 ).format(count=tests, target=target))
