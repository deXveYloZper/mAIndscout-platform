"""The Brief (Slice 3): what to ask on the call, compiled from what the system does not know or does not trust.
Pure: no database, no model. Every question comes from a fixed template and traces to the source that produced it.

Two scopes: about the person (asked once, inherited by every job they are on) and for this job. Each question that is
not self-explanatory carries a one-line reason ("why"), so a recruiter who has never seen the person can work through
Briefs at speed (owner, 2026-10-04). Obvious ones (salary, notice, where they live) carry none.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Item:
    source_key: str
    scope: str  # person | job
    kind: str  # requirement | career | contact | mobility | standard
    question: str
    why: str | None


STANDARD = [
    ("std:notice", "When could they start? Notice period and availability."),
    ("std:salary", "What are their salary expectations?"),
    ("std:marketable", "Are they open to being put forward for other suitable roles, beyond this one?"),
    ("std:looking_for", "What are they looking for next: kind of work, level, and on site, hybrid or remote?"),
]

STRENGTH_WORDS = {"must": "a must-have", "deal_breaker": "a must-have", "strong_plus": "a strong plus", "nice": "nice to have",
                  "unknown": "listed"}


def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:10]


def _asked_by(company: str, source: str | None, strength: str | None) -> str:
    """Who wants it and how much, in a few words."""
    weight = STRENGTH_WORDS.get(strength or "unknown", "listed")
    if source == "intake":
        return f"The hiring manager asked for this ({weight})"
    if source == "recruiter":
        return f"You added this ({weight})"
    if strength in ("must", "deal_breaker"):
        return f"Required by {company} ({weight})"
    if strength == "nice":
        return f"Nice to have for {company}"
    return f"Wanted by {company} ({weight})"


def for_job(match_rows: list[dict[str, Any]], company: str = "the company", sources: dict[str, str] | None = None) -> list[Item]:
    """Questions for this job, from the match: what can only be asked, and must-haves / strong-plus items the CV does
    not show. Where someone lives, visas and relocation are always questions, never exclusions."""
    out: list[Item] = []
    rank = {"must": 0, "deal_breaker": 0, "strong_plus": 1, "unknown": 2, "nice": 3}
    # Must-haves first, then strong-plus, then the rest; where they may live and work last.
    ordered = sorted(match_rows, key=lambda v: (v["kind"] == "mobility", rank.get(v.get("strength") or "unknown", 2)))
    for v in ordered:
        rid, text, detail, strength = v["requirement_id"], v["requirement"], v.get("detail") or "", v.get("strength")
        asked = _asked_by(company, (sources or {}).get(rid), strength)
        if v["kind"] == "mobility":
            out.append(Item(f"req:{rid}", "job", "mobility", f"{text}: {detail[:1].upper()}{detail[1:]}",
                            f"{asked}. Never a reason to drop them on its own: settle it on the call."))
        elif v["verdict"] == "ask":
            out.append(Item(f"req:{rid}", "job", "requirement", f"Ask about: {text}.", f"{asked}; the CV cannot confirm it."))
        elif v["verdict"] in ("gap", "partly", "partial") and strength in ("must", "deal_breaker", "strong_plus"):
            stake = "without it they are unlikely to progress" if strength in ("must", "deal_breaker") else "having it puts them ahead"
            out.append(Item(f"req:{rid}", "job", "requirement", f"Check: {text}. Do they have it?",
                            f"{asked}; the CV does not show it, and {stake}."))
    return out


def career_why(question: str) -> str:
    """One line on why a career question matters, from what kind of question it is."""
    q = question.lower()
    m = re.search(r"between (\w+ \d{4}) and (\w+ \d{4})", question)
    if m:
        return f"A gap from {m.group(1)} to {m.group(2)}: clients ask, so have the answer ready."
    if "short stays" in q:
        return "Left after a short time; a pattern clients ask about. Usually there is a good reason: get it."
    if "shut down or was sold" in q:
        return "The company closed or was sold, which likely explains the move. Worth confirming what they did at the end."
    if "contracts were mostly short" in q:
        return "Short contracts can be by design or not; the client will want to know which."
    if "consultancy work" in q:
        return "Consultancy careers vary: ownership of a product is what product companies look for."
    if "clear direction" in q:
        return "Titles alone do not show growth; scope and reporting line do."
    if "no dates" in q:
        return "A job without dates leaves a hole in the timeline."
    if "kind of work" in q:
        return "The CV does not make their actual work clear."
    return "From their career history."


def for_person(profile: dict[str, Any] | None, suspect_contacts: list[dict[str, Any]], lives_known: bool) -> list[Item]:
    """Questions about the person, asked once whatever the job."""
    out: list[Item] = []
    for q in (profile or {}).get("questions") or []:
        out.append(Item(f"career:{_h(q)}", "person", "career", q, career_why(q)))
    for c in suspect_contacts:
        out.append(Item(f"contact:{c['claim_id']}", "person", "contact",
                        f"Confirm their {c['kind']}: {c['value']}.", "It looks garbled in the file; a wrong contact loses the candidate."))
    if not lives_known:
        out.append(Item("std:location", "person", "standard", "Where do they live now, and where can they work from?", None))
    for key, question in STANDARD:
        out.append(Item(key, "person", "standard", question, None))
    return out
