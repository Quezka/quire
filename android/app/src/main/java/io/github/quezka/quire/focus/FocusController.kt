package io.github.quezka.quire.focus

import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.FocusSession
import io.github.quezka.quire.domain.FocusSettings
import io.github.quezka.quire.domain.Phase
import io.github.quezka.quire.domain.PomodoroTimer
import io.github.quezka.quire.domain.TimerState
import io.github.quezka.quire.notify.Notifier
import io.github.quezka.quire.sync.Settings
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId

/**
 * The one focus timer. Its state is saved on every change, and an alarm is set for the
 * end of the running phase, so it keeps time (and notifies) while the app is closed.
 * Focus sessions are logged and synced, like on the desktop; one skipped or reset part-way
 * is logged as unfinished, so its minutes still count.
 */
class FocusController(
    private val repo: Repository,
    private val settings: Settings,
    private val notifier: Notifier?,
    private val clock: () -> Instant = Instant::now,
) {
    val timer = PomodoroTimer(loadSettings(), loadState())
    private val _changes = MutableStateFlow(0)
    val changes: StateFlow<Int> = _changes

    private fun loadSettings(): FocusSettings {
        val d = FocusSettings()
        fun n(name: String, default: Int) = settings.get("focus.$name")?.toIntOrNull() ?: default
        return FocusSettings(n("work", d.workMinutes), n("short_break", d.shortBreakMinutes),
            n("long_break", d.longBreakMinutes), n("rounds", d.rounds),
            settings.get("focus.auto_continue")?.let { it == "1" } ?: d.autoContinue)
    }

    private fun loadState() = TimerState(
        Phase.of(settings.get("focus.state.phase")),
        settings.get("focus.state.completed")?.toIntOrNull() ?: 0,
        settings.get("focus.state.remaining")?.toLongOrNull(),
        settings.get("focus.state.ends")?.let { runCatching { Instant.parse(it) }.getOrNull() },
        settings.get("focus.state.started")?.let { runCatching { Instant.parse(it) }.getOrNull() },
        settings.get("focus.state.length")?.toLongOrNull(),
        settings.get("focus.state.block_started")?.let { runCatching { Instant.parse(it) }.getOrNull() },
        settings.get("focus.state.block_ends")?.let { runCatching { Instant.parse(it) }.getOrNull() },
    )

    private fun saveState() {
        val s = timer.state
        settings.set("focus.state.phase", s.phase.code)
        settings.set("focus.state.completed", s.completed.toString())
        settings.set("focus.state.remaining", s.remainingMs?.toString())
        settings.set("focus.state.ends", s.endsAt?.toString())
        settings.set("focus.state.started", s.startedAt?.toString())
        settings.set("focus.state.length", s.lengthMs?.toString())
        settings.set("focus.state.block_started", s.blockStarted?.toString())
        settings.set("focus.state.block_ends", s.blockEnds?.toString())
        _changes.value += 1
        planAlarm()
    }

    fun planAlarm() {
        notifier?.wakeAt(Notifier.ACTION_FOCUS, timer.state.endsAt?.let { LocalDateTime.ofInstant(it, ZoneId.systemDefault()) })
    }

    fun now(): Instant = clock()

    fun toggle() { tick(); timer.toggle(clock()); saveState() }
    fun skip() { tick(); logCutShort(); timer.skip(clock()); saveState() }
    fun reset() { tick(); logCutShort(); endBlock(clock()); timer.reset(); saveState() }

    /** Focus for a set time (2 hours, say): rounds and breaks run by themselves; at the end it goes into the week. */
    fun startBlock(totalMinutes: Int) {
        tick(); logCutShort(); endBlock(clock())
        timer.startBlock(clock(), totalMinutes)
        saveState()
    }

    private fun endBlock(until: Instant) {
        val started = timer.state.blockStarted ?: return
        addBlockEvent(started, until)
    }

    private fun addBlockEvent(started: Instant, end: Instant) {
        val zone = ZoneId.systemDefault()
        val from = LocalDateTime.ofInstant(started, zone)
        val to = LocalDateTime.ofInstant(end, zone)
        if (java.time.Duration.between(from, to).toMinutes() < 1) return
        val first = from.hour * 60 + from.minute
        val last = if (to.toLocalDate() == from.toLocalDate()) to.hour * 60 + to.minute else 24 * 60
        if (last <= first) return
        val what = taskUid?.let(repo::task)?.title ?: project
        repo.saveEvent(io.github.quezka.quire.domain.Event(Codec.newUid(), from.toLocalDate(), first, last,
            if (what.isBlank()) "Focus" else "Focus: $what", "Quire focus block", BLOCK_COLOR))
    }

    companion object {
        const val BLOCK_COLOR = "#4f46e5"
    }

    /** A focus session ended early still counts towards your focus time. */
    private fun logCutShort() {
        timer.cutShort(clock())?.let { log(it.started, it.minutes, complete = false) }
    }

    private fun log(started: Instant, minutes: Int, complete: Boolean) {
        val task = taskUid?.let(repo::task)
        repo.logFocus(FocusSession(Codec.newUid(), LocalDateTime.ofInstant(started, ZoneId.systemDefault()),
            minutes, task?.uid, task?.title ?: project, complete))
    }

    fun saveSettings(new: FocusSettings) {
        if (!new.valid()) return
        settings.set("focus.work", new.workMinutes.toString())
        settings.set("focus.short_break", new.shortBreakMinutes.toString())
        settings.set("focus.long_break", new.longBreakMinutes.toString())
        settings.set("focus.rounds", new.rounds.toString())
        settings.set("focus.auto_continue", if (new.autoContinue) "1" else "0")
        timer.applySettings(new)
        saveState()
    }

    // ---- what you're focusing on: a task, or a project that isn't one ----

    val taskUid get() = settings.get("focus.task")?.takeIf { uid -> repo.task(uid)?.done == false }
    val project get() = settings.get("focus.project").orEmpty()

    fun focusOn(taskUid: String?, project: String = "") {
        settings.set("focus.task", taskUid)
        settings.set("focus.project", if (taskUid == null) project.trim().ifEmpty { null } else null)
        _changes.value += 1
    }

    /** Advance the timer; log finished focus sessions and say what ended. After a long
     *  time away several phases may have passed: all are processed, the last announced. */
    fun tick(announce: Boolean = true) {
        var last: io.github.quezka.quire.domain.PhaseEnded? = null
        var blockStarted = timer.state.blockStarted
        while (true) {
            val event = timer.tick(clock()) ?: break
            last = event
            if (event.phase == Phase.WORK) log(event.started, event.minutes, complete = true)
            if (event.blockDone && blockStarted != null) {
                addBlockEvent(blockStarted, event.started.plusSeconds(event.minutes * 60L))
                blockStarted = null
            }
        }
        if (last != null) {
            saveState()
            if (announce) { if (last.blockDone) notifier?.focusBlockDone() else notifier?.focusEnded(last.phase, last.next, timer.running) }
        }
    }
}
