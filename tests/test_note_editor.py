"""The notes editor: you write into the formatted note, and it's kept as Markdown."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from quire.domain import note_snippet  # noqa: E402
from quire.presentation.note_editor import NoteEditor, block_kind  # noqa: E402

ROUND_TRIPS = [
    "# Biology: cellular respiration\n\n**Equation:** C6H12O6 + 6 O2 → energy (~34 ATP)\n\n"
    "## Stages\n1. Glycolysis\n2. Krebs cycle\n\n- [x] Review p. 112\n- [ ] Ask about it",
    "Some **bold**, *italic*, ***both***, `code`, ~~gone~~ and [a link](https://x.org).",
    "- top\n    - nested\n        - deeper\n    - back\n- top again\n3. three\n4. four",
    "> quote\n> > deeper",
    "```py\nx = 1\n  y = 2\n\n```\nafter",
    "![ER](quire-image:ab12cd34ab12cd34)\n\nline one\nline two\n---\nend",
    "A * star, a_snake_name, 2*3*4 and \\*not italic*",
    "\\# not a heading\n\\- not a list",
    "",
]


@pytest.fixture
def editor():
    from quire.presentation.qt_app import create_application

    QApplication.instance() or create_application(["quire-tests"])
    e = NoteEditor()
    e.resize(600, 400)
    e.show()
    return e


def key(e, k, mods=Qt.NoModifier, text=""):
    e.keyPressEvent(QKeyEvent(QEvent.KeyPress, k, mods, text))


def type_text(e, text):
    for ch in text:
        k = {" ": Qt.Key_Space, "\n": Qt.Key_Return}.get(ch, Qt.Key_unknown)
        key(e, k, text="" if ch == "\n" else ch)


def at_end(e, markdown):
    e.set_markdown(markdown)
    e.moveCursor(QTextCursor.End)


@pytest.mark.parametrize("body", ROUND_TRIPS)
def test_notes_round_trip_exactly(editor, body):
    editor.set_markdown(body)
    assert editor.markdown() == body


def test_notes_show_formatted(editor):
    editor.set_markdown("# Title\n- [ ] todo\n> quote\n```\ncode\n```")
    doc = editor.document()
    assert [block_kind(doc.findBlockByNumber(i)) for i in range(4)] == [
        "heading", "list", "quote", "code"]
    assert editor.toPlainText() == "Title\ntodo\nquote\ncode"  # no Markdown marks on screen


def test_typing_markdown_formats_it(editor):
    editor.set_markdown("")
    type_text(editor, "# Title\n- milk\neggs\n\n[ ] call Anna\n\n> wise words\nPlain and **bold** "
                      "and *it* and `x`.")
    assert editor.markdown() == ("# Title\n- milk\n- eggs\n- [ ] call Anna\n> wise words\n"
                                 "Plain and **bold** and *it* and `x`.")


def test_enter_on_an_empty_item_ends_the_list(editor):
    at_end(editor, "- milk")
    key(editor, Qt.Key_Return)
    key(editor, Qt.Key_Return)
    type_text(editor, "done")
    assert editor.markdown() == "- milk\ndone"


def test_new_checklist_items_start_unticked(editor):
    at_end(editor, "- [x] done")
    key(editor, Qt.Key_Return)
    type_text(editor, "next")
    assert editor.markdown() == "- [x] done\n- [ ] next"


def test_tab_nests_list_items(editor):
    at_end(editor, "- a\n- b")
    key(editor, Qt.Key_Tab)
    assert editor.markdown() == "- a\n    - b"
    key(editor, Qt.Key_Backtab)
    assert editor.markdown() == "- a\n- b"


def test_backspace_at_the_start_turns_a_heading_back_into_text(editor):
    editor.set_markdown("## Heading")
    editor.moveCursor(QTextCursor.Start)
    key(editor, Qt.Key_Backspace)
    assert editor.markdown() == "Heading"


def test_shortcuts_toggle_formatting(editor):
    editor.set_markdown("make this bold")
    cursor = editor.textCursor()
    cursor.setPosition(10)
    cursor.setPosition(14, QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    key(editor, Qt.Key_B, Qt.ControlModifier)
    assert editor.markdown() == "make this **bold**"
    key(editor, Qt.Key_B, Qt.ControlModifier)
    assert editor.markdown() == "make this bold"


def test_toolbar_lists_and_headings(editor):
    editor.set_markdown("eggs\nflour")
    editor.selectAll()
    editor.toggle_list(checklist=True)
    assert editor.markdown() == "- [ ] eggs\n- [ ] flour"
    editor.selectAll()
    editor.toggle_list(checklist=True)
    assert editor.markdown() == "eggs\nflour"
    editor.moveCursor(QTextCursor.Start)
    editor.set_heading(2)
    assert editor.markdown() == "## eggs\nflour"


def test_clicking_a_checkbox_ticks_it(editor):
    editor.set_markdown("- [ ] Krebs cycle")
    rect = editor.cursorRect(editor.textCursor())
    point = QPointF(rect.left() - 12, rect.center().y())
    event = QMouseEvent(QEvent.MouseButtonPress, point, point, Qt.LeftButton, Qt.LeftButton,
                        Qt.NoModifier)
    QApplication.sendEvent(editor.viewport(), event)
    assert editor.markdown() == "- [x] Krebs cycle"


def test_pictures_go_in_on_a_line_of_their_own(editor):
    at_end(editor, "Before")
    editor.insert_picture("![ER](quire-image:ab12cd34ab12cd34)")
    type_text(editor, "after")
    assert editor.markdown() == "Before\n![ER](quire-image:ab12cd34ab12cd34)\nafter"


def test_the_list_shows_the_text_after_the_title():
    body = "# Mitochondria\n\nThe **powerhouse** of the cell\n- [ ] see [p. 4](http://x)"
    assert note_snippet(body) == "The powerhouse of the cell see p. 4"
    assert note_snippet("Only a title") == ""
    assert note_snippet("T\n*Nature vs. nurture* and _this_") == "Nature vs. nurture and this"
