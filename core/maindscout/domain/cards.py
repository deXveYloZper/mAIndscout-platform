"""A suggestion's card in a few words (step E of understanding the hire; owner, 2026-10-20: "too much information"):
why they fit, what a possible match is short of, and what to settle on the call, all read from their stored match.
Pure: no database, no model. Never a score, and nothing their match does not already say; every row stays on their
page behind the card.
"""

from __future__ import annotations

import re
from typing import Any

from maindscout.domain.geo import in_city, only_country

MUST = ("must", "deal_breaker")


def _years(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".") + (" year" if round(x, 1) == 1 else " years")


def short(detail: str | None) -> str:
    """A match row's detail, short enough for a card. "4.7 years in luxury / fashion / beauty, travel / hospitality
    (luxury companies only)" -> "4.7 years in luxury"; "4.7 years at companies making leather goods, leather, bags
    (Prada Group)" -> "4.7 years at leather goods companies (Prada Group)". The first part only ("…; about 12 years
    across 9 jobs" is dropped) and no caveat in brackets that only the full row needs."""
    d = (detail or "").split("; ")[0]
    # The gap table's "likely" (their employer's own job advert names it): "React only likely: Tacto uses it, not in their file".
    d = re.sub(r"^not in their file, but (.+?) uses (.+?) \(its job advert[^)]*\) and they (?:work|worked) there as .+?: likely, "
               r"confirm on the call$", r"\2 only likely: \1 uses it, not in their file", d)
    d = re.sub(r"\s*\((luxury companies only|as far as research shows)\)", "", d)
    d = re.sub(r"^(no time|[\d.]+ years?) in ([^,/(]+?)\s*[/,].*$", r"\1 in \2", d)  # the first industry named
    d = re.sub(r"companies making ([^,(]+?)(?:,[^(]*?)?(\s*\(|$)", r"\1 companies\2", d)
    return re.sub(r"\s+", " ", d).strip()


def work_line(work: dict[str, Any] | None) -> str | None:
    """Years in their kind of work and their level, from the career profile: "11.5 years in marketing, manager"."""
    if not work or not work.get("years") or work.get("label") in (None, "unknown"):
        return None
    level = work.get("level")
    return f"{_years(float(work['years']))} in {work['label']}" + (f", {level}" if level and level != "unknown" else "")


def why(rows: list[dict[str, Any]], work: dict[str, Any] | None, tier: str | None = None) -> list[str]:
    """Their work and level, then each strong plus they meet, in the role's order."""
    if tier == "unclear":
        return ["being read: rated once their career reading arrives, never strong before"]
    out = [w for w in [work_line(work)] if w]
    for r in rows:
        if r.get("strength") == "strong_plus" and r.get("verdict") == "strong":
            s = short(r.get("detail"))
            if s and s not in out:
                out.append(s)
    return out


def short_of(rows: list[dict[str, Any]]) -> list[str]:
    """What keeps a match from strong: must-haves that are gaps or only partly met, then strong-plus items they miss."""
    musts = [r for r in rows if r.get("strength") in MUST and r.get("verdict") in ("gap", "partial")]
    plus = [r for r in rows if r.get("strength") == "strong_plus" and r.get("verdict") in ("gap", "partial")]
    out: list[str] = []
    for r in musts + plus:
        s = short(r.get("detail")) or (r.get("requirement") or "")
        s = f"{s} (partly)" if r.get("verdict") == "partial" and "partly" not in s and "likely" not in s else s
        if s and s not in out:
            out.append(s)
    return out


def _town(place: str) -> str:
    """ "Rome, Latium, Italy" -> "Rome, Italy"; "Munich" -> "Munich"."""
    parts = [p.strip() for p in place.split(",") if p.strip()]
    return f"{parts[0]}, {parts[-1]}" if len(parts) >= 3 else ", ".join(parts)


def settle(residence: tuple[str, str] | None, place: str | None, cities: list[str], reach: str | None = None) -> list[str]:
    """What only the call can settle and could change the decision: a current job above the role (a reach), and living
    outside the country or city the role asks for. Not every question: the call brief has those.

    `residence`: the gap table's (status, detail) for the role's "where people must live"; `cities`: the cities that
    requirement names."""
    out: list[str] = []
    if reach:
        out.append(reach.rstrip("."))
    where = " or ".join(cities)
    if residence is not None and residence[0] == "question":
        out.append("where they live is not known" if "does not say where" in residence[1] else residence[1])
    elif in_city(place, cities) is False:
        town = _town(place or "")
        # "Italy" alone may well be Milan: the city is what to ask, not a sign they live elsewhere.
        out.append(f"lives in {town}, city not known; the role is in {where}" if only_country(place) else f"lives in {town}; the role is in {where}")
    return out


def place_words(place: str | None) -> str | None:
    """Where they live, short for the card's main line."""
    return _town(place) if place else None
