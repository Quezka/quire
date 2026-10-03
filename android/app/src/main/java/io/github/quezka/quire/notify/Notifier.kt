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
        // A channel's sound can't change once created, so the chime came with new ids;
        // the old soundless channels are deleted in createChannels().
        const val REMINDERS = "reminders_chime"
        const val FOCUS = "focus_chime"
        const val SCHOOL = "school_chime"
        private val OLD_CHANNELS = listOf("reminders", "focus", "school")
        const val ACTION_REMIND = "io.github.quezka.quire.REMIND"
        const val ACTION_FOCUS = "io.github.quezka.quire.FOCUS"
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
        manager.createNotificationChannels(listOf(
            channel(REMINDERS, R.string.channel_reminders, NotificationManager.IMPORTANCE_HIGH),
            channel(FOCUS, R.string.channel_focus, NotificationManager.IMPORTANCE_HIGH),
            channel(SCHOOL, R.string.channel_school, NotificationManager.IMPORTANCE_DEFAULT),
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
        if (allowed()) NotificationManagerCompat.from(context).notify(id, builder.build())
    }

    fun reminder(r: Reminder, now: LocalDateTime) {
        val left = java.time.Duration.between(now, r.starts).toMinutes().toInt().coerceAtLeast(0)
        val kind = context.getString(when (r.item.kind) {
            ItemKind.CLASS -> R.string.kind_class
            ItemKind.EVENT -> R.string.kind_event
            ItemKind.SHIFT -> R.string.kind_shift
        })
        val `when` = if (left <= 0) context.getString(R.string.starting_now)
        else context.resources.getQuantityString(R.plurals.starts_in, left, left)
        val place = listOf(r.item.room).filter { it.isNotBlank() }
        post(r.key.hashCode(), NotificationCompat.Builder(context, REMINDERS)
            .setSmallIcon(R.drawable.ic_notification)
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
            .setSmallIcon(R.drawable.ic_notification).setContentTitle(title).setContentText(text)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setContentIntent(openApp(MainActivity.TAB_FOCUS)).setAutoCancel(true))
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
            .setSmallIcon(R.drawable.ic_notification)
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
            else -> container.reminders.fire()
        }
        container.reminders.plan()
        container.focus.planAlarm()
        // A start passed, or the clock or time zone changed.
        val pending = goAsync()
        AgendaWidget.scope.launch { try { AgendaWidget.refreshNow(context) } finally { pending.finish() } }
    }
}
