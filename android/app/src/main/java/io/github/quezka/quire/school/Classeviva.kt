package io.github.quezka.quire.school

import io.github.quezka.quire.domain.Absence
import io.github.quezka.quire.domain.AbsenceKind
import io.github.quezka.quire.domain.Grade
import io.github.quezka.quire.domain.Lesson
import io.github.quezka.quire.domain.Notice
import io.github.quezka.quire.domain.School
import io.github.quezka.quire.domain.Subject
import io.github.quezka.quire.domain.TaskKind
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate

open class RegisterException(message: String) : Exception(message)
class RegisterAuthException(message: String) : RegisterException(message)

/** Homework, a test or a note a teacher put on the register. */
data class RemoteAssignment(
    val id: String,
    val day: LocalDate,
    val kind: TaskKind,
    val text: String,
    val subjectId: String?,
    val subjectName: String,
    val author: String = "",
    val done: Boolean = false,
)

/** HTTP for the register: (method, url, body, headers) -> (status, text). */
typealias RegisterHttp = (String, String, String?, Map<String, String>) -> Pair<Int, String>

val registerHttp: RegisterHttp = { method, url, body, headers ->
    val connection = URL(url).openConnection() as HttpURLConnection
    try {
        connection.requestMethod = method
        connection.connectTimeout = 20_000
        connection.readTimeout = 30_000
        headers.forEach(connection::setRequestProperty)
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
 * Classeviva (Spaggiari) over the REST API behind its mobile app, like the desktop's
 * infrastructure/classeviva.py. It isn't officially documented; see
 * https://github.com/Lioydiano/Classeviva-Official-Endpoints.
 */
class Classeviva(private val http: RegisterHttp = registerHttp, private val today: () -> LocalDate = LocalDate::now) {
    private var token: String? = null
    private var student: String? = null

    companion object {
        const val BASE = "https://web.spaggiari.eu/rest/v1"
        private val HEADERS = mapOf(
            "User-Agent" to "CVVS/std/4.2.3 Android/12",
            "Z-Dev-Apikey" to "Tg1NWEwNGIgIC0K",
            "Content-Type" to "application/json",
        )
        private const val HOMEWORK_CODE = "AGHW"
        private val ABSENCE_CODES = mapOf("ABA0" to AbsenceKind.ABSENT, "ABR0" to AbsenceKind.LATE,
            "ABR1" to AbsenceKind.SHORT_LATE, "ABU0" to AbsenceKind.EARLY_EXIT)
        private val HOMEWORK_WORDS = Regex("\\b(compit\\w*|eserciz\\w*|es\\.|pag\\.|pagg?\\b|pagin\\w*|" +
            "studi\\w*|legger\\w*|ripass\\w*|svolger\\w*|homework|exercis\\w*)", RegexOption.IGNORE_CASE)
        private val EXAM_WORDS = Regex("\\b(verific\\w*|compit\\w* in classe|interrogazion\\w*|test|prova|" +
            "prove|esame|esami|simulazione)\\b", RegexOption.IGNORE_CASE)

        /** 1 September to 30 June: the school year Classeviva serves. */
        fun schoolYear(today: LocalDate): Pair<LocalDate, LocalDate> {
            val start = if (today.monthValue >= 9) today.year else today.year - 1
            return LocalDate.of(start, 9, 1) to LocalDate.of(start + 1, 6, 30)
        }

        fun classify(code: String?, text: String): TaskKind = when {
            code == HOMEWORK_CODE -> TaskKind.HOMEWORK
            EXAM_WORDS.containsMatchIn(text) -> TaskKind.EXAM
            HOMEWORK_WORDS.containsMatchIn(text) -> TaskKind.HOMEWORK
            else -> TaskKind.TASK
        }
    }

    private fun send(method: String, path: String, body: String? = null): JsonObject {
        val headers = HEADERS + listOfNotNull(token?.let { "Z-Auth-Token" to it })
        val (status, text) = try {
            http(method, BASE + path, body, headers)
        } catch (e: IOException) {
            throw RegisterException("Couldn't reach Classeviva. Check your internet connection.")
        }
        if (status >= 400) {
            val code = runCatching {
                (Json.parseToJsonElement(text).jsonObject["error"] as JsonPrimitive).content
            }.getOrDefault("")
            // 122: the dates fall outside the school year (e.g. in summer); nothing to read.
            if (status == 404 && code.startsWith("122")) return JsonObject(emptyMap())
            throw when {
                path == "/auth/login" && status in listOf(401, 403, 422) ->
                    RegisterAuthException("Classeviva didn't accept that username and password.")
                status == 401 || status == 403 ->
                    RegisterAuthException("Your Classeviva session was refused. Try connecting your account again.")
                else -> RegisterException("Classeviva answered with an error ($status).")
            }
        }
        return runCatching { Json.parseToJsonElement(text.ifBlank { "{}" }).jsonObject }
            .getOrElse { throw RegisterException("Classeviva sent a response Quire couldn't read.") }
    }

    private fun get(path: String): JsonObject {
        val id = student ?: throw RegisterException("Not signed in to Classeviva.")
        return send("GET", "/students/$id$path")
    }

    private fun stamp(d: LocalDate) = d.toString().replace("-", "")

    private fun ranged(path: String, first: LocalDate, last: LocalDate): JsonObject {
        val (start, end) = schoolYear(today())
        val from = maxOf(first, start)
        val to = minOf(last, end)
        if (from > to) return JsonObject(emptyMap())
        return get("$path/${stamp(from)}/${stamp(to)}")
    }

    /** Signs in; returns the student's name. */
    fun login(username: String, password: String): String {
        token = null
        fun body(ident: String?) = buildJsonObject {
            if (ident == null) put("ident", JsonNull) else put("ident", ident)
            put("pass", password); put("uid", username)
        }.toString()
        var data = send("POST", "/auth/login", body(null))
        val choices = data["choices"] as? JsonArray
        if (data["token"] == null && !choices.isNullOrEmpty()) {
            // An account with several profiles (a parent with two children): use the first.
            data = send("POST", "/auth/login", body((choices[0] as JsonObject).str("ident")))
        }
        token = data.str("token").ifEmpty { throw RegisterException("Classeviva didn't open a session for this account.") }
        student = data.str("ident").filter(Char::isDigit).ifEmpty {
            throw RegisterException("Classeviva didn't say which student this account belongs to.")
        }
        val name = listOf(data.str("firstName"), data.str("lastName")).filter { it.isNotBlank() }.joinToString(" ")
        return School.tidyPerson(name)
    }

    fun subjects(): List<Subject> = get("/subjects").list("subjects").map { s ->
        Subject(s.str("id"), s.str("description"), s.list("teachers").map { it.str("teacherName") })
    }

    fun assignments(first: LocalDate, last: LocalDate): List<RemoteAssignment> =
        ranged("/agenda/all", first, last).list("agenda").mapNotNull { e ->
            val text = e.str("notes").trim()
            val day = date(e.str("evtDatetimeBegin")) ?: return@mapNotNull null
            RemoteAssignment(e.str("evtId"), day, classify(e.str("evtCode"), text), text,
                e.str("subjectId").ifEmpty { null }, e.str("subjectDesc"), e.str("authorName"))
        }

    fun homework(): List<RemoteAssignment> = get("/homeworks").list("items").mapNotNull { h ->
        val due = date(h.str("expiryDate").ifEmpty { h.str("assignmentDate") }) ?: return@mapNotNull null
        RemoteAssignment(h.str("evtId"), due, TaskKind.HOMEWORK, h.str("homeworkDesc").trim(),
            h.str("subjectId").ifEmpty { null }, h.str("subjectDesc"), h.str("teacherName"),
            done = h.bool("homeworkDone"))
    }

    /** Grades, each with its subject id (for linking to a course). */
    fun grades(): List<Pair<Grade, String?>> = get("/grades").list("grades").mapNotNull { g ->
        val day = date(g.str("evtDate")) ?: return@mapNotNull null
        Grade(g.str("evtId"), School.tidySubject(g.str("subjectDesc")), day,
            g.str("displayValue").trim(), (g["decimalValue"] as? JsonPrimitive)?.doubleOrNull,
            g.str("componentDesc"), g.str("periodDesc"), g.str("notesForFamily").trim(),
            g.bool("canceled")) to g.str("subjectId").ifEmpty { null }
    }

    fun lessons(first: LocalDate, last: LocalDate): List<Lesson> {
        val seen = mutableSetOf<String>()
        return ranged("/lessons", first, last).list("lessons").mapNotNull { l ->
            val id = l.str("evtId")
            val day = date(l.str("evtDate"))
            if (day == null || !seen.add(id)) return@mapNotNull null
            Lesson(id, day, School.tidySubject(l.str("subjectDesc")),
                l.str("lessonArg").trim(), School.tidyPerson(l.str("authorName")),
                l.int("evtHPos") ?: 0)
        }
    }

    /** Absences, late entries and early exits. The hour can be missing (`evtHPos: null`)
     *  when the school didn't record it; then the student can enter it in Quire. */
    fun absences(): List<Absence> = get("/absences/details").list("events").mapNotNull { e ->
        val kind = ABSENCE_CODES[e.str("evtCode")] ?: return@mapNotNull null
        val day = date(e.str("evtDate")) ?: return@mapNotNull null
        Absence(e.str("evtId"), day, kind, e.int("evtHPos")?.takeIf { it > 0 }, e.bool("isJustified"),
            e.str("justifReasonDesc").trim(), (e["hoursAbsence"] as? JsonArray)?.size ?: 0)
    }

    fun notices(): List<Notice> = get("/noticeboard").list("items").mapNotNull { n ->
        if (n.str("cntStatus") == "deleted") return@mapNotNull null
        val published = date(n.str("pubDT").ifEmpty { n.str("cntValidFrom") }) ?: today()
        Notice("${n.str("evtCode")}:${n.str("pubId")}", n.str("cntTitle").split(Regex("\\s+"))
            .filter { it.isNotEmpty() }.joinToString(" "), n.str("cntCategory"), published, n.bool("readStatus"))
    }

    fun schoolDays(): List<LocalDate> = get("/calendar/all").list("calendar")
        .filter { it.str("dayStatus") == "SD" }.mapNotNull { date(it.str("dayDate")) }

    // ---- JSON helpers ----

    private fun JsonObject.str(key: String): String = when (val v = this[key]) {
        is JsonPrimitive -> if (v is JsonNull) "" else v.content
        else -> ""
    }

    private fun JsonObject.int(key: String): Int? = (this[key] as? JsonPrimitive)?.let { p ->
        p.intOrNull ?: p.content.trim().toIntOrNull()
    }

    private fun JsonObject.bool(key: String) = (this[key] as? JsonPrimitive)?.booleanOrNull ?: false

    private fun JsonObject.list(key: String): List<JsonObject> =
        (this[key] as? JsonArray)?.mapNotNull { it as? JsonObject } ?: emptyList()

    private fun date(text: String): LocalDate? =
        text.takeIf { it.length >= 10 }?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() }
}
