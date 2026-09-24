from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSettings, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import DEVELOPER, HOMEPAGE, __version__
from ..application.services import Services
from . import theme
from .bridge import ChangeRelay
from .dialogs import CoursesDialog, EventDialog, JobsDialog, ShiftDialog, TaskDialog
from .icons import APP_ICON
from .views.coursework import CourseworkView
from .views.notes import NotesView
from .views.school import SchoolView
from .views.today import TodayView
from .views.week import WeekView
from .settings import SettingsDialog
from .reminders import Reminders
from .views.focus import FocusView
from .views.work import WorkView
from .i18n import N_, _


class Sidebar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(216)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)

        brand_icon = QLabel()
        brand_icon.setPixmap(QIcon(str(APP_ICON)).pixmap(28, 28))
        brand = QHBoxLayout()
        brand.setContentsMargins(12, 4, 12, 0)
        brand.setSpacing(10)
        brand.addWidget(brand_icon)
        brand.addWidget(QLabel(_("Quire"), objectName="brand"))
        brand.addStretch()

        self.nav = QVBoxLayout()
        self.nav.setSpacing(2)
        self.footer = QVBoxLayout()
        self.footer.setSpacing(2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 14)
        layout.setSpacing(6)
        layout.addLayout(brand)
        layout.addSpacing(18)
        layout.addLayout(self.nav)
        layout.addStretch()
        layout.addLayout(self.footer)

    def nav_button(self, icon_name: str, text: str, checkable: bool = True) -> QToolButton:
        button = QToolButton(objectName="nav", text=f"  {text}", checkable=checkable)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.setIconSize(QSize(18, 18))
        button.setCursor(Qt.PointingHandCursor)
        theme.set_icon(button, icon_name, "muted", "accent" if checkable else None)
        return button

    def add_page(self, icon_name: str, text: str, shortcut: str) -> QToolButton:
        button = self.nav_button(icon_name, text)
        button.setToolTip(f"{text}  ({shortcut})")
        self.group.addButton(button, len(self.group.buttons()))
        self.nav.addWidget(button)
        return button


class MainWindow(QMainWindow):
    PAGES = [("today", N_("Today")), ("week", N_("Week")), ("coursework", N_("Coursework")),
             ("notes", N_("Notes")), ("school", N_("School")), ("briefcase", N_("Work")),
             ("timer", N_("Focus"))]

    def __init__(self, services: Services):
        super().__init__()
        self.services = services
        self.setWindowTitle(_("Quire"))
        self.resize(1240, 800)
        self.setMinimumSize(980, 620)

        relay = ChangeRelay(services.bus, self)
        self.today = TodayView(services, relay)
        self.week = WeekView(services, relay)
        self.coursework = CourseworkView(services, relay)
        self.notes = NotesView(services, relay)
        self.school = SchoolView(services, relay)
        self.work = WorkView(services, relay)
        self.focus = FocusView(services, relay)

        self.sidebar = Sidebar()
        self.stack = QStackedWidget()
        for i, (page, (icon_name, label)) in enumerate(zip(
                [self.today, self.week, self.coursework, self.notes, self.school, self.work,
                 self.focus],
                self.PAGES)):
            self.stack.addWidget(page)
            self.sidebar.add_page(icon_name, _(label), f"Ctrl+{i + 1}")
        self.sidebar.group.idClicked.connect(self.show_page)
        self.school.newsChanged.connect(self._school_news)
        self.focus.statusChanged.connect(self._focus_status)
        self.reminders = Reminders(services.reminders, self)

        more = self.sidebar.nav_button("more", _("More"), checkable=False)
        more.setPopupMode(QToolButton.InstantPopup)
        more.setMenu(self._more_menu())
        self.sidebar.footer.addWidget(more)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.today.openClassNote.connect(self.open_class_note)
        self.week.openClassNote.connect(self.open_class_note)
        self.school.openClassNote.connect(self.open_class_note)
        self._shortcuts()

        settings = QSettings()
        geometry = settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self.show_page(int(settings.value("window/tab", 0)))

    # ---- navigation -------------------------------------------------------

    def show_page(self, index: int):
        if self.stack.currentWidget() is self.notes and index != 3:
            self.notes.flush()
        self.stack.setCurrentIndex(index)
        self.sidebar.group.button(index).setChecked(True)
        if self.stack.currentWidget() is self.school:
            self._school_news(0)

    def _focus_status(self, remaining: str):
        """Show the running focus timer on its sidebar entry and in the title bar."""
        button = self.sidebar.group.button(self.stack.indexOf(self.focus))
        button.setText("  " + _("Focus") + (f"   {remaining}" if remaining else ""))
        self.setWindowTitle(_("{remaining} · Quire").format(remaining=remaining) if remaining else _("Quire"))

    def _school_news(self, count: int):
        button = self.sidebar.group.button(self.stack.indexOf(self.school))
        seen = self.stack.currentWidget() is self.school
        badge = "   " + _("{count} new").format(count=count) if count and not seen else ""
        button.setText("  " + _("School") + badge)

    def _shortcut(self, keys, slot):
        action = QAction(self)
        action.setShortcut(QKeySequence(keys))
        action.setShortcutContext(Qt.ApplicationShortcut)
        action.triggered.connect(slot)
        self.addAction(action)

    def _shortcuts(self):
        for i in range(len(self.PAGES)):
            self._shortcut(f"Ctrl+{i + 1}", lambda _checked=False, i=i: self.show_page(i))
        self._shortcut("Ctrl+N", self.new_note)
        self._shortcut("Ctrl+T", self.new_task)
        self._shortcut("Ctrl+Shift+E", self.new_event)
        self._shortcut("Ctrl+Shift+C", self.open_courses)
        self._shortcut("Ctrl+Shift+W", self.new_shift)
        self._shortcut("Ctrl+,", self.open_settings)
        self._shortcut("Ctrl+D", self._go_today)
        self._shortcut("Ctrl+R", lambda: self.school.sync())
        self._shortcut(QKeySequence.Find, self._search_notes)
        self._shortcut(QKeySequence.Quit, self.close)

    def _more_menu(self) -> QMenu:
        menu = QMenu(self)
        entries = [
            (_("New task"), "Ctrl+T", self.new_task),
            (_("New event"), "Ctrl+Shift+E", self.new_event),
            (_("New note"), "Ctrl+N", self.new_note),
            (_("New work shift"), "Ctrl+Shift+W", self.new_shift),
            None,
            (_("Courses && timetable"), "Ctrl+Shift+C", self.open_courses),
            (_("Jobs"), None, lambda: JobsDialog(self.services, self).exec()),
            (_("Sync school register"), "Ctrl+R", lambda: self.school.sync()),
            None,
            (_("Settings…"), "Ctrl+,", self.open_settings),
            (_("Keyboard shortcuts"), None, self.show_shortcuts),
            (_("About Quire"), None, self.about),
        ]
        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            text, keys, slot = entry
            action = menu.addAction(text, slot)
            if keys:
                action.setShortcut(QKeySequence(keys))
                action.setShortcutVisibleInContextMenu(True)
                action.setShortcutContext(Qt.WidgetShortcut)  # the window-level ones fire
        return menu

    # ---- actions ----------------------------------------------------------

    def new_note(self):
        self.show_page(3)
        self.notes.new_note()

    def new_task(self):
        TaskDialog(self.services, due=self.today.day, parent=self).exec()

    def new_event(self):
        EventDialog(self.services, day=self.today.day, parent=self).exec()

    def open_settings(self):
        SettingsDialog(self.services, self.backup, self).exec()

    def new_shift(self):
        ShiftDialog(self.services, day=self.today.day, parent=self).exec()

    def open_courses(self):
        CoursesDialog(self.services, self).exec()

    def open_class_note(self, course_id, day):
        self.show_page(3)
        self.notes.open_class_note(course_id, day)

    def _go_today(self):
        self.show_page(0)
        self.today.set_day(self.services.planner.today())

    def _search_notes(self):
        self.show_page(3)
        self.notes.search.setFocus()
        self.notes.search.selectAll()

    def _flush(self):
        self.notes.flush()
        self.today.flush_journal()

    def backup(self):
        self._flush()
        path, _filter = QFileDialog.getSaveFileName(
            self, _("Back up data"), f"quire-backup-{date.today().isoformat()}.db",
            _("Quire database") + " (*.db)")
        if path:
            self.services.storage.backup_to(path)
            QMessageBox.information(self, _("Backed up"), _("Saved a copy of your data to\n{path}").format(path=path))

    def open_data_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.services.storage.location.parent)))

    def show_shortcuts(self):
        pages = " / ".join(_(label) for _icon, label in self.PAGES)
        rows = [("Ctrl+1 … 7", pages), ("Ctrl+,", _("Settings")),
                ("Ctrl+Shift+W", _("New work shift")), ("Ctrl+D", _("Jump to today")),
                ("Ctrl+R", _("Sync school register")), ("Ctrl+N", _("New note")),
                ("Ctrl+T", _("New task")), ("Ctrl+Shift+E", _("New event")),
                ("Ctrl+Shift+C", _("Courses & timetable")), ("Ctrl+F", _("Search notes")),
                ("Ctrl+E", _("Toggle note preview")),
                ("Ctrl+= / Ctrl+- / Ctrl+0", _("Zoom in / out / fit the day"))]
        table = "".join(f"<tr><td style='padding:3px 18px 3px 0'><b>{k}</b></td><td>{v}</td></tr>"
                        for k, v in rows)
        QMessageBox.information(self, _("Keyboard shortcuts"), f"<table>{table}</table>")

    def about(self):
        QMessageBox.about(
            self, _("About Quire"),
            f"<h3>Quire {__version__}</h3>"
            f"<p>{_('Notes, day planner and school timetable.')}</p>"
            f"<p>{_('By {developer}').format(developer=DEVELOPER)} · "
            f"<a href='{HOMEPAGE}'>{HOMEPAGE}</a></p>"
            f"<p>{_('Your data lives in:')}<br><code>{self.services.storage.location}</code></p>")

    def closeEvent(self, event):
        self._flush()
        settings = QSettings()
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/tab", self.stack.currentIndex())
        super().closeEvent(event)
