"""Sourcing feeder (Slice 2): refill a thin priority queue on a live job, through the same triage as uploads.

Sourcing is not a second product. A campaign derives a query from the job's must-haves, asks one source
adapter for people, and puts each one on the job with the ordinary pair + triage path. Being sourced never
changes a band (P13: a sourcing signal must not become a scoring feature); it is only noted in the pair's
history. Campaigns stop at their cap, when priority reaches the target, or when a human stops them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.api.process import _ensure_pair
from maindscout.db.models import Campaign, Candidate, CandidateJob, CareerProfile, Claim, Job
from maindscout.intelligence.triage import supports

DEFAULT_TARGET = 5
DEFAULT_CAP = 25
MAX_CAP = 200
LIVE = ("proposed", "approved")


class SourcingError(ValueError):
    pass


class SourceAdapter(Protocol):
    name: str

    def find(self, session: Session, org_id: uuid.UUID, job: Job, query: dict, limit: int) -> list[uuid.UUID]:
        """Up to `limit` candidate ids not yet on the job, in a fixed order that is NOT a ranking by fit."""


class DeskAdapter:
    """The desk's own people graph: everyone already read into the platform (the pool and people on other jobs)
    whose skills or job titles mention one of the tokens. Order: newest first, never by how well they match."""

    name = "desk"

    def find(self, session: Session, org_id: uuid.UUID, job: Job, query: dict, limit: int) -> list[uuid.UUID]:
        tokens = query["tokens"]
        on_job = select(CandidateJob.candidate_id).where(CandidateJob.job_id == job.id)
        people = session.scalars(select(Candidate).where(Candidate.org_id == org_id, Candidate.merged_into_id.is_(None),
                                                         Candidate.id.not_in(on_job)).order_by(Candidate.created_at.desc()))
        found: list[uuid.UUID] = []
        for person in people:
            claims = list(session.scalars(select(Claim).where(Claim.subject_id == person.id, Claim.status.in_(LIVE),
                                                              Claim.claim_type.in_(("SkillClaim", "CareerStepClaim")))))
            skills = [c.payload["normalized_skill"] for c in claims if c.claim_type == "SkillClaim"]
            titles = [c.payload.get("title_raw", "") for c in claims if c.claim_type == "CareerStepClaim"]
            if any(supports(t, skills, titles) for t in tokens):
                from maindscout.api import coverage

                if not coverage.would_accept(session, org_id, person.id, job):
                    continue  # archived as outside coverage, and this job does not accept their country either
                found.append(person.id)
                if len(found) >= limit:
                    break
        return found


class ProfileAdapter:
    """I6: the desk's people by career profile. First the alumni of the job's target companies (the hiring manager
    named them), then everyone whose profile meets the job's must-haves; newest first within each. The order is by
    channel, never by fit: matching decides the band of everyone found."""

    name = "profile"

    def find(self, session: Session, org_id: uuid.UUID, job: Job, query: dict, limit: int) -> list[uuid.UUID]:
        from maindscout.api import coverage, search

        on_job = set(session.scalars(select(CandidateJob.candidate_id).where(CandidateJob.job_id == job.id)))
        found: list[uuid.UUID] = []
        channels = []
        if query.get("targets"):
            channels.append(search.Filters(company_ids=query["targets"]))
        channels.append(search.Filters(**query["filters"]))
        for f in channels:
            for row in search.search(session, org_id, f, exclude=on_job | set(found)):
                cid = uuid.UUID(row["candidate_id"])
                if coverage.would_accept(session, org_id, cid, job):
                    found.append(cid)
                    if len(found) >= limit:
                        return found
        return found


ADAPTERS: dict[str, SourceAdapter] = {"desk": DeskAdapter(), "profile": ProfileAdapter()}


def profile_query(session: Session, job: Job) -> dict | None:
    """The profile search a job's hiring profile gives, or None if it gives nothing to search by."""
    from maindscout.api import search

    f, targets = search.job_filters(session, job)
    if not (f.family or f.employer_kinds or f.domains or targets):
        return None
    words = f.words() + ([f"alumni of {len(targets)} target compan{'y' if len(targets) == 1 else 'ies'} first"] if targets else [])
    return {"filters": f.as_dict(), "targets": targets, "words": words}


def query_tokens(session: Session, job: Job) -> list[str]:
    """Distinctive must-haves first; if the job has none, its must-have skill tokens."""
    reqs = [c.payload for c in session.scalars(select(Claim).where(
        Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim", Claim.status.in_(LIVE)))]
    must = [r for r in reqs if r.get("category") == "skill" and r.get("strength") in ("must", "deal_breaker") and r.get("normalized_token")]
    distinctive = sorted({r["normalized_token"] for r in must if r.get("distinctive")})
    return distinctive or sorted({r["normalized_token"] for r in must})


def priority_count(session: Session, job_id: uuid.UUID) -> int:
    return session.scalar(select(func.count()).select_from(CandidateJob).where(
        CandidateJob.job_id == job_id, CandidateJob.triage_band == "priority")) or 0


def start(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, actor: str, source: str = "auto",
          cap: int = DEFAULT_CAP, target: int = DEFAULT_TARGET) -> Campaign:
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    if source == "auto":  # the hiring profile when it gives something to search by and people have profiles
        source = "profile" if profile_query(session, job) and session.scalar(select(func.count()).select_from(CareerProfile)) else "desk"
    if source not in ADAPTERS:
        raise SourcingError(f"Unknown source {source!r}; available: {sorted(ADAPTERS)}")
    if not 1 <= cap <= MAX_CAP or not 1 <= target <= 100:
        raise SourcingError(f"cap must be 1-{MAX_CAP} and target 1-100")
    if priority_count(session, job.id) >= target:
        raise SourcingError(f"This job already has {target} or more priority people; sourcing is for a thin queue")
    if session.scalar(select(Campaign.id).where(Campaign.job_id == job.id, Campaign.status == "running")):
        raise SourcingError("A campaign is already running for this job")
    if source == "profile":
        query = profile_query(session, job)
        if query is None:
            raise SourcingError("This job's hiring profile gives nothing to search by yet (no role, background, industry or target companies)")
    else:
        tokens = query_tokens(session, job)
        if not tokens:
            raise SourcingError("This job has no must-have skills to search for yet")
        query = {"tokens": tokens}
    campaign = Campaign(org_id=org_id, job_id=job.id, source=source, query=query, cap=cap,
                        target_priority=target, created_by=actor)
    session.add(campaign)
    session.flush()
    return run(session, campaign)


def run(session: Session, campaign: Campaign) -> Campaign:
    """Look at people one by one until the cap, the target, or the source runs out."""
    job = session.get(Job, campaign.job_id)
    adapter = ADAPTERS[campaign.source]
    while campaign.status == "running":
        if priority_count(session, job.id) >= campaign.target_priority:
            return _end(campaign, "stopped", "target_reached")
        if campaign.spent >= campaign.cap:
            return _end(campaign, "stopped", "cap")
        batch = adapter.find(session, campaign.org_id, job, campaign.query, limit=1)
        if not batch:
            return _end(campaign, "exhausted", None)
        campaign.spent += 1
        pair = _ensure_pair(session, campaign.org_id, batch[0], job,
                            cause={"act": "sourced", "campaign_id": str(campaign.id), "source": campaign.source})
        campaign.added += 1
        if pair.triage_band == "priority":
            campaign.priority_added += 1
        session.flush()
    return campaign


def stop(session: Session, org_id: uuid.UUID, campaign_id: uuid.UUID, actor: str) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise LookupError(f"No campaign {campaign_id}")
    if campaign.status == "running":
        _end(campaign, "stopped", "human")
    session.flush()
    return campaign


def _end(campaign: Campaign, status: str, reason: str | None) -> Campaign:
    campaign.status, campaign.stop_reason, campaign.ended_at = status, reason, datetime.now(timezone.utc)
    return campaign


def as_dict(c: Campaign) -> dict:
    return {"id": str(c.id), "job_id": str(c.job_id), "source": c.source, "query": c.query, "cap": c.cap,
            "target_priority": c.target_priority, "spent": c.spent, "added": c.added, "priority_added": c.priority_added,
            "status": c.status, "stop_reason": c.stop_reason, "created_by": c.created_by,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "ended_at": c.ended_at.isoformat() if c.ended_at else None}
