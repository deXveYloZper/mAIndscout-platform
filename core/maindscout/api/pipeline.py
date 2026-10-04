"""The pipeline (Slice 4, step 2): client blocks and the pipeline's shape on a job.

A client's rejection is a wall: the person is blocked at that client company (every job there, including companies
merged into it) until a person lifts the block with a note. Blocked people cannot be put in front of that client,
are not sourced for its jobs, and matching marks them unlikely there with the reason.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.db.models import CLIENT_STAGES, PAIR_STATES, CandidateJob, ClientBlock, Company, Job


class BlockedError(ValueError):
    pass


def _company_ids(session: Session, company_id: uuid.UUID | None) -> list[uuid.UUID]:
    if company_id is None:
        return []
    company = session.get(Company, company_id)
    while company is not None and company.merged_into_id:
        company = session.get(Company, company.merged_into_id)
    if company is None:
        return []
    return [company.id] + list(session.scalars(select(Company.id).where(Company.merged_into_id == company.id)))


def active_block(session: Session, org_id, job_id: uuid.UUID, candidate_id) -> ClientBlock | None:
    job = session.get(Job, job_id)
    ids = _company_ids(session, job.hiring_company_id if job else None)
    if not ids:
        return None
    return session.scalar(select(ClientBlock).where(ClientBlock.org_id == org_id, ClientBlock.candidate_id == candidate_id,
                                                    ClientBlock.company_id.in_(ids), ClientBlock.lifted_at.is_(None))
                          .order_by(ClientBlock.created_at.desc()).limit(1))


def ensure_not_blocked(session: Session, org_id, job_id: uuid.UUID, candidate_id, state: str) -> None:
    if state not in CLIENT_STAGES:
        return
    b = active_block(session, org_id, job_id, candidate_id)
    if b is not None:
        company = session.get(Company, b.company_id)
        raise BlockedError(f"{company.name if company else 'This client'} said no to this person ({b.reason}); "
                           "lift the block with a note first if that has changed")


def block(session: Session, org_id, job_id: uuid.UUID, candidate_id, reason: str, actor: str) -> ClientBlock | None:
    job = session.get(Job, job_id)
    ids = _company_ids(session, job.hiring_company_id if job else None)
    if not ids:
        return None  # no known hiring company: the rejection stays on this job only
    existing = active_block(session, org_id, job_id, candidate_id)
    if existing is not None:
        return existing
    b = ClientBlock(org_id=org_id, company_id=ids[0], candidate_id=candidate_id, job_id=job_id, reason=reason[:2000], created_by=actor)
    session.add(b)
    session.flush()
    from maindscout.api.process import retriage_candidate

    retriage_candidate(session, org_id, candidate_id, {"act": "client_block", "block_id": str(b.id)}, actor)
    return b


def lift(session: Session, org_id, block_id: uuid.UUID, note: str, actor: str) -> ClientBlock:
    b = session.get(ClientBlock, block_id)
    if b is None or b.org_id != org_id:
        raise LookupError(f"No block {block_id}")
    if not (note or "").strip():
        raise ValueError("Say why the block is lifted")
    if b.lifted_at is None:
        b.lifted_at, b.lifted_by, b.lift_note = datetime.now(timezone.utc), actor, note.strip()[:2000]
        session.flush()
        from maindscout.api.process import retriage_candidate

        retriage_candidate(session, org_id, b.candidate_id, {"act": "client_block_lifted", "block_id": str(b.id)}, actor)
    return b


def blocks_for_person(session: Session, org_id, candidate_id) -> list[dict[str, Any]]:
    out = []
    for b in session.scalars(select(ClientBlock).where(ClientBlock.org_id == org_id, ClientBlock.candidate_id == candidate_id)
                             .order_by(ClientBlock.created_at.desc())):
        company = session.get(Company, b.company_id)
        out.append({"id": str(b.id), "company_id": str(b.company_id), "company": company.name if company else None,
                    "reason": b.reason, "at": b.created_at.isoformat() if b.created_at else None, "by": b.created_by,
                    "lifted": b.lifted_at is not None, "lift_note": b.lift_note})
    return out


def blocked_ids_for_job(session: Session, org_id, job: Job) -> set[uuid.UUID]:
    ids = _company_ids(session, job.hiring_company_id)
    if not ids:
        return set()
    return set(session.scalars(select(ClientBlock.candidate_id).where(
        ClientBlock.org_id == org_id, ClientBlock.company_id.in_(ids), ClientBlock.lifted_at.is_(None))))


def stage_counts(session: Session, job_id: uuid.UUID) -> dict[str, int]:
    counts = dict(session.execute(select(CandidateJob.pair_state, func.count()).where(CandidateJob.job_id == job_id)
                                  .group_by(CandidateJob.pair_state)).all())
    return {s: counts.get(s, 0) for s in PAIR_STATES}
