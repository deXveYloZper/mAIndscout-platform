"""Hiring profile: what a job really asks for, read from its ad or from the recruiter's intake notes. No database.

One model call per text. Every item must quote the text it came from (checked); values come from fixed lists shared
with career profiles, so matching (I5) can compare like with like. Never personality, culture or "fit": items about
those are dropped (owner's rule, 2026-10-03).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.domain.profile import DOMAINS, LEVELS, ROLE_FAMILIES, domains_in
from maindscout.intelligence.llm import LLMClient

HIRING_PROMPT_VERSION = "2026-10-19.1"  # sizes in people, level limits, and no ask dropped
EMPLOYER_KINDS = ["startup", "scaleup", "large", "consultancy", "agency", "public_sector", "non_profit"]
STRENGTHS = ["must", "strong_plus", "nice", "anti"]
KINDS = ["role", "employer", "domain", "target_company", "employment", "skill", "other", "hiring_company", "location"]
# Read from intake notes only: who is hiring (an anonymised ad names nobody), and where the person must be.
INTAKE_ONLY = ("hiring_company", "location")

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "strength", "text", "quote", "role_family", "level", "min_years", "employer_kinds", "domains",
                     "companies", "employment", "skill_token", "note", "countries", "cities", "relocation", "min_staff",
                     "max_staff"],
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
            "countries": {"type": "array", "items": {"type": "string"},
                          "description": "location only: two-letter country codes of the places named (Milan -> IT)"},
            "cities": {"type": "array", "items": {"type": "string"}, "description": "location only: cities named"},
            "relocation": {"type": ["boolean", "null"], "description": "location only: true if moving there is fine"},
            "min_staff": {"type": ["integer", "null"], "description": "employer only: the smallest company size in people"},
            "max_staff": {"type": ["integer", "null"], "description": "employer only: the largest company size in people"},
        }}}},
}

# Company sizes in the desk's words (owner, 2026-10-19; domain/profile.SIZE_BANDS): when notes say "small" or "big"
# without a number, these are the sizes meant.
SIZE_WORDS = ("Company sizes in people: small is up to 50, mid-size up to 250, big or large means over 500 "
              "(min_staff 501) unless a number is written; 'up to 200 people' is max_staff 200. ")
LEVEL_LIMIT = ("A limit on seniority ('not too senior', 'no heads or directors', 'not global or regional roles') is a "
               "role item with strength anti, the kind of work of the job, and level = the FIRST level that is too "
               "senior (head when heads, global or regional leads are not wanted; director when directors are not). ")
NO_ASK_DROPPED = ("Every concrete ask in the text must become an item: if it fits none of the kinds, give it as kind "
                  "other with its quote, never leave it out. ")

SYSTEM_AD = (
    "You read ONE job advertisement for a recruiting desk and state the hiring profile it gives. Give: one 'role' item "
    "(the kind of work from the list, the level if the ad states or clearly implies it, min_years only if a number is "
    "written); 'employment' (permanent or contract) if stated; 'employer' items only if the ad asks for a background "
    "(e.g. 'start-up experience', or a company size); 'domain' items only if the ad asks for industry experience; "
    "'target_company' only if companies are named as where people should come from. Skills, education and languages "
    "are read elsewhere: do not repeat them. Strength: must (required, essential), strong_plus (highly desirable, big "
    "plus, strongly preferred), nice (nice to have, bonus), anti (explicitly not wanted). " + SIZE_WORDS + LEVEL_LIMIT +
    "Every item quotes the ad exactly. Never items about personality, attitude, culture or fit. Never guess: leave out "
    "what the ad does not say."
)
SYSTEM_INTAKE = (
    "You read a recruiter's notes from a call with a hiring manager and turn them into hiring requirements. Kinds: "
    "role (kind of work, level, years), employer (background: startup, scaleup, large, consultancy, agency, public "
    "sector, non-profit), domain (industry experience, from the list), target_company (companies to source from, or "
    "with anti, not from), employment (permanent / contract / either), skill (a technical skill, with a lowercase "
    "token), other (anything else concrete, e.g. '0-to-1 product delivery'), hiring_company (the company that is hiring, "
    "when the notes say who it is: its name in companies), location (where the person must live or work: cities, "
    "two-letter country codes, and relocation true when moving there is fine, e.g. 'must be in Milan or willing to "
    "move to Milan'). Give a role item only when the notes "
    "state what kind of work, level or years the person needs; the job's title mentioned in passing is not one, and never give any item that only names the job. Strength exactly as the notes put it: "
    "must, strong_plus ('strong plus', 'really wants', 'highly desirable', 'ideally'), nice ('nice to have', 'bonus'), "
    "anti ('no', 'not', 'avoid', 'cannot'). If the notes say one thing can substitute for another, put that in note. "
    "An employer item may name a size in people instead of, or as well as, a kind ('ideally from small brands up to "
    "200 people': strong_plus, max_staff 200; 'not from big brands': anti, min_staff 501). " + SIZE_WORDS + LEVEL_LIMIT +
    NO_ASK_DROPPED + "Right to work is handled elsewhere: leave it out. Every item quotes the notes exactly. Never "
    "items about personality, attitude, culture or fit. Never guess."
)

EMPLOYMENT_WORDS = re.compile(r"\b(permanent|full[- ]time|part[- ]time|contract|contractor|freelance|fixed[- ]term|temporary|"
                              r"employment|employee|perm|b2b|interim)\b", re.I)
EMPLOYER_WORDS = {
    "startup": re.compile(r"\bstart-?ups?\b|\bearly[- ]stage\b", re.I),
    "scaleup": re.compile(r"\bscale-?ups?\b|\bhigh[- ]growth\b", re.I),
    "large": re.compile(r"\b(large|big) (companies|company|corporates?|enterprises?)\b|\bcorporates?\b", re.I),
    "consultancy": re.compile(r"\bconsultanc(y|ies)\b|\boutsourc", re.I),
    "agency": re.compile(r"\bagenc(y|ies)\b", re.I),
}
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
        elif source == "ad" and kind in INTAKE_ONLY:
            why = "the ad's company and places are read by the ad reader"
        if why:
            rejected.append({"item": raw.get("text", "")[:80], "reason": why})
            continue
        fields: dict[str, Any] = {}
        if kind == "role" and source == "intake" and raw.get("level") is None and raw.get("min_years") is None:
            # From notes, a "role" with no level and no years is a concrete ask (e.g. "0-to-1 product delivery"),
            # not the job's role: it must never replace the role the ad states.
            kind = "other"
        if kind == "role":
            if not raw.get("role_family"):
                rejected.append({"item": raw.get("text", "")[:80], "reason": "a role needs a kind of work"})
                continue
            fields = {"role_family": raw["role_family"], "level": raw.get("level")}
            years = raw.get("min_years")
            if years is not None and re.search(rf"\b{int(years)}\b", quote):  # a number of years must be written
                fields["min_years"] = years
        elif kind == "employer":
            kinds = [k for k in raw.get("employer_kinds") or [] if k in EMPLOYER_KINDS]
            sizes = {k: int(raw[k]) for k in ("min_staff", "max_staff")
                     if isinstance(raw.get(k), (int, float)) and 1 <= raw[k] <= 1_000_000}
            if sizes:
                kinds = [k for k in kinds if k not in ("startup", "scaleup", "large")]  # the size says it in people
            elif not kinds:  # the model left it empty: read it from the quote's own words
                kinds = [k for k, rx in EMPLOYER_WORDS.items() if rx.search(quote)]
            if not kinds and not sizes and domains_in(quote):
                # "Experience in luxury, premium fashion … consumer brand" is an industry, not a kind of employer (the
                # model called it a background twice on a real marketing ad, 2026-10-18, and it was lost).
                kind, fields = "domain", {"domains": domains_in(quote)}
            elif not kinds and not sizes:
                # "not from big brands" with no kind and no size was dropped as "nothing usable" (2026-10-19): it is
                # kept for the conversation instead.
                kind, fields = "other", {}
            else:
                fields = ({"employer_kinds": kinds} if kinds else {}) | sizes
        elif kind == "domain":
            fields = {"domains": [d for d in raw.get("domains") or [] if d in DOMAINS] or domains_in(quote)}
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
        elif kind == "hiring_company":
            # The model sometimes gives the name as the item's text only (seen on a real note, 2026-10-13).
            names = [n.strip() for n in [*(raw.get("companies") or []), raw.get("text") or ""]
                     if n.strip() and len(n.split()) <= 6 and n.strip().lower() in quote.lower()]
            fields = {"companies": names[:1]}
        elif kind == "location":
            from maindscout.domain.geo import NAMES

            cities = [c.strip() for c in raw.get("cities") or [] if c.strip() and c.strip().lower() in quote.lower()]
            codes = [c.upper() for c in raw.get("countries") or [] if c.upper() in NAMES]
            if not codes:
                rejected.append({"item": raw.get("text", "")[:80], "reason": "no country for the place"})
                continue
            fields = {"countries": list(dict.fromkeys(codes)), "cities": cities,
                      "relocation": bool(raw.get("relocation")) if re.search(r"\b(move|moving|relocat|trasfer)", quote, re.I) else False}
        if any(v in (None, [], "") for k, v in fields.items() if k not in ("level", "min_years", "cities", "relocation")):
            rejected.append({"item": raw.get("text", "")[:80], "reason": "nothing usable from the lists"})
            continue
        if raw.get("note"):
            fields["note"] = raw["note"][:200]
        items.append(Item(kind, raw["strength"], raw.get("text", "").strip()[:200] or quote[:120], quote.strip()[:400],
                          where[0], where[1], fields))
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return HiringOutcome(items, rejected, cost)
