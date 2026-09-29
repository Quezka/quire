"""The notes editor: Markdown shortcuts, lists that continue, checkboxes that tick."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from quire.domain import note_snippet  # noqa: E402
from quire.presentation.markdown_editor import MarkdownEdit  # noqa: E402


@pytest.fixture
def editor():
    from quire.presentation.qt_app import create_application

    QApplication.instance() or create_application(["quire-tests"])
    e = MarkdownEdit()
    e.resize(600, 400)
    e.show()
    return e


def key(e, k, mods=Qt.NoModifier, text=""):
    e.keyPressEvent(QKeyEvent(QEvent.KeyPress, k, mods, text))


def at_end(e, text):
    e.setPlainText(text)
    e.moveCursor(QTextCursor.End)


def test_enter_continues_lists_and_numbering(editor):
    at_end(editor, "- milk")
    key(editor, Qt.Key_Return)
    assert editor.toPlainText() == "- milk\n- "
    at_end(editor, "  3. third")
    key(editor, Qt.Key_Return)
    assert editor.toPlainText() == "  3. third\n  4. "
    at_end(editor, "- [x] done")
    key(editor, Qt.Key_Return)
    assert editor.toPlainText() == "- [x] done\n- [ ] "


def test_enter_on_an_empty_item_ends_the_list(editor):
    at_end(editor, "- milk\n- ")
    key(editor, Qt.Key_Return)
    assert editor.toPlainText() == "- milk\n"


def test_shortcuts_wrap_the_selection_and_unwrap_it(editor):
    editor.setPlainText("make this bold")
    cursor = editor.textCursor()
    cursor.setPosition(10)
    cursor.setPosition(14, QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    key(editor, Qt.Key_B, Qt.ControlModifier)
    assert editor.toPlainText() == "make this **bold**"
    cursor = editor.textCursor()
    cursor.setPosition(10)
    cursor.setPosition(18, QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    key(editor, Qt.Key_B, Qt.ControlModifier)
    assert editor.toPlainText() == "make this bold"


def test_lines_become_checklists_and_headings(editor):
    editor.setPlainText("eggs\nflour")
    editor.selectAll()
    editor.toggle_prefix("- [ ] ")
    assert editor.toPlainText() == "- [ ] eggs\n- [ ] flour"
    editor.selectAll()
    editor.toggle_prefix("- [ ] ")
    assert editor.toPlainText() == "eggs\nflour"
    editor.moveCursor(QTextCursor.Start)
    editor.set_heading(2)
    assert editor.toPlainText().startswith("## eggs")


def test_clicking_a_checkbox_ticks_it(editor):
    editor.setPlainText("- [ ] Krebs cycle")
    rect = editor.cursorRect(_cursor_at(editor, 3))
    point = QPointF(rect.center())
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        event = QMouseEvent(kind, point, point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QApplication.sendEvent(editor.viewport(), event)
    assert editor.toPlainText() == "- [x] Krebs cycle"


def _cursor_at(editor, position):
    cursor = editor.textCursor()
    cursor.setPosition(position)
    return cursor


def test_the_list_shows_the_text_after_the_title():
    body = "# Mitochondria\n\nThe **powerhouse** of the cell\n- [ ] see [p. 4](http://x)"
    assert note_snippet(body) == "The powerhouse of the cell see p. 4"
    assert note_snippet("Only a title") == ""
    assert note_snippet("T\n*Nature vs. nurture* and _this_") == "Nature vs. nurture and this"
