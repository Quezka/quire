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
- **School (Classeviva)**: connect your Classeviva student account to pull in what teachers
  post:
  - homework and tests from the agenda, which land in Coursework and Today;
  - grades, with per-subject and overall averages;
  - lesson topics from the class register.

  Your subjects become courses automatically; courses you already made are matched by name.
  Quire re-syncs every 30 minutes while it's open, and on demand with Ctrl+R. You get a
  desktop notification when something new appears. Ticking off an imported task sticks
  across syncs. If a teacher deletes an assignment, Quire removes it too, unless you had
  already finished it.
- A modern sidebar layout with light and dark themes. It follows your system by default; change
  it under **More → Appearance**. **More → Back up data…** writes a copy of your database.

### About the Classeviva connection

Classeviva has no public API. Quire uses the same REST API as the official Classeviva mobile
app (endpoints as documented by the community in
[Classeviva-Official-Endpoints](https://github.com/Lioydiano/Classeviva-Official-Endpoints)).
If Spaggiari changes that API, the sync may stop working until Quire is updated.

- Your password goes into the operating system's keyring (GNOME Keyring or KWallet on Linux,
  Credential Manager on Windows). It is never written to Quire's database.
- Quire only contacts `web.spaggiari.eu`, and only while you're connected.
- **More → Sync school register** (Ctrl+R) syncs now. The **⋯** menu on the School page
  disconnects the account. Imported items stay after you disconnect.
- Accounts linked to several students (for example a parent account) sync the first one.

### Keyboard shortcuts

| Keys | Action |
| --- | --- |
| Ctrl+1 … Ctrl+5 | Today / Week / Coursework / Notes / School |
| Ctrl+R | Sync school register |
| Ctrl+N | New note |
| Ctrl+T | New task |
| Ctrl+Shift+E | New event |
| Ctrl+Shift+C | Courses & timetable |
| Ctrl+Q | Quit |
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

**Debian / Ubuntu (.deb):**

```bash
pip install -e ".[build]"
python scripts/build.py --deb                  # → dist/quire_<version>_<arch>.deb
sudo apt install ./dist/quire_*.deb
```

The package installs the self-contained app to `/opt/quire`, a `quire` command, and a menu
entry with an icon. Remove it with `sudo apt remove quire`. Your notes and timetable are
stored in your home folder and are left untouched.

**Linux from source (per-user, no root):**

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
push and uploads the `.deb` and `Quire.exe` as artifacts.

## Releasing a new version

Developer and publisher details (`DEVELOPER`, `APP_ID`, `HOMEPAGE`) live in
`quire/__init__.py`. The `.deb`, the AppStream metadata checks, the Windows `.exe` file properties
and the About dialog all read them from there.

1. Bump `__version__` in `quire/__init__.py`.
2. Add a `<release version="…" date="…">` entry at the top of
   `packaging/io.github.quezka.Quire.metainfo.xml`. The tests fail if you forget.
3. Commit, tag (`git tag v0.2.0`) and push.

`packaging/io.github.quezka.Quire.metainfo.xml` is what Ubuntu App Center and GNOME Software
read to show the app's developer, description and version history.

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
| `quire/application` | Use-case services (`TimetableService`, `PlannerService`, `TaskService`, `NoteService`, `SchoolSyncService`), **ports** (`Protocol`s) for repositories, the school register and credential storage, read-model DTOs, and a framework-free `ChangeBus` | domain |
| `quire/infrastructure` | `SqliteDatabase` (with schema migrations), SQLite repositories, the `ClassevivaRegister` HTTP adapter, the keyring credential store, the system clock and platform data paths | application, domain |
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
