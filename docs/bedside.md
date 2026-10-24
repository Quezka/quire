# Bedside provider (phone app)

The Android app exposes a read-only `ContentProvider` so that one other app on the same phone, the Vesper bedside clock
(`github.com/Quezka/vesper`), can show your schedule. Nothing goes through the cloud.

- URI: `content://io.github.quezka.quire.bedside/feed`, one row.
- Guarded by the runtime permission `io.github.quezka.quire.permission.READ_BEDSIDE` (protection level `dangerous`, defined by
  Quire's manifest). The user grants it once, from Vesper. A different signing key does not matter for it.
- Times are epoch milliseconds, so the clock can count down on its own. Nothing from the school register (grades, absences)
  is ever included.

| Column | Meaning |
| --- | --- |
| `generated_ms` | when the row was made |
| `next_title`, `next_kind` (`class`/`event`/`shift`), `next_start_ms`, `next_end_ms` | what is on now or comes next today (null if the day is over) |
| `tomorrow_title`, `tomorrow_kind`, `tomorrow_start_ms` | the first thing that starts tomorrow (the tail of tonight's shift does not count) |
| `tasks_today`, `tasks_tomorrow` | open tasks due today (overdue included) and tomorrow |
| `task_title`, `task_due_epoch_day` | the most urgent of those (exams first) |
| `focus_phase` (`work`/`short_break`/`long_break`), `focus_ends_ms`, `focus_label` | the focus timer while it runs, else null |

Routines (repeating milestones) reach the clock as `event`s, so the contract has no new kind.

The rules are `domain/Bedside.kt` (pure, tested by `BedsideTest`); the provider is `bedside/BedsideProvider.kt`.
Vesper mirrors the contract in its `domain/QuireFeed.kt` and `data/QuireLink.kt`: keep both sides in step.
