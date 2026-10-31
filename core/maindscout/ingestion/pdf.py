"""Read the text layer of a document. Pure: bytes in, result out. No database, no model calls.

Offsets: `text` is the pages joined by FORM_FEED. A locator's char_start/char_end index into
`text`; the page number is 1 + the count of form feeds before char_start.
"""

from __future__ import annotations

import io
import logging
import math
import re
import statistics
from collections import Counter
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


TEXT_REPAIR_VERSION = "3"  # 3: pages in two columns read column by column (2026-10-27). Bump when the repairs change


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


# --- pages in two columns (2026-10-27) ---------------------------------------------------------------------------------
# Many CVs set a narrow column (contact, skills, languages) beside a wide one (profile, jobs). Read line by line across
# the page, the two interleave ("...la formazione sul funzionamento eLingue Italiano Francese..."), so sentences break
# and quotes no longer match. pypdf's layout mode renders a page as fixed-width text with its own spacing; a band of
# blank characters running down the page between two sides is a column gap. Each column is then read top to bottom,
# the left first, after any header rows (a name set large over both columns). A page without such a gap, or whose
# narrow side is mostly dates ("2018 - 2021" beside each job, to be read across with its job), is read exactly as
# before. The ordinary reading stays the reference for the words themselves: layout mode only decides their order.
MIN_GUTTER_CHARS = 3  # a gap at least three characters wide
MIN_COLUMN_LINES = 3  # a column has at least three lines of its own (not a stray page number or footer)
LARGE_TYPE = 1.8  # a name is set at least this many times the page's usual size (section headings stay below it)
EDGE_ROWS = (6, 3)  # top and bottom rows that may run across a split page (a header, a footer): read it yourself
_DATE = re.compile(r"\b(19|20)\d{2}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|gen|mag|giu|lug|ago|set|ott|dic)[a-z]*\.?\s+\d{2,4}\b"
                   r"|\b(present|today|current|oggi|heute|actuel)\b", re.I)


@dataclass
class Columns:
    head: str  # top rows read across: a name set large over both columns ("RADWA ... ZAKY"); often empty
    left: str
    right: str
    sure: bool = True  # False: the page looks split, but its top or bottom rows cross the gap; read across, flagged


def plain_reading(page: Any) -> tuple[str, set[str]]:
    """The page's ordinary reading, and the pieces of text set in large type on it."""
    pieces: list[tuple[str, float]] = []

    def visit(text: str, cm: Any, tm: Any, font: Any, size: float) -> None:
        if not text.strip() or not size:
            return
        try:  # the type's height on the page: its size through the text and drawing matrices
            pieces.append((text, size * math.hypot(tm[2] * cm[0] + tm[3] * cm[2], tm[2] * cm[1] + tm[3] * cm[3])))
        except (TypeError, IndexError, ValueError):  # an odd matrix: the piece only goes unmeasured
            pass

    plain = page.extract_text(visitor_text=visit) or ""
    if not pieces:
        return plain, set()
    usual = statistics.median([size for text, size in pieces for _ in text.strip()])
    return plain, {w for text, size in pieces if size >= LARGE_TYPE * usual for w in text.split()}


def _in_large_type(word: str, large: set[str]) -> bool:
    """Whether a word is made of large-type pieces: "RADWA" of a larger "R" and a large "ADWA"."""
    made = [True] + [False] * len(word)
    for i in range(len(word)):
        if made[i]:
            for piece in large:
                if word.startswith(piece, i):
                    made[i + len(piece)] = True
    return made[-1]


def page_columns(page: Any, reading: tuple[str, set[str]] | None = None) -> Columns | None:
    """A page's two columns, each in reading order, or None when it is read across. `reading` is the page's
    plain_reading (read here when not given). Its words are whole, so pieces that layout mode spaced apart are joined
    back; and top rows set in large type on both sides are the page's header, read across."""
    try:
        layout = page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False) or ""
    except Exception:  # an odd page never stops the reading
        return None
    rows = [line.rstrip() for line in layout.split("\n") if line.strip()]
    if len(rows) < 2 * MIN_COLUMN_LINES:
        return None
    sure = True
    best = _gutter(rows, len(rows) // 100)  # a stray line may cross the gap
    if best is None:  # a header or footer across the whole page may hide the gap: then the page looks split
        top, bottom = EDGE_ROWS
        sure, best = False, _gutter(rows[top:len(rows) - bottom], 0) if len(rows) > top + bottom + 6 else None
        width = max(len(r) for r in rows)
        if best is None or not 0.25 * width <= (best[0] + best[1]) / 2 <= 0.75 * width:
            return None
    cut = (best[0] + best[1]) // 2
    # letter-spaced words are rejoined before the spacing is squeezed: "T E C H N I C A L   L E A D" keeps its wider
    # gap between the two words only until then
    halves = [(_squeeze(_unspace_line(r[:cut])), _squeeze(_unspace_line(r[cut:]))) for r in rows]
    plain, large = reading if reading is not None else plain_reading(page)
    head = 0
    while head < len(halves) and all(halves[head]) and all(
            _in_large_type(w, large) for half in halves[head] for w in half.split()):
        head += 1
    left = [a for a, _ in halves[head:] if a]
    right = [b for _, b in halves[head:] if b]
    if len(left) < MIN_COLUMN_LINES or len(right) < MIN_COLUMN_LINES:
        return None
    narrow = left if sum(map(len, left)) <= sum(map(len, right)) else right
    if sum(1 for r in narrow if _DATE.search(r)) * 2 >= len(narrow):
        return None  # a column of dates beside the jobs: read across, each date with its job
    words = set(repair_text(plain).split())

    def text(column: list[str]) -> str:
        return "\n".join(_rejoin(r, words) for r in column)

    return Columns(text([" ".join(h) for h in halves[:head]]), text(left), text(right), sure)


def _gutter(rows: list[str], quiet: int) -> tuple[int, int] | None:
    """The widest band of character columns, between 15% and 85% of the page width, that at most `quiet` rows
    write in: a column gap, as (start, end)."""
    width = max(len(r) for r in rows)
    filled = [0] * width
    for r in rows:
        for i, ch in enumerate(r):
            if not ch.isspace():
                filled[i] += 1
    lo, hi = int(width * 0.15), int(width * 0.85)
    best: tuple[int, int] | None = None
    start = None
    for i in range(lo, hi + 1):
        if i < hi and filled[i] <= quiet:
            start = i if start is None else start
            continue
        if start is not None and (best is None or i - start > best[1] - best[0]):
            best = (start, i)
        start = None
    return best if best is not None and best[1] - best[0] >= MIN_GUTTER_CHARS else None


def _same_characters(a: str, b: str) -> bool:
    """Whether two readings of a page hold the same characters, spacing aside: reordering may move text, never
    lose or add any."""
    return Counter("".join(a.split())) == Counter("".join(b.split()))


def _squeeze(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", text).strip()


MAX_PIECES = 4  # a word layout mode broke into at most this many pieces


def _rejoin(line: str, words: set[str]) -> str:
    """Layout mode sets text on a grid of characters, so it can space a word apart: a large first letter ("T ECHNICAL"),
    odd letter spacing ("Montre al"). Pieces side by side are joined back when together they are a word of the
    page's ordinary reading and one of them is not a word there on its own. Real word pairs stay apart."""
    pieces = line.split(" ")
    out: list[str] = []
    i = 0
    while i < len(pieces):
        for j in range(min(len(pieces), i + MAX_PIECES), i + 1, -1):  # the longest run first
            run = pieces[i:j]
            if "".join(run) in words and not all(p in words for p in run):
                out.append("".join(run))
                i = j
                break
        else:
            out.append(pieces[i])
            i += 1
    return " ".join(out)


def pages_text(pages: list[Any]) -> tuple[list[str], list[int]]:
    """Each page's text, and the pages whose layout is unsure. A two-column page starts with the column the page
    before it ended on, so a sentence that runs over the page turn in the main column stays whole ("...sul
    funzionamento e" / "sulla corretta gestione di Salesforce", not the sidebar's "Lingue Italiano Francese" in
    between). Every page keeps its own text. The fallback (owner, 2026-10-27: "keep what you have but also have a
    fallback, instead of overengineering"): a page that looks split but could not be read as columns, or whose column
    reading lost or added any character, is read across as before and reported, for a person to read the file."""
    out: list[str] = []
    unsure: list[int] = []
    in_columns = False
    ended_on = None  # "left" | "right": the column the previous two-column page ended with
    for number, page in enumerate(pages, start=1):
        reading = plain_reading(page)
        plain = reading[0]
        cols = page_columns(page, reading)
        if cols is not None:
            first, second = (cols.right, cols.left) if ended_on == "right" else (cols.left, cols.right)
            text = "\n".join(t for t in (cols.head, first, second) if t).strip()
            if cols.sure and _same_characters(text, plain):
                out.append(text)
                in_columns = True
                ended_on = "left" if ended_on == "right" else "right"
                continue
            unsure.append(number)
        out.append(plain.strip())
        ended_on = None
    return (without_furniture(out) if in_columns else out), unsure


FURNITURE_CHARS = 30  # a repeated line this long is page furniture; short ones (a name, "Experience") are not


def without_furniture(texts: list[str]) -> list[str]:
    """Page furniture out of the flow, in a document read in columns: a long line found word for word on more than one
    page (a consent line, a running header or footer) is kept once, on the last page it appears on. Otherwise it
    lands mid-sentence where a column runs over the page turn. Other documents keep their reading as it was."""
    seen: dict[str, list[int]] = {}
    for n, t in enumerate(texts):
        for line in {ln.strip() for ln in t.split("\n") if len(ln.strip()) >= FURNITURE_CHARS}:
            seen.setdefault(line, []).append(n)
    repeated = {line: pages[-1] for line, pages in seen.items() if len(pages) > 1}
    if not repeated:
        return texts
    return ["\n".join(ln for ln in t.split("\n") if repeated.get(ln.strip(), n) == n) for n, t in enumerate(texts)]


def extract_pdf(data: bytes) -> ExtractionResult:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = list(reader.pages)
        read, unsure = pages_text(pages)
        texts = [repair_text(t) for t in read]
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
    if unsure:
        reasons.append(f"unsure_layout_pages:{','.join(map(str, unsure))}")

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


# A glyph with no character behind it (the emoji bullets of a job ad, 2026-10-30) is read as NUL, which Postgres text
# cannot hold: storing the ad failed with a server error. Nothing readable is lost without it.
NUL = "\x00"


def extract(data: bytes, media_type: str) -> ExtractionResult:
    if media_type == "application/pdf":
        result = extract_pdf(data)
    elif media_type.startswith("text/plain"):
        text = data.decode("utf-8", errors="replace")
        result = ExtractionResult(text=text, pages=1, extractor={"name": "plain", "version": "1"})
    else:
        raise UnsupportedMedia(f"Unsupported media type: {media_type}")
    result.text = result.text.replace(NUL, "")
    return result
