"""Messages (Slice 4, step 5): draft from outward-safe facts, edit, put in the recruiter's own mailbox, notice when it
is sent and when someone replies. Nothing is ever sent automatically. Any reply stops the follow-ups.

Flow: draft -> in_mailbox (in Gmail / Outlook drafts) -> sent (the recruiter pressed send) -> replied.
Follow-ups are drafted when due and nobody replied; a reply cancels any follow-up still waiting.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs, relationship
from maindscout.db.models import BriefItem, Candidate, Claim, ClientContact, Job, Message
from maindscout.intelligence import drafts
from maindscout.settings import env

FOLLOW_UP_KINDS = ("candidate_outreach", "client_submission")
OPEN = ("draft", "in_mailbox")


class MessageError(ValueError):
    pass


def follow_up_days() -> int:
    try:
        return max(1, int(env("FOLLOW_UP_DAYS", "4") or 4))
    except ValueError:
        return 4


# --- what may be said outward ------------------------------------------------------------------------------


def _approved(session: Session, org_id, candidate_id, claim_type: str) -> list[Claim]:
    return list(session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                    Claim.claim_type == claim_type, Claim.status == "approved")))


def _name(session: Session, org_id, candidate_id) -> str | None:
    from maindscout.api.queries import names

    return names(session, [candidate_id]).get(candidate_id)


def _email(session: Session, org_id, candidate_id) -> str | None:
    rows = list(session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                    Claim.claim_type == "ContactClaim", Claim.status.in_(("approved", "proposed")),
                                                    Claim.payload["kind"].astext == "email")))
    rows.sort(key=lambda c: c.status != "approved")
    return (rows[0].approved_view or rows[0].payload)["value"] if rows else None


def _facts(session: Session, org_id, candidate_id) -> list[str]:
    """Approved facts only: current role, recent roles, skills. Never anything the desk has not approved."""
    out = []
    steps = sorted(_approved(session, org_id, candidate_id, "CareerStepClaim"), key=lambda c: (c.valid_to is not None, c.valid_from or datetime.min.date()), reverse=False)
    for c in steps[:2]:
        p = c.approved_view or c.payload
        since = f" (since {c.valid_from.year})" if c.valid_from and c.valid_to is None else ""
        out.append(f"{p['title_raw']} at {p['company']['raw_name']}{since}")
    skills = [(c.approved_view or c.payload)["raw_label"] for c in _approved(session, org_id, candidate_id, "SkillClaim")][:4]
    if skills:
        out.append("skills: " + ", ".join(skills))
    return out


def _job(session: Session, job: Job | None) -> dict[str, Any]:
    if job is None:
        return {}
    musts = [c.payload["text_raw"] for c in session.scalars(select(Claim).where(
        Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim", Claim.status.in_(("proposed", "approved"))))
        if c.payload.get("strength") in ("must", "deal_breaker") and c.payload.get("category") == "skill"
        and (c.payload.get("source") or "ad") == "ad"][:3]  # the ad's own words: public; the intake is not
    return {"title": job.title, "company": job.hiring_company, "key requirements": ", ".join(musts) or None}


def _call_answers(session: Session, candidate_id, job_id) -> list[str]:
    """What the candidate said on the call that may go to a client: requirement answers and notice period. Salary,
    career explanations and anything about other roles stay internal."""
    out = []
    for b in session.scalars(select(BriefItem).where(BriefItem.candidate_id == candidate_id, BriefItem.status == "answered",
                                                     BriefItem.outcome.in_(("confirmed", "noted")))):
        if b.job_id not in (None, job_id):
            continue
        if b.source_key == "std:notice" and b.answer:
            out.append(f"availability: {b.answer}")
        elif b.source_key.startswith("req:") and b.outcome == "confirmed":
            text = b.question.removeprefix("Ask about: ").removeprefix("Check: ").split(". Do they have it?")[0].rstrip(".")
            out.append(f"confirmed: {text}" + (f" ({b.answer})" if b.answer else ""))
    return out


def projection(session: Session, org_id, kind: str, *, candidate_id=None, contact: ClientContact | None = None,
               job: Job | None = None, thread: list[Message] | None = None, note: str | None = None) -> drafts.Projection:
    recruiter = env("RECRUITER_NAME", "") or None
    if kind == "client_submission":
        first = (contact.name.split()[0] if contact and contact.name else None)
        facts = _facts(session, org_id, candidate_id)
        who = _name(session, org_id, candidate_id)
        if who:
            facts = [f"name: {who}"] + facts
        return drafts.Projection(kind, first, recruiter, _job(session, job), facts, _call_answers(session, candidate_id, job.id if job else None),
                                 [{"subject": m.subject, "body": m.body} for m in thread or []], note)
    if contact is not None:  # a follow-up to a client contact: greet the contact, say nothing new about the candidate
        first = contact.name.split()[0] if contact.name else None
        return drafts.Projection(kind, first, recruiter, _job(session, job), [], [],
                                 [{"subject": m.subject, "body": m.body} for m in thread or []], note)
    name = _name(session, org_id, candidate_id)
    return drafts.Projection(kind, name.split()[0] if name else None, recruiter, _job(session, job), _facts(session, org_id, candidate_id),
                             [], [{"subject": m.subject, "body": m.body} for m in thread or []], note)


# --- drafting -------------------------------------------------------------------------------------------


def draft(session: Session, org_id, kind: str, actor: str, client, *, candidate_id: uuid.UUID | None = None,
          contact_id: uuid.UUID | None = None, job_id: uuid.UUID | None = None, note: str | None = None) -> Message:
    if kind not in drafts.KINDS or kind == "follow_up":
        raise MessageError("kind must be candidate_outreach, client_submission, interview_confirm or decline")
    job = session.get(Job, job_id) if job_id else None
    if job_id and (job is None or job.org_id != org_id):
        raise LookupError(f"No job {job_id}")
    contact = None
    if kind == "client_submission":
        contact = session.get(ClientContact, contact_id) if contact_id else None
        if contact is None or contact.org_id != org_id:
            raise MessageError("A submission goes to a contact at the client: choose one")
        if not contact.email:
            raise MessageError(f"{contact.name} has no email on file")
        if candidate_id is None or job is None:
            raise MessageError("A submission needs the candidate and the job")
        from maindscout.api.pipeline import active_block

        if active_block(session, org_id, job.id, candidate_id) is not None:
            raise MessageError("The client said no to this person: lift the block first if that has changed")
        to = contact.email
    else:
        person = session.get(Candidate, candidate_id) if candidate_id else None
        if person is None or person.org_id != org_id:
            raise LookupError(f"No candidate {candidate_id}")
        to = _email(session, org_id, candidate_id)
        if not to:
            raise MessageError("No email for this person on file")
    p = projection(session, org_id, kind, candidate_id=candidate_id, contact=contact, job=job, note=note)
    if client is not None:
        costs.ensure_budget(session, org_id)
    out = drafts.write(p, client)
    if out.cost:
        costs.record(session, org_id, "draft_message", out.cost)
    m = Message(org_id=org_id, kind=kind, to_address=to, subject=out.subject, body=out.body, status="draft", created_by=actor,
                candidate_id=None if kind == "client_submission" else candidate_id,
                about_candidate_id=candidate_id if kind == "client_submission" else None,
                contact_id=contact.id if contact else None, company_id=contact.company_id if contact else (job.hiring_company_id if job else None),
                job_id=job.id if job else None)
    session.add(m)
    session.flush()
    return m


def edit(session: Session, org_id, message_id: uuid.UUID, subject: str, body: str) -> Message:
    m = get(session, org_id, message_id)
    if m.status != "draft":
        raise MessageError("Only a draft not yet in the mailbox can be edited here; edit it in your mailbox")
    if not subject.strip() or not body.strip():
        raise MessageError("A message needs a subject and a body")
    if drafts.INTERNAL.search(subject + "\n" + body):
        raise MessageError(f"The message mentions something internal ({drafts.INTERNAL.search(subject + body).group(0)}): take it out")
    m.subject, m.body = subject.strip()[:200], body.strip()[:5000]
    session.flush()
    return m


def get(session: Session, org_id, message_id: uuid.UUID) -> Message:
    m = session.get(Message, message_id)
    if m is None or m.org_id != org_id:
        raise LookupError(f"No message {message_id}")
    return m


def to_mailbox(session: Session, org_id, message_id: uuid.UUID) -> dict[str, Any]:
    """Put the draft in the connected mailbox's drafts. The recruiter sends it from there."""
    from maindscout.api import mailbox

    m = get(session, org_id, message_id)
    if m.status != "draft":
        raise MessageError(f"This message is already {m.status.replace('_', ' ')}")
    box, provider = mailbox.provider_for(session, org_id)
    if provider is None:
        raise MessageError("No mailbox connected: connect Gmail or Outlook first, or copy the text and send it yourself")
    made = provider.create_draft(m.to_address, m.subject, m.body, m.provider_thread_id)
    m.provider, m.provider_draft_id, m.provider_thread_id, m.status = box.provider, made["draft_id"], made.get("thread_id"), "in_mailbox"
    session.flush()
    return {"status": m.status, "open": made.get("web_link")}


# --- sent, replied, follow-ups ----------------------------------------------------------------------------------


def _log(session: Session, m: Message, direction: str, when: datetime, text: str) -> None:
    if m.candidate_id:
        relationship.log(session, m.org_id, "candidate", m.candidate_id, "email", text, "system", direction=direction,
                         occurred_at=min(when, datetime.now(timezone.utc)), job_id=m.job_id)
    if m.company_id and m.contact_id:
        # The client's timeline says what happened without the subject line, which may name the candidate (and would
        # outlive their erasure there).
        neutral = f"{'Sent' if direction == 'out' else 'Reply to'}: {m.kind.replace('_', ' ')}"
        relationship.log(session, m.org_id, "company", m.company_id, "email", neutral, "system", direction=direction,
                         occurred_at=min(when, datetime.now(timezone.utc)), job_id=m.job_id, contact_id=m.contact_id)


def mark_sent(session: Session, org_id, message_id: uuid.UUID, when: datetime | None = None) -> Message:
    m = get(session, org_id, message_id)
    if m.status not in OPEN:
        return m
    when = when or datetime.now(timezone.utc)
    m.status, m.sent_at = "sent", when
    if m.kind in FOLLOW_UP_KINDS:
        m.follow_up_due = when + timedelta(days=follow_up_days())
    _log(session, m, "out", when, f"Sent: {m.subject}")
    session.flush()
    return m


def mark_replied(session: Session, org_id, message_id: uuid.UUID, when: datetime | None = None) -> Message:
    """A reply stops every follow-up in this thread."""
    m = get(session, org_id, message_id)
    if m.status == "replied":
        return m
    root = m if m.follow_up_of is None else session.get(Message, m.follow_up_of)
    thread = [root] + list(session.scalars(select(Message).where(Message.follow_up_of == root.id)))
    when = when or datetime.now(timezone.utc)
    from maindscout.api import mailbox

    for t in thread:
        t.follow_up_due = None
        if t.kind == "follow_up" and t.status in OPEN:
            if t.status == "in_mailbox" and t.provider_draft_id:
                mailbox.delete_draft(session, org_id, t.provider_draft_id)
            t.status = "cancelled"
    m.status, m.replied_at = "replied", when
    if m is not root and root.status == "sent":
        root.status, root.replied_at = "replied", when
    _log(session, m, "in", when, f"Reply to: {m.subject}")
    session.flush()
    return m


def due_follow_ups(session: Session, org_id, client=None, now: datetime | None = None) -> list[Message]:
    """Draft the follow-ups that are due (nobody replied). They go to the mailbox's drafts too, never sent."""
    from maindscout.api import mailbox

    now = now or datetime.now(timezone.utc)
    made = []
    for m in session.scalars(select(Message).where(Message.org_id == org_id, Message.status == "sent",
                                                   Message.follow_up_due.is_not(None), Message.follow_up_due <= now)):
        thread = [m]
        p = projection(session, org_id, "follow_up", candidate_id=m.candidate_id or m.about_candidate_id,
                       contact=session.get(ClientContact, m.contact_id) if m.contact_id else None,
                       job=session.get(Job, m.job_id) if m.job_id else None, thread=thread)
        p.kind = "follow_up"
        out = drafts.write(p, client)
        f = Message(org_id=org_id, kind="follow_up", to_address=m.to_address, subject=out.subject, body=out.body, status="draft",
                    created_by="system", candidate_id=m.candidate_id, about_candidate_id=m.about_candidate_id, contact_id=m.contact_id,
                    company_id=m.company_id, job_id=m.job_id, follow_up_of=m.id, provider_thread_id=m.provider_thread_id)
        session.add(f)
        m.follow_up_due = None
        session.flush()
        box, provider = mailbox.provider_for(session, org_id)
        if provider is not None:
            created = provider.create_draft(f.to_address, f.subject, f.body, f.provider_thread_id)
            f.provider, f.provider_draft_id, f.status = box.provider, created["draft_id"], "in_mailbox"
            f.provider_thread_id = created.get("thread_id") or f.provider_thread_id
        made.append(f)
    session.flush()
    return made


def sync(session: Session, org_id, now: datetime | None = None) -> dict[str, int]:
    """Look at the mailbox: drafts that were sent, replies that came in; then draft the follow-ups that are due."""
    from maindscout.api import mailbox

    box, provider = mailbox.provider_for(session, org_id)
    sent = replied = 0
    if provider is not None:
        for m in session.scalars(select(Message).where(Message.org_id == org_id, Message.status == "in_mailbox",
                                                       Message.provider == box.provider)):
            state = provider.draft_state(m.provider_draft_id, m.provider_thread_id)
            if state.get("state") == "sent":
                m.provider_thread_id = state.get("thread_id") or m.provider_thread_id
                mark_sent(session, org_id, m.id, state.get("at"))
                sent += 1
            elif state.get("state") == "gone":
                m.status = "cancelled"  # deleted from the mailbox without sending
        for m in session.scalars(select(Message).where(Message.org_id == org_id, Message.status == "sent",
                                                       Message.provider == box.provider, Message.provider_thread_id.is_not(None))):
            replies = provider.replies_since(m.provider_thread_id, m.sent_at, box.account)
            if replies:
                mark_replied(session, org_id, m.id, replies[0])
                replied += 1
        box.last_sync_at = datetime.now(timezone.utc)
    follow = due_follow_ups(session, org_id, None, now)
    session.flush()
    return {"sent": sent, "replied": replied, "follow_ups_drafted": len(follow)}


def as_dict(m: Message) -> dict[str, Any]:
    return {"id": str(m.id), "kind": m.kind, "to": m.to_address, "subject": m.subject, "body": m.body, "status": m.status,
            "provider": m.provider, "job_id": str(m.job_id) if m.job_id else None,
            "follow_up_of": str(m.follow_up_of) if m.follow_up_of else None,
            "follow_up_due": m.follow_up_due.isoformat() if m.follow_up_due else None,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None, "replied_at": m.replied_at.isoformat() if m.replied_at else None}


def for_person(session: Session, org_id, candidate_id) -> list[dict[str, Any]]:
    rows = session.scalars(select(Message).where(Message.org_id == org_id,
                                                 (Message.candidate_id == candidate_id) | (Message.about_candidate_id == candidate_id))
                           .order_by(Message.created_at.desc()))
    return [as_dict(m) for m in rows]


def contacts_for_jobs(session: Session, org_id, jobs: list[Job]) -> list[dict[str, Any]]:
    """Who a candidate could be introduced to: contacts with an email at the hiring company of each of their jobs."""
    out = []
    for job in jobs:
        if not job.hiring_company_id:
            continue
        for c in session.scalars(select(ClientContact).where(ClientContact.org_id == org_id, ClientContact.company_id == job.hiring_company_id,
                                                             ClientContact.email.is_not(None)).order_by(ClientContact.name)):
            out.append({"id": str(c.id), "name": c.name, "role": c.role, "job_id": str(job.id), "job": job.title})
    return out
