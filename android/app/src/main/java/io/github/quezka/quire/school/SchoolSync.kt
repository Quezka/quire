package io.github.quezka.quire.school

import io.github.quezka.quire.data.Codec
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.COURSE_COLORS
import io.github.quezka.quire.domain.Course
import io.github.quezka.quire.domain.Grade
import io.github.quezka.quire.domain.Lesson
import io.github.quezka.quire.domain.MAX_LESSON_HOUR
import io.github.quezka.quire.domain.RegisterData
import io.github.quezka.quire.domain.School
import io.github.quezka.quire.domain.Subject
import io.github.quezka.quire.domain.Task
import io.github.quezka.quire.sync.Settings
import java.time.LocalDate
import java.time.temporal.ChronoUnit

/** What one register sync brought, for the notification and the School screen. */
data class SchoolReport(
    val newTasks: List<String> = emptyList(), // titles
    val newGrades: List<Grade> = emptyList(),
    val newAbsences: Int = 0,
    val newNotices: List<String> = emptyList(),
    val problems: List<String> = emptyList(),
    val firstSync: Boolean = false,
) {
    val hasNews get() = newTasks.isNotEmpty() || newGrades.isNotEmpty() || newAbsences > 0 || newNotices.isNotEmpty()
}

data class SchoolStatus(val connected: Boolean, val username: String, val student: String, val lastSync: String?)

/**
 * The register account and mirroring it into Quire, like the desktop's SchoolSyncService:
 * homework and tests become tasks, subjects become courses (both synced to the computer
 * under the same register ids, so they don't double up), and grades, lesson topics,
 * absences and the noticeboard are kept on this device.
 */
class SchoolSync(
    private val register: Classeviva,
    private val repo: Repository,
    private val store: RegisterStore,
    private val settings: Settings,
    private val box: SecretBox,
) {
    companion object {
        const val SOURCE = "classeviva"
        const val ASSIGNMENTS_PAST_DAYS = 30L
        const val ASSIGNMENTS_FUTURE_DAYS = 120L
        const val LESSON_DAYS = 21L
        const val TITLE_LENGTH = 90

        fun external(kind: String, id: String) = "$SOURCE:$kind:$id"

        fun title(item: RemoteAssignment): String {
            val first = item.text.lines().map { it.trim() }.firstOrNull { it.isNotEmpty() }.orEmpty()
            val title = first.ifEmpty { School.tidySubject(item.subjectName) }.ifEmpty { "School assignment" }
            return if (title.length <= TITLE_LENGTH) title else title.take(TITLE_LENGTH - 1).trimEnd() + "…"
        }
    }

    fun status(): SchoolStatus {
        val data = store.load()
        return SchoolStatus(settings.get("school.username") != null, settings.get("school.username").orEmpty(),
            data.student, data.lastSync)
    }

    fun data(): RegisterData = store.load()

    /** Check the account with the register, then remember it. Network. */
    fun connect(username: String, password: String): String {
        val student = register.login(username.trim(), password)
        settings.set("school.username", username.trim())
        settings.set("school.password", box.seal(password))
        store.save(store.load().copy(student = student))
        return student
    }

    /** Forget the account. What was imported stays. */
    fun disconnect() {
        settings.set("school.username", null)
        settings.set("school.password", null)
        store.clear()
    }

    /** Everything fetched in one go (network only; nothing is written). */
    class Snapshot(
        val student: String,
        val subjects: List<Subject>?,
        val assignments: List<RemoteAssignment>?,
        val homework: List<RemoteAssignment>?,
        val grades: List<Pair<Grade, String?>>?,
        val lessons: List<Lesson>?,
        val absences: List<io.github.quezka.quire.domain.Absence>?,
        val notices: List<io.github.quezka.quire.domain.Notice>?,
        val schoolDays: List<LocalDate>?,
        val assignmentWindow: Pair<LocalDate, LocalDate>,
        val lessonWindow: Pair<LocalDate, LocalDate>,
        val problems: List<String>,
    )

    fun fetch(): Snapshot {
        val username = settings.get("school.username") ?: throw RegisterException("Connect your Classeviva account first.")
        val password = settings.get("school.password")?.let(box::open)
            ?: throw RegisterAuthException("Connect your Classeviva account again.")
        val today = repo.today()
        val student = register.login(username, password)
        val problems = mutableListOf<String>()
        fun <T> part(label: String, call: () -> T): T? = try {
            call()
        } catch (e: RegisterAuthException) {
            throw e
        } catch (e: RegisterException) {
            problems += "$label: ${e.message}"; null
        }
        val assignmentWindow = today.minusDays(ASSIGNMENTS_PAST_DAYS) to today.plusDays(ASSIGNMENTS_FUTURE_DAYS)
        val lessonWindow = today.minusDays(LESSON_DAYS) to today
        val snap = Snapshot(
            student,
            part("Subjects") { register.subjects() },
            part("Agenda") { register.assignments(assignmentWindow.first, assignmentWindow.second) },
            part("Homework") { register.homework() },
            part("Grades") { register.grades() },
            part("Lesson topics") { register.lessons(lessonWindow.first, lessonWindow.second) },
            part("Absences") { register.absences() },
            part("Noticeboard") { register.notices() },
            part("School calendar") { register.schoolDays() },
            assignmentWindow, lessonWindow, problems,
        )
        if (problems.size == 8) throw RegisterException("Couldn't sync anything from Classeviva. " + problems.joinToString(" "))
        return snap
    }

    /** Write a snapshot locally (main thread). */
    fun apply(snap: Snapshot): SchoolReport {
        val before = store.load()
        val firstSync = before.lastSync == null
        val newTasks = mutableListOf<String>()

        val courseFor = repo.batch {
            val courseFor = syncCourses(snap)
            for ((items, feed, window) in listOf(Triple(snap.assignments, "agenda", snap.assignmentWindow),
                Triple(snap.homework, "homework", null))) {
                if (items != null) newTasks += syncAssignments(items, feed, window, courseFor)
            }
            courseFor
        }

        val knownGrades = before.grades.map { it.id }.toSet()
        val grades = snap.grades?.map { (g, _) -> g.copy(id = external("grade", g.id)) }
        val knownAbsences = before.absences.associateBy { it.id }
        val absences = snap.absences?.map { a ->
            val id = external("absence", a.id)
            a.copy(id = id, ownHour = knownAbsences[id]?.ownHour) // an hour you entered stays
        }
        val readNotices = before.notices.filter { it.read }.map { it.id }.toSet()
        val notices = snap.notices?.map { n ->
            val id = external("notice", n.id)
            n.copy(id = id, read = n.read || id in readNotices)
        }
        val lessons = snap.lessons?.let { fresh ->
            val (first, last) = snap.lessonWindow
            before.lessons.filter { it.day < first || it.day > last } + fresh.map { it.copy(id = external("lesson", it.id)) }
        }
        val data = RegisterData(
            student = snap.student,
            grades = grades ?: before.grades,
            lessons = lessons ?: before.lessons,
            absences = absences ?: before.absences,
            notices = notices ?: before.notices,
            subjects = snap.subjects?.map { it.copy(name = School.tidySubject(it.name),
                teachers = it.teachers.map(School::tidyPerson)) } ?: before.subjects,
            schoolDays = snap.schoolDays ?: before.schoolDays,
            lastSync = repo.now().truncatedTo(ChronoUnit.SECONDS).toString(),
        )
        store.save(data)
        return SchoolReport(
            newTasks = if (firstSync) emptyList() else newTasks,
            newGrades = if (firstSync) emptyList() else grades.orEmpty().filter { it.id !in knownGrades && !it.cancelled },
            newAbsences = if (firstSync) 0 else absences.orEmpty().count { it.id !in knownAbsences },
            newNotices = if (firstSync) emptyList() else notices.orEmpty().filter { it.id !in before.notices.map { n -> n.id } }.map { it.title },
            problems = snap.problems, firstSync = firstSync,
        )
    }

    /** Match register subjects to courses, creating missing ones; returns the lookup. */
    private fun syncCourses(snap: Snapshot): (String?, String) -> String? {
        val courses = repo.courses().toMutableList()
        val bySubject = mutableMapOf<String, String>()
        val used = courses.map { it.color }.toMutableSet()
        for (subject in snap.subjects.orEmpty()) {
            val ext = external("subject", subject.id)
            val name = School.tidySubject(subject.name)
            val teacher = subject.teachers.filter { it.isNotBlank() }.joinToString(", ", transform = School::tidyPerson)
            var course = courses.firstOrNull { it.externalId == ext }
                ?: courses.firstOrNull { it.name.equals(name, ignoreCase = true) }
            if (course == null) {
                val color = COURSE_COLORS.firstOrNull { it !in used } ?: COURSE_COLORS[used.size % COURSE_COLORS.size]
                used += color
                course = repo.saveCourse(Course(Codec.newUid(), name, teacher, color = color, externalId = ext))
                courses += course
            } else if (course.externalId != ext || (teacher.isNotEmpty() && course.teacher.isEmpty())) {
                course = repo.saveCourse(course.copy(externalId = ext, teacher = course.teacher.ifEmpty { teacher }))
                courses.replaceAll { if (it.uid == course.uid) course else it }
            }
            bySubject[subject.id] = course.uid
        }
        return { id, name ->
            id?.let(bySubject::get) ?: courses.firstOrNull { it.name.equals(School.tidySubject(name), ignoreCase = true) }?.uid
        }
    }

    /** Mirror one feed into tasks. With a window the feed is complete for those dates, so
     *  undone tasks that vanished from it were deleted by the teacher and go too. */
    private fun syncAssignments(items: List<RemoteAssignment>, feed: String, window: Pair<LocalDate, LocalDate>?,
                                courseFor: (String?, String) -> String?): List<String> {
        val prefix = external(feed, "")
        val existing = repo.tasks().filter { it.externalId?.startsWith(prefix) == true }.associateBy { it.externalId!! }
        val seen = mutableSetOf<String>()
        val added = mutableListOf<String>()
        for (item in items) {
            val ext = prefix + item.id
            seen += ext
            var details = item.text.trim()
            if (item.author.isNotBlank()) details += "\n\n— ${School.tidyPerson(item.author)}"
            val fields = Task("", title(item), item.kind, courseFor(item.subjectId, item.subjectName), item.day,
                details = details, externalId = ext)
            val task = existing[ext]
            if (task == null) {
                repo.saveTask(fields.copy(uid = Codec.newUid(), done = item.done))
                added += fields.title
            } else {
                val updated = fields.copy(uid = task.uid, done = task.done || item.done)
                if (updated != task) repo.saveTask(updated) // keeps your own tick
            }
        }
        if (window != null) {
            for ((ext, task) in existing) {
                val due = task.due
                if (ext !in seen && !task.done && due != null && due in window.first..window.second) {
                    repo.deleteTask(task.uid)
                }
            }
        }
        return added
    }

    /** Enter the hour of a late entry or early exit the school left blank (null forgets). */
    fun setAbsenceHour(id: String, hour: Int?) {
        require(hour == null || hour in 1..MAX_LESSON_HOUR)
        val data = store.load()
        store.save(data.copy(absences = data.absences.map { if (it.id == id) it.copy(ownHour = hour) else it }))
        repo.refreshed()
    }

    fun markNoticeRead(id: String) {
        val data = store.load()
        store.save(data.copy(notices = data.notices.map { if (it.id == id) it.copy(read = true) else it }))
        repo.refreshed()
    }
}
