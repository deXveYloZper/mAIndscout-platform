"""Companies: resolve names to shared company records, merge by human decision, and answer "who do we know there".

Companies live in the shared public tier. Which people worked at a company is read from each desk's own career
claims (org-scoped), so one desk never sees another desk's people.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from maindscout.db.models import Candidate, Claim, Company, CompanyAlias, Decision, DecisionItem, Job
from maindscout.domain import companies as names

LIVE = ("proposed", "approved")


def canonical(session: Session, company: Company | None) -> Company | None:
    """Follow merge redirects to the company that stands today."""
    seen = set()
    while company is not None and company.merged_into_id and company.id not in seen:
        seen.add(company.id)
        company = session.get(Company, company.merged_into_id)
    return company


def resolve(session: Session, raw_name: str, source: str, org_id: uuid.UUID | None = None,
            subject_id: uuid.UUID | None = None) -> tuple[Company | None, names.CompanyName]:
    """Exact match on the normalised name, else a new company. Self-employment and undisclosed names are not
    companies. A new name that looks like an existing one raises a "Same company?" card for a human (when the
    caller gives an org and subject to file it under); it is never merged automatically."""
    parsed = names.normalize(raw_name)
    if parsed.kind != "company":
        return None, parsed
    alias = session.get(CompanyAlias, parsed.normalized)
    if alias is not None:
        return canonical(session, session.get(Company, alias.company_id)), parsed
    company = Company(name=parsed.display, normalized=parsed.normalized)
    session.add(company)
    session.flush()
    session.add(CompanyAlias(normalized=parsed.normalized, company_id=company.id, source=source))
    session.flush()
    if org_id is not None and subject_id is not None:
        _suggest_duplicates(session, company, org_id, subject_id)
    return company, parsed


def _suggest_duplicates(session: Session, company: Company, org_id: uuid.UUID, subject_id: uuid.UUID) -> None:
    first = company.normalized.split()[0]
    nearby = session.scalars(select(CompanyAlias).where(
        CompanyAlias.company_id != company.id,
        or_(CompanyAlias.normalized.like(f"{first}%"), func.length(CompanyAlias.normalized).between(len(company.normalized) - 1, len(company.normalized) + 1))))
    for alias in nearby:
        if names.possibly_same(company.normalized, alias.normalized):
            other = canonical(session, session.get(Company, alias.company_id))
            if other is None or other.id == company.id:
                continue
            session.add(Decision(org_id=org_id, type="company_same", priority=30, subject_type="company",
                                 subject_id=company.id, context={
                                     "question": "same company?",
                                     "new": {"id": str(company.id), "name": company.name},
                                     "existing": {"id": str(other.id), "name": other.name},
                                     "candidate_id": str(subject_id)}))
            session.flush()
            return


def merge(session: Session, keep_id: uuid.UUID, drop_id: uuid.UUID) -> Company:
    """Fold one company into another: a redirect plus its aliases. Claims keep pointing at the old id and are read
    through the redirect, so nothing about any person is rewritten."""
    keep, drop = canonical(session, session.get(Company, keep_id)), canonical(session, session.get(Company, drop_id))
    if keep is None or drop is None:
        raise LookupError("No such company")
    if keep.id == drop.id:
        return keep
    drop.merged_into_id = keep.id
    for alias in session.scalars(select(CompanyAlias).where(CompanyAlias.company_id == drop.id)):
        alias.company_id = keep.id
    session.flush()
    return keep


def _ids_for(session: Session, company: Company) -> list[str]:
    """The company and everything merged into it."""
    ids, frontier = {company.id}, [company.id]
    while frontier:
        children = list(session.scalars(select(Company.id).where(Company.merged_into_id.in_(frontier))))
        frontier = [c for c in children if c not in ids]
        ids.update(frontier)
    return [str(i) for i in ids]


def people_at(session: Session, org_id: uuid.UUID, company_id: uuid.UUID) -> list[dict[str, Any]]:
    """Who this desk knows at a company: people with a live career step there, with title and period."""
    company = canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    ids = _ids_for(session, company)
    steps = session.scalars(select(Claim).where(
        Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
        Claim.payload["company"]["company_id"].astext.in_(ids)).order_by(Claim.valid_from.desc().nulls_last()))
    from maindscout.api.queries import names as person_names

    rows = list(steps)
    who = person_names(session, list({c.subject_id for c in rows}))
    return [{"candidate_id": str(c.subject_id), "name": who.get(c.subject_id), "title": c.payload.get("title_raw"),
             "valid_from": c.valid_from.isoformat() if c.valid_from else None,
             "valid_to": c.valid_to.isoformat() if c.valid_to else None, "current": c.valid_to is None,
             "status": c.status} for c in rows]


def company_page(session: Session, org_id: uuid.UUID, company_id: uuid.UUID) -> dict[str, Any]:
    company = canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    aliases = list(session.scalars(select(CompanyAlias.normalized).where(CompanyAlias.company_id == company.id)))
    jobs = session.scalars(select(Job).where(Job.org_id == org_id, Job.hiring_company_id.in_([uuid.UUID(i) for i in _ids_for(session, company)])))
    stints = people_at(session, org_id, company.id)
    grouped: dict[str, dict[str, Any]] = {}
    for st in stints:  # one row per person, every role they held there
        row = grouped.setdefault(st["candidate_id"], {"candidate_id": st["candidate_id"], "name": st["name"], "roles": [], "current": False})
        row["roles"].append({k: st[k] for k in ("title", "valid_from", "valid_to", "current")})
        row["current"] = row["current"] or st["current"]
    from maindscout.api import relationship, research

    return {"id": str(company.id), "name": company.name, "website": company.website, "hq_country": company.hq_country,
            "research_status": company.research_status,
            "researched_at": company.researched_at.isoformat() if company.researched_at else None,
            "facts": research.facts(session, company),
            "aliases": sorted(aliases), "people": list(grouped.values()), "people_count": len(grouped),
            "jobs": [{"id": str(j.id), "title": j.title} for j in jobs],
            "contacts": relationship.contacts_at(session, org_id, [uuid.UUID(i) for i in _ids_for(session, company)]),
            "timeline": relationship.timeline(session, org_id, "company", company.id),
            "last_contacted": (lambda d: d.isoformat() if d else None)(relationship.last_contacted(session, org_id, "company", company.id))}


def search(session: Session, org_id: uuid.UUID, q: str | None, limit: int = 50) -> list[dict[str, Any]]:
    """Companies this desk has touched (through people or jobs), optionally filtered by name, most people first."""
    steps = session.execute(select(Claim.payload["company"]["company_id"].astext, Claim.subject_id).where(
        Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
        Claim.payload["company"]["company_id"].astext.is_not(None))).all()
    counts: dict[uuid.UUID, set] = {}
    for cid, person in steps:
        company = canonical(session, session.get(Company, uuid.UUID(cid)))
        if company:
            counts.setdefault(company.id, set()).add(person)
    for job in session.scalars(select(Job).where(Job.org_id == org_id, Job.hiring_company_id.is_not(None))):
        company = canonical(session, session.get(Company, job.hiring_company_id))
        if company:
            counts.setdefault(company.id, set())
    out = []
    needle = names.normalize(q).normalized if q else None
    for company_id, people in counts.items():
        company = session.get(Company, company_id)
        if needle:
            aliases = set(session.scalars(select(CompanyAlias.normalized).where(CompanyAlias.company_id == company_id)))
            if not any(needle in a for a in aliases | {company.normalized}):
                continue
        out.append({"id": str(company.id), "name": company.name, "people_count": len(people)})
    out.sort(key=lambda c: (-c["people_count"], c["name"].lower()))
    return out[:limit]


def link_org(session: Session, org_id: uuid.UUID) -> dict[str, int]:
    """Resolve companies for this desk's existing career steps and jobs that have no company link yet."""
    linked = 0
    for claim in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim",
                                                     Claim.status.in_(LIVE))):
        company_part = (claim.payload or {}).get("company") or {}
        if company_part.get("company_id"):
            continue
        company, _ = resolve(session, company_part.get("raw_name", ""), "cv", org_id, claim.subject_id)
        if company is not None:
            claim.payload = {**claim.payload, "company": {**company_part, "company_id": str(company.id)}}
            if claim.approved_view:
                claim.approved_view = {**claim.approved_view, "company": {**claim.approved_view.get("company", {}), "company_id": str(company.id)}}
            linked += 1
    jobs = 0
    for job in session.scalars(select(Job).where(Job.org_id == org_id, Job.hiring_company_id.is_(None), Job.hiring_company.is_not(None))):
        company, _ = resolve(session, job.hiring_company, "jd")
        if company is not None:
            job.hiring_company_id = company.id
            jobs += 1
    session.flush()
    return {"career_steps_linked": linked, "jobs_linked": jobs}
