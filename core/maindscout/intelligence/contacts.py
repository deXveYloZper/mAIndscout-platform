"""Decide whether a contact found in a document may be trusted as a way to identify or reach a person.

Text layers lie: a design-heavy CV can misspell an email or link in its text while the visible page
(and the link underneath) is right. A contact the text layer shows that the file's own links
disagree with, or that has nothing to do with the person's name, is flagged `possible_ocr_identifier`
and must not become an identity key or a mail target until a human confirms it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FREE_MAIL = {"gmail", "outlook", "hotmail", "yahoo", "icloud", "proton", "protonmail", "live", "me", "msn"}


@dataclass
class ContactVerdict:
    attributable: bool
    attribution: str  # subject | author | template | unknown
    possible_ocr_identifier: bool
    reason: str | None = None


def normalise(kind: str, value: str) -> str:
    value = value.strip()
    if kind == "email":
        return value.removeprefix("mailto:").lower()
    if kind == "phone":
        digits = re.sub(r"\D", "", value)
        return ("+" if value.strip().startswith("+") else "") + digits
    if kind in ("linkedin", "url"):
        cleaned = re.sub(r"^(https?://)?(www\.)?", "", value.lower()).split("?")[0].rstrip("/")
        return cleaned
    return value.lower()


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z]+", name.lower()) if len(t) >= 3]


def _similar(a: str, b: str) -> bool:
    """True if the strings differ by at most one edit (a typo), and are not equal."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


def annotation_targets(kind: str, annotations: list[dict]) -> list[str]:
    """The normalised targets of the file's own links, for this kind of contact."""
    wanted = {"email": "email", "phone": "link", "linkedin": "link", "url": "link"}.get(kind)
    out = []
    for a in annotations:
        if a["kind"] != wanted:
            continue
        uri = a["uri"]
        if kind == "linkedin" and "linkedin.com" not in uri.lower():
            continue
        if kind == "email" or kind == "linkedin":
            out.append(normalise(kind, uri))
    return out


def judge(kind: str, value: str, full_name: str | None, annotations: list[dict], email_domain_of_company: bool = False) -> ContactVerdict:
    """Attribution is assumed `subject` for a CV; this checks the value itself."""
    norm = normalise(kind, value)
    targets = annotation_targets(kind, annotations)

    if targets and norm not in targets:
        near = [t for t in targets if _similar(t, norm) or _close_local(t, norm)]
        if near or kind in ("email", "linkedin"):
            return ContactVerdict(True, "subject", True, f"text shows {norm!r} but the file's link says {targets[0]!r}")

    if kind in ("email", "linkedin") and full_name and not targets:
        local = norm.split("@")[0] if kind == "email" else norm.rsplit("/", 1)[-1]
        name_tokens = _tokens(full_name)
        local_tokens = _tokens(local.replace(".", " ").replace("-", " ").replace("_", " "))
        if name_tokens and local_tokens:
            typo = any(
                n not in local_tokens and any(_similar(n, lt) for lt in local_tokens) for n in name_tokens
            )
            if typo:
                return ContactVerdict(True, "subject", True, "looks like a misspelling of the name")
    return ContactVerdict(True, "subject", False)


def _close_local(a: str, b: str) -> bool:
    return _similar(a.split("@")[0], b.split("@")[0]) and a.split("@")[-1] == b.split("@")[-1]
