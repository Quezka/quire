# Changelog

All notable changes to Quire. Versions follow [Semantic Versioning](https://semver.org):
patch for fixes, minor for new features, major for breaking changes (while below 1.0,
breaking changes bump the minor version).

## [0.45.1] - 2026-11-09

- Smoother scrolling and window moves: the app only asks GNOME's Blur my Shell to blur behind its windows while they're see-through (with see-through off, that blur was redone on every frame for nothing). The glass header over scrolling pages is cheaper to draw.

## [0.45.0] - 2026-11-09

The suite's new shared look (one design system for every app, `suite-rs/design/tokens.json`):

- **Neutral greys** instead of blue-tinted backgrounds, sidebars and borders; indigo stays as the one accent colour.
- **Bigger, clearer text** on one type scale shared with the phone apps: body text 16 px, nothing smaller than 13 px;
  titles and buttons follow the same sizes everywhere (the Interface size setting still scales it all).
- The same corner radii and spacing in every app.

## [0.44.0] - 2026-11-09

Real transparency and corners that line up (suite-kit 0.10).

- **See-through windows**: where the desktop can blur what's behind a window, the main window and dialogs let it show
  through, like Windows Aero or macOS sidebars; cards stay solid. On Windows it's the system's Acrylic. On GNOME it
  needs the Blur my Shell extension (the app adds itself to its list). Switch it in Settings, Look.
- **Corners line up**: the sidebar, cards and the Settings list share one radius and one gap, and what's inside them is
  rounded to match, so the curves run side by side. The Settings header floats over the cards, as wide as them.
- The glass look's description in Settings says what it really does now.
- Phone: the glass bars are much more see-through (a lighter tint over a stronger blur), so the list under them clearly shows.

## [0.43.0] - 2026-11-09

### Changed
- **Liquid glass done properly, the Apple way, on both apps.** Backgrounds are plain again and content stays solid; the colour wash is gone.
  - Computer: menus, drop-down lists and tooltips blur what's really under them, settings headers float over their cards and blur them as they scroll, and the sidebar floats as an inset panel. On Windows 11 the window shows the system's Mica behind the sidebar.
  - Phone: the top bar of Today, Week, Tasks, Notes and More, and the bottom bar, are glass: the content scrolls under them and shows through, blurred (Android 13 and newer; older phones get a see-through tint). Notes keeps its filters in the glass bar.

## [0.42.0] - 2026-11-08

### Added
- **Quick log on the main page, on both apps:** one tap for a glass of water, going to sleep / waking up, the next medicine taken, or an expense, with Undo. Right-click (computer) or long-press (phone) offers other amounts and the other medicines due.
- **Phone: swipe sideways to move between Today, Week, Tasks, Notes and More.** The day and the week now change with the arrows at the top.
- **Phone: a "now" line on Today**, with the time, between what has started and what hasn't, like the computer's. What's over is dimmed, and what's on now shows how far through it is.
- **Glass look:** frosted, see-through surfaces over a soft wash of colour, on top of Material 3, with brighter colours. Settings → Look turns it off; High contrast stays solid.

### Changed
- **Settings is redone in the new look:** sections on the left (Look, Money, Reminders, Sync, Startup, Your data), cards of rows with switches, nothing cut off on a small screen. Every other window (events, tasks, courses…) has its title on top and a filled Save button.

### Fixed
- **Phone notes: the cursor goes where you tap again,** and dragging its handle or sliding on the keyboard's space bar moves it. The editor placed it at the start of the run of text instead, and some keyboards closed the app.
- Phone notes: no empty band between the formatting bar and the keyboard.

## [0.41.0] - 2026-11-04

### Changed
- **The phone app has the same indigo and colours as the computer.** The home-screen widget keeps following the system's colours.

## [0.40.0] - 2026-11-04

### Changed
- **The icons are Material Symbols**, outlined, and filled for what is selected.
- **The home-screen widget is Material 3**: it takes the system's Material You colours on Android 12 and later (Quire's own before that) and follows light and dark, with rows on tonal cards, a tonal add button and Material icons.

## [0.39.0] - 2026-11-04

### Added
- **New look**: Material 3 and the Manrope typeface in the whole suite, on the computer and the phone. A flick on a trackpad keeps gliding on the computer; a mouse wheel works as before.
- **Sleep**: the chart keeps a place for every day, so a night you didn't log shows as a gap, and pressing a day opens it in the form. After you wake up, "Tonight" shows last night and rates it with one tap, and counts down to bedtime. The goal saves as soon as you change it. The phone also shows average quality and the comparison with the week before.
- **Water**: press a day on the chart to see it, add what you forgot or remove an entry. The chart shows the amounts and how many of the last 7 days were on goal. The phone gains any amount, undo, a chosen daily goal, the streak and the weekly average.

### Fixed
- **The formatting buttons stay lit for the format that is on.** On the phone they never lit up, and pressing Bold twice doubled the marks: pressing it again now takes the format off. The heading button lights up too, and on the computer the buttons follow a selection dragged backwards.

## [0.38.1] - 2026-11-04

### Fixed
- **Do Not Disturb now comes off when the event ends**, on the computer and the phone.
  - Computer: if switching on ran twice or was interrupted, Quire took its own silence for the way things were and restored that. It now keeps the original state, checks that switching off worked, and tries again until it does.
  - Phone: it gave up if the phone reported anything other than "alarms only" by then. It now goes back regardless, never takes a leftover silence for the original state, looks again two minutes after the end, every time you open the app, and every couple of hours.

## [0.38.0] - 2026-11-04

### Added
- **Medicines**, on the computer and the phone: what to take and when, ticking each dose as taken or skipped, how the week went, and a notification when a dose is due. Quire only remembers what you tell it: it isn't medical advice and it doesn't check doses.
- **Money**, on the computer and the phone: what came in and went out by month and category, with exact sums. On the computer also a monthly budget and CSV export.
- **Your agenda in the computer's calendar**: Settings → Calendar. On Linux, classes, events, shifts and due dates appear in GNOME Calendar and Evolution as a read-only calendar that follows Quire. On Windows the file is handed to your calendar app, which imports it as it is then. It goes one way: you keep editing in Quire.

### Changed
- **More Material You on the computer**: surfaces tinted by the accent colour, a pill for the current page, round buttons and softer corners. High contrast keeps its own stark look.

## [0.37.0] - 2026-11-04

### Added
- **All-day events**, on the computer and the phone: a switch in the event editor. They sit above the timeline instead of filling it, never remind you and never turn on Do Not Disturb.
- **The noticeboard on the phone can be read**: tapping a notice opens its whole text and its attachments. Once opened, the text stays on the phone, also offline.
- **Export several notes into one PDF**: pick them with Ctrl or Shift and right-click; each starts on a new page.
- **A new note right where you want it**: a + appears on a class, notebook or topic heading under the mouse. In School, right-click a lesson for a note on its topic.
- **Water**: any amount, not only the quick buttons; remove a single entry with a right-click; choose your own daily goal instead of the one from height and weight; days in a row and the week's average.
- Phone notes: arrow buttons in the formatting bar move the cursor, also from one line to the next, and so do the keyboard's cursor keys.

### Changed
- Formatting buttons in notes work as switches: they light up when the format is on where the cursor is, and pressing them again turns it off.
- Classes and notebooks in the notes list start closed. Searching looks inside them, and a note you open is shown.
- Long lesson topics take as many lines as they need instead of being cut.
- The phone widget can be made much smaller, and redraws for the size it really has.

### Fixed
- The Water page starts a new day at midnight even if Quire stays open.
- Changing the interface size and pressing Restart now works, and the new copy waits for the old one to close.
- A button's menu opens exactly under the button (kit 0.5.2).
- Scrolling no longer interrupts dragging the cursor handle in phone notes.

## [0.36.4] - 2026-10-27

Fixed: the compact text size now reaches labels, buttons, menus and lists too (the desktop theme was keeping them at the system's larger size), so the whole interface really is smaller.

## [0.36.3] - 2026-10-27

The interface is compact: smaller text (never above 9 pt), tighter spacing and smaller icons and panels, instead of the zoom the size setting used to apply. "Automatic" size is 100% again.

## [0.36.2] - 2026-10-26

The interface size set to Automatic is a compact 85% now (the shared toolkit's new standard; 80% and 90% are new choices). Larger sizes stay in Settings.

## [0.36.1] - 2026-10-26

- The interface size set to Automatic is the system's own size again (100%); the shared toolkit had made it 115%, which was too big. Larger sizes stay one choice away in Settings.

## [0.36.0] - 2026-10-26

- The look now comes from the suite's shared toolkit: darker text and firmer borders, larger captions, and a High contrast option in Settings. "Automatic" interface size is 115%.

## [0.35.1] - 2026-10-26

### Fixed
- The Sleep and Water pages scroll when the window is short, instead of making it taller than a small laptop screen.

## [0.35.0] - 2026-10-26

### Added
- **Water tracking** (desktop and phone). A daily goal from your height and weight, a ring for the day with one-tap
  glasses (and undo), the last seven days, and a nudge when you fall behind the pace. Glasses sync between devices.
- **Sleep, more useful.** One tap when you go to bed and one when you wake, instead of typing times. It also shows
  how steady your bedtimes are, nights in a row on goal, this week against last week, and (on the desktop) how much
  you focus after a full night against a short one. A reminder comes half an hour before the bedtime goal.
- **Collapse all note groups** with one button on the desktop Notes page (press again to open them all).
- **Phone widget:** tasks you tick off stay on the list struck through with a check until the day is over, and tapping
  the check undoes it.

### Fixed
- Phone: the cursor now stays in view while you type in a long note, and when a new line is added.
- Phone: pressing Enter or Done in a one-line box lets go of focus and the keyboard.
- Phone: ticking a task in the widget now redraws the widget straight away.
- Drop-down lists open directly under their box instead of over it.

## [0.34.0] - 2026-10-24

### Added
- **Milestones.** An event can now be a moment with no duration, such as "Wake up at 6:00". Add one from "+ Add →
  Milestone…" or by double-clicking an empty time. It shows as a marker on the timeline, and the Vesper clock counts
  down to it like any other event.
- **Routines.** A milestone can repeat on chosen weekdays ("Wake up" at 6:00, Monday to Friday): "+ Add → Routine…".
  Routines show on Today and Week, send reminders, sync between devices and reach the Vesper clock.
- **Sleep tracking.** A new Sleep page (desktop) and Sleep screen under More (phone): log when you fell asleep and
  woke up, rate the night, set a goal (hours and wake-up time) and see when to be in bed. The last two weeks show as
  bars with how many nights reached the goal. Nights sync between devices.
- **Do Not Disturb while things are on.** In Settings, Quire can silence notifications from the start to the end of
  each class, event or work shift, then put things back. On the phone it sets Do Not Disturb (alarms only) and needs
  "Do Not Disturb access"; on the desktop it works on GNOME (Ubuntu) while Quire is open. Milestones and routines
  never silence anything.
- **Phone:** milestones and routines can be added and edited, and routines show on Today, Week, the widget and the
  Vesper clock (as events).

### Fixed
- On the phone, the keyboard covered the day's note on Today; the page now lifts above it.
- On Windows, Quire could show two tray icons after the first notification; notifications now use the tray icon
  Quire already has.

## [0.33.0] - 2026-10-20

### Added
- **Vesper bedside clock.** The phone app now shares what is on today and tomorrow with the Vesper charging clock
  (github.com/Quezka/vesper), only after you allow it once in Vesper: the next class, event or shift, what starts
  tomorrow, how many tasks are due and the focus timer. Nothing leaves the phone, and grades are never shared.
- **Sync through your own Quire server** (desktop and phone) as an alternative to Firebase, with a splash screen while
  the desktop app starts.

## [0.32.2] - 2026-10-09

### Fixed
- On Windows, Quire could crash with "RuntimeError: Signal source has been deleted" when a notification appeared.

## [0.32.1] - 2026-10-08

### Fixed
- Clicking a desktop notification now opens Quire instead of just dismissing it.

## [0.32.0] - 2026-10-05

### Added
- Changing the week on Week (touchpad swipe, arrows, "This week") now slides smoothly, like Today does for days.

## [0.31.0] - 2026-10-05

### Added
- **Italian translation** of the whole desktop app and of the Android app, with the Language setting (More → Settings). Systems set to Italian now start in Italian by default.

## [0.30.0] - 2026-10-03

### Added
- **Smooth day changes on Today.** Swiping two fingers on the touchpad, the arrows, the Today button and the calendar now slide the old day out and the new one in, instead of jumping.

## [0.29.0] - 2026-10-03

### Added
- **Payslip-style pay for jobs** (desktop and phone). A job is now paid **by the hour** or a **fixed monthly pay** (for example 446.23 × 13 payments), optionally with contract start and end dates. The first and last month are prorated by days, the tredicesima (and quattordicesima) builds up month by month and is paid in December or with the last payslip.
- **Italian tax model.** Take-home pay now follows the rules for an employee: INPS contributions, IRPEF with the work detrazione (prorated by the days worked), regional and municipal surtax and the optional low-income bonus (cuneo fiscale). The year is worked out as a whole and spread over its months. The old flat percentage is still there, and existing jobs keep it.
- **Payslips** (Jobs, then Edit job, then Payslips): gross, contributions, IRPEF, surtax, bonus, net and the TFR set aside, month by month for any year.
- The Work summaries (week and month) include monthly jobs, even in weeks without shifts.

### Changed
- Settings of a job now sync more fields (pay mode, monthly pay, contract dates, tax model). Update both devices so an older app doesn't reset them.

## [0.28.0] - 2026-10-03

### Added
- **Phone: agenda home-screen widget** (Android). Shows the next 7 days of classes, events, shifts and tasks, with a + button for a new task and a circle to mark a task done. Refreshes on changes, syncs and reminders.

## [0.27.0] - 2026-10-02

### Added
- **Two-finger swipe on the touchpad:** swipe sideways on Today to change day and on Week to change week. It triggers sooner and ignores slight vertical drift.

## [0.26.0] - 2026-10-02

### Added
- Pressing Enter in a one-line box now finishes with it: the cursor stops blinking and the box lets go of the focus.

## [0.25.1] - 2026-10-02

### Fixed
- Fixed: opening the app put a second icon on the dock instead of using the pinned one (the screen-size check forgot the app's desktop name).

## [0.25.0] - 2026-10-02

### Added
- **Interface size.** Settings has a new "Interface size" choice (Automatic, 80%–130%). Automatic
  makes everything a little smaller on small screens such as a 1366x768 laptop. It applies
  after a restart.
- The window never opens bigger than the screen, and Settings (or any dialog taller than the
  screen) scrolls instead of running off the bottom.

## [0.24.0] - 2026-10-01

### Added
- **Edit a notebook from the notes list.** With a notebook chosen in the filter, a pencil
  button appears beside it: rename the notebook, recolour it, or delete it (its notes stay,
  filed nowhere). It used to be reachable only by right-clicking a heading in grouped view.

## [0.23.0] - 2026-09-30

### Added
- **Phone: notebooks.** The notes screen has a chip for each notebook next to your courses
  (with its topics under it), and a **New notebook** chip and menu entry. With a notebook
  chosen, the pencil next to its chip renames or recolours it, or deletes it (its notes
  stay, filed nowhere). In a note, the picker now offers courses, notebooks and "New
  notebook". New notes and scanned pages go into whatever the list is filtered to. As on
  the computer, a note is in a course or a notebook, and a course wins.

## [0.22.0] - 2026-09-30

### Added
- **Notebooks: groups of notes that aren't classes.** Make one (Ideas, Trips, a project) with
  the new book button next to the notes filter, or with **New notebook…** at the bottom of a
  note's class picker. Notebooks have a name and a colour, sit next to your classes in the
  filter and the picker, and get their own heading in the grouped list (classes first, then
  notebooks, then notes filed nowhere). Topics work inside notebooks too.
- Right-click a notebook's heading to add a note to it, or to rename, recolour or delete it.
  Deleting a notebook keeps its notes; they just aren't filed anywhere.
- Notebooks sync between your devices. The phone keeps them and the notes in them intact
  when you edit on it, but doesn't show them yet; a note you give a class on the phone
  leaves its notebook.

### Changed
- The heading for notes filed nowhere is now "Not filed" (it was "No class").

## [0.21.0] - 2026-09-30

### Changed
- **Phone: notes are edited formatted too**, like on the computer. The preview button is
  gone: headings, lists, checkboxes (tap to tick), quotes, code and pictures show as you
  write. The line you're typing in shows its Markdown marks faded, so you can still see
  and fix `**bold**` or a link; the other lines show just the formatting.
- Typing `# `, `- `, `1. `, `[ ] `, `> ` or ``` at the start of a line formats it; Enter
  continues a list (Enter on an empty item ends it); Backspace at the start of a line
  turns it back into text, then joins it to the line above.
- New buttons to nest list items and bring them back out. Tap a picture to select it and
  remove it. Scanned pages go where the cursor is.

## [0.20.0] - 2026-09-30

### Changed
- **Notes: you write straight into the formatted note.** There's no separate preview
  any more (Ctrl+E is gone): headings, bold, lists, checklists, quotes, code and pictures
  show as they are while you type. Markdown habits still work: `# ` makes a heading,
  `- ` a list, `1. ` a numbered list, `[ ] ` a checklist, `> ` a quote, ``` a code block,
  and `**bold**`, `*italic*`, `` `code` `` and `~~struck~~` format as you close them.
  Tab and Shift+Tab nest list items; click a checkbox to tick it; Ctrl+click opens a link.
- Notes are still saved as Markdown, line for line, so the phone and sync read them as
  before. Copying text out of a note gives its Markdown.

## [0.19.0] - 2026-09-30

### Added
- **Pictures in notes.** Paste a picture (a screenshot, or a diagram copied from
  [Ligature](https://github.com/Quezka/ligature)), drop a picture file onto a note, or use
  the new picture button. The note shows it in the preview (Ctrl+E), and hovering its line
  in the editor shows a thumbnail. Pictures sync to your other devices, and the phone
  shows them in a note's preview too. Big photos are scaled down to fit (up to 700 KB each).
- **Edit diagrams in Ligature.** Right-click a Ligature diagram in a note and choose
  *Edit in Ligature*. Save in Ligature and the note updates by itself. Ligature pictures
  keep the diagram inside them, so nothing is lost on the way.
- **Export a note as PDF**, pictures included (the new download button beside the preview).
  A4, ready to print or hand in.
- Right-click a picture to copy it or save it as a file.

## [0.18.2] - 2026-09-30

### Fixed
- Desktop: noticeboard notices written as text, with no document attached, opened empty.
  Opening a notice now shows its text (fetched from Classeviva, which also marks it read
  there, as its own app does); formatting some schools add is turned into plain text.

## [0.18.1] - 2026-09-29

### Fixed
- Desktop: quitting Quire in the middle of a focus session threw that session away. The
  minutes you'd focused now go into your focus time, the same as when you skip or reset.
  (On the phone the timer keeps running while the app is closed, so nothing is lost there.)

## [0.18.0] - 2026-09-29

### Changed
- **A focus session you end early still counts.** Skipping or resetting part-way through a
  focus session now adds the minutes you actually focused (pauses don't count) to your focus
  time for today and this week, and to the task or project you were on. It isn't counted as
  a pomodoro, since it wasn't finished. Less than a minute, or a skipped break, adds nothing.
  The desktop and the phone both do this, and sync it.

## [0.17.0] - 2026-09-29

### Added
- **Quire has its own notification sound**, a soft two-note chime, the same on the desktop and
  the phone. You can tell Quire's reminders, focus timer and school news apart from other
  apps.
  - Desktop: Settings → Reminders → Sound, with a *Play* button to hear it and a switch to
    turn it off. On GNOME and KDE the desktop plays it, so Do Not Disturb silences it too.
  - Phone: every Quire notification plays it. To change or mute it, go to Android's settings
    for Quire → Notifications. Because Android can't change a channel's sound after the fact,
    the channels were replaced, and any sound or mute setting you'd changed there is back to
    the default.

## [0.16.1] - 2026-09-29

### Fixed
- Finished tasks and homework showed an empty circle in Today's due list and the School
  page's homework list, even though they were saved as done, and clicking a finished one
  couldn't untick it. They're shown ticked and crossed out again.

## [0.16.0] - 2026-09-29

### Added
- **Quire for Android now does what the desktop does.**
  - **Today:** swipe left and right to change days. Tap a class, event or shift to edit it;
    the + button adds a task, an event or a work shift.
  - **Week:** a view of the whole week, swipeable by week.
  - **School:** connect Classeviva on the phone. Homework and tests become tasks and subjects
    become courses, matching the ones your computer imports. Grades (with "what do I need?"),
    absences and the 25% limit, lesson topics and the noticeboard stay on the phone. The
    password is encrypted with a key kept in the phone's secure hardware.
  - **Work:** hours and take-home pay for this week or month, upcoming shifts, jobs with a
    weekly schedule. Change a weekly shift just this week, or skip a week.
  - **Focus:** the Pomodoro timer. It keeps running while the app is closed, notifies you
    when a phase ends, and logs your sessions (they sync).
  - **Courses:** edit your timetable on the phone.
  - **Notifications:** reminders before events, classes and shifts (same settings as the
    desktop), the focus timer, and new grades, homework, absences and notices from
    Classeviva, checked every two hours.
  - **Updates:** Settings → Updates checks GitHub and installs the new version.
  - Smoother motion throughout: sliding pages, animated lists and numbers, a timer ring.
- **Set up the phone with a QR code.** On the computer, Settings → Sync → Set up your phone…
  shows a code; scan it in the phone app and it's signed in, with Classeviva too if you
  like. Nothing to type.
- **Notes, on both.**
  - Markdown is styled as you type: headings, **bold**, *italic*, code, quotes and ticked
    checklist items, with the marks faded.
  - A formatting bar (heading, bold, italic, lists, checklist, quote, code) and shortcuts
    (Ctrl+B, Ctrl+I, Ctrl+Shift+L…). Enter continues a list; an empty item ends it.
  - Click (or tap) a checkbox to tick it. The list shows the start of each note.
  - On the phone: course and topic filters, swipe to delete (with undo), long-press to pin.
- **Scan a page (phone):** photograph a printed handout, or pick a picture, and its text
  becomes a note or goes into the one you're writing. It works offline, in Italian and
  English.
- **Enter the hour of a late entry or early exit** when the school didn't record it (Classeviva
  then sends no hour, and even its website shows "ora -1"). Double-click it on the desktop's
  Absences page, or tap it on the phone. Your hour is kept across syncs, and the school's
  wins if it's added later.

## [0.15.0] - 2026-09-28

### Added
- **Quire for Android** (first version), attached to this release as
  `Quire-0.15.0-android.apk`.
  - **Today:** classes, events and work shifts, including overnight ones. Below them, what's
    overdue or due soon, a quick "add a task for this day", and the day note.
  - **Tasks:** grouped like the desktop (Overdue, Today, Next 7 days, …). Tick them off, or
    open one to edit its type, course, due date and details.
  - **Notes:** search, pinned first, and a full-screen editor with course, topic and pin.
  - **Sync:** the same Firebase project and account as your computers. It syncs when the app
    opens, about 10 seconds after a change, and every 15 minutes in the background. The newer
    change wins, as on the desktop.
  - It works offline, in English and Russian, in light and dark, with Quire's look and icon.
  - Classeviva, work pay, the focus timer and reminders are for later versions. Things
    synced from them (homework from Classeviva, your shifts) already show on the phone.

## [0.14.0] - 2026-09-28

### Added
- **Runs in the background.** Closing the window keeps Quire in the system tray, so
  reminders, sync and school updates carry on.
  - Click the tray icon to bring the window back.
  - Quit from the tray menu, More → Quit Quire, or Ctrl+Q.
  - Switch this off in Settings → Startup.
- **Start Quire when I log in** (Settings → Startup). Quire starts straight into the tray.
  Uninstalling on Windows removes the login entry.
- **Only one Quire at a time.** Opening Quire while it's already running brings up the
  running window instead of starting a second copy.

### Changed
- The Settings dialog is wider and shorter, in two columns, so everything fits without
  scrolling.

## [0.13.2] - 2026-09-28

### Changed
- **Quire is free software**, under the GNU General Public License, version 3 or later. The
  licence is in the repository, the packages and More → About Quire.
- The README now has a **Privacy** section listing every connection Quire makes. There are no
  analytics or telemetry.
- Windows: the app is built without UPX compression. Antivirus software often distrusts
  compressed executables, so this should make Avast and others less wary.
- Groundwork for code-signed Windows releases through SignPath.

## [0.13.1] - 2026-09-28

### Fixed
- **Day notes and notes from another computer show up right away.** They synced, but
  Today's day note and the note open on the Notes page only updated after switching day or
  note, or restarting.
  - Typing into that stale copy could then overwrite what was written on the other computer.
  - Now they refresh as soon as a sync brings a change. Anything you're in the middle of
    typing is kept and saved as the newer version.
- A note deleted on another computer while you were editing it here is saved again as a new
  note, instead of the edit failing.

## [0.13.0] - 2026-09-28

### Added
- **School → Absences.** Days absent, late entries and early exits, each marked justified or
  not.
  - A bar shows the lesson hours you've missed against the 25% limit that can mean
    repeating the year.
  - The year's hours are estimated from Classeviva's school calendar and your timetable.
- **School → Noticeboard.** Circulars and announcements, with a count of unread ones on the
  tab.
  - Open a notice to read its attachments (PDFs open in your viewer). Classeviva is told
    you've read it, as its own app does.
  - New notices trigger a desktop notification.
- **School → Books & documents.**
  - Your textbook list per subject: title, author, ISBN (double-click to copy), price, and
    whether to buy it. The header shows the total to buy.
  - Report cards and documents appear there too, when the school publishes them.
- **What do I need?** Double-click a subject on the School overview. Pick a target average
  and a number of tests, and see the mark you need (in Italian notation: 7½, 6+, 7-), or
  whether you're already safe.
- **Grade trend.** The same dialog charts each mark and how the subject's average moved,
  with the pass mark dashed.

## [0.12.0] - 2026-09-28

### Added
- **Update Quire from inside the app.** Quire checks GitHub for a new version about once a
  day, and on request with More → Check for updates….
  - You see what's new and choose **Update now**, **Later** or **Skip this version**.
  - On Linux the new .deb installs through the system's password dialog, then Quire
    restarts.
  - On Windows the new setup runs silently and starts Quire again.
  - Downloads are checked against GitHub's checksum before anything is installed.
  - Switch off the daily check in Settings → Updates.
  - This version still has to be installed by hand once; later versions arrive through the
    app.

- **Sync between your computers** (More → Settings → Sync), through your own free Firebase
  project: timetable, tasks, notes, journal, work shifts and focus log.
  - Grades stay on each computer.
  - 0.11.0, which introduced sync, was tagged but never published, so it arrives here. See
    its notes in CHANGELOG.md for details.

## [0.11.0] - 2026-09-28

### Added
- **Sync between your computers** (More → Settings → Sync). Your timetable, tasks, notes,
  journal, work shifts and focus log stay the same everywhere.
  - It runs through your own free Firebase project; the setup dialog walks you through
    creating it.
  - Quire still works offline. It syncs at start-up, every 5 minutes, and shortly after you
    change something.
  - When the same thing changed on two computers, the newer change wins. Deletions sync too.
  - Grades and lesson topics stay on each computer; homework you tick off syncs.
  - A second computer can take the cloud copy instead of merging, so nothing ends up
    twice.
  - The sign-in token is kept in the system keyring; your password isn't stored.

## [0.10.2] - 2026-09-27

### Changed
- **Windows: a real installer** instead of a portable `.exe`.
  - `Quire-…-windows-x64-setup.exe` installs Quire for your user, with no admin needed.
  - It adds a Start menu entry, and a desktop shortcut if you want one.
  - Uninstall it from Settings → Apps.
  - Running a newer setup upgrades Quire in place, keeping your notes and settings.
  - The installer is in English, Italian or Russian.
  - It also starts faster than the portable file did, since nothing is unpacked on each
    launch.

## [0.10.1] - 2026-09-24

### Changed
- **New app icon**: a gathering of pages stitched at the spine (that's what a quire is),
  with an amber bookmark ribbon.
  - It uses the app's own indigo, so the icon and the window match.
  - Redrawn to stay readable at taskbar sizes.

## [0.10.0] - 2026-09-24

### Added
- **Focus on anything, not just tasks.** Type into "Focusing on" on the Focus page, e.g. a
  side project, or pick one of your tasks as before.
  - Finished sessions are logged under that name.
  - Your recent projects are offered in the list again.
  - The Today card shows how long you spent on each task or project.

### Fixed
- Switching the language back to English left Qt's own number and date formats in
  Russian until restart.

## [0.9.0] - 2026-09-24

### Added
- **Reminders**: a desktop notification shortly before your next event or work shift
  starts, e.g. "Dentist in 10 min", with the time, room and first line of the details.
  - Set them in More → Settings → Reminders: off, when it starts, or 5 to 60 minutes
    before.
  - Choose what they're for: events and work shifts (on by default) and classes (off by
    default).
  - They fire while Quire is open. Each start is announced once, and something that
    started while the laptop was asleep isn't announced late.

### Changed
- **Internals: stricter Clean Architecture.** The interface no longer touches the core
  model directly.
  - Screens send plain request models to the use cases and get read-only records back.
  - The school service is split into sync and records.
  - The Focus timer is only reachable through its use cases.
  - Tests now fail if the interface imports the domain, or if a use case takes or
    returns a domain entity.
  - No visible change, except that saving can no longer silently drop fields the editor
    doesn't show.

## [0.8.0] - 2026-09-24

### Added
- **Task view**: double-clicking a task (Today, Coursework, School) opens it to check it,
  not to edit it.
  - It shows the title, chips for subject, type and due date (red when overdue), and the
    full details.
  - Tasks from Classeviva say so.
  - **Mark as done** (Space) or **Edit…** (E).
- **Today shows everything still to do**: overdue work, today's, and the next 14 days,
  grouped under Overdue / Today / Tomorrow / … with round checkboxes. Other days still
  show just that day.

### Changed
- **Redesigned task editor**: a large title, type and subject side by side, quick due
  dates (Today, Tomorrow, Next week, **Next class** for the chosen subject), a bigger
  details box, and a note on tasks that came from Classeviva.

### Fixed
- Saving a task from the editor crashed: Qt handed the task type back as plain text.
- Editing a homework imported from Classeviva dropped its link, so the next sync would
  have imported it again as a duplicate.
- "Back up data…" and right-clicking a note topic crashed since 0.7.0 (a variable named
  `_` hid the translation function). A test now forbids that.

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
