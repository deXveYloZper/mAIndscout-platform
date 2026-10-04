"""The Brief (Slice 3): what to ask on the call, compiled from what the system does not know or does not trust.
Pure: no database, no model. Every question comes from a fixed template and traces to the source that produced it.

Two scopes: about the person (asked once, inherited by every job they are on) and for this job.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Item:
    source_key: str
    scope: str  # person | job
    kind: str  # requirement | career | contact | mobility | standard
    question: str
    why: str


STANDARD = [
    ("std:notice", "When could they start? Notice period and availability.", "Availability is never on a CV."),
    ("std:salary", "What are their salary expectations?", "Pay is never on a CV."),
    ("std:marketable", "Are they open to being put forward for other suitable roles, beyond this one?",
     "Ask once; it decides whether the desk may present them proactively."),
]

HIRING_KINDS = ("role", "employer", "domain", "target_company", "employment")


def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:10]


def for_job(match_rows: list[dict[str, Any]]) -> list[Item]:
    """Questions for this job, from the match: what can only be asked, and must-haves / strong-plus items the CV does
    not show. Where someone lives, visas and relocation are always questions, never exclusions."""
    out: list[Item] = []
    rank = {"must": 0, "deal_breaker": 0, "strong_plus": 1, "unknown": 2, "nice": 3}
    # Must-haves first, then strong-plus, then the rest; where they may live and work last.
    ordered = sorted(match_rows, key=lambda v: (v["kind"] == "mobility", rank.get(v.get("strength") or "unknown", 2)))
    for v in ordered:
        rid, text, detail, strength = v["requirement_id"], v["requirement"], v.get("detail") or "", v.get("strength")
        if v["kind"] == "mobility":
            out.append(Item(f"req:{rid}", "job", "mobility", f"{text}: {detail[:1].upper()}{detail[1:]}", "Where someone lives or may work is settled on the call."))
        elif v["verdict"] == "ask":
            out.append(Item(f"req:{rid}", "job", "requirement", f"Ask about: {text}.", detail or "The file cannot settle it."))
        elif v["verdict"] in ("gap", "partly", "partial") and strength in ("must", "deal_breaker", "strong_plus"):
            weight = "a must-have" if strength in ("must", "deal_breaker") else "a strong plus"
            out.append(Item(f"req:{rid}", "job", "requirement", f"Check: {text} ({weight}). Do they have it?",
                            f"The CV does not show it: {detail}." if detail else "The CV does not show it."))
    return out


def for_person(profile: dict[str, Any] | None, suspect_contacts: list[dict[str, Any]], lives_known: bool) -> list[Item]:
    """Questions about the person, asked once whatever the job."""
    out: list[Item] = []
    for q in (profile or {}).get("questions") or []:
        out.append(Item(f"career:{_h(q)}", "person", "career", q, "From the career profile (dates, stays, companies)."))
    for c in suspect_contacts:
        out.append(Item(f"contact:{c['claim_id']}", "person", "contact",
                        f"Confirm their {c['kind']}: {c['value']}.", "The file may have garbled it (it looks like a scanned identifier)."))
    if not lives_known:
        out.append(Item("std:location", "person", "standard", "Where do they live now, and where can they work from?",
                        "The CV does not say where they live."))
    for key, question, why in STANDARD:
        out.append(Item(key, "person", "standard", question, why))
    return out
