# Quire

*A quire is a bundle of pages folded together, the old name for a notebook section.*

Quire is a native desktop app for **Linux and Windows** that puts your school timetable, a day
planner and your notes in one place. Built with Python and Qt 6 (PySide6). Your data stays on
your machine in a single SQLite file.

## Features

- **Today**: a timeline of today's classes and events with a live "now" line. Beside it are
  tasks due today, overdue work carried over from earlier days, a quick-add box and a
  free-form **day notes** journal.
- **Week**: your weekly school timetable in colour, with one-off events layered on top.
  Saturday and Sunday appear only when something is scheduled on them.
  - Double-click an empty slot to add an event.
  - Double-click (or right-click) a class to:
    - open **that lesson's notes**, which are created automatically and filed under the course;
    - **add homework**, with the due date defaulting to the next time that class meets;
    - edit the course.
- **Coursework**: every task, homework, assignment, reading and exam, grouped by Overdue,
  Today, Next 7 days, Later and No date. You can filter by course, tick items off, and
  press Delete to remove one.
- **Notes**: Markdown notes with live search, course filing, pinning, autosave and a
  preview mode (Ctrl+E). Checklists work: `- [ ]`.
- Follows your system's light or dark theme. **File → Back up data…** writes a copy of
  your database.

### Keyboard shortcuts

| Keys | Action |
| --- | --- |
| Ctrl+1 … Ctrl+4 | Today / Week / Coursework / Notes |
| Ctrl+N | New note |
| Ctrl+T | New task |
| Ctrl+Shift+E | New event |
| Ctrl+Shift+C | Courses & timetable |
| Ctrl+D | Jump to today |
| Ctrl+F | Search notes |
| Ctrl+E | Toggle note preview |

## Running from source

```bash
python3 -m venv .venv
.venv/bin/pip install -e .          # Windows: .venv\Scripts\pip install -e .
.venv/bin/quire                     # or: python -m quire
.venv/bin/quire --demo              # try it with sample data (separate throwaway database)
```

Data lives in `~/.local/share/Quire/quire.db` on Linux and `%APPDATA%\Quire\quire.db` on
Windows. Use `--db path/to/file.db` to point somewhere else.

## Installing

**Linux (per-user, adds a menu entry):**

```bash
./scripts/install-linux.sh
```

**Standalone builds (Linux binary or Windows .exe):**

```bash
pip install -e ".[build]"
python scripts/build.py --onefile   # output in dist/
```

PyInstaller builds for the platform it runs on, so run the build on Windows to get
`Quire.exe`. The GitHub Actions workflow in `.github/workflows/build.yml` builds both on every
push and uploads them as artifacts.

## Architecture

Quire follows **Clean Architecture**: source-code dependencies point only inward.

```
            ┌──────────────────────────────────────────────┐
            │ presentation/   Qt widgets, views, dialogs    │
            │ infrastructure/ SQLite repositories, clock    │
            │   ┌──────────────────────────────────────┐   │
            │   │ application/  use cases, ports, DTOs  │   │
            │   │   ┌──────────────────────────────┐   │   │
            │   │   │ domain/  entities & rules     │   │   │
            │   │   └──────────────────────────────┘   │   │
            │   └──────────────────────────────────────┘   │
            └──────────────────────────────────────────────┘
                bootstrap.py (composition root) wires it all
```

| Layer | Contents | May depend on |
| --- | --- | --- |
| `quire/domain` | `Course`, `ClassSlot`, `TimeRange`, `Event`, `Task`, `Note`, and rules such as due-date buckets, next class meeting, note titles and validation | nothing |
| `quire/application` | Use-case services (`TimetableService`, `PlannerService`, `TaskService`, `NoteService`), repository **ports** (`Protocol`s), read-model DTOs, and a framework-free `ChangeBus` | domain |
| `quire/infrastructure` | `SqliteDatabase`, SQLite repositories implementing the ports, the system clock and platform data paths | application, domain |
| `quire/presentation` | PySide6 UI. It talks only to the `Services` facade and adapts `ChangeBus` into a Qt signal (`bridge.py`) | application, domain |
| `quire/bootstrap.py` | Composition root: builds repositories and injects them into services | everything |

The rule is enforced by `tests/test_architecture.py`, which parses every module's imports.
For example, if you import `sqlite3` or `PySide6` into the domain, the test suite fails.

The domain and application layers never touch Qt or SQL, so they are tested directly
against an in-memory database with a fixed clock:

```bash
pip install pytest
pytest
```

## Adding a feature

1. Put the rules on the entity in `domain/` and unit-test them.
2. If you need new data access, add it to the port in `application/ports.py`, then implement
   it in `infrastructure/repositories.py`.
3. Expose the new behaviour as a use-case method on a service. Return a DTO if the UI needs a
   shaped view of the data.
4. Call that method from `presentation/`. UI code should never reach past the service.
