package io.github.quezka.quire

import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.MemoryRowStore
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.data.SyncRecord
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.sync.Cloud
import io.github.quezka.quire.sync.CloudAuthException
import io.github.quezka.quire.sync.CloudConfig
import io.github.quezka.quire.sync.CloudSession
import io.github.quezka.quire.sync.FirebaseCloud
import io.github.quezka.quire.sync.MemorySettings
import io.github.quezka.quire.sync.SyncEngine
import io.github.quezka.quire.sync.SyncException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.time.Instant

/** An in-memory Firebase, like the desktop's tests/fakes.FakeCloud. */
class FakeCloud : Cloud {
    val accounts = mutableMapOf<String, String>()
    val docs = linkedMapOf<Triple<String, String, String>, Pair<Int, SyncRecord>>()
    var clock = 0
    var offline = false

    private fun check() { if (offline) throw SyncException("Can't reach the sync server.") }
    private fun session(email: String) = CloudSession("user-$email", email, "t", "refresh-$email")

    override fun signUp(config: CloudConfig, email: String, password: String, invite: String): CloudSession {
        check(); if (email in accounts) throw CloudAuthException("exists")
        accounts[email] = password; return session(email)
    }
    override fun signIn(config: CloudConfig, email: String, password: String): CloudSession {
        check(); if (accounts[email] != password) throw CloudAuthException("wrong")
        return session(email)
    }
    override fun refresh(config: CloudConfig, refreshToken: String): CloudSession {
        check(); val email = refreshToken.removePrefix("refresh-")
        if (email !in accounts) throw CloudAuthException("expired")
        return session(email)
    }
    override fun pull(config: CloudConfig, session: CloudSession, cursor: String?): Pair<List<SyncRecord>, String?> {
        check(); val since = cursor?.toInt() ?: 0
        val mine = docs.filter { it.key.first == session.userId && it.value.first > since }
            .values.sortedBy { it.first }
        return mine.map { it.second } to (mine.maxOfOrNull { it.first } ?: since).toString()
    }
    override fun push(config: CloudConfig, session: CloudSession, records: List<SyncRecord>) {
        check(); for (r in records) docs[Triple(session.userId, r.kind, r.uid)] = ++clock to r
    }
}

class SyncTest {
    private val config = CloudConfig("quire-sync-test", "AIzaSyTESTKEY-0123456789abcdef")
    private var now = Instant.parse("2026-09-28T10:00:00Z")

    private inner class Device(cloud: FakeCloud) {
        val records = Records(MemoryRowStore()) { now }
        val repo = Repository(records)
        val engine = SyncEngine(records, cloud, MemorySettings()) { now }
    }

    private fun tick() { now = now.plusMillis(5) }

    @Test fun twoPhonesSyncTasksBothWaysAndNewerWins() {
        val cloud = FakeCloud()
        val a = Device(cloud); val b = Device(cloud)
        a.engine.connect(config, "me@example.com", "secret1", create = true, takeCloudCopy = false)
        b.engine.connect(config, "me@example.com", "secret1", create = false, takeCloudCopy = false)

        val task = a.repo.saveTask(Task(Codec.newUid(), "Essay"))
        assertEquals(1, a.engine.sync().sent)
        assertEquals(1, b.engine.sync().received)
        assertEquals(0, b.engine.status().pending) // received isn't "changed here"

        tick(); a.repo.saveTask(task.copy(title = "Essay: draft"))   // older
        tick(); b.repo.saveTask(task.copy(title = "Essay: final"))   // newer
        a.engine.sync(); b.engine.sync(); a.engine.sync()
        assertEquals("Essay: final", a.repo.task(task.uid)!!.title)
        assertEquals("Essay: final", b.repo.task(task.uid)!!.title)

        tick(); b.repo.deleteTask(task.uid)
        b.engine.sync(); a.engine.sync()
        assertTrue(a.repo.tasks().isEmpty())
        assertEquals(0, a.engine.sync().sent)
    }

    @Test fun takingTheCloudCopyReplacesLocalData() {
        val cloud = FakeCloud()
        val a = Device(cloud); val b = Device(cloud)
        a.repo.saveTask(Task(Codec.newUid(), "From the laptop"))
        a.engine.connect(config, "me@example.com", "secret1", create = true, takeCloudCopy = false)
        a.engine.sync()
        b.repo.saveTask(Task(Codec.newUid(), "Typed twice"))
        b.engine.connect(config, "me@example.com", "secret1", create = false, takeCloudCopy = true)
        b.engine.sync()
        assertEquals(listOf("From the laptop"), b.repo.tasks().map { it.title })
    }

    @Test fun problemsAreRememberedAndADeadSignInAsksToSetUpAgain() {
        val cloud = FakeCloud()
        val a = Device(cloud)
        a.engine.connect(config, "me@example.com", "secret1", create = true, takeCloudCopy = false)
        cloud.offline = true
        try { a.engine.sync(); fail() } catch (e: SyncException) { }
        assertTrue(a.engine.status().problem.isNotEmpty())
        cloud.offline = false
        a.engine.sync()
        assertEquals("", a.engine.status().problem)
        cloud.accounts.clear()
        try { a.engine.sync(); fail() } catch (e: CloudAuthException) { }
        assertTrue(!a.engine.status().setUp)
    }

    @Test fun setupChecksItsInputs() {
        assertTrue(SyncEngine.check("My Project", config.apiKey, "a@b.co", "x") != null)
        assertTrue(SyncEngine.check(config.projectId, "short", "a@b.co", "x") != null)
        assertTrue(SyncEngine.check(config.projectId, config.apiKey, "nope", "x") != null)
        assertNull(SyncEngine.check(config.projectId, config.apiKey, "a@b.co", "x"))
    }

    // ---- a Quire server instead of Firebase -------------------------------------------

    private val server = CloudConfig("https://sync.example.com", "", io.github.quezka.quire.sync.Backends.SERVER)

    @Test fun serverSetupChecksItsInputs() {
        for (bad in listOf("", "   ", "ftp://sync.example.com", "sync example com", "https://"))
            assertTrue(bad, SyncEngine.checkServer(bad, "me@example.com", "pw")!!.contains("Quire server"))
        assertTrue(SyncEngine.checkServer("sync.example.com", "nope", "pw")!!.contains("email"))
        assertTrue(SyncEngine.checkServer("sync.example.com", "me@example.com", "")!!.contains("password"))
        assertNull(SyncEngine.checkServer("sync.example.com", "me@example.com", "pw"))
        assertEquals(server, SyncEngine.serverConfig("  sync.example.com/ "))
        assertEquals("http://192.168.1.106:8080", SyncEngine.serverConfig("http://192.168.1.106:8080/")!!.projectId)
    }

    @Test fun twoPhonesSyncThroughAServerAccount() {
        val cloud = FakeCloud()
        val a = Device(cloud); val b = Device(cloud)
        a.engine.connect(server, "me@example.com", "secret1", create = true, takeCloudCopy = false, invite = "code")
        b.engine.connect(server, "me@example.com", "secret1", create = false, takeCloudCopy = false)
        val status = a.engine.status()
        assertTrue(status.setUp)
        assertEquals(io.github.quezka.quire.sync.Backends.SERVER, status.backend)
        assertEquals("https://sync.example.com", status.projectId)
        a.repo.saveTask(Task(Codec.newUid(), "From the server"))
        a.engine.sync()
        assertEquals(1, b.engine.sync().received)
    }

    @Test fun movingFromFirebaseToAServerSendsEverythingAgain() {
        val cloud = FakeCloud()
        val a = Device(cloud)
        a.repo.saveTask(Task(Codec.newUid(), "One")); a.repo.saveTask(Task(Codec.newUid(), "Two"))
        a.engine.connect(config, "me@example.com", "secret1", create = true, takeCloudCopy = false)
        a.engine.sync()
        assertEquals(0, a.engine.status().pending)
        a.engine.connect(server, "me@example.com", "secret1", create = false, takeCloudCopy = false)
        assertEquals(2, a.engine.status().pending)
        cloud.docs.clear() // what the new server lacks
        assertEquals(2, a.engine.sync().sent)
        assertEquals(2, cloud.docs.size)
    }

    @Test fun signingInAgainToTheSamePlaceDoesNotResendEverything() {
        val cloud = FakeCloud()
        val a = Device(cloud)
        a.repo.saveTask(Task(Codec.newUid(), "One"))
        a.engine.connect(server, "me@example.com", "secret1", create = true, takeCloudCopy = false)
        a.engine.sync()
        a.engine.connect(server, "me@example.com", "secret1", create = false, takeCloudCopy = false)
        assertEquals(0, a.engine.status().pending)
    }

    @Test fun aServerLinkFromTheComputerSetsUpThePhone() {
        val cloud = FakeCloud()
        val laptop = Device(cloud); val phone = Device(cloud)
        laptop.engine.connect(server, "me@example.com", "secret1", create = true, takeCloudCopy = false)
        laptop.repo.saveTask(Task(Codec.newUid(), "On the laptop"))
        laptop.engine.sync()
        val link = io.github.quezka.quire.sync.DeviceLink(
            "https://sync.example.com", "", "me@example.com", "refresh-me@example.com",
            backend = io.github.quezka.quire.sync.Backends.SERVER)
        phone.engine.connectWithLink(link)
        assertEquals(io.github.quezka.quire.sync.Backends.SERVER, phone.engine.status().backend)
        assertEquals(1, phone.engine.sync().received)
        assertEquals(listOf("On the laptop"), phone.repo.tasks().map { it.title })
    }

    @Test fun disconnectingForgetsTheServer() {
        val cloud = FakeCloud()
        val a = Device(cloud)
        a.engine.connect(server, "me@example.com", "secret1", create = true, takeCloudCopy = false)
        a.engine.disconnect()
        val status = a.engine.status()
        assertFalse(status.setUp)
        assertEquals(io.github.quezka.quire.sync.Backends.FIREBASE, status.backend)
        assertEquals("", status.projectId)
    }

    @Test fun theRouterSendsEachCallToItsBackend() {
        val calls = mutableListOf<String>()
        class Spy(val name: String) : Cloud {
            private fun s() = CloudSession("u", "e", "t", "r")
            override fun signUp(config: CloudConfig, email: String, password: String, invite: String) = s().also { calls += "$name:signUp:$invite" }
            override fun signIn(config: CloudConfig, email: String, password: String) = s().also { calls += "$name:signIn" }
            override fun refresh(config: CloudConfig, refreshToken: String) = s().also { calls += "$name:refresh" }
            override fun pull(config: CloudConfig, session: CloudSession, cursor: String?) =
                (emptyList<SyncRecord>() to cursor).also { calls += "$name:pull" }
            override fun push(config: CloudConfig, session: CloudSession, records: List<SyncRecord>) { calls += "$name:push" }
        }
        val router = io.github.quezka.quire.sync.RoutingCloud(Spy("firebase"), Spy("server"))
        router.signIn(config, "a@b.c", "pw")
        router.signUp(server, "a@b.c", "pw", "code")
        router.refresh(server, "r")
        router.push(config, CloudSession("u", "e", "t", "r"), emptyList())
        assertEquals(listOf("firebase:signIn", "server:signUp:code", "server:refresh", "firebase:push"), calls)
    }
}

class FirebaseTest {
    private val config = CloudConfig("quire-test", "AIzaKEY")
    private val session = CloudSession("uid1", "me@example.com", "tok", "ref")

    @Test fun recordsRoundTripThroughFirestoreFields() {
        val r = SyncRecord("task", "ext:classeviva:homework:1", "2026-09-28T10:00:00.000Z", false,
            buildJsonObject { put("title", "Esercizi"); put("done", true) })
        assertEquals(r, FirebaseCloud.fromFields(FirebaseCloud.toFields(r)))
        val gone = SyncRecord("note", "abc", "2026-09-28T10:00:00.000Z", true, null)
        assertEquals(gone, FirebaseCloud.fromFields(FirebaseCloud.toFields(gone)))
    }

    @Test fun pushCommitsWithAServerTimestampAndPullPages() {
        val calls = mutableListOf<Pair<String, String?>>()
        val cloud = FirebaseCloud { _, url, body, _, token ->
            calls += url to body
            assertEquals("tok", token)
            if (url.endsWith(":commit")) 200 to "{}" else 200 to """[{"document": {
                "name": "projects/p/databases/(default)/documents/users/uid1/records/task~a",
                "fields": ${FirebaseCloud.toFields(SyncRecord("task", "a", "2026-09-28T10:00:00.000Z",
                    false, buildJsonObject { put("title", "x") }))
                    .let { JsonObject(it + ("synced" to buildJsonObject { put("timestampValue", "2026-09-28T10:00:01Z") })) }}
            }}, {"readTime": "x"}]"""
        }
        cloud.push(config, session, listOf(SyncRecord("note", "n1", "2026-09-28T10:00:00.000Z")))
        val write = (Json.parseToJsonElement(calls[0].second!!).jsonObject["writes"] as JsonArray)[0].jsonObject
        assertTrue(((write["update"] as JsonObject)["name"] as JsonPrimitive).content
            .endsWith("/users/uid1/records/note~n1"))
        val (records, cursor) = cloud.pull(config, session, null)
        assertEquals(listOf("a"), records.map { it.uid })
        assertTrue(cursor!!.contains("task~a"))
    }

    @Test fun signInErrorsAreExplained() {
        val cloud = FirebaseCloud { _, _, _, _, _ -> 400 to """{"error": {"message": "INVALID_LOGIN_CREDENTIALS"}}""" }
        try {
            cloud.signIn(config, "me@example.com", "x"); fail()
        } catch (e: CloudAuthException) {
            assertEquals("Wrong email or password.", e.message)
        }
    }
}
