# Quire

*A quire is a bundle of pages folded together, the old name for a notebook section.*

Quire is a native desktop app for **Linux and Windows** that puts your school timetable, a day
planner and your notes in one place. Built with Python and Qt 6 (PySide6). Your data stays on
your machine in a single SQLite file.

## Features

- **Today**: a timeline of today's classes and events with a live "now" line. Beside it are
  tasks due today, overdue work carried over from earlier days, a quick-add box and a
  free-form **day notes** journal.
- **Zoom**: Today and Week fit the whole day on screen by default. Zoom in or out with the
  − / + buttons, Ctrl+scroll or a touchpad pinch, and press Ctrl+0 to fit again.
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
  - **Topics** split a class's notes into chapters or units (e.g. Biology → *Cell biology*,
    *Genetics*). Type one in the tag box in the note's toolbar; topics you've already used in
    that class are suggested, and different capitalisation is merged into one spelling.
  - The **group** button next to the class filter shows notes under their class and topic.
    Click a heading to collapse it. Right-click a topic to rename it (a rename into an
    existing name merges the two) or to start a new note in it.
- **Work**: add your jobs, with an optional gross hourly rate and a tax & deductions
  percentage (presets for Italian occasional work and employee contributions). Give each
  job a **weekly schedule** so its regular shifts show up every week in Today and Week,
  right next to your classes.
  - Late shifts can run past midnight, e.g. 18:00–01:00.
  - Any shift can repeat every week, every work day, every day or on chosen days, with an
    optional end date.
  - Click a regular shift to skip it this week or change just this week's times.
  - The shift editor shows paid hours (minus your unpaid break) and gross and take-home pay. It warns
    you if a shift overlaps a class, an event or another shift.
  - The Work page lists upcoming shifts and totals hours, gross and take-home pay for this
    week and this month, per job. Take-home pay is an estimate: real withholding depends on
    your contract and yearly income.
  - Double-click an empty time in Today or Week to add an event or a shift there.
- **School (Classeviva)**: connect your Classeviva student account to pull in what teachers
  post:
  - homework and tests from the agenda and from Classeviva's homework feature ("Compiti").
    They land in Coursework and Today, and in the School page's **Homework & tests** list
    (overdue first, tick them off right there);
  - grades, with per-subject and overall averages;
  - lesson topics from the class register.

  Your subjects become courses automatically. A course you already made is matched when its
  name is the same as the subject's (ignoring capitals). If you named it differently (say
  "Maths" for *MATEMATICA*), open it in **Week → Courses** and pick its **Classeviva subject**.
  Its timetable stays as it is. Anything the sync had put in a separate "Matematica" course
  (homework, grades, lesson topics, notes) moves over, and the empty duplicate is removed.
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
| Ctrl+1 … Ctrl+6 | Today / Week / Coursework / Notes / School / Work |
| Ctrl+Shift+W | New work shift |
| Ctrl+R | Sync school register |
| Ctrl+N | New note |
| Ctrl+T | New task |
| Ctrl+Shift+E | New event |
| Ctrl+Shift+C | Courses & timetable |
| Ctrl+Q | Quit |
| Ctrl+D | Jump to today |
| Ctrl+F | Search notes |
| Ctrl+E | Toggle note preview |
| Ctrl+= / Ctrl+- / Ctrl+0 | Zoom in / out / fit the day (Today, Week) |

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

Every version is published as a GitHub release with the `.deb` and `.exe` attached. Versions
follow [semver](https://semver.org): patch for fixes, minor for new features, major for
breaking changes. Developer and publisher details (`DEVELOPER`, `APP_ID`, `HOMEPAGE`) live
next to `__version__` in `quire/__init__.py`, which is the single source for the package
version too.

1. Bump `__version__` in `quire/__init__.py`.
2. Add a `## [x.y.z] - date` section to `CHANGELOG.md`; it becomes the release notes.
3. Add a `<release version="…" date="…">` entry at the top of
   `packaging/io.github.quezka.Quire.metainfo.xml`.
4. Commit, then `git tag vX.Y.Z && git push && git push --tags`.

The tests fail if step 2 or 3 is missing. On the tag, CI checks that the tag matches
`__version__`, builds both packages and publishes the release.

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
| `quire/application` | Use-case services (`TimetableService`, `PlannerService`, `TaskService`, `NoteService`, `SchoolSyncService`, `WorkService`), **ports** (`Protocol`s) for repositories, the school register and credential storage, read-model DTOs, and a framework-free `ChangeBus` | domain |
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
