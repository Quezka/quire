package io.github.quezka.quire.school

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import io.github.quezka.quire.container
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/** Checks the register every couple of hours and notifies about new grades, homework,
 *  absences and notices. */
class SchoolWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val container = applicationContext.container
        if (!container.school.status().connected) return Result.success()
        return try {
            container.syncSchool()
            Result.success()
        } catch (e: RegisterAuthException) {
            Result.success() // needs the user; the School screen says why
        } catch (e: RegisterException) {
            Result.retry()
        }
    }

    companion object {
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<SchoolWorker>(2, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork("school", ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
