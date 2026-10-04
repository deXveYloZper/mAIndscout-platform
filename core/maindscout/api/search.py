"""People search over career profiles (I6): structured filters, fast and free (code over stored profiles, no model).

Filters (all must pass): kind of work (with related work, by default), years of related work, level by title,
years at a kind of employer, years in an industry, worked at one of these companies, currently or ever. Results come
newest first: the filters decide who is in, never an order "by fit" (sourcing must not become a ranking).
Archived people (outside coverage) are not searched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from maindscout.api import companies
from maindscout.db.models import Candidate, CareerProfile, Claim, Company, Job
from maindscout.domain.profile import FAMILY_LABEL, GROUP_LABEL, LEVEL_RANK, group_of

LIVE = ("proposed", "approved")


@dataclass
class Filters:
    family: str | None = None
    related: bool = True  # count related kinds of work (e.g. GIS for a data role)
    min_years: float | None = None
    level: str | None = None  # at least this level by title
    employer_kinds: list[str] = field(default_factory=list)  # at least 1 year at any of them
    domains: list[str] = field(default_factory=list)  # at least 1 year in any of them
    company_ids: list[str] = field(default_factory=list)  # worked at any of them
    current_only: bool = False  # ... and still works there

    def words(self) -> list[str]:
        out = []
        if self.family:
            out.append(FAMILY_LABEL.get(self.family, self.family) + (" (or related)" if self.related else ""))
        if self.min_years:
            out.append(f"{self.min_years:g}+ years")
        if self.level:
            out.append(f"{self.level} or above")
        if self.employer_kinds:
            out.append("time at " + " / ".join(k.replace("_", " ") for k in self.employer_kinds))
        if self.domains:
            out.append("time in " + " / ".join(self.domains))
        if self.company_ids:
            out.append(("works at " if self.current_only else "worked at ") + f"{len(self.company_ids)} named compan{'y' if len(self.company_ids) == 1 else 'ies'}")
        return out

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _latest_profiles(session: Session, org_id: uuid.UUID) -> dict[uuid.UUID, dict[str, Any]]:
    rows = session.execute(select(CareerProfile.candidate_id, CareerProfile.profile)
                           .join(Candidate, Candidate.id == CareerProfile.candidate_id)
                           .where(CareerProfile.org_id == org_id, Candidate.archived_at.is_(None), Candidate.merged_into_id.is_(None))
                           .order_by(CareerProfile.candidate_id, CareerProfile.computed_at.desc())
                           .ext(distinct_on(CareerProfile.candidate_id))).all()
    return {cid: profile for cid, profile in rows}


def _company_ids(session: Session, ids: list[str]) -> set[str]:
    """The companies and everything merged into them."""
    out = set(ids)
    for cid in ids:
        out |= {str(i) for i in session.scalars(select(Company.id).where(Company.merged_into_id == uuid.UUID(cid)))}
    return out


def _worked_at(session: Session, org_id: uuid.UUID, ids: list[str], current_only: bool) -> dict[uuid.UUID, list[str]]:
    wanted = _company_ids(session, ids)
    out: dict[uuid.UUID, list[str]] = {}
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim",
                                                 Claim.status.in_(LIVE),
                                                 Claim.payload["company"]["company_id"].astext.in_(list(wanted)))):
        if current_only and c.valid_to is not None:
            continue
        p = c.approved_view or c.payload
        when = f"{c.valid_from.year if c.valid_from else '?'}-{'now' if c.valid_to is None else c.valid_to.year}"
        out.setdefault(c.subject_id, []).append(f"{p['company']['raw_name']} ({when})")
    return out


def passes(profile: dict[str, Any], f: Filters) -> list[str] | None:
    """What this profile meets of the filters, in words; None if it misses any."""
    dims, met = profile["dimensions"], []
    ry = dims["relevant_years"]
    if f.family:
        main = ry.get("main")
        if main == f.family:
            met.append(f"works in {FAMILY_LABEL.get(main, main)}")
        elif f.related and main and group_of(main) == group_of(f.family) and group_of(main) != main:
            met.append(f"works in {FAMILY_LABEL.get(main, main)} ({GROUP_LABEL.get(group_of(main), 'related')})")
        else:
            return None
    if f.min_years:
        if ry.get("main_years", 0) < f.min_years:
            return None
        met.append(f"{ry['main_years']:g} years of related work")
    if f.level:
        have = dims["seniority"].get("label")
        if have not in LEVEL_RANK or LEVEL_RANK[have] < LEVEL_RANK.get(f.level, 0):
            return None
        met.append(f"{have} by title")
    if f.employer_kinds:
        years = dims["employer_mix"].get("years") or {}
        have = sum(years.get(k, 0) for k in f.employer_kinds)
        if have < 1:
            return None
        met.append(f"{have:g} years at {' / '.join(k.replace('_', ' ') for k in f.employer_kinds)}")
    if f.domains:
        years = dims["domain_exposure"].get("years") or {}
        have = max((years.get(d, 0) for d in f.domains), default=0)
        if have < 1:
            return None
        met.append(f"{have:g} years in {' / '.join(f.domains)}")
    return met


def search(session: Session, org_id: uuid.UUID, f: Filters, exclude: set[uuid.UUID] | None = None, limit: int = 200) -> list[dict[str, Any]]:
    from maindscout.api.queries import names

    profiles = _latest_profiles(session, org_id)
    at = _worked_at(session, org_id, f.company_ids, f.current_only) if f.company_ids else None
    people = list(session.scalars(select(Candidate).where(Candidate.id.in_(list(profiles) or [None]))
                                  .order_by(Candidate.created_at.desc())))
    rows = []
    for person in people:
        if exclude and person.id in exclude:
            continue
        if at is not None and person.id not in at:
            continue
        met = passes(profiles[person.id], f)
        if met is None:
            continue
        if at is not None:
            met.append(("works at " if f.current_only else "worked at ") + ", ".join(at[person.id]))
        p = profiles[person.id]
        rows.append({"candidate_id": str(person.id), "summary": p["summary"], "reading": p["reading"]["label"], "met": met})
        if len(rows) >= limit:
            break
    who = names(session, [uuid.UUID(r["candidate_id"]) for r in rows])
    for r in rows:
        r["name"] = who.get(uuid.UUID(r["candidate_id"]))
    return rows


def job_filters(session: Session, job: Job) -> tuple[Filters, list[str]]:
    """The hard filters a job's hiring profile gives (its must-haves), and its target companies."""
    f, targets = Filters(), []
    for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.status.in_(LIVE))):
        p = c.approved_view or c.payload
        strength, cat = p.get("strength"), p.get("category")
        if cat == "target_company" and strength != "anti":
            targets += [x["company_id"] for x in p.get("companies") or [] if x.get("company_id")]
        if strength not in ("must", "deal_breaker"):
            continue
        if cat == "role" and p.get("role_family"):
            f.family = p["role_family"]
            if p.get("min_years"):
                f.min_years = p["min_years"] * 0.75  # a little short of the ask still deserves a look: matching decides
        elif cat == "seniority" and p.get("min_years") and not f.min_years:
            f.min_years = p["min_years"] * 0.75
        elif cat == "employer":
            f.employer_kinds += p.get("employer_kinds") or []
        elif cat == "domain":
            f.domains += p.get("domains") or []
    return f, sorted(set(targets))


def alumni(session: Session, org_id: uuid.UUID, company_id: uuid.UUID) -> list[dict[str, Any]]:
    """Everyone on the desk who has worked at this company, and when (target-company alumni)."""
    return companies.people_at(session, org_id, company_id)


# --- search in the recruiter's own words, ranked (owner's decision 2026-10-04) ------------------------------------

# How much each kind of criterion counts when ordering results. The order is shown with its reasons; no number is.
WEIGHT = {"role": 3, "skill": 3, "level": 2, "years": 2, "country": 2, "company": 2, "employer": 1, "domain": 1}
CREDIT = {"met": 1.0, "partly": 0.5, "missed": 0.0}


def _lives(session: Session, org_id: uuid.UUID, cid: uuid.UUID) -> list[str]:
    from maindscout.api import coverage

    return coverage.signals(session, org_id, cid)[0]


def _skills_and_titles(session: Session, org_id: uuid.UUID, cid: uuid.UUID) -> tuple[list[str], list[str]]:
    skills, titles = [], []
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == cid, Claim.status.in_(LIVE),
                                                 Claim.claim_type.in_(("SkillClaim", "CareerStepClaim")))):
        p = c.approved_view or c.payload
        if c.claim_type == "SkillClaim":
            skills.append(p["normalized_skill"])
        else:
            titles.append(p.get("title_raw", ""))
    return skills, titles


def _company_ids_by_name(session: Session, names: list[str]) -> dict[str, list[str]]:
    from maindscout.domain.companies import normalize

    out = {}
    for name in names:
        found = session.scalar(select(Company).where(Company.normalized == normalize(name).normalized))
        out[name] = sorted(_company_ids(session, [str(found.id)])) if found else []
    return out


def criteria_for(profile: dict[str, Any], q, skills: list[str], titles: list[str], lives: list[str],
                 worked: dict[str, bool]) -> list[dict[str, str]]:
    """Each criterion of the search, as met / partly / missed with the reason. Pure."""
    from maindscout.intelligence.triage import supports

    dims, out = profile["dimensions"], []
    ry, years = dims["relevant_years"], dims["relevant_years"].get("main_years", 0)
    if q.role_family:
        main = ry.get("main")
        label = FAMILY_LABEL.get(q.role_family, q.role_family)
        if main == q.role_family:
            out.append({"kind": "role", "label": label, "verdict": "met", "detail": f"works in {label}"})
        elif main and group_of(main) == group_of(q.role_family) and group_of(main) != main:
            out.append({"kind": "role", "label": label, "verdict": "partly", "detail": f"works in {FAMILY_LABEL.get(main, main)} (related)"})
        else:
            out.append({"kind": "role", "label": label, "verdict": "missed",
                        "detail": f"works in {FAMILY_LABEL.get(main, main)}" if main else "kind of work not clear"})
    if q.level:
        have = dims["seniority"].get("label")
        diff = LEVEL_RANK[have] - LEVEL_RANK[q.level] if have in LEVEL_RANK and q.level in LEVEL_RANK else None
        verdict = "met" if diff is not None and diff >= 0 else "partly" if diff == -1 else "missed"
        out.append({"kind": "level", "label": q.level, "verdict": verdict, "detail": f"{have or 'no level'} by title"})
    if q.min_years:
        verdict = "met" if years >= q.min_years else "partly" if years >= 0.75 * q.min_years else "missed"
        out.append({"kind": "years", "label": f"{q.min_years:g}+ years", "verdict": verdict, "detail": f"{years:g} years of related work"})
    for sk in q.skills:
        token, need = sk["token"], sk.get("min_years")
        label = token + (f", {need:g}+ years" if need else "")
        if not supports(token, skills, titles):
            out.append({"kind": "skill", "label": label, "verdict": "missed", "detail": f"no {token} on the CV"})
        elif need and years < need:
            out.append({"kind": "skill", "label": label, "verdict": "partly", "detail": f"{token} on the CV; {years:g} years of related work"})
        else:
            extra = f"; {years:g} years of related work (CVs do not date each skill)" if need else ""
            out.append({"kind": "skill", "label": label, "verdict": "met", "detail": f"{token} on the CV{extra}"})
    if q.countries:
        names = ", ".join(q.countries)
        if not lives:
            out.append({"kind": "country", "label": f"lives in {names}", "verdict": "partly", "detail": "where they live is not stated"})
        else:
            hit = any(c in q.countries for c in lives)
            out.append({"kind": "country", "label": f"lives in {names}", "verdict": "met" if hit else "missed", "detail": f"lives in {', '.join(lives)}"})
    if q.employer_kinds:
        yrs = dims["employer_mix"].get("years") or {}
        have = sum(yrs.get(k, 0) for k in q.employer_kinds)
        names = " / ".join(k.replace("_", " ") for k in q.employer_kinds)
        out.append({"kind": "employer", "label": f"time at {names}", "verdict": "met" if have >= 1 else "partly" if have > 0 else "missed",
                    "detail": f"{have:g} years at {names}"})
    if q.domains:
        yrs = dims["domain_exposure"].get("years") or {}
        have = max((yrs.get(d, 0) for d in q.domains), default=0)
        names = " / ".join(q.domains)
        out.append({"kind": "domain", "label": f"time in {names}", "verdict": "met" if have >= 1 else "partly" if have > 0 else "missed",
                    "detail": f"{have:g} years in {names}"})
    for name, hit in worked.items():
        out.append({"kind": "company", "label": f"worked at {name}", "verdict": "met" if hit else "missed",
                    "detail": f"worked at {name}" if hit else f"not at {name}"})
    return out


def ranked(session: Session, org_id: uuid.UUID, q, limit: int = 100) -> list[dict[str, Any]]:
    """Everyone with a career profile who meets at least part of the search, best first: most important criteria met
    first (kind of work and skills count most), then most criteria met, then newest. Each result carries its reasons."""
    from maindscout.api.queries import names

    profiles = _latest_profiles(session, org_id)
    company_ids = _company_ids_by_name(session, q.companies) if q.companies else {}
    worked_by: dict[uuid.UUID, set[str]] = {}
    if company_ids:
        for name, ids in company_ids.items():
            for cid in _worked_at(session, org_id, ids, q.current_company_only) if ids else {}:
                worked_by.setdefault(cid, set()).add(name)
    people = list(session.scalars(select(Candidate).where(Candidate.id.in_(list(profiles) or [None]))
                                  .order_by(Candidate.created_at.desc())))
    rows = []
    for order, person in enumerate(people):
        skills, titles = _skills_and_titles(session, org_id, person.id) if q.skills else ([], [])
        lives = _lives(session, org_id, person.id) if q.countries else []
        worked = {name: name in worked_by.get(person.id, set()) for name in q.companies}
        crit = criteria_for(profiles[person.id], q, skills, titles, lives, worked)
        weight = sum(WEIGHT[c["kind"]] * CREDIT[c["verdict"]] for c in crit)
        if crit and weight == 0:
            continue
        met = sum(c["verdict"] == "met" for c in crit)
        p = profiles[person.id]
        rows.append({"candidate_id": str(person.id), "summary": p["summary"], "reading": p["reading"]["label"],
                     "criteria": crit, "met_words": f"meets {met} of {len(crit)}" if crit else "",
                     "_key": (-weight, -met, order)})
    rows.sort(key=lambda r: r["_key"])
    rows = rows[:limit]
    who = names(session, [uuid.UUID(r["candidate_id"]) for r in rows])
    for r in rows:
        r.pop("_key")
        r["name"] = who.get(uuid.UUID(r["candidate_id"]))
    return rows


def understood(q) -> list[str]:
    """How the search was read, in words, so the recruiter can see (and correct) the reading."""
    from maindscout.domain import geo

    out = []
    if q.level:
        out.append(q.level)
    if q.role_family:
        out.append(FAMILY_LABEL.get(q.role_family, q.role_family))
    if q.min_years:
        out.append(f"{q.min_years:g}+ years")
    out += [s["token"] + (f" {s['min_years']:g}+ years" if s.get("min_years") else "") for s in q.skills]
    out += [f"lives in {geo.name_of(c)}" for c in q.countries]
    out += [f"time at {k.replace('_', ' ')}" for k in q.employer_kinds]
    out += [f"time in {d}" for d in q.domains]
    out += [("works at " if q.current_company_only else "worked at ") + c for c in q.companies]
    return out
