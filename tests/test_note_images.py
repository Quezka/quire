"""Pictures in notes: kept, shown, synced, and diagram pictures edited in Ligature."""
import pytest

from quire.application.errors import ValidationError
from quire.application.inputs import NoteInput
from quire.domain import (
    MAX_IMAGE_BYTES, NotFound, derive_note_title, image_markdown, image_uids, note_snippet,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 40
DIAGRAM = b"\x89PNG\r\n\x1a\n" + b"...zTXtligature\0\0..." + b"\0" * 20


def test_markdown_for_a_picture():
    assert image_markdown("ab12cd34", "ER [v2]") == "![ER (v2)](quire-image:ab12cd34)"
    body = "# Title\n![a](quire-image:ab12cd34ab12cd34)\ntext ![b](quire-image:ab12cd34ab12cd34)"
    assert image_uids(body) == ["ab12cd34ab12cd34"]


def test_pictures_dont_show_in_titles_and_snippets():
    body = "![](quire-image:ab12cd34ab12cd34)\n# Schema\n![Diagram](quire-image:ab12cd34)\nNotes"
    assert derive_note_title(body) == "Schema"
    assert note_snippet(body) == "Diagram Notes"


def test_add_and_show_a_picture(services):
    markdown = services.notes.add_image(PNG, "image/png", "Sketch")
    uid = image_uids(markdown)[0]
    image = services.notes.image(uid)
    assert image.data == PNG and image.mime == "image/png" and not image.diagram
    note = services.notes.create(f"# Lesson\n\n{markdown}\n")
    assert [i.uid for i in services.notes.images_in(note.body)] == [uid]
    assert services.notes.image("0" * 32) is None


@pytest.mark.parametrize("data, mime", [(PNG, "image/svg+xml"), (b"", "image/png"),
                                        (b"x" * (MAX_IMAGE_BYTES + 1), "image/png")])
def test_pictures_notes_cannot_keep(services, data, mime):
    with pytest.raises(ValidationError):
        services.notes.add_image(data, mime)


def test_editing_a_diagram_in_ligature(services, diagrams):
    uid = image_uids(services.notes.add_image(DIAGRAM, "image/png"))[0]
    image = services.notes.image(uid)
    assert image.diagram and services.notes.can_edit_diagrams()
    path = services.notes.edit_diagram(uid)
    assert diagrams.files[path] == DIAGRAM
    assert not services.notes.diagram_saved(uid, path)  # nothing changed yet
    diagrams.files[path] = DIAGRAM + b"edited"
    assert services.notes.diagram_saved(uid, path)
    assert services.notes.image(uid).data == DIAGRAM + b"edited"


def test_only_ligature_pictures_open_in_ligature(services, diagrams):
    uid = image_uids(services.notes.add_image(PNG, "image/png"))[0]
    with pytest.raises(NotFound):
        services.notes.edit_diagram(uid)
    diagrams.installed = False
    assert not services.notes.can_edit_diagrams()


def test_a_note_with_a_picture_reaches_the_other_device(tmp_path):
    from .test_sync import connect, device
    from .fakes import FakeCloud
    cloud = FakeCloud()
    a, db_a = device(tmp_path, cloud, "laptop")
    b, db_b = device(tmp_path, cloud, "desktop")
    connect(a, create=True)
    connect(b)
    markdown = a.notes.add_image(DIAGRAM, "image/png", "ER")
    note = a.notes.create(f"# Database\n{markdown}")
    a.sync.sync()
    b.sync.sync()
    (summary,) = b.notes.search()
    body = b.notes.note(summary.id).body
    assert body == note.body
    (image,) = b.notes.images_in(body)
    assert image.data == DIAGRAM and image.diagram
    # An edit made in Ligature on one device reaches the other.
    uid = image.uid
    path = a.notes.edit_diagram(uid)
    a.notes._diagrams.files[path] = DIAGRAM + b"v2"
    a.notes.diagram_saved(uid, path)
    a.sync.sync()
    b.sync.sync()
    assert b.notes.image(uid).data == DIAGRAM + b"v2"
    db_a.close()
    db_b.close()


def test_large_pictures_are_pushed_in_several_commits():
    from quire.application.ports import SyncRecord
    from quire.infrastructure.firebase import BATCH_BYTES, _batches
    big = SyncRecord("image", "u", "t", data={"data": "x" * (BATCH_BYTES // 3)})
    small = SyncRecord("note", "n", "t", data={"body": "hi"})
    batches = list(_batches([big, big, big, small, big]))
    assert [len(b) for b in batches] == [2, 3]
    assert sum(len(b) for b in batches) == 5


def test_note_edits_keep_pictures(services):
    markdown = services.notes.add_image(PNG, "image/png")
    note = services.notes.create(markdown)
    services.notes.update(note.id, NoteInput(markdown + "\nmore", None, False, ""))
    assert len(services.notes.images_in(services.notes.note(note.id).body)) == 1
