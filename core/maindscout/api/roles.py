"""A role's life (x-ray B6, owner 2026-10-13: "there is no way to delete the job or archive the job").

- **Close**: on hold, filled or cancelled. Sourcing stops (its plan is paused), the role leaves the open lists, and
  everything on it (people, history, messages) is kept. It can be opened again.
- **Delete**: for a role added by mistake. The role, its hiring profile, its pairs, its sourcing and its ad go; spend
  stays in the ledger (real money spent). Optionally the people its own sourcing found who are on no other role and are
  known only from public profiles go too, without being put on the never-again list (a later search may find them).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from maindscout.db.models import (
    Activity,
    BriefItem,
    CallReview,
    Campaign,
    CandidateJob,
    Claim,
    ClaimObservation,
    ClientBlock,
    CompanySignal,
    Decision,
    DecisionItem,
    Document,
    DocumentSubject,
    Evidence,
    ExtractionArtifact,
    IntelligenceRun,
    Job,
    JobIntake,
    Message,
    PairEvent,
    Permission,
    Score,
    SourcingHit,
    SourcingPlan,
    SourcingQuery,
    SourcingRun,
    Task,
)
from maindscout.storage import BlobStore

STATES = ("open", "on_hold", "filled", "cancelled")
WORDS = {"open": "open again", "on_hold": "on hold", "filled": "filled", "cancelled": "cancelled"}


def _job(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    return job


def set_state(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, state: str, actor: str, note: str | None = None) -> Job:
    """Close a role (on hold, filled, cancelled) or open it again. A closed role's sourcing is paused; reopening leaves
    it paused until a person chooses how often to search."""
    from maindscout.api import autosource, relationship

    if state not in STATES:
        raise ValueError(f"state must be one of {STATES}")
    job = _job(session, org_id, job_id)
    if job.state == state:
        return job
    job.state = state
    if state != "open":
        p = autosource.current_plan(session, job.id)
        if p is not None and p.mode != "paused":
            autosource.update_plan(session, org_id, job.id, actor, mode="paused")
    if job.hiring_company_id:  # the client's timeline says what happened to their role
        relationship.log(session, org_id, "company", job.hiring_company_id, "note",
                         f"Role {job.title}: {WORDS[state]}" + (f". {note.strip()}" if (note or "").strip() else ""), actor, job_id=job.id)
    session.flush()
    return job


def found_only_here(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> list[uuid.UUID]:
    """People this role's sourcing found who are on no other role and known only from public profiles (no CV)."""
    found = set(session.scalars(select(SourcingHit.candidate_id).where(SourcingHit.org_id == org_id, SourcingHit.job_id == job_id)))
    if not found:
        return []
    elsewhere = set(session.scalars(select(CandidateJob.candidate_id).where(CandidateJob.candidate_id.in_(found),
                                                                            CandidateJob.job_id != job_id)))
    kinds: dict[uuid.UUID, set[str]] = {}
    for cid, kind in session.execute(select(DocumentSubject.subject_id, Document.doc_type).join(
            Document, Document.id == DocumentSubject.document_id).where(DocumentSubject.subject_id.in_(found))):
        kinds.setdefault(cid, set()).add(kind)
    from maindscout.db.models import PUBLIC_DOC_TYPES

    return sorted((c for c in found - elsewhere if kinds.get(c) and kinds[c] <= PUBLIC_DOC_TYPES), key=str)


def delete_role(session: Session, blobs: BlobStore, org_id: uuid.UUID, job_id: uuid.UUID, actor: str,
                remove_found_people: bool = False) -> dict[str, Any]:
    """Delete a role added by mistake, and everything that belongs to it only."""
    from maindscout.api import erasure

    job = _job(session, org_id, job_id)
    people = found_only_here(session, org_id, job_id) if remove_found_people else []
    claims = select(Claim.id).where(Claim.subject_id == job.id)
    pairs = select(CandidateJob.id).where(CandidateJob.job_id == job.id)
    decisions = select(Decision.id).where(Decision.job_id == job.id)
    doc_id = job.source_document_id
    counts: dict[str, int] = {}

    def run(name: str, statement) -> None:
        counts[name] = session.execute(statement).rowcount or 0

    # Pairs are permanent (a database trigger refuses deletes); deleting a role is, like erasure, the one exception.
    session.execute(text("SET LOCAL maindscout.erasure = 'on'"))
    run("decision_items", delete(DecisionItem).where(or_(DecisionItem.claim_id.in_(claims), DecisionItem.decision_id.in_(decisions))))
    run("decisions", delete(Decision).where(Decision.job_id == job.id))
    run("brief_items", delete(BriefItem).where(or_(BriefItem.job_id == job.id, BriefItem.answer_claim_id.in_(claims))))
    session.execute(update(Claim).where(Claim.superseded_by.in_(claims)).values(superseded_by=None))
    run("observations", delete(ClaimObservation).where(ClaimObservation.claim_id.in_(claims)))
    run("evidence", delete(Evidence).where(or_(Evidence.claim_id.in_(claims), *([Evidence.document_id == doc_id] if doc_id else []))))
    run("requirements", delete(Claim).where(Claim.subject_id == job.id))
    run("pair_history", delete(PairEvent).where(PairEvent.pair_id.in_(pairs)))
    session.execute(update(CandidateJob).where(CandidateJob.merged_into_id.in_(pairs)).values(merged_into_id=None))
    run("pairs", delete(CandidateJob).where(CandidateJob.job_id == job.id))
    run("snapshots", delete(Score).where(Score.job_id == job.id))
    run("sourcing_hits", delete(SourcingHit).where(SourcingHit.job_id == job.id))
    run("sourcing_queries", delete(SourcingQuery).where(SourcingQuery.job_id == job.id))
    run("sourcing_runs", delete(SourcingRun).where(SourcingRun.job_id == job.id))
    run("sourcing_plans", delete(SourcingPlan).where(SourcingPlan.job_id == job.id))
    run("campaigns", delete(Campaign).where(Campaign.job_id == job.id))
    run("intake_notes", delete(JobIntake).where(JobIntake.job_id == job.id))
    run("activities", delete(Activity).where(Activity.job_id == job.id))
    session.execute(update(Message).where(Message.follow_up_of.in_(select(Message.id).where(Message.job_id == job.id))).values(follow_up_of=None))
    run("messages", delete(Message).where(Message.job_id == job.id))
    run("permissions", delete(Permission).where(Permission.job_id == job.id))
    run("signals", delete(CompanySignal).where(CompanySignal.job_id == job.id))
    run("client_blocks", delete(ClientBlock).where(ClientBlock.job_id == job.id))
    run("call_reviews", delete(CallReview).where(or_(CallReview.job_id == job.id, *([CallReview.document_id == doc_id] if doc_id else []))))
    run("tasks", delete(Task).where(Task.payload["job_id"].astext == str(job.id)))
    job.source_document_id = None
    session.flush()
    session.delete(job)
    session.flush()
    if doc_id is not None and not session.scalar(select(func.count()).select_from(Job).where(Job.source_document_id == doc_id)):
        doc = session.get(Document, doc_id)
        key = doc.storage_key if doc is not None else None
        run("ad_links", delete(DocumentSubject).where(DocumentSubject.document_id == doc_id))
        run("ad_text", delete(ExtractionArtifact).where(ExtractionArtifact.document_id == doc_id))
        run("ad_runs", delete(IntelligenceRun).where(IntelligenceRun.document_id == doc_id))
        run("ad", delete(Document).where(Document.id == doc_id))
        if key and not session.scalar(select(func.count()).select_from(Document).where(Document.storage_key == key)):
            blobs.delete(key)  # the same PDF uploaded again is read fresh
    removed = 0
    for cid in people:
        record = erasure.erase_candidate(session, blobs, org_id, cid, actor, "removed: found only by a role that was deleted",
                                         suppress=False)
        removed += not record.survivors
    counts["people_removed"] = removed
    session.flush()
    return counts
