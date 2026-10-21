"""What a company uses in its own work, read from its own job adverts and careers pages (employer evidence, owner
2026-10-17). No database.

"If this company uses Node.js and the person hasn't mentioned it, it is reasonable to think they work with it" (the
owner): a company's adverts name its stack, its tools and its methods. One web search finds its adverts; a page counts
only when it is the company's own (its website) or an advert for it (its name in the address and in the text), so an
aggregator's other companies never lend it their stack. One model call lists what the pages say the company uses,
each with an exact quote that is checked against the page; nothing about any person is ever kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from maindscout.intelligence import spans
from maindscout.intelligence.exa import Found
from maindscout.intelligence.llm import LLMClient

READER_VERSION = "practices-2026-10-17.1"
KINDS = ["technology", "tool", "method", "standard"]
AREAS = ["engineering", "product_design", "commercial", "operations", "company_wide"]
MAX_PAGES = 3
PAGE_CHARS = 6000

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["page", "label", "token", "kind", "area", "mention", "quote"],
        "properties": {
            "page": {"type": "integer", "description": "the page number it is quoted from"},
            "label": {"type": "string", "description": "the name as the page writes it"},
            "token": {"type": "string", "description": "lowercase token, e.g. react, node.js, salesforce, sap ariba"},
            "kind": {"type": "string", "enum": KINDS},
            "area": {"type": "string", "enum": AREAS},
            "mention": {"type": "string", "enum": ["uses", "nice_to_have"],
                        "description": "uses: the company uses it or requires it for this role; nice_to_have: a bonus only"},
            "quote": {"type": "string", "description": "short EXACT quote from that page that names it"},
        }}}},
}

SYSTEM = (
    "You read pages published by or about ONE company for a recruiting desk: its own job adverts, careers or "
    "engineering pages. List what the pages say the company itself uses in its work: technologies (languages, "
    "frameworks, databases, cloud), tools (software products, e.g. Salesforce, SAP Ariba, Figma), methods (e.g. "
    "Scrum, MEDDIC) and standards (e.g. ISO 26262). A requirement in the company's own job advert counts: it "
    "describes the company's stack (mention 'uses'), a bonus or nice-to-have is 'nice_to_have'. For each item give "
    "the page number, the name as written, a lowercase token, its kind, the area of work it is used in "
    "(engineering, product_design, commercial, operations; company_wide when the page does not tie it to one team) "
    "and an EXACT quote from that page that names it. Never: benefits, office equipment, degrees, spoken languages, "
    "soft skills, years of experience, or anything about a person (no names, no people's titles). Never guess: leave "
    "out what the pages do not say."
)


@dataclass
class Item:
    page: int  # index into the pages read
    token: str
    raw_label: str
    kind: str
    area: str
    quote: str


@dataclass
class Reading:
    items: list[Item]
    rejected: list[dict[str, str]]
    cost: dict[str, Any] = field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def own_page(found: Found, name: str, domain: str | None) -> bool:
    """The company's own page (its website), or an advert for it: its name in the address and as a word in the text.
    A person's profile never counts."""
    url = urlparse(found.url)
    host = (url.hostname or "").lower().removeprefix("www.")
    if "linkedin.com" in host and "/in/" in url.path:
        return False
    if domain and (host == domain or host.endswith("." + domain)):
        return True
    slug = _slug(name)
    named = re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", found.text or "", re.I)
    return len(slug) >= 4 and slug in _slug(url.path) and bool(named)


def query(name: str, title: str | None) -> str:
    """The search for a company's adverts: its name and the kind of role, so the adverts are for the same work."""
    return " ".join(f"{name} {title or ''} job".split())


def read(pages: list[Found], name: str, client: LLMClient) -> Reading:
    """One model call over at most three pages; every item's quote must be on its page and must name the item."""
    pages = pages[:MAX_PAGES]
    if not pages:
        return Reading([], [])
    blocks = [f"Page {i}: {p.url}\n{p.title}\n\n{(p.text or '')[:PAGE_CHARS]}" for i, p in enumerate(pages, 1)]
    result = client.complete_json(SYSTEM, f"Company: {name}\n\n" + "\n\n---\n\n".join(blocks), SCHEMA, "company_practices")
    items: list[Item] = []
    rejected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in result.data.get("items", []):
        token = " ".join((raw.get("token") or "").lower().split())
        label = " ".join((raw.get("label") or "").split())
        quote = raw.get("quote") or ""
        page = raw.get("page")
        why = None
        if not isinstance(page, int) or not 1 <= page <= len(pages):
            why = "no such page"
        elif raw.get("mention") != "uses":
            why = "only a nice-to-have"
        elif raw.get("kind") not in KINDS or raw.get("area") not in AREAS:
            why = "unknown kind or area"
        elif not token or len(token) > 60 or not label:
            why = "no name"
        elif spans.locate((pages[page - 1].text or "")[:PAGE_CHARS], quote) is None:
            why = "the quote is not on the page"
        elif token not in quote.lower() and label.lower() not in quote.lower():
            why = "the quote does not name it"
        if why:
            rejected.append({"item": label[:80] or token[:80], "reason": why})
            continue
        if (token, raw["area"]) in seen:
            continue
        seen.add((token, raw["area"]))
        items.append(Item(page - 1, token, label[:120], raw["kind"], raw["area"], quote.strip()[:400]))
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return Reading(items, rejected, cost)
