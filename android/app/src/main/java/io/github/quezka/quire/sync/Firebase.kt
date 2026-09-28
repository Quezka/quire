package io.github.quezka.quire.sync

import io.github.quezka.quire.data.SyncRecord
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

data class CloudConfig(val projectId: String, val apiKey: String)
data class CloudSession(val userId: String, val email: String, val token: String, val refreshToken: String)

open class SyncException(message: String) : Exception(message)
class CloudAuthException(message: String) : SyncException(message)

/** The cloud side of sync, as the desktop's CloudBackend port. */
interface Cloud {
    fun signUp(config: CloudConfig, email: String, password: String): CloudSession
    fun signIn(config: CloudConfig, email: String, password: String): CloudSession
    fun refresh(config: CloudConfig, refreshToken: String): CloudSession
    fun pull(config: CloudConfig, session: CloudSession, cursor: String?): Pair<List<SyncRecord>, String?>
    fun push(config: CloudConfig, session: CloudSession, records: List<SyncRecord>)
}

/** HTTP transport, replaceable in tests: (method, url, body, contentType, token) -> (status, text). */
typealias Http = (String, String, String?, String, String?) -> Pair<Int, String>

val urlConnectionHttp: Http = { method, url, body, contentType, token ->
    val connection = URL(url).openConnection() as HttpURLConnection
    try {
        connection.requestMethod = method
        connection.connectTimeout = 20_000
        connection.readTimeout = 30_000
        connection.setRequestProperty("Content-Type", contentType)
        token?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
        if (body != null) {
            connection.doOutput = true
            connection.outputStream.use { it.write(body.toByteArray()) }
        }
        val status = connection.responseCode
        val stream = if (status < 400) connection.inputStream else connection.errorStream
        status to (stream?.bufferedReader()?.use { it.readText() } ?: "")
    } finally {
        connection.disconnect()
    }
}

/**
 * Firebase Auth (Identity Toolkit) and Firestore over REST, in exactly the desktop's format:
 * users/<account>/records/<kind>~<uid> with kind, uid, modified, deleted, data (a JSON
 * string) and a server-stamped `synced` time used to page through changes.
 */
class FirebaseCloud(private val http: Http = urlConnectionHttp) : Cloud {

    companion object {
        const val PAGE = 300
        const val BATCH = 400
        private const val FIRESTORE = "https://firestore.googleapis.com/v1"

        fun docId(r: SyncRecord) = "${r.kind}~${r.uid}".replace("/", "%2F")

        fun toFields(r: SyncRecord) = buildJsonObject {
            putJsonObject("kind") { put("stringValue", r.kind) }
            putJsonObject("uid") { put("stringValue", r.uid) }
            putJsonObject("modified") { put("stringValue", r.modified) }
            putJsonObject("deleted") { put("booleanValue", r.deleted) }
            if (r.data != null) putJsonObject("data") { put("stringValue", r.data.toString()) }
            else putJsonObject("data") { put("nullValue", JsonNull) }
        }

        fun fromFields(fields: JsonObject): SyncRecord? = runCatching {
            fun str(key: String) = (fields[key] as JsonObject)["stringValue"]!!.let {
                (it as JsonPrimitive).content
            }
            val data = (fields["data"] as? JsonObject)?.get("stringValue")?.let {
                Json.parseToJsonElement((it as JsonPrimitive).content) as? JsonObject
            }
            val deleted = ((fields["deleted"] as? JsonObject)?.get("booleanValue") as? JsonPrimitive)
                ?.booleanOrNull ?: false
            SyncRecord(str("kind"), str("uid"), str("modified"), deleted, data)
        }.getOrNull()

        private val AUTH_MESSAGES = mapOf(
            "EMAIL_EXISTS" to "There's already an account with this email: sign in instead.",
            "EMAIL_NOT_FOUND" to "No account with this email: create one first.",
            "INVALID_PASSWORD" to "Wrong email or password.",
            "INVALID_LOGIN_CREDENTIALS" to "Wrong email or password.",
            "INVALID_EMAIL" to "That email address doesn't look right.",
            "OPERATION_NOT_ALLOWED" to "Turn on Email/Password sign-in in the Firebase console.",
            "TOO_MANY_ATTEMPTS_TRY_LATER" to "Too many attempts: wait a few minutes and try again.",
            "TOKEN_EXPIRED" to "Your sign-in has expired: set up sync again.",
            "INVALID_REFRESH_TOKEN" to "Your sign-in has expired: set up sync again.",
            "USER_NOT_FOUND" to "This account no longer exists: set up sync again.",
        )

        fun authMessage(code: String): String {
            val base = code.substringBefore(":").trim()
            return when {
                base == "WEAK_PASSWORD" -> "Choose a password of at least 6 characters."
                base.startsWith("API key not valid") ->
                    "The Web API key isn't right: copy it again from the Firebase console."
                else -> AUTH_MESSAGES[base] ?: "Firebase refused the sign-in ($base)."
            }
        }
    }

    private fun call(method: String, url: String, body: String?, token: String? = null,
                     form: Boolean = false, auth: Boolean = false): JsonElement {
        val (status, text) = try {
            http(method, url, body,
                if (form) "application/x-www-form-urlencoded" else "application/json", token)
        } catch (e: IOException) {
            throw SyncException("Can't reach the sync server. Check your internet connection.")
        }
        if (status >= 400) {
            val message = runCatching {
                ((Json.parseToJsonElement(text).jsonObject["error"] as JsonObject)["message"]
                    as JsonPrimitive).content
            }.getOrDefault("")
            throw when {
                auth && status < 500 -> CloudAuthException(authMessage(message))
                status == 401 -> CloudAuthException("Your sign-in has expired: set up sync again.")
                status == 403 -> SyncException("Firestore refused access. Check that the database " +
                    "exists and the security rules are published.")
                status == 404 -> SyncException("Firestore database not found. Check the project ID.")
                else -> SyncException("The sync server answered with an error ($status).")
            }
        }
        return runCatching { Json.parseToJsonElement(text.ifBlank { "null" }) }
            .getOrElse { throw SyncException("The sync server sent an answer Quire doesn't understand.") }
    }

    private fun account(action: String, config: CloudConfig, email: String, password: String): CloudSession {
        val body = buildJsonObject {
            put("email", email); put("password", password); put("returnSecureToken", true)
        }.toString()
        val r = call("POST", "https://identitytoolkit.googleapis.com/v1/accounts:$action?key=${config.apiKey}",
            body, auth = true).jsonObject
        fun s(k: String) = (r[k] as JsonPrimitive).content
        return CloudSession(s("localId"), (r["email"] as? JsonPrimitive)?.content ?: email,
            s("idToken"), s("refreshToken"))
    }

    override fun signUp(config: CloudConfig, email: String, password: String) =
        account("signUp", config, email, password)

    override fun signIn(config: CloudConfig, email: String, password: String) =
        account("signInWithPassword", config, email, password)

    override fun refresh(config: CloudConfig, refreshToken: String): CloudSession {
        val body = "grant_type=refresh_token&refresh_token=" + URLEncoder.encode(refreshToken, "UTF-8")
        val r = call("POST", "https://securetoken.googleapis.com/v1/token?key=${config.apiKey}", body,
            form = true, auth = true).jsonObject
        fun s(k: String) = (r[k] as JsonPrimitive).content
        return CloudSession(s("user_id"), "", s("id_token"), s("refresh_token"))
    }

    private fun root(config: CloudConfig) = "projects/${config.projectId}/databases/(default)/documents"

    override fun pull(config: CloudConfig, session: CloudSession, cursor: String?): Pair<List<SyncRecord>, String?> {
        val parent = "${root(config)}/users/${session.userId}"
        val records = mutableListOf<SyncRecord>()
        var position = cursor
        while (true) {
            val query = buildJsonObject {
                putJsonObject("structuredQuery") {
                    putJsonArray("from") { add(buildJsonObject { put("collectionId", "records") }) }
                    putJsonArray("orderBy") {
                        add(buildJsonObject {
                            putJsonObject("field") { put("fieldPath", "synced") }
                            put("direction", "ASCENDING")
                        })
                        add(buildJsonObject {
                            putJsonObject("field") { put("fieldPath", "__name__") }
                            put("direction", "ASCENDING")
                        })
                    }
                    put("limit", PAGE)
                    position?.let { p ->
                        val (synced, name) = Json.parseToJsonElement(p) as JsonArray
                        putJsonObject("startAt") {
                            putJsonArray("values") {
                                add(buildJsonObject { put("timestampValue", (synced as JsonPrimitive).content) })
                                add(buildJsonObject { put("referenceValue", (name as JsonPrimitive).content) })
                            }
                            put("before", false)
                        }
                    }
                }
            }
            val rows = call("POST", "$FIRESTORE/$parent:runQuery", query.toString(), session.token)
            val documents = (rows as? JsonArray).orEmpty().mapNotNull {
                (it as? JsonObject)?.get("document") as? JsonObject
            }
            for (doc in documents) {
                val fields = doc["fields"] as? JsonObject ?: continue
                fromFields(fields)?.let(records::add)
                val synced = ((fields["synced"] as? JsonObject)?.get("timestampValue") as? JsonPrimitive)?.content
                if (synced != null) {
                    position = buildJsonArray {
                        add(JsonPrimitive(synced)); add(doc["name"]!!)
                    }.toString()
                }
            }
            if (documents.size < PAGE) return records to position
        }
    }

    override fun push(config: CloudConfig, session: CloudSession, records: List<SyncRecord>) {
        val base = "${root(config)}/users/${session.userId}/records"
        for (batch in records.chunked(BATCH)) {
            val body = buildJsonObject {
                putJsonArray("writes") {
                    for (r in batch) add(buildJsonObject {
                        putJsonObject("update") {
                            put("name", "$base/${docId(r)}")
                            put("fields", toFields(r))
                        }
                        putJsonArray("updateTransforms") {
                            add(buildJsonObject {
                                put("fieldPath", "synced"); put("setToServerValue", "REQUEST_TIME")
                            })
                        }
                    })
                }
            }
            call("POST", "$FIRESTORE/${root(config)}:commit", body.toString(), session.token)
        }
    }
}
