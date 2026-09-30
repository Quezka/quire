package io.github.quezka.quire.domain

/**
 * A note as the editor shows it: one block per line of its Markdown, the same way the
 * desktop editor maps it, so notes round-trip exactly between the two.
 *
 * [text] is the line's inline Markdown without its line prefix ("# ", "- [ ] ", "> "…).
 */
enum class BlockKind { TEXT, HEADING, BULLET, NUMBERED, CHECK, QUOTE, CODE, IMAGE, RULE }

data class NoteBlock(
    val kind: BlockKind = BlockKind.TEXT,
    val text: String = "",
    val level: Int = 0, // heading level (1-6), list depth (0 = top), quote depth (1+)
    val checked: Boolean = false,
    val number: Int = 1, // a numbered item's number (the first of a run sets the start)
    val extra: String = "", // a picture's uid, or a code block's language
) {
    val isList get() = kind == BlockKind.BULLET || kind == BlockKind.NUMBERED || kind == BlockKind.CHECK
}

/** What an edit did: the new blocks, and where the cursor goes (block index, offset). */
data class BlockEdit(val blocks: List<NoteBlock>, val focus: Int, val cursor: Int)

object NoteBlocks {
    private val HEADING = Regex("""^(#{1,6})\s+(.*)$""")
    private val LIST_ITEM = Regex("""^(\s*)([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?(.*)$""")
    private val QUOTE = Regex("""^\s*((?:>\s?)+)(.*)$""")
    private val FENCE = Regex("""^\s*(```+|~~~+)\s*([\w+#.-]*)\s*$""")
    private val IMAGE = Regex("""^\s*!\[([^\]\n]*)\]\(quire-image:([0-9a-f]{8,64})\)\s*$""")
    private val RULE = Regex("""^\s*(?:-{3,}|\*{3,}|_{3,})\s*$""")

    private fun depth(spaces: String) = (spaces.replace("\t", "    ").length + 2) / 4

    fun parse(body: String): List<NoteBlock> {
        val blocks = mutableListOf<NoteBlock>()
        var fence: String? = null
        var language = ""
        for (line in body.split("\n")) {
            if (fence == null) {
                val m = FENCE.matchEntire(line)
                if (m != null) {
                    fence = m.groupValues[1]; language = m.groupValues[2]
                    continue
                }
            } else if (line.trim().startsWith(fence!!.take(3)) && line.trim().trim(fence!![0]).isEmpty()) {
                fence = null
                continue
            }
            if (fence != null) {
                blocks += NoteBlock(BlockKind.CODE, line, extra = language)
                language = ""
                continue
            }
            blocks += line(line)
        }
        return blocks.ifEmpty { listOf(NoteBlock()) }
    }

    /** One line outside code as a block. */
    fun line(line: String): NoteBlock {
        IMAGE.matchEntire(line)?.let { return NoteBlock(BlockKind.IMAGE, it.groupValues[1], extra = it.groupValues[2]) }
        HEADING.matchEntire(line)?.let { return NoteBlock(BlockKind.HEADING, it.groupValues[2], it.groupValues[1].length) }
        LIST_ITEM.matchEntire(line)?.let { m ->
            val (spaces, marker, box, rest) = m.destructured
            val level = depth(spaces)
            return when {
                box.isNotEmpty() -> NoteBlock(BlockKind.CHECK, rest, level, checked = box[1] in "xX")
                marker[0].isDigit() -> NoteBlock(BlockKind.NUMBERED, rest, level, number = marker.dropLast(1).toInt())
                else -> NoteBlock(BlockKind.BULLET, rest, level)
            }
        }
        QUOTE.matchEntire(line)?.let { return NoteBlock(BlockKind.QUOTE, it.groupValues[2], it.groupValues[1].count { c -> c == '>' }) }
        if (RULE.matches(line)) return NoteBlock(BlockKind.RULE)
        return NoteBlock(BlockKind.TEXT, line)
    }

    fun write(blocks: List<NoteBlock>): String {
        val lines = mutableListOf<String>()
        var inCode = false
        // Numbered items count on from the first of their run, per depth.
        val counters = mutableMapOf<Int, Int>()
        for (b in blocks) {
            if (b.kind != BlockKind.CODE && inCode) { lines += "```"; inCode = false }
            if (!b.isList) counters.clear()
            val indent = "    ".repeat(b.level.coerceAtLeast(0))
            when (b.kind) {
                BlockKind.CODE -> {
                    if (!inCode) { lines += "```" + b.extra; inCode = true }
                    lines += b.text
                }
                BlockKind.HEADING -> lines += "#".repeat(b.level.coerceIn(1, 6)) + " " + b.text
                BlockKind.BULLET -> { counters.keys.removeAll { it >= b.level }; lines += "$indent- ${b.text}" }
                BlockKind.CHECK -> {
                    counters.keys.removeAll { it >= b.level }
                    lines += "$indent- [${if (b.checked) "x" else " "}] ${b.text}"
                }
                BlockKind.NUMBERED -> {
                    counters.keys.removeAll { it > b.level }
                    val n = counters[b.level]?.plus(1) ?: b.number
                    counters[b.level] = n
                    lines += "$indent$n. ${b.text}"
                }
                BlockKind.QUOTE -> lines += "> ".repeat(b.level.coerceAtLeast(1)) + b.text
                BlockKind.IMAGE -> lines += "![${b.text}](quire-image:${b.extra})"
                BlockKind.RULE -> lines += "---"
                BlockKind.TEXT -> lines += escapeStart(b.text)
            }
        }
        if (inCode) lines += "```"
        return lines.joinToString("\n")
    }

    /** Plain text that would read as Markdown at the start of a line keeps its meaning. */
    private fun escapeStart(text: String): String {
        val looks = line(text).kind != BlockKind.TEXT || FENCE.matches(text)
        return if (looks) "\\$text" else text
    }

    // ---- editing ----------------------------------------------------------------------

    /** Typing a line prefix at the start of a plain block formats it: "# ", "- ", "1. ",
     *  "[ ] ", "> ", "```". Returns null when nothing applies. */
    fun shortcut(block: NoteBlock): NoteBlock? {
        val t = block.text
        if (block.kind == BlockKind.BULLET) {
            Regex("""^\[([ xX]?)\] (.*)$""", RegexOption.DOT_MATCHES_ALL).matchEntire(t)?.let {
                return block.copy(kind = BlockKind.CHECK, text = it.groupValues[2], checked = it.groupValues[1].isNotBlank())
            }
            return null
        }
        if (block.kind != BlockKind.TEXT) return null
        if (t.startsWith("```")) return NoteBlock(BlockKind.CODE, t.removePrefix("```").trimStart('`'))
        Regex("""^(#{1,6}) (.*)$""", RegexOption.DOT_MATCHES_ALL).matchEntire(t)?.let {
            return NoteBlock(BlockKind.HEADING, it.groupValues[2], it.groupValues[1].length)
        }
        Regex("""^(?:[-*+] )?\[([ xX]?)\] (.*)$""", RegexOption.DOT_MATCHES_ALL).matchEntire(t)?.let {
            return NoteBlock(BlockKind.CHECK, it.groupValues[2], checked = it.groupValues[1].isNotBlank())
        }
        Regex("""^[-*+] (.*)$""", RegexOption.DOT_MATCHES_ALL).matchEntire(t)?.let {
            return NoteBlock(BlockKind.BULLET, it.groupValues[1])
        }
        Regex("""^(\d+)[.)] (.*)$""", RegexOption.DOT_MATCHES_ALL).matchEntire(t)?.let {
            return NoteBlock(BlockKind.NUMBERED, it.groupValues[2], number = it.groupValues[1].toInt())
        }
        Regex("""^> (.*)$""", RegexOption.DOT_MATCHES_ALL).matchEntire(t)?.let {
            return NoteBlock(BlockKind.QUOTE, it.groupValues[1], 1)
        }
        if (t == "---" || t == "***") return NoteBlock(BlockKind.RULE)
        return null
    }

    /** Enter in block [index], with the cursor at [at]. */
    fun enter(blocks: List<NoteBlock>, index: Int, at: Int): BlockEdit {
        val b = blocks[index]
        val out = blocks.toMutableList()
        if (b.isList && b.text.isEmpty()) {
            // Enter on an empty item: out one level, or out of the list.
            out[index] = if (b.level > 0) b.copy(level = b.level - 1) else NoteBlock()
            return BlockEdit(out, index, 0)
        }
        if (b.kind == BlockKind.CODE && b.text.isEmpty() && index > 0 && blocks[index - 1].kind == BlockKind.CODE) {
            out[index] = NoteBlock()  // an empty code line leaves the code block
            return BlockEdit(out, index, 0)
        }
        val cut = at.coerceIn(0, b.text.length)
        val next = when (b.kind) {
            BlockKind.BULLET, BlockKind.NUMBERED -> b.copy(text = b.text.substring(cut), number = b.number + 1)
            BlockKind.CHECK -> b.copy(text = b.text.substring(cut), checked = false)
            BlockKind.CODE -> NoteBlock(BlockKind.CODE, b.text.substring(cut))
            BlockKind.IMAGE, BlockKind.RULE -> NoteBlock()
            else -> NoteBlock(BlockKind.TEXT, b.text.substring(cut))
        }
        if (b.kind != BlockKind.IMAGE && b.kind != BlockKind.RULE) out[index] = b.copy(text = b.text.substring(0, cut))
        out.add(index + 1, next)
        return BlockEdit(out, index + 1, 0)
    }

    /** Backspace at the very start of block [index]. */
    fun backspace(blocks: List<NoteBlock>, index: Int): BlockEdit {
        val b = blocks[index]
        val out = blocks.toMutableList()
        when {
            b.isList && b.level > 0 -> { out[index] = b.copy(level = b.level - 1); return BlockEdit(out, index, 0) }
            b.kind != BlockKind.TEXT && b.kind != BlockKind.IMAGE && b.kind != BlockKind.RULE -> {
                out[index] = NoteBlock(BlockKind.TEXT, b.text)
                return BlockEdit(out, index, 0)
            }
            index == 0 -> return BlockEdit(out, 0, 0)
        }
        val previous = blocks[index - 1]
        if (previous.kind == BlockKind.IMAGE || previous.kind == BlockKind.RULE) {
            out.removeAt(index - 1)  // backspace after a picture removes the picture
            return BlockEdit(out, index - 1, 0)
        }
        out[index - 1] = previous.copy(text = previous.text + b.text)
        out.removeAt(index)
        return BlockEdit(out, index - 1, previous.text.length)
    }

    /** Several lines arrived in one block (pasted, or scanned text): the first joins the
     *  block where the cursor was, the rest become blocks of their own. */
    fun paste(blocks: List<NoteBlock>, index: Int, before: String, lines: String, after: String): BlockEdit {
        val parts = lines.split("\n")
        val out = blocks.toMutableList()
        out[index] = blocks[index].copy(text = before + parts.first())
        val rest = parse(parts.drop(1).joinToString("\n"))
        val last = rest.last()
        val merged = rest.dropLast(1) + last.copy(text = last.text + after)
        out.addAll(index + 1, merged)
        return BlockEdit(out, index + merged.size, last.text.length)
    }

    fun toggleCheck(blocks: List<NoteBlock>, index: Int): List<NoteBlock> =
        blocks.toMutableList().also { it[index] = it[index].copy(checked = !it[index].checked) }

    /** The toolbar: make the block this kind, or back to plain text if it already is. */
    fun setKind(blocks: List<NoteBlock>, index: Int, kind: BlockKind, level: Int = 0): List<NoteBlock> {
        val b = blocks[index]
        val out = blocks.toMutableList()
        out[index] = if (b.kind == kind && (kind != BlockKind.HEADING || b.level == level)) NoteBlock(BlockKind.TEXT, b.text)
        else NoteBlock(kind, b.text, if (kind == BlockKind.HEADING || kind == BlockKind.QUOTE) level.coerceAtLeast(1)
            else if (b.isList) b.level else 0)
        return out
    }

    fun indent(blocks: List<NoteBlock>, index: Int, deeper: Boolean): List<NoteBlock> {
        val b = blocks[index]
        if (!b.isList) return blocks
        return blocks.toMutableList().also {
            it[index] = b.copy(level = (b.level + if (deeper) 1 else -1).coerceIn(0, 5))
        }
    }
}
