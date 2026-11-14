package io.github.quezka.quire.domain

import java.time.LocalDate
import java.time.LocalDateTime

/** An idea caught in a second (the desktop's domain/ideas.py), looked at again in the digest. */
data class Idea(val uid: String, val text: String, val created: LocalDateTime, val done: Boolean = false)

object Ideas {
    const val MAX_CHARS = 2000

    fun valid(text: String) = text.isNotBlank() && text.length <= MAX_CHARS

    /** Open ones first, newest first. */
    fun sorted(items: List<Idea>) = items.sortedWith(compareBy<Idea> { it.done }.thenByDescending { it.created })

    fun caughtBetween(items: List<Idea>, first: LocalDate, last: LocalDate) =
        items.filter { it.created.toLocalDate() in first..last }.sortedBy { it.created }
}
