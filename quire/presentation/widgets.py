"""Reusable Qt widgets."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QColorDialog, QPushButton, QStyle, QStyledItemDelegate, QToolTip, QWidget

from . import icons, theme

PALETTE = [
    "#4f7cff", "#e5484d", "#30a46c", "#f5a524", "#8e4ec6",
    "#12a594", "#e93d82", "#f76b15", "#0090ff", "#978365",
]
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
        color = QColorDialog.getColor(QColor(self._color), self, "Pick a colour")
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


class TimeGrid(QWidget):
    """A vertical timeline with one or more day columns and coloured blocks.

    Used by both the single-day planner and the weekly timetable.
    """

    blockActivated = Signal(object, QPoint)  # payload, global position
    emptyActivated = Signal(int, int)  # column, minute (snapped to 15)

    GUTTER = 58
    HOUR = 64
    PAD = 10

    def __init__(self, parent=None):
        super().__init__(parent)
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

    def _recalc(self):
        start, end = 7 * 60, 21 * 60
        for b in self.blocks:
            start = min(start, b.start // 60 * 60)
            end = max(end, -(-b.end // 60) * 60)
        self.start_min = max(0, start)
        self.end_min = min(24 * 60, end)
        self.setMinimumHeight(int(self.y_for(self.end_min) + self.PAD))

    def y_for(self, minute: int) -> float:
        return self.PAD + (minute - self.start_min) * self.HOUR / 60

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
                y0, y1 = self.y_for(b.start), self.y_for(b.end)
                out.append((b, QRectF(x, y0, colw / n, max(20.0, y1 - y0))))

        for col in range(self.column_count):
            items = sorted((b for b in self.blocks if b.column == col),
                           key=lambda b: (b.start, -b.end))
            cluster, lanes, cluster_end = [], [], -1
            for b in items:
                if cluster and b.start >= cluster_end:
                    place(cluster, lanes, col)
                    cluster, lanes = [], []
                if not cluster:
                    cluster_end = b.end
                for i, lane_end in enumerate(lanes):
                    if lane_end <= b.start:
                        lanes[i] = b.end
                        lane = i
                        break
                else:
                    lanes.append(b.end)
                    lane = len(lanes) - 1
                cluster.append((b, lane))
                cluster_end = max(cluster_end, b.end)
            place(cluster, lanes, col)
        return out

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

    def mouseDoubleClickEvent(self, e):
        pos = e.position()
        b = self._block_at(pos)
        if b:
            self.blockActivated.emit(b.payload, e.globalPosition().toPoint())
        elif pos.x() > self.GUTTER:
            col = min(self.column_count - 1, int((pos.x() - self.GUTTER) // self.column_width()))
            minute = self.start_min + (pos.y() - self.PAD) * 60 / self.HOUR
            minute = int(minute // 15 * 15)
            self.emptyActivated.emit(col, max(0, min(minute, 24 * 60 - 15)))

    def contextMenuEvent(self, e):
        b = self._block_at(QPointF(e.pos()))
        if b:
            self.blockActivated.emit(b.payload, e.globalPos())


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

    def sizeHint(self, option, index):
        return QSize(0, 54)

    def paint(self, p, option, index):
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(0, 2, 0, -2)
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
        meta_font = scaled_font(option.widget or self.parent(), 0.85)
        p.setFont(title_font)
        p.setPen(QColor(t.text))
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
