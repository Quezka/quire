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

    const val RESURFACE_AFTER_DAYS = 7L // an open idea this old may come back in the digest
    const val RESURFACE_GAP_DAYS = 14L // and not again sooner than this
    private val TAG = Regex("(?<![\\w#])#(\\w[\\w-]*)")

    /** `#school`, `#game`: tags are words in the text (same rule as the desktop's domain/ideas.py). */
    fun tags(text: String): List<String> = TAG.findAll(text).map { it.groupValues[1].lowercase() }.distinct().toList()

    /** Every word of the query is in the text; `#tag` words must be tags. */
    fun matches(idea: Idea, query: String): Boolean {
        val text = idea.text.lowercase()
        val own = tags(idea.text)
        return query.lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() }.all { w ->
            if (w.startsWith("#")) w.drop(1) in own else w in text
        }
    }

    /** Tags of the open ideas, most used first. */
    fun allTags(items: List<Idea>): List<String> = items.filter { !it.done }.flatMap { tags(it.text) }
        .groupingBy { it }.eachCount().entries.sortedWith(compareBy({ -it.value }, { it.key })).map { it.key }

    /** One open idea to look at again: older than a week, not shown in the last two, the longest unseen first. */
    fun resurface(items: List<Idea>, today: LocalDate, seen: Map<String, String>): Idea? {
        fun last(i: Idea) = seen[i.uid]?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
        return items.filter { !it.done && !it.created.toLocalDate().isAfter(today.minusDays(RESURFACE_AFTER_DAYS)) &&
            (last(it)?.let { d -> !d.isAfter(today.minusDays(RESURFACE_GAP_DAYS)) } ?: true) }
            .minWithOrNull(compareBy<Idea>({ last(it) ?: LocalDate.MIN }, { it.created }))
    }

    /** A task title from an idea: its first line without tags, cut at a word. */
    fun firstLine(text: String, limit: Int = 120): String {
        val line = TAG.replace(text.trim().lineSequence().firstOrNull().orEmpty(), "").trim().split(Regex("\\s+"))
            .filter { it.isNotEmpty() }.joinToString(" ")
        if (line.length <= limit) return line
        return line.take(limit).substringBeforeLast(' ') + "…"
    }
}
