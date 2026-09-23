# Changelog

All notable changes to Quire. Versions follow [Semantic Versioning](https://semver.org):
patch for fixes, minor for new features, major for breaking changes (while below 1.0,
breaking changes bump the minor version).

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
