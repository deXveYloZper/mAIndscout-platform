"""Company names: normalise, recognise non-companies, spot possible duplicates. Pure, no database.

A wrong merge of two companies poisons every alumnus, so matching here is exact after normalising;
anything fuzzier is only ever a suggestion for a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LEGAL_SUFFIXES = {
    "ltd", "limited", "llc", "llp", "inc", "incorporated", "corp", "corporation", "co", "company", "plc", "gmbh", "ag",
    "kg", "se", "sa", "sas", "sarl", "srl", "spa", "bv", "nv", "oy", "oyj", "ab", "as", "aps", "doo", "dd", "sro",
    "kft", "zrt", "spzoo", "pty", "pte", "group", "holding", "holdings",
}
SELF_EMPLOYED = {"self employed", "selfemployed", "freelance", "freelancer", "independent", "independent consultant",
                 "contractor", "self", "sole trader", "own company", "consulting freelance"}
UNDISCLOSED = {"confidential", "stealth", "stealth startup", "stealth mode", "undisclosed", "various", "n a", "na",
               "private client", "confidential client"}


@dataclass
class CompanyName:
    kind: str  # company | self_employed | undisclosed
    display: str  # cleaned name to show (without a trailing parenthetical)
    normalized: str  # the matching key
    note: str | None = None  # e.g. "(Entain)": a former or parent name, kept as a note, never an alias


def normalize(raw: str) -> CompanyName:
    text = " ".join((raw or "").split())
    note = None
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", text)
    if m and m.group(1).strip():
        text, note = m.group(1).strip(), m.group(2).strip()
    display = text.strip(" ,-·")
    key = display.lower().replace("&", " and ")
    key = re.sub(r"\bs\.?\s?p\.?\s?z\.?\s?o\.?\s?o\.?", " spzoo ", key)  # Polish "sp. z o.o."
    key = re.sub(r"\b(d\.o\.o|s\.r\.o|s\.r\.l|s\.a\.s|s\.a|b\.v|n\.v|a\.g|a/s)\b\.?", lambda x: x.group(0).replace(".", "").replace("/", ""), key)
    key = re.sub(r"[^a-z0-9]+", " ", key).split()
    while len(key) > 1 and key[-1] in LEGAL_SUFFIXES:
        key.pop()
    normalized = " ".join(key)
    if normalized in SELF_EMPLOYED or re.fullmatch(r"(self employed|freelance)( .*)?", normalized or ""):
        return CompanyName("self_employed", display, normalized, note)
    if not normalized or normalized in UNDISCLOSED:
        return CompanyName("undisclosed", display, normalized, note)
    return CompanyName("company", display, normalized, note)


def _distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def possibly_same(a: str, b: str) -> bool:
    """Normalised names that a human should look at: one is the other plus extra words ("bitpanda" /
    "bitpanda technology solutions"), or they differ by a typo in a long name. Never used to merge."""
    if a == b or not a or not b:
        return False
    ta, tb = a.split(), b.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short[0]) >= 4 and long_[: len(short)] == short:
        return True
    return min(len(a), len(b)) >= 6 and _distance(a, b) <= 1
