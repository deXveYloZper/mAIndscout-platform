"""The gap table: every requirement of a job against one person's facts. Pure, no database.

Each row is one of:
- evidence  the person's facts support it (with the facts, and whether they are approved);
- likely    nothing of theirs shows a skill, but their employer uses it in their area of work, by the employer's own
            job adverts (employer evidence, owner 2026-10-17): a reason to ask, never proof;
- missing   nothing in the file speaks to it;
- conflict  the facts speak against it (e.g. fewer years than asked);
- question  only a conversation can settle it (residence, visa, relocation, vague requirements).

There is no total and no score. Where someone lives is never a conflict: it is a question to ask.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from maindscout.intelligence.triage import canon, supports

STATUSES = ("evidence", "likely", "missing", "conflict", "question")
PRACTICE = "CompanyPracticeClaim"  # an employer's fact, given to the gap table once per stint it covers (api/practices.py)
PRACTICE_REACH = 730  # days: someone who left more than two years before the advert is not taken to use its stack
EDUCATION_RANK = {"diploma": 1, "associate": 1, "other": 1, "bachelor": 2, "master": 3, "doctorate": 4}
NOT_COUNTED_FOR_YEARS = {"internship", "side"}


@dataclass
class Fact:
    """One claim about the person, as the gap table needs it."""

    id: str
    claim_type: str
    payload: dict[str, Any]
    status: str  # proposed | approved
    valid_from: date | None = None
    valid_to: date | None = None
    snippet: str | None = None


@dataclass
class Row:
    requirement_id: str
    requirement: str
    kind: str
    strength: str
    status: str
    detail: str
    distinctive: bool = False
    facts: list[Fact] = field(default_factory=list)
    token: str | None = None  # the skill token, for skill rows

    @property
    def official(self) -> bool:
        """True only if every fact behind this row has been approved by a human. An employer's practice is never
        an approved fact about the person."""
        return self.status != "likely" and bool(self.facts) and all(f.status == "approved" for f in self.facts)


def _of(facts: list[Fact], claim_type: str) -> list[Fact]:
    return [f for f in facts if f.claim_type == claim_type]


def years_of_experience(careers: list[Fact], today: date) -> tuple[float, int, bool]:
    """(years, jobs counted, any dates missing). Overlapping jobs are merged, so time is not counted twice."""
    spans, undated = [], False
    for c in careers:
        if (c.payload.get("employment_type") or "unknown") in NOT_COUNTED_FOR_YEARS:
            continue
        if not c.valid_from:
            undated = True
            continue
        spans.append((c.valid_from, min(c.valid_to or today, today)))
    spans.sort()
    total, end = 0, None
    for start, stop in spans:
        if end is None or start > end:
            total += (stop - start).days
            end = stop
        elif stop > end:
            total += (stop - end).days
            end = stop
    return round(total / 365.25, 1), len(spans), undated


def _skill(req: dict, facts: list[Fact]) -> tuple[str, str, list[Fact]]:
    token = req.get("normalized_token")
    if not token:
        return "question", "not a single skill the file can show; check on the call", []
    skills, careers = _of(facts, "SkillClaim"), _of(facts, "CareerStepClaim")
    hits = [f for f in skills if supports(token, [f.payload["normalized_skill"], f.payload.get("raw_label", "")], [])]
    hits += [f for f in careers if supports(token, [], [f.payload.get("title_raw", "")])]
    label = " or ".join(canon(t) for t in token.split("/") if t.strip())
    if hits:
        where = "skills" if any(f.claim_type == "SkillClaim" for f in hits) else "a job title"
        return "evidence", f"{label} appears in {where}", hits
    via = employer_support(token, facts)
    if via is not None:
        p = via.payload
        tense = "work" if via.valid_to is None else "worked"
        when = f", {p['as_of'][:7]}" if p.get("as_of") else ""
        return "likely", (f"not in their file, but {p['company']} uses {p['raw_label']} (its job advert{when}) and they "
                          f"{tense} there as {p['title']}: likely, confirm on the call"), [via]
    return "missing", f"no mention of {label} in the file", []


def employer_support(token: str, facts: list[Fact], today: date | None = None) -> Fact | None:
    """An employer's practice that makes a skill likely: the company uses it in the person's area of work (or
    company-wide), and they were there no more than two years before the advert said so. None otherwise."""
    from maindscout.domain.profile import area_of_title

    today = today or date.today()
    for f in _of(facts, PRACTICE):
        p = f.payload
        if not supports(token, [p["token"], p.get("raw_label", "")], []):
            continue
        if p["area"] != "company_wide" and area_of_title(p.get("title")) != p["area"]:
            continue
        seen = date.fromisoformat(p["as_of"]) if p.get("as_of") else today
        if (f.valid_to or today) < seen - timedelta(days=PRACTICE_REACH):
            continue
        return f
    return None


def _seniority(req: dict, facts: list[Fact], today: date) -> tuple[str, str, list[Fact]]:
    need = req.get("min_years")
    careers = _of(facts, "CareerStepClaim")
    if need is None:
        return "question", "the level asked for is not a number; judge it from the career history", careers[:3]
    have, counted, undated = years_of_experience(careers, today)
    if counted == 0:
        return "missing", "no dated jobs in the file", []
    note = " (some jobs have no dates)" if undated else ""
    if have >= need:
        return "evidence", f"about {have:g} years across {counted} jobs; {need:g}+ asked{note}", careers
    return "conflict", f"about {have:g} years across {counted} jobs; {need:g}+ asked{note}", careers


def _education(req: dict, facts: list[Fact]) -> tuple[str, str, list[Fact]]:
    edu = _of(facts, "EducationClaim")
    if not edu:
        return "missing", "no education in the file", []
    need = req.get("education_level")
    if not need:
        return "evidence", "education is listed; check the field on the call", edu
    best = max(edu, key=lambda f: EDUCATION_RANK.get(f.payload.get("level") or "", 0))
    have = best.payload.get("level")
    if not have:
        return "question", f"a {need} is asked; the file does not say the level", edu
    if EDUCATION_RANK.get(have, 0) >= EDUCATION_RANK.get(need, 0):
        return "evidence", f"{have} listed; {need} asked", [best]
    return "conflict", f"highest listed is {have}; {need} asked", [best]


def _language(req: dict, facts: list[Fact]) -> tuple[str, str, list[Fact]]:
    lang = (req.get("language") or req.get("normalized_token") or "").lower()
    hits = [f for f in _of(facts, "SkillClaim") if lang and lang in (f.payload.get("raw_label", "") + " " + f.payload["normalized_skill"]).lower()]
    if hits:
        return "evidence", f"{req.get('language') or lang} is listed", hits
    return "missing", f"{req.get('language') or lang} is not mentioned; ask", []


def _names(codes: set[str]) -> str:
    from maindscout.intelligence.extract import COUNTRY_ALIASES

    return " or ".join(sorted(COUNTRY_ALIASES[c][0].title() if c in COUNTRY_ALIASES else c for c in codes))


def _current_places(facts: list[Fact]) -> list[Fact]:
    return [f for f in _of(facts, "LocationClaim") if f.payload.get("kind", "current") == "current" and f.payload.get("country_code")]


def _mobility(req: dict, facts: list[Fact], residence: set[str]) -> tuple[str, str, list[Fact]]:
    """`residence`: the countries the job's residence fact allows (used by all three facets)."""
    m = req["mobility"]
    places = _current_places(facts)
    allowed = set(m.get("countries") or []) or residence
    here = [f for f in places if f.payload["country_code"] in allowed]
    if m["facet"] == "residence":
        if here:
            return "evidence", f"lives in {here[0].payload['place_raw']}", here
        if places:
            return "question", f"lives in {places[0].payload['place_raw']}; ask about working from {_names(allowed)}", places
        return "question", "the file does not say where they live; ask", []
    if m["facet"] == "visa_sponsorship":
        if m.get("offered"):
            return "evidence", "the employer sponsors visas", []
        return "question", "no sponsorship: ask whether they already have the right to work there", []
    # relocation_assistance
    if m.get("offered"):
        return "evidence", "the employer helps with relocation", []
    if here:
        return "evidence", "already lives there; no move needed", here
    return "question", "no relocation help: ask whether they would move on their own", places


def gap_table(requirements: list[dict[str, Any]], facts: list[Fact], today: date | None = None) -> list[Row]:
    """`requirements`: [{id, payload}] of the job's live JobRequirementClaims. Process dates and plain work
    locations are job-level information, not rows. Rows keep the job's order, mobility last."""
    today = today or date.today()
    residence = {c for r in requirements if (r["payload"].get("mobility") or {}).get("facet") == "residence"
                 for c in r["payload"]["mobility"].get("countries") or []}
    rows: list[Row] = []
    for r in requirements:
        p = r["payload"]
        cat = p["category"]
        if cat == "process" or (cat == "location" and not p.get("mobility")):
            continue
        if p.get("mobility"):
            status, detail, used = _mobility(p, facts, residence)
        elif cat == "skill":
            status, detail, used = _skill(p, facts)
        elif cat == "seniority":
            status, detail, used = _seniority(p, facts, today)
        elif cat == "education":
            status, detail, used = _education(p, facts)
        elif cat == "language":
            status, detail, used = _language(p, facts)
        else:
            status, detail, used = "question", "check on the call", []
        rows.append(Row(r["id"], p["text_raw"], "mobility" if p.get("mobility") else cat, p["strength"], status, detail,
                        bool(p.get("distinctive")), used, p.get("normalized_token") if cat == "skill" else None))
    rows.sort(key=lambda row: row.kind == "mobility")
    return rows


def counts(rows: list[Row]) -> dict[str, int]:
    """How many rows of each kind. Counts, not a score: they are never added up or weighted."""
    return {s: sum(r.status == s for r in rows) for s in STATUSES}
