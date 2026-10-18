"""A client's market tier: a luxury brand recruits from luxury, also in the next industry (owner, 2026-10-18: "buonaventura
is a high luxury, so high luxury hospitality should be fine, not low level ... there needs to be that type of
synonyms"). Pure, no database.

- **A luxury role**: its own requirements say so ("luxury", "high-end", "haute couture", "premium fashion"…).
- **A luxury company**: it says so of itself, in its offering, its about text, its industry or its industry words
  ("luxury hotels", "4 and 5-star hotels", "Retail Luxury Goods and Jewelry"); or it is a fashion, beauty, accessories,
  jewellery or eyewear house, which the luxury industry is made of (Armani never writes the word). Categories that sell
  ("luxury travel" on a tour operator) do not count.
- **Searching**: a luxury role's industries are searched in luxury words ("luxury hotels, five-star hotel groups and
  high-end hospitality companies in Italy", not "travel and hospitality companies").
- **Matching**: years in an industry outside luxury itself (hotels, travel…) count only at luxury companies.
"""

from __future__ import annotations

import re
from typing import Any

LUXURY = re.compile(r"\b(luxury|luxe|high[- ]end|haute couture|five[- ]star|5[- ]star|upscale|palace hotels?|prestige|lusso)\b", re.I)
LUXURY_HOUSE = re.compile(r"\b(fashion|apparel|couture|beauty|cosmetics?|fragrances?|perfumes?|jewel(le)?ry|accessories|leather|"
                          r"eyewear|watch(es|making)?)\b", re.I)
# A hotel's stars are its tier, whatever its copy says ("Domina Hotels is a 4-star hotel and resort company ... a new way
# of experiencing luxury").
TOP_STARS = re.compile(r"\b(5|five)[- ]stars?\b", re.I)
LOWER_STARS = re.compile(r"\b([1-4]|one|two|three|four)[- ]stars?\b", re.I)
INHERENT = "luxury / fashion / beauty"  # the industry that is luxury itself; every other one needs the tier shown
# How each industry is searched for a luxury client (the "synonyms"); any other industry gets "luxury" in front.
# Each is followed by "companies in <place>". Luxury itself is already said in luxury words.
SEARCH_WORDS = {
    "travel / hospitality": "luxury hotels, five-star hotel groups and high-end hospitality",
    "automotive / mobility": "luxury and premium automotive",
    "e-commerce": "luxury e-commerce",
    "retail": "luxury retail",
    "media / entertainment": "luxury and fashion media",
}


def luxury_role(texts: list[str]) -> bool:
    """Do the role's own requirements ask for luxury? (A fashion role without the word is not a luxury role.)"""
    return any(LUXURY.search(t or "") for t in texts)


def search_words(domain: str, words: str) -> str:
    """The words a luxury client's industry is searched with: its synonyms, or "luxury" in front."""
    if domain in SEARCH_WORDS:
        return SEARCH_WORDS[domain]
    return words if LUXURY.search(words) else f"luxury {words}"


def luxury_company(exa_profile: dict[str, Any] | None, domains: list[str] | None = None) -> bool | None:
    """True when the company is a luxury company by its own words or a fashion / beauty house; False when it is
    known and is not; None when nothing is known about it."""
    p = exa_profile or {}
    words = list(domains or []) + list(p.get("domains") or [])
    own = " ".join([p.get("offering") or "", p.get("about") or "", p.get("industry") or "", " ".join(words)])
    if not own.strip():
        return None
    if LOWER_STARS.search(own) and not TOP_STARS.search(own):
        return False
    return bool(LUXURY.search(own) or LUXURY_HOUSE.search(" ".join(words) + " " + (p.get("industry") or "")))
