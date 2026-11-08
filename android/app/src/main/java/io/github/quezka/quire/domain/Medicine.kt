package io.github.quezka.quire.domain

import java.time.LocalDate

/** Medicines, mirroring the desktop's domain/medicine.py. It remembers what you told it: no medical advice. */
data class Medicine(
    val uid: String,
    val name: String,
    val dose: String = "",
    val times: List<Int> = emptyList(), // minutes after midnight
    val weekdays: List<Int> = emptyList(), // 0 = Monday; none: every day
    val active: Boolean = true,
    val notes: String = "",
) {
    fun dueOn(day: LocalDate) = active && (weekdays.isEmpty() || (day.dayOfWeek.value - 1) in weekdays)
}

/** A dose you ticked: taken, or deliberately skipped. A planned dose with no log is still open. */
data class DoseLog(val uid: String, val medicineUid: String, val day: LocalDate, val planned: Int,
                   val taken: Boolean = true, val at: Int = 0)

data class PlannedDose(val medicine: Medicine, val day: LocalDate, val planned: Int, val log: DoseLog?) {
    val done get() = log != null
}

object Doses {
    const val LATE_AFTER = 60
    const val REMIND_FOR = 180

    /** Every dose of a day in time order; one already logged shows even if the medicine has since changed. */
    fun plan(day: LocalDate, medicines: List<Medicine>, logs: List<DoseLog>): List<PlannedDose> {
        val byKey = logs.filter { it.day == day }.associateBy { it.medicineUid to it.planned }.toMutableMap()
        val plan = mutableListOf<PlannedDose>()
        for (m in medicines) if (m.dueOn(day)) for (t in m.times) plan += PlannedDose(m, day, t, byKey.remove(m.uid to t))
        val known = medicines.associateBy { it.uid }
        for ((key, log) in byKey) known[key.first]?.let { plan += PlannedDose(it, day, key.second, log) }
        return plan.sortedWith(compareBy({ if (it.planned >= 0) it.planned else it.log?.at ?: 0 }, { it.medicine.name.lowercase() }))
    }

    /** Doses of the plan still to take, the next one first: what "Took …" on the main page ticks. */
    fun pending(plan: List<PlannedDose>): List<PlannedDose> = plan.filter { !it.done && it.planned >= 0 }.sortedBy { it.planned }

    fun isLate(dose: PlannedDose, minute: Int) = !dose.done && dose.planned >= 0 && minute > dose.planned + LATE_AFTER

    fun dueNow(dose: PlannedDose, minute: Int) =
        !dose.done && dose.planned >= 0 && dose.planned <= minute && minute <= dose.planned + REMIND_FOR

    /** "8:00, 13.30 20" -> minutes after midnight, or null if a piece isn't a time. */
    fun parseTimes(text: String): List<Int>? {
        val times = mutableListOf<Int>()
        for (piece in text.trim().split(Regex("[,;\\s]+")).filter { it.isNotEmpty() }) {
            val m = Regex("(\\d{1,2})(?:[:.](\\d{2}))?").matchEntire(piece) ?: return null
            val hour = m.groupValues[1].toInt()
            val minute = m.groupValues[2].ifEmpty { "0" }.toInt()
            if (hour > 23 || minute > 59) return null
            times += hour * 60 + minute
        }
        return times.distinct().sorted()
    }
}
