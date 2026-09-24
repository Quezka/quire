"""Reusable Qt widgets."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import (
    QEvent, QObject, QPoint, QPointF, QRectF, QSettings, QSize, Qt, QTime, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QLineEdit, QPushButton, QSpinBox, QStyle, QStyledItemDelegate, QToolTip, QWidget,
)

from ..domain import COURSE_COLORS
from . import icons, theme
from .i18n import _, weekday_names

PALETTE = list(COURSE_COLORS)
NO_COLOR = "#00000000"


def qtime_to_min(t: QTime) -> int:
    return t.hour() * 60 + t.minute()


def min_to_qtime(minutes: int) -> QTime:
    minutes = max(0, min(minutes, 24 * 60 - 1))
    return QTime(minutes // 60, minutes % 60)


def color_icon(color: str, size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(0, 0, size, size)
    p.end()
    return QIcon(pm)


def scaled_font(widget: QWidget, factor: float, bold: bool = False) -> QFont:
    font = QFont(widget.font())
    font.setPointSizeF(font.pointSizeF() * factor)
    font.setBold(bold)
    return font


def parse_amount(text: str) -> float | None:
    """Read a money amount typed with either decimal separator; blank means none.

    Raises ValueError for anything that isn't a non-negative number.
    """
    text = text.strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:  # 1.234,50 or 1,234.50: the last one is the decimal mark
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal == "," else ",", "")
    value = float(text.replace(",", "."))
    if value < 0 or value != value:
        raise ValueError(text)
    return round(value, 2)


class AmountEdit(QLineEdit):
    """A line edit for an optional money amount, e.g. an hourly rate."""

    def amount(self) -> float | None:
        return parse_amount(self.text())

    def setAmount(self, value: float | None):
        self.setText("" if value is None else f"{value:.2f}")


class SpinBox(QSpinBox):
    """A spin box whose contents get selected on focus, so typing replaces them.

    Without this, clicking into special text such as "No break" and typing does nothing.
    """

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def mousePressEvent(self, event):
        first_click = not self.hasFocus()
        super().mousePressEvent(event)
        if first_click:
            QTimer.singleShot(0, self.selectAll)


class DaysPicker(QWidget):
    """Seven round toggles (M T W T F S S) for picking weekdays."""

    changed = Signal()

    def __init__(self, days=(), parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout, QToolButton

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.buttons = []
        for i, name in enumerate(weekday_names()):
            button = QToolButton(objectName="day", text=name[0], checkable=True, toolTip=name)
            button.setCursor(Qt.PointingHandCursor)
            button.toggled.connect(lambda _on: self.changed.emit())
            layout.addWidget(button)
            self.buttons.append(button)
        layout.addStretch()
        self.setDays(days)

    def days(self) -> list[int]:
        return [i for i, b in enumerate(self.buttons) if b.isChecked()]

    def setDays(self, days):
        wanted = set(days)
        for i, button in enumerate(self.buttons):
            button.blockSignals(True)
            button.setChecked(i in wanted)
            button.blockSignals(False)
        self.changed.emit()


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, color: str = PALETTE[0], parent=None):
        super().__init__(parent)
        self._color = color
        self.clicked.connect(self._pick)
        self._sync()

    def color(self) -> str:
        return self._color

    def setColor(self, color: str):
        self._color = color
        self._sync()

    def _sync(self):
        self.setIcon(color_icon(self._color, 16))
        self.setText(self._color.upper())

    def _pick(self):
        for i, c in enumerate(PALETTE):
            QColorDialog.setCustomColor(i, QColor(c))
        color = QColorDialog.getColor(QColor(self._color), self, _("Pick a colour"))
        if color.isValid():
            self.setColor(color.name())
            self.colorChanged.emit(self._color)


@dataclass(frozen=True)
class Block:
    column: int
    start: int
    end: int
    title: str
    subtitle: str
    color: str
    payload: object
    # The early-morning tail of something that started the evening before (a late
    # shift). It doesn't stretch the shown hours; if it ends before them, it's drawn
    # as a thin strip at the top of its day.
    carry_over: bool = False


class TimeGrid(QWidget):
    """A vertical timeline with one or more day columns and coloured blocks.

    Used by both the single-day planner and the weekly timetable.
    """

    blockActivated = Signal(object, QPoint)  # payload, global position
    emptyActivated = Signal(int, int)  # column, minute (snapped to 15)
    zoomRequested = Signal(float, float)  # factor, y in grid coordinates to keep in place

    GUTTER = 58
    PAD = 10
    DEFAULT_HOUR = 64.0
    MIN_HOUR = 18.0
    MAX_HOUR = 200.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hour_height = self.DEFAULT_HOUR
        self.column_count = 1
        self.blocks: list[Block] = []
        self.now_col = -1
        self.start_min = 7 * 60
        self.end_min = 21 * 60
        self.setMouseTracking(True)
        self._tick = QTimer(self, interval=60_000, timeout=self.update)
        self._tick.start()
        self._recalc()

    # ---- data & geometry --------------------------------------------------

    def set_data(self, column_count: int, blocks, now_col: int = -1):
        self.column_count = max(1, column_count)
        self.blocks = list(blocks)
        self.now_col = now_col
        self._recalc()
        self.update()

    CARRY_OVER_MINUTES = 30  # height of a carried-over strip, in minutes

    def _recalc(self):
        start, end = 7 * 60, 21 * 60
        for b in self.blocks:
            if b.carry_over:
                continue
            start = min(start, b.start // 60 * 60)
            end = max(end, -(-b.end // 60) * 60)
        self.start_min = max(0, start)
        self.end_min = min(24 * 60, end)
        self.setMinimumHeight(int(self.y_for(self.end_min) + self.PAD))

    def set_hour_height(self, height: float):
        height = max(self.MIN_HOUR, min(self.MAX_HOUR, height))
        if abs(height - self.hour_height) > 0.01:
            self.hour_height = height
            self._recalc()
            self.update()

    @property
    def span_hours(self) -> float:
        return (self.end_min - self.start_min) / 60

    def y_for(self, minute: float) -> float:
        return self.PAD + (minute - self.start_min) * self.hour_height / 60

    def minute_at(self, y: float) -> float:
        return self.start_min + (y - self.PAD) * 60 / self.hour_height

    def first_daytime_start(self, default: int = 8 * 60 + 30) -> int:
        """Where to scroll: the first block after 06:00 (late shifts spill past midnight)."""
        return min((b.start for b in self.blocks if b.start >= 6 * 60), default=default)

    def column_width(self) -> float:
        return max(1.0, (self.width() - self.GUTTER) / self.column_count)

    def sizeHint(self):
        return QSize(480, self.minimumHeight())

    def _layout(self):
        """Place blocks, splitting a column into lanes where blocks overlap."""
        out = []
        colw = self.column_width()

        def place(cluster, lanes, col):
            n = max(1, len(lanes))
            for b, lane in cluster:
                x = self.GUTTER + col * colw + lane * colw / n
                start, end = self._shown_span(b)
                y0, y1 = self.y_for(start), self.y_for(end)
                out.append((b, QRectF(x, y0, colw / n, max(20.0, y1 - y0))))

        for col in range(self.column_count):
            items = sorted((b for b in self.blocks if b.column == col),
                           key=lambda b: (self._shown_span(b)[0], -self._shown_span(b)[1]))
            cluster, lanes, cluster_end = [], [], -1
            for b in items:
                b_start, b_end = self._shown_span(b)
                if cluster and b_start >= cluster_end:
                    place(cluster, lanes, col)
                    cluster, lanes = [], []
                if not cluster:
                    cluster_end = b_end
                for i, lane_end in enumerate(lanes):
                    if lane_end <= b_start:
                        lanes[i] = b_end
                        lane = i
                        break
                else:
                    lanes.append(b_end)
                    lane = len(lanes) - 1
                cluster.append((b, lane))
                cluster_end = max(cluster_end, b_end)
            place(cluster, lanes, col)
        return out

    def _shown_span(self, b: Block) -> tuple[int, int]:
        """Where a block is drawn: carried-over tails before the shown hours become a
        short strip at the top instead of disappearing off-screen."""
        if b.carry_over and b.end <= self.start_min:
            return self.start_min, self.start_min + self.CARRY_OVER_MINUTES
        return b.start, b.end

    def _block_at(self, pos: QPointF):
        for b, rect in reversed(self._layout()):
            if rect.contains(pos):
                return b
        return None

    # ---- painting -----------------------------------------------------------

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        colw = self.column_width()
        line = QColor(t.border)

        p.fillRect(self.rect(), QColor(t.surface))

        if 0 <= self.now_col < self.column_count and self.column_count > 1:
            tint = QColor(t.accent)
            tint.setAlpha(14 if t.dark else 10)
            p.fillRect(QRectF(self.GUTTER + self.now_col * colw, 0, colw, self.height()), tint)

        small = scaled_font(self, 0.82)
        p.setFont(small)
        for hour in range(self.start_min // 60, self.end_min // 60 + 1):
            y = self.y_for(hour * 60)
            p.setPen(QPen(line, 1))
            p.drawLine(QPointF(self.GUTTER, y), QPointF(width, y))
            p.setPen(QColor(t.faint))
            p.drawText(QRectF(0, y - 9, self.GUTTER - 12, 18), Qt.AlignRight | Qt.AlignVCenter,
                       f"{hour:02d}:00")

        p.setPen(QPen(line, 1))
        for i in range(1, self.column_count):
            x = self.GUTTER + i * colw
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))

        bold = scaled_font(self, 0.95, bold=True)
        for b, rect in self._layout():
            self._paint_block(p, b, rect.adjusted(3, 2, -3, -2), t, bold, small)

        if 0 <= self.now_col < self.column_count:
            now = datetime.now()
            minute = now.hour * 60 + now.minute
            if self.start_min <= minute <= self.end_min:
                y = self.y_for(minute)
                x0 = self.GUTTER + self.now_col * colw
                color = QColor(t.danger)
                p.setPen(QPen(color, 2))
                p.drawLine(QPointF(x0, y), QPointF(x0 + colw, y))
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawEllipse(QPointF(x0, y), 4.5, 4.5)
        p.end()

    @staticmethod
    def _mix(color: str, base: str, amount: float) -> QColor:
        a, b = QColor(color), QColor(base)
        return QColor(int(a.red() * amount + b.red() * (1 - amount)),
                      int(a.green() * amount + b.green() * (1 - amount)),
                      int(a.blue() * amount + b.blue() * (1 - amount)))

    def _paint_block(self, p, b, r, t, bold, small):
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.fillPath(path, self._mix(b.color, t.surface, 0.30 if t.dark else 0.16))
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(r.left(), r.top(), 3, r.height()), QColor(b.color))
        inner = r.adjusted(11, 4, -6, -3)
        title_color = QColor(t.text) if t.dark else self._mix(b.color, t.text, 0.35)
        bold_fm = QFontMetrics(bold)
        p.setFont(bold)
        p.setPen(title_color)
        if r.height() < 40:
            title = bold_fm.elidedText(b.title, Qt.ElideRight, int(inner.width()))
            p.drawText(inner, Qt.AlignLeft | Qt.AlignVCenter, title)
            title_w = bold_fm.horizontalAdvance(title) + 8
            if title_w < inner.width():
                p.setFont(small)
                p.setPen(QColor(t.muted))
                sub = QFontMetrics(small).elidedText(b.subtitle, Qt.ElideRight,
                                                     int(inner.width() - title_w))
                p.drawText(inner.adjusted(title_w, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, sub)
        else:
            p.drawText(inner, Qt.AlignLeft | Qt.AlignTop,
                       bold_fm.elidedText(b.title, Qt.ElideRight, int(inner.width())))
            p.setFont(small)
            p.setPen(QColor(t.muted))
            p.drawText(inner.adjusted(0, bold_fm.height() + 2, 0, 0),
                       Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, b.subtitle)
        p.restore()

    # ---- interaction --------------------------------------------------------

    def event(self, e):
        if (e.type() == QEvent.NativeGesture
                and e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture):
            self.zoomRequested.emit(1 + e.value(), e.position().y())  # touchpad pinch
            return True
        if e.type() == QEvent.ToolTip:
            b = self._block_at(QPointF(e.pos()))
            if b:
                QToolTip.showText(e.globalPos(),
                                  f"<b>{html.escape(b.title)}</b><br>{html.escape(b.subtitle)}",
                                  self)
            else:
                QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)

    def mouseMoveEvent(self, e):
        over = self._block_at(e.position()) is not None
        self.setCursor(Qt.PointingHandCursor if over else Qt.ArrowCursor)
        super().mouseMoveEvent(e)

    def wheelEvent(self, e):
        # Ctrl+scroll zooms; plain scrolling goes to the scroll area.
        if e.modifiers() & Qt.ControlModifier and e.angleDelta().y():
            self.zoomRequested.emit(1.0015 ** e.angleDelta().y(), e.position().y())
            e.accept()
        else:
            super().wheelEvent(e)

    def mouseDoubleClickEvent(self, e):
        pos = e.position()
        b = self._block_at(pos)
        if b:
            self.blockActivated.emit(b.payload, e.globalPosition().toPoint())
        elif pos.x() > self.GUTTER:
            col = min(self.column_count - 1, int((pos.x() - self.GUTTER) // self.column_width()))
            minute = self.minute_at(pos.y())
            minute = int(minute // 15 * 15)
            self.emptyActivated.emit(col, max(0, min(minute, 24 * 60 - 15)))

    def contextMenuEvent(self, e):
        b = self._block_at(QPointF(e.pos()))
        if b:
            self.blockActivated.emit(b.payload, e.globalPos())


class TimelineZoom(QObject):
    """Vertical zoom for a TimeGrid in a scroll area.

    "Fit" squeezes the whole shown day into the visible height (and keeps doing so
    as the window resizes). Zooming by hand keeps the time under the pointer in
    place. Each view remembers its own setting.
    """

    changed = Signal()

    def __init__(self, grid: TimeGrid, scroll, key: str, parent=None):
        super().__init__(parent or grid)
        self.grid = grid
        self.scroll = scroll
        self._key = f"zoom/{key}"
        settings = QSettings()
        self.fit = settings.value(f"{self._key}/fit", True, type=bool)
        self.level = float(settings.value(f"{self._key}/hour", TimeGrid.DEFAULT_HOUR))
        scroll.viewport().installEventFilter(self)
        grid.zoomRequested.connect(self._zoom_at)
        self.apply()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Resize and self.fit:
            QTimer.singleShot(0, self.apply)
        return False

    def _fit_height(self) -> float | None:
        viewport = self.scroll.viewport().height()
        if viewport < 80 or self.grid.span_hours <= 0:
            return None
        return (viewport - 2 * TimeGrid.PAD - 1) / self.grid.span_hours

    def apply(self):
        """Re-apply after the grid's data (and so its hour range) changed."""
        height = self._fit_height() if self.fit else self.level
        if height is not None:
            self.grid.set_hour_height(height)

    def _save(self):
        settings = QSettings()
        settings.setValue(f"{self._key}/fit", self.fit)
        settings.setValue(f"{self._key}/hour", self.level)
        self.changed.emit()

    def set_fit(self, on: bool):
        self.fit = on
        if not on:
            self.level = self.grid.hour_height
        self.apply()
        self._save()

    def _zoom_at(self, factor: float, grid_y: float):
        bar = self.scroll.verticalScrollBar()
        minute = self.grid.minute_at(grid_y)
        offset = grid_y - bar.value()  # where that time sits in the viewport
        self.fit = False
        self.level = max(TimeGrid.MIN_HOUR, min(TimeGrid.MAX_HOUR,
                                                self.grid.hour_height * factor))
        self.grid.set_hour_height(self.level)
        QTimer.singleShot(0, lambda: bar.setValue(int(self.grid.y_for(minute) - offset)))
        self._save()

    def zoom_in(self):
        self._zoom_at(1.25, self._viewport_centre())

    def zoom_out(self):
        self._zoom_at(0.8, self._viewport_centre())

    def _viewport_centre(self) -> float:
        return self.scroll.verticalScrollBar().value() + self.scroll.viewport().height() / 2


class GridHeader(QWidget):
    """Day names above a TimeGrid; lives outside the scroll area so it stays put."""

    def __init__(self, grid: TimeGrid, parent=None):
        super().__init__(parent)
        self.grid = grid
        self.days: list[tuple[str, int]] = []  # (weekday abbreviation, day of month)
        self.current = -1
        self.setFixedHeight(58)

    def set_days(self, days, current=-1):
        self.days = list(days)
        self.current = current
        self.update()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        area = self.contentsRect()
        colw = (area.width() - TimeGrid.GUTTER) / max(1, len(self.days))
        label_font = scaled_font(self, 0.78, bold=True)
        label_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        number_font = scaled_font(self, 1.35, bold=True)
        for i, (name, number) in enumerate(self.days):
            x = TimeGrid.GUTTER + i * colw
            today = i == self.current
            p.setFont(label_font)
            p.setPen(QColor(t.accent if today else t.faint))
            p.drawText(QRectF(x, 6, colw, 16), Qt.AlignCenter, name.upper())
            circle = QRectF(x + colw / 2 - 15, 24, 30, 30)
            if today:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(t.accent))
                p.drawEllipse(circle)
            p.setFont(number_font)
            p.setPen(QColor(t.on_accent if today else t.text))
            p.drawText(circle, Qt.AlignCenter, str(number))
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()


class TwoLineDelegate(QStyledItemDelegate):
    """List row with a colour dot, a bold title and a muted second line.

    Title comes from the display role; the rest from the roles below.
    """

    META = Qt.UserRole + 1
    COLOR = Qt.UserRole + 2
    PINNED = Qt.UserRole + 3
    HEADER = Qt.UserRole + 4  # 1 = group heading, 2 = sub-heading; rows without it are items
    COUNT = Qt.UserRole + 5
    INDENT = Qt.UserRole + 6
    COLLAPSED = Qt.UserRole + 7
    ALERT = Qt.UserRole + 8  # e.g. overdue: title in the danger colour

    CHECK = 18  # diameter of the round checkbox on checkable rows

    def sizeHint(self, option, index):
        level = index.data(self.HEADER)
        if level == 1:
            return QSize(0, 34)
        if level == 2:
            return QSize(0, 28)
        return QSize(0, 54)

    def _check_rect(self, option) -> QRectF:
        r = QRectF(option.rect)
        return QRectF(r.left() + 10, r.top() + 17 - self.CHECK / 2 + 2, self.CHECK, self.CHECK)

    def editorEvent(self, event, model, option, index):
        # Clicking the round checkbox toggles the row's check state.
        if (index.data(Qt.CheckStateRole) is not None and not index.data(self.HEADER)
                and event.type() == QEvent.MouseButtonRelease
                and self._check_rect(option).adjusted(-4, -4, 4, 4).contains(event.position())):
            checked = index.data(Qt.CheckStateRole) == Qt.Checked
            model.setData(index, Qt.Unchecked if checked else Qt.Checked, Qt.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)

    def _paint_header(self, p, option, index, level, t):
        r = QRectF(option.rect)
        x = r.left() + 8
        if option.state & QStyle.State_MouseOver:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(0, 1, 0, -1), 6, 6)
            p.fillPath(path, QColor(t.hover))
        if level == 2:
            x += 8
        collapsed = index.data(self.COLLAPSED)
        if collapsed is not None:  # only collapsible headings get an arrow
            chevron = "chevron-right" if collapsed else "chevron-down"
            p.drawPixmap(int(x), int(r.center().y() - 7), icons.pixmap(chevron, t.faint, 14))
            x += 20
        color = index.data(self.COLOR)
        if level == 1 and color:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x + 4, r.center().y()), 4, 4)
            x += 14
        font = scaled_font(option.widget or self.parent(), 0.95 if level == 1 else 0.88,
                           bold=level == 1)
        p.setFont(font)
        count = str(index.data(self.COUNT) or "")
        count_w = QFontMetrics(font).horizontalAdvance(count) + 12
        p.setPen(QColor(t.text if level == 1 else t.muted))
        title = QFontMetrics(font).elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight,
                                             int(r.right() - x - count_w))
        p.drawText(QRectF(x, r.top(), r.right() - x - count_w, r.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setPen(QColor(t.faint))
        p.drawText(QRectF(r.right() - count_w, r.top(), count_w - 8, r.height()),
                   Qt.AlignRight | Qt.AlignVCenter, count)

    def paint(self, p, option, index):
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        level = index.data(self.HEADER)
        if level:
            self._paint_header(p, option, index, level, t)
            p.restore()
            return
        r = QRectF(option.rect).adjusted(index.data(self.INDENT) or 0, 2, 0, -2)
        if option.state & QStyle.State_Selected:
            bg = QColor(t.accent_soft)
        elif option.state & QStyle.State_MouseOver:
            bg = QColor(t.hover)
        else:
            bg = None
        if bg is not None:
            path = QPainterPath()
            path.addRoundedRect(r, 8, 8)
            p.fillPath(path, bg)

        x = r.left() + 12
        checkable = index.data(Qt.CheckStateRole) is not None
        checked = index.data(Qt.CheckStateRole) == Qt.Checked
        if checkable:
            box = self._check_rect(option)
            if checked:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(t.accent))
                p.drawEllipse(box)
                p.drawPixmap(int(box.left() + 3), int(box.top() + 3),
                             icons.pixmap("check", t.on_accent, int(self.CHECK - 6)))
            else:
                p.setPen(QPen(QColor(t.faint), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(box.adjusted(0.75, 0.75, -0.75, -0.75))
            x = box.right() + 10
        color = index.data(self.COLOR)
        if color:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x + 4, r.top() + 17), 4, 4)
        x += 16
        right = r.right() - 10
        if index.data(self.PINNED):
            pin = icons.pixmap("pin", t.accent, 14)
            p.drawPixmap(int(right - 14), int(r.top() + 10), pin)
            right -= 20

        title_font = scaled_font(option.widget or self.parent(), 1.0, bold=True)
        title_font.setStrikeOut(checked)
        meta_font = scaled_font(option.widget or self.parent(), 0.85)
        p.setFont(title_font)
        alert = index.data(self.ALERT)
        p.setPen(QColor(t.faint if checked else t.danger if alert else t.text))
        title = QFontMetrics(title_font).elidedText(index.data(Qt.DisplayRole) or "",
                                                   Qt.ElideRight, int(right - x))
        p.drawText(QRectF(x, r.top() + 6, right - x, 22), Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setFont(meta_font)
        p.setPen(QColor(t.muted))
        meta = QFontMetrics(meta_font).elidedText(index.data(self.META) or "", Qt.ElideRight,
                                                  int(r.right() - 10 - x))
        p.drawText(QRectF(x, r.top() + 27, r.right() - 10 - x, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, meta)
        p.restore()


def mark_color(value: float | None, t) -> str:
    """Italian 1-10 marks: red below 6, amber below 7, green from 7."""
    if value is None:
        return t.muted
    if value < 6:
        return t.danger
    if value < 7:
        return "#f5a524"
    return t.success


class SubjectDelegate(QStyledItemDelegate):
    """Rows of the School page's subject list.

    Subject rows: dot, name, latest marks as chips, a trend sparkline and the
    average in a pill. Grade rows (shown when a subject is expanded): what the
    mark was for, its date and the mark.
    """

    KIND = Qt.UserRole + 30  # "subject" or "grade"
    COLOR = Qt.UserRole + 31
    AVERAGE = Qt.UserRole + 32
    CHIPS = Qt.UserRole + 33  # [(display, value, cancelled)], newest first
    TREND = Qt.UserRole + 34  # [values], oldest first
    EXPANDED = Qt.UserRole + 35
    META = Qt.UserRole + 36

    PILL_W = 58
    SPARK_W = 84

    def sizeHint(self, option, index):
        return QSize(0, 58 if index.data(self.KIND) == "subject" else 34)

    def _chip(self, p, rect: QRectF, text: str, value, cancelled, t, font):
        color = QColor(t.faint if cancelled else mark_color(value, t))
        fill = QColor(color)
        fill.setAlpha(40 if t.dark else 28)
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.fillPath(path, fill)
        p.setPen(color)
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, text)

    def paint(self, p, option, index):
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(0, 2, 0, -2)
        if option.state & QStyle.State_MouseOver:
            path = QPainterPath()
            path.addRoundedRect(r, 8, 8)
            p.fillPath(path, QColor(t.hover))
        widget = option.widget or self.parent()
        if index.data(self.KIND) == "subject":
            self._paint_subject(p, r, index, t, widget)
        else:
            self._paint_grade(p, r, index, t, widget)
        p.restore()

    def _paint_subject(self, p, r, index, t, widget):
        cy = r.center().y()
        chevron = "chevron-down" if index.data(self.EXPANDED) else "chevron-right"
        p.drawPixmap(int(r.left() + 6), int(cy - 7), icons.pixmap(chevron, t.faint, 14))
        x = r.left() + 28
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(index.data(self.COLOR) or t.faint))
        p.drawEllipse(QPointF(x + 5, cy - 7), 5, 5)
        x += 18

        # Average pill on the right.
        avg = index.data(self.AVERAGE)
        pill = QRectF(r.right() - self.PILL_W - 8, cy - 14, self.PILL_W, 28)
        bold = scaled_font(widget, 1.0, bold=True)
        self._chip(p, pill, f"{avg:.2f}" if avg is not None else "–", avg, False, t, bold)
        right = pill.left() - 12

        # Trend sparkline, with the pass line at 6.
        values = [v for v in (index.data(self.TREND) or []) if v is not None]
        if len(values) >= 2 and right - self.SPARK_W > x + 120:
            box = QRectF(right - self.SPARK_W, cy - 14, self.SPARK_W, 28)
            lo, hi = min(min(values), 5.0), max(max(values), 8.0)
            to_y = lambda v: box.bottom() - (v - lo) / (hi - lo) * box.height()  # noqa: E731
            pass_pen = QPen(QColor(t.border), 1, Qt.DashLine)
            p.setPen(pass_pen)
            p.drawLine(QPointF(box.left(), to_y(6.0)), QPointF(box.right(), to_y(6.0)))
            step = box.width() / (len(values) - 1)
            points = [QPointF(box.left() + i * step, to_y(v)) for i, v in enumerate(values)]
            p.setPen(QPen(QColor(mark_color(avg, t)), 1.8))
            for a, b in zip(points, points[1:]):
                p.drawLine(a, b)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(mark_color(values[-1], t)))
            p.drawEllipse(points[-1], 3, 3)
            right = box.left() - 12

        # Latest marks as chips, as many as fit.
        small = scaled_font(widget, 0.85, bold=True)
        fm = QFontMetrics(small)
        for display, value, cancelled in index.data(self.CHIPS) or []:
            w = max(30, fm.horizontalAdvance(display) + 16)
            if right - w < x + 140:
                break
            self._chip(p, QRectF(right - w, cy - 11, w, 22), display, value, cancelled, t, small)
            right -= w + 5

        name_font = scaled_font(widget, 1.02, bold=True)
        p.setFont(name_font)
        p.setPen(QColor(t.text))
        name = QFontMetrics(name_font).elidedText(index.data(Qt.DisplayRole) or "",
                                                 Qt.ElideRight, int(right - x - 8))
        p.drawText(QRectF(x, r.top() + 7, right - x, 22), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setFont(scaled_font(widget, 0.85))
        p.setPen(QColor(t.muted))
        p.drawText(QRectF(x, r.top() + 29, right - x, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   index.data(self.META) or "")

    def _paint_grade(self, p, r, index, t, widget):
        x = r.left() + 46
        display, value, cancelled = index.data(self.CHIPS)[0]
        small = scaled_font(widget, 0.85, bold=True)
        w = max(30, QFontMetrics(small).horizontalAdvance(display) + 16)
        chip = QRectF(r.right() - 8 - (self.PILL_W + w) / 2, r.center().y() - 11, w, 22)
        self._chip(p, chip, display, value, cancelled, t, small)
        body = scaled_font(widget, 0.92)
        fm = QFontMetrics(body)
        date_text = index.data(self.META) or ""
        date_w = fm.horizontalAdvance(date_text) + 16
        p.setFont(body)
        p.setPen(QColor(t.faint))
        p.drawText(QRectF(chip.left() - date_w - 8, r.top(), date_w, r.height()),
                   Qt.AlignRight | Qt.AlignVCenter, date_text)
        p.setPen(QColor(t.text if not cancelled else t.faint))
        what = fm.elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight,
                             int(chip.left() - date_w - 16 - x))
        p.drawText(QRectF(x, r.top(), chip.left() - x, r.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, what)



class ProgressRing(QWidget):
    """The Focus page's big round timer: a ring that fills as the phase goes by."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0
        self.time_text = "25:00"
        self.label = "Focus"
        self.color = PALETTE[0]
        self.dots = (0, 4)  # (done, total) rounds
        self.setMinimumSize(260, 260)

    def set_state(self, progress: float, time_text: str, label: str, color: str,
                  dots: tuple[int, int]):
        self.progress, self.time_text, self.label = progress, time_text, label
        self.color, self.dots = color, dots
        self.update()

    def paintEvent(self, _event):
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 16
        ring = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        thickness = max(10.0, side * 0.045)
        inner = ring.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2)

        p.setPen(QPen(QColor(t.border), thickness, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(inner)
        if self.progress > 0:
            p.setPen(QPen(QColor(self.color), thickness, Qt.SolidLine, Qt.RoundCap))
            # Qt angles are in 1/16 degree, counter-clockwise from 3 o'clock.
            p.drawArc(inner, 90 * 16, int(-360 * 16 * min(self.progress, 1.0)))

        big = QFont(self.font())
        big.setPointSizeF(max(20.0, side / 7.5))
        big.setBold(True)
        p.setFont(big)
        p.setPen(QColor(t.text))
        p.drawText(QRectF(ring.left(), ring.center().y() - side * 0.16, side, side * 0.22),
                   Qt.AlignCenter, self.time_text)

        small = scaled_font(self, max(0.9, side / 330), bold=True)
        small.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        p.setFont(small)
        p.setPen(QColor(self.color))
        p.drawText(QRectF(ring.left(), ring.center().y() - side * 0.30, side, side * 0.12),
                   Qt.AlignCenter, self.label.upper())

        done, total = self.dots
        r = max(4.0, side / 70)
        gap = r * 3.2
        x0 = ring.center().x() - gap * (total - 1) / 2
        y = ring.center().y() + side * 0.20
        for i in range(total):
            p.setPen(Qt.NoPen if i < done else QPen(QColor(t.faint), 1.5))
            p.setBrush(QColor(self.color) if i < done else Qt.NoBrush)
            p.drawEllipse(QPointF(x0 + i * gap, y), r, r)
        p.end()
