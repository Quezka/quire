package io.github.quezka.quire.domain

/** The bits of Markdown the notes editor understands, as on the desktop
 *  (presentation/markdown_editor.py). Pure text in, text out. */
object Markdown {
    private val LIST_ITEM = Regex("""^(\s*)([-*+]|\d+[.)])(\s+)(\[[ xX]\]\s+)?""")
    private val CHECKBOX = Regex("""^(\s*[-*+]\s+)\[([ xX])\]""")

    /** The start of a note's text after its title, as plain words. */
    fun snippet(body: String, length: Int = 90): String {
        val lines = withoutImages(body).lines().map { it.trim() }.filter { it.isNotEmpty() }
        var text = lines.drop(1).joinToString(" ")
        text = text.replace(Regex("""(^|\s)#{1,6}\s+"""), "$1")
            .replace(Regex("""[-*+]\s+\[[ xX]\]\s+|(^|(?<=\s))[-*+>]\s+|\*\*|__|`|~~"""), "")
            .replace(Regex("""\[([^\]]+)\]\([^)]+\)"""), "$1")
            .replace(Regex("""(?<![\w*])[*_](?=\S)(.+?)(?<=\S)[*_](?![\w*])"""), "$1")
            .split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
        return if (text.length <= length) text else text.take(length - 1).trimEnd() + "…"
    }

    /**
     * Called when the text changed from [old] to [new] with the cursor at [cursor]: if a
     * newline was just typed at the end of a list item, continue the list (or end it, on an
     * empty item). Returns the new text and cursor, or null to leave the edit alone.
     */
    fun continueList(old: String, new: String, cursor: Int): Pair<String, Int>? {
        if (new.length != old.length + 1 || cursor < 1 || cursor > new.length || new[cursor - 1] != '\n') return null
        if (new.removeRange(cursor - 1, cursor) != old) return null
        val lineStart = new.lastIndexOf('\n', cursor - 2) + 1
        val line = new.substring(lineStart, cursor - 1)
        val m = LIST_ITEM.find(line) ?: return null
        if (line.substring(m.range.last + 1).isBlank()) {
            // Enter on an empty item ends the list: drop its marker.
            val text = new.removeRange(lineStart, cursor)
            return text to lineStart
        }
        val (indent, marker0, space, box) = m.destructured
        val marker = marker0.dropLast(1).toIntOrNull()?.let { "${it + 1}${marker0.last()}" } ?: marker0
        val prefix = indent + marker + space + if (box.isNotEmpty()) "[ ] " else ""
        return new.substring(0, cursor) + prefix + new.substring(cursor) to cursor + prefix.length
    }

    /** Tick or untick the checkbox on line [index] (0-based); unchanged if it has none. */
    fun toggleCheckbox(body: String, index: Int): String {
        val lines = body.lines().toMutableList()
        val line = lines.getOrNull(index) ?: return body
        val m = CHECKBOX.find(line) ?: return body
        val mark = m.groups[2]!!
        lines[index] = line.replaceRange(mark.range, if (mark.value.lowercase() == "x") " " else "x")
        return lines.joinToString("\n")
    }

    /** A span of inline format: the whole of it, marks included, and how long its marks are. */
    private data class Span(val kinds: Set<String>, val start: Int, val end: Int, val mark: Int)

    private val SPANS = Regex(
        """(`[^`\n]+`)""" +
            """|\*\*\*((?=\S)[^*]+?(?<=\S))\*\*\*""" +
            """|\*\*((?=\S).+?(?<=\S))\*\*|__((?=\S).+?(?<=\S))__""" +
            """|~~((?=\S).+?(?<=\S))~~""" +
            """|(?<![*\w\\])\*((?=[^\s*]).+?(?<=[^\s*]))\*(?!\*)""" +
            """|(?<![\w\\])_((?=\S).+?(?<=\S))_(?!\w)""")

    private fun spansAround(text: String, start: Int, end: Int, from: Int, to: Int, out: MutableList<Span>) {
        for (m in SPANS.findAll(text.subSequence(0, to), from)) {
            val g = m.groups
            val index = (2..7).firstOrNull { g[it] != null }
            val mark = when (index) { null -> 1; 2 -> 3; 6, 7 -> 1; else -> 2 }
            val s = m.range.first; val e = m.range.last + 1
            if (start < s + mark || end > e - mark) continue  // on the marks or outside: typing there isn't in the span
            val kinds = when (index) {
                null -> setOf("code"); 2 -> setOf("bold", "italic"); 3, 4 -> setOf("bold")
                5 -> setOf("strike"); else -> setOf("italic")
            }
            out += Span(kinds, s, e, mark)
            if (index != null) spansAround(text, start, end, s + mark, e - mark, out)
        }
    }

    /** "bold", "italic", "code" and "strike", where they hold from [start] to [end] on this line. */
    fun formatsAt(text: String, start: Int, end: Int = start): Set<String> {
        val out = mutableListOf<Span>()
        spansAround(text, start, end, 0, text.length, out)
        return out.flatMapTo(mutableSetOf()) { it.kinds }
    }

    /** The toolbar's press: off if the cursor is inside [kind] already, else [wrap]. Like the desktop, off
     *  takes the format from the whole span. */
    fun toggle(text: String, start: Int, end: Int, kind: String, marker: String, placeholder: String): Triple<String, Int, Int> {
        val spans = mutableListOf<Span>()
        spansAround(text, start, end, 0, text.length, spans)
        val span = spans.lastOrNull { kind in it.kinds } ?: return wrap(text, start, end, marker, placeholder)
        val n = if (span.mark == 3) marker.length else span.mark  // bold italic keeps the other one
        val out = text.removeRange(span.end - n, span.end).removeRange(span.start, span.start + n)
        return Triple(out, (start - n).coerceAtLeast(span.start), (end - n).coerceAtLeast(span.start))
    }

    /** Put [marker] around the selection (or around [placeholder]); again removes it. */
    fun wrap(text: String, start: Int, end: Int, marker: String, placeholder: String): Triple<String, Int, Int> {
        val selected = text.substring(start, end)
        val n = marker.length
        if (selected.length >= 2 * n && selected.startsWith(marker) && selected.endsWith(marker)) {
            val inner = selected.substring(n, selected.length - n)
            return Triple(text.replaceRange(start, end, inner), start, start + inner.length)
        }
        val inner = selected.ifEmpty { placeholder }
        return Triple(text.replaceRange(start, end, "$marker$inner$marker"), start + n, start + n + inner.length)
    }

    /** Turn the lines touched by start..end into list items with [prefix] ("- ", "- [ ] ",
     *  "> ", "# "), or back when they all have it already. */
    fun togglePrefix(text: String, start: Int, end: Int, prefix: String): Pair<String, Int> {
        val first = text.lastIndexOf('\n', start - 1) + 1
        val lastNl = text.indexOf('\n', end).let { if (it < 0) text.length else it }
        val block = text.substring(first, lastNl).lines()
        val strip = Regex("""^(\s*)(?:[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+[.)]\s+|>\s?|#{1,6}\s+)""")
        val allHave = block.filter { it.isNotBlank() }.all { it.trimStart().startsWith(prefix.trim()) }
        val changed = block.joinToString("\n") { line ->
            val indent = line.takeWhile { it == ' ' || it == '\t' }
            val body = strip.find(line)?.let { line.substring(it.range.last + 1) } ?: line.substring(indent.length)
            if (allHave) indent + body else indent + prefix + body
        }
        val result = text.substring(0, first) + changed + text.substring(lastNl)
        return result to (first + changed.length)
    }

    /** Clean up text read from a photo: rejoin words hyphenated across lines and lines
     *  wrapped mid-sentence, keep paragraph breaks and list-looking lines. */
    fun tidyOcr(raw: String): String {
        val paragraphs = raw.replace("\r", "").split(Regex("\n\\s*\n"))
        return paragraphs.map { p ->
            val lines = p.lines().map { it.trim() }.filter { it.isNotEmpty() }
            val out = StringBuilder()
            for (line in lines) {
                val listy = Regex("""^([-•*]|\d+[.)])\s""").containsMatchIn(line)
                when {
                    out.isEmpty() -> out.append(line)
                    out.endsWith("-") && line.first().isLowerCase() -> { out.setLength(out.length - 1); out.append(line) }
                    listy || out.last() in ".:;!?" && line.first().isUpperCase() -> out.append('\n').append(line)
                    else -> out.append(' ').append(line)
                }
            }
            out.toString().replace("•", "-").replace(Regex(" {2,}"), " ")
        }.filter { it.isNotBlank() }.joinToString("\n\n")
    }
}
