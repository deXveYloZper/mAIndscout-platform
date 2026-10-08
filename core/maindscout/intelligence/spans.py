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
    """Expand ligatures, collapse whitespace and lowercase, remembering for every kept character which
    character of the ORIGINAL text it came from (so offsets stay true even when "ﬁ" becomes "fi")."""
    out: list[str] = []
    origin: list[int] = []
    previous_space = True
    for index, raw in enumerate(text):
        for char in _LIGATURE_MAP.get(raw, raw):
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


_LIGATURE_MAP = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
                 "’": "'", "‘": "'", "“": '"', "”": '"'}
_LIGATURES = str.maketrans(_LIGATURE_MAP)


def locate(text: str, quote: str) -> Located | None:
    """Find the quote in the document, tolerant only of whitespace and case. Returns offsets into text."""
    if not quote or not quote.strip():
        return None
    haystack, origin = _squash(text)
    needle, _ = _squash(quote)
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


def locate_parts(text: str, quote: str) -> list[Located] | None:
    """A quote the model pieced together from separate lines of a multi-column page ("June 2021 - August 2024" and,
    elsewhere, "Full-stack Engineer | BlueCat Networks"). Accepted only when it has two to four pieces and every piece
    is literally in the text; returns them in the order of the quote, or None."""
    pieces = [x.strip() for x in re.split(r"\n+", quote or "") if x.strip()]
    if not 2 <= len(pieces) <= 4 or any(len(x) < 3 for x in pieces):
        return None
    found = [locate(text, x) for x in pieces]
    return None if any(f is None for f in found) else found


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _year_written(year: str, lowered: str) -> bool:
    """The four-digit year, or a two-digit year that is plainly a date: 03/19, 03.19, Mar 19, Mar '19, '19.
    A bare two-digit number ("24th", "24/7") is not a year."""
    if re.search(rf"(?<!\d){year}(?!\d)", lowered):
        return True
    yy = year[2:]
    months = "|".join(MONTHS)
    return bool(re.search(rf"(?<!\d)(0?[1-9]|1[0-2])\s*[/.\-]\s*{yy}(?!\d)"
                          rf"|\b(?:{months})[a-z]*\.?\s*'?{yy}(?!\d)"
                          rf"|['’]{yy}(?!\d)", lowered))


def date_supported(iso: str | None, precision: str, quote: str) -> bool:
    """The year (and month, if the claim says month) must be written in the quote."""
    if not iso:
        return True
    year, month = iso[:4], int(iso[5:7]) if len(iso) >= 7 else None
    lowered = quote.lower().replace("’", "'")
    if not _year_written(year, lowered):
        return False
    if precision in ("month", "exact") and month:
        named = re.search(rf"\b{MONTHS[month - 1]}", lowered)
        yy = rf"(?:{year}|{year[2:]})"
        numeric = re.search(rf"(?<!\d)0?{month}\s*[/.\-]\s*{yy}(?!\d)|(?<!\d){year}\s*[/.\-]\s*0?{month}(?!\d)", lowered)
        return bool(named or numeric)
    return True


def _phone_runs(text: str) -> list[str]:
    """The digits of each phone-like run in the text (digits with spaces, dots, dashes, slashes, brackets, a leading +)."""
    return [_digits(m) for m in re.findall(r"\+?\d[\d\s().\-/]{4,}\d", text)]


def value_supported(kind: str, value: str, text: str, annotation_uris: list[str]) -> bool:
    """A contact value must appear in the document text or in a link annotation.

    Phones: the digits must be one written number, not digits gathered from different places. Emails and links:
    spaces are tolerated (PDF text often splits a word in two), but only where the text has nothing else in between.
    """
    haystack = text.translate(_LIGATURES).lower()
    needle = value.strip().lower()
    if kind == "phone":
        digits = _digits(value)
        return len(digits) >= 6 and any(digits in run for run in _phone_runs(text))
    if needle in haystack or _spaced(needle, haystack):
        return True
    stripped = re.sub(r"^(https?://)?(www\.)?", "", needle).rstrip("/")
    if stripped and (stripped in haystack or _spaced(stripped, haystack)):
        return True
    return any(stripped in uri.lower() or needle in uri.lower() for uri in annotation_uris)


def _spaced(needle: str, haystack: str) -> bool:
    """The needle with at most one stray space inside (a split word), starting and ending at a token edge."""
    if len(needle) < 5:
        return False
    pattern = r"\s?".join(re.escape(c) for c in needle)
    for m in re.finditer(rf"(?<![\w.@\-]){pattern}(?![\w@\-])", haystack):
        if m.group(0).count(" ") <= 1:
            return True
    return False


def name_supported(value: str, quote: str) -> bool:
    """A tidied name is in the quote, ignoring spaces, case and accents, starting and ending on word edges.

    Spaces are ignored because PDF text splits words ("GUST AVO"); word edges stop "Ann" being found in "Joann".
    """
    import unicodedata

    def fold(text: str) -> str:
        text = unicodedata.normalize("NFKD", text.translate(_LIGATURES))
        return "".join(c for c in text.lower() if c.isalpha() or c.isspace() or c in "-'")

    target = "".join(c for c in fold(value) if c.isalpha())
    if not target:
        return False
    words = re.findall(r"[a-z]+", fold(quote))
    flat, starts, ends, pos = "", set(), set(), 0
    for w in words:
        starts.add(pos)
        flat += w
        pos += len(w)
        ends.add(pos)
    i = flat.find(target)
    while i >= 0:
        if i in starts and i + len(target) in ends:
            return True
        i = flat.find(target, i + 1)
    return False


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
