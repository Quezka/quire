package io.github.quezka.quire.update

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import io.github.quezka.quire.BuildConfig
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

data class Release(val version: String, val apkUrl: String, val size: Long, val notes: String)

class UpdateException(message: String) : Exception(message)

/** Versions like "0.16.0", compared number by number. */
fun newer(candidate: String, current: String): Boolean {
    fun parts(v: String) = v.trimStart('v').split(".").map { it.takeWhile(Char::isDigit).toIntOrNull() ?: 0 }
    val a = parts(candidate); val b = parts(current)
    for (i in 0 until maxOf(a.size, b.size)) {
        val x = a.getOrElse(i) { 0 }; val y = b.getOrElse(i) { 0 }
        if (x != y) return x > y
    }
    return false
}

/** Finds the phone's APK in the newest GitHub release. */
fun parseRelease(json: String): Release? {
    val o = Json.parseToJsonElement(json).jsonObject
    val version = (o["tag_name"] as? JsonPrimitive)?.content?.trimStart('v') ?: return null
    val asset = (o["assets"] as? JsonArray)?.mapNotNull { it as? JsonObject }?.firstOrNull {
        (it["name"] as? JsonPrimitive)?.content == "Quire-$version-android.apk"
    } ?: return null
    return Release(version, (asset["browser_download_url"] as JsonPrimitive).content,
        (asset["size"] as? JsonPrimitive)?.content?.toLongOrNull() ?: 0,
        (o["body"] as? JsonPrimitive)?.content.orEmpty())
}

/**
 * Updates from the project's GitHub releases, like the desktop (infrastructure/updates.py):
 * the APK `Quire-<version>-android.apk` is downloaded and handed to Android's installer,
 * which asks before installing. It's signed with the same key, so data is kept.
 */
class Updater(private val context: Context) {
    companion object {
        const val FEED = "https://api.github.com/repos/Quezka/quire/releases/latest"
    }

    /** The newer release, or null when this is the latest. Network. */
    fun check(): Release? {
        val text = try {
            val c = URL(FEED).openConnection() as HttpURLConnection
            c.setRequestProperty("Accept", "application/vnd.github+json")
            c.connectTimeout = 15_000; c.readTimeout = 20_000
            try {
                if (c.responseCode != 200) throw UpdateException("GitHub answered with an error (${c.responseCode}).")
                c.inputStream.bufferedReader().use { it.readText() }
            } finally { c.disconnect() }
        } catch (e: IOException) {
            throw UpdateException("Couldn't reach GitHub. Check your internet connection.")
        }
        val release = parseRelease(text) ?: return null
        return release.takeIf { newer(it.version, BuildConfig.VERSION_NAME) }
    }

    /** Download and start installing; [progress] gets 0..1. Network. */
    fun install(release: Release, progress: (Float) -> Unit) {
        val installer = context.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(context.packageName)
        val id = installer.createSession(params)
        installer.openSession(id).use { session ->
            try {
                val c = URL(release.apkUrl).openConnection() as HttpURLConnection
                c.connectTimeout = 15_000; c.readTimeout = 60_000
                val total = c.contentLengthLong.takeIf { it > 0 } ?: release.size
                c.inputStream.use { input ->
                    session.openWrite("quire.apk", 0, total.takeIf { it > 0 } ?: -1).use { out ->
                        val buffer = ByteArray(64 * 1024)
                        var done = 0L
                        while (true) {
                            val n = input.read(buffer)
                            if (n < 0) break
                            out.write(buffer, 0, n)
                            done += n
                            if (total > 0) progress(done.toFloat() / total)
                        }
                        session.fsync(out)
                    }
                }
                c.disconnect()
            } catch (e: IOException) {
                session.abandon()
                throw UpdateException("The download stopped. Try again.")
            }
            val intent = PendingIntent.getBroadcast(context, id,
                Intent(context, InstallReceiver::class.java),
                (if (android.os.Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0) or
                    PendingIntent.FLAG_UPDATE_CURRENT)
            session.commit(intent.intentSender)
        }
    }
}

/** Android asks the user to confirm the install; show that screen. */
class InstallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -1) == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            @Suppress("DEPRECATION")
            val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
            context.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
}
