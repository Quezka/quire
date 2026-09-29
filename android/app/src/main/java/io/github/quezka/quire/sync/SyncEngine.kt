package io.github.quezka.quire.sync

import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.SyncRecord
import java.time.Instant

/** Small persistent settings (SharedPreferences in the app, a map in tests). */
interface Settings {
    fun get(key: String): String?
    fun set(key: String, value: String?)
}

class MemorySettings : Settings {
    private val map = mutableMapOf<String, String>()
    override fun get(key: String) = map[key]
    override fun set(key: String, value: String?) {
        if (value == null) map.remove(key) else map[key] = value
    }
}

data class SyncStatus(
    val setUp: Boolean,
    val email: String,
    val projectId: String,
    val lastSync: Instant?,
    val pending: Int,
    val problem: String,
)

data class SyncResult(val received: Int, val sent: Int)

/**
 * The same sync as the desktop's SyncService: pull what changed elsewhere, push what
 * changed here and is still newest, then keep the newer version of each record.
 */
class SyncEngine(
    private val records: Records,
    private val cloud: Cloud,
    private val settings: Settings,
    private val clock: () -> Instant = Instant::now,
) {
    private fun get(name: String) = settings.get("sync.$name").orEmpty()
    private fun set(name: String, value: String?) = settings.set("sync.$name", value)

    fun config(): CloudConfig? {
        val project = get("project")
        val key = get("api_key")
        return if (project.isNotEmpty() && key.isNotEmpty()) CloudConfig(project, key) else null
    }

    fun status() = SyncStatus(
        config() != null && get("refresh").isNotEmpty(), get("email"), get("project"),
        get("last_sync").takeIf { it.isNotEmpty() }?.let(Instant::parse),
        records.pending(), get("problem"),
    )

    companion object {
        private val PROJECT = Regex("^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]$")
        private val EMAIL = Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")

        /** Returns the problem to show, or null if the inputs look right. */
        fun check(projectId: String, apiKey: String, email: String, password: String): String? = when {
            !PROJECT.matches(projectId.trim()) ->
                "Copy the project ID from the Firebase console, e.g. quire-sync-1a2b3."
            apiKey.trim().length < 20 || ' ' in apiKey.trim() ->
                "Copy the Web API key from the Firebase console."
            !EMAIL.matches(email.trim()) -> "Type the email address for your sync account."
            password.isEmpty() -> "Type a password."
            else -> null
        }
    }

    /** Sign in (or create the account) and remember it. Network: call off the main thread. */
    fun connect(config: CloudConfig, email: String, password: String, create: Boolean,
                takeCloudCopy: Boolean) {
        val session = if (create) cloud.signUp(config, email.trim(), password)
        else cloud.signIn(config, email.trim(), password)
        if (takeCloudCopy) records.clear()
        set("project", config.projectId); set("api_key", config.apiKey)
        set("email", session.email); set("refresh", session.refreshToken)
        set("cursor", null); set("problem", null)
    }

    /** Connect with a link from the computer (its QR code): no password needed, the
     *  computer's sign-in is checked and reused, and this phone takes the cloud copy.
     *  Network: call off the main thread. */
    fun connectWithLink(link: DeviceLink) {
        val config = CloudConfig(link.projectId, link.apiKey)
        val session = cloud.refresh(config, link.refreshToken)
        records.clear()
        set("project", config.projectId); set("api_key", config.apiKey)
        set("email", link.email.ifEmpty { session.email }); set("refresh", session.refreshToken)
        set("cursor", null); set("problem", null)
    }

    fun disconnect() {
        for (name in listOf("project", "api_key", "email", "refresh", "cursor", "last_sync", "problem")) {
            set(name, null)
        }
    }

    /** One full sync. Network and storage: call off the main thread. */
    fun sync(): SyncResult {
        val config = config() ?: throw SyncException("Set up sync first.")
        val refresh = get("refresh").ifEmpty { throw SyncException("Set up sync first.") }
        try {
            val session = cloud.refresh(config, refresh)
            val outgoing = records.outgoing()
            val (incoming, cursor) = cloud.pull(config, session, get("cursor").ifEmpty { null })
            val newest = mutableMapOf<Pair<String, String>, String>()
            for (r in incoming) if (r.modified > (newest[r.key] ?: "")) newest[r.key] = r.modified
            val sent: List<SyncRecord> = outgoing.filter { it.modified >= (newest[it.key] ?: "") }
            if (sent.isNotEmpty()) cloud.push(config, session, sent)
            val taken = records.apply(incoming)
            records.markSent(sent)
            set("cursor", cursor)
            set("last_sync", clock().toString())
            set("problem", null)
            if (session.refreshToken != refresh) set("refresh", session.refreshToken)
            return SyncResult(taken.size, sent.size)
        } catch (e: SyncException) {
            set("problem", e.message)
            if (e is CloudAuthException) set("refresh", null) // ask to set up again
            throw e
        }
    }
}
