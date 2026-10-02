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


def blank_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.showPage()
    c.save()
    return buf.getvalue()
