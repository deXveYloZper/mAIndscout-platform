"""What a candidate wants next, against what a job is. Pure: no database, no model, never a number.

Each approved preference (PreferenceClaim, said on a call) becomes one match row:
- strong  the job fits what they want (known company or job facts show it);
- gap     the job is what they said they do not want; the detail quotes both sides;
- ask     the job's side is not known (e.g. the company's size was never found): check it.
A must that the job contradicts makes the match unlikely; a prefer is only a note (matching.py, RULES).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from maindscout.domain.geo import name_of
from maindscout.domain.profile import CATEGORY_LABEL, FAMILY_LABEL, LEVEL_RANK, CompanyFacts, Stint, stint_category

ONE = {"startup": "a start-up", "scaleup": "a scale-up", "large": "a large company", "consultancy": "a consultancy or outsourcer",
       "agency": "an agency", "public_sector": "public sector", "non_profit": "a non-profit"}
SETTING_LABEL = {"onsite": "on site", "hybrid": "hybrid", "remote": "remote"}


@dataclass
class JobSide:
    """What is known about the job and its hiring company, for comparing with preferences."""

    company: str = "the company"
    facts: CompanyFacts | None = None
    family: str | None = None
    level: str | None = None
    employment: str | None = None  # permanent | contract | either
    countries: list[str] = field(default_factory=list)  # where the person must live or work from


def _kinds(values: list[str]) -> str:
    return " or ".join(CATEGORY_LABEL.get(v, v.replace("_", " ")) for v in values)


def _places(values: list[str]) -> str:
    return ", ".join(name_of(c) for c in values)


def describe(p: dict[str, Any]) -> str:
    """One preference in plain words, e.g. 'Must: at least 200 people' or 'Prefers: not start-ups'."""
    facet, lead = p["facet"], "Must" if p["strength"] == "must" else "Prefers"
    want, avoid = p.get("want") or [], p.get("avoid") or []
    if facet == "company_size":
        lo, hi = p.get("min"), p.get("max")
        size = f"{lo} to {hi} people" if lo is not None and hi is not None else f"at least {lo} people" if lo is not None else f"at most {hi} people"
        return f"{lead}: a company of {size}"
    parts = []
    if facet == "employer_kind":
        parts += [_kinds(want)] if want else []
        parts += [f"not {_kinds(avoid)}"] if avoid else []
    elif facet == "setting":
        parts += [" or ".join(SETTING_LABEL.get(w, w) for w in want)] if want else []
        parts += [f"not {' or '.join(SETTING_LABEL.get(a, a) for a in avoid)}"] if avoid else []
    elif facet == "places":
        parts += [f"in {_places(want)}"] if want else []
        parts += [f"not in {_places(avoid)}"] if avoid else []
    elif facet == "work":
        parts += [" or ".join(FAMILY_LABEL.get(w, w) for w in want)] if want else []
        parts += [f"{p['level']} level"] if p.get("level") else []
        parts += [f"not {' or '.join(FAMILY_LABEL.get(a, a) for a in avoid)}"] if avoid else []
    elif facet == "employment":
        parts += [" or ".join(want)] if want else []
        parts += [f"not {' or '.join(avoid)}"] if avoid else []
    return f"{lead}: {', '.join(parts) or 'nothing usable'}"


def category_now(facts: CompanyFacts | None) -> str:
    """What kind of employer the hiring company is today (the same reading as a career step that starts today)."""
    if facts is None:
        return "unknown"
    return stint_category(Stint(id="job", company="", title="", start=date.today(), end=None, facts=facts))


def _size(facts: CompanyFacts | None) -> str | None:
    if facts is None or facts.team_min is None:
        return None
    return f"{facts.team_min}-{facts.team_max} people" if facts.team_max else f"{facts.team_min}+ people"


def check(p: dict[str, Any], job: JobSide) -> tuple[str, str]:
    """(verdict, detail) for one preference against one job."""
    facet, said = p["facet"], p.get("said") or ""
    they = f'they said "{said}"' if said else "they said so on the call"
    want, avoid = p.get("want") or [], p.get("avoid") or []
    if facet == "company_size":
        f, lo, hi = job.facts, p.get("min"), p.get("max")
        size = _size(f)
        if size is None:
            return "ask", f"{job.company}'s size is not known: check it ({they})"
        low, high = f.team_min, f.team_max
        if (lo is not None and high is not None and high < lo) or (hi is not None and low > hi):
            return "gap", f"{job.company} has {size}; {they}"
        if (lo is None or low >= lo) and (hi is None or (high is not None and high <= hi)):
            return "strong", f"fits what they want: {job.company} has {size}"
        return "ask", f"{job.company} has {size}, which may or may not fit: check it ({they})"
    if facet == "employer_kind":
        cat = category_now(job.facts)
        if cat == "unknown":
            return "ask", f"what kind of employer {job.company} is is not known: check it ({they})"
        label = ONE.get(cat, cat)
        if cat in avoid or (want and cat not in want):
            return "gap", f"{job.company} reads as {label}; {they}"
        return "strong", f"fits what they want: {job.company} reads as {label}"
    if facet == "work":
        if job.family is None and job.level is None:
            return "ask", f"the kind of work is not known for this job ({they})"
        fam = FAMILY_LABEL.get(job.family or "", job.family or "")
        if job.family and (job.family in avoid or (want and job.family not in want)):
            return "gap", f"this job is {fam}; {they}"
        wanted = p.get("level")
        if wanted and job.level and LEVEL_RANK.get(job.level, 99) < LEVEL_RANK.get(wanted, -1):
            return "gap", f"this job is {job.level} level; {they}"
        return "strong", "fits what they want" + (f": {fam}" if fam else "") + (f", {job.level} level" if job.level else "")
    if facet == "employment":
        if job.employment is None:
            return "ask", f"permanent or contract is not known for this job ({they})"
        if job.employment != "either" and (job.employment in avoid or (want and job.employment not in want)):
            return "gap", f"this job is {job.employment}; {they}"
        return "strong", f"fits what they want: {job.employment}"
    if facet == "places":
        if not job.countries:
            return "ask", f"where this job is based is not known ({they})"
        names = _places(job.countries)
        if (avoid and all(c in avoid for c in job.countries)) or (want and not set(job.countries) & set(want)):
            return "gap", f"this job is for {names}; {they}"
        return "strong", f"fits what they want: {names}"
    # setting: on site, hybrid or remote is not recorded for jobs yet
    return "ask", f"on site, hybrid or remote: check this job ({they})"


def rows(preferences: list[dict[str, Any]], job: JobSide) -> list[tuple[str, str, str, str, str]]:
    """(id, words, strength, verdict, detail) per preference: the match rows for matching.py."""
    out = []
    for p in preferences:
        verdict, detail = check(p, job)
        out.append((f"pref:{p['facet']}", describe(p), p["strength"], verdict, detail))
    return out
