package io.github.quezka.quire

import io.github.quezka.quire.data.SyncRecord
import io.github.quezka.quire.sync.CloudAuthException
import io.github.quezka.quire.sync.CloudConfig
import io.github.quezka.quire.sync.CloudSession
import io.github.quezka.quire.sync.Http
import io.github.quezka.quire.sync.QuireServerCloud
import io.github.quezka.quire.sync.SyncException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.IOException

/** The Quire server adapter against canned HTTP answers, like the desktop's test_quire_server.py. */
class QuireServerCloudTest {
    private val config = CloudConfig("https://sync.example.com", "")
    private val session = CloudSession("u1", "me@example.com", "tok", "ref")
    private val sessionAnswer = """{"user_id":"u1","email":"me@example.com","token":"t","refresh_token":"r","expires_in":3600}"""

    private class Call(val method: String, val url: String, val body: String?, val token: String?)

    private class Script(vararg answers: Pair<Int, String>) {
        val calls = mutableListOf<Call>()
        private val queue = answers.toMutableList()
        val http: Http = { method, url, body, _, token ->
            calls += Call(method, url, body, token)
            queue.removeAt(0)
        }
    }

    private fun refused(status: Int, code: String, message: String = "m") =
        status to """{"error":{"code":"$code","message":"$message"}}"""

    private fun rec(uid: String = "a", deleted: Boolean = false, modified: String = "2026-10-10T10:00:00.000Z") =
        SyncRecord("task", uid, modified, deleted, if (deleted) null else buildJsonObject { put("t", uid) })

    private fun json(text: String?) = Json.parseToJsonElement(text!!).jsonObject

    private inline fun <reified T : Throwable> raises(block: () -> Unit): T {
        try { block() } catch (e: Throwable) {
            if (e is T) return e
            throw e
        }
        fail("expected ${T::class.simpleName}"); throw IllegalStateException()
    }

    @Test fun signInReturnsASessionAndLabelsTheDevice() {
        val s = Script(200 to sessionAnswer)
        val got = QuireServerCloud(s.http).apply { device = "Pixel" }.signIn(config, "me@example.com", "pw")
        assertEquals(CloudSession("u1", "me@example.com", "t", "r"), got)
        assertEquals("https://sync.example.com/v1/signin", s.calls[0].url)
        assertEquals("POST", s.calls[0].method)
        assertEquals("Pixel", json(s.calls[0].body)["device"]!!.let { (it as JsonPrimitive).content })
    }

    @Test fun signUpSendsTheInviteOnlyWhenGiven() {
        val s = Script(200 to sessionAnswer, 200 to sessionAnswer)
        val cloud = QuireServerCloud(s.http)
        cloud.signUp(config, "me@example.com", "pw")
        cloud.signUp(config, "me@example.com", "pw", "open-sesame")
        assertFalse("invite" in json(s.calls[0].body))
        assertEquals("open-sesame", (json(s.calls[1].body)["invite"] as JsonPrimitive).content)
    }

    @Test fun accountRefusalsShowTheServersMessage() {
        for ((status, code, message) in listOf(
            Triple(401, "invalid_credentials", "Wrong email or password."),
            Triple(403, "signup_closed", "Sign-ups are closed on this server."),
            Triple(409, "email_exists", "That email is already registered."),
            Triple(400, "weak_password", "Choose a longer password."),
        )) {
            val e = raises<CloudAuthException> {
                QuireServerCloud(Script(refused(status, code, message)).http).signUp(config, "a@b.c", "pw")
            }
            assertEquals(message, e.message)
        }
    }

    @Test fun tooManyAttemptsIsAPlainSyncErrorNotADeadSignIn() {
        val e = raises<SyncException> {
            QuireServerCloud(Script(refused(429, "too_many_attempts", "Wait 30 seconds.")).http)
                .signIn(config, "a@b.c", "pw")
        }
        assertFalse(e is CloudAuthException)
        assertEquals("Wait 30 seconds.", e.message)
    }

    @Test fun refreshKeepsTheRefreshTokenAndSendsNoBearer() {
        val s = Script(200 to """{"user_id":"u1","token":"t2","refresh_token":"r1","expires_in":3600}""",
            200 to """{"user_id":"u1","token":"t3"}""")
        val cloud = QuireServerCloud(s.http)
        val a = cloud.refresh(config, "r1")
        assertEquals(Triple("u1", "t2", "r1"), Triple(a.userId, a.token, a.refreshToken))
        assertNull(s.calls[0].token)
        assertEquals("r1", cloud.refresh(config, "r1").refreshToken) // an answer without it
    }

    @Test fun aDeadRefreshTokenMeansSetUpSyncAgain() {
        val e = raises<CloudAuthException> {
            QuireServerCloud(Script(refused(401, "invalid_refresh_token")).http).refresh(config, "old")
        }
        assertTrue(e.message!!.contains("expired"))
    }

    @Test fun pullFollowsTheCursorUntilThereIsNoMore() {
        fun row(uid: String, deleted: Boolean = false) = QuireServerCloud.toJson(rec(uid, deleted)).toString()
        val s = Script(
            200 to """{"records":[${row("a")},${row("b")}],"cursor":"c 1/+","more":true}""",
            200 to """{"records":[${row("c", true)}],"cursor":"c2","more":false}""")
        val (records, cursor) = QuireServerCloud(s.http).pull(config, session, null)
        assertEquals(listOf("a", "b", "c"), records.map { it.uid })
        assertTrue(records[2].deleted); assertNull(records[2].data)
        assertEquals("c2", cursor)
        assertEquals("https://sync.example.com/v1/records", s.calls[0].url) // no cursor the first time
        assertEquals("https://sync.example.com/v1/records?after=c+1%2F%2B", s.calls[1].url)
        assertEquals("tok", s.calls[0].token)
        assertEquals("GET", s.calls[0].method)
    }

    @Test fun pullSkipsDamagedRecordsButKeepsTheRest() {
        val good = QuireServerCloud.toJson(rec("ok")).toString()
        val s = Script(200 to """{"records":[{"kind":"task"},"junk",$good,
            {"kind":"task","uid":"x","modified":"m","deleted":false,"data":"not an object"}],
            "cursor":"c","more":false}""")
        val (records, _) = QuireServerCloud(s.http).pull(config, session, "old")
        assertEquals(listOf("ok"), records.map { it.uid })
    }

    @Test fun pullWithNothingNewKeepsTheCursor() {
        val s = Script(200 to """{"records":[],"cursor":"","more":false}""")
        assertEquals(emptyList<SyncRecord>() to "c9", QuireServerCloud(s.http).pull(config, session, "c9"))
    }

    @Test fun anExpiredAccessTokenIsRefreshedOnceAndTheCallRetried() {
        val s = Script(refused(401, "token_expired"),
            200 to """{"user_id":"u1","token":"fresh","refresh_token":"ref"}""",
            200 to """{"records":[],"cursor":"c","more":false}""")
        QuireServerCloud(s.http).pull(config, session, null)
        assertEquals(listOf("records", "refresh", "records"), s.calls.map { it.url.substringAfterLast("/") })
        assertEquals("fresh", s.calls[2].token)
    }

    @Test fun expiredTwiceGivesUpInsteadOfLooping() {
        val s = Script(refused(401, "token_expired"),
            200 to """{"user_id":"u1","token":"fresh","refresh_token":"ref"}""",
            refused(401, "token_expired"))
        raises<CloudAuthException> { QuireServerCloud(s.http).pull(config, session, null) }
        assertEquals(3, s.calls.size)
    }

    @Test fun aRevokedAccountAsksForANewSignIn() {
        raises<CloudAuthException> {
            QuireServerCloud(Script(refused(401, "user_not_found")).http).pull(config, session, null)
        }
    }

    @Test fun pushSendsRecordsInTheShapeTheServerExpects() {
        val s = Script(200 to """{"stored":2,"cursor":"c"}""")
        QuireServerCloud(s.http).push(config, session, listOf(rec("a"), rec("b", deleted = true)))
        val call = s.calls[0]
        assertEquals("https://sync.example.com/v1/records", call.url)
        assertEquals("tok", call.token)
        val sent = json(call.body)["records"]!!.jsonArray
        assertEquals(2, sent.size)
        val a = sent[0] as JsonObject
        assertEquals(setOf("kind", "uid", "modified", "deleted", "data"), a.keys)
        assertEquals("""{"t":"a"}""", a["data"].toString())
        assertEquals("null", (sent[1] as JsonObject)["data"].toString())
        assertEquals("true", (sent[1] as JsonObject)["deleted"].toString())
    }

    @Test fun bigBatchesAreSplitByCountAndSize() {
        val many = (0 until QuireServerCloud.BATCH * 2 + 1).map { rec("$it") }
        assertEquals(listOf(QuireServerCloud.BATCH, QuireServerCloud.BATCH, 1),
            QuireServerCloud.batches(many).map { it.size })
        val big = (0 until 5).map {
            SyncRecord("image", "$it", "m", false, buildJsonObject { put("data", "x".repeat(3_000_000)) })
        }
        assertEquals(listOf(2, 2, 1), QuireServerCloud.batches(big).map { it.size })
        assertEquals(emptyList<List<SyncRecord>>(), QuireServerCloud.batches(emptyList()))
    }

    @Test fun anUnreachableServerIsExplained() {
        val e = raises<SyncException> {
            QuireServerCloud({ _, _, _, _, _ -> throw IOException("no route") }).signIn(config, "a@b.c", "pw")
        }
        assertTrue(e.message!!.startsWith("Can't reach the sync server"))
    }

    @Test fun garbageFromAProxyIsASyncError() {
        val e = raises<SyncException> {
            QuireServerCloud(Script(200 to "<html>Bad gateway</html>").http).pull(config, session, null)
        }
        assertTrue(e.message!!.contains("doesn't understand"))
        val e2 = raises<SyncException> {
            QuireServerCloud(Script(502 to "<html>").http).pull(config, session, null)
        }
        assertTrue(e2.message!!.contains("502"))
        raises<SyncException> { QuireServerCloud(Script(200 to """{"nothing":1}""").http).signIn(config, "a@b.c", "pw") }
    }

    @Test fun theAddressIsTidied() {
        for ((typed, url) in listOf(
            "https://sync.example.com" to "https://sync.example.com",
            "https://sync.example.com/" to "https://sync.example.com",
            "  sync.example.com  " to "https://sync.example.com",
            "http://192.168.1.106:8080/" to "http://192.168.1.106:8080",
        )) assertEquals(url, QuireServerCloud.baseUrl(CloudConfig(typed, "")))
    }

    @Test fun recordsRoundTripThroughJson() {
        for (r in listOf(rec("a"), rec("b", deleted = true)))
            assertEquals(r, QuireServerCloud.fromJson(QuireServerCloud.toJson(r)))
        assertNull(QuireServerCloud.fromJson(buildJsonObject { put("kind", "x") }))
    }
}
