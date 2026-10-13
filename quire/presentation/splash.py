"""The start-up splash: a borderless card with the app icon, name, version, what Quire is doing
right now and a thin progress bar, in the manner of big desktop apps. It appears before the
database is opened, so it covers the slow part of starting, and fades out once the window is up.
"""
from __future__ import annotations

import time

from PySide6.QtCore import (
    QEasingCurve, QEventLoop, QPointF, QRectF, Qt, QTimer, QVariantAnimation,
)
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

from .i18n import _
from .icons import APP_ICON

CARD_WIDTH, CARD_HEIGHT = 620, 340
MARGIN = 26  # room around the card for its shadow
RADIUS = 18
ACCENT = QColor("#f5a524")  # the bookmark in the icon


class SplashScreen(QWidget):
    MIN_VISIBLE_MS = 900  # long enough to read, even when Quire starts quickly
    FADE_IN_MS = 180
    FADE_OUT_MS = 240
    STEP_MS = 140

    def __init__(self, version: str):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(CARD_WIDTH + 2 * MARGIN, CARD_HEIGHT + 2 * MARGIN)
        self.version = version
        self.status = ""
        self.progress = 0.0
        self._shown_at = 0.0
        self._closing = False
        self._icon = QSvgRenderer(str(APP_ICON))

    # ---- showing it ---------------------------------------------------------------

    def show(self):
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.setWindowOpacity(0.0)
        super().show()
        self._shown_at = time.monotonic()
        self._animate(self.FADE_IN_MS, 0.0, 1.0, self.setWindowOpacity)
        QApplication.processEvents()

    def step(self, status: str, progress: float):
        """Say what is happening and how far along it is (0 to 1). The bar glides there; this
        returns once it has, so the next slow thing starts with a painted splash."""
        if self._closing:
            return
        self.status = status
        start, target = self.progress, max(self.progress, min(1.0, progress))
        self._animate(self.STEP_MS, start, target, self._set_progress)

    def finish(self):
        """Fade away once it has been up long enough. Safe to call from the event loop."""
        if self._closing:
            return
        self._closing = True
        wait = self.MIN_VISIBLE_MS - int((time.monotonic() - self._shown_at) * 1000)
        QTimer.singleShot(max(0, wait), self._fade_out)

    def close_now(self):
        self._closing = True
        self.close()
        self.deleteLater()

    def _fade_out(self):
        self._set_progress(1.0)
        animation = self._animate(self.FADE_OUT_MS, self.windowOpacity(), 0.0,
                                  self.setWindowOpacity, wait=False)
        animation.finished.connect(self.close_now)

    # ---- animation ------------------------------------------------------------------

    def _set_progress(self, value: float):
        self.progress = float(value)
        self.update()

    def _animate(self, ms: int, start: float, end: float, apply, wait: bool = True):
        animation = QVariantAnimation(self, duration=ms, startValue=float(start),
                                      endValue=float(end))
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.valueChanged.connect(apply)
        if wait and start != end:
            loop = QEventLoop(self)
            animation.finished.connect(loop.quit)
            animation.start(QVariantAnimation.DeleteWhenStopped)
            loop.exec()  # keeps painting while the caller's slow work is still to come
        else:
            animation.start(QVariantAnimation.DeleteWhenStopped)
        return animation

    # ---- painting -------------------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                               | QPainter.SmoothPixmapTransform)
        card = QRectF(MARGIN, MARGIN, CARD_WIDTH, CARD_HEIGHT)
        self._paint_shadow(painter, card)

        shape = QPainterPath()
        shape.addRoundedRect(card, RADIUS, RADIUS)
        painter.setClipPath(shape)
        background = QLinearGradient(card.topLeft(), card.bottomRight())
        background.setColorAt(0.0, QColor("#3a3a7a"))
        background.setColorAt(1.0, QColor("#1a1a40"))
        painter.fillPath(shape, background)
        self._paint_pages(painter, card)

        icon = QRectF(card.left() + 46, card.center().y() - 96, 150, 150)
        self._icon.render(painter, icon)

        left = icon.right() + 38
        width = card.right() - left - 30
        title = QFont(self.font())
        title.setPointSizeF(40)
        title.setWeight(QFont.Bold)
        painter.setFont(title)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(left, card.top() + 84, width, 64), Qt.AlignLeft | Qt.AlignVCenter,
                         "Quire")

        small = QFont(self.font())
        small.setPointSizeF(12)
        painter.setFont(small)
        painter.setPen(QColor(255, 255, 255, 175))
        painter.drawText(QRectF(left, card.top() + 150, width, 28), Qt.AlignLeft | Qt.AlignVCenter,
                         _("Notes, planner and timetable."))
        smaller = QFont(self.font())
        smaller.setPointSizeF(10)
        painter.setFont(smaller)
        painter.setPen(QColor(255, 255, 255, 120))
        painter.drawText(QRectF(left, card.top() + 182, width, 24), Qt.AlignLeft | Qt.AlignVCenter,
                         _("Version {version}").format(version=self.version))

        painter.setFont(smaller)
        painter.setPen(QColor(255, 255, 255, 190))
        painter.drawText(QRectF(card.left() + 46, card.bottom() - 62, card.width() - 92, 24),
                         Qt.AlignLeft | Qt.AlignVCenter, self.status)

        track = QRectF(card.left(), card.bottom() - 5, card.width(), 5)
        painter.fillRect(track, QColor(255, 255, 255, 28))
        painter.fillRect(QRectF(track.left(), track.top(), track.width() * self.progress,
                                track.height()), ACCENT)

    @staticmethod
    def _paint_shadow(painter: QPainter, card: QRectF):
        painter.setPen(Qt.NoPen)
        for i in range(MARGIN, 0, -2):
            painter.setBrush(QColor(0, 0, 0, 3 + (MARGIN - i) // 2))
            painter.drawRoundedRect(card.adjusted(-i, -i + 6, i, i + 6), RADIUS + i, RADIUS + i)

    @staticmethod
    def _paint_pages(painter: QPainter, card: QRectF):
        """A few faint, tilted pages behind the right-hand side: the icon's gathering of pages,
        large and out of focus."""
        painter.save()
        painter.setPen(QPen(QColor(255, 255, 255, 14), 1))
        for turn, alpha, dx in ((16, 10, 0), (9, 14, 34), (2, 18, 68)):
            painter.save()
            painter.translate(QPointF(card.right() - 120 + dx, card.bottom() - 40))
            painter.rotate(turn)
            painter.setBrush(QColor(255, 255, 255, alpha))
            painter.drawRoundedRect(QRectF(-120, -250, 240, 310), 20, 20)
            painter.restore()
        painter.restore()
