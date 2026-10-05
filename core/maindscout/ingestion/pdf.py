"""Read the text layer of a document. Pure: bytes in, result out. No database, no model calls.

Offsets: `text` is the pages joined by FORM_FEED. A locator's char_start/char_end index into
`text`; the page number is 1 + the count of form feeds before char_start.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

FORM_FEED = "\f"
MIN_PHOTO_PIXELS = 150  # an embedded image at least this wide and tall may be a photo or a scan
MIN_CHARS_PER_PAGE = 200  # below this the text layer is probably not the whole page

logging.getLogger("pypdf").setLevel(logging.ERROR)


class UnsupportedMedia(ValueError):
    pass


class UnreadableDocument(ValueError):
    pass


@dataclass
class Annotation:
    page: int
    kind: str  # "email" for mailto:, otherwise "link"
    uri: str


@dataclass
class ExtractionResult:
    text: str
    pages: int
    annotations: list[Annotation] = field(default_factory=list)
    needs_vision: bool = False
    needs_vision_reasons: list[str] = field(default_factory=list)
    created: date | None = None  # from file metadata, if present
    extractor: dict[str, str] = field(default_factory=dict)


def _pdf_date(value: Any) -> date | None:
    match = re.match(r"D:(\d{4})(\d{2})(\d{2})", str(value or ""))
    if not match:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None


def _large_images(page: Any) -> int:
    """Count embedded images big enough to be a photo or scan, without decoding them."""
    count = 0
    try:
        xobjects = page["/Resources"]["/XObject"].get_object()
    except (KeyError, AttributeError, TypeError):
        return 0
    for ref in xobjects.values():
        obj = ref.get_object()
        if obj.get("/Subtype") == "/Image":
            width, height = int(obj.get("/Width", 0)), int(obj.get("/Height", 0))
            if width >= MIN_PHOTO_PIXELS and height >= MIN_PHOTO_PIXELS:
                count += 1
    return count


def _annotations(page: Any, number: int) -> list[Annotation]:
    found: list[Annotation] = []
    for ref in page.get("/Annots") or []:
        action = ref.get_object().get("/A")
        uri = action.get_object().get("/URI") if action else None
        if uri:
            uri = str(uri)
            found.append(Annotation(page=number, kind="email" if uri.lower().startswith("mailto:") else "link", uri=uri))
    return found


TEXT_REPAIR_VERSION = "2"  # bump when the repairs below change; a forced re-read then reads the file again


def _unspace_line(line: str) -> str:
    """Some PDFs (tracked-out designer CVs) store every letter as its own word: "S p a n i s h  ( n a t i v e )".
    On such a line, a single space is inside a word and two or more separate words. Ordinary lines are left alone:
    only a line of at least 6 pieces, 80% of them single characters, is rejoined."""
    pieces = line.split(" ")
    solid = [p for p in pieces if p]
    singles = sum(len(p) == 1 for p in solid)
    short_word = 3 <= len(solid) == singles and len(line.strip()) <= 40  # "K y r a", "P w C"
    if not short_word and (len(solid) < 6 or singles < 0.8 * len(solid)):
        return line
    words = re.split(r" {2,}", line.strip())
    return " ".join(w.replace(" ", "") for w in words)


def repair_text(text: str) -> str:
    return "\n".join(_unspace_line(line) for line in text.split("\n"))


def extract_pdf(data: bytes) -> ExtractionResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = list(reader.pages)
        texts = [repair_text((page.extract_text() or "").strip()) for page in pages]
    except (PyPdfError, ValueError, KeyError, OSError) as error:
        raise UnreadableDocument(f"Could not read PDF: {error}") from error

    annotations: list[Annotation] = []
    photo_pages: list[int] = []
    for number, page in enumerate(pages, start=1):
        annotations.extend(_annotations(page, number))
        if _large_images(page):
            photo_pages.append(number)

    text = FORM_FEED.join(texts)
    reasons: list[str] = []
    if not text.strip():
        reasons.append("no_text_layer")
    elif sum(len(t) for t in texts) / max(len(pages), 1) < MIN_CHARS_PER_PAGE:
        reasons.append("sparse_text_layer")
    if photo_pages:
        reasons.append(f"embedded_image_pages:{','.join(map(str, photo_pages))}")

    meta = reader.metadata
    from pypdf import __version__ as pypdf_version

    return ExtractionResult(
        text=text,
        pages=len(pages),
        annotations=annotations,
        needs_vision=bool(reasons),
        needs_vision_reasons=reasons,
        created=_pdf_date(meta.get("/CreationDate")) if meta else None,
        extractor={"name": "pypdf", "version": pypdf_version, "text_repair": TEXT_REPAIR_VERSION},
    )


def extract(data: bytes, media_type: str) -> ExtractionResult:
    if media_type == "application/pdf":
        return extract_pdf(data)
    if media_type.startswith("text/plain"):
        text = data.decode("utf-8", errors="replace")
        return ExtractionResult(text=text, pages=1, extractor={"name": "plain", "version": "1"})
    raise UnsupportedMedia(f"Unsupported media type: {media_type}")
