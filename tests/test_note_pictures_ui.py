"""Pictures in the notes page: pasting, the preview, PDF export and editing in Ligature."""
import os

import pytest
from PySide6.QtCore import QEventLoop, QMimeData, QTimer

from quire.domain import image_uids
from quire.infrastructure.ligature import LigatureApp, has_diagram

pytestmark = pytest.mark.usefixtures("qt_app")

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def png(extra: bytes = b"") -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage
    image = QImage(40, 30, QImage.Format_ARGB32)
    image.fill(QColor("#5b5bd6"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    raw = bytes(data)
    if extra:  # a zTXt "ligature" chunk before IEND, as Ligature writes it
        import struct
        import zlib
        body = b"ligature\0\0" + zlib.compress(extra)
        chunk = struct.pack(">I", len(body)) + b"zTXt" + body + struct.pack(
            ">I", zlib.crc32(b"zTXt" + body) & 0xFFFFFFFF)
        raw = raw[:-12] + chunk + raw[-12:]
    return raw


@pytest.fixture
def qt_app():
    from PySide6.QtWidgets import QApplication
    from quire.presentation.qt_app import create_application
    return QApplication.instance() or create_application(["quire-tests"])


def pump(ms=60):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def notes_view(services):
    from quire.presentation.bridge import ChangeRelay
    from quire.presentation.views.notes import NotesView
    view = NotesView(services, ChangeRelay(services.bus))
    view.new_note()
    return view


def test_pasting_a_picture_keeps_it_byte_for_byte(notes_view, services):
    data = png(b'{"format": "ligature"}')
    assert has_diagram(data)
    mime = QMimeData()
    mime.setData("image/png", data)
    notes_view.editor.insertPlainText("# Schema")
    notes_view.editor.insertFromMimeData(mime)
    (uid,) = image_uids(notes_view.editor.toPlainText())
    record = services.notes.image(uid)
    assert record.data == data and record.diagram
    notes_view.flush()
    assert uid in services.notes.note(notes_view.note.id).body
    notes_view.preview_btn.setChecked(True)
    pump()
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QTextDocument
    image = notes_view.viewer.loadResource(QTextDocument.ImageResource, QUrl(f"quire-image:{uid}"))
    assert image.width() == 40


def test_pasted_screenshots_become_pictures(notes_view, services):
    from PySide6.QtGui import QImage
    mime = QMimeData()
    mime.setImageData(QImage.fromData(png()))
    notes_view.editor.insertFromMimeData(mime)
    (uid,) = image_uids(notes_view.editor.toPlainText())
    assert services.notes.image(uid).data.startswith(PNG_HEADER)


def test_note_exports_to_pdf(notes_view, services, tmp_path):
    from quire.presentation.note_images import note_pdf
    markdown = services.notes.add_image(png(), "image/png")
    path = tmp_path / "note.pdf"
    note_pdf(services, "Schema", f"# Schema\n\n{markdown}\n\nText", str(path))
    data = path.read_bytes()
    assert data.startswith(b"%PDF") and b"/Image" in data


def test_a_diagram_saved_in_ligature_updates_the_note(services, tmp_path, monkeypatch):
    from quire.presentation.bridge import ChangeRelay
    from quire.presentation.views.notes import NotesView
    launched = []
    services.notes._diagrams = LigatureApp(tmp_path, finder=lambda: "/usr/bin/ligature",
                                           launcher=lambda args, **kw: launched.append(args))
    view = NotesView(services, ChangeRelay(services.bus))
    view.new_note()
    uid = image_uids(services.notes.add_image(png(b"v1"), "image/png"))[0]
    view.edit_diagram(uid)
    path = launched[0][1]
    assert launched[0][0] == "/usr/bin/ligature" and os.path.exists(path)
    # Ligature saves by replacing the file.
    temp = tmp_path / ".saving"
    temp.write_bytes(png(b"v2"))
    os.replace(temp, path)
    for _i in range(40):
        pump(50)
        if services.notes.image(uid).data == png(b"v2"):
            break
    assert services.notes.image(uid).data == png(b"v2")
