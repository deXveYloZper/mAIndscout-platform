"""Relationship memory (Slice 4, step 1): what happened with each person and client, when we last spoke, when their
facts were last confirmed, tags as talent pools, and the people we know at client companies.

The timeline joins what the recruiter logs (calls, emails, meetings, messages, notes) with what the platform already
records (CVs read, band and stage changes, Brief answers), so nothing is entered twice.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.db.models import (ACTIVITY_KINDS, Activity, BriefItem, Candidate, CandidateJob, CandidateTag, Claim,
                                  ClientContact, Company, Document, DocumentSubject, Job, PairEvent)

CONTACT_KINDS = ("call", "email", "meeting", "message")


class RelationshipError(ValueError):
    pass


def _iso(d) -> str | None:
    return d.isoformat() if d else None


def _subject(session: Session, org_id, subject_type: str, subject_id: uuid.UUID):
    if subject_type == "candidate":
        person = session.get(Candidate, subject_id)
        if person is None or person.org_id != org_id:
            raise LookupError(f"No candidate {subject_id}")
        return person
    if subject_type == "company":
        company = session.get(Company, subject_id)
        if company is None:
            raise LookupError(f"No company {subject_id}")
        return company
    raise RelationshipError("subject_type must be candidate or company")


def log(session: Session, org_id, subject_type: str, subject_id: uuid.UUID, kind: str, summary: str, actor: str, *,
        direction: str | None = None, occurred_at: datetime | None = None, job_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None) -> Activity:
    _subject(session, org_id, subject_type, subject_id)
    if kind not in ACTIVITY_KINDS:
        raise RelationshipError(f"kind must be one of {ACTIVITY_KINDS}")
    summary = (summary or "").strip()
    if not summary:
        raise RelationshipError("Write what happened, in a line")
    if direction not in (None, "out", "in"):
        raise RelationshipError("direction must be out or in")
    if job_id is not None:
        job = session.get(Job, job_id)
        if job is None or job.org_id != org_id:
            raise LookupError(f"No job {job_id}")
    if contact_id is not None:
        contact = session.get(ClientContact, contact_id)
        if contact is None or contact.org_id != org_id or (subject_type == "company" and contact.company_id != subject_id):
            raise LookupError(f"No contact {contact_id} at this company")
    when = occurred_at or datetime.now(timezone.utc)
    if when > datetime.now(timezone.utc):
        raise RelationshipError("That is in the future")
    a = Activity(org_id=org_id, subject_type=subject_type, subject_id=subject_id, kind=kind, direction=direction,
                 summary=summary[:4000], job_id=job_id, contact_id=contact_id, occurred_at=when, created_by=actor)
    session.add(a)
    session.flush()
    return a


def remove_activity(session: Session, org_id, activity_id: uuid.UUID) -> None:
    a = session.get(Activity, activity_id)
    if a is None or a.org_id != org_id:
        raise LookupError(f"No activity {activity_id}")
    session.delete(a)
    session.flush()


# --- dates ----------------------------------------------------------------------------------------


def last_contacted(session: Session, org_id, subject_type: str, subject_id) -> datetime | None:
    logged = session.scalar(select(func.max(Activity.occurred_at)).where(
        Activity.org_id == org_id, Activity.subject_type == subject_type, Activity.subject_id == subject_id,
        Activity.kind.in_(CONTACT_KINDS)))
    if subject_type != "candidate":
        return logged
    answered = session.scalar(select(func.max(BriefItem.updated_at)).where(
        BriefItem.org_id == org_id, BriefItem.candidate_id == subject_id, BriefItem.status == "answered"))
    return max([d for d in (logged, answered) if d], default=None)


def last_verified(session: Session, org_id, candidate_id) -> datetime | None:
    """When a person last confirmed or refreshed their facts: a fact approved or typed by a person, a Brief answer, or
    a CV read."""
    approved = session.scalar(select(func.max(Claim.approved_at)).where(
        Claim.org_id == org_id, Claim.subject_id == candidate_id, Claim.status == "approved"))
    cv = session.scalar(select(func.max(Document.created_at)).join(DocumentSubject, DocumentSubject.document_id == Document.id)
                        .where(DocumentSubject.org_id == org_id, DocumentSubject.subject_id == candidate_id))
    return max([d for d in (approved, cv) if d], default=None)


# --- timeline -------------------------------------------------------------------------------------


def _activity_row(a: Activity, contacts: dict, jobs: dict) -> dict[str, Any]:
    c = contacts.get(a.contact_id)
    return {"at": _iso(a.occurred_at), "type": a.kind, "direction": a.direction, "text": a.summary,
            "job": jobs.get(a.job_id), "contact": c.name if c else None, "by": a.created_by, "id": str(a.id), "removable": True}


def timeline(session: Session, org_id, subject_type: str, subject_id, limit: int = 200) -> list[dict[str, Any]]:
    acts = list(session.scalars(select(Activity).where(Activity.org_id == org_id, Activity.subject_type == subject_type,
                                                       Activity.subject_id == subject_id)))
    contacts = {c.id: c for c in session.scalars(select(ClientContact).where(
        ClientContact.id.in_([a.contact_id for a in acts if a.contact_id] or [None])))}
    jobs = {j.id: j.title for j in session.scalars(select(Job).where(Job.org_id == org_id))}
    rows = [_activity_row(a, contacts, jobs) for a in acts]
    if subject_type == "candidate":
        for d in session.scalars(select(Document).join(DocumentSubject, DocumentSubject.document_id == Document.id)
                                 .where(DocumentSubject.org_id == org_id, DocumentSubject.subject_id == subject_id)):
            rows.append({"at": _iso(d.created_at), "type": "cv", "text": f"CV read: {d.filename or 'document'}", "by": "system"})
        for e, job_id in session.execute(select(PairEvent, CandidateJob.job_id).join(CandidateJob, CandidateJob.id == PairEvent.pair_id)
                                         .where(CandidateJob.org_id == org_id, CandidateJob.candidate_id == subject_id)):
            what = "band" if e.kind == "band" else "stage"
            change = f"{e.from_value} → {e.to_value}" if e.from_value and e.from_value != "unassigned" else e.to_value
            rows.append({"at": _iso(e.created_at), "type": e.kind, "text": f"{what} {change.replace('_', ' ')}",
                         "job": jobs.get(job_id), "by": e.actor})
        for b in session.scalars(select(BriefItem).where(BriefItem.org_id == org_id, BriefItem.candidate_id == subject_id,
                                                         BriefItem.status == "answered")):
            said = f": {b.answer}" if b.answer else ""
            rows.append({"at": _iso(b.updated_at), "type": "brief", "text": f"{b.question} {b.outcome.replace('_', ' ')}{said}",
                         "job": jobs.get(b.job_id), "by": b.answered_by})
    else:
        for j in session.scalars(select(Job).where(Job.org_id == org_id, Job.hiring_company_id == subject_id)):
            rows.append({"at": _iso(j.created_at), "type": "job", "text": f"Job opened: {j.title}", "job": j.title, "by": "system"})
    rows.sort(key=lambda r: r["at"] or "", reverse=True)
    return rows[:limit]


# --- tags (talent pools) ------------------------------------------------------------------------------


def _norm_tag(tag: str) -> str:
    tag = re.sub(r"[^a-z0-9+#\- ]", "", (tag or "").strip().lower()).replace(" ", "-")
    if not tag or len(tag) > 40:
        raise RelationshipError("A tag is a short word or two, e.g. insar-pool")
    return tag


def add_tag(session: Session, org_id, candidate_id: uuid.UUID, tag: str, actor: str) -> str:
    _subject(session, org_id, "candidate", candidate_id)
    tag = _norm_tag(tag)
    if session.scalar(select(CandidateTag.id).where(CandidateTag.candidate_id == candidate_id, CandidateTag.tag == tag)) is None:
        session.add(CandidateTag(org_id=org_id, candidate_id=candidate_id, tag=tag, created_by=actor))
        session.flush()
    return tag


def remove_tag(session: Session, org_id, candidate_id: uuid.UUID, tag: str) -> None:
    row = session.scalar(select(CandidateTag).where(CandidateTag.org_id == org_id, CandidateTag.candidate_id == candidate_id,
                                                    CandidateTag.tag == tag))
    if row is not None:
        session.delete(row)
        session.flush()


def tags_of(session: Session, candidate_id) -> list[str]:
    return sorted(session.scalars(select(CandidateTag.tag).where(CandidateTag.candidate_id == candidate_id)))


def pools(session: Session, org_id) -> list[dict[str, Any]]:
    return [{"tag": t, "people": n} for t, n in session.execute(
        select(CandidateTag.tag, func.count()).where(CandidateTag.org_id == org_id).group_by(CandidateTag.tag).order_by(CandidateTag.tag))]


# --- contacts at client companies -----------------------------------------------------------------------


def add_contact(session: Session, org_id, company_id: uuid.UUID, fields: dict[str, Any], actor: str) -> ClientContact:
    _subject(session, org_id, "company", company_id)
    name = (fields.get("name") or "").strip()
    if not name:
        raise RelationshipError("A contact needs a name")
    c = ClientContact(org_id=org_id, company_id=company_id, name=name[:200], created_by=actor,
                      **{k: (fields.get(k) or "").strip()[:500] or None for k in ("role", "email", "phone", "linkedin", "notes")})
    session.add(c)
    session.flush()
    return c


def remove_contact(session: Session, org_id, contact_id: uuid.UUID) -> None:
    """Forget a contact (their details go; activities about the company stay, without the link)."""
    c = session.get(ClientContact, contact_id)
    if c is None or c.org_id != org_id:
        raise LookupError(f"No contact {contact_id}")
    session.delete(c)
    session.flush()


def contacts_at(session: Session, org_id, company_ids: list) -> list[dict[str, Any]]:
    rows = session.scalars(select(ClientContact).where(ClientContact.org_id == org_id, ClientContact.company_id.in_(company_ids))
                           .order_by(ClientContact.name))
    out = []
    for c in rows:
        last = session.scalar(select(func.max(Activity.occurred_at)).where(Activity.contact_id == c.id, Activity.kind.in_(CONTACT_KINDS)))
        out.append({"id": str(c.id), "name": c.name, "role": c.role, "email": c.email, "phone": c.phone, "linkedin": c.linkedin,
                    "notes": c.notes, "last_contacted": _iso(last)})
    return out


def summary_for_person(session: Session, org_id, candidate_id) -> dict[str, Any]:
    return {"last_contacted": _iso(last_contacted(session, org_id, "candidate", candidate_id)),
            "last_verified": _iso(last_verified(session, org_id, candidate_id)),
            "tags": tags_of(session, candidate_id), "timeline": timeline(session, org_id, "candidate", candidate_id)}
