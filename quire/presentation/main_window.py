from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget

from .. import DEVELOPER, HOMEPAGE, __version__
from ..application.services import Services
from .bridge import ChangeRelay
from .dialogs import CoursesDialog, EventDialog, TaskDialog
from .views.coursework import CourseworkView
from .views.notes import NotesView
from .views.today import TodayView
from .views.week import WeekView


class MainWindow(QMainWindow):
    def __init__(self, services: Services):
        super().__init__()
        self.services = services
        self.setWindowTitle("Quire")
        self.resize(1180, 780)

        relay = ChangeRelay(services.bus, self)
        self.today = TodayView(services, relay)
        self.week = WeekView(services, relay)
        self.coursework = CourseworkView(services, relay)
        self.notes = NotesView(services, relay)

        self.tabs = QTabWidget(documentMode=True)
        self.tabs.addTab(self.today, "Today")
        self.tabs.addTab(self.week, "Week")
        self.tabs.addTab(self.coursework, "Coursework")
        self.tabs.addTab(self.notes, "Notes")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        self.today.openClassNote.connect(self.open_class_note)
        self.week.openClassNote.connect(self.open_class_note)

        self._build_menus()

        settings = QSettings()
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.tabs.setCurrentIndex(int(settings.value("window/tab", 0)))

    def _action(self, menu, text, slot, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menus(self):
        bar = self.menuBar()
        file = bar.addMenu("&File")
        self._action(file, "New note", self.new_note, "Ctrl+N")
        self._action(file, "New task…",
                     lambda: TaskDialog(self.services, due=self.today.day, parent=self).exec(),
                     "Ctrl+T")
        self._action(file, "New event…",
                     lambda: EventDialog(self.services, day=self.today.day, parent=self).exec(),
                     "Ctrl+Shift+E")
        self._action(file, "Courses && timetable…",
                     lambda: CoursesDialog(self.services, self).exec(), "Ctrl+Shift+C")
        file.addSeparator()
        self._action(file, "Back up data…", self.backup)
        self._action(file, "Open data folder", self.open_data_folder)
        file.addSeparator()
        self._action(file, "Quit", self.close, QKeySequence.Quit)

        view = bar.addMenu("&View")
        for i, name in enumerate(["Today", "Week", "Coursework", "Notes"]):
            self._action(view, name, lambda _=False, i=i: self.tabs.setCurrentIndex(i),
                         f"Ctrl+{i + 1}")
        view.addSeparator()
        self._action(view, "Go to today", self._go_today, "Ctrl+D")
        self._action(view, "Search notes", self._search_notes, QKeySequence.Find)

        help_menu = bar.addMenu("&Help")
        self._action(help_menu, "About Quire", self.about)

    # ---- actions ----------------------------------------------------------

    def _tab_changed(self, index):
        if self.tabs.widget(index) is not self.notes:
            self.notes.flush()

    def new_note(self):
        self.tabs.setCurrentWidget(self.notes)
        self.notes.new_note()

    def open_class_note(self, course_id, day):
        self.tabs.setCurrentWidget(self.notes)
        self.notes.open_class_note(course_id, day)

    def _go_today(self):
        self.tabs.setCurrentWidget(self.today)
        self.today.set_day(self.services.planner.today())

    def _search_notes(self):
        self.tabs.setCurrentWidget(self.notes)
        self.notes.search.setFocus()
        self.notes.search.selectAll()

    def _flush(self):
        self.notes.flush()
        self.today.flush_journal()

    def backup(self):
        self._flush()
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up data", f"quire-backup-{date.today().isoformat()}.db",
            "Quire database (*.db)")
        if path:
            self.services.storage.backup_to(path)
            self.statusBar().showMessage(f"Backed up to {path}", 5000)

    def open_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.services.storage.location.parent)))

    def about(self):
        QMessageBox.about(
            self, "About Quire",
            f"<h3>Quire {__version__}</h3>"
            "<p>Notes, day planner and school timetable.</p>"
            f"<p>By {DEVELOPER} · <a href='{HOMEPAGE}'>{HOMEPAGE}</a></p>"
            f"<p>Your data lives in:<br><code>{self.services.storage.location}</code></p>")

    def closeEvent(self, event):
        self._flush()
        settings = QSettings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/tab", self.tabs.currentIndex())
        super().closeEvent(event)
