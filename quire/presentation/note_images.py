"""Pictures in notes: turning what's pasted or dropped into a picture notes can keep,
showing them in the preview, and printing a note (pictures included) to PDF."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QMimeData, QSizeF, QUrl, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPdfWriter, QTextCursor, QTextDocument
from PySide6.QtWidgets import QTextBrowser

from ..application.services import Services

SCHEME = "quire-image"
IMAGE_LINE = re.compile(r"!\[([^\]\n]*)\]\(quire-image:([0-9a-f]{8,64})\)")
MAX_BYTES = 700_000  # what notes keep (the rule lives in the domain; this avoids a round trip)
LARGEST_SIDE = 2000  # photos are scaled down to this before being kept
FILE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".gif": "image/gif", ".webp": "image/webp"}
OPENABLE = "*.png *.jpg *.jpeg *.gif *.webp *.bmp"


def _encode(image: QImage, fmt: str, quality: int = -1) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, fmt, quality)
    buffer.close()
    return bytes(data)


def fit_picture(image: QImage) -> tuple[bytes, str]:
    """A picture small enough to keep in a note: PNG when that fits (screenshots,
    diagrams), otherwise a JPEG, scaled down until it fits."""
    if max(image.width(), image.height()) > LARGEST_SIDE:
        image = image.scaled(LARGEST_SIDE, LARGEST_SIDE, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
    png = _encode(image, "PNG")
    if len(png) <= MAX_BYTES:
        return png, "image/png"
    flat = image.convertToFormat(QImage.Format_RGB32)
    for quality in (85, 75, 60):
        jpeg = _encode(flat, "JPG", quality)
        if len(jpeg) <= MAX_BYTES:
            return jpeg, "image/jpeg"
    smaller = flat.scaled(flat.width() * 2 // 3, flat.height() * 2 // 3, Qt.KeepAspectRatio,
                          Qt.SmoothTransformation)
    return fit_picture(smaller) if smaller.width() > 200 else (jpeg, "image/jpeg")


def picture_from_file(path: str) -> tuple[bytes, str] | None:
    """A picture file as notes keep it. PNGs that fit are kept byte for byte, so a
    Ligature diagram inside one survives."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError:
        return None
    mime = FILE_TYPES.get(p.suffix.lower())
    if mime and len(data) <= MAX_BYTES:
        return data, mime
    image = QImage.fromData(data)
    return None if image.isNull() else fit_picture(image)


def picture_from_mime(mime: QMimeData) -> tuple[bytes, str] | None:
    """What was pasted or dropped, as a picture: raw PNG data first (it keeps a Ligature
    diagram inside), then an image file, then whatever image the clipboard has."""
    if mime.hasFormat("image/png"):
        data = bytes(mime.data("image/png"))
        if data and len(data) <= MAX_BYTES:
            return data, "image/png"
    for url in mime.urls():
        if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (
                *FILE_TYPES, ".bmp"):
            return picture_from_file(url.toLocalFile())
    if mime.hasImage():
        image = QImage(mime.imageData())
        if not image.isNull():
            return fit_picture(image)
    return None


def has_picture(mime: QMimeData) -> bool:
    return mime.hasImage() or mime.hasFormat("image/png") or any(
        url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in (*FILE_TYPES, ".bmp")
        for url in mime.urls())


def image_at(text: str, column: int) -> str | None:
    """The uid of the picture written at `column` of a line, if any."""
    for m in IMAGE_LINE.finditer(text):
        if m.start() <= column <= m.end():
            return m.group(2)
    return None


def load_picture(services: Services, url: QUrl, width: int) -> QImage | None:
    if url.scheme() != SCHEME:
        return None
    record = services.notes.image(url.path())
    if record is None:
        return None
    image = QImage.fromData(record.data)
    if image.isNull():
        return None
    if width > 0 and image.width() > width:
        image = image.scaledToWidth(width, Qt.SmoothTransformation)
    return image


class NoteBrowser(QTextBrowser):
    """The note preview, with its pictures."""

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.services = services

    def loadResource(self, kind, url):  # noqa: N802 (Qt naming)
        if kind == QTextDocument.ImageResource and url.scheme() == SCHEME:
            image = load_picture(self.services, url, self.viewport().width() - 24)
            return image if image is not None else QImage()
        return super().loadResource(kind, url)

    def image_at(self, pos) -> str | None:
        """The picture under a point of the viewport."""
        cursor = self.cursorForPosition(pos)
        after = QTextCursor(cursor)
        after.movePosition(QTextCursor.NextCharacter)
        for c in (after, cursor):  # a cursor's format is the character before it
            fmt = c.charFormat()
            if fmt.isImageFormat():
                url = QUrl(fmt.toImageFormat().name())
                if url.scheme() == SCHEME:
                    return url.path()
        return None


def note_pdf(services: Services, title: str, body: str, path: str):
    """Print a note, pictures included, to an A4 PDF."""
    writer = QPdfWriter(path)
    writer.setTitle(title)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(18, 18, 18, 18), QPageLayout.Millimeter))
    writer.setResolution(300)
    writer.setCreator("Quire")
    document = QTextDocument()
    # Lay the note out on a page of A4's printable size at 96 dpi; printing scales it.
    page = writer.pageLayout().paintRect(QPageLayout.Point)
    document.setPageSize(QSizeF(page.width() * 96 / 72, page.height() * 96 / 72))
    width = int(page.width() * 96 / 72 - 2 * document.documentMargin() - 2)
    document.setMarkdown(body)  # first: it clears the document's resources
    for m in IMAGE_LINE.finditer(body):
        url = QUrl(f"{SCHEME}:{m.group(2)}")
        image = load_picture(services, url, width)
        if image is not None:
            document.addResource(QTextDocument.ImageResource, url, image)
    document.print_(writer)
