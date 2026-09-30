package io.github.quezka.quire.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.isShiftPressed
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import io.github.quezka.quire.R
import io.github.quezka.quire.domain.BlockEdit
import io.github.quezka.quire.domain.BlockKind
import io.github.quezka.quire.domain.Markdown
import io.github.quezka.quire.domain.NoteBlock
import io.github.quezka.quire.domain.NoteBlocks

// ---- state ------------------------------------------------------------------------------

@Stable
class EditorBlock(val id: Long, block: NoteBlock) {
    var block by mutableStateOf(block)
    var field by mutableStateOf(TextFieldValue(block.text))
    val current get() = block.copy(text = field.text)
}

/** The note being edited, as blocks (one per line of its Markdown). */
@Stable
class BlockEditorState(body: String, private val onChange: () -> Unit = {}) {
    val blocks = mutableStateListOf<EditorBlock>()
    var focused by mutableStateOf<Long?>(null)
    /** A block to move the cursor into (its id and the offset), once it's on screen. */
    var pendingFocus by mutableStateOf<Pair<Long, Int>?>(null)
    var revision by mutableIntStateOf(0)
        private set
    private var nextId = 0L

    init { load(body) }

    fun load(body: String) {
        blocks.clear()
        NoteBlocks.parse(body).forEach { blocks += EditorBlock(nextId++, it) }
    }

    fun markdown(): String = NoteBlocks.write(blocks.map { it.current })

    private fun changed() { revision++; onChange() }

    private fun indexOf(id: Long?) = blocks.indexOfFirst { it.id == id }

    /** Make the list match [edit], keeping the blocks that didn't change (and their focus). */
    fun apply(edit: BlockEdit) {
        val old = blocks.map { it.current }
        val new = edit.blocks
        var prefix = 0
        while (prefix < old.size && prefix < new.size && old[prefix] == new[prefix] && prefix != edit.focus) prefix++
        var suffix = 0
        while (suffix < old.size - prefix && suffix < new.size - prefix &&
            old[old.size - 1 - suffix] == new[new.size - 1 - suffix] && new.size - 1 - suffix != edit.focus) suffix++
        val reusable = blocks.subList(prefix, blocks.size - suffix).toMutableList()
        val middle = new.subList(prefix, new.size - suffix).map { b ->
            val reuse = reusable.removeFirstOrNull()
            (reuse ?: EditorBlock(nextId++, b)).also { it.block = b; it.field = TextFieldValue(b.text) }
        }
        for (i in (blocks.size - suffix - 1) downTo prefix) blocks.removeAt(i)
        blocks.addAll(prefix, middle)
        val target = blocks.getOrNull(edit.focus)
        if (target != null) {
            target.field = TextFieldValue(target.field.text, TextRange(edit.cursor.coerceIn(0, target.field.text.length)))
            pendingFocus = target.id to edit.cursor
        }
        changed()
    }

    fun typed(index: Int, value: TextFieldValue) {
        val block = blocks[index]
        val old = block.field.text
        if ('\n' in value.text) {
            val all = blocks.map { it.current }
            val cut = value.text.indexOf('\n')
            if (value.text.count { it == '\n' } == 1 && value.text.removeRange(cut, cut + 1) == old) {
                apply(NoteBlocks.enter(all.toMutableList().also { it[index] = block.current }, index, cut))
            } else {
                // Pasted lines: the text before the paste stays, what followed the cursor ends up
                // after the last pasted line.
                val start = commonPrefix(old, value.text)
                val end = old.length - commonSuffix(old.substring(start), value.text.substring(start))
                val inserted = value.text.substring(start, value.text.length - (old.length - end))
                apply(NoteBlocks.paste(all, index, old.substring(0, start), inserted, old.substring(end)))
            }
            return
        }
        if (value.text == old) { block.field = value; return }
        val shortcut = NoteBlocks.shortcut(block.block.copy(text = value.text))
        if (shortcut != null) {
            val removed = value.text.length - shortcut.text.length
            block.block = shortcut
            block.field = TextFieldValue(shortcut.text, TextRange((value.selection.start - removed).coerceIn(0, shortcut.text.length)))
        } else {
            block.field = value
        }
        changed()
    }

    fun backspace(index: Int) = apply(NoteBlocks.backspace(blocks.map { it.current }, index))

    fun toggleCheck(index: Int) {
        blocks[index].block = blocks[index].block.copy(checked = !blocks[index].block.checked)
        changed()
    }

    fun remove(index: Int) {
        val all = blocks.map { it.current }.toMutableList()
        all.removeAt(index)
        if (all.isEmpty()) all += NoteBlock()
        apply(BlockEdit(all, (index - 1).coerceAtLeast(0), all[(index - 1).coerceAtLeast(0)].text.length))
    }

    // ---- the toolbar -------------------------------------------------------------------

    private fun focusedIndex() = indexOf(focused).takeIf { it >= 0 } ?: (blocks.size - 1)

    fun setKind(kind: BlockKind, level: Int = 0) {
        val i = focusedIndex()
        val cursor = blocks[i].field.selection.start
        apply(BlockEdit(NoteBlocks.setKind(blocks.map { it.current }, i, kind, level), i, cursor))
    }

    fun indent(deeper: Boolean) {
        val i = focusedIndex()
        val cursor = blocks[i].field.selection.start
        apply(BlockEdit(NoteBlocks.indent(blocks.map { it.current }, i, deeper), i, cursor))
    }

    fun wrap(marker: String, placeholder: String) {
        val i = focusedIndex()
        val block = blocks[i]
        if (block.block.kind == BlockKind.IMAGE || block.block.kind == BlockKind.RULE) return
        val f = block.field
        val (text, s, e) = Markdown.wrap(f.text, f.selection.min, f.selection.max, marker, placeholder)
        block.field = TextFieldValue(text, TextRange(s, e))
        pendingFocus = block.id to s
        changed()
    }

    /** Scanned text goes where the cursor is, as lines of its own. */
    fun insertText(text: String) {
        val i = focusedIndex()
        val block = blocks[i]
        val at = block.field.selection.end.coerceIn(0, block.field.text.length)
        val before = block.field.text.substring(0, at)
        val after = block.field.text.substring(at)
        val lines = (if (before.isBlank()) "" else "\n") + text.trimEnd('\n') + (if (after.isBlank()) "" else "\n")
        apply(NoteBlocks.paste(blocks.map { it.current }, i, before, lines, after))
    }

    val words get() = blocks.sumOf { b ->
        if (b.block.kind == BlockKind.IMAGE) 0 else b.field.text.split(Regex("\\s+")).count { it.isNotBlank() }
    }

    val empty get() = blocks.size == 1 && blocks[0].field.text.isEmpty() && blocks[0].block.kind == BlockKind.TEXT

    companion object {
        private fun commonPrefix(a: String, b: String): Int {
            var i = 0
            while (i < a.length && i < b.length && a[i] == b[i]) i++
            return i
        }
        private fun commonSuffix(a: String, b: String): Int {
            var i = 0
            while (i < a.length && i < b.length && a[a.length - 1 - i] == b[b.length - 1 - i]) i++
            return i
        }
    }
}

/** Display numbers for numbered items, counting on within each run and depth. */
private fun numbers(blocks: List<NoteBlock>): IntArray {
    val out = IntArray(blocks.size)
    val counters = mutableMapOf<Int, Int>()
    blocks.forEachIndexed { i, b ->
        if (!b.isList) counters.clear()
        when (b.kind) {
            BlockKind.NUMBERED -> {
                counters.keys.removeAll { it > b.level }
                val n = counters[b.level]?.plus(1) ?: b.number
                counters[b.level] = n
                out[i] = n
            }
            BlockKind.BULLET, BlockKind.CHECK -> counters.keys.removeAll { it >= b.level }
            else -> Unit
        }
    }
    return out
}

// ---- inline Markdown: faded marks while editing a line, hidden otherwise --------------------

private val INLINE = Regex(
    """(`[^`\n]+`)""" +
        """|\*\*\*((?=\S)[^*]+?(?<=\S))\*\*\*""" +
        """|\*\*((?=\S).+?(?<=\S))\*\*|__((?=\S).+?(?<=\S))__""" +
        """|~~((?=\S).+?(?<=\S))~~""" +
        """|(?<![*\w\\])\*((?=[^\s*]).+?(?<=[^\s*]))\*(?!\*)""" +
        """|(?<![\w\\])_((?=\S).+?(?<=\S))_(?!\w)""" +
        """|\[([^\]\n]+)\]\(([^)\s]+)\)""" +
        """|\\([\\`*_{}\[\]()#+\-.!~>|])""")

private class InlineStyler(private val source: String, private val hide: Boolean,
                           private val accent: Color, private val faint: Color, private val codeBg: Color) {
    val builder = AnnotatedString.Builder()
    val toTransformed = IntArray(source.length + 1)
    val toOriginal = ArrayList<Int>(source.length + 1)

    private fun show(from: Int, to: Int, style: SpanStyle?) {
        val start = builder.length
        for (k in from until to) { toTransformed[k] = builder.length; toOriginal += k }
        builder.append(source.substring(from, to))
        if (style != null && to > from) builder.addStyle(style, start, builder.length)
    }

    private fun mark(from: Int, to: Int) {
        if (hide) for (k in from until to) toTransformed[k] = builder.length
        else show(from, to, SpanStyle(color = faint))
    }

    fun run(from: Int = 0, to: Int = source.length, styles: List<SpanStyle> = emptyList()) {
        var pos = from
        val merged = styles.fold(SpanStyle()) { a, b -> a.merge(b) }
        for (m in INLINE.findAll(source.subSequence(0, to), from)) {
            if (m.range.first < pos) continue
            show(pos, m.range.first, merged.takeIf { styles.isNotEmpty() })
            val g = m.groups
            val s = m.range.first
            val e = m.range.last + 1
            when {
                g[1] != null -> {
                    mark(s, s + 1)
                    show(s + 1, e - 1, merged.merge(SpanStyle(fontFamily = FontFamily.Monospace, color = accent, background = codeBg)))
                    mark(e - 1, e)
                }
                g[10] != null -> { mark(s, s + 1); show(s + 1, e, merged) }  // an escaped character
                g[8] != null -> {
                    val text = g[8]!!.range
                    mark(s, text.first)
                    run(text.first, text.last + 1, styles + SpanStyle(color = accent, textDecoration = TextDecoration.Underline))
                    mark(text.last + 1, e)
                }
                else -> {
                    val (index, style) = when {
                        g[2] != null -> 2 to SpanStyle(fontWeight = FontWeight.Bold, fontStyle = FontStyle.Italic)
                        g[3] != null -> 3 to SpanStyle(fontWeight = FontWeight.Bold)
                        g[4] != null -> 4 to SpanStyle(fontWeight = FontWeight.Bold)
                        g[5] != null -> 5 to SpanStyle(textDecoration = TextDecoration.LineThrough)
                        g[6] != null -> 6 to SpanStyle(fontStyle = FontStyle.Italic)
                        else -> 7 to SpanStyle(fontStyle = FontStyle.Italic)
                    }
                    val inner = g[index]!!.range
                    mark(s, inner.first)
                    run(inner.first, inner.last + 1, styles + style)
                    mark(inner.last + 1, e)
                }
            }
            pos = e
        }
        show(pos, to, merged.takeIf { styles.isNotEmpty() })
    }

    fun transformed(): TransformedText {
        run()
        toTransformed[source.length] = builder.length
        toOriginal += source.length
        val text = builder.toAnnotatedString()
        return TransformedText(text, object : OffsetMapping {
            override fun originalToTransformed(offset: Int) = toTransformed[offset.coerceIn(0, source.length)]
            override fun transformedToOriginal(offset: Int) = toOriginal[offset.coerceIn(0, toOriginal.size - 1)]
        })
    }
}

private class InlineMarkdown(val hide: Boolean, val accent: Color, val faint: Color, val codeBg: Color) : VisualTransformation {
    override fun filter(text: AnnotatedString) = InlineStyler(text.text, hide, accent, faint, codeBg).transformed()
    override fun equals(other: Any?) = other is InlineMarkdown && other.hide == hide && other.accent == accent && other.faint == faint
    override fun hashCode() = (if (hide) 1 else 0) * 31 + accent.hashCode()
}

// ---- the editor --------------------------------------------------------------------------

@Composable
fun BlockEditor(state: BlockEditorState, image: (String) -> ByteArray?, placeholder: String,
                modifier: Modifier = Modifier) {
    val c = MaterialTheme.colorScheme
    val type = MaterialTheme.typography
    val faint = c.onSurfaceVariant.copy(alpha = 0.5f)
    val editing = remember(c) { InlineMarkdown(false, c.primary, faint, c.surfaceVariant) }
    val reading = remember(c) { InlineMarkdown(true, c.primary, faint, c.surfaceVariant) }
    val numbers = numbers(state.blocks.map { it.block })
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        state.blocks.forEachIndexed { index, eb ->
            key(eb.id) {
                val requester = remember { FocusRequester() }
                val b = eb.block
                val selected = state.focused == eb.id
                LaunchedEffect(state.pendingFocus) {
                    val pending = state.pendingFocus
                    if (pending != null && pending.first == eb.id) {
                        runCatching { requester.requestFocus() }
                        state.pendingFocus = null
                    }
                }
                when (b.kind) {
                    BlockKind.IMAGE -> Box(Modifier.fillMaxWidth()
                        .clickable { state.focused = eb.id }
                        .then(if (selected) Modifier.border(2.dp, c.primary, RoundedCornerShape(8.dp)) else Modifier)) {
                        NotePicture(b.extra, b.text, image)
                        if (selected) IconButton(onClick = { state.remove(index) },
                            modifier = Modifier.align(Alignment.TopEnd).padding(4.dp)
                                .background(c.surface.copy(alpha = 0.85f), RoundedCornerShape(50))) {
                            Icon(Icons.Filled.Delete, stringResource(R.string.remove_picture))
                        }
                    }
                    BlockKind.RULE -> Box(Modifier.fillMaxWidth().heightIn(min = 20.dp)
                        .clickable { state.focused = eb.id }, contentAlignment = Alignment.Center) {
                        HorizontalDivider(color = if (selected) c.primary else c.outlineVariant)
                    }
                    else -> {
                        val style: TextStyle = when (b.kind) {
                            BlockKind.HEADING -> when (b.level) { 1 -> type.headlineSmall; 2 -> type.titleLarge; else -> type.titleMedium }
                                .copy(fontWeight = FontWeight.Bold)
                            BlockKind.QUOTE -> type.bodyLarge.copy(fontStyle = FontStyle.Italic, color = c.onSurfaceVariant)
                            BlockKind.CODE -> type.bodyMedium.copy(fontFamily = FontFamily.Monospace)
                            BlockKind.CHECK -> if (b.checked) type.bodyLarge.copy(color = c.onSurfaceVariant,
                                textDecoration = TextDecoration.LineThrough) else type.bodyLarge
                            else -> type.bodyLarge
                        }.let { if (it.color == Color.Unspecified) it.copy(color = c.onSurface) else it }
                        Row(Modifier.fillMaxWidth()
                            .padding(top = if (b.kind == BlockKind.HEADING && index > 0) 10.dp else 0.dp)
                            .then(if (b.kind == BlockKind.CODE) Modifier.background(c.surfaceVariant, RoundedCornerShape(4.dp)).padding(horizontal = 8.dp) else Modifier),
                            verticalAlignment = Alignment.Top) {
                            Gutter(b, numbers[index], style) { state.toggleCheck(index) }
                            BasicTextField(
                                value = eb.field,
                                onValueChange = { state.typed(index, it) },
                                textStyle = style,
                                cursorBrush = SolidColor(c.primary),
                                visualTransformation = when {
                                    b.kind == BlockKind.CODE -> VisualTransformation.None
                                    selected -> editing  // the line being edited shows its marks, faded
                                    else -> reading
                                },
                                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                                modifier = Modifier.weight(1f)
                                    .focusRequester(requester)
                                    .onFocusChanged { if (it.isFocused) state.focused = eb.id }
                                    .onPreviewKeyEvent { e ->
                                        if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                                        val sel = eb.field.selection
                                        when {
                                            e.key == Key.Backspace && sel.collapsed && sel.start == 0 -> { state.backspace(index); true }
                                            e.key == Key.Tab && b.isList -> { state.indent(!e.isShiftPressed); true }
                                            else -> false
                                        }
                                    },
                                decorationBox = { inner ->
                                    Box {
                                        if (state.empty && index == 0) Text(placeholder, style = style.copy(color = faint))
                                        inner()
                                    }
                                },
                            )
                        }
                    }
                }
            }
        }
        // Tapping below the note carries on writing at its end.
        Spacer(Modifier.fillMaxWidth().height(160.dp).clickable(
            interactionSource = remember { MutableInteractionSource() }, indication = null) {
            val last = state.blocks.last()
            if (last.block.kind == BlockKind.IMAGE || last.block.kind == BlockKind.RULE || last.block.kind == BlockKind.CODE) {
                state.apply(BlockEdit(state.blocks.map { it.current } + NoteBlock(), state.blocks.size, 0))
            } else {
                last.field = last.field.copy(selection = TextRange(last.field.text.length))
                state.pendingFocus = last.id to last.field.text.length
            }
        })
    }
}

@Composable
private fun Gutter(b: NoteBlock, number: Int, style: TextStyle, toggle: () -> Unit) {
    val c = MaterialTheme.colorScheme
    val indent = (b.level * 22).dp
    when (b.kind) {
        BlockKind.BULLET -> Row {
            Spacer(Modifier.width(indent))
            Text(listOf("•", "◦", "▪")[b.level % 3], style = style, color = c.primary,
                fontWeight = FontWeight.Bold, modifier = Modifier.width(22.dp))
        }
        BlockKind.NUMBERED -> Row {
            Spacer(Modifier.width(indent))
            Text("$number.", style = style, color = c.primary, fontWeight = FontWeight.Bold,
                modifier = Modifier.width(30.dp))
        }
        BlockKind.CHECK -> Row(verticalAlignment = Alignment.CenterVertically) {
            Spacer(Modifier.width(indent))
            Checkbox(b.checked, { toggle() }, Modifier.size(28.dp).padding(end = 4.dp))
            Spacer(Modifier.width(6.dp))
        }
        BlockKind.QUOTE -> Row {
            repeat(b.level.coerceAtLeast(1)) {
                Box(Modifier.padding(end = 8.dp).width(3.dp).height(24.dp).background(c.primary.copy(alpha = 0.5f)))
            }
        }
        else -> Unit
    }
}
