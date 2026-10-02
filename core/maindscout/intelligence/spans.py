"""Typed span check. Mechanical, not a model's opinion.

A claim is supported only if (1) its quote is really in the document text, and (2) every typed value
in the claim (dates, emails, phone digits, URLs) is really in the quote or the document. Failing
claims are blocked from commit. Paraphrase support is a separate, lower-trust matter and is not
handled here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MONTHS = [
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
]


@dataclass
class Located:
    char_start: int
    char_end: int
    page: int
    snippet: str


def _squash(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace and lowercase, remembering where each kept character came from."""
    out: list[str] = []
    origin: list[int] = []
    previous_space = True
    for index, char in enumerate(text):
        if char.isspace():
            if not previous_space:
                out.append(" ")
                origin.append(index)
            previous_space = True
        else:
            out.append(char.lower())
            origin.append(index)
            previous_space = False
    return "".join(out), origin


_LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "’": "'", "‘": "'", "“": '"', "”": '"'})


def locate(text: str, quote: str) -> Located | None:
    """Find the quote in the document, tolerant only of whitespace and case. Returns offsets into text."""
    if not quote or not quote.strip():
        return None
    haystack, origin = _squash(text.translate(_LIGATURES))
    needle, _ = _squash(quote.translate(_LIGATURES))
    needle = needle.strip()
    if not needle:
        return None
    position = haystack.find(needle)
    if position < 0:
        return None
    start = origin[position]
    end = origin[position + len(needle) - 1] + 1
    page = 1 + text.count("\f", 0, start)
    return Located(start, end, page, text[start:end])


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def date_supported(iso: str | None, precision: str, quote: str) -> bool:
    """The year (and month, if the claim says month) must be written in the quote."""
    if not iso:
        return True
    year, month = iso[:4], int(iso[5:7]) if len(iso) >= 7 else None
    lowered = quote.lower()
    if year not in lowered and year[2:] not in re.findall(r"(?<!\d)(\d{2})(?!\d)", lowered):
        return False
    if precision in ("month", "exact") and month:
        named = MONTHS[month - 1] in lowered
        numeric = re.search(rf"(?<!\d)0?{month}\s*[/.\-]\s*{year}|{year}\s*[/.\-]\s*0?{month}(?!\d)", lowered)
        return bool(named or numeric)
    return True


def value_supported(kind: str, value: str, text: str, annotation_uris: list[str]) -> bool:
    """A contact value must appear in the document text or in a link annotation."""
    haystack = text.translate(_LIGATURES).lower()
    needle = value.strip().lower()
    if kind == "phone":
        digits = _digits(value)
        return len(digits) >= 6 and digits in _digits(text)
    if needle in haystack.replace(" ", "") or needle in haystack:
        return True
    stripped = re.sub(r"^(https?://)?(www\.)?", "", needle).rstrip("/")
    if stripped and stripped in haystack.replace(" ", ""):
        return True
    return any(stripped in uri.lower() or needle in uri.lower() for uri in annotation_uris)


def name_supported(value: str, quote: str) -> bool:
    """A tidied name is supported if, ignoring spaces, case and accents, it is inside the quote."""
    import unicodedata

    def flat(text: str) -> str:
        text = unicodedata.normalize("NFKD", text.translate(_LIGATURES))
        return "".join(c for c in text.lower() if c.isalpha())

    return bool(flat(value)) and flat(value) in flat(quote)


def month_day_supported(when, quote: str) -> bool:
    """Day and month are written in the quote, as 26.08, 26/08, 26 Aug or Aug 26."""
    lowered = quote.lower()
    day, month = when.day, when.month
    named = MONTHS[month - 1]
    numeric = re.search(rf"(?<!\d)0?{day}\s*[./\-]\s*0?{month}(?!\d)", lowered)
    words = re.search(rf"(?<!\d)0?{day}(st|nd|rd|th)?\s+{named}|{named}[a-z]*\.?\s+0?{day}(?!\d)", lowered)
    return bool(numeric or words)


_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


def number_supported(value: float, quote: str) -> bool:
    """A number of years must be written: as digits (3, 3+, 3-5) or as a word (three)."""
    n = int(value) if float(value).is_integer() else value
    lowered = quote.lower()
    if re.search(rf"(?<![\d.]){re.escape(str(n))}(?![\d])", lowered):
        return True
    word = _NUMBER_WORDS.get(n) if isinstance(n, int) else None
    return bool(word and re.search(rf"\b{word}\b", lowered))
