# Quire

*A quire is a bundle of pages folded together, the old name for a notebook section.*

Quire puts your school timetable, a day planner, your notes, your work shifts and your
Classeviva register in one place. It's a native desktop app for **Linux and Windows** (Python
and Qt 6 / PySide6), with a companion **Android** app (Kotlin and Jetpack Compose). Your data
stays on your devices; syncing between them is optional and goes through a Firebase project
you own.

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
  preview mode (Ctrl+E).
  - Markdown is styled as you type: headings grow, **bold** and *italic* show as such, and
    the marks fade into the background.
  - A formatting bar (bold, italic, heading, list, checklist, code, quote) with shortcuts.
  - Enter continues a list or checklist, and Enter on an empty item ends it. Tab and
    Shift+Tab indent. Click a checkbox (`- [ ]`) to tick it.
  - The note list shows the first words of each note and a word count.
  - **Topics** split a class's notes into chapters or units (e.g. Biology → *Cell biology*,
    *Genetics*). Type one in the tag box in the note's toolbar; topics you've already used in
    that class are suggested, and different capitalisation is merged into one spelling.
  - **Notebooks** group notes that aren't a class: Ideas, Trips, a project. Make one with the
    book button next to the filter (or **New notebook…** in a note's picker), give it a
    name and a colour, and file notes in it from the same picker you use for classes. A note
    is in a class *or* a notebook. Topics work inside notebooks too. Right-click a
    notebook's heading to add a note or to rename, recolour or delete it (its notes stay,
    filed nowhere). Notebooks sync between your devices, and the phone has them too.
  - The **group** button next to the filter shows notes under their class or notebook and
    topic. Click a heading to collapse it. Right-click a topic to rename it (a rename into an
    existing name merges the two) or to start a new note in it.
- **Work**: add your jobs, paid **by the hour** or a **fixed monthly pay** (with 12, 13 or
  14 payments and optional contract dates). Take-home pay follows the Italian rules for an
  employee (INPS, IRPEF with the work detrazione, surtax, tredicesima, TFR), or a flat
  percentage if you prefer; **Payslips** in the job editor shows it month by month. Give each
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
- **Focus**: a Pomodoro timer in the spirit of KDE's Francis. You get 25 minute focus
  sessions and 5 minute breaks, with a long break every 4 rounds (all adjustable).
  - Pick the task you're working on, and get a notification when each phase ends.
  - Pomodoros and focus time are counted for today and the week.
  - The countdown shows in the sidebar from any page.
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
- **Languages**: English and Русский (Russian). Change it in **More → Settings → Language**.
- A modern sidebar layout with light and dark themes. It follows your system by default; change
  it in **More → Settings**, which also sets your currency and backs up your data.

The School page has four sections:
- **Overview:** grades, homework and tests, lesson topics. Double-click a subject to see how its
  average moved (a small chart) and **what you need** on the next test, or the next few, to
  reach an average you pick.
- **Absences:** days absent, late entries and early exits, whether they're justified, and how
  many lesson hours you've missed against the **25% limit**. The year's hours are estimated
  from the school calendar and your timetable. Some schools record a late entry or early exit
  without its hour (Classeviva shows "ora -1"); double-click it to enter the hour yourself.
  Quire keeps it across syncs, and if the school fills it in later, theirs is used.
- **Noticeboard:** school circulars with their attachments; opening one tells the school
  you've read it, as the Classeviva app does. New notices trigger a desktop notification.
- **Books & documents:** the textbook list per subject (ISBN, price, to buy or owned), plus
  report cards and documents when the school publishes them.

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

### Sync between your devices

**More → Settings → Sync** keeps your timetable, tasks, notes, journal, work shifts and focus
log the same on all your computers and your phone. It goes through **your own free Firebase project**, so
your data sits in an account only you control.

- **Setup, once:** create a Firebase project and turn on Email/Password sign-in. Create a
  Firestore database, then paste the security rules from the setup dialog (**Copy security
  rules**). Add a Web app, and copy its *projectId* and *apiKey* into Quire. The setup
  dialog lists these steps with a link to the console.
- **On the next computer:** enter the same project and sign in with the same account. Tick
  **Replace this computer's data with the cloud copy** if it already has its own copy of
  things (for example the same timetable typed in twice), so nothing ends up doubled.
- **Local-first:** Quire works offline as before. It syncs at start-up, every 5 minutes, and
  about 15 seconds after you change something.
- **Conflicts:** when the same thing changed on two computers, the newer change wins.
- **Deletions:** deleting something on one computer deletes it everywhere.
- **Kept local:** grades, absences and lesson topics are never uploaded; each device gets
  them from Classeviva itself. Homework you tick off does sync.
- **Sign-in:** a sign-in token is kept in the system keyring; your password isn't stored.
- **Sign out** stops syncing that computer. Its data stays, and the cloud copy isn't deleted.

### Android app

Quire for Android (`android/`, Kotlin and Jetpack Compose) has what the desktop has:
- **Today:** swipe left and right between days. Classes, events and work shifts, what's due,
  and the day note. Tap something to edit it; + adds a task, an event or a shift.
- **Week:** swipe between weeks.
- **Tasks** and **Notes.** Notes have course, notebook and topic filters, Markdown styled as you type,
  a formatting bar and checklists. Swipe a note away to delete it (with undo), long-press to
  pin it. **Scan a page** turns a photo of a printed handout into a note, offline (Tesseract,
  Italian and English).
- **School:** Classeviva on the phone. Homework and tests become tasks, subjects become
  courses; grades, absences, lesson topics and the noticeboard stay on the phone. It checks
  for news every two hours. Tap an early exit with no hour to enter it.
- **Work** (hours and pay), **Focus** (the Pomodoro timer, which keeps running when the app
  is closed), **Courses** (the timetable).
- **Notifications:** reminders before events, classes and shifts, the end of each focus
  phase, and new grades, homework and absences. The app asks for permission on first launch.
- **Sync:** the same Firebase project and account as on your computers. The quickest way to
  set it up: on the computer, Settings → Sync → **Set up your phone…** shows a QR code, and
  the phone scans it. It can bring the Classeviva login along; the code goes screen to camera
  and is never uploaded.
- **Updates:** Settings → Updates downloads the new APK from GitHub and installs it.

It works offline and syncs when the app opens, about 10 seconds after a change, and every
15 minutes in the background. Install `Quire-<version>-android.apk` from the releases (Android 8
or later; allow installing from your browser or file manager when asked). Later versions
install over it and keep your data. The Classeviva password is encrypted with a key in the
phone's Android Keystore.

The phone stores records in the same format sync uses (`android/app/src/main/java/.../data`).
Tests read real desktop records (`android/app/src/test/resources/desktop_records.json`), so the
two apps can't drift apart silently. Build it with `cd android && ./gradlew assembleRelease`
and test it with `./gradlew testDebugUnitTest` (needs JDK 17 and the Android SDK; add
`SCREENSHOTS=1` to render the screens to `app/build/screenshots`).

### Updates

Quire updates itself from its GitHub releases. It checks about once a day (switch that off
in **More → Settings → Updates**), and **More → Check for updates…** checks right away. When
there's a new version, you see what's new and can update, skip that version, or wait.

- **Linux (.deb):** the new package is downloaded and installed through the system's password
  dialog, then Quire restarts.
- **Windows (installer):** the new setup runs silently. It closes Quire, upgrades it and
  starts it again.
- **Checks:** every download is checked against its size and the SHA-256 checksum GitHub
  publishes before anything is installed.
- **Other copies:** a copy that can't replace itself (running from source, the portable
  build) gets a link to the release page instead.

### Keyboard shortcuts

| Keys | Action |
| --- | --- |
| Ctrl+1 … Ctrl+7 | Today / Week / Coursework / Notes / School / Work / Focus |
| Ctrl+, | Settings (appearance, currency, backup) |
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
| Ctrl+B / Ctrl+I | Bold / italic (notes) |
| Ctrl+Shift+8 / Ctrl+Shift+L | Bulleted list / checklist (notes) |
| Ctrl+` | Inline code (notes) |
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

**Windows installer:**

```bash
pip install -e ".[build]"
python scripts/build.py --installer   # needs Inno Setup 6; output in dist/
```

This makes `Quire-<version>-windows-x64-setup.exe`, a setup wizard built with Inno Setup from
`packaging/quire.iss`. It installs per user by default (no admin), adds Start menu and
uninstall entries, and upgrades in place. `--onefile` still makes a single portable binary.

PyInstaller builds for the platform it runs on, so build the installer on Windows. The GitHub
Actions workflow in `.github/workflows/build.yml` builds the `.deb`, the setup `.exe` and the
Android APK on every push and uploads them as artifacts.

**Android:** download the APK from the releases, or build it as described under
[Android app](#android-app).

## Releasing a new version

Every version is published as a GitHub release with the `.deb`, the `.exe` and the `.apk`
attached. Versions
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
`__version__`, builds the packages and publishes the release. The Android app takes its
version from `__version__` too. The APK is signed with the release key stored in the repository secrets
`QUIRE_KEYSTORE_B64` and `QUIRE_KEYSTORE_PASSWORD`; every release must use that same key, or
phones can't update.

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
| `quire/infrastructure` | `SqliteDatabase` (with schema migrations), SQLite repositories, the `ClassevivaRegister` HTTP adapter, the `FirebaseCloud` adapter and `SqliteSyncStore` for sync, the keyring credential store, the system clock and platform data paths | application, domain |
| `quire/presentation` | PySide6 UI. It talks only to the `Services` facade and adapts `ChangeBus` into a Qt signal (`bridge.py`) | application, domain |
| `quire/bootstrap.py` | Composition root: builds repositories and injects them into services | everything |

Sync is a use case like the others. `SyncService` works through two ports:
- `SyncStore`, this device's changes, implemented by SQLite triggers that stamp every change
  and leave tombstones for deletions, so the repositories don't know sync exists;
- `CloudBackend`, the cloud, implemented by Firestore over REST.

Records travel with stable ids instead of local row numbers, and the newer change wins.

The rule is enforced by `tests/test_architecture.py`, which parses every module's imports.
For example, if you import `sqlite3` or `PySide6` into the domain, the test suite fails.

The Android app follows the same idea on a smaller scale: `domain/` holds pure Kotlin rules
that mirror the desktop's (agenda, work pay, focus timer, register, Markdown); `data/`,
`sync/`, `school/`, `notify/`, `ocr/` and `update/` are the adapters; `ui/` is Compose. It's
all wired in `QuireApp.kt`.

The domain and application layers never touch Qt or SQL, so they are tested directly
against an in-memory database with a fixed clock:

```bash
pip install pytest
pytest
```

## Translations

On-screen text goes through `quire/presentation/i18n.py`:

- Wrap text in `_("…")`. Put values in named placeholders:
  `_("Delete “{title}”?").format(title=…)`.
- Use `N_("…")` for text defined in a table and translated where it's shown.
- Use `C_("button", "Start")` when one English word needs different translations.
- Use `plural(n, "lesson")` for counts, and the name helpers (`weekday_name`, `month_of`, …)
  for dates; never use `strftime("%A")`.

Russian lives in `quire/presentation/locales/ru.py`. `tests/test_i18n.py` fails when a string,
error message or plural word has no Russian translation, or when a translation's placeholders
differ from the English.

## Adding a feature

1. Put the rules on the entity in `domain/` and unit-test them.
2. If you need new data access, add it to the port in `application/ports.py`, then implement
   it in `infrastructure/repositories.py`.
3. Expose the new behaviour as a use-case method on a service. Return a DTO if the UI needs a
   shaped view of the data.
4. Call that method from `presentation/`. UI code should never reach past the service.

## Privacy

Quire keeps your data in a SQLite file on your computer, and in the app's private storage
on your phone. It connects to other systems only for features you turn on, plus one check
you can switch off:

| Connects to | When | What is sent |
| --- | --- | --- |
| `web.spaggiari.eu` (Classeviva) | Only after you connect your school account | Your Classeviva login; Quire reads your register and marks notices you open as read |
| Your own Firebase project (`googleapis.com`) | Only after you set up sync | Your synced notes, tasks, timetable, journal, work shifts and focus log, into *your* project |
| `api.github.com`, `github.com` | About once a day to check for updates (switch off in Settings → Updates), and when you choose to update | Nothing personal: a request for the latest release, and the download |

There are no analytics, telemetry or ads. On a computer, passwords and sign-in tokens are
kept in your system's keyring, never in Quire's database; on the phone, they're encrypted with
a key in the Android Keystore. Scanning a page reads the text on the phone itself; the photo
isn't uploaded anywhere.

## Code signing

The Windows builds are not code-signed, so Windows SmartScreen may warn the first time you run
the installer: choose **More info → Run anyway**. Every build is made by GitHub Actions from
this repository's source at the tagged release commit (see `.github/workflows/build.yml`),
and the in-app updater checks each download against the SHA-256 checksum GitHub publishes.
The Android APK is signed with the project's own release key.

## Licence

Quire is free software: you can redistribute it and/or modify it under the terms of the
[GNU General Public License](LICENSE) as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version. It comes with no warranty.
