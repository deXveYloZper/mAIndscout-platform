"""The hiring company's competitors and similar companies, researched on the web (step D of understanding the hire,
owner 2026-10-21: "the LLM deep search into competitors and similar companies is a must, we should build a strong
understanding"). One Grok call with web search; every company must come with a page the search opened and a quote
from it that names the company. No people, ever. No database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maindscout.intelligence.research import SearchClient, _host, _same_page

COMPETITORS_PROMPT_VERSION = "2026-10-21.1"

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["companies"],
    "properties": {"companies": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "website", "why", "source_url", "quote", "staff_hint"],
        "properties": {
            "name": {"type": "string", "description": "the company's own name"},
            "website": {"type": ["string", "null"]},
            "why": {"type": "string", "description": "a few words: what it sells and to whom, why it competes"},
            "source_url": {"type": "string", "description": "a page you opened that names this company"},
            "quote": {"type": "string", "description": "short EXACT words from that page, naming the company"},
            "staff_hint": {"type": ["integer", "null"], "description": "about how many people work there, if a page says"}}}}}}

SYSTEM = (
    "You research a company's real competitors and similar companies for a recruiter, who will look for people to hire "
    "at them. A competitor sells the same kind of product to the same customers at a similar price level; a similar "
    "company is of a similar kind and size in the same market. Search the web well: the company's own site and press, "
    "trade press, market reports, lists of brands, the brands sold next to it by the same retailers and marketplaces, "
    "industry associations, fairs. Prefer companies of a similar size: never a group many times bigger (for a 60-person "
    "brand, not a 10,000-person fashion house), and nothing only loosely related. Give 25 to 40 companies when the market "
    "has them, fewer if it does not; never invent one. For each: its name, website, why in a few words, a page you opened "
    "that names it, a short exact quote from that page naming it, and its staff when a page says. Never research or "
    "name any person.")


@dataclass
class Competitor:
    name: str
    website: str | None
    why: str
    source_url: str
    quote: str
    staff_hint: int | None = None


@dataclass
class CompetitorsOutcome:
    companies: list[Competitor] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


def _names_it(name: str, quote: str) -> bool:
    """The quote names the company: its name, or its first long word ("IL BISONTE S.p.A." in "Il Bisonte bags")."""
    q, n = quote.lower(), name.lower().strip()
    first = next((w for w in n.replace(".", " ").split() if len(w) >= 4 and w not in ("group", "s.p.a", "spa", "srl", "ltd")), n)
    return n in q or first in q


def read(client_name: str, about: str, countries: list[str], client: SearchClient) -> CompetitorsOutcome:
    """`about`: what the desk knows of the hiring company (what it sells, its size, where), never a person."""
    where = ", ".join(countries) or "its markets"
    user = (f"Company: {client_name}\nWhat we know about it: {about or 'nothing more'}\n"
            f"Find its competitors and similar companies, with people in {where}.")
    data, visited, cost = client.search_json(SYSTEM, user, SCHEMA, "competitors")
    out = CompetitorsOutcome(visited=visited, cost=cost)
    seen: set[str] = set()
    for raw in data.get("companies") or []:
        name = (raw.get("name") or "").strip()
        url, quote = (raw.get("source_url") or "").strip(), (raw.get("quote") or "").strip()
        if not name or name.lower() == client_name.lower() or name.lower() in seen:
            continue
        if not any(_same_page(url, v) or _host(url) == _host(v) for v in visited):
            out.rejected.append({"company": name, "reason": "its page was not one the search opened"})
            continue
        if not quote or not _names_it(name, quote):
            out.rejected.append({"company": name, "reason": "the quote does not name it"})
            continue
        seen.add(name.lower())
        hint = raw.get("staff_hint")
        out.companies.append(Competitor(name, (raw.get("website") or None), (raw.get("why") or "").strip()[:160], url,
                                        quote[:300], hint if isinstance(hint, int) and hint > 0 else None))
    return out
