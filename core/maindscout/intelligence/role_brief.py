"""The role brief: what one hire will really do, read from the job ad, the hiring manager's notes and public research on
the hiring company (owner, 2026-10-19: "read between the lines"; a Japanese brand building Europe needs someone
hands-on). One model call per role. No database.

Every line names where it comes from. When it says the ad, the notes or research, its quote must be written there
(checked); a quote that is not found makes the line our reading. A reading that changes whom to look for may carry
one short question for whoever uploaded the job; at most five questions in all. Never personality, culture or fit,
never protected characteristics, never a person's name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.domain.profile import LEVELS
from maindscout.intelligence.hiring import NOT_CRITERIA, _find
from maindscout.intelligence.llm import LLMClient

ROLE_BRIEF_PROMPT_VERSION = "2026-10-19.1"
# facet -> its fixed values (None: said in words only)
FACETS: dict[str, list[str] | None] = {
    "situation": None,
    "core_work": None,
    "team": ["works_alone", "small_team", "leads_a_team", "joins_a_team"],
    "hands_on": ["hands_on", "mixed", "manages_managers"],
    "market": ["entering", "growing", "established"],
    "reports_to": None,
    "level": LEVELS,
}
# Readings that change whom to look for: only these may carry a question.
DECIDING = ("team", "hands_on", "market", "reports_to", "level")
BASIS = ["ad", "notes", "research", "reading"]
MAX_QUESTIONS = 5

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["facets", "questions"],
    "properties": {
        "facets": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["facet", "value", "words", "basis", "quote"],
            "properties": {
                "facet": {"type": "string", "enum": list(FACETS)},
                "value": {"type": ["string", "null"], "description": "one of the facet's fixed values, or null"},
                "words": {"type": "string", "description": "the line in plain words, one sentence at most"},
                "basis": {"type": "string", "enum": BASIS},
                "quote": {"type": ["string", "null"], "description": "short EXACT quote from the text the basis names; null for reading"},
            }}},
        "questions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["facet", "question", "why"],
            "properties": {
                "facet": {"type": "string", "enum": list(FACETS)},
                "question": {"type": "string", "description": "one short, specific question for whoever uploaded the job"},
                "why": {"type": "string", "description": "how the answer changes whom to look for, in a few words"},
            }}},
    },
}

SYSTEM = (
    "You prepare a short brief of what ONE hire will really do, for a recruiting desk, from three texts: the job ad, the "
    "recruiter's notes from the hiring manager (maybe none), and public research on the hiring company. Read between "
    "the lines the way a senior headhunter would (a small brand building a new market needs someone who does the work "
    "themselves). Give each facet at most once:\n"
    "- situation: where the company stands, as it matters for this hire (its size, where its people are, whether it "
    "is entering or growing in the market this role serves), one sentence;\n"
    "- core_work: the work at the heart of the role, in a few words;\n"
    "- team: works_alone, small_team (leads one to a few people), leads_a_team (an existing team), joins_a_team;\n"
    "- hands_on: hands_on (does the work), mixed (leads and does), manages_managers;\n"
    "- market: the company's presence in the market this role serves: entering, growing, established;\n"
    "- reports_to: to whom and where, in a few words (a role or a place, never a person's name);\n"
    "- level: the level this scope implies, from the list.\n"
    "basis: notes, ad or research when that text says it, with a short EXACT quote from it; reading when you infer it "
    "(quote null). Prefer the notes over the ad, the ad over research. Leave a facet out when nothing supports even a "
    "reading. questions: for whoever uploaded the job, at most five, short and specific, only about facets whose basis "
    "is reading and only when the answer changes whom to look for (team, hands_on, market, reports_to, level). Never "
    "ask what the ad or the notes already answer. Never personality, attitude, culture or fit; never protected "
    "characteristics; never a person's name."
)


@dataclass
class Facet:
    facet: str
    value: str | None
    words: str
    basis: str
    quote: str | None
    start: int | None = None  # where the quote is, in the text its basis names
    end: int | None = None
    question: str | None = None
    why: str | None = None


@dataclass
class Brief:
    facets: list[Facet]
    rejected: list[dict[str, str]] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)

    def questions(self) -> list[Facet]:
        return [f for f in self.facets if f.question]


def user_text(ad: str, notes: str, research: str) -> str:
    return (f"Job ad:\n{(ad or '(none)')[:9000]}\n\nNotes from the hiring manager:\n{(notes or '(none)')[:6000]}\n\n"
            f"Public research on the hiring company:\n{(research or '(none)')[:4000]}")


def read(ad: str, notes: str, research: str, client: LLMClient) -> Brief:
    texts = {"ad": ad or "", "notes": notes or "", "research": research or ""}
    result = client.complete_json(SYSTEM, user_text(ad, notes, research), SCHEMA, "role_brief")
    facets: dict[str, Facet] = {}
    rejected: list[dict[str, str]] = []
    for raw in result.data.get("facets", []):
        name, words = raw.get("facet"), " ".join((raw.get("words") or "").split())[:400]
        if name not in FACETS or not words:
            rejected.append({"facet": str(name), "reason": "unknown facet or no words"})
            continue
        if name in facets:
            rejected.append({"facet": name, "reason": "said twice: the first is kept"})
            continue
        if NOT_CRITERIA.search(words):
            rejected.append({"facet": name, "reason": "personality, culture or fit is never part of a brief"})
            continue
        allowed = FACETS[name]
        value = raw.get("value")
        if allowed is None:
            value = None
        elif value is not None and value not in allowed:
            rejected.append({"facet": name, "reason": f"value {value!r} is not one of {allowed}"})
            continue
        # value None on a listed facet: said in words only ("any level"); code uses only a listed value.
        basis, quote, where = raw.get("basis"), (raw.get("quote") or "").strip() or None, None
        if basis in ("ad", "notes", "research"):
            where = _find(quote or "", texts[basis]) if quote else None
            if where is None:  # not written where it says: it is our reading, and says so
                rejected.append({"facet": name, "reason": f"quote not found in the {basis}: kept as our reading"})
                basis, quote = "reading", None
        elif basis != "reading":
            basis, quote = "reading", None
        else:
            quote = None
        facets[name] = Facet(name, value, words, basis, quote, *(where or (None, None)))
    asked = 0
    for q in result.data.get("questions", []):
        f = facets.get(q.get("facet"))
        text = " ".join((q.get("question") or "").split())[:300]
        if f is None or not text:
            rejected.append({"facet": str(q.get("facet")), "reason": "a question about a facet the brief does not have"})
        elif f.facet not in DECIDING or f.basis != "reading":
            rejected.append({"facet": f.facet, "reason": "only a reading that changes whom to look for is asked"})
        elif f.question or asked >= MAX_QUESTIONS:
            rejected.append({"facet": f.facet, "reason": "one question per line, five in all"})
        elif NOT_CRITERIA.search(text):
            rejected.append({"facet": f.facet, "reason": "personality, culture or fit is never asked"})
        else:
            f.question, f.why = text, " ".join((q.get("why") or "").split())[:300] or None
            asked += 1
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    order = list(FACETS)
    return Brief(sorted(facets.values(), key=lambda f: order.index(f.facet)), rejected, cost)


def research_text(name: str, profile: dict[str, Any] | None, facts: Any, signals: list[dict[str, Any]] | None = None) -> str:
    """The public research a brief may quote, written by code from the company's stored facts (so a quote with basis
    research can be checked against exactly this text)."""
    p = profile or {}
    lines = [f"{name}: {p.get('offering') or p.get('industry') or 'a company'}."]
    if p.get("about"):
        lines.append(re.sub(r"\s+", " ", p["about"])[:900])
    staff = p.get("employees") or (facts.team_min if facts is not None else None)
    if staff:
        lines.append(f"Staff: {staff} people.")
    countries = [c for c in p.get("countries") or [] if c.get("country")]
    if countries:
        lines.append("Where its people work: " + ", ".join(f"{c['country']} {c.get('pct')}%" for c in countries[:6]) + ".")
    if p.get("hq") or p.get("hq_country"):
        lines.append(f"Headquarters: {p.get('hq') or p.get('hq_country')}.")
    if facts is not None and facts.founded:
        lines.append(f"Founded: {facts.founded.year}.")
    if facts is not None and facts.rounds:
        lines.append("Funding: " + ", ".join(f"{s.replace('_', ' ')}{f' ({d:%Y-%m})' if d else ''}" for s, d in facts.rounds) + ".")
    for s in (signals or [])[:3]:
        lines.append(f"News: {s.get('quote')}")
    return "\n".join(lines)
