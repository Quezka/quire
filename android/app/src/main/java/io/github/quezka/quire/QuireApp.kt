package io.github.quezka.quire

import android.app.Application
import android.content.Context
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.data.SqliteRowStore
import io.github.quezka.quire.sync.FirebaseCloud
import io.github.quezka.quire.sync.Settings
import io.github.quezka.quire.sync.SyncEngine
import io.github.quezka.quire.sync.SyncManager

/** Wires the app together (the phone's equivalent of the desktop's bootstrap.py). */
class QuireApp : Application() {
    lateinit var container: Container
        private set

    override fun onCreate() {
        super.onCreate()
        container = Container(this)
        container.sync.start()
    }
}

class Container(context: Context) {
    val records = Records(SqliteRowStore(context))
    val repository = Repository(records)
    val settings: Settings = PrefsSettings(context)
    val engine = SyncEngine(records, FirebaseCloud(), settings)
    val sync = SyncManager(context, engine, repository)
}

/** Sync settings in the app's private preferences (only this app can read them). */
class PrefsSettings(context: Context) : Settings {
    private val prefs = context.getSharedPreferences("quire", Context.MODE_PRIVATE)
    override fun get(key: String): String? = prefs.getString(key, null)
    override fun set(key: String, value: String?) {
        prefs.edit().apply { if (value == null) remove(key) else putString(key, value) }.apply()
    }
}

val Context.container: Container get() = (applicationContext as QuireApp).container
