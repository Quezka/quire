package io.github.quezka.quire.sync

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import io.github.quezka.quire.container
import io.github.quezka.quire.data.Repository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

data class SyncUi(val status: SyncStatus, val running: Boolean)

/**
 * When to sync: when the app starts, shortly after a local change, when asked, and every
 * 15 minutes in the background (WorkManager, only with a network connection).
 */
class SyncManager(
    private val context: Context,
    private val engine: SyncEngine,
    private val repository: Repository,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Mutex()
    private var soon: Job? = null
    private val _state = MutableStateFlow(SyncUi(engine.status(), running = false))
    val state: StateFlow<SyncUi> = _state

    fun start() {
        repository.onLocalChange = {
            refreshState()
            soon?.cancel()
            soon = scope.launch { delay(AFTER_EDIT_MS); syncNow() }
        }
        schedule()
        scope.launch { syncNow() }
    }

    fun refreshState() {
        _state.value = SyncUi(engine.status(), _state.value.running)
    }

    fun syncNow() {
        if (!engine.status().setUp) return
        scope.launch {
            lock.withLock {
                _state.value = SyncUi(engine.status(), running = true)
                val result = runCatching { engine.sync() }
                _state.value = SyncUi(engine.status(), running = false)
                if ((result.getOrNull()?.received ?: 0) > 0) {
                    withContext(Dispatchers.Main) { repository.refreshed() }
                }
            }
        }
    }

    /** Connect on a worker thread; the result comes back on the main thread. */
    fun connect(config: CloudConfig, email: String, password: String, create: Boolean,
                takeCloudCopy: Boolean, done: (Throwable?) -> Unit) {
        scope.launch {
            val result = runCatching { engine.connect(config, email, password, create, takeCloudCopy) }
            withContext(Dispatchers.Main) {
                if (takeCloudCopy && result.isSuccess) repository.refreshed()
                refreshState()
                done(result.exceptionOrNull())
            }
            if (result.isSuccess) syncNow()
        }
    }

    fun disconnect() {
        engine.disconnect()
        refreshState()
    }

    private fun schedule() {
        val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(context)
            .enqueueUniquePeriodicWork("sync", ExistingPeriodicWorkPolicy.KEEP, request)
    }

    companion object {
        const val AFTER_EDIT_MS = 10_000L
    }
}

class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val container = applicationContext.container
        if (!container.engine.status().setUp) return Result.success()
        return try {
            container.engine.sync()
            withContext(Dispatchers.Main) { container.repository.refreshed() }
            container.sync.refreshState()
            Result.success()
        } catch (e: CloudAuthException) {
            Result.success() // needs the user; the status shows why
        } catch (e: SyncException) {
            Result.retry()
        }
    }
}
