package io.github.quezka.quire.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em

private val HEADING = Regex("""^(#{1,6})\s+.*$""")
private val LIST_ITEM = Regex("""^(\s*)([-*+]|\d+[.)])(\s+)(\[[ xX]\]\s+)?""")
private val INLINE = listOf(
    Regex("""\*\*(?=\S)(.+?)(?<=\S)\*\*""") to "bold",
    Regex("""(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?!\*)""") to "italic",
    Regex("""~~(?=\S)(.+?)(?<=\S)~~""") to "strike",
    Regex("""`[^`\n]+`""") to "code",
    Regex("""\[[^\]\n]+\]\([^)\s]+\)|https?://\S+""") to "link",
)
private val HEADING_SIZE = mapOf(1 to 1.45f, 2 to 1.3f, 3 to 1.15f, 4 to 1.05f, 5 to 1f, 6 to 1f)

private data class Palette(val accent: Color, val faint: Color, val muted: Color, val codeBg: Color)

/** Styles Markdown in the editor while keeping every character where it is (the marks
 *  stay, faded), like the desktop's editor. */
class MarkdownStyling(private val accent: Color, private val faint: Color, private val muted: Color,
                      private val codeBg: Color) : VisualTransformation {
    override fun filter(text: AnnotatedString): TransformedText =
        TransformedText(style(text.text, Palette(accent, faint, muted, codeBg)), OffsetMapping.Identity)

    override fun equals(other: Any?) = other is MarkdownStyling && other.accent == accent && other.faint == faint
    override fun hashCode() = accent.hashCode() * 31 + faint.hashCode()
}

private fun style(text: String, p: Palette): AnnotatedString = buildAnnotatedString {
    append(text)
    var offset = 0
    var inCode = false
    for (line in text.split('\n')) {
        val start = offset
        val end = offset + line.length
        offset = end + 1
        if (line.trimStart().startsWith("```")) {
            addStyle(SpanStyle(color = p.faint, fontFamily = FontFamily.Monospace), start, end)
            inCode = !inCode
            continue
        }
        if (inCode) { addStyle(SpanStyle(fontFamily = FontFamily.Monospace, background = p.codeBg), start, end); continue }
        HEADING.find(line)?.let { m ->
            val level = m.groupValues[1].length
            addStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = HEADING_SIZE.getValue(level).em), start, end)
            addStyle(SpanStyle(color = p.faint), start, start + level)
            return@let
        } ?: run {
            if (line.trimStart().startsWith(">")) addStyle(SpanStyle(color = p.muted, fontStyle = FontStyle.Italic), start, end)
            LIST_ITEM.find(line)?.let { m ->
                val marker = m.groups[2]!!.range
                addStyle(SpanStyle(color = p.accent, fontWeight = FontWeight.Bold), start + marker.first, start + marker.last + 1)
                m.groups[4]?.let { box ->
                    addStyle(SpanStyle(color = p.accent, fontWeight = FontWeight.Bold), start + box.range.first, start + box.range.first + 3)
                    if (box.value[1] in "xX") addStyle(SpanStyle(color = p.faint, textDecoration = TextDecoration.LineThrough),
                        start + box.range.last + 1, end)
                }
            }
            for ((regex, kind) in INLINE) for (m in regex.findAll(line)) {
                val s = start + m.range.first
                val e = start + m.range.last + 1
                when (kind) {
                    "bold" -> { addStyle(SpanStyle(fontWeight = FontWeight.Bold), s, e); fade(s, e, 2, p) }
                    "italic" -> { addStyle(SpanStyle(fontStyle = FontStyle.Italic), s, e); fade(s, e, 1, p) }
                    "strike" -> { addStyle(SpanStyle(textDecoration = TextDecoration.LineThrough, color = p.muted), s, e); fade(s, e, 2, p) }
                    "code" -> addStyle(SpanStyle(fontFamily = FontFamily.Monospace, color = p.accent, background = p.codeBg), s, e)
                    else -> addStyle(SpanStyle(color = p.accent), s, e)
                }
            }
        }
    }
}

private fun AnnotatedString.Builder.fade(s: Int, e: Int, n: Int, p: Palette) {
    addStyle(SpanStyle(color = p.faint), s, s + n)
    addStyle(SpanStyle(color = p.faint), e - n, e)
}

@Composable
fun markdownStyling(): MarkdownStyling {
    val c = MaterialTheme.colorScheme
    return MarkdownStyling(c.primary, c.onSurfaceVariant.copy(alpha = 0.5f), c.onSurfaceVariant, c.surfaceVariant)
}

/** Inline Markdown as styled text, with the marks removed (for the preview). */
@Composable
private fun inline(text: String): AnnotatedString {
    val c = MaterialTheme.colorScheme
    return buildAnnotatedString {
        var rest = text
        val pattern = Regex("""\*\*(.+?)\*\*|(?<![*\w])\*([^*\s][^*]*?)\*|~~(.+?)~~|`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)""")
        while (true) {
            val m = pattern.find(rest) ?: break
            append(rest.substring(0, m.range.first))
            val (bold, italic, strike, code, linkText) = m.destructured
            when {
                bold.isNotEmpty() -> { pushStyle(SpanStyle(fontWeight = FontWeight.Bold)); append(bold); pop() }
                italic.isNotEmpty() -> { pushStyle(SpanStyle(fontStyle = FontStyle.Italic)); append(italic); pop() }
                strike.isNotEmpty() -> { pushStyle(SpanStyle(textDecoration = TextDecoration.LineThrough)); append(strike); pop() }
                code.isNotEmpty() -> { pushStyle(SpanStyle(fontFamily = FontFamily.Monospace, color = c.primary, background = c.surfaceVariant)); append(code); pop() }
                linkText.isNotEmpty() -> { pushStyle(SpanStyle(color = c.primary, textDecoration = TextDecoration.Underline)); append(linkText); pop() }
            }
            rest = rest.substring(m.range.last + 1)
        }
        append(rest)
    }
}

/** The note rendered for reading; tapping a checkbox ticks it ([onToggle] gets the line). */
@Composable
fun MarkdownPreview(body: String, onToggle: (Int) -> Unit, modifier: Modifier = Modifier) {
    val c = MaterialTheme.colorScheme
    val type = MaterialTheme.typography
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        val lines = body.lines()
        var i = 0
        while (i < lines.size) {
            val line = lines[i]
            val index = i
            when {
                line.trimStart().startsWith("```") -> {
                    val code = mutableListOf<String>()
                    i++
                    while (i < lines.size && !lines[i].trimStart().startsWith("```")) code += lines[i++]
                    Box(Modifier.fillMaxWidth().background(c.surfaceVariant, RoundedCornerShape(8.dp)).padding(10.dp)) {
                        Text(code.joinToString("\n"), fontFamily = FontFamily.Monospace, style = type.bodyMedium)
                    }
                }
                HEADING.matches(line) -> {
                    val level = line.takeWhile { it == '#' }.length
                    Text(inline(line.drop(level).trim()), fontWeight = FontWeight.Bold,
                        style = when (level) { 1 -> type.headlineSmall; 2 -> type.titleLarge; else -> type.titleMedium },
                        modifier = Modifier.padding(top = if (index == 0) 0.dp else 8.dp))
                }
                line.isBlank() -> Spacer(Modifier.height(6.dp))
                line.trimStart().startsWith(">") -> Row {
                    Box(Modifier.width(3.dp).height(22.dp).background(c.primary.copy(alpha = 0.5f)))
                    Spacer(Modifier.width(10.dp))
                    Text(inline(line.trimStart().removePrefix(">").trim()), fontStyle = FontStyle.Italic, color = c.onSurfaceVariant)
                }
                else -> {
                    val m = LIST_ITEM.find(line)
                    if (m == null) Text(inline(line), style = type.bodyLarge)
                    else {
                        val depth = m.groupValues[1].replace("\t", "    ").length / 2
                        val box = m.groups[4]?.value
                        val rest = line.substring(m.range.last + 1)
                        Row(Modifier.padding(start = (depth * 12).dp), verticalAlignment = Alignment.CenterVertically) {
                            if (box != null) {
                                val done = box[1] in "xX"
                                Checkbox(done, { onToggle(index) }, Modifier.height(28.dp))
                                Text(inline(rest), style = type.bodyLarge,
                                    color = if (done) c.onSurfaceVariant else c.onSurface,
                                    textDecoration = if (done) TextDecoration.LineThrough else null,
                                    modifier = Modifier.clickable { onToggle(index) })
                            } else {
                                val marker = m.groupValues[2]
                                Text(if (marker.first().isDigit()) marker else "•", color = c.primary,
                                    fontWeight = FontWeight.Bold, modifier = Modifier.width(22.dp))
                                Text(inline(rest), style = type.bodyLarge)
                            }
                        }
                    }
                }
            }
            i++
        }
    }
}
