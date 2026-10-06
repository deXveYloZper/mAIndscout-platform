"""Reads for the desk's navigation (design plan, 2026-10-06): the sidebar's counts, the ⌘K lookup, the Today page.

All read-only and cheap: a few aggregate queries, never a per-person loop.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session

from maindscout.db.models import (Activity, Candidate, CandidateJob, Claim, Decision, Job, PairEvent)

LIVE = ("proposed", "approved")


def _scope(org_id):
    """People the inbox asks about: everyone on the desk who is not archived."""
    return select(Candidate.id).where(Candidate.org_id == org_id, Candidate.archived_at.is_(None))


def inbox_count(session: Session, org_id: uuid.UUID) -> int:
    """How many cards the all-jobs inbox shows (queries.inbox with no job), counted without building them."""
    decisions = session.scalar(select(func.count()).select_from(Decision).where(
        Decision.org_id == org_id, Decision.sealed_at.is_(None),
        or_(Decision.subject_id.in_(_scope(org_id)),
            (Decision.type == "company_same")
            & Decision.context["candidate_id"].astext.in_(select(func.cast(Candidate.id, String)).where(
                Candidate.org_id == org_id, Candidate.archived_at.is_(None))))))
    contacts = session.scalar(select(func.count()).select_from(Claim).where(
        Claim.org_id == org_id, Claim.claim_type == "ContactClaim", Claim.status == "proposed",
        Claim.subject_id.in_(_scope(org_id)), Claim.flags["possible_ocr_identifier"].astext == "true"))
    return (decisions or 0) + (contacts or 0)


def nav_counts(session: Session, org_id: uuid.UUID) -> dict[str, int]:
    """The inbox badge: its cards plus call reviews waiting for a person."""
    from maindscout.db.models import CallReview

    calls = session.scalar(select(func.count()).select_from(CallReview).where(
        CallReview.org_id == org_id, CallReview.status.in_(("pending", "failed")))) or 0
    return {"inbox": inbox_count(session, org_id) + calls}


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def lookup(session: Session, org_id: uuid.UUID, q: str, limit: int = 6) -> dict[str, list[dict[str, Any]]]:
    """Names that contain `q`: people, jobs and companies of this desk, best known first. For ⌘K."""
    from maindscout.api import companies

    q = " ".join((q or "").split())[:80]
    if len(q) < 2:
        return {"people": [], "jobs": [], "companies": []}
    pattern = _like(q)
    name = func.coalesce(Claim.approved_view["full_name"].astext, Claim.payload["full_name"].astext)
    rows = session.execute(
        select(Claim.subject_id, name).join(Candidate, Candidate.id == Claim.subject_id)
        .where(Claim.org_id == org_id, Claim.claim_type == "IdentityClaim", Claim.status.in_(LIVE),
               Candidate.merged_into_id.is_(None), name.ilike(pattern, escape="\\"))
        .order_by(func.length(name)).limit(limit * 3)).all()
    people, seen = [], set()
    for cid, full in rows:
        if cid not in seen:
            seen.add(cid)
            people.append({"id": str(cid), "name": full})
    people = people[:limit]
    jobs_on = dict(session.execute(select(CandidateJob.candidate_id, func.count()).where(
        CandidateJob.candidate_id.in_([uuid.UUID(p["id"]) for p in people] or [None])).group_by(CandidateJob.candidate_id)).all())
    for p in people:
        n = jobs_on.get(uuid.UUID(p["id"]), 0)
        p["meta"] = f"on {n} job{'s' if n != 1 else ''}" if n else "in the pool"
    jobs = [{"id": str(j.id), "name": j.title, "meta": j.hiring_company or ""} for j in session.scalars(
        select(Job).where(Job.org_id == org_id, Job.title.ilike(pattern, escape="\\")).order_by(Job.created_at.desc()).limit(limit))]
    found = [{"id": c["id"], "name": c["name"], "meta": f"{c['people_count']} known"} for c in companies.search(session, org_id, q, limit)]
    return {"people": people, "jobs": jobs, "companies": found}


def today(session: Session, org_id: uuid.UUID) -> dict[str, Any]:
    """The recruiter's start of day: who's waiting per job, decisions to make, who's going stale, what just happened."""
    from maindscout.api import freshness, queries

    jobs = queries.list_jobs(session, org_id)
    live = [j for j in jobs if j["state"] not in ("closed", "filled", "cancelled")]
    status = freshness.people_status(session, org_id)
    archived = set(session.scalars(select(Candidate.id).where(Candidate.org_id == org_id, Candidate.archived_at.is_not(None))))
    stale = sum(1 for cid, s in status.items() if s["status"] == "stale" and cid not in archived)
    pool = session.scalar(select(func.count()).select_from(Candidate).where(
        Candidate.org_id == org_id, Candidate.archived_at.is_(None), Candidate.merged_into_id.is_(None),
        ~Candidate.id.in_(select(CandidateJob.candidate_id)))) or 0

    recent: list[dict[str, Any]] = []
    events = session.execute(
        select(PairEvent, CandidateJob.candidate_id, CandidateJob.job_id).join(CandidateJob, CandidateJob.id == PairEvent.pair_id)
        .where(PairEvent.org_id == org_id).order_by(PairEvent.seq.desc()).limit(12)).all()
    acts = list(session.scalars(select(Activity).where(Activity.org_id == org_id, Activity.subject_type == "candidate")
                                .order_by(Activity.created_at.desc()).limit(12)))
    who = queries.names(session, list({e[1] for e in events} | {a.subject_id for a in acts}))
    titles = {uuid.UUID(j["id"]): j["title"] for j in jobs}
    for ev, cid, jid in events:
        recent.append({"at": ev.created_at.isoformat(), "kind": ev.kind, "person": who.get(cid), "person_id": str(cid),
                       "job": titles.get(jid), "job_id": str(jid), "to": ev.to_value, "by": ev.actor})
    for a in acts:
        recent.append({"at": a.created_at.isoformat(), "kind": a.kind, "person": who.get(a.subject_id), "person_id": str(a.subject_id),
                       "text": a.summary[:140], "by": a.created_by})
    recent.sort(key=lambda r: r["at"], reverse=True)
    return {
        "inbox": inbox_count(session, org_id),
        "priority": sum(j["bands"].get("priority", 0) for j in live),
        "stale": stale,
        "pool": pool,
        "jobs": [{"id": j["id"], "title": j["title"], "company": j["hiring_company"], "priority": j["bands"].get("priority", 0),
                  "review_later": j["bands"].get("review_later", 0), "to_review": j["to_review"]} for j in live],
        "recent": recent[:12],
    }
