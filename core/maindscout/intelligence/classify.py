"""Classify each career step on a CV in one model call: kind of work, level, industry, stated signals. No database.

The model reads the CV text and a numbered list of the steps already extracted, and labels each step from fixed
lists. Checks: a step id must be one we sent; a signal is kept only if its quote is written in the CV; domains are
industries, never technologies (owner's rule). Facts it cannot see are left empty, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.domain.profile import DOMAINS, LEVELS, ROLE_FAMILIES, SIGNALS
from maindscout.intelligence.llm import LLMClient

CLASSIFY_PROMPT_VERSION = "2026-10-04.3"

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["steps"],
    "properties": {"steps": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "role_family", "level", "domains", "signals"],
        "properties": {
            "id": {"type": "string"},
            "role_family": {"type": "string", "enum": ROLE_FAMILIES},
            "level": {"type": ["string", "null"], "enum": LEVELS + [None]},
            "domains": {"type": "array", "items": {"type": "string", "enum": DOMAINS},
                        "description": "1-3 industries the employer or the work served, most important first"},
            "signals": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["kind", "quote"],
                "properties": {"kind": {"type": "string", "enum": SIGNALS}, "quote": {"type": "string"}}}},
        }}}},
}

SYSTEM = (
    "You label the jobs on one CV for a recruiting desk. For each numbered step decide, from what the CV says: "
    "role_family (the kind of work actually done, not only the title; a waiter is hospitality, a backend developer is "
    "software_engineering, an InSAR or GIS analyst is gis_remote_sensing); level, read from the TITLE WORDS first: "
    "Intern/Student/Placement -> intern, Junior/Graduate/Associate -> junior, no level word -> mid, Senior -> senior, "
    "Lead/Staff/Team Leader -> lead, Principal -> principal, Manager -> manager, Head of -> head, Director/VP -> "
    "director, C-level -> executive, Founder/Co-founder -> founder; use the described responsibilities only when the "
    "title has no level word AND the CV states it plainly (e.g. 'led a team of five' -> lead); "
    "domains (1-3 industries the work served, from the given list, MOST IMPORTANT FIRST: for a product company, the "
    "industry its product serves (use the public research given for the company); 'it services / consulting' ONLY "
    "when the employer itself is an IT services or consulting firm, and then put the client's industry first if the "
    "CV names it; never technologies); level (give your best reading; the title decides it in the end); signals, ONLY when the CV states them, "
    "each with a short EXACT quote from the CV: founder (founded or co-founded the company), first_hire (one of the "
    "first employees or founding engineer), people_manager (managed people), team_lead (led a team), promotion "
    "(promoted within the company). Do not judge personality, attitude, culture or fit. Never guess."
)


@dataclass
class StepLabel:
    claim_id: str
    role_family: str
    level: str | None
    domains: list[str]
    signals: list[str]
    quotes: dict[str, str] = field(default_factory=dict)


@dataclass
class ClassifyOutcome:
    labels: list[StepLabel]
    rejected: list[dict[str, str]]
    cost: dict[str, Any]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# Level from the title words, by code (predictable; the model is not asked to judge it). First match wins.
TITLE_LEVELS = [
    ("founder", r"\b(co-?founder|founder|founding partner)\b"),
    ("executive", r"\b(ceo|cto|cfo|coo|cpo|chief)\b"),
    ("director", r"\b(director|vp|vice president)\b"),
    ("head", r"\bhead of\b|\bhead\b"),
    ("principal", r"\bprincipal\b"),
    ("lead", r"\b(lead|staff|team leader|tech lead)\b"),
    ("manager", r"\bmanager\b"),
    ("senior", r"\b(senior|sr)\b"),
    ("junior", r"\b(junior|jr|graduate|associate|trainee|apprentice)\b"),
    ("intern", r"\b(intern|internship|student|placement|undergraduate|werkstudent)\b"),
]


def title_level(title: str, signals: list[str] | None = None) -> str:
    """The level a title states; no level word means mid. Leading a team without the title shows as a notable
    signal, never as a higher level (signals are kept for that)."""
    lowered = title.lower()
    for level, rx in TITLE_LEVELS:
        if re.search(rx, lowered):
            return level
    return "mid"


TECH_WORDS = re.compile(r"\b(python|java|javascript|typescript|react|node|aws|azure|gcp|kubernetes|docker|sql|c\+\+|golang|rust|"
                        r"\.net|php|ruby|kotlin|swift|terraform|spark|tensorflow|pytorch)\b", re.I)


def classify_steps(cv_text: str, steps: list[dict[str, Any]], client: LLMClient) -> ClassifyOutcome:
    """`steps`: [{"claim_id", "company", "title", "start", "end", "employment_type"}] in CV order."""
    if not steps:
        return ClassifyOutcome([], [], {"usd": 0})
    ids = {f"s{i + 1}": s["claim_id"] for i, s in enumerate(steps)}
    listing = "\n".join(f"s{i + 1}: {s['title']} at {s['company']} ({s.get('start') or '?'} to {s.get('end') or 'present'}; "
                        f"{s.get('employment_type') or 'unknown'})"
                        + (f" [the company, from public research: {s['company_known']}]" if s.get("company_known") else "")
                        for i, s in enumerate(steps))
    user = f"Steps:\n{listing}\n\nCV text:\n{cv_text[:20000]}"
    result = client.complete_json(SYSTEM, user, SCHEMA, "step_classification")
    text = _norm(cv_text)
    labels, rejected, seen = [], [], set()
    for item in result.data.get("steps", []):
        cid = ids.get(item.get("id", ""))
        if cid is None or cid in seen:
            rejected.append({"step": str(item.get("id")), "reason": "not a step we sent, or labelled twice"})
            continue
        seen.add(cid)
        domains = []
        for dom in item.get("domains") or []:
            dom = dom.strip().lower()
            if dom not in DOMAINS or TECH_WORDS.search(dom):
                rejected.append({"step": item["id"], "reason": f"domain is not an industry from the list: {dom!r}"})
            elif dom not in domains:
                domains.append(dom)
        signals, quotes = [], {}
        for sig in item.get("signals") or []:
            quote = sig.get("quote") or ""
            if len(quote.strip()) < 4 or _norm(quote) not in text:
                rejected.append({"step": item["id"], "reason": f"{sig.get('kind')} quote is not written in the CV"})
            elif sig["kind"] not in signals:
                signals.append(sig["kind"])
                quotes[sig["kind"]] = quote.strip()[:300]
        title = next((s["title"] for s in steps if s["claim_id"] == cid), "")
        labels.append(StepLabel(cid, item["role_family"], title_level(title, signals), domains[:3], signals, quotes))
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return ClassifyOutcome(labels, rejected, cost)
