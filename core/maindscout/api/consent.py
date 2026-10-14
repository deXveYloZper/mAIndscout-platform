"""What a person said yes to, and "stop" (docs/next/PLAN.md S4).

People found by sourcing are public data only, a guide to contact them. When they answer, their permission is
recorded as they give it: put forward for this role, and/or for other roles. "Stop" is permanent until a person on
the desk lifts it with a reason: they are never suggested or drafted to again, and open follow-ups are cancelled.
Nothing more (owner, 2026-10-12: "do not over engineer this GDPR").
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.db.models import Candidate, Job, Message, Permission

HOW = ("message", "call", "email", "other")


class ConsentError(ValueError):
    pass


def _person(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID) -> Candidate:
    person = session.get(Candidate, candidate_id)
    if person is None or person.org_id != org_id:
        raise LookupError(f"No candidate {candidate_id}")
    return person


def record(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, actor: str, *, this_role: bool, other_roles: bool,
           job_id: uuid.UUID | None = None, how: str | None = None, note: str | None = None) -> list[Permission]:
    from maindscout.api import relationship

    person = _person(session, org_id, candidate_id)
    if not this_role and not other_roles:
        raise ConsentError("Choose what they said yes to: this role, other roles, or both")
    if this_role:
        job = session.get(Job, job_id) if job_id else None
        if job is None or job.org_id != org_id:
            raise ConsentError("Permission for a role needs the role")
    if how is not None and how not in HOW:
        raise ConsentError(f"how must be one of {HOW}")
    if person.do_not_contact_at is not None:
        raise ConsentError("They asked not to be contacted: lift that first if they have changed their mind")
    rows = []
    for scope, wanted in (("this_role", this_role), ("other_roles", other_roles)):
        if wanted:
            row = Permission(org_id=org_id, candidate_id=candidate_id, job_id=job_id if scope == "this_role" else None,
                             scope=scope, how=how, note=(note or "").strip()[:2000] or None, recorded_by=actor)
            session.add(row)
            rows.append(row)
    words = " and ".join(w for w, on in (("this role", this_role), ("other roles", other_roles)) if on)
    relationship.log(session, org_id, "candidate", candidate_id, "note", f"Said yes to being put forward for {words}", actor,
                     job_id=job_id if this_role else None)
    session.flush()
    return rows


def of(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID) -> list[dict[str, Any]]:
    titles = dict(session.execute(select(Job.id, Job.title).where(Job.org_id == org_id)).all())
    return [{"id": str(p.id), "scope": p.scope, "job_id": str(p.job_id) if p.job_id else None,
             "job": titles.get(p.job_id) if p.job_id else None, "how": p.how, "note": p.note, "by": p.recorded_by,
             "at": p.created_at.isoformat() if p.created_at else None}
            for p in session.scalars(select(Permission).where(Permission.org_id == org_id, Permission.candidate_id == candidate_id)
                                     .order_by(Permission.created_at.desc()))]


def may_put_forward(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    return session.scalar(select(Permission.id).where(
        Permission.org_id == org_id, Permission.candidate_id == candidate_id,
        ((Permission.scope == "this_role") & (Permission.job_id == job_id)) | (Permission.scope == "other_roles")).limit(1)) is not None


def stop(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, actor: str, note: str | None = None) -> Candidate:
    """They asked not to be contacted: never suggested or drafted to again; open follow-ups are cancelled."""
    from maindscout.api import mailbox, relationship

    person = _person(session, org_id, candidate_id)
    if person.do_not_contact_at is None:
        person.do_not_contact_at = datetime.now(timezone.utc)
        person.do_not_contact_note = (note or "").strip()[:2000] or None
        for m in session.scalars(select(Message).where(Message.org_id == org_id, Message.candidate_id == candidate_id,
                                                       Message.status.in_(("draft", "in_mailbox")))):
            if m.status == "in_mailbox" and m.provider_draft_id and m.provider != "linkedin":
                mailbox.delete_draft(session, org_id, m.provider_draft_id)
            m.status = "cancelled"
        for m in session.scalars(select(Message).where(Message.org_id == org_id, Message.candidate_id == candidate_id,
                                                       Message.follow_up_due.is_not(None))):
            m.follow_up_due = None
        relationship.log(session, org_id, "candidate", candidate_id, "note",
                         "Asked not to be contacted" + (f": {person.do_not_contact_note}" if person.do_not_contact_note else ""), actor)
    session.flush()
    return person


def lift_stop(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, actor: str, note: str) -> Candidate:
    from maindscout.api import relationship

    person = _person(session, org_id, candidate_id)
    if not (note or "").strip():
        raise ConsentError("Say why they may be contacted again (for example: they got back in touch)")
    if person.do_not_contact_at is not None:
        person.do_not_contact_at, person.do_not_contact_note = None, None
        relationship.log(session, org_id, "candidate", candidate_id, "note", f"May be contacted again: {note.strip()}", actor)
    session.flush()
    return person
