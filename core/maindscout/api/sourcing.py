"""The pool step of every sourcing run (autosource.run, step 1): the desk's own people, found by the role's distinctive
skills (DeskAdapter) or by its hiring profile (ProfileAdapter), and put on the role through the ordinary pair + matching
path. Being found never changes a band (P13: a sourcing signal must not become a scoring feature); it is only noted in
the pair's history. (Slice 2's campaigns, which wrapped these adapters, were removed with their endpoint: 2026-10-13
the endpoint, 2026-10-19 the code. Old `campaign` rows stay as history.)
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.db.models import Candidate, CandidateJob, Claim, Job
from maindscout.intelligence.triage import supports

LIVE = ("proposed", "approved")


class SourcingError(ValueError):
    pass


class SourceAdapter(Protocol):
    name: str

    def find(self, session: Session, org_id: uuid.UUID, job: Job, query: dict, limit: int,
             exclude: frozenset[uuid.UUID] = frozenset()) -> list[uuid.UUID]:
        """Up to `limit` candidate ids not yet on the job and not in `exclude`, in a fixed order that is NOT a ranking
        by fit."""


class DeskAdapter:
    """The desk's own people graph: everyone already read into the platform (the pool and people on other jobs)
    whose skills or job titles mention one of the tokens. Order: newest first, never by how well they match."""

    name = "desk"

    def find(self, session: Session, org_id: uuid.UUID, job: Job, query: dict, limit: int,
             exclude: frozenset[uuid.UUID] = frozenset()) -> list[uuid.UUID]:
        from maindscout.api.pipeline import blocked_ids_for_job

        from maindscout.api.process import not_wanted_by

        tokens = query["tokens"]
        blocked = blocked_ids_for_job(session, org_id, job) | not_wanted_by(session, org_id, job) | set(exclude)
        on_job = select(CandidateJob.candidate_id).where(CandidateJob.job_id == job.id)
        people = session.scalars(select(Candidate).where(Candidate.org_id == org_id, Candidate.merged_into_id.is_(None),
                                                         Candidate.id.not_in(on_job)).order_by(Candidate.created_at.desc()))
        found: list[uuid.UUID] = []
        for person in people:
            if person.id in blocked:
                continue
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

    def find(self, session: Session, org_id: uuid.UUID, job: Job, query: dict, limit: int,
             exclude: frozenset[uuid.UUID] = frozenset()) -> list[uuid.UUID]:
        from maindscout.api import coverage, search

        from maindscout.api.pipeline import blocked_ids_for_job

        on_job = set(session.scalars(select(CandidateJob.candidate_id).where(CandidateJob.job_id == job.id)))
        from maindscout.api.process import not_wanted_by

        on_job |= blocked_ids_for_job(session, org_id, job)  # the client said no to them: never sourced for this client
        on_job |= not_wanted_by(session, org_id, job)  # they said they will not consider a job like this one
        on_job |= set(exclude)
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
