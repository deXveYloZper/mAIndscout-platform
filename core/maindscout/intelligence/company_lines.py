"""A company's lines of business, each described along a few dimensions (owner, 2026-10-26: "how deep does the tags
go, is it just general or does it also go deeper into more specific domains?"). One model call per batch of companies,
no web search, read only from what the desk already holds about each (its Exa profile, and for a hiring company the
lines its research found). Every line must quote the words that support it, or it is dropped.

The dimensions, for every company in every field:
- industry: the broad field, from the fixed list careers are counted in ("luxury / fashion / beauty", "procurement");
- market: what it sells, as specific as the text allows ("apparel", "leather goods", "source-to-pay software", "AI
  procurement automation", "cross-border B2B payments");
- positioning: the level it sells at (luxury, premium, mainstream, budget; for business software: enterprise,
  mid-market, small business);
- customers: consumers, businesses, both, or the public sector.

They add, order and explain; they never leave a company out by themselves (owner: "we shouldn't start our searches
from the deepest, but do have an option if we want to reach more specific person").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maindscout.domain.profile import DOMAINS
from maindscout.intelligence.llm import LLMClient

LINES_PROMPT_VERSION = "2026-10-26.1"
POSITIONING = ["luxury", "premium", "mainstream", "budget", "enterprise", "mid-market", "small business", "unknown"]
CUSTOMERS = ["consumers", "businesses", "both", "public sector", "unknown"]
BATCH = 25

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["companies"],
    "properties": {"companies": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["number", "lines"],
        "properties": {
            "number": {"type": "integer", "description": "the company's number in the list"},
            "lines": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["line", "industry", "market", "positioning", "customers", "basis"],
                "properties": {
                    "line": {"type": "string", "description": "the line of business in a few words"},
                    "industry": {"type": "string", "enum": DOMAINS},
                    "market": {"type": "string", "description": "what it sells, as specific as the text allows"},
                    "positioning": {"type": "string", "enum": POSITIONING},
                    "customers": {"type": "string", "enum": CUSTOMERS},
                    "basis": {"type": "string", "description": "EXACT words from that company's text that support this line"}}}}}}}}}

SYSTEM = (
    "You describe companies for a recruiter, from the text given for each and nothing else. For each company give its "
    "lines of business, one to four, the main one first; a company that sells one thing has one line. For each line: "
    "its industry, from the list; its market, meaning what it sells, as specific as the text allows (e.g. 'apparel', "
    "'leather goods', 'fine jewellery', 'watches', 'sports cars', 'source-to-pay software', 'AI procurement automation', "
    "'cross-border B2B payments'; never just 'software' or 'products' when the text says more); its positioning, the "
    "level it sells at (luxury, premium, mainstream or budget for what people buy; enterprise, mid-market or small "
    "business for what companies buy), or unknown when the text does not say; its customers; and the basis: short "
    "EXACT words from that company's text that support the line. Never use a customer's industry as the company's own "
    "(software sold to car makers is software, not automotive). Never invent a line the text does not support.")


@dataclass
class Line:
    line: str
    industry: str
    market: str
    positioning: str
    customers: str
    basis: str


@dataclass
class Outcome:
    lines: dict[int, list[Line]] = field(default_factory=dict)  # number in the batch -> its lines
    rejected: list[dict[str, Any]] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


def text_block(number: int, name: str, profile: dict[str, Any] | None, extra: list[str] | None = None) -> str:
    """What the model may read about one company."""
    p = profile or {}
    parts = [f"[{number}] {name}"]
    for label, key in (("Industry", "industry"), ("Sells", "offering"), ("About", "about")):
        if p.get(key):
            parts.append(f"{label}: {str(p[key])[:700]}")
    if p.get("categories"):
        parts.append("Categories: " + ", ".join(str(c) for c in p["categories"][:12]))
    if extra:
        parts.append("Lines of business found by research: " + "; ".join(extra[:8]))
    return "\n".join(parts)


def supported(basis: str | None, text: str) -> bool:
    """The basis is the company's own words: every part of it (the model often joins several phrases with commas)
    appears in that company's text."""
    import re

    parts = [" ".join(x.lower().split()) for x in re.split(r"[,;]|\s[-–]\s", basis or "")]
    parts = [x.strip(" .'\"") for x in parts if len(x.strip(" .'\"")) >= 3]
    return bool(parts) and all(x in text for x in parts)


def classify(blocks: list[tuple[int, str]], client: LLMClient) -> Outcome:
    """`blocks`: (number, text) for up to BATCH companies. A line whose basis is not in its company's text is dropped."""
    result = client.complete_json(SYSTEM, "\n\n".join(text for _, text in blocks), SCHEMA, "company_lines")
    texts = {n: " ".join(t.lower().split()) for n, t in blocks}
    out = Outcome(cost={"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                        "usd": result.usd})
    for item in result.data.get("companies") or []:
        n = item.get("number")
        if n not in texts:
            continue
        for raw in (item.get("lines") or [])[:4]:
            if not supported(raw.get("basis"), texts[n]):
                out.rejected.append({"number": n, "line": raw.get("line"), "reason": "its words are not in the text"})
                continue
            market = (raw.get("market") or "").strip().lower()[:80]
            if not market:
                continue
            out.lines.setdefault(n, []).append(Line(
                (raw.get("line") or market).strip()[:80], raw.get("industry") if raw.get("industry") in DOMAINS else "other",
                market, raw.get("positioning") if raw.get("positioning") in POSITIONING else "unknown",
                raw.get("customers") if raw.get("customers") in CUSTOMERS else "unknown", (raw.get("basis") or "").strip()[:300]))
    return out
