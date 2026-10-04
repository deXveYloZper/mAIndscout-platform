"""Read a recruiter's search in their own words into structured criteria. No database.

"senior devops engineer in Germany with at least 3 years working with kubernetes" ->
  kind of work devops_infrastructure, level senior, country DE, skill kubernetes with 3+ years.
One small model call; every value is checked against the fixed lists shared with career and hiring profiles.
Never criteria about personality, culture or "fit", nor nationality, age or gender: those are dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.domain.profile import DOMAINS, LEVELS, ROLE_FAMILIES
from maindscout.intelligence.llm import LLMClient

QUERY_PROMPT_VERSION = "2026-10-04.1"
EMPLOYER_KINDS = ["startup", "scaleup", "large", "consultancy", "agency", "public_sector", "non_profit"]

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["role_family", "level", "min_years", "skills", "countries", "employer_kinds", "domains", "companies",
                 "current_company_only", "ignored"],
    "properties": {
        "role_family": {"type": ["string", "null"], "enum": ROLE_FAMILIES + [None]},
        "level": {"type": ["string", "null"], "enum": LEVELS + [None]},
        "min_years": {"type": ["number", "null"], "description": "years of experience in the kind of work, only if a number is written"},
        "skills": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["token", "min_years"],
            "properties": {"token": {"type": "string", "description": "lowercase skill, e.g. kubernetes, react, insar"},
                           "min_years": {"type": ["number", "null"], "description": "only if a number of years is written for this skill"}}}},
        "countries": {"type": "array", "items": {"type": "string", "description": "ISO 3166-1 alpha-2 of where the person should live or work"}},
        "employer_kinds": {"type": "array", "items": {"type": "string", "enum": EMPLOYER_KINDS}},
        "domains": {"type": "array", "items": {"type": "string", "enum": DOMAINS}},
        "companies": {"type": "array", "items": {"type": "string"}, "description": "company names the person worked at"},
        "current_company_only": {"type": "boolean", "description": "true only if they must still work at the named company"},
        "ignored": {"type": "array", "items": {"type": "string"}, "description": "parts of the search that are not one of these criteria"},
    },
}

SYSTEM = (
    "You turn a recruiter's search for people into criteria. Use only the lists given. role_family: the kind of work "
    "('devops engineer' -> devops_infrastructure, 'frontend developer' -> software_engineering, 'InSAR specialist' -> "
    "gis_remote_sensing). level: only if a level word is used (junior, senior, lead, principal, head, ...). min_years: "
    "only if a number of years of experience is written for the work in general; years written for one skill go on "
    "that skill. countries: where the person should live or work ('in Germany' -> DE, 'UK-based' -> GB). "
    "employer_kinds: a background ('start-up experience' -> startup). domains: industry experience. companies: only "
    "named companies they worked at. Put anything else in ignored. Never criteria about personality, culture, fit, "
    "nationality, age, gender or family: put those in ignored."
)

NOT_CRITERIA = re.compile(r"\b(culture|fit|personality|nationality|national|age|young|old|gender|male|female|man|woman|"
                          r"married|kids|children|religion|religious)\b", re.I)


@dataclass
class Query:
    text: str
    role_family: str | None = None
    level: str | None = None
    min_years: float | None = None
    skills: list[dict[str, Any]] = field(default_factory=list)  # [{token, min_years}]
    countries: list[str] = field(default_factory=list)
    employer_kinds: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    current_company_only: bool = False
    ignored: list[str] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)

    def empty(self) -> bool:
        return not (self.role_family or self.level or self.min_years or self.skills or self.countries
                    or self.employer_kinds or self.domains or self.companies)


def read(text: str, client: LLMClient) -> Query:
    from maindscout.intelligence.triage import canon

    result = client.complete_json(SYSTEM, text[:500], SCHEMA, "people_search")
    d = result.data
    q = Query(text=text)
    q.role_family = d.get("role_family") if d.get("role_family") in ROLE_FAMILIES else None
    q.level = d.get("level") if d.get("level") in LEVELS else None
    years = d.get("min_years")
    q.min_years = years if isinstance(years, (int, float)) and years > 0 and re.search(rf"\b{int(years)}\b", text) else None
    for s in d.get("skills") or []:
        token = canon((s.get("token") or "").strip().lower())
        if len(token) < 2 or NOT_CRITERIA.search(token):
            continue
        y = s.get("min_years")
        q.skills.append({"token": token, "min_years": y if isinstance(y, (int, float)) and y > 0 and re.search(rf"\b{int(y)}\b", text) else None})
    q.countries = sorted({c.upper() for c in d.get("countries") or [] if re.fullmatch(r"[A-Za-z]{2}", c or "")})
    q.employer_kinds = [k for k in d.get("employer_kinds") or [] if k in EMPLOYER_KINDS]
    q.domains = [x for x in d.get("domains") or [] if x in DOMAINS]
    q.companies = [c.strip() for c in d.get("companies") or [] if c and c.strip().lower() in text.lower()]
    q.current_company_only = bool(d.get("current_company_only")) and bool(q.companies)
    q.ignored = [x for x in d.get("ignored") or [] if x]
    q.cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return q
