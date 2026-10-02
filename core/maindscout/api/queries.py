"""Read models for the cockpit. Reads only; no writes here."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.db.models import (
    Candidate,
    CandidateJob,
    Claim,
    Decision,
    DecisionItem,
    Document,
    Evidence,
    Job,
)

LIVE = ("proposed", "approved")
BANDS = ("priority", "review_later", "do_not_submit")
BLOCKING = ("identity_note", "ocr_contact")


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def names(session: Session, candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    """Approved name if there is one, else the first proposed name."""
    out: dict[uuid.UUID, str | None] = {cid: None for cid in candidate_ids}
    if not candidate_ids:
        return out
    rows = session.scalars(select(Claim).where(
        Claim.claim_type == "IdentityClaim", Claim.subject_id.in_(candidate_ids), Claim.status.in_(LIVE)
    ).order_by(Claim.created_at))
    for claim in rows:
        current = out.get(claim.subject_id)
        if current is None or claim.status == "approved":
            out[claim.subject_id] = (claim.approved_view or claim.payload)["full_name"]
    return out


def evidence_for(session: Session, claim_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    out: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    if not claim_ids:
        return out
    rows = session.execute(
        select(Evidence, Document.filename).outerjoin(Document, Document.id == Evidence.document_id)
        .where(Evidence.claim_id.in_(claim_ids)).order_by(Evidence.created_at))
    for ev, filename in rows:
        out[ev.claim_id].append({
            "type": ev.evidence_type, "document_id": str(ev.document_id) if ev.document_id else None,
            "filename": filename, "page": (ev.locator or {}).get("page"), "snippet": ev.snippet,
            "origin": ev.origin, "source_authority": ev.source_authority, "observed_as_of": _iso(ev.observed_as_of),
            "note": (ev.span_validation or {}).get("detail"),
        })
    return out


def claim_view(claim: Claim, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(claim.id), "claim_type": claim.claim_type, "status": claim.status, "payload": claim.payload,
        "approved_view": claim.approved_view, "flags": claim.flags, "valid_from": _iso(claim.valid_from),
        "valid_to": _iso(claim.valid_to), "temporal_precision": claim.temporal_precision, "evidence": evidence,
    }


def list_jobs(session: Session, org_id: uuid.UUID) -> list[dict[str, Any]]:
    counts: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: {b: 0 for b in BANDS})
    for job_id, band, n in session.execute(
            select(CandidateJob.job_id, CandidateJob.triage_band, func.count()).where(CandidateJob.org_id == org_id)
            .group_by(CandidateJob.job_id, CandidateJob.triage_band)):
        if band in BANDS:
            counts[job_id][band] = n
    jobs = session.scalars(select(Job).where(Job.org_id == org_id).order_by(Job.created_at.desc()))
    return [{"id": str(j.id), "title": j.title, "hiring_company": j.hiring_company, "state": j.state,
             "created_at": _iso(j.created_at), "bands": counts[j.id]} for j in jobs]


def job_page(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    reqs = list(session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                    Claim.status.in_(LIVE)).order_by(Claim.created_at)))
    ev = evidence_for(session, [c.id for c in reqs])
    pairs = list(session.scalars(select(CandidateJob).where(CandidateJob.job_id == job.id).order_by(CandidateJob.created_at)))
    who = names(session, [p.candidate_id for p in pairs])
    open_counts = dict(session.execute(
        select(Decision.subject_id, func.count()).where(Decision.org_id == org_id, Decision.sealed_at.is_(None))
        .group_by(Decision.subject_id)).all())
    people: dict[str, list[dict[str, Any]]] = {b: [] for b in BANDS}
    for p in pairs:
        people.setdefault(p.triage_band, []).append({
            "candidate_id": str(p.candidate_id), "name": who.get(p.candidate_id), "band": p.triage_band,
            "reason": p.triage_reason, "overridden_by": p.band_overridden_by, "open_decisions": open_counts.get(p.candidate_id, 0),
        })
    return {
        "id": str(job.id), "title": job.title, "hiring_company": job.hiring_company, "state": job.state,
        "source_document_id": str(job.source_document_id) if job.source_document_id else None,
        "requirements": [claim_view(c, ev[c.id]) for c in reqs],
        "process_stale": any(c.flags.get("job_process_stale") for c in reqs),
        "people": people,
    }


def person_page(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID) -> dict[str, Any]:
    person = session.get(Candidate, candidate_id)
    if person is None or person.org_id != org_id:
        raise LookupError(f"No candidate {candidate_id}")
    claims = list(session.scalars(select(Claim).where(Claim.subject_id == person.id).order_by(Claim.valid_from.desc().nulls_last(), Claim.created_at)))
    ev = evidence_for(session, [c.id for c in claims])
    pairs = session.execute(select(CandidateJob, Job).join(Job, Job.id == CandidateJob.job_id).where(CandidateJob.candidate_id == person.id))
    documents = session.execute(
        select(Document).join(Evidence, Evidence.document_id == Document.id).join(Claim, Claim.id == Evidence.claim_id)
        .where(Claim.subject_id == person.id).distinct())
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in claims:
        grouped[c.claim_type].append(claim_view(c, ev[c.id]))
    return {
        "id": str(person.id), "name": names(session, [person.id])[person.id],
        "merged_into_id": str(person.merged_into_id) if person.merged_into_id else None,
        "claims": grouped,
        "jobs": [{"job_id": str(j.id), "title": j.title, "band": p.triage_band, "reason": p.triage_reason} for p, j in pairs],
        "documents": [{"id": str(d.id), "filename": d.filename, "needs_vision": d.needs_vision, "as_of": _iso(d.as_of)}
                      for (d,) in documents],
        "open_decisions": [str(d) for d in session.scalars(select(Decision.id).where(
            Decision.subject_id == person.id, Decision.sealed_at.is_(None)))],
    }


def _side(claim: Claim, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    first = evidence[0] if evidence else {}
    return {"claim_id": str(claim.id), "claim_type": claim.claim_type, "status": claim.status, "payload": claim.payload,
            "snippet": first.get("snippet"), "page": first.get("page"), "filename": first.get("filename")}


def inbox(session: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None, band: str | None = "priority") -> list[dict[str, Any]]:
    """Only the questions the system may not answer itself.

    Scope: people on the given job in the given band (default priority); without a job, everyone.
    Order: blocking items (identity notes, suspect contacts) first, then oldest first. Never by score.
    """
    if job_id:
        q = select(CandidateJob.candidate_id).where(CandidateJob.job_id == job_id, CandidateJob.org_id == org_id)
        if band and band != "all":
            q = q.where(CandidateJob.triage_band == band)
        scope = list(session.scalars(q))
    else:
        scope = list(session.scalars(select(Candidate.id).where(Candidate.org_id == org_id)))
    if not scope:
        return []
    who = names(session, scope)
    items: list[dict[str, Any]] = []

    decisions = list(session.scalars(select(Decision).where(
        Decision.org_id == org_id, Decision.sealed_at.is_(None), Decision.subject_id.in_(scope))))
    links = defaultdict(list)
    for item in session.scalars(select(DecisionItem).where(DecisionItem.decision_id.in_([d.id for d in decisions] or [None]))):
        links[item.decision_id].append(item)
    claim_ids = [i.claim_id for its in links.values() for i in its]
    claims = {c.id: c for c in session.scalars(select(Claim).where(Claim.id.in_(claim_ids or [None])))}
    ev = evidence_for(session, list(claims))
    for d in decisions:
        sides = [_side(claims[i.claim_id], ev[i.claim_id]) for i in links[d.id]]
        entry = {"id": str(d.id), "kind": d.type, "blocking": d.type in BLOCKING, "created_at": _iso(d.created_at),
                 "subject": {"id": str(d.subject_id), "name": who.get(d.subject_id)}, "context": d.context}
        if d.type == "revision_diff":
            old, new = d.context.get("old_view", {}), d.context.get("new_view", {})
            entry.update(claim_id=sides[0]["claim_id"], old_view=old, new_view=new,
                         changed_paths=sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k)))
        elif d.type in ("duplicate_stint", "contradiction") and len(sides) == 2:
            entry.update(left=sides[0], right=sides[1])
        items.append(entry)

    suspect = session.scalars(select(Claim).where(
        Claim.org_id == org_id, Claim.claim_type == "ContactClaim", Claim.status == "proposed",
        Claim.subject_id.in_(scope), Claim.flags["possible_ocr_identifier"].astext == "true"))
    for c in suspect:
        e = ev.get(c.id) or evidence_for(session, [c.id])[c.id]
        items.append({"id": f"contact:{c.id}", "kind": "ocr_contact", "blocking": True, "created_at": _iso(c.created_at),
                      "subject": {"id": str(c.subject_id), "name": who.get(c.subject_id)}, "claim": _side(c, e),
                      "note": (e[0] if e else {}).get("note")})

    items.sort(key=lambda i: (not i["blocking"], i["created_at"] or ""))
    return items
