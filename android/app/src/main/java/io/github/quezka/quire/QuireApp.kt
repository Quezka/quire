package io.github.quezka.quire

import android.app.Application
import android.content.Context
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.data.SqliteRowStore
import io.github.quezka.quire.focus.FocusController
import io.github.quezka.quire.notify.Notifier
import io.github.quezka.quire.notify.ReminderManager
import io.github.quezka.quire.school.Classeviva
import io.github.quezka.quire.school.KeystoreBox
import io.github.quezka.quire.school.RegisterStore
import io.github.quezka.quire.school.SchoolReport
import io.github.quezka.quire.school.SchoolSync
import io.github.quezka.quire.school.SchoolWorker
import io.github.quezka.quire.sync.FirebaseCloud
import io.github.quezka.quire.sync.Settings
import io.github.quezka.quire.sync.SyncEngine
import io.github.quezka.quire.sync.SyncManager
import io.github.quezka.quire.update.Updater
import io.github.quezka.quire.widget.AgendaWidget
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/** Wires the app together (the phone's equivalent of the desktop's bootstrap.py). */
class QuireApp : Application() {
    lateinit var container: Container
        private set

    override fun onCreate() {
        super.onCreate()
        container = Container(this)
        container.start()
    }
}

class Container(
    private val context: Context,
    val records: Records = Records(SqliteRowStore(context)),
    val repository: Repository = Repository(records),
    val settings: Settings = PrefsSettings(context),
) {
    val engine = SyncEngine(records, FirebaseCloud(), settings)
    val sync = SyncManager(context, engine, repository)
    val notifier = Notifier(context)
    val reminders = ReminderManager(repository, settings, notifier)
    val focus = FocusController(repository, settings, notifier)
    val school = SchoolSync(Classeviva(), repository, RegisterStore(settings), settings, KeystoreBox())
    val updater = Updater(context)

    /** The register sync's state, for the School screen. */
    val schoolState = MutableStateFlow(SchoolState())
    private val schoolLock = Mutex()

    fun start() {
        notifier.createChannels()
        io.github.quezka.quire.ui.currencyCode = settings.get("currency") ?: "EUR"
        sync.start()
        SchoolWorker.schedule(context)
        repository.onChanged = { reminders.plan(); AgendaWidget.refresh(context) }
        reminders.plan()
        focus.tick(announce = false)
        focus.planAlarm()
    }

    /** Fetch from the register (call off the main thread) and apply it on the main thread.
     *  On a phone that syncs but hasn't yet, sync first so imports match the computer's. */
    suspend fun syncSchool(): SchoolReport = schoolLock.withLock {
        schoolState.value = schoolState.value.copy(running = true)
        try {
            val status = engine.status()
            if (status.setUp && status.lastSync == null) runCatching { engine.sync() }
            val snap = school.fetch()
            val report = withContext(Dispatchers.Main) { school.apply(snap) }
            notifier.school(report)
            schoolState.value = SchoolState(problem = report.problems.joinToString("\n").ifEmpty { null })
            report
        } catch (e: Exception) {
            schoolState.value = SchoolState(problem = e.message)
            throw e
        }
    }
}

data class SchoolState(val running: Boolean = false, val problem: String? = null)

/** Settings in the app's private preferences (only this app can read them). */
class PrefsSettings(context: Context) : Settings {
    private val prefs = context.getSharedPreferences("quire", Context.MODE_PRIVATE)
    override fun get(key: String): String? = prefs.getString(key, null)
    override fun set(key: String, value: String?) {
        prefs.edit().apply { if (value == null) remove(key) else putString(key, value) }.apply()
    }
}

val Context.container: Container get() = (applicationContext as QuireApp).container
