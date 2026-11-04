package io.github.quezka.quire.domain

import java.time.LocalDate

/** Personal finance, mirroring the desktop's domain/finance.py. Amounts are whole cents, so they add up exactly. */
data class Transaction(val uid: String, val day: LocalDate, val cents: Long, val income: Boolean = false,
                       val category: String = "", val note: String = "")

object Finance {
    const val MAX_CENTS = 10_000_000_000L

    /** "12,50", "12.5", "1.234,56", "1,234.56" -> cents, or null. The last separator followed by one or two
     *  digits is the decimal one; any other only groups thousands. */
    fun parseCents(input: String): Long? {
        val text = input.trim().replace(" ", "").replace("€", "").replace("$", "").replace("£", "")
        val last = maxOf(text.lastIndexOf(','), text.lastIndexOf('.'))
        val (rawWhole, cents) = if (last >= 0 && text.length - last - 1 in 1..2)
            text.substring(0, last) to text.substring(last + 1).padEnd(2, '0') else text to "00"
        val whole = rawWhole.replace(",", "").replace(".", "")
        if (whole.isEmpty() && cents.trim('0').isEmpty()) return null
        if (!whole.all(Char::isDigit) || !cents.all(Char::isDigit)) return null
        return (whole.ifEmpty { "0" }.toLongOrNull() ?: return null) * 100 + cents.toLong()
    }

    /** What went out, per category, biggest first. */
    fun byCategory(items: List<Transaction>): List<Pair<String, Long>> =
        items.filter { !it.income }.groupBy { it.category }.map { (k, v) -> k to v.sumOf { it.cents } }
            .sortedWith(compareBy({ -it.second }, { it.first.lowercase() }))
}
