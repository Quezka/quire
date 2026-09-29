"""A plain-text Markdown editor that styles the text as you type: headings grow, **bold**
and *italic* show as such, list markers and `code` are tinted, and ticked checklist items
are struck through. Enter continues a list, clicking a checkbox ticks it, and the usual
shortcuts (Ctrl+B, Ctrl+I, …) wrap the selection."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QFont, QKeySequence, QSyntaxHighlighter, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import QPlainTextEdit

from . import theme

HEADING = re.compile(r"^(#{1,6})\s+.*$")
LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])(\s+)(\[[ xX]\]\s+)?")
CHECKBOX = re.compile(r"^(\s*[-*+]\s+)\[([ xX])\]")
QUOTE = re.compile(r"^\s*>.*$")
FENCE = re.compile(r"^\s*```")
INLINE = [
    (re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__"), "bold"),
    (re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?!\*)|(?<![_\w])_(?=\S)(.+?)(?<=\S)_(?!\w)"), "italic"),
    (re.compile(r"~~(?=\S)(.+?)(?<=\S)~~"), "strike"),
    (re.compile(r"`[^`\n]+`"), "code"),
    (re.compile(r"\[[^\]\n]+\]\([^)\s]+\)|https?://\S+"), "link"),
]
HEADING_SCALE = {1: 1.55, 2: 1.35, 3: 1.2, 4: 1.1, 5: 1.05, 6: 1.0}
IN_CODE_BLOCK = 1


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document, base_font: QFont):
        super().__init__(document)
        self._base = base_font
        theme.themed(lambda _t: self.rehighlight())

    def _fmt(self, **kw) -> QTextCharFormat:
        t = theme.current()
        f = QTextCharFormat()
        if kw.get("color"):
            f.setForeground(QColor(getattr(t, kw["color"])))
        if kw.get("bold"):
            f.setFontWeight(QFont.Bold)
        if kw.get("italic"):
            f.setFontItalic(True)
        if kw.get("strike"):
            f.setFontStrikeOut(True)
        if kw.get("size"):
            f.setFontPointSize(self._base.pointSizeF() * kw["size"])
        if kw.get("mono"):
            f.setFontFamilies(["JetBrains Mono", "DejaVu Sans Mono", "Consolas", "monospace"])
            f.setBackground(QColor(t.hover))
        return f

    def highlightBlock(self, text: str):
        # Fenced code blocks: everything inside is code.
        in_code = self.previousBlockState() == IN_CODE_BLOCK
        if FENCE.match(text):
            self.setFormat(0, len(text), self._fmt(color="faint", mono=True))
            self.setCurrentBlockState(-1 if in_code else IN_CODE_BLOCK)
            return
        if in_code:
            self.setFormat(0, len(text), self._fmt(mono=True))
            self.setCurrentBlockState(IN_CODE_BLOCK)
            return
        self.setCurrentBlockState(-1)

        if m := HEADING.match(text):
            level = len(m.group(1))
            self.setFormat(0, len(text), self._fmt(bold=True, size=HEADING_SCALE[level]))
            self.setFormat(0, level, self._fmt(color="faint", bold=True, size=HEADING_SCALE[level]))
            return
        if QUOTE.match(text):
            self.setFormat(0, len(text), self._fmt(color="muted", italic=True))
        if m := LIST_ITEM.match(text):
            self.setFormat(m.start(2), len(m.group(2)), self._fmt(color="accent", bold=True))
            if m.group(4):
                done = m.group(4)[1] in "xX"
                self.setFormat(m.start(4), 3, self._fmt(color="accent", bold=True))
                if done:
                    self.setFormat(m.end(4), len(text) - m.end(4), self._fmt(color="faint", strike=True))
        for pattern, kind in INLINE:
            for m in pattern.finditer(text):
                style = {"bold": dict(bold=True), "italic": dict(italic=True),
                         "strike": dict(strike=True, color="muted"),
                         "code": dict(mono=True, color="accent"),
                         "link": dict(color="accent")}[kind]
                self.setFormat(m.start(), m.end() - m.start(), self._fmt(**style))
                marks = {"bold": 2, "italic": 1, "strike": 2}.get(kind)
                if marks:  # the ** and * themselves fade back
                    faint = self._fmt(color="faint", **{k: v for k, v in style.items() if k != "color"})
                    self.setFormat(m.start(), marks, faint)
                    self.setFormat(m.end() - marks, marks, faint)


class MarkdownEdit(QPlainTextEdit):
    """QPlainTextEdit with Markdown-aware editing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.highlighter = MarkdownHighlighter(self.document(), self.font())
        self.setMouseTracking(True)

    def setFont(self, font):  # noqa: N802 (Qt naming)
        super().setFont(font)
        if hasattr(self, "highlighter"):
            self.highlighter._base = font
            self.highlighter.rehighlight()

    # ---- formatting commands (toolbar and shortcuts) ----

    def wrap(self, marker: str, placeholder: str = ""):
        """Put `marker` around the selection (or around a placeholder); again removes it."""
        cursor = self.textCursor()
        text = cursor.selectedText()
        n = len(marker)
        if len(text) >= 2 * n and text.startswith(marker) and text.endswith(marker):
            cursor.insertText(text[n:-n])
            return
        start = cursor.selectionStart()
        inner = text or placeholder
        cursor.insertText(f"{marker}{inner}{marker}")
        cursor.setPosition(start + n)
        cursor.setPosition(start + n + len(inner), QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)

    def _selected_blocks(self):
        cursor = self.textCursor()
        doc = self.document()
        first = doc.findBlock(cursor.selectionStart())
        last = doc.findBlock(cursor.selectionEnd())
        block = first
        while block.isValid():
            yield block
            if block == last:
                break
            block = block.next()

    def _edit_lines(self, change):
        """Apply `change(line) -> line` to each selected line, as one undo step."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in list(self._selected_blocks()):
            new = change(block.text())
            if new != block.text():
                c = QTextCursor(block)
                c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                c.insertText(new)
        cursor.endEditBlock()

    def set_heading(self, level: int):
        """Make the lines headings of `level` (0 turns them back into text)."""
        def change(line):
            body = re.sub(r"^#{1,6}\s+", "", line)
            return ("#" * level + " " + body) if level else body
        self._edit_lines(change)

    def toggle_prefix(self, prefix: str):
        """Turn lines into list items ("- ", "- [ ] ", "> ") or back."""
        lines = [b.text() for b in self._selected_blocks()]
        strip = re.compile(r"^(\s*)(?:[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+[.)]\s+|>\s?)")
        all_have = all(l.lstrip().startswith(prefix.strip()) for l in lines if l.strip())

        def change(line):
            m = strip.match(line)
            indent = re.match(r"^\s*", line).group(0)
            body = line[m.end():] if m else line[len(indent):]
            return f"{indent}{body}" if all_have else f"{indent}{prefix}{body}"
        self._edit_lines(change)

    def toggle_checkbox(self, block) -> bool:
        m = CHECKBOX.match(block.text())
        if not m:
            return False
        c = QTextCursor(block)
        c.setPosition(block.position() + m.start(2))
        c.setPosition(block.position() + m.end(2), QTextCursor.KeepAnchor)
        c.insertText(" " if m.group(2) in "xX" else "x")
        return True

    # ---- keys and mouse ----

    def keyPressEvent(self, event):  # noqa: N802
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)
        shift = bool(mods & Qt.ShiftModifier)
        if ctrl and not shift and key == Qt.Key_B:
            return self.wrap("**", "bold")
        if ctrl and not shift and key == Qt.Key_I:
            return self.wrap("*", "italic")
        if ctrl and shift and key == Qt.Key_X:
            return self.wrap("~~", "struck")
        if ctrl and key == Qt.Key_QuoteLeft:
            return self.wrap("`", "code")
        if ctrl and shift and key == Qt.Key_L:
            return self.toggle_prefix("- [ ] ")
        if ctrl and shift and key == Qt.Key_8:
            return self.toggle_prefix("- ")
        if ctrl and key == Qt.Key_Return:
            block = self.textCursor().block()
            if self.toggle_checkbox(block):
                return
        if key in (Qt.Key_Return, Qt.Key_Enter) and not mods & ~Qt.KeypadModifier:
            if self._continue_list():
                return
        if key == Qt.Key_Tab and not self.textCursor().hasSelection() and self._in_list():
            return self._indent(True)
        if key == Qt.Key_Backtab and self._in_list():
            return self._indent(False)
        super().keyPressEvent(event)

    def _in_list(self) -> bool:
        return bool(LIST_ITEM.match(self.textCursor().block().text()))

    def _indent(self, deeper: bool):
        def change(line):
            if deeper:
                return "    " + line
            return re.sub(r"^( {1,4}|\t)", "", line)
        self._edit_lines(change)

    def _continue_list(self) -> bool:
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()
        m = LIST_ITEM.match(text)
        if not m or cursor.positionInBlock() < m.end():
            return False
        if not text[m.end():].strip():
            # Enter on an empty item ends the list.
            c = QTextCursor(block)
            c.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            c.insertText("")
            return True
        indent, marker, space, box = m.group(1), m.group(2), m.group(3), m.group(4)
        if marker[:-1].isdigit():
            marker = f"{int(marker[:-1]) + 1}{marker[-1]}"
        cursor.insertText("\n" + indent + marker + space + ("[ ] " if box else ""))
        self.ensureCursorVisible()
        return True

    def _checkbox_at(self, pos):
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        m = CHECKBOX.match(block.text())
        if m and m.start(2) - 1 <= cursor.positionInBlock() <= m.end(2) + 1:
            return block
        return None

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and not self.textCursor().hasSelection():
            block = self._checkbox_at(event.position().toPoint())
            if block is not None:
                self.toggle_checkbox(block)
                return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        over = self._checkbox_at(event.position().toPoint()) is not None
        self.viewport().setCursor(Qt.PointingHandCursor if over else Qt.IBeamCursor)
        super().mouseMoveEvent(event)


SHORTCUTS = {
    "bold": QKeySequence("Ctrl+B"), "italic": QKeySequence("Ctrl+I"),
    "list": QKeySequence("Ctrl+Shift+8"), "checklist": QKeySequence("Ctrl+Shift+L"),
    "code": QKeySequence("Ctrl+`"),
}
