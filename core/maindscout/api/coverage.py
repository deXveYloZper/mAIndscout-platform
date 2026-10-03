"""The coverage gate: archive people who live or work outside every country the desk and their jobs accept, so no
further paid intelligence (company research, career profiles, matching) is spent on them.

- The desk covers the EU / EEA, the UK, Switzerland, the US and Canada (`COVERAGE_COUNTRIES` to change).
- A job widens it: countries its ad names ("live in or work from: Brazil") and countries a recruiter opens on it.
- Signals, all free: where the person says they live now; where each current job is; only if a job's place is
  unknown, where the employer is based (when we already know it). Unknown is never outside.
- Never nationality, birthplace, name or where someone studied ([ADR](docs/decisions/2026-10-03-coverage-gate.md)).
- Archived is not deleted and not final: a person can bring anyone back, and the gate then leaves them be.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.db.models import Candidate, CandidateJob, Claim, Company, Job
from maindscout.domain import geo
from maindscout.settings import env

LIVE = ("proposed", "approved")


def desk_countries() -> frozenset[str]:
    raw = env("COVERAGE_COUNTRIES", "") or ""
    codes = {c.strip().upper() for c in raw.split(",") if re.fullmatch(r"\s*[A-Za-z]{2}\s*", c)}
    return frozenset(codes) if codes else geo.DEFAULT_COVERAGE


def ad_countries(session: Session, job: Job) -> set[str]:
    """Countries the job ad itself says people may live in or work from."""
    out: set[str] = set()
    for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.status.in_(LIVE))):
        mobility = c.payload.get("mobility") or {}
        if mobility.get("facet") == "residence":
            out |= set(mobility.get("countries") or [])
    return out


def job_countries(session: Session, job: Job) -> frozenset[str]:
    return desk_countries() | ad_countries(session, job) | set(job.open_countries or [])


def _jobs_of(session: Session, org_id, candidate_id) -> list[Job]:
    return list(session.scalars(select(Job).join(CandidateJob, CandidateJob.job_id == Job.id).where(
        CandidateJob.org_id == org_id, CandidateJob.candidate_id == candidate_id)))


def accepted(session: Session, org_id, candidate_id, extra_job: Job | None = None) -> frozenset[str]:
    countries = set(desk_countries())
    for job in _jobs_of(session, org_id, candidate_id) + ([extra_job] if extra_job else []):
        countries |= job_countries(session, job)
    return frozenset(countries)


def signals(session: Session, org_id, candidate_id) -> tuple[list[str], list[tuple[str, str]]]:
    """(countries the person lives in now, [(country, 'role' | 'employer') for each current job])."""
    lives: list[str] = []
    works: list[tuple[str, str]] = []
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                 Claim.status.in_(LIVE),
                                                 Claim.claim_type.in_(("LocationClaim", "CareerStepClaim")))
                             .order_by(Claim.created_at)):
        p = c.payload
        if c.claim_type == "LocationClaim":
            if p.get("kind", "current") == "current":
                code = p.get("country_code") or geo.country_in(p.get("place_raw"))
                if code and code not in lives:
                    lives.append(code)
            continue
        if c.valid_to is not None or p.get("employment_type") == "side":
            continue
        code = p.get("location_country") or geo.country_in(p.get("location_raw"))
        if code:
            works.append((code, "role"))
            continue
        company_id = (p.get("company") or {}).get("company_id")
        company = session.get(Company, uuid.UUID(company_id)) if company_id else None
        if company is not None and company.hq_country:
            works.append((company.hq_country, "employer"))
    return lives, works


def evaluate(session: Session, org_id, candidate_id, cause: dict[str, Any], actor: str = "system") -> geo.Verdict:
    """Archive or un-archive one person from the facts we have now. A person who is (still) in coverage gets their
    company research queued (deduplicated, and skipped while facts are fresh)."""
    person = session.get(Candidate, candidate_id)
    if person is None:
        raise LookupError(f"No candidate {candidate_id}")
    if person.coverage_override:
        verdict = geo.Verdict(False)
    else:
        lives, works = signals(session, org_id, candidate_id)
        verdict = geo.decide(lives, works, accepted(session, org_id, candidate_id))
    if verdict.outside:
        reason = {"text": verdict.reason, "basis": verdict.basis, "country": verdict.country, "by": actor, "cause": cause}
        if person.archived_at is None:
            person.archived_at = datetime.now(timezone.utc)
        if (person.archived_reason or {}).get("text") != verdict.reason:
            person.archived_reason = reason
    else:
        if person.archived_at is not None:
            person.archived_at, person.archived_reason = None, None
        from maindscout.api import profiles
        from maindscout.api.process import _queue_research

        _queue_research(session, candidate_id, org_id)
        profiles.queue(session, org_id, candidate_id)
    session.flush()
    return verdict


def would_accept(session: Session, org_id, candidate_id, job: Job) -> bool:
    """Would this person be in coverage if they were on this job? (Sourcing skips archived people otherwise.)"""
    person = session.get(Candidate, candidate_id)
    if person is None or person.archived_at is None or person.coverage_override:
        return True
    lives, works = signals(session, org_id, candidate_id)
    return not geo.decide(lives, works, accepted(session, org_id, candidate_id, job)).outside


def bring_back(session: Session, org_id, candidate_id, actor: str) -> Candidate:
    """A person decided this one is worth working on: un-archive and stop the gate from archiving them again."""
    person = session.get(Candidate, candidate_id)
    if person is None or person.org_id != org_id:
        raise LookupError(f"No candidate {candidate_id}")
    person.coverage_override = True
    evaluate(session, org_id, candidate_id, {"act": "brought_back"}, actor)
    return person


def reevaluate_job(session: Session, job: Job, cause: dict[str, Any], actor: str = "system") -> int:
    pairs = list(session.scalars(select(CandidateJob.candidate_id).where(CandidateJob.job_id == job.id)))
    for cid in pairs:
        evaluate(session, job.org_id, cid, cause, actor)
    return len(pairs)


def reevaluate_company(session: Session, company_id: uuid.UUID) -> int:
    """New facts about where a company is based: re-check everyone whose current job there has no place of its own."""
    rows = session.execute(select(Claim.org_id, Claim.subject_id).where(
        Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE), Claim.valid_to.is_(None),
        Claim.payload["company"]["company_id"].astext == str(company_id)).distinct()).all()
    for org_id, cid in rows:
        evaluate(session, org_id, cid, {"act": "company_researched", "company_id": str(company_id)})
    return len(rows)


def set_open_countries(session: Session, org_id, job_id: uuid.UUID, countries: list[str], actor: str) -> list[str]:
    """Open a job to countries beyond the desk's coverage (ISO codes or country names). Re-checks its people."""
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    codes: list[str] = []
    for raw in countries:
        raw = raw.strip()
        if not raw:
            continue
        code = raw.upper() if re.fullmatch(r"[A-Za-z]{2}", raw) else geo.country_in(raw)
        if not code or not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError(f"Not a country we recognise: {raw!r}")
        if code not in codes:
            codes.append(code)
    job.open_countries = sorted(codes)
    session.flush()
    reevaluate_job(session, job, {"act": "job_countries", "job_id": str(job.id)}, actor)
    return job.open_countries


def summary(session: Session, job: Job) -> dict[str, Any]:
    desk = desk_countries()
    return {"desk": sorted(desk), "from_ad": sorted(ad_countries(session, job) - desk),
            "opened": sorted(job.open_countries or []),
            "names": {c: geo.name_of(c) for c in ad_countries(session, job) | set(job.open_countries or [])}}
