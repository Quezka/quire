# Changelog

All notable changes to Quire. Versions follow [Semantic Versioning](https://semver.org):
patch for fixes, minor for new features, major for breaking changes (while below 1.0,
breaking changes bump the minor version).

## [0.7.0] - 2026-09-24

### Added
- **Русский язык** (Russian). Choose it in **Settings → Language** (System / English /
  Русский). "System" picks Russian on Russian systems. It covers:
  - the whole interface, including day and month names in the right grammatical case
    ("23 сентября"), Russian plurals (1 урок, 2 урока, 5 уроков), and error messages;
  - Qt's own buttons and dialogs ("Сохранить", "Отмена");
  - Russian date pickers.
  Switching language offers a "Restart now" button.

### Changed
- All on-screen text goes through a translation layer, and a test fails if any of it lacks
  a Russian translation or a translation drops a `{placeholder}`.

## [0.6.0] - 2026-09-24

### Added
- **Focus timer** (Ctrl+7), a Pomodoro timer in the spirit of KDE's Francis.
  - A ring counts down focus sessions and breaks: 25 minutes of focus and 5 minute
    breaks, with a 15 minute long break after 4 rounds (all adjustable).
  - Start/pause, reset and skip; the next phase can start by itself.
  - Pick the task or homework you're working on.
  - You get a notification when a phase ends.
  - It counts completed pomodoros and focus time for today and the week.
  - While it runs, the countdown shows in the sidebar and the window title.
  - The timer measures against the clock, so it stays exact through sleep or a busy app.
- **Settings** (More → Settings…, Ctrl+,) for appearance, currency and your data (backup,
  data folder).
- **Currency choice**: Euro, Pound, US dollar, Swiss franc or Russian ruble, or follow the
  system. Pay used the system's currency before, which showed £ on English (UK) systems.

### Changed
- The Appearance submenu and the backup/data-folder entries moved from More into Settings.

## [0.5.0] - 2026-09-23

### Added
- **Classeviva homework**: Quire now also reads Classeviva's homework feature ("Compiti"),
  which is separate from the agenda. Before, homework set there never reached Quire.
  - If you've already marked a homework done on Classeviva, it arrives ticked off.
  - Homework that drops off Classeviva's current list is kept, not deleted.
- **Homework & tests** on the School page:
  - lists overdue work first, then today and the days ahead;
  - round checkboxes tick things off, in sync with Today and Coursework;
  - "Show done" brings back what you've finished recently;
  - double-click an item to edit it.

### Changed
- Agenda notes that read like homework ("compiti", "esercizi", "pag.", "studiare", …) are
  filed as homework instead of plain tasks.

## [0.4.0] - 2026-09-23

### Added
- **Zoomable calendars**: Today and Week zoom vertically. **Fit day** (on by default)
  shows the whole day without scrolling and keeps fitting as the window resizes. Zoom in
  and out with the − / + buttons, Ctrl+scroll, a touchpad pinch or Ctrl+= / Ctrl+-, and
  fit again with Ctrl+0. Each view remembers its zoom.
- **Redesigned School page**:
  - summary tiles for your average, next test, homework due this week and subjects below 6;
  - subject rows with your latest marks as coloured chips, a trend sparkline and the
    average; click a subject to see every grade;
  - a term switcher (e.g. Trimestre / Pentamestre) that filters grades and averages;
  - "Coming up" homework and tests;
  - lesson topics grouped by day (double-click one to open that lesson's class notes).

### Changed
- A late shift's after-midnight tail no longer stretches the timeline back to 00:00. It
  shows as a slim strip at the top of the next day.

## [0.3.1] - 2026-09-23

### Fixed
- Classeviva sync is resilient: homework, grades, lesson topics and subjects sync
  independently, so one failing part no longer stops the rest. A part that fails never
  wipes the data you already have, and the School page lists what couldn't be synced.
- If Classeviva's grades endpoint answers "wrong uri" (reported for some accounts in
  Lioydiano/Classeviva#31), Quire reads grades from the overview endpoint instead.

## [0.3.0] - 2026-09-23

### Added
- **Weekly work schedule**: give a job its regular shifts (day toggles M T W T F S S, start,
  end, unpaid break). They show up every week in Week and Today next to your classes and
  count towards hours and pay. Schedule changes apply from this week on, so past weeks
  keep the hours you actually worked.
- **Repeat a shift**: every week, every work day (Mon–Fri), every day or custom days, with
  an optional end date.
- Click a regular shift to **skip this week**, **change just this week** (e.g. a different
  time) or edit the weekly schedule.
- **Take-home pay**: set each job's tax and deductions (presets for Italian occasional work
  at 20% withholding and employee INPS contributions at 9.19%, or any percentage). Shifts,
  the Work page and weekly/monthly totals show gross and net pay.
- The Week screen's **Timetable** button opens both courses and jobs, and **+ Add** creates
  an event or a work shift. Today has **+ Add** too.

### Fixed
- Hourly pay couldn't be entered: typing into the "Not set" field did nothing. Pay is now
  a plain field that accepts `8.50` or `8,50`.
- Number boxes (unpaid break) ignored typing over their placeholder text and had no arrow
  buttons.
- Classeviva: syncing early in the school year failed, because Quire asked for dates before
  1 September, which Classeviva rejects (error 122). Date ranges now stay inside the school
  year, and the app identifies itself as a current Classeviva app version.

## [0.2.0] - 2026-09-23

### Added
- **Classeviva sync** (School page): homework and tests land in Coursework and Today, grades
  with per-subject and overall averages, recent lesson topics, and a "What's new" list.
  Syncs every 30 minutes and with Ctrl+R, and sends a desktop notification when a teacher
  posts something. The password is stored in the system keyring.
- **Link courses to Classeviva subjects** in the course editor, so your own course names
  work. Linking merges any course the sync created for that subject.
- **Note topics**: file notes under a topic within a class, and group the notes list by
  class and topic (collapsible headings, rename/merge topics, topic suggestions).
- **Work shifts**:
  - jobs with optional hourly pay;
  - shifts that can run past midnight, with unpaid breaks and weekly repeats;
  - clash warnings against classes and events;
  - a Work page with weekly and monthly hours and pay.
  Shifts appear in Today and Week.
- **New look**: sidebar navigation, card layout, and light and dark themes that follow the
  system (or More → Appearance).
- Packages list Quezka as developer and publisher (AppStream metadata, .deb maintainer,
  Windows file properties).

### Fixed
- Cancel/Escape in the task dialog raised an error.
- Saving a synced course in the editor dropped its Classeviva link.
- The week view could open scrolled to midnight when a late shift crossed into the next day.

### Changed
- Existing data is migrated automatically (database schema v5). Nothing is removed.

## [0.1.0] - 2026-09-23

### Added
- First release: day planner with timeline and day notes, weekly school timetable,
  coursework tracker, Markdown notes with search and pinning, backups.
- Linux `.deb` package and Windows `.exe`.
