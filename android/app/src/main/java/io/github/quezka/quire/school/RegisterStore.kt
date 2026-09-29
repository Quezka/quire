package io.github.quezka.quire.school

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import io.github.quezka.quire.domain.Absence
import io.github.quezka.quire.domain.AbsenceKind
import io.github.quezka.quire.domain.Grade
import io.github.quezka.quire.domain.Lesson
import io.github.quezka.quire.domain.Notice
import io.github.quezka.quire.domain.RegisterData
import io.github.quezka.quire.domain.Subject
import io.github.quezka.quire.sync.Settings
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import java.security.KeyStore
import java.time.LocalDate
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** What the register sync keeps on this device, as JSON in the app's private settings. */
class RegisterStore(private val settings: Settings) {
    private val key = "school.data"

    fun load(): RegisterData = settings.get(key)?.let { text ->
        runCatching { decode(Json.parseToJsonElement(text).jsonObject) }.getOrNull()
    } ?: RegisterData()

    fun save(data: RegisterData) = settings.set(key, encode(data).toString())

    fun clear() = settings.set(key, null)

    companion object {
        private fun s(v: String?): JsonElement = v?.let(::JsonPrimitive) ?: JsonNull

        fun encode(d: RegisterData) = buildJsonObject {
            put("student", d.student)
            put("last_sync", s(d.lastSync))
            put("grades", buildJsonArray {
                for (g in d.grades) add(buildJsonObject {
                    put("id", g.id); put("subject", g.subject); put("day", g.day.toString())
                    put("display", g.display); put("value", g.value?.let(::JsonPrimitive) ?: JsonNull)
                    put("component", g.component); put("period", g.period); put("notes", g.notes)
                    put("cancelled", g.cancelled)
                })
            })
            put("lessons", buildJsonArray {
                for (l in d.lessons) add(buildJsonObject {
                    put("id", l.id); put("day", l.day.toString()); put("subject", l.subject)
                    put("topic", l.topic); put("teacher", l.teacher); put("hour", l.hour)
                })
            })
            put("absences", buildJsonArray {
                for (a in d.absences) add(buildJsonObject {
                    put("id", a.id); put("day", a.day.toString()); put("kind", a.kind.code)
                    put("hour", a.hour?.let(::JsonPrimitive) ?: JsonNull); put("justified", a.justified)
                    put("reason", a.reason); put("hours", a.hours)
                    put("own_hour", a.ownHour?.let(::JsonPrimitive) ?: JsonNull)
                })
            })
            put("notices", buildJsonArray {
                for (n in d.notices) add(buildJsonObject {
                    put("id", n.id); put("title", n.title); put("category", n.category)
                    put("published", n.published.toString()); put("read", n.read)
                })
            })
            put("subjects", buildJsonArray {
                for (x in d.subjects) add(buildJsonObject {
                    put("id", x.id); put("name", x.name)
                    put("teachers", buildJsonArray { x.teachers.forEach { add(JsonPrimitive(it)) } })
                })
            })
            put("school_days", buildJsonArray { d.schoolDays.forEach { add(JsonPrimitive(it.toString())) } })
        }

        private fun JsonObject.str(k: String) = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content ?: ""
        private fun JsonObject.int(k: String) = (this[k] as? JsonPrimitive)?.intOrNull
        private fun JsonObject.bool(k: String) = (this[k] as? JsonPrimitive)?.booleanOrNull ?: false
        private fun JsonObject.objects(k: String) = (this[k] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()
        private fun day(text: String) = runCatching { LocalDate.parse(text) }.getOrNull()

        fun decode(o: JsonObject) = RegisterData(
            student = o.str("student"),
            grades = o.objects("grades").mapNotNull { g ->
                Grade(g.str("id"), g.str("subject"), day(g.str("day")) ?: return@mapNotNull null,
                    g.str("display"), (g["value"] as? JsonPrimitive)?.doubleOrNull, g.str("component"),
                    g.str("period"), g.str("notes"), g.bool("cancelled"))
            },
            lessons = o.objects("lessons").mapNotNull { l ->
                Lesson(l.str("id"), day(l.str("day")) ?: return@mapNotNull null, l.str("subject"),
                    l.str("topic"), l.str("teacher"), l.int("hour") ?: 0)
            },
            absences = o.objects("absences").mapNotNull { a ->
                Absence(a.str("id"), day(a.str("day")) ?: return@mapNotNull null,
                    AbsenceKind.of(a.str("kind")) ?: return@mapNotNull null, a.int("hour"),
                    a.bool("justified"), a.str("reason"), a.int("hours") ?: 0, a.int("own_hour"))
            },
            notices = o.objects("notices").mapNotNull { n ->
                Notice(n.str("id"), n.str("title"), n.str("category"),
                    day(n.str("published")) ?: return@mapNotNull null, n.bool("read"))
            },
            subjects = o.objects("subjects").map { x ->
                Subject(x.str("id"), x.str("name"),
                    (x["teachers"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content } ?: emptyList())
            },
            schoolDays = (o["school_days"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content?.let(::day) }
                ?: emptyList(),
            lastSync = o.str("last_sync").ifEmpty { null },
        )
    }
}

/** Keeps a secret (the register password) unreadable outside this app. */
interface SecretBox {
    fun seal(plain: String): String
    fun open(sealed: String): String?
}

/** For tests: no encryption. */
class PlainBox : SecretBox {
    override fun seal(plain: String) = plain
    override fun open(sealed: String) = sealed
}

/** AES-GCM with a key that lives in the Android Keystore and never leaves it. */
class KeystoreBox(private val alias: String = "quire-register") : SecretBox {
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(alias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }

    override fun seal(plain: String): String {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val sealed = cipher.iv + cipher.doFinal(plain.toByteArray())
        return Base64.encodeToString(sealed, Base64.NO_WRAP)
    }

    override fun open(sealed: String): String? = runCatching {
        val bytes = Base64.decode(sealed, Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes, 0, 12))
        String(cipher.doFinal(bytes, 12, bytes.size - 12))
    }.getOrNull()
}
