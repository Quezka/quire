package io.github.quezka.quire.notify

import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Doses
import io.github.quezka.quire.sync.Settings
import java.time.LocalDateTime

/** A notification when a dose is due: one alarm, for the next planned dose of today or tomorrow. */
class MedicineManager(
    private val repo: Repository,
    private val settings: Settings,
    private val notifier: Notifier,
    private val now: () -> LocalDateTime = LocalDateTime::now,
) {
    fun check() {
        val time = now()
        val minute = time.hour * 60 + time.minute
        val day = time.toLocalDate()
        val told = settings.get("medicine.told").orEmpty().split("|").filter { it.startsWith("$day/") }.toMutableSet()
        for (dose in Doses.plan(day, repo.medicines(), repo.doseLogs())) {
            val key = "$day/${dose.medicine.uid}/${dose.planned}"
            if (Doses.dueNow(dose, minute) && key !in told) {
                told += key
                notifier.medicine(dose.medicine.name, dose.medicine.dose, dose.planned)
            }
        }
        settings.set("medicine.told", told.joinToString("|"))
        plan()
    }

    fun plan() {
        val time = now()
        val minute = time.hour * 60 + time.minute
        val today = time.toLocalDate()
        val medicines = repo.medicines()
        val next = (0L..7L).firstNotNullOfOrNull { offset ->
            val day = today.plusDays(offset)
            medicines.filter { it.dueOn(day) }.flatMap { it.times }.filter { offset > 0 || it > minute }.minOrNull()
                ?.let { day.atStartOfDay().plusMinutes(it.toLong()) }
        }
        notifier.wakeAt(Notifier.ACTION_MEDICINE, next)
    }
}
