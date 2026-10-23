"""The hiring company's competitors and similar companies, researched on the web (step D of understanding the hire,
owner 2026-10-21: "the LLM deep search into competitors and similar companies is a must, we should build a strong
understanding"). One Grok call with web search; every company must come with a page the search opened and a quote
from it that names the company. No people, ever. No database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maindscout.intelligence.research import SearchClient, _host, _same_page

COMPETITORS_PROMPT_VERSION = "2026-10-22.1"

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["business_lines", "companies"],
    "properties": {
        "business_lines": {"type": "array", "items": {"type": "string"},
                           "description": "every line of business the company has today, each in a few words"},
        "companies": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "website", "line", "why", "source_url", "quote", "staff_hint"],
            "properties": {
                "name": {"type": "string", "description": "the company's own name"},
                "website": {"type": ["string", "null"]},
                "line": {"type": "string", "description": "which business line it competes in, or 'talent' for a company "
                                                           "whose people do the role's work for the same kind of customers"},
                "why": {"type": "string", "description": "a few words: what it sells and to whom, why it competes"},
                "source_url": {"type": "string", "description": "a page you opened that names this company"},
                "quote": {"type": "string", "description": "short EXACT words from that page, naming the company"},
                "staff_hint": {"type": ["integer", "null"], "description": "about how many people work there, if a page says"}}}}}}

SYSTEM = (
    "You research a company's real competitors and similar companies for a recruiter, who will look for people to hire "
    "at them. First establish every line of business the company has today, including recent ones (a carmaker that "
    "also sells a fashion collection and lifestyle goods, a bank with an asset manager). Then, for each line, find its "
    "competitors (the same kind of product, to the same customers, at a similar price level) and similar companies (of "
    "a similar kind and size in the same market). When a role is given, also include companies whose people do that "
    "work for the same kind of customers (for a CRM role at a luxury brand, other luxury brands with client and CRM "
    "teams), with line 'talent'. Search the web well: the company's own site and press, trade press, market reports, "
    "lists of brands, the brands sold next to it by the same retailers and marketplaces, industry associations, fairs. "
    "Prefer companies of a similar size: never a group many times bigger (for a 60-person brand, not a 10,000-person "
    "fashion house), and nothing only loosely related. Give 25 to 40 companies when the market has them, fewer if it "
    "does not; never invent one. For each: its name, website, its line, why in a few words, a page you opened that "
    "names it, a short exact quote from that page naming it, and its staff when a page says. Never research or name "
    "any person.")


@dataclass
class Competitor:
    name: str
    website: str | None
    why: str
    source_url: str
    quote: str
    staff_hint: int | None = None
    quoted: bool = True  # the quote names it
    line: str | None = None  # the business line it competes in, or 'talent'


@dataclass
class CompetitorsOutcome:
    companies: list[Competitor] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)  # the client's lines of business, as the research found them


GENERIC = {"group", "s.p.a", "spa", "srl", "s.r.l", "ltd", "gmbh", "italia", "italy", "milano", "firenze", "leather",
           "the", "company", "brand", "brands", "bags", "fashion", "design"}


def _names_it(name: str, quote: str) -> bool:
    """The quote names the company: its name, or one of its own long words ("Il Bisonte" for "IL BISONTE S.p.A.",
    "Chiarini" for "Gianni Chiarini"), never a word any company could have ("Italia", "leather")."""
    q, n = quote.lower(), name.lower().strip()
    own = [w for w in n.replace(".", " ").replace("&", " ").split() if len(w) >= 4 and w not in GENERIC]
    return n in q or any(w in q for w in own)


# The talent map (owner, 2026-10-23: "our understanding of Ferrari, apart from its competitors but also pool of
# companies we should find, is thin ... Luxury is Luxury"): first the pools of companies where the people for this
# role work, across industries; then each pool is researched in rounds of its own.
POOLS_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["business_lines", "pools"],
    "properties": {
        "business_lines": {"type": "array", "items": {"type": "string"},
                           "description": "every line of business the company has today, each in a few words"},
        "pools": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "why", "examples"],
            "properties": {
                "name": {"type": "string", "description": "the pool in a few words, e.g. 'luxury jewellery and watches'"},
                "why": {"type": "string", "description": "why people for this role are found there"},
                "examples": {"type": "array", "items": {"type": "string"}, "description": "three to six real company names"}}}}}}

POOLS_SYSTEM = (
    "You plan where a recruiter should look for people for a role. First establish every line of business the hiring "
    "company has today, including recent ones (a carmaker that also sells fashion and lifestyle goods). Then list the "
    "pools of companies where people who could do this role work: the client's direct competitors for each line, and "
    "every other industry whose companies serve the same kind of customer at the same level, with the same kind of "
    "work. Positioning carries across industries: for a luxury brand, luxury in every industry is a pool (luxury cars, "
    "luxury fashion and leather goods, luxury jewellery and watches, luxury beauty and fragrance, luxury hospitality, "
    "luxury e-commerce and retail); for a deep-tech start-up, deep-tech companies of every kind. Six to ten pools, most "
    "relevant first, each with why and three to six real example companies. Search the web to know the company well. "
    "Never research or name any person.")


@dataclass
class Pools:
    lines: list[str] = field(default_factory=list)
    pools: list[dict[str, Any]] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


def pools(client_name: str, about: str, countries: list[str], client: SearchClient, role: str | None = None) -> Pools:
    """The client's lines of business and the role's talent pools (one web search call)."""
    where = ", ".join(countries) or "its markets"
    user = (f"Company: {client_name}\nWhat we know about it: {about or 'nothing more'}\n"
            + (f"The role we are filling: {role}\n" if role else "")
            + f"The people must live in: {where}.")
    data, _visited, cost = client.search_json(POOLS_SYSTEM, user, POOLS_SCHEMA, "talent_pools")
    found = []
    for raw in (data.get("pools") or [])[:10]:
        name = (raw.get("name") or "").strip()
        if name:
            found.append({"name": name[:80], "why": (raw.get("why") or "").strip()[:200],
                          "examples": [str(e)[:60] for e in (raw.get("examples") or [])][:6]})
    return Pools([str(x)[:80] for x in data.get("business_lines") or []][:12], found, cost)


def pool_angle(pool: dict[str, Any], deeper: bool) -> str:
    """One pool's round: only its companies; a deeper round asks for the smaller and less obvious names."""
    text = (f"Only this pool: {pool['name']} ({pool['why']}). List every company in it with people in the places "
            f"given, as many as the market has, e.g. {', '.join(pool['examples'][:4])}; mark each with line "
            f"'{pool['name']}'.")
    if deeper:
        text += " Look further: smaller, younger and less obvious names in this pool, not the best known."
    return text


# A deeper round asks again, told what is already known, from another side of the market (owner, 2026-10-21: "we
# should however search harder from extended list of competitors").
ANGLES = [None,
          "Look further than the first lists: smaller and younger brands, direct-to-consumer and online brands, brands "
          "sold by the same retailers and marketplaces, makers in the same districts.",
          "Look at the neighbouring markets: brands selling similar products to the same customers in other categories "
          "or from nearby countries, with people in the same places."]


def read(client_name: str, about: str, countries: list[str], client: SearchClient, known: list[str] | None = None,
         angle: str | None = None, role: str | None = None) -> CompetitorsOutcome:
    """`about`: what the desk knows of the hiring company (what it sells, its size, where), never a person. `known`:
    companies already listed, so a round finds others. `role`: the role being filled and its kind of work, so the
    places such people work are found too (owner, 2026-10-22: Ferrari's CRM role and the fashion houses)."""
    where = ", ".join(countries) or "its markets"
    user = (f"Company: {client_name}\nWhat we know about it: {about or 'nothing more'}\n"
            + (f"The role we are filling: {role}\n" if role else "")
            + f"Find its competitors and similar companies, with people in {where}.")
    if known:
        user += "\nAlready known, do not repeat them, find others: " + "; ".join(known[:80])
    if angle:
        user += "\n" + angle
    skip = {k.lower() for k in known or []}
    data, visited, cost = client.search_json(SYSTEM, user, SCHEMA, "competitors")
    out = CompetitorsOutcome(visited=visited, cost=cost, lines=[str(x)[:80] for x in data.get("business_lines") or []][:12])
    seen: set[str] = set()
    for raw in data.get("companies") or []:
        name = (raw.get("name") or "").strip()
        url, quote = (raw.get("source_url") or "").strip(), (raw.get("quote") or "").strip()
        if not name or name.lower() == client_name.lower() or name.lower() in seen or name.lower() in skip:
            continue
        if not any(_same_page(url, v) or _host(url) == _host(v) for v in visited):
            out.rejected.append({"company": name, "reason": "its page was not one the search opened"})
            continue
        seen.add(name.lower())
        hint = raw.get("staff_hint")
        # A quote that does not name it is not proof on its own; the caller keeps it only if Exa confirms the company.
        out.companies.append(Competitor(name, (raw.get("website") or None), (raw.get("why") or "").strip()[:160], url,
                                        quote[:300], hint if isinstance(hint, int) and hint > 0 else None,
                                        quoted=bool(quote) and _names_it(name, quote), line=(raw.get("line") or None)))
    return out
