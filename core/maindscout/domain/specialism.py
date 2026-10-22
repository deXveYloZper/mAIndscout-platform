"""A role's specialism: work narrower than its broad family, read from the ad's own words (owner, 2026-10-22: "CRM
should have been clear as the JD mentions Salesforce, which is a CRM"). Pure, no database.

The broad families (marketing, customer success, data…) come from the model's reading and stay as they are; a
specialism sharpens three things:
- the searches: its own titles ("CRM specialist", "Salesforce administrator"), not the family's ("account manager");
- the broad search at a small company ("CRM", not "customer success");
- matching: a person whose title says the specialism does that work, whatever family their career was filed under
  (a CRM manager read as marketing, a Salesforce administrator read as IT support).
"""

from __future__ import annotations

import re
from typing import Iterable

# name -> (words in an ad or a title that say it, the titles to search, the broad search word)
SPECIALISMS: dict[str, tuple[str, list[str], str]] = {
    "crm": (r"\bcrm\b|salesforce|hubspot|dynamics 365|microsoft dynamics|clienteling|client (data|relationship management)|"
            r"customer (data|relationship management)|\bcdp\b|marketing cloud|\bbraze\b|\bsfmc\b",
            ["CRM specialist", "CRM manager", "Salesforce administrator", "CRM analyst"], "CRM"),
}


def of_role(texts: Iterable[str | None]) -> str | None:
    """The specialism an ad's title and requirements name, or None."""
    blob = " ".join(t for t in texts if t)
    for name, (words, _, _) in SPECIALISMS.items():
        if re.search(words, blob, re.I):
            return name
    return None


def titles(name: str | None) -> list[str]:
    return list(SPECIALISMS[name][1]) if name in SPECIALISMS else []


def broad_word(name: str | None) -> str | None:
    return SPECIALISMS[name][2] if name in SPECIALISMS else None


def title_says(name: str | None, title: str | None) -> bool:
    """Does a job title say this specialism ("CRM Manager", "Salesforce Administrator", "Clienteling Lead")?"""
    return bool(name in SPECIALISMS and title and re.search(SPECIALISMS[name][0], title, re.I))
