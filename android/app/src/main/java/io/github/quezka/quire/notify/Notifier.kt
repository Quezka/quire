package io.github.quezka.quire.notify

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import io.github.quezka.quire.MainActivity
import io.github.quezka.quire.R
import io.github.quezka.quire.container
import io.github.quezka.quire.widget.AgendaWidget
import io.github.quezka.quire.domain.ItemKind
import io.github.quezka.quire.domain.Phase
import io.github.quezka.quire.school.SchoolReport
import io.github.quezka.quire.ui.minutes
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.time.ZoneId

/** Posts Quire's notifications and wakes the app for reminders and the focus timer. */
class Notifier(private val context: Context) {
    companion object {
        // one channel per kind, each with its own icon (2026-11-14): the user can silence one kind and keep the rest;
        // a channel's sound and importance can't change once created, so old ids are deleted in createChannels()
        const val REMINDERS = "quire_events"
        const val WATER = "quire_water"
        const val MEDICINE = "quire_medicine"
        const val SLEEP = "quire_sleep"
        const val FOCUS = "quire_focus"
        const val SCHOOL = "quire_school"
        const val DIGEST = "quire_digest"
        const val NUDGES = "quire_nudges"
        const val NOW = "quire_now"
        private val OLD_CHANNELS = listOf("reminders", "focus", "school", "reminders_chime", "focus_chime", "school_chime")
        const val ACTION_REMIND = "io.github.quezka.quire.REMIND"
        const val ACTION_FOCUS = "io.github.quezka.quire.FOCUS"
        const val ACTION_QUIET = "io.github.quezka.quire.QUIET"
        const val ACTION_QUIET_AGAIN = "io.github.quezka.quire.QUIET_AGAIN"
        const val ACTION_WATER = "io.github.quezka.quire.WATER"
        const val ACTION_MEDICINE = "io.github.quezka.quire.MEDICINE"
        const val ACTION_SLEEP = "io.github.quezka.quire.SLEEP"
        const val ACTION_DIGEST = "io.github.quezka.quire.DIGEST"
        const val ACTION_NOW = "io.github.quezka.quire.NOW"
        const val ACTION_NUDGE = "io.github.quezka.quire.NUDGE"
        const val ACTION_BATCH = "io.github.quezka.quire.BATCH"
        const val ACTION_FOCUS_ON = "io.github.quezka.quire.FOCUS_ON"
        private const val NOW_ID = 6
        private const val DIGEST_ID = 7
        private const val NUDGE_ID = 8
        private const val BATCH_ID = 9
        private const val SLEEP_ID = 5
        private const val WATER_ID = 4
        private const val MEDICINE_ID = 40  // up to MEDICINE_ID + 19: one per dose, so they don't replace each other
        private const val FOCUS_ID = 2
        private const val SCHOOL_ID = 3
    }

    /** Quire's chime (res/raw/chime.wav, the same sound as on the desktop). */
    private val chime: Uri get() = Uri.parse("android.resource://${context.packageName}/${R.raw.chime}")

    fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        val audio = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build()
        fun channel(id: String, name: Int, importance: Int) =
            NotificationChannel(id, context.getString(name), importance).apply { setSound(chime, audio) }
        OLD_CHANNELS.forEach(manager::deleteNotificationChannel)
        val high = NotificationManager.IMPORTANCE_HIGH
        manager.createNotificationChannels(listOf(
            channel(REMINDERS, R.string.channel_reminders, high),
            channel(WATER, R.string.channel_water, high),
            channel(MEDICINE, R.string.channel_medicine, high),
            channel(SLEEP, R.string.channel_sleep, high),
            channel(FOCUS, R.string.channel_focus, high),
            channel(NUDGES, R.string.channel_nudges, high),
            channel(DIGEST, R.string.channel_digest, NotificationManager.IMPORTANCE_DEFAULT),
            channel(SCHOOL, R.string.channel_school, NotificationManager.IMPORTANCE_DEFAULT),
            // the lock-screen glance: always there, never a sound
            NotificationChannel(NOW, context.getString(R.string.channel_now), NotificationManager.IMPORTANCE_LOW)
                .apply { setSound(null, null); setShowBadge(false); lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC },
        ))
    }

    fun allowed(): Boolean = NotificationManagerCompat.from(context).areNotificationsEnabled() &&
        (Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)

    private fun openApp(tab: Int = 0): PendingIntent = PendingIntent.getActivity(context, tab,
        Intent(context, MainActivity::class.java).putExtra("tab", tab)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    @Suppress("MissingPermission")
    private fun post(id: Int, builder: NotificationCompat.Builder) {
        // every quire notif: high priority, accent colour, shown in full on the lock screen
        builder.setPriority(NotificationCompat.PRIORITY_HIGH)
            .setColor(ContextCompat.getColor(context, R.color.notification_accent))
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
        if (allowed()) NotificationManagerCompat.from(context).notify(id, builder.build())
    }

    fun reminder(r: Reminder, now: LocalDateTime) {
        val left = java.time.Duration.between(now, r.starts).toMinutes().toInt().coerceAtLeast(0)
        val kind = context.getString(when (r.item.kind) {
            ItemKind.CLASS -> R.string.kind_class
            ItemKind.EVENT -> R.string.kind_event
            ItemKind.ROUTINE -> R.string.kind_routine
            ItemKind.SHIFT -> R.string.kind_shift
        })
        val `when` = if (left <= 0) context.getString(R.string.starting_now)
        else context.resources.getQuantityString(R.plurals.starts_in, left, left)
        val place = listOf(r.item.room).filter { it.isNotBlank() }
        post(r.key.hashCode(), NotificationCompat.Builder(context, REMINDERS)
            .setSmallIcon(R.drawable.ic_n_event)
            .setContentTitle(r.item.title)
            .setContentText((listOf("$kind · ${minutes(r.item.start)}", `when`) + place).joinToString(" · "))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setWhen(r.starts.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli())
            .setContentIntent(openApp(0)).setAutoCancel(true))
    }

    fun focusEnded(ended: Phase, next: Phase, continuing: Boolean) {
        val title = context.getString(if (ended == Phase.WORK) R.string.focus_done else R.string.break_over)
        val text = context.getString(when (next) {
            Phase.WORK -> if (continuing) R.string.next_focus_running else R.string.next_focus_ready
            Phase.SHORT_BREAK -> if (continuing) R.string.short_break_running else R.string.short_break_ready
            Phase.LONG_BREAK -> if (continuing) R.string.long_break_running else R.string.long_break_ready
        })
        post(FOCUS_ID, NotificationCompat.Builder(context, FOCUS)
            .setSmallIcon(R.drawable.ic_n_focus).setContentTitle(title).setContentText(text)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setContentIntent(openApp(MainActivity.TAB_FOCUS)).setAutoCancel(true))
    }

    fun focusBlockDone() {
        post(FOCUS_ID, NotificationCompat.Builder(context, FOCUS)
            .setSmallIcon(R.drawable.ic_n_focus).setContentTitle(context.getString(R.string.focus_block_done))
            .setContentText(context.getString(R.string.focus_block_done_text))
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setContentIntent(openApp(MainActivity.TAB_FOCUS)).setAutoCancel(true))
    }

    // ---- the assistant ----

    @Suppress("MissingPermission")
    fun nowNext(now: io.github.quezka.quire.domain.AgendaItem?, next: io.github.quezka.quire.domain.AgendaItem?,
                step: io.github.quezka.quire.domain.Task?, drunk: Int, goal: Int) {
        val title = when {
            now != null -> context.getString(R.string.glance_now, now.title, minutes(now.end))
            next != null -> context.getString(R.string.glance_next, next.title, minutes(next.start))
            step != null -> context.getString(R.string.glance_step, step.title)
            else -> context.getString(R.string.glance_free)
        }
        val lines = buildList {
            if (now != null && next != null) add(context.getString(R.string.glance_then, next.title, minutes(next.start)))
            if (step != null && (now != null || next != null)) add(context.getString(R.string.glance_step, step.title))
            add(context.getString(R.string.glance_water, drunk / 1000.0, goal / 1000.0))
        }
        val builder = NotificationCompat.Builder(context, NOW)
            .setSmallIcon(R.drawable.ic_n_now).setContentTitle(title).setContentText(lines.joinToString(" · "))
            .setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString("\n")))
            .setOngoing(true).setSilent(true).setShowWhen(false).setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW).setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setColor(ContextCompat.getColor(context, R.color.notification_accent))
            .setContentIntent(openApp(0))
        if (allowed()) NotificationManagerCompat.from(context).notify(NOW_ID, builder.build())
    }

    fun cancelNow() = NotificationManagerCompat.from(context).cancel(NOW_ID)

    fun digest(morning: Boolean, items: List<io.github.quezka.quire.domain.AgendaItem>,
               due: List<io.github.quezka.quire.domain.Task>, overdue: Int, ideas: List<String>,
               held: List<Pair<String, Int>>) {
        val lines = buildList {
            if (items.isEmpty()) add(context.getString(if (morning) R.string.digest_free_today else R.string.digest_free_tomorrow))
            for (i in items.sortedBy { it.start }.take(5)) add("${minutes(i.start)}  ${i.title}")
            for (t in due.take(4)) add(context.getString(R.string.digest_task, t.title))
            if (overdue > 0) add(context.resources.getQuantityString(R.plurals.digest_overdue, overdue, overdue))
            for (idea in ideas.take(5)) add(context.getString(R.string.digest_idea, idea))
            for ((app, count) in held.take(6)) add(context.getString(R.string.digest_held, app, count))
        }
        val style = NotificationCompat.InboxStyle()
        lines.forEach(style::addLine)
        post(DIGEST_ID, NotificationCompat.Builder(context, DIGEST)
            .setSmallIcon(R.drawable.ic_n_digest)
            .setContentTitle(context.getString(if (morning) R.string.digest_morning else R.string.digest_evening))
            .setContentText(lines.firstOrNull().orEmpty()).setStyle(style)
            .setContentIntent(openApp(0)).setAutoCancel(true))
    }

    fun nudge(task: io.github.quezka.quire.domain.Task) {
        val start = PendingIntent.getBroadcast(context, ACTION_FOCUS_ON.hashCode(),
            Intent(context, AlarmReceiver::class.java).setAction(ACTION_FOCUS_ON).putExtra("task", task.uid),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        post(NUDGE_ID, NotificationCompat.Builder(context, NUDGES)
            .setSmallIcon(R.drawable.ic_n_nudge)
            .setContentTitle(context.getString(R.string.nudge_title))
            .setContentText(context.getString(R.string.nudge_text, task.title))
            .addAction(0, context.getString(R.string.nudge_start), start)
            .setContentIntent(openApp(2)).setAutoCancel(true))
    }

    fun batch(lines: List<Pair<String, Int>>, latest: List<io.github.quezka.quire.domain.Assistant.Held>) {
        val style = NotificationCompat.InboxStyle()
        for ((app, count) in lines.take(6)) style.addLine(context.getString(R.string.digest_held, app, count))
        for (h in latest.reversed()) style.addLine("${h.app}: ${h.title}".take(80))
        post(BATCH_ID, NotificationCompat.Builder(context, DIGEST)
            .setSmallIcon(R.drawable.ic_n_digest)
            .setContentTitle(context.getString(R.string.batch_title, lines.sumOf { it.second }))
            .setContentText(lines.joinToString(", ") { it.first }).setStyle(style).setAutoCancel(true))
    }

    fun windDown(bedtime: Int) {
        post(SLEEP_ID, NotificationCompat.Builder(context, SLEEP)
            .setSmallIcon(R.drawable.ic_n_sleep).setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentTitle(context.getString(R.string.sleep_wind_down_title))
            .setContentText(context.getString(R.string.sleep_wind_down_text, minutes(bedtime)))
            .setContentIntent(openApp(0)).setAutoCancel(true))
    }

    fun water(drunk: Int, goal: Int) {
        post(WATER_ID, NotificationCompat.Builder(context, WATER)
            .setSmallIcon(R.drawable.ic_n_water).setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentTitle(context.getString(R.string.water_reminder_title))
            .setContentText(context.getString(R.string.water_reminder_text, drunk, goal))
            .setContentIntent(openApp(0)).setAutoCancel(true))
    }

    fun medicine(name: String, dose: String, planned: Int) {
        val what = if (dose.isBlank()) name else "$name · $dose"
        post(MEDICINE_ID + Math.floorMod((name + planned).hashCode(), 20), NotificationCompat.Builder(context, MEDICINE)
            .setSmallIcon(R.drawable.ic_n_medicine).setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentTitle(context.getString(R.string.medicine_reminder_title))
            .setContentText(context.getString(R.string.medicine_reminder_text, what, minutes(planned)))
            .setContentIntent(openApp(0)).setAutoCancel(true))
    }

    fun school(report: SchoolReport) {
        if (!report.hasNews) return
        val lines = buildList {
            for (g in report.newGrades.take(4)) add(context.getString(R.string.new_grade_line, g.subject, g.display))
            for (t in report.newTasks.take(4)) add(context.getString(R.string.new_task_line, t))
            for (n in report.newNotices.take(3)) add(context.getString(R.string.new_notice_line, n))
            if (report.newAbsences > 0) add(context.resources.getQuantityString(R.plurals.new_absences,
                report.newAbsences, report.newAbsences))
        }
        val style = NotificationCompat.InboxStyle()
        lines.forEach(style::addLine)
        post(SCHOOL_ID, NotificationCompat.Builder(context, SCHOOL)
            .setSmallIcon(R.drawable.ic_n_school)
            .setContentTitle(context.getString(R.string.news_from_school))
            .setContentText(lines.first()).setStyle(style)
            .setContentIntent(openApp(MainActivity.TAB_SCHOOL)).setAutoCancel(true))
    }

    // ---- alarms ----

    private val alarms get() = context.getSystemService(AlarmManager::class.java)

    private fun pending(action: String) = PendingIntent.getBroadcast(context, action.hashCode(),
        Intent(context, AlarmReceiver::class.java).setAction(action),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    /** Wake at [at] (exactly, when the phone allows it). Null cancels. */
    fun wakeAt(action: String, at: LocalDateTime?) {
        val intent = pending(action)
        if (at == null) { alarms.cancel(intent); return }
        val millis = at.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        val exact = Build.VERSION.SDK_INT < 31 || alarms.canScheduleExactAlarms()
        if (exact) alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, millis, intent)
        else alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, millis, intent)
    }
}

/** Alarms for reminders and the focus timer; also re-plans after a restart or clock change. */
class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val container = context.container
        when (intent.action) {
            Notifier.ACTION_FOCUS -> container.focus.tick()
            Notifier.ACTION_QUIET, Notifier.ACTION_QUIET_AGAIN -> Unit
            Notifier.ACTION_WATER -> container.water.check()
            Notifier.ACTION_MEDICINE -> container.medicines.check()
            Notifier.ACTION_SLEEP -> container.sleepNudge.check()
            Notifier.ACTION_DIGEST -> container.assistant.digest()
            Notifier.ACTION_NUDGE -> container.assistant.nudge()
            Notifier.ACTION_BATCH -> container.assistant.batch()
            Notifier.ACTION_NOW -> Unit
            Notifier.ACTION_FOCUS_ON -> {
                // the nudge's button: focus on that task now
                container.focus.focusOn(intent.getStringExtra("task"))
                if (!container.focus.timer.running) container.focus.toggle()
                androidx.core.app.NotificationManagerCompat.from(context).cancel(8)
            }
            else -> container.reminders.fire()
        }
        container.reminders.plan()
        container.quiet.update()
        container.water.plan()
        container.sleepNudge.plan()
        container.focus.planAlarm()
        container.assistant.plan()
        container.assistant.updateNow()
        // A start passed, or the clock or time zone changed.
        val pending = goAsync()
        AgendaWidget.scope.launch { try { AgendaWidget.refreshNow(context) } finally { pending.finish() } }
    }
}
