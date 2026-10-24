package io.github.quezka.quire.bedside

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import io.github.quezka.quire.container
import io.github.quezka.quire.domain.Bedside
import io.github.quezka.quire.domain.BedsideItem
import java.time.ZoneId

/**
 * Hands the bedside clock (Vesper, on the same phone) what it shows: `content://<authority>/feed`, one row, read
 * only. Times are epoch milliseconds, so the clock counts down on its own. It is guarded by [Contract.PERMISSION],
 * a runtime permission the user grants once. Nothing from the school register is ever included.
 */
class BedsideProvider : ContentProvider() {
    object Contract {
        const val AUTHORITY = "io.github.quezka.quire.bedside"
        const val PERMISSION = "io.github.quezka.quire.permission.READ_BEDSIDE"
        val FEED: Uri = Uri.parse("content://$AUTHORITY/feed")

        const val GENERATED_MS = "generated_ms"
        const val NEXT_TITLE = "next_title"
        const val NEXT_KIND = "next_kind"
        const val NEXT_START_MS = "next_start_ms"
        const val NEXT_END_MS = "next_end_ms"
        const val TOMORROW_TITLE = "tomorrow_title"
        const val TOMORROW_KIND = "tomorrow_kind"
        const val TOMORROW_START_MS = "tomorrow_start_ms"
        const val TASKS_TODAY = "tasks_today"
        const val TASKS_TOMORROW = "tasks_tomorrow"
        const val TASK_TITLE = "task_title"
        const val TASK_DUE_EPOCH_DAY = "task_due_epoch_day"
        const val FOCUS_PHASE = "focus_phase"
        const val FOCUS_ENDS_MS = "focus_ends_ms"
        const val FOCUS_LABEL = "focus_label"

        val COLUMNS = arrayOf(
            GENERATED_MS, NEXT_TITLE, NEXT_KIND, NEXT_START_MS, NEXT_END_MS,
            TOMORROW_TITLE, TOMORROW_KIND, TOMORROW_START_MS,
            TASKS_TODAY, TASKS_TOMORROW, TASK_TITLE, TASK_DUE_EPOCH_DAY,
            FOCUS_PHASE, FOCUS_ENDS_MS, FOCUS_LABEL,
        )
    }

    override fun onCreate() = true

    override fun query(uri: Uri, projection: Array<String>?, selection: String?, selectionArgs: Array<String>?, sortOrder: String?): Cursor? {
        if (uri.path != "/feed") return null
        val app = context?.applicationContext ?: return null
        val c = app.container
        val repo = c.repository
        val now = repo.now()
        val feed = Bedside.build(now, repo.courses(), repo.events(), repo.jobs(), repo.shifts(), repo.tasks(), repo.routines())
        val zone = ZoneId.systemDefault()
        fun ms(t: java.time.LocalDateTime) = t.atZone(zone).toInstant().toEpochMilli()
        fun BedsideItem?.kind() = this?.kind?.let { if (it == io.github.quezka.quire.domain.ItemKind.ROUTINE) "event" else it.name.lowercase() }

        // The focus timer counts only while it runs; a paused or idle timer shows nothing.
        val focus = c.focus.timer
        val endsAt = focus.state.endsAt
        val label = c.focus.taskUid?.let(repo::task)?.title ?: c.focus.project.ifEmpty { null }

        val cursor = MatrixCursor(Contract.COLUMNS, 1)
        cursor.addRow(arrayOf(
            ms(now), feed.next?.title, feed.next.kind(), feed.next?.let { ms(it.start) }, feed.next?.let { ms(it.end) },
            feed.tomorrowFirst?.title, feed.tomorrowFirst.kind(), feed.tomorrowFirst?.let { ms(it.start) },
            feed.tasksToday, feed.tasksTomorrow, feed.nextTask?.title, feed.nextTask?.due?.toEpochDay(),
            if (endsAt != null) focus.phase.code else null, endsAt?.toEpochMilli(), if (endsAt != null) label else null,
        ))
        return cursor
    }

    override fun getType(uri: Uri) = "vnd.android.cursor.item/vnd.${Contract.AUTHORITY}.feed"
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<String>?) = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<String>?) = 0
}
