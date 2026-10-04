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
