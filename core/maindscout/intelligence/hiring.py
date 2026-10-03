"""Hiring profile: what a job really asks for, read from its ad or from the recruiter's intake notes. No database.

One model call per text. Every item must quote the text it came from (checked); values come from fixed lists shared
with career profiles, so matching (I5) can compare like with like. Never personality, culture or "fit": items about
those are dropped (owner's rule, 2026-10-03).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.domain.profile import DOMAINS, LEVELS, ROLE_FAMILIES
from maindscout.intelligence.llm import LLMClient

HIRING_PROMPT_VERSION = "2026-10-04.2"
EMPLOYER_KINDS = ["startup", "scaleup", "large", "consultancy", "agency", "public_sector", "non_profit"]
STRENGTHS = ["must", "strong_plus", "nice", "anti"]
KINDS = ["role", "employer", "domain", "target_company", "employment", "skill", "other"]

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "strength", "text", "quote", "role_family", "level", "min_years", "employer_kinds", "domains",
                     "companies", "employment", "skill_token", "note"],
        "properties": {
            "kind": {"type": "string", "enum": KINDS},
            "strength": {"type": "string", "enum": STRENGTHS},
            "text": {"type": "string", "description": "the requirement in a few plain words"},
            "quote": {"type": "string", "description": "short EXACT quote from the text it comes from"},
            "role_family": {"type": ["string", "null"], "enum": ROLE_FAMILIES + [None]},
            "level": {"type": ["string", "null"], "enum": LEVELS + [None]},
            "min_years": {"type": ["number", "null"], "description": "only when a number of years is written"},
            "employer_kinds": {"type": "array", "items": {"type": "string", "enum": EMPLOYER_KINDS}},
            "domains": {"type": "array", "items": {"type": "string", "enum": DOMAINS}},
            "companies": {"type": "array", "items": {"type": "string"}},
            "employment": {"type": ["string", "null"], "enum": ["permanent", "contract", "either", None]},
            "skill_token": {"type": ["string", "null"], "description": "lowercase skill token, only for kind skill"},
            "note": {"type": ["string", "null"], "description": "e.g. what it can substitute for, as stated"},
        }}}},
}

SYSTEM_AD = (
    "You read ONE job advertisement for a recruiting desk and state the hiring profile it gives. Give: one 'role' item "
    "(the kind of work from the list, the level if the ad states or clearly implies it, min_years only if a number is "
    "written); 'employment' (permanent or contract) if stated; 'employer' items only if the ad asks for a background "
    "(e.g. 'start-up experience'); 'domain' items only if the ad asks for industry experience; 'target_company' only if "
    "companies are named as where people should come from. Skills, education and languages are read elsewhere: do not "
    "repeat them. Strength: must (required, essential), strong_plus (highly desirable, big plus, strongly preferred), "
    "nice (nice to have, bonus), anti (explicitly not wanted). Every item quotes the ad exactly. Never items about "
    "personality, attitude, culture or fit. Never guess: leave out what the ad does not say."
)
SYSTEM_INTAKE = (
    "You read a recruiter's notes from a call with a hiring manager and turn them into hiring requirements. Kinds: "
    "role (kind of work, level, years), employer (background: startup, scaleup, large, consultancy, agency, public "
    "sector, non-profit), domain (industry experience, from the list), target_company (companies to source from, or "
    "with anti, not from), employment (permanent / contract / either), skill (a technical skill, with a lowercase "
    "token), other (anything else concrete, e.g. '0-to-1 product delivery'). Give a role item only when the notes "
    "state what kind of work, level or years the person needs; the job's title mentioned in passing is not one. Strength exactly as the notes put it: "
    "must, strong_plus ('strong plus', 'really wants', 'highly desirable'), nice ('nice to have', 'bonus'), anti ('no', "
    "'not', 'avoid'). If the notes say one thing can substitute for another, put that in note. Location and right to "
    "work are handled elsewhere: leave them out. Every item quotes the notes exactly. Never items about personality, "
    "attitude, culture or fit. Never guess."
)

EMPLOYMENT_WORDS = re.compile(r"(permanent|full[- ]time|part[- ]time|contract|contractor|freelance|fixed[- ]term|temporary|"
                              r"employment|employee|perm|b2b|interim)", re.I)
# Dropped whatever the model says: these are not evidence-based hiring criteria (owner's rule).
NOT_CRITERIA = re.compile(r"\b(culture|cultural fit|personality|vibe|attitude|team player|charism|likeable|good fit|fit in)\b", re.I)


@dataclass
class Item:
    kind: str
    strength: str
    text: str
    quote: str
    start: int
    end: int
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class HiringOutcome:
    items: list[Item]
    rejected: list[dict[str, str]]
    cost: dict[str, Any]


def _find(quote: str, text: str) -> tuple[int, int] | None:
    """Where the quote is in the text, ignoring case and runs of whitespace."""
    q = re.escape(" ".join(quote.split())).replace(r"\ ", r"\s+")
    m = re.search(q, text, re.I) if quote.strip() else None
    return (m.start(), m.end()) if m else None


def read(text: str, client: LLMClient, source: str) -> HiringOutcome:
    """`source`: 'ad' or 'intake'."""
    system = SYSTEM_AD if source == "ad" else SYSTEM_INTAKE
    result = client.complete_json(system, text[:20000], SCHEMA, "hiring_profile")
    items, rejected = [], []
    for raw in result.data.get("items", []):
        kind, quote = raw.get("kind"), raw.get("quote") or ""
        where = _find(quote, text)
        why = None
        if kind not in KINDS or raw.get("strength") not in STRENGTHS:
            why = "unknown kind or strength"
        elif where is None:
            why = "the quote is not in the text"
        elif NOT_CRITERIA.search(raw.get("text", "") + " " + quote):
            why = "personality, culture or fit is never a criterion"
        elif source == "ad" and kind in ("skill", "other"):
            why = "skills and other items from the ad are read by the ad reader"
        if why:
            rejected.append({"item": raw.get("text", "")[:80], "reason": why})
            continue
        fields: dict[str, Any] = {}
        if kind == "role":
            if not raw.get("role_family"):
                rejected.append({"item": raw.get("text", "")[:80], "reason": "a role needs a kind of work"})
                continue
            fields = {"role_family": raw["role_family"], "level": raw.get("level")}
            years = raw.get("min_years")
            if years is not None and re.search(rf"\b{int(years)}\b", quote):  # a number of years must be written
                fields["min_years"] = years
        elif kind == "employer":
            fields = {"employer_kinds": [k for k in raw.get("employer_kinds") or [] if k in EMPLOYER_KINDS]}
        elif kind == "domain":
            fields = {"domains": [d for d in raw.get("domains") or [] if d in DOMAINS]}
        elif kind == "target_company":
            names = [n.strip() for n in raw.get("companies") or [] if n.strip() and n.strip().lower() in quote.lower()]
            fields = {"companies": names}
        elif kind == "employment":
            if not EMPLOYMENT_WORDS.search(quote):
                rejected.append({"item": raw.get("text", "")[:80], "reason": "the quote does not speak about permanent or contract work"})
                continue
            fields = {"employment": raw.get("employment")}
        elif kind == "skill":
            fields = {"skill_token": (raw.get("skill_token") or "").strip().lower() or None}
        if any(v in (None, [], "") for k, v in fields.items() if k not in ("level", "min_years")):
            rejected.append({"item": raw.get("text", "")[:80], "reason": "nothing usable from the lists"})
            continue
        if raw.get("note"):
            fields["note"] = raw["note"][:200]
        items.append(Item(kind, raw["strength"], raw.get("text", "").strip()[:200] or quote[:120], quote.strip()[:400],
                          where[0], where[1], fields))
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return HiringOutcome(items, rejected, cost)
