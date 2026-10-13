package io.github.quezka.quire.sync

import io.github.quezka.quire.data.SyncRecord
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import java.io.IOException
import java.net.URLEncoder

/**
 * The self-hosted Quire sync server (quire-server), as the desktop's QuireServerCloud:
 * accounts and records over its small JSON API (docs/PROTOCOL.md in that repo).
 *
 * `CloudConfig.projectId` carries the server's base URL (for example
 * https://sync.quezka.uk); `apiKey` is unused. Records keep the shape they always had, and
 * pulling follows an opaque cursor the server hands out, so device clocks never matter.
 */
class QuireServerCloud(private val http: Http = urlConnectionHttp) : Cloud {

    companion object {
        const val BATCH = 400 // records per push call (the server accepts up to 1000)
        const val BATCH_BYTES = 8_000_000 // and 16 MB per request: pictures in notes are big
        private val EXPIRED = setOf("invalid_refresh_token", "user_not_found", "invalid_token", "missing_token")
        private const val SIGN_IN_EXPIRED = "Your sign-in has expired: set up sync again."
        private const val UNREADABLE = "The sync server sent an answer Quire doesn't understand."

        /** The server's address from the settings; https:// is assumed when none is typed. */
        fun baseUrl(config: CloudConfig): String {
            val url = config.projectId.trim().trimEnd('/')
            return if ("://" in url) url else "https://$url"
        }

        fun toJson(r: SyncRecord): JsonObject = buildJsonObject {
            put("kind", r.kind); put("uid", r.uid); put("modified", r.modified)
            put("deleted", r.deleted)
            put("data", if (r.deleted) JsonNull else (r.data ?: JsonNull))
        }

        fun fromJson(raw: JsonElement): SyncRecord? = runCatching {
            val o = raw as JsonObject
            fun s(key: String) = (o[key] as JsonPrimitive).also { require(it.isString) }.content
            val deleted = (o["deleted"] as? JsonPrimitive)?.booleanOrNull ?: false
            val data = if (deleted) null else o["data"] as JsonObject
            SyncRecord(s("kind"), s("uid"), s("modified"), deleted, data)
        }.getOrNull() // not ours, or damaged: skip it

        /** Groups small enough for one call: at most BATCH records and about BATCH_BYTES of data. */
        fun batches(records: List<SyncRecord>): List<List<SyncRecord>> {
            val out = mutableListOf<List<SyncRecord>>()
            var batch = mutableListOf<SyncRecord>()
            var size = 0
            for (r in records) {
                val length = r.data?.toString()?.length ?: 0
                if (batch.isNotEmpty() && (batch.size >= BATCH || size + length > BATCH_BYTES)) {
                    out += batch; batch = mutableListOf(); size = 0
                }
                batch += r; size += length
            }
            if (batch.isNotEmpty()) out += batch
            return out
        }
    }

    /** The server answered with an error status; turned into a message for the person. */
    private class Refused(val status: Int, val code: String, val text: String) : Exception()

    private fun call(config: CloudConfig, method: String, path: String, body: JsonElement? = null,
                     query: String = "", token: String? = null): JsonElement {
        val (status, text) = try {
            http(method, baseUrl(config) + path + query, body?.toString(), "application/json", token)
        } catch (e: IOException) {
            throw SyncException("Can't reach the sync server. Check your internet connection.")
        }
        if (status >= 400) {
            val error = runCatching { Json.parseToJsonElement(text).jsonObject["error"] as JsonObject }.getOrNull()
            fun field(k: String) = (error?.get(k) as? JsonPrimitive)?.content.orEmpty()
            throw Refused(status, field("code"), field("message"))
        }
        return runCatching { Json.parseToJsonElement(text.ifBlank { "null" }) }
            .getOrElse { throw SyncException(UNREADABLE) }
    }

    private fun explain(e: Refused, account: Boolean): Exception = when {
        e.code in EXPIRED -> CloudAuthException(SIGN_IN_EXPIRED)
        e.status == 429 && e.text.isNotEmpty() -> SyncException(e.text) // "wait N seconds"
        account && e.status in 400..499 && e.text.isNotEmpty() -> CloudAuthException(e.text)
        e.status == 401 -> CloudAuthException(SIGN_IN_EXPIRED)
        else -> SyncException("The sync server answered with an error (${e.status}).")
    }

    private fun account(config: CloudConfig, path: String, body: JsonObject, email: String): CloudSession {
        val r = try {
            call(config, "POST", path, body)
        } catch (e: Refused) {
            throw explain(e, account = true)
        }
        return session(r, email)
    }

    private fun session(answer: JsonElement, email: String = ""): CloudSession = try {
        val o = answer.jsonObject
        fun s(k: String) = (o[k] as JsonPrimitive).content
        CloudSession(s("user_id"), (o["email"] as? JsonPrimitive)?.content ?: email, s("token"), s("refresh_token"))
    } catch (e: Exception) {
        throw SyncException(UNREADABLE)
    }

    /** A signed-in call. If the access token ran out meanwhile (they last an hour), get a new
     *  one from the refresh token and try once more. */
    private fun authed(config: CloudConfig, session: CloudSession, method: String, path: String,
                       body: JsonElement? = null, query: String = ""): JsonElement {
        try {
            return call(config, method, path, body, query, session.token)
        } catch (e: Refused) {
            if (e.code != "token_expired") throw explain(e, account = false)
        }
        val fresh = refresh(config, session.refreshToken)
        try {
            return call(config, method, path, body, query, fresh.token)
        } catch (e: Refused) {
            throw explain(e, account = false)
        }
    }

    // ---- accounts -----------------------------------------------------------------------

    /** Sign-up is closed unless the server is set to invite or open; `invite` is the code. */
    override fun signUp(config: CloudConfig, email: String, password: String, invite: String): CloudSession =
        account(config, "/v1/signup", buildJsonObject {
            put("email", email); put("password", password); put("device", device)
            if (invite.isNotEmpty()) put("invite", invite)
        }, email)

    override fun signIn(config: CloudConfig, email: String, password: String) =
        account(config, "/v1/signin", buildJsonObject {
            put("email", email); put("password", password); put("device", device)
        }, email)

    override fun refresh(config: CloudConfig, refreshToken: String): CloudSession {
        val answer = try {
            call(config, "POST", "/v1/refresh", buildJsonObject { put("refresh_token", refreshToken) })
        } catch (e: Refused) {
            throw explain(e, account = false)
        }
        // The refresh token comes back unchanged; keep ours if an older server leaves it out.
        val o = (answer as? JsonObject)?.let {
            if ("refresh_token" in it) it else JsonObject(it + ("refresh_token" to JsonPrimitive(refreshToken)))
        } ?: answer
        return session(o)
    }

    /** Shown in the server's sign-in list. */
    var device: String = "Quire Android"

    // ---- records ------------------------------------------------------------------------

    override fun pull(config: CloudConfig, session: CloudSession, cursor: String?): Pair<List<SyncRecord>, String?> {
        val records = mutableListOf<SyncRecord>()
        var position = cursor
        while (true) {
            val query = position?.takeIf { it.isNotEmpty() }
                ?.let { "?after=" + URLEncoder.encode(it, "UTF-8") }.orEmpty()
            val answer = authed(config, session, "GET", "/v1/records", query = query)
            val rows: JsonArray
            val more: Boolean
            try {
                val o = answer.jsonObject
                rows = o["records"] as JsonArray
                more = (o["more"] as JsonPrimitive).booleanOrNull ?: throw IllegalStateException()
                (o["cursor"] as? JsonPrimitive)?.content?.takeIf { it.isNotEmpty() }?.let { position = it }
            } catch (e: Exception) {
                throw SyncException(UNREADABLE)
            }
            rows.mapNotNull(::fromJson).let(records::addAll)
            if (!more) return records to position
        }
    }

    override fun push(config: CloudConfig, session: CloudSession, records: List<SyncRecord>) {
        for (batch in batches(records)) {
            authed(config, session, "POST", "/v1/records",
                body = buildJsonObject { put("records", JsonArray(batch.map(::toJson))) })
        }
    }
}
