"""A company's domain: the markets it serves, read from its own description. No database.

Exa's company page gives an industry ("Software Development") and category tags sorted alphabetically ("ai, artificial
intelligence (ai), automation, b2b, …"): neither says that a company is in procurement or cybersecurity. A small model
call reads each company's description and names 1 to 3 markets it serves, never a technology, plus what it offers in a
few words, each with an exact quote from that company's text. Code keeps only what its quote supports, and drops
technology words. Owner (2026-10-13): "what is their domain: are they security, are they procurement, or something else".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DOMAIN_PROMPT_VERSION = "2026-10-13.1"
BATCH = 20
GENERIC = {
    "ai", "artificial intelligence", "artificial intelligence (ai)", "machine learning", "ml", "software", "saas", "cloud",
    "automation", "b2b", "b2c", "enterprise", "enterprise software", "technology", "technologies", "tech", "internet",
    "platform", "platforms", "application software", "application-software", "data", "analytics", "data analytics",
    "digital", "digital transformation", "it", "it services", "information technology", "business services", "consulting",
    "startup", "start-up", "mobile", "web", "api", "integrations", "innovation", "services", "solutions", "agents", "ai agents",
    "generative ai", "llm", "computer software", "software development", "technology, information and internet",
}
SYSTEM = (
    "Each company below is described by its own profile text. For each company: (1) name 1 to 3 domains: the markets or "
    "industries it serves or works in, such as procurement, supply chain, payments, cybersecurity, earth observation, "
    "insurance, logistics, healthcare, energy, automotive, defence, recruiting. Never a technology or a way of working: not "
    "AI, software, SaaS, cloud, automation, data, platform, B2B, agents. (2) say what it offers in a few words (at most 8), "
    "for example 'procurement automation platform' or 'satellite radar imaging'. For every domain and for the offering, "
    "give a short EXACT quote from that company's own text that shows it. If its text does not say, return no domains. "
    "Answer for every key given, in the same order."
)
SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["companies"],
    "properties": {"companies": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["key", "offering", "offering_quote", "domains"],
        "properties": {
            "key": {"type": "string"},
            "offering": {"type": ["string", "null"]},
            "offering_quote": {"type": ["string", "null"]},
            "domains": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["domain", "quote"],
                "properties": {"domain": {"type": "string"}, "quote": {"type": "string"}}}},
        }}}},
}


@dataclass
class Reading:
    domains: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    offering: str | None = None
    offering_quote: str | None = None


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("’", "'").split())


def generic(word: str) -> bool:
    w = _norm(word).strip(" .,;:-")
    return w in GENERIC or not re.search(r"[a-z]", w)


def user_text(items: list[tuple[str, str, str]]) -> str:
    return "\n\n".join(f"### key: {key}\nname: {name}\n{text[:1500]}" for key, name, text in items)


def check(items: list[tuple[str, str, str]], data: dict[str, Any]) -> dict[str, Reading]:
    """Keep what each quote supports: the quote is in that company's text, and a domain is not a technology."""
    texts = {key: _norm(text) for key, _, text in items}
    out: dict[str, Reading] = {}
    for row in data.get("companies") or []:
        key = row.get("key")
        if key not in texts:
            continue
        r = Reading()
        for d in row.get("domains") or []:
            domain, quote = _norm(d.get("domain") or "").strip(" .,;:"), d.get("quote") or ""
            if 3 <= len(domain) <= 40 and not generic(domain) and quote and _norm(quote) in texts[key] and domain not in r.domains:
                r.domains.append(domain)
                r.quotes.append(quote.strip())
        offering, oq = (row.get("offering") or "").strip(), row.get("offering_quote") or ""
        if offering and len(offering.split()) <= 8 and oq and _norm(oq) in texts[key]:
            r.offering, r.offering_quote = offering, oq.strip()
        out[key] = r
        r.domains, r.quotes = r.domains[:3], r.quotes[:3]
    return out


def fallback(categories: list[str]) -> list[str]:
    """Without a model: the category tags that are not technology words (they may still be broad)."""
    out = []
    for c in categories:
        c = _norm(c.split("/")[-1].replace("_", " ").replace("-", " "))
        if not generic(c) and c not in out:
            out.append(c)
    return out[:2]
