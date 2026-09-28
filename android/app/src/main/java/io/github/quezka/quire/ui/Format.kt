package io.github.quezka.quire.ui

import android.content.Context
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.TaskKind
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

fun minutes(m: Int) = "%02d:%02d".format(m / 60 % 24, m % 60).let { if (m == 24 * 60) "24:00" else it }

fun span(start: Int, end: Int) = "${minutes(start)}–${minutes(end)}"

fun relativeDate(context: Context, day: LocalDate, today: LocalDate): String = when (day) {
    today -> context.getString(R.string.today)
    today.plusDays(1) -> context.getString(R.string.tomorrow)
    today.minusDays(1) -> context.getString(R.string.yesterday)
    else -> day.format(DateTimeFormatter.ofPattern(
        if (day.year == today.year) "EEE d MMM" else "d MMM yyyy", Locale.getDefault()))
}

/** "Wednesday, 23 September" (the year only when it isn't this one). */
fun longDate(day: LocalDate, today: LocalDate = LocalDate.now()): String =
    day.format(DateTimeFormatter.ofPattern(
        if (day.year == today.year) "EEEE, d MMMM" else "EEEE, d MMMM yyyy", Locale.getDefault()))
        .replaceFirstChar { it.titlecase(Locale.getDefault()) }

/** Mid-sentence: "was due yesterday", not "was due Yesterday". */
fun relativeDateInline(context: Context, day: LocalDate, today: LocalDate): String {
    val text = relativeDate(context, day, today)
    return if (day in today.minusDays(1)..today.plusDays(1)) text.lowercase(Locale.getDefault()) else text
}

fun kindLabel(kind: TaskKind) = when (kind) {
    TaskKind.TASK -> R.string.kind_task
    TaskKind.HOMEWORK -> R.string.kind_homework
    TaskKind.ASSIGNMENT -> R.string.kind_assignment
    TaskKind.EXAM -> R.string.kind_exam
    TaskKind.READING -> R.string.kind_reading
}

/** The engine speaks English (like the desktop's core); show it in the phone's language. */
fun syncMessage(context: Context, message: String?): String {
    val text = message.orEmpty()
    val known = mapOf(
        "Can't reach" to R.string.err_offline,
        "Wrong email or password" to R.string.err_wrong_login,
        "has expired" to R.string.err_expired,
        "already an account" to R.string.err_exists,
        "at least 6 characters" to R.string.err_weak_password,
        "project ID" to R.string.err_project,
        "Web API key" to R.string.err_api_key,
        "email address" to R.string.err_email,
        "Type a password" to R.string.err_password,
        "refused access" to R.string.err_access,
    )
    return known.entries.firstOrNull { text.contains(it.key) }?.let { context.getString(it.value) } ?: text
}
