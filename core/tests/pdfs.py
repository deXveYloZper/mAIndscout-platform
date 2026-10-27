"""Build small PDFs for tests, so no real person's file is needed in the repo."""

import io

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

BODY = [
    "Jane Example",
    "Senior Software Engineer",
    "jane.example@example.com",
    "Experience: Acme Corp 2019-2024. Built flight software in Rust and C++ for a launch vehicle.",
    "Education: BSc Computer Science, Example University, 2014-2018.",
] * 6


def text_pdf(lines=BODY, mailto: str | None = None, photo: bool = False, pages: int = 1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for page in range(pages):
        y = 800
        for line in lines:
            c.drawString(40, y, line)
            y -= 16
        if mailto and page == 0:
            c.linkURL(mailto, (40, 770, 200, 785), relative=0)
        if photo and page == 0:
            image = Image.new("RGB", (300, 300), (200, 120, 90))
            c.drawImage(ImageReader(image), 400, 600, 120, 120)
        c.showPage()
    c.save()
    return buf.getvalue()


SIDEBAR = ["Contact", "jane.example@example.com", "Skills", "Salesforce", "SQL", "Languages", "Italian", "English"]
MAIN = ["Experience", "CRM Operations Specialist, Example Motors, 2021 - today",
        "Trained users in every market on how the new CRM",
        "platform works, and turned their requests into",
        "requirements for the platform team.",
        "Supported dealers through the roll-out of the platform."]


def two_column_pdf(sidebar: list[list[str]] | None = None, main: list[list[str]] | None = None,
                   header: tuple[str, str] | None = None, footer: str | None = None, banner: str | None = None,
                   rotated: str | None = None) -> bytes:
    """Pages with a narrow left column beside a wide right one, the lines of the two drawn row by row, as a CV
    designer does: read across, they interleave. `header` is a name set large over both columns; `footer` a line
    at the foot of the main column on every page (a consent line); `banner` a line across the whole page above the
    columns; `rotated` a label running up the left edge."""
    sidebar = sidebar or [SIDEBAR]
    main = main or [MAIN]
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for left, right in zip(sidebar, main, strict=True):
        y = 800
        if header:
            c.setFont("Helvetica", 30)
            c.drawString(40, y, header[0])
            c.drawString(230, y, header[1])
            y -= 40
        if banner:
            c.setFont("Helvetica", 10)
            c.drawString(40, y, banner)
            y -= 20
        if rotated:
            c.saveState()
            c.translate(20, 400)
            c.rotate(90)
            c.drawString(0, 0, rotated)
            c.restoreState()
        c.setFont("Helvetica", 10)
        for row in range(max(len(left), len(right))):
            if row < len(left):
                c.drawString(40, y, left[row])
            if row < len(right):
                c.drawString(230, y, right[row])
            y -= 14
        if footer:
            c.setFont("Helvetica", 7)
            c.drawString(230, 40, footer)
        c.showPage()
    c.save()
    return buf.getvalue()


def blank_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.showPage()
    c.save()
    return buf.getvalue()
