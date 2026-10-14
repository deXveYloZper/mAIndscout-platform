"""From suggestion to conversation (docs/next/PLAN.md section 4c, phase 1c): the owner's fast workflow on a role's
sourcing suggestions, and the contact track that follows.

- **Suggestions stay suggestions** until the owner decides: a person found by sourcing, with no CV, no call and no
  decision, is not in the role's bands. Viewing a profile marks them seen.
- **Decide in one click**: reach out (Priority, by the owner's hand), maybe later (Review later), or not for this role
  (passed, with a reason that teaches the desk the owner's taste). Every decision can be undone.
- **The contact track** (`candidate_job.contact`): contacted how and when (a LinkedIn invitation or message, InMail,
  email; a follow-up due after 4 days), their LinkedIn acceptance, their reply (interested, not now, not interested,
  stop), the call booked, then the ordinary pipeline (spoken, CV, permission, submitted).
- **A reach**: a head, director, VP, C-level, founder or engineering manager put forward for a role for individual
  contributors ("all levels" means junior to senior, owner 2026-10-13): shown as "possible, a reach", never blocked.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.db.models import Candidate, CandidateJob, Claim, Job, Message, PairEvent, SourcingHit

LIVE = ("proposed", "approved")
WAITING = ("new", "seen")
CHANNELS = {"linkedin_invite": "LinkedIn connection request", "linkedin_message": "LinkedIn message",
            "inmail": "LinkedIn InMail / Recruiter", "email": "email",
            "phone": "phone call", "other": "another way"}
OUTCOMES = ("interested", "not_now", "not_interested", "stop")
PASS = {"level": "seniority", "skills": "skills", "location": "location", "domain": "other", "other": "other"}
MANAGES = re.compile(r"\b(head of|director|vice president|vp\b|chief|cto|cio|ceo|coo|cpo|co-?founder|founder|"
                     r"engineering manager|manager,? engineering|head\b)", re.I)
MANAGEMENT_ROLE = re.compile(r"\b(head|director|vp|vice president|chief|cto|manager|lead)\b", re.I)


class OutreachError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pair(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID) -> CandidateJob:
    pair = session.scalar(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.job_id == job_id,
                                                     CandidateJob.candidate_id == candidate_id))
    if pair is None:
        raise LookupError("This person is not on this role")
    return pair


def _track(pair: CandidateJob, **changes: Any) -> dict[str, Any]:
    pair.contact = {**(pair.contact or {}), **changes}
    return pair.contact


def undecided_pairs(session: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """(job, person) for people found by sourcing whom the owner has not decided on yet: known only from public
    profiles, no band chosen by a person, still new or seen. They are suggestions on the Sourcing tab, not part of the
    role's bands (a public profile alone never makes anyone Priority)."""
    from maindscout.db.models import Document, DocumentSubject

    q = select(CandidateJob.job_id, CandidateJob.candidate_id).join(
        SourcingHit, (SourcingHit.job_id == CandidateJob.job_id) & (SourcingHit.candidate_id == CandidateJob.candidate_id)).join(
        Candidate, Candidate.id == CandidateJob.candidate_id).where(
        Candidate.do_not_contact_at.is_(None),  # someone who said stop is shown on the role as stopped, not hidden
        CandidateJob.org_id == org_id, CandidateJob.pair_state.in_(WAITING), CandidateJob.band_overridden_by.is_(None),
        CandidateJob.triage_band.in_(("priority", "review_later")))  # the ones shown as suggestions; the rest stay in their band
    rows = session.execute(q.where(CandidateJob.job_id == job_id) if job_id else q).all()
    if not rows:
        return set()
    kinds: dict[uuid.UUID, set[str]] = {}
    for cid, kind in session.execute(select(DocumentSubject.subject_id, Document.doc_type).join(
            Document, Document.id == DocumentSubject.document_id).where(DocumentSubject.subject_id.in_({c for _, c in rows}))):
        kinds.setdefault(cid, set()).add(kind)
    return {(j, c) for j, c in rows if kinds.get(c) and kinds[c] <= {"web_profile"}}


def undecided(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> set[uuid.UUID]:
    return {c for _, c in undecided_pairs(session, org_id, job_id)}


# --- a reach ---------------------------------------------------------------------------------------------------------


def reach(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, job: Job) -> str | None:
    """Why this person is a reach for the role, or None: someone who leads a team now, for a role for individual
    contributors. The role's own title decides whether it is one ("Head of Engineering" is its own job spec)."""
    if MANAGEMENT_ROLE.search(job.title or ""):
        return None
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                 Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
                                                 Claim.valid_to.is_(None))):
        title = (c.approved_view or c.payload).get("title_raw") or ""
        if MANAGES.search(title):
            return f"{title} now: above this role. Ask whether they would go back to hands-on work."
    return None


# --- the owner's decisions -------------------------------------------------------------------------------------------


def viewed(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, actor: str) -> CandidateJob:
    """They opened the profile: the suggestion is seen."""
    from maindscout.api import review

    pair = _pair(session, org_id, job_id, candidate_id)
    if pair.pair_state == "new":
        review.set_state(session, org_id, job_id, candidate_id, "seen", actor)
    _track(pair, viewed_at=(pair.contact or {}).get("viewed_at") or _now().isoformat())
    session.flush()
    return pair


def decide(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, choice: str, actor: str,
           reason: str | None = None, note: str | None = None) -> CandidateJob:
    """reach_out (Priority, by the owner), later (Review later), or pass (not for this role, with a reason)."""
    from maindscout.api import review

    pair = _pair(session, org_id, job_id, candidate_id)
    if pair.pair_state == "new":
        review.set_state(session, org_id, job_id, candidate_id, "seen", actor)
    if pair.band_overridden_by is None:
        _track(pair, machine={"band": pair.triage_band, "reason": pair.triage_reason})
    if choice == "reach_out":
        review.override_band(session, org_id, job_id, candidate_id, "priority", actor, "you chose to reach out")
        _track(pair, stage="to_contact", decided_at=_now().isoformat())
    elif choice == "later":
        review.override_band(session, org_id, job_id, candidate_id, "review_later", actor, "maybe later")
        _track(pair, stage="later", decided_at=_now().isoformat())
    elif choice == "pass":
        if reason not in PASS:
            raise OutreachError(f"Say why: one of {tuple(PASS)}")
        review.set_state(session, org_id, job_id, candidate_id, "we_passed", actor, reason=PASS[reason],
                         note=note or ("not their field" if reason == "domain" else None))
        _track(pair, stage="passed", passed_for=reason, decided_at=_now().isoformat())
    else:
        raise OutreachError("choice must be reach_out, later or pass")
    session.flush()
    return pair


def undo(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, actor: str) -> CandidateJob:
    """Back to the suggestions: the machine's band again, and a pass reopened (before anyone was contacted)."""
    from maindscout.api import review

    pair = _pair(session, org_id, job_id, candidate_id)
    if pair.pair_state not in ("new", "seen", "we_passed") or (pair.contact or {}).get("contacted_at"):
        raise OutreachError("Already contacted: change the stage on their page instead")
    if pair.pair_state == "we_passed":
        review.set_state(session, org_id, job_id, candidate_id, "seen", actor, note="undone: back to the suggestions")
    if pair.band_overridden_by is not None:
        kept = (pair.contact or {}).get("machine") or {}
        if not kept:
            last = session.scalar(select(PairEvent).where(PairEvent.pair_id == pair.id, PairEvent.kind == "band",
                                                          PairEvent.cause["act"].astext == "override")
                                  .order_by(PairEvent.seq.desc()).limit(1))
            kept = {"band": last.from_value if last is not None else pair.triage_band, "reason": pair.triage_reason}
        session.add(PairEvent(org_id=org_id, pair_id=pair.id, kind="band", from_value=pair.triage_band, to_value=kept["band"],
                              reason="undone: back to the suggestions", cause={"act": "undo"}, actor=actor))
        pair.triage_band, pair.triage_reason, pair.band_overridden_by = kept["band"], kept.get("reason"), None
        pair.version = (pair.version or 1) + 1
    pair.contact = {k: v for k, v in (pair.contact or {}).items() if k == "viewed_at"} or None
    session.flush()
    return pair


# --- the contact track -----------------------------------------------------------------------------------------------


def record_contact(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, channel: str, actor: str,
                   at: datetime | None = None, message: Message | None = None) -> CandidateJob | None:
    """The one record of first contact on a role, whichever door was used: the card's "Contacted by", a message marked
    sent, the stage set to contacted by hand, or a logged outgoing call or email about the role (x-ray B2, 2026-10-13).
    The card, the follow-up reminder, the LinkedIn email reader, freshness and the results all read this. A later
    door never overwrites the first record."""
    from maindscout.api import messages, review

    pair = session.scalar(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.job_id == job_id,
                                                     CandidateJob.candidate_id == candidate_id))
    if pair is None:
        return None
    at = at or _now()
    track = pair.contact or {}
    if not track.get("contacted_at"):
        due = message.follow_up_due if message is not None and message.follow_up_due else at + timedelta(days=messages.follow_up_days())
        _track(pair, stage=track.get("stage") if track.get("stage") in ("replied", "call_booked") else "contacted",
               channel=channel if channel in CHANNELS else "other", contacted_at=at.isoformat(), follow_up_due=due.isoformat(),
               **({"message_id": str(message.id)} if message is not None else {}))
    elif message is not None and not track.get("message_id"):
        _track(pair, message_id=str(message.id))
    if pair.pair_state in WAITING:
        review.set_state(session, org_id, job_id, candidate_id, "contacted", actor)
    session.flush()
    return pair


def record_reply(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, actor: str, *,
                 at: datetime | None = None, outcome: str | None = None, text: str | None = None, note: str | None = None,
                 check_back: date | None = None, source: str | None = None, from_message: bool = False) -> CandidateJob | None:
    """The one record of their reply, whichever door it came through: one click on the card, a message marked replied,
    a logged call or email from them about the role, or LinkedIn's email. A reply stops the follow-ups. A reply whose
    meaning the owner already gave is never blanked by a later one that has none."""
    from maindscout.api import messages

    pair = record_contact(session, org_id, job_id, candidate_id, "other", actor, at=at)  # a reply means they were reached
    if pair is None:
        return None
    at = at or _now()
    if not from_message:
        m = _open_outreach(session, org_id, job_id, candidate_id)
        if m is not None and m.status == "sent":
            messages.mark_replied(session, org_id, m.id, at, track=False)
    old = (pair.contact or {}).get("reply") or {}
    if old.get("outcome") and not outcome:
        return pair
    _track(pair, stage="call_booked" if (pair.contact or {}).get("stage") == "call_booked" else "replied",
           reply={"outcome": outcome, "at": at.isoformat(), "note": note or old.get("note"),
                  "text": (text or "")[:2000] or old.get("text"), "source": source or old.get("source"),
                  "check_back": (check_back or (date.today() + timedelta(days=90))).isoformat() if outcome == "not_now" else None})
    session.flush()
    return pair


ACTIVITY_CHANNEL = {"call": "phone", "email": "email", "message": "other", "meeting": "other"}


def from_activity(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, kind: str, direction: str | None,
                  job_id: uuid.UUID | None, actor: str, at: datetime | None = None, summary: str | None = None) -> None:
    """A call, email, message or meeting logged by a person about a role counts on that role: "we reached out" is first
    contact; "they reached out" is a reply."""
    if job_id is None or kind not in ACTIVITY_CHANNEL or direction not in ("in", "out"):
        return
    if direction == "out":
        record_contact(session, org_id, job_id, candidate_id, ACTIVITY_CHANNEL[kind], actor, at=at)
    else:
        record_reply(session, org_id, job_id, candidate_id, actor, at=at, text=summary, source="logged")


def contacted(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, channel: str, actor: str,
              note: str | None = None) -> Message:
    """They were contacted outside the desk (on LinkedIn, by InMail, by email, by phone): recorded as a sent first
    contact, so the follow-up reminder (4 days) and the reply tracking work as for any message."""
    from maindscout.api import messages

    if channel not in CHANNELS:
        raise OutreachError(f"channel must be one of {tuple(CHANNELS)}")
    person = session.get(Candidate, candidate_id)
    if person is None or person.org_id != org_id:
        raise LookupError(f"No candidate {candidate_id}")
    if person.do_not_contact_at is not None:
        raise OutreachError("They asked not to be contacted")
    _pair(session, org_id, job_id, candidate_id)
    linkedin = channel in LINKEDIN_CHANNELS
    to = (messages._linkedin(session, org_id, candidate_id) if linkedin
          else messages._email(session, org_id, candidate_id) if channel == "email" else None) or "(outside the desk)"
    m = Message(org_id=org_id, kind="candidate_outreach", to_address=to, subject=CHANNELS[channel],
                body=(note or "").strip() or f"Contacted by {CHANNELS[channel]}, outside the desk.", status="draft",
                created_by=actor, provider="linkedin" if linkedin else None, candidate_id=candidate_id, job_id=job_id)
    session.add(m)
    session.flush()
    messages.mark_sent(session, org_id, m.id, channel=channel)
    return m


def _open_outreach(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID) -> Message | None:
    return session.scalar(select(Message).where(Message.org_id == org_id, Message.candidate_id == candidate_id,
                                                Message.kind == "candidate_outreach", Message.job_id == job_id,
                                                Message.status.in_(("sent", "replied"))).order_by(Message.created_at.desc()).limit(1))


def replied(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, outcome: str, actor: str,
            note: str | None = None, check_back: date | None = None, text: str | None = None) -> CandidateJob:
    """Their answer: interested, not now (back in the pool, with a date to check back), not interested, or stop. A
    reply stops the follow-ups."""
    from maindscout.api import consent, relationship, review

    if outcome not in OUTCOMES:
        raise OutreachError(f"outcome must be one of {OUTCOMES}")
    pair = _pair(session, org_id, job_id, candidate_id)
    words = {"interested": "interested", "not_now": "not now", "not_interested": "not interested", "stop": "asked to stop"}[outcome]
    relationship.log(session, org_id, "candidate", candidate_id, "message",
                     f"Replied: {words}" + (f". {note.strip()}" if (note or "").strip() else "") + (f' "{text.strip()[:500]}"' if text else ""),
                     actor, direction="in", job_id=job_id)
    record_reply(session, org_id, job_id, candidate_id, actor, outcome=outcome, text=text, note=note, check_back=check_back,
                 source="you")
    if outcome == "stop":
        consent.stop(session, org_id, candidate_id, actor, note)
    elif outcome in ("not_now", "not_interested") and pair.pair_state not in ("we_passed", "withdrawn", "placed", "client_rejected"):
        when = check_back or (date.today() + timedelta(days=90) if outcome == "not_now" else None)
        review.set_state(session, org_id, job_id, candidate_id, "we_passed", actor, reason="candidate_not_interested",
                         note=f"{words}" + (f"; check back from {when.isoformat()}" if when else ""))
    session.flush()
    return pair


def call_booked(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, actor: str,
                when: datetime | None = None) -> CandidateJob:
    from maindscout.api import relationship

    pair = _pair(session, org_id, job_id, candidate_id)
    relationship.log(session, org_id, "candidate", candidate_id, "note",
                     "Call booked" + (f" for {when.strftime('%d %b %Y %H:%M')}" if when else ""), actor, job_id=job_id)
    _track(pair, stage="call_booked", call_at=when.isoformat() if when else None)
    session.flush()
    return pair


def linkedin_accepted(session: Session, org_id: uuid.UUID, pair: CandidateJob, at: datetime) -> None:
    from maindscout.api import relationship

    if (pair.contact or {}).get("accepted_at"):
        return
    relationship.log(session, org_id, "candidate", pair.candidate_id, "message", "Accepted your LinkedIn invitation", "mailbox",
                     direction="in", occurred_at=at, job_id=pair.job_id)
    _track(pair, accepted_at=at.isoformat())
    session.flush()


# --- the role's lists ---------------------------------------------------------------------------------------------------


def stage(pair: CandidateJob) -> str:
    """Where this person is in the workflow, for the Sourcing tab."""
    track = pair.contact or {}
    if pair.pair_state in ("screened", "submitted", "interviewing", "offer", "placed"):
        return pair.pair_state
    if pair.pair_state in ("we_passed", "withdrawn", "client_rejected"):
        return "passed"
    if track.get("stage") in ("contacted", "replied", "call_booked"):
        return track["stage"]
    if pair.pair_state == "contacted":
        return "contacted"
    if pair.band_overridden_by is not None:
        return "to_contact" if pair.triage_band == "priority" else "later" if pair.triage_band == "review_later" else "passed"
    return "to_review"


# --- LinkedIn notifications from the owner's mailbox --------------------------------------------------------------------
#
# LinkedIn emails the owner when an invitation is accepted or a message arrives. The desk asks the mailbox (Google or
# Microsoft does the search) only for mail from LinkedIn naming someone contacted on LinkedIn; no other email is
# fetched. A match moves the person's track on; two contacted people with one name raise a question on both cards.

LINKEDIN_CHANNELS = ("linkedin_invite", "linkedin_message", "inmail")
ACCEPTED = re.compile(r"accepted your invitation|are now connected|now a connection|hat Ihre Einladung angenommen|"
                      r"Einladung angenommen|a accepté votre invitation", re.I)
MESSAGED = re.compile(r"sent you (a |an )?(new )?(message|InMail)|new message|just messaged you|messaged you|replied to your|"
                      r"hat Ihnen (eine )?Nachricht|neue Nachricht|vous a envoyé un message|nouveau message", re.I)
NAMES_PER_SEARCH = 20


def _watched(session: Session, org_id: uuid.UUID) -> list[CandidateJob]:
    """Pairs contacted on LinkedIn, still waiting for an acceptance or a reply."""
    pairs = session.scalars(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.contact.is_not(None),
                                                       CandidateJob.contact["channel"].astext.in_(LINKEDIN_CHANNELS)))
    return [p for p in pairs if (p.contact or {}).get("stage") in ("contacted", "replied")
            and p.pair_state not in ("we_passed", "withdrawn", "client_rejected", "placed")
            and not ((p.contact or {}).get("stage") == "replied" and (p.contact or {}).get("accepted_at"))]


def _named(name: str, text: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I))


def read_linkedin(session: Session, org_id: uuid.UUID, provider: Any, now: datetime | None = None) -> dict[str, Any]:
    """Read LinkedIn's notification emails about the people contacted on LinkedIn, and move their tracks on."""
    from maindscout.api.queries import names

    out = {"accepted": 0, "replied": 0, "unclear": 0}
    if not hasattr(provider, "linkedin_mail"):
        return out
    pairs = [p for p in _watched(session, org_id) if not session.get(Candidate, p.candidate_id).do_not_contact_at]
    if not pairs:
        return out
    who = {cid: n for cid, n in names(session, list({p.candidate_id for p in pairs})).items() if n and " " in n.strip()}
    by_name: dict[str, set[uuid.UUID]] = {}
    for cid, n in who.items():
        by_name.setdefault(n.strip().lower(), set()).add(cid)
    pairs = [p for p in pairs if p.contact.get("contacted_at")]
    if not pairs:
        return out
    since = min(datetime.fromisoformat(p.contact["contacted_at"]) for p in pairs)
    wanted = sorted({who[cid].strip() for cid in who})
    mails: dict[str, dict[str, Any]] = {}
    for i in range(0, len(wanted), NAMES_PER_SEARCH):
        for mail in provider.linkedin_mail(wanted[i:i + NAMES_PER_SEARCH], since):
            mails[mail["id"]] = mail
    for mail in sorted(mails.values(), key=lambda m: m["at"]):
        mail["at"] = min(mail["at"], _now())  # a mail server's clock a little ahead of ours
        if "linkedin.com" not in (mail.get("from") or "").lower():
            continue  # the search asked for LinkedIn's mail only; anything else is never read
        text = f"{mail.get('subject') or ''}\n{mail.get('snippet') or ''}"
        kind = "accepted" if ACCEPTED.search(text) else "message" if MESSAGED.search(text) else None
        if kind is None:
            continue
        for name, cids in by_name.items():
            if not _named(name, text):
                continue
            hits = [p for p in pairs if p.candidate_id in cids]
            fresh = [p for p in hits if mail["id"] not in (p.contact or {}).get("mail_ids", [])
                     and datetime.fromisoformat(p.contact["contacted_at"]) <= mail["at"]]
            if not fresh:
                continue
            for p in fresh:
                _track(p, mail_ids=[*(p.contact or {}).get("mail_ids", []), mail["id"]][-50:])
            if len({p.candidate_id for p in fresh}) > 1:
                for p in fresh:
                    _track(p, unclear={"kind": kind, "at": mail["at"].isoformat(), "subject": (mail.get("subject") or "")[:200],
                                       "snippet": (mail.get("snippet") or "")[:500], "mail_id": mail["id"],
                                       "others": len({q.candidate_id for q in fresh}) - 1})
                out["unclear"] += 1
                continue
            for p in fresh:
                if _apply(session, org_id, p, kind, mail["at"], mail.get("snippet")):
                    out["accepted" if kind == "accepted" else "replied"] += 1
    session.flush()
    return out


def _apply(session: Session, org_id: uuid.UUID, pair: CandidateJob, kind: str, at: datetime, snippet: str | None) -> bool:
    from maindscout.api import relationship

    if kind == "accepted":
        if (pair.contact or {}).get("accepted_at"):
            return False
        linkedin_accepted(session, org_id, pair, at)
        return True
    if (pair.contact or {}).get("stage") != "contacted":
        return False
    relationship.log(session, org_id, "candidate", pair.candidate_id, "message",
                     "Replied on LinkedIn" + (f': "{snippet.strip()[:500]}"' if (snippet or "").strip() else ""), "mailbox",
                     direction="in", occurred_at=at, job_id=pair.job_id)
    record_reply(session, org_id, pair.job_id, pair.candidate_id, "mailbox", at=at, text=snippet, source="linkedin_email")
    return True


def settle(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, mine: bool, actor: str) -> CandidateJob:
    """The owner answers "is this LinkedIn email about this person?" on a card: yes applies it, no drops it."""
    pair = _pair(session, org_id, job_id, candidate_id)
    notice = (pair.contact or {}).get("unclear")
    if not notice:
        raise OutreachError("Nothing to settle")
    pair.contact = {k: v for k, v in pair.contact.items() if k != "unclear"}
    if mine:
        _apply(session, org_id, pair, notice["kind"], datetime.fromisoformat(notice["at"]), notice.get("snippet"))
        for other in session.scalars(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.id != pair.id,
                                                                CandidateJob.contact["unclear"]["mail_id"].astext == notice["mail_id"])):
            other.contact = {k: v for k, v in other.contact.items() if k != "unclear"}
            if other.candidate_id == candidate_id:  # the same person on another role
                _apply(session, org_id, other, notice["kind"], datetime.fromisoformat(notice["at"]), notice.get("snippet"))
    session.flush()
    return pair
