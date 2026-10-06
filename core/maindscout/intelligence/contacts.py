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
    use_value: str | None = None  # the file's own link, when it says the same thing better than the text layer


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


def _name_words(name: str) -> list[str]:
    import unicodedata

    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return [w for w in re.split(r"[^a-z]+", folded) if w]


def same_name(a: str | None, b: str | None) -> bool:
    """Could these be the same person's name? Every word of the shorter name is in the longer one, either whole or as
    its initial ("J. Domajnko" and "Jure Domajnko"; "Jure Domajnko" and "Domajnko Jure"). No name on either side is
    not a match: a shared email or phone alone never decides who someone is."""
    wa, wb = _name_words(a or ""), _name_words(b or "")
    if not wa or not wb:
        return False

    def within(short: list[str], long: list[str]) -> bool:
        return any(len(w) > 1 for w in short) and all(
            w in long if len(w) > 1 else any(x.startswith(w) for x in long) for w in short)

    return within(wa, wb) or within(wb, wa)


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
        if kind == "linkedin" and not _is_linkedin_profile(uri):
            continue  # e.g. a Google search link that mentions linkedin.com in its query
        if kind == "email" or kind == "linkedin":
            out.append(normalise(kind, uri))
    return out


def judge(kind: str, value: str, full_name: str | None, annotations: list[dict], email_domain_of_company: bool = False) -> ContactVerdict:
    """Attribution is assumed `subject` for a CV; this checks the value itself."""
    norm = normalise(kind, value)
    targets = annotation_targets(kind, annotations)

    if targets and norm not in targets:
        same = _same_target(kind, value, targets)
        if same:  # the text layer garbled or shortened what the link says: take the link, nothing to ask
            return ContactVerdict(True, "subject", False, "Taken from the file's own link.", use_value=same)
        near = [t for t in targets if _similar(t, norm) or _close_local(t, norm)]
        if near or kind in ("email", "linkedin"):
            return ContactVerdict(True, "subject", True, f"The file's own link says {targets[0]}.")

    if kind in ("email", "linkedin") and full_name and not targets:
        local = norm.split("@")[0] if kind == "email" else norm.rsplit("/", 1)[-1]
        name_tokens = _tokens(full_name)
        local_tokens = _tokens(local.replace(".", " ").replace("-", " ").replace("_", " "))
        if name_tokens and local_tokens:
            initials = {w[0] for w in _name_words(full_name)}
            typo = any(
                n not in local_tokens and any(_similar(n, lt) and not _name_with_initials(lt, name_tokens, initials)
                                              for lt in local_tokens) for n in name_tokens
            )
            if typo:
                return ContactVerdict(True, "subject", True, "It looks like a misspelling of the person's name.")
    return ContactVerdict(True, "subject", False)


def _close_local(a: str, b: str) -> bool:
    return _similar(a.split("@")[0], b.split("@")[0]) and a.split("@")[-1] == b.split("@")[-1]


def _is_linkedin_profile(uri: str) -> bool:
    from urllib.parse import urlparse

    u = uri.strip()
    host = urlparse(u if "://" in u else f"https://{u}").netloc.lower()
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _slug(text: str) -> str:
    """The profile part of a LinkedIn address, with the spaces a text layer inserts removed ("alice -joanne -fox")."""
    squashed = re.sub(r"\s+", "", text.lower()).split("?")[0].rstrip("/")
    return squashed.rsplit("/", 1)[-1]


def _same_target(kind: str, value: str, targets: list[str]) -> str | None:
    """The link the text means, when the text is the same address garbled or shortened, or only a label."""
    if kind == "linkedin":
        if re.fullmatch(r"\s*(linked\s*in|profile|linkedin profile)\s*:?\s*", value, re.I):
            return targets[0] if len(targets) == 1 else None  # only the word "LinkedIn", the address is in the link
        slug = _slug(value)
        hits = [t for t in targets if slug and _slug(t) == slug]
        return hits[0] if hits else None
    if kind == "email":
        squashed = re.sub(r"\s+", "", value.lower()).removeprefix("mailto:")
        return squashed if squashed in targets else None
    return None


def _name_with_initials(token: str, name_tokens: list[str], initials: set[str]) -> bool:
    """"siketr", "rsiket", "jdomajnko": a name with one or two initials of the person's other names, not a typo."""
    for n in name_tokens:
        for rest in (token.removeprefix(n) if token.startswith(n) else None, token.removesuffix(n) if token.endswith(n) else None):
            if rest and len(rest) <= 2 and all(ch in initials for ch in rest):
                return True
    return False
