"""The note editor: you write straight into the formatted note, pictures included.

Notes are stored as Markdown, one line per block, the same way the phone reads and writes
them: a heading line is a heading block, a list line a list item, a picture line a picture,
a blank line an empty block. Loading turns lines into formatted blocks; saving turns each
block back into its line, so notes round-trip exactly.

Markdown typed by habit still works: "# " makes a heading, "- " a list, "1. " a numbered
list, "[ ] " a checklist, "> " a quote, ``` a code block, and **bold**, *italic*, `code` and
~~struck~~ turn into formatting as you close them.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QKeySequence, QPainter, QTextBlockFormat, QTextCharFormat,
    QTextCursor, QTextDocument, QTextFormat, QTextImageFormat, QTextListFormat,
)
from PySide6.QtWidgets import QTextEdit

from . import theme

P = QTextFormat.Property
SCHEME = "quire-image"
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?(.*)$")
QUOTE = re.compile(r"^\s*((?:>\s?)+)(.*)$")
FENCE = re.compile(r"^\s*(```+|~~~+)\s*([\w+#.-]*)\s*$")
IMAGE_LINE = re.compile(r"^\s*!\[([^\]\n]*)\]\(([^)\s]+)\)\s*$")
RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
HEADING_SIZE = {1: 3, 2: 2, 3: 1, 4: 0, 5: 0, 6: 0}  # QTextFormat.FontSizeAdjustment
BULLETS = (QTextListFormat.ListDisc, QTextListFormat.ListCircle, QTextListFormat.ListSquare)
SOFT = QColor(128, 128, 128, 38)  # code backgrounds: reads on light and dark
DONE = QColor(128, 128, 128)  # ticked checklist items

SHORTCUTS = {
    "bold": QKeySequence("Ctrl+B"), "italic": QKeySequence("Ctrl+I"),
    "list": QKeySequence("Ctrl+Shift+8"), "checklist": QKeySequence("Ctrl+Shift+L"),
    "code": QKeySequence("Ctrl+`"),
}

# Inline Markdown, earliest match wins: **bold**, __bold__, *italic*, _italic_, ~~struck~~,
# `code`, [text](link).
INLINE = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|\*\*\*(?P<bi>(?=\S)[^*]+?(?<=\S))\*\*\*"
    r"|\*\*(?P<b1>(?=\S).+?(?<=\S))\*\*|__(?P<b2>(?=\S).+?(?<=\S))__"
    r"|~~(?P<s>(?=\S).+?(?<=\S))~~"
    r"|(?<![*\w\\])\*(?P<i1>(?=[^\s*]).+?(?<=[^\s*]))\*(?!\*)"
    r"|(?<![\w\\])_(?P<i2>(?=\S).+?(?<=\S))_(?!\w)"
    r"|\[(?P<lt>[^\]\n]+)\]\((?P<lu>[^)\s]+)\)"
    r"|\\(?P<esc>[\\`*_{}\[\]()#+\-.!~>|])")


def escape(text: str) -> str:
    """Backslashes only where plain text would otherwise read as formatting."""
    text = re.sub(r"\\(?=[\\`*_{}\[\]()#+\-.!~>|])", r"\\\\", text)
    out, pos = [], 0
    while True:
        m = INLINE.search(text, pos)
        while m is not None and m.group("esc") is not None:
            m = INLINE.search(text, m.end())
        if m is None:
            out.append(text[pos:])
            return "".join(out)
        out.append(text[pos:m.start()] + "\\" + text[m.start()])
        pos = m.start() + 1

# ---- formats -----------------------------------------------------------------------------


def _mono(fmt: QTextCharFormat):
    fmt.setFontFamilies(["JetBrains Mono", "DejaVu Sans Mono", "Consolas", "monospace"])
    fmt.setFontFixedPitch(True)


def is_code(fmt: QTextCharFormat) -> bool:
    return fmt.fontFixedPitch()


def plain_block() -> QTextBlockFormat:
    fmt = QTextBlockFormat()
    fmt.setBottomMargin(3)
    return fmt


def plain_char() -> QTextCharFormat:
    return QTextCharFormat()


def heading_formats(level: int) -> tuple[QTextBlockFormat, QTextCharFormat]:
    block = plain_block()
    block.setHeadingLevel(level)
    block.setTopMargin(10 if level <= 2 else 6)
    block.setBottomMargin(4)
    char = QTextCharFormat()
    char.setFontWeight(QFont.Bold)
    char.setProperty(P.FontSizeAdjustment, HEADING_SIZE[level])
    return block, char


def quote_formats(level: int) -> tuple[QTextBlockFormat, QTextCharFormat]:
    block = plain_block()
    block.setProperty(P.BlockQuoteLevel, level)
    block.setLeftMargin(18 * level)
    char = QTextCharFormat()
    char.setFontItalic(True)
    return block, char


def code_formats(language: str = "") -> tuple[QTextBlockFormat, QTextCharFormat]:
    block = QTextBlockFormat()
    block.setProperty(P.BlockCodeFence, "`")
    if language:
        block.setProperty(P.BlockCodeLanguage, language)
    block.setNonBreakableLines(True)
    block.setBackground(SOFT)
    block.setLeftMargin(6)
    char = QTextCharFormat()
    _mono(char)
    return block, char


def rule_format() -> QTextBlockFormat:
    block = plain_block()
    block.setProperty(P.BlockTrailingHorizontalRulerWidth, 1)
    return block


def block_kind(block) -> str:
    fmt = block.blockFormat()
    if block.textList() is not None:
        return "list"
    if fmt.hasProperty(P.BlockCodeFence):
        return "code"
    if fmt.headingLevel():
        return "heading"
    if fmt.hasProperty(P.BlockQuoteLevel) and fmt.intProperty(P.BlockQuoteLevel):
        return "quote"
    if fmt.hasProperty(P.BlockTrailingHorizontalRulerWidth):
        return "rule"
    return "text"


def _list_level(spaces: str) -> int:
    width = len(spaces.replace("\t", "    "))
    return 1 + (width + 2) // 4


# ---- Markdown -> document ---------------------------------------------------------------

def insert_inline(cursor: QTextCursor, text: str, base: QTextCharFormat):
    """Insert a line's text with its inline Markdown turned into formatting."""
    pos = 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            cursor.insertText(text[pos:m.start()], base)
        fmt = QTextCharFormat(base)
        if m.group("code"):
            _mono(fmt)
            fmt.setBackground(SOFT)
            cursor.insertText(m.group("code")[1:-1], fmt)
        elif m.group("esc") is not None:
            cursor.insertText(m.group("esc"), base)
        elif m.group("lt") is not None:
            fmt.setAnchor(True)
            fmt.setAnchorHref(m.group("lu"))
            fmt.setFontUnderline(True)
            fmt.setForeground(QColor(theme.current().accent))
            insert_inline(cursor, m.group("lt"), fmt)
        else:
            inner = m.group("b1") or m.group("b2")
            if m.group("bi") is not None:
                inner = m.group("bi")
                fmt.setFontWeight(QFont.Bold)
                fmt.setFontItalic(True)
            elif inner is not None:
                fmt.setFontWeight(QFont.Bold)
            elif m.group("s") is not None:
                inner = m.group("s")
                fmt.setFontStrikeOut(True)
            else:
                inner = m.group("i1") or m.group("i2")
                fmt.setFontItalic(True)
            insert_inline(cursor, inner, fmt)
        pos = m.end()
    if pos < len(text):
        cursor.insertText(text[pos:], base)


def load_markdown(document: QTextDocument, body: str):
    """Fill the document from Markdown, one block per line."""
    document.clear()
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    lists: dict[int, object] = {}  # level -> QTextList, for the list being written
    fence = None
    language = ""
    first = True
    for line in body.split("\n"):
        if fence is None:
            m = FENCE.match(line)
            if m:
                fence, language = m.group(1), m.group(2)
                continue
        elif line.strip().startswith(fence[:3]) and not line.strip().strip(fence[0]):
            fence = None
            continue
        if not first:
            cursor.insertBlock(plain_block(), plain_char())
        first = False
        if fence is not None:
            block, char = code_formats(language)
            language = ""
            cursor.setBlockFormat(block)
            cursor.insertText(line, char)
            lists.clear()
            continue
        item = LIST_ITEM.match(line)
        if item is None:
            lists.clear()
        if (m := IMAGE_LINE.match(line)) and m.group(2).startswith(f"{SCHEME}:"):
            cursor.setBlockFormat(plain_block())
            insert_picture_at(cursor, m.group(2), m.group(1))
        elif m := HEADING.match(line):
            block, char = heading_formats(len(m.group(1)))
            cursor.setBlockFormat(block)
            insert_inline(cursor, m.group(2), char)
        elif item is not None:
            spaces, marker, box, rest = item.groups()
            level = _list_level(spaces)
            numbered = marker[0].isdigit()
            for deeper in [lv for lv in lists if lv > level]:
                del lists[deeper]
            current = lists.get(level)
            style = QTextListFormat.ListDecimal if numbered else BULLETS[(level - 1) % 3]
            if current is None or current.format().style() != style:
                fmt = QTextListFormat()
                fmt.setStyle(style)
                fmt.setIndent(level)
                if numbered:
                    fmt.setStart(int(marker[:-1]))
                current = cursor.createList(fmt)
                lists[level] = current
            else:
                current.add(cursor.block())
            block = cursor.blockFormat()
            char = QTextCharFormat()
            if box:
                done = box[1] in "xX"
                block.setMarker(QTextBlockFormat.MarkerType.Checked if done
                                else QTextBlockFormat.MarkerType.Unchecked)
                if done:
                    char.setForeground(DONE)
            cursor.setBlockFormat(block)
            insert_inline(cursor, rest, char)
        elif m := QUOTE.match(line):
            block, char = quote_formats(m.group(1).count(">"))
            cursor.setBlockFormat(block)
            insert_inline(cursor, m.group(2), char)
        elif RULE.match(line):
            cursor.setBlockFormat(rule_format())
        else:
            cursor.setBlockFormat(plain_block())
            insert_inline(cursor, line, plain_char())
    cursor.endEditBlock()
    document.clearUndoRedoStacks()


def insert_picture_at(cursor: QTextCursor, name: str, alt: str = ""):
    fmt = QTextImageFormat()
    fmt.setName(name)
    fmt.setProperty(P.ImageAltText, alt)
    cursor.insertImage(fmt)


# ---- document -> Markdown -------------------------------------------------------------------

def _marks(fmt: QTextCharFormat) -> list[str]:
    """The Markdown marks a run of text carries, outermost first."""
    marks = []
    if fmt.isAnchor() and fmt.anchorHref():
        marks.append("link:" + fmt.anchorHref())
    if fmt.fontWeight() >= QFont.DemiBold:
        marks.append("**")
    if fmt.fontItalic():
        marks.append("*")
    if fmt.fontStrikeOut():
        marks.append("~~")
    return marks


def _open(mark: str) -> str:
    return "[" if mark.startswith("link:") else mark


def _close(mark: str) -> str:
    return f"]({mark[5:]})" if mark.startswith("link:") else mark


def block_markdown(block, heading_or_quote: bool = False) -> str:
    """A block's text as inline Markdown. Formatting that the whole block carries by its
    kind (headings are bold, quotes italic) isn't repeated as marks."""
    kind = block_kind(block)
    runs: list[tuple[str, list[str] | None, str]] = []  # (text, marks, special)
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        fmt = fragment.charFormat()
        if fmt.isImageFormat():
            image = fmt.toImageFormat()
            alt = str(image.property(P.ImageAltText) or "")
            runs.append((f"![{alt}]({image.name()})", None, "raw"))
        elif is_code(fmt):
            text = fragment.text().replace(" ", " ")
            ticks = "``" if "`" in text else "`"
            pad = " " if ticks == "``" else ""
            runs.append((f"{ticks}{pad}{text}{pad}{ticks}", None, "raw"))
        else:
            marks = _marks(fmt)
            if kind == "heading" and "**" in marks:
                marks.remove("**")
            if kind == "quote" and "*" in marks:
                marks.remove("*")
            runs.append((fragment.text().replace(" ", " "), marks, "text"))
        it += 1

    # Whitespace at the edges of a run goes outside its marks ("**bold** text").
    tokens: list[tuple[str, list[str] | None]] = []
    for text, marks, special in runs:
        if special == "raw":
            tokens.append((text, None))
            continue
        core = text.strip(" ")
        lead = text[:len(text) - len(text.lstrip(" "))]
        trail = text[len(text.rstrip(" ")):] if core else ""
        if lead:
            tokens.append((lead, "space"))
        if core:
            tokens.append((escape(core), marks))
        if trail:
            tokens.append((trail, "space"))
    out, open_marks = [], []
    for index, (text, marks) in enumerate(tokens):
        if marks == "space":
            out.append(text)
            continue
        wanted = marks or []
        common = 0
        while common < min(len(open_marks), len(wanted)) and open_marks[common] == wanted[common]:
            common += 1
        # Close what this run doesn't carry, before the spaces that came first.
        closing = "".join(_close(m) for m in reversed(open_marks[common:]))
        if closing:
            spaces = []
            while out and out[-1].strip(" ") == "":
                spaces.insert(0, out.pop())
            out.append(closing)
            out.extend(spaces)
        open_marks = open_marks[:common]
        for m in wanted[common:]:
            out.append(_open(m))
            open_marks.append(m)
        out.append(text)
    closing = "".join(_close(m) for m in reversed(open_marks))
    if closing:
        spaces = []
        while out and out[-1].strip(" ") == "":
            spaces.insert(0, out.pop())
        out.append(closing)
        out.extend(spaces)
    return "".join(out).rstrip(" ")


def _escape_start(text: str) -> str:
    """Plain text that would read as Markdown at the start of a line keeps its meaning."""
    if HEADING.match(text) or LIST_ITEM.match(text) or QUOTE.match(text) or RULE.match(text) \
            or FENCE.match(text):
        return "\\" + text
    return text


def document_markdown(document: QTextDocument) -> str:
    lines = []
    block = document.begin()
    in_code = False
    while block.isValid():
        kind = block_kind(block)
        fmt = block.blockFormat()
        if kind != "code" and in_code:
            lines.append("```")
            in_code = False
        if kind == "code":
            if not in_code:
                language = fmt.stringProperty(P.BlockCodeLanguage) if fmt.hasProperty(
                    P.BlockCodeLanguage) else ""
                lines.append("```" + language)
                in_code = True
            lines.append(block.text().replace(" ", "\n"))
        elif kind == "heading":
            lines.append("#" * fmt.headingLevel() + " " + block_markdown(block))
        elif kind == "list":
            lst = block.textList()
            lf = lst.format()
            prefix = "    " * max(0, lf.indent() - 1)
            if lf.style() in BULLETS:
                marker = "-"
            else:
                marker = f"{lst.itemNumber(block) + max(lf.start(), 1)}."
            box = {QTextBlockFormat.MarkerType.Checked: "[x] ",
                   QTextBlockFormat.MarkerType.Unchecked: "[ ] "}.get(fmt.marker(), "")
            lines.append(f"{prefix}{marker} {box}{block_markdown(block)}".rstrip()
                         if not box else f"{prefix}{marker} {box}{block_markdown(block)}")
        elif kind == "quote":
            level = fmt.intProperty(P.BlockQuoteLevel)
            lines.append("> " * level + block_markdown(block))
        elif kind == "rule":
            lines.append("---")
        else:
            text = block_markdown(block)
            lines.append(_escape_start(text) if not text.startswith("![") else text)
        block = block.next()
    if in_code:
        lines.append("```")
    return "\n".join(lines)


# ---- the editor ---------------------------------------------------------------------------------

class NoteEditor(QTextEdit):
    """Pictures pasted or dropped in go to `picture_handler(mime) -> str | None` (it keeps the
    picture and returns its Markdown); `picture_loader(url, width) -> QImage | None` gives
    the pictures to show."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setMouseTracking(True)
        self.picture_handler = None
        self.picture_loader = None
        self.document().setDocumentMargin(8)
        theme.themed(lambda _t: self.viewport().update())

    # ---- Markdown in and out -----------------------------------------------------

    def set_markdown(self, body: str):
        load_markdown(self.document(), body)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.setTextCursor(cursor)

    def markdown(self) -> str:
        return document_markdown(self.document())

    # ---- pictures --------------------------------------------------------------------

    def loadResource(self, kind, url):  # noqa: N802 (Qt naming)
        if kind == QTextDocument.ImageResource and url.scheme() == SCHEME and self.picture_loader:
            image = self.picture_loader(url, self.viewport().width() - 40)
            if image is not None:
                return image
            from PySide6.QtGui import QImage
            return QImage()
        return super().loadResource(kind, url)

    def refresh_picture(self, uid: str):
        """A picture changed (e.g. saved again in Ligature): show the new one."""
        url = QUrl(f"{SCHEME}:{uid}")
        if self.picture_loader:
            image = self.picture_loader(url, self.viewport().width() - 40)
            if image is not None:
                self.document().addResource(QTextDocument.ImageResource, url, image)
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def insert_picture(self, markdown: str):
        """Insert a picture (its Markdown, "![alt](quire-image:uid)") as a line of its own."""
        m = IMAGE_LINE.match(markdown)
        if not m:
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if cursor.block().length() > 1:
            if cursor.atBlockStart():
                cursor.insertBlock(plain_block(), plain_char())
                cursor.movePosition(QTextCursor.PreviousBlock)
            else:
                cursor.insertBlock(plain_block(), plain_char())
        self._reset_block(cursor)
        insert_picture_at(cursor, m.group(2), m.group(1))
        if cursor.atBlockEnd() and not cursor.block().next().isValid():
            cursor.insertBlock(plain_block(), plain_char())
        else:
            cursor.movePosition(QTextCursor.NextBlock)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def picture_at(self, pos) -> str | None:
        cursor = self.cursorForPosition(pos)
        after = QTextCursor(cursor)
        after.movePosition(QTextCursor.NextCharacter)
        for c in (after, cursor):  # a cursor's format is the character before it
            fmt = c.charFormat()
            if fmt.isImageFormat():
                url = QUrl(fmt.toImageFormat().name())
                if url.scheme() == SCHEME:
                    rect = self.cursorRect(c)
                    if abs(rect.center().y() - pos.y()) < 4000:
                        return url.path()
        return None

    def canInsertFromMimeData(self, source):  # noqa: N802
        from .note_images import has_picture
        if self.picture_handler is not None and has_picture(source):
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData):  # noqa: N802
        from .note_images import has_picture
        if self.picture_handler is not None and has_picture(source):
            markdown = self.picture_handler(source)
            if markdown:
                self.insert_picture(markdown)
                return
            if not source.hasText():
                return
        if source.hasFormat("application/x-qt-richtext") or source.hasFormat(
                "application/vnd.oasis.opendocument.text"):
            super().insertFromMimeData(source)  # moved within notes: keep its formatting
        elif source.hasText():
            self.textCursor().insertText(source.text())

    def createMimeDataFromSelection(self):  # noqa: N802
        mime = super().createMimeDataFromSelection()
        # Copying out of a note gives its Markdown as the plain text.
        document = QTextDocument()
        cursor = QTextCursor(document)
        cursor.insertFragment(self.textCursor().selection())
        mime.setText(document_markdown(document))
        return mime

    # ---- formatting commands (toolbar and shortcuts) --------------------------------------

    def _merge(self, fmt: QTextCharFormat):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.mergeCurrentCharFormat(fmt)

    def toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal if self.fontWeight() >= QFont.DemiBold else QFont.Bold)
        self._merge(fmt)

    def toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.fontItalic())
        self._merge(fmt)

    def toggle_strike(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self.currentCharFormat().fontStrikeOut())
        self._merge(fmt)

    def toggle_code(self):
        on = not is_code(self.currentCharFormat())
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        fmt = QTextCharFormat()
        if on:
            _mono(fmt)
            fmt.setBackground(SOFT)
            cursor.mergeCharFormat(fmt)
            self.mergeCurrentCharFormat(fmt)
        else:
            plain = QTextCharFormat()
            plain.setFontFixedPitch(False)
            plain.setFontFamilies([self.font().family()])
            plain.clearBackground()
            cursor.mergeCharFormat(plain)
            self.mergeCurrentCharFormat(plain)

    def _each_block(self):
        cursor = self.textCursor()
        doc = self.document()
        block = doc.findBlock(cursor.selectionStart())
        last = doc.findBlock(cursor.selectionEnd())
        while block.isValid():
            yield block
            if block == last:
                break
            block = block.next()

    def _set_block(self, block, block_fmt: QTextBlockFormat, char_fmt: QTextCharFormat | None):
        cursor = QTextCursor(block)
        lst = block.textList()
        if lst is not None:
            lst.remove(block)
        cursor.setBlockFormat(block_fmt)
        if char_fmt is not None:
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            whole = QTextCharFormat()
            whole.setFontWeight(QFont.Normal)
            whole.setFontItalic(False)
            whole.setProperty(P.FontSizeAdjustment, 0)
            cursor.mergeCharFormat(whole)
            cursor.mergeCharFormat(char_fmt)
            cursor.setBlockCharFormat(char_fmt)

    def _reset_block(self, cursor: QTextCursor):
        self._set_block(cursor.block(), plain_block(), QTextCharFormat())

    def set_heading(self, level: int):
        """Make the selected lines headings of `level` (0 turns them back into text)."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in list(self._each_block()):
            if level:
                self._set_block(block, *heading_formats(level))
            else:
                self._set_block(block, plain_block(), QTextCharFormat())
        cursor.endEditBlock()

    def toggle_quote(self):
        blocks = list(self._each_block())
        on = not all(block_kind(b) == "quote" for b in blocks)
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in blocks:
            if on:
                self._set_block(block, *quote_formats(1))
            else:
                self._set_block(block, plain_block(), QTextCharFormat())
        cursor.endEditBlock()

    def toggle_list(self, checklist: bool = False, numbered: bool = False):
        """Turn the selected lines into a list (or checklist), or back into text."""
        blocks = list(self._each_block())
        marker = QTextBlockFormat.MarkerType.Unchecked if checklist else \
            QTextBlockFormat.MarkerType.NoMarker
        already = all(b.textList() is not None and (
            (b.blockFormat().marker() != QTextBlockFormat.MarkerType.NoMarker) == checklist)
            for b in blocks)
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if already:
            for block in blocks:
                self._set_block(block, plain_block(), None)
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.ListDecimal if numbered else QTextListFormat.ListDisc)
            fmt.setIndent(1)
            lst = None
            for block in blocks:
                c = QTextCursor(block)
                if block.textList() is not None:
                    block.textList().remove(block)
                bf = plain_block()
                bf.setMarker(marker)
                c.setBlockFormat(bf)
                if lst is None:
                    lst = c.createList(fmt)
                else:
                    lst.add(block)
                bf = block.blockFormat()
                bf.setMarker(marker)
                c.setBlockFormat(bf)
        cursor.endEditBlock()

    def _indent(self, deeper: bool):
        block = self.textCursor().block()
        lst = block.textList()
        if lst is None:
            return False
        fmt = QTextListFormat(lst.format())
        level = max(1, min(6, fmt.indent() + (1 if deeper else -1)))
        if level == fmt.indent():
            return True
        fmt.setIndent(level)
        if fmt.style() in BULLETS:
            fmt.setStyle(BULLETS[(level - 1) % 3])
        marker = block.blockFormat().marker()
        lst.remove(block)
        cursor = QTextCursor(block)
        # Join a list at that level just above, if there is one; else start one.
        previous = block.previous()
        while previous.isValid() and previous.textList() is not None:
            if previous.textList().format().indent() == level:
                previous.textList().add(block)
                break
            if previous.textList().format().indent() < level:
                previous = None
                break
            previous = previous.previous()
        else:
            previous = None
        if previous is None or not previous.isValid() or block.textList() is None:
            cursor.createList(fmt)
        bf = block.blockFormat()
        bf.setMarker(marker)
        cursor.setBlockFormat(bf)
        return True

    def toggle_checkbox(self, block) -> bool:
        fmt = block.blockFormat()
        if block.textList() is None or fmt.marker() == QTextBlockFormat.MarkerType.NoMarker:
            return False
        done = fmt.marker() == QTextBlockFormat.MarkerType.Unchecked
        fmt.setMarker(QTextBlockFormat.MarkerType.Checked if done
                      else QTextBlockFormat.MarkerType.Unchecked)
        cursor = QTextCursor(block)
        cursor.beginEditBlock()
        cursor.setBlockFormat(fmt)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        color = QTextCharFormat()
        if done:
            color.setForeground(DONE)
            cursor.mergeCharFormat(color)
        else:
            cursor.setCharFormat(_without_foreground(cursor))
        cursor.endEditBlock()
        return True

    # ---- typing ------------------------------------------------------------------------------

    def keyPressEvent(self, event):  # noqa: N802
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        cursor = self.textCursor()
        block = cursor.block()
        kind = block_kind(block)
        if ctrl and not shift and key == Qt.Key_B:
            return self.toggle_bold()
        if ctrl and not shift and key == Qt.Key_I:
            return self.toggle_italic()
        if ctrl and shift and key == Qt.Key_X:
            return self.toggle_strike()
        if ctrl and key == Qt.Key_QuoteLeft:
            return self.toggle_code()
        if ctrl and shift and key == Qt.Key_L:
            return self.toggle_list(checklist=True)
        if ctrl and shift and key in (Qt.Key_8, Qt.Key_Asterisk):
            return self.toggle_list()
        if ctrl and key in (Qt.Key_Return, Qt.Key_Enter) and self.toggle_checkbox(block):
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and not ctrl:
            if shift and kind != "code":
                self.textCursor().insertBlock()
                return
            return self._enter(cursor, block, kind)
        if key == Qt.Key_Backspace and not cursor.hasSelection() and cursor.atBlockStart() \
                and kind != "text":
            if kind == "list" and block.textList().format().indent() > 1:
                self._indent(False)
            else:
                cursor.beginEditBlock()
                self._reset_block(cursor)
                cursor.endEditBlock()
            return
        if key == Qt.Key_Tab and kind == "list" and not ctrl:
            self._indent(True)
            return
        if key == Qt.Key_Backtab and kind == "list":
            self._indent(False)
            return
        super().keyPressEvent(event)
        text = event.text()
        if text == " ":
            self._block_shortcut()
        elif text and text in "*_~`":
            self._inline_shortcut()

    def _enter(self, cursor: QTextCursor, block, kind: str):
        empty = not block.text().strip()
        cursor.beginEditBlock()
        if kind == "list" and empty:
            if block.textList().format().indent() > 1:
                self._indent(False)
            else:
                self._reset_block(cursor)
        elif kind == "code" and empty and block.previous().isValid() and \
                block_kind(block.previous()) == "code":
            self._reset_block(cursor)  # Enter on an empty code line leaves the code block
        elif kind in ("heading", "quote", "rule") or (kind == "text" and cursor.atBlockEnd()):
            if kind == "text":
                cursor.insertBlock(block.blockFormat(), _without_foreground(cursor))
            else:
                cursor.insertBlock(plain_block(), QTextCharFormat())
                if not cursor.atBlockEnd():
                    self._set_block(cursor.block(), plain_block(), QTextCharFormat())
        elif kind == "list":
            cursor.insertBlock()
            fmt = cursor.blockFormat()
            if fmt.marker() != QTextBlockFormat.MarkerType.NoMarker:
                fmt.setMarker(QTextBlockFormat.MarkerType.Unchecked)
                cursor.setBlockFormat(fmt)
                cursor.setCharFormat(_without_foreground(cursor))
        else:
            cursor.insertBlock()
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _block_shortcut(self):
        """"# ", "- ", "1. ", "[ ] ", "> " at the start of a line format it."""
        cursor = self.textCursor()
        block = cursor.block()
        before = block.text()[:cursor.positionInBlock()]
        kind = block_kind(block)
        if kind == "code":
            return

        def clear_prefix():
            c = QTextCursor(block)
            c.setPosition(block.position() + len(before), QTextCursor.KeepAnchor)
            c.removeSelectedText()

        cursor.beginEditBlock()
        try:
            if kind != "list" and (m := re.fullmatch(r"(#{1,6}) ", before)):
                clear_prefix()
                self._set_block(block, *heading_formats(len(m.group(1))))
            elif kind == "text" and re.fullmatch(r"[-*+] ", before):
                clear_prefix()
                self.toggle_list()
            elif kind == "text" and re.fullmatch(r"\d+[.)] ", before):
                clear_prefix()
                self.toggle_list(numbered=True)
            elif re.fullmatch(r"(?:[-*+] )?\[[ xX]?\] ", before) and kind in ("text", "list"):
                clear_prefix()
                done = "x" in before.lower()
                if kind == "text":
                    self.toggle_list(checklist=True)
                fmt = block.blockFormat()
                fmt.setMarker(QTextBlockFormat.MarkerType.Checked if done
                              else QTextBlockFormat.MarkerType.Unchecked)
                QTextCursor(block).setBlockFormat(fmt)
            elif kind == "text" and before == "> ":
                clear_prefix()
                self._set_block(block, *quote_formats(1))
        finally:
            cursor.endEditBlock()

    def _inline_shortcut(self):
        """Closing **bold**, *italic*, _italic_, ~~struck~~ or `code` formats it."""
        cursor = self.textCursor()
        block = cursor.block()
        if block_kind(block) == "code":
            return
        before = block.text()[:cursor.positionInBlock()]
        if before.rstrip().startswith("```") and before.strip() == "```":
            # ``` at the start of a line: a code block.
            cursor.beginEditBlock()
            c = QTextCursor(block)
            c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            c.removeSelectedText()
            self._set_block(block, *code_formats())
            cursor.endEditBlock()
            return
        for pattern, kind in ((r"\*\*((?=\S)[^*]+?(?<=\S))\*\*$", "bold"),
                              (r"__((?=\S)[^_]+?(?<=\S))__$", "bold"),
                              (r"~~((?=\S)[^~]+?(?<=\S))~~$", "strike"),
                              (r"`([^`]+)`$", "code"),
                              (r"(?<![*\w])\*((?=[^\s*])[^*]+?(?<=[^\s*]))\*$", "italic"),
                              (r"(?<![_\w])_((?=\S)[^_]+?(?<=\S))_$", "italic")):
            m = re.search(pattern, before)
            if not m:
                continue
            start = block.position() + m.start()
            end = block.position() + m.end()
            c = QTextCursor(self.document())
            c.beginEditBlock()
            c.setPosition(start)
            c.setPosition(end, QTextCursor.KeepAnchor)
            base = QTextCursor(self.document())
            base.setPosition(start + (2 if kind in ("bold", "strike") else 1))
            fmt = QTextCharFormat(base.charFormat())
            if kind == "bold":
                fmt.setFontWeight(QFont.Bold)
            elif kind == "italic":
                fmt.setFontItalic(True)
            elif kind == "strike":
                fmt.setFontStrikeOut(True)
            else:
                _mono(fmt)
                fmt.setBackground(SOFT)
            c.insertText(m.group(1), fmt)
            c.endEditBlock()
            # Carry on typing without the formatting.
            after = QTextCharFormat(fmt)
            if kind == "bold":
                after.setFontWeight(QFont.Normal)
            elif kind == "italic":
                after.setFontItalic(False)
            elif kind == "strike":
                after.setFontStrikeOut(False)
            else:
                after.setFontFixedPitch(False)
                after.setFontFamilies([self.font().family()])
                after.clearBackground()
            self.setCurrentCharFormat(after)
            return

    # ---- mouse -------------------------------------------------------------------------------

    def _checkbox_at(self, pos):
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        if block.textList() is None or \
                block.blockFormat().marker() == QTextBlockFormat.MarkerType.NoMarker:
            return None
        start = QTextCursor(block)
        rect = self.cursorRect(start)
        if rect.left() - 26 <= pos.x() <= rect.left() + 2 and \
                rect.top() - 2 <= pos.y() <= rect.bottom() + 2:
            return block
        return None

    def mousePressEvent(self, event):  # noqa: N802
        pos = event.position().toPoint()
        if event.button() == Qt.LeftButton:
            block = self._checkbox_at(pos)
            if block is not None:
                self.toggle_checkbox(block)
                return
            if event.modifiers() & Qt.ControlModifier and self.anchorAt(pos):
                QDesktopServices.openUrl(QUrl(self.anchorAt(pos)))
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        pos = event.position().toPoint()
        over = self._checkbox_at(pos) is not None or (
            bool(self.anchorAt(pos)) and event.modifiers() & Qt.ControlModifier)
        self.viewport().setCursor(Qt.PointingHandCursor if over else Qt.IBeamCursor)
        super().mouseMoveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        # A bar beside quotes.
        painter = QPainter(self.viewport())
        color = QColor(theme.current().accent)
        color.setAlpha(140)
        offset = self.verticalScrollBar().value()
        block = self.document().begin()
        layout = self.document().documentLayout()
        while block.isValid():
            if block_kind(block) == "quote":
                rect = layout.blockBoundingRect(block)
                level = block.blockFormat().intProperty(P.BlockQuoteLevel)
                for i in range(level):
                    x = int(self.document().documentMargin() + 18 * i + 4)
                    painter.fillRect(x, int(rect.top() - offset), 3, int(rect.height()), color)
            block = block.next()
        painter.end()


def _without_foreground(cursor: QTextCursor) -> QTextCharFormat:
    fmt = QTextCharFormat(cursor.charFormat())
    fmt.clearForeground()
    return fmt
