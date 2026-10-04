"""The Brief (Slice 3): compile, reconcile and answer call questions for a person on a job.

- Default scope: priority people on a job (others on request).
- Reconcile, never regenerate: new sources add open items; items whose source is gone expire; answered and dismissed
  items are never brought back.
- Answering creates a born-approved human assertion (BriefAnswerClaim, or a SkillClaim / LocationClaim when the answer
  is one) and re-matches the person at once. Person-scope answers count for every job.
- No send path: the Brief is a checklist for the recruiter's own call.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import review
from maindscout.db.models import BriefItem, Candidate, CandidateJob, Claim, Job
from maindscout.domain import brief as compiler
from maindscout.domain import geo

LIVE = ("proposed", "approved")
ALIVE = ("open", "asked")


class BriefError(ValueError):
    pass


def _pair(session: Session, org_id, job_id, candidate_id) -> CandidateJob:
    pair = session.scalar(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.job_id == job_id,
                                                     CandidateJob.candidate_id == candidate_id))
    if pair is None:
        raise LookupError("This person is not on this job")
    return pair


def _sources(session: Session, org_id, pair: CandidateJob) -> list[compiler.Item]:
    from maindscout.api import coverage, profiles

    snap = profiles.latest(session, pair.candidate_id)
    suspects = [{"claim_id": str(c.id), "kind": c.payload.get("kind"), "value": c.payload.get("value")}
                for c in session.scalars(select(Claim).where(
                    Claim.org_id == org_id, Claim.subject_id == pair.candidate_id, Claim.claim_type == "ContactClaim",
                    Claim.status == "proposed", Claim.flags["possible_ocr_identifier"].astext == "true"))]
    lives = coverage.signals(session, org_id, pair.candidate_id)[0]
    items = compiler.for_person(snap.profile if snap else None, suspects, bool(lives))
    job = session.get(Job, pair.job_id)
    sources = {str(c.id): (c.approved_view or c.payload).get("source") or "ad"
               for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                            Claim.status.in_(LIVE)))}
    items += compiler.for_job((pair.match or {}).get("rows") or [], job.hiring_company or "the company", sources)
    return items


def build(session: Session, org_id, job_id: uuid.UUID, candidate_id: uuid.UUID, force: bool = False) -> list[BriefItem]:
    """Compile and reconcile the Brief for one person on one job. Only priority people unless `force`."""
    pair = _pair(session, org_id, job_id, candidate_id)
    person = session.get(Candidate, candidate_id)
    if person.archived_at is not None:
        raise BriefError("This person is archived as outside coverage: bring them back first.")
    if pair.triage_band != "priority" and not force:
        raise BriefError("Briefs are made for priority people; ask for one anyway if you want it.")
    wanted = {(i.scope, i.source_key): i for i in _sources(session, org_id, pair)}
    existing = list(session.scalars(select(BriefItem).where(
        BriefItem.candidate_id == candidate_id, (BriefItem.job_id == job_id) | (BriefItem.job_id.is_(None)))))
    have = {("job" if b.job_id else "person", b.source_key): b for b in existing}
    now = datetime.now(timezone.utc)
    for key, item in wanted.items():
        row = have.get(key)
        if row is None:
            session.add(BriefItem(org_id=org_id, candidate_id=candidate_id, job_id=job_id if item.scope == "job" else None,
                                  source_key=item.source_key, kind=item.kind, question=item.question, why=item.why,
                                  status="open"))
        elif row.status == "expired":  # the reason came back (e.g. a fact was un-approved): ask again
            row.status, row.question, row.why, row.updated_at = "open", item.question, item.why, now
        elif row.status in ALIVE and (row.question, row.why) != (item.question, item.why):
            row.question, row.why, row.updated_at = item.question, item.why, now
    for key, row in have.items():
        if key not in wanted and row.status in ALIVE:
            # Person-wide items are only retired from a person's own sources, which every job compiles the same way.
            row.status, row.updated_at = "expired", now
    session.flush()
    return items_for(session, job_id, candidate_id)


def header(session: Session, org_id, job_id: uuid.UUID, candidate_id: uuid.UUID) -> dict[str, Any]:
    """Who this is and why they are on the call list, in two lines (for a recruiter who has never seen them)."""
    from maindscout.api import profiles

    pair = _pair(session, org_id, job_id, candidate_id)
    snap = profiles.latest(session, candidate_id)
    rules = {r["id"]: r for r in (pair.match or {}).get("rules") or []}
    text = None
    if "strong_match" in rules:
        text = "Strong match: every must-have met or only to ask"
        detail = rules["strong_match"].get("detail") or ""
        if "strong-plus" in detail:
            text += f"; {detail}"
    elif "partial_must" in rules:
        text = f"Possible match: {rules['partial_must'].get('detail')}"
    elif "must_gaps" in rules:
        text = f"Possible match: a must-have is a gap ({rules['must_gaps'].get('detail')})"
    extras = {"domain_over_seniority": "a strong industry match outweighs one level below",
              "substitution": "one requirement stands in for another, as the intake allows",
              "contractor_fit": "long contract engagements fit this contract job"}
    if text:
        text += "".join(f"; {words}" for rid, words in extras.items() if rid in rules) + "."
    else:
        text = reason_words(pair.triage_reason)
    return {"summary": snap.profile["summary"] if snap else None, "reading": snap.profile["reading"]["label"] if snap else None,
            "band": pair.triage_band, "tier": pair.match_tier, "why": text}


def reason_words(reason: str | None) -> str | None:
    """The pair's band reason in plain words (when no matching rule explains it yet)."""
    if not reason:
        return None
    code, _, rest = reason.partition(":")
    if code == "supported":
        return f"Has {rest.replace(',', ', ')}, a must-have that decides the band."
    if code == "no_support_for_must_have":
        return f"No evidence of {rest}, a must-have that decides the band."
    if code == "human_override":
        return f"Set by hand: {rest}"
    if code == "match":
        return rest.partition(":")[2] or rest
    if code == "no_distinctive_requirements":
        return "The job has no must-have that decides the band yet."
    return reason


def items_for(session: Session, job_id: uuid.UUID, candidate_id: uuid.UUID) -> list[BriefItem]:
    return list(session.scalars(select(BriefItem).where(
        BriefItem.candidate_id == candidate_id, (BriefItem.job_id == job_id) | (BriefItem.job_id.is_(None)))
        .order_by(BriefItem.job_id.is_(None).desc(), BriefItem.created_at, BriefItem.source_key)))


def _item(session: Session, org_id, item_id: uuid.UUID) -> BriefItem:
    item = session.get(BriefItem, item_id)
    if item is None or item.org_id != org_id:
        raise LookupError(f"No brief item {item_id}")
    return item


def mark_asked(session: Session, org_id, item_id: uuid.UUID, actor: str) -> BriefItem:
    item = _item(session, org_id, item_id)
    if item.status == "open":
        item.status, item.updated_at = "asked", datetime.now(timezone.utc)
    session.flush()
    return item


def dismiss(session: Session, org_id, item_id: uuid.UUID, actor: str) -> BriefItem:
    item = _item(session, org_id, item_id)
    if item.status in ALIVE:
        item.status, item.answered_by, item.updated_at = "dismissed", actor, datetime.now(timezone.utc)
    session.flush()
    return item


def answer(session: Session, org_id, item_id: uuid.UUID, outcome: str, text: str | None, actor: str) -> BriefItem:
    """Capture the answer as an approved fact and re-match the person."""
    item = _item(session, org_id, item_id)
    if outcome not in ("confirmed", "not_met", "noted"):
        raise BriefError("outcome must be confirmed, not_met or noted")
    if item.status not in ALIVE:
        raise BriefError(f"This question is already {item.status}")
    text = (text or "").strip() or None
    if outcome == "noted" and not text:
        raise BriefError("Write what they said")
    claim = None
    if item.kind == "contact":
        target = uuid.UUID(item.source_key.split(":", 1)[1])
        if outcome == "confirmed":
            review.approve_claim(session, org_id, target, actor)
        elif outcome == "not_met":
            review.reject_claim(session, org_id, target, actor, "wrong", text)
    elif item.source_key == "std:location" and text and geo.country_in(text):
        claim = review.assert_claim(session, org_id, actor, subject_type="candidate", subject_id=item.candidate_id,
                                    claim_type="LocationClaim",
                                    payload={"place_raw": text, "country_code": geo.country_in(text), "basis": "stated", "kind": "current"})
    if item.kind != "contact":
        requirement = _requirement(session, item)
        token = (requirement.payload.get("normalized_token") if requirement is not None else None)
        if outcome == "confirmed" and requirement is not None and requirement.payload.get("category") == "skill" and token:
            # A skill confirmed on the call is an official skill: the gap table and matching see it.
            review.assert_claim(session, org_id, actor, subject_type="candidate", subject_id=item.candidate_id,
                                claim_type="SkillClaim", payload={"raw_label": token, "normalized_skill": token})
        claim = review.assert_claim(session, org_id, actor, subject_type="candidate", subject_id=item.candidate_id,
                                    claim_type="BriefAnswerClaim", payload={
                                        "topic": item.source_key, "question": item.question, "outcome": outcome, "answer": text,
                                        "job_id": str(item.job_id) if item.job_id else None,
                                        "requirement_id": str(requirement.id) if requirement is not None else None})
    item.status, item.outcome, item.answer, item.answered_by = "answered", outcome, text, actor
    item.answer_claim_id = claim.id if claim is not None else None
    item.updated_at = datetime.now(timezone.utc)
    session.flush()
    from maindscout.api.process import retriage_candidate

    retriage_candidate(session, org_id, item.candidate_id, {"act": "brief_answer", "item_id": str(item.id)}, actor)
    return item


def _requirement(session: Session, item: BriefItem) -> Claim | None:
    if not item.source_key.startswith("req:"):
        return None
    try:
        return session.get(Claim, uuid.UUID(item.source_key[4:]))
    except ValueError:
        return None


def answers_for(session: Session, org_id, candidate_id) -> dict[str, dict[str, Any]]:
    """requirement id -> the latest call answer about it (matching reads these)."""
    out: dict[str, dict[str, Any]] = {}
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                 Claim.claim_type == "BriefAnswerClaim", Claim.status == "approved")
                             .order_by(Claim.created_at)):
        rid = c.payload.get("requirement_id")
        if rid and c.payload.get("outcome") in ("confirmed", "not_met"):
            out[rid] = {"outcome": c.payload["outcome"], "answer": c.payload.get("answer")}
    return out


def as_dict(b: BriefItem) -> dict[str, Any]:
    return {"id": str(b.id), "scope": "job" if b.job_id else "person", "kind": b.kind, "source_key": b.source_key,
            "question": b.question, "why": b.why, "status": b.status, "outcome": b.outcome, "answer": b.answer,
            "answered_by": b.answered_by, "updated_at": b.updated_at.isoformat() if b.updated_at else None}
