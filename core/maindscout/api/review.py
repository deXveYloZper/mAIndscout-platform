"""Human acts. The only way anything becomes official.

- approve: pin the claim's current view as `approved_view`; it never changes behind anyone's back.
- reject: the claim stops counting; its reason is kept.
- assert: a human types a fact; it is born approved (source `human_assertion`).
- resolve: answer a review card (revision_diff, duplicate_stint, contradiction, identity_note).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import writer
from maindscout.api.process import natural_key
from maindscout.db.models import Candidate, CandidateJob, Claim, ClaimObservation, Decision, DecisionItem, Evidence, Job
from maindscout.domain import stints

REJECT_CODES = ("low_confidence", "wrong", "not_about_subject", "duplicate", "outdated", "other")


class ReviewError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _claim(session: Session, org_id: uuid.UUID, claim_id: uuid.UUID) -> Claim:
    claim = session.get(Claim, claim_id)
    if claim is None or claim.org_id != org_id:
        raise LookupError(f"No claim {claim_id}")
    return claim


def _decision(session: Session, org_id: uuid.UUID, decision_id: uuid.UUID) -> Decision:
    decision = session.get(Decision, decision_id)
    if decision is None or decision.org_id != org_id:
        raise LookupError(f"No decision {decision_id}")
    return decision


def _items(session: Session, decision: Decision) -> list[DecisionItem]:
    return list(session.scalars(select(DecisionItem).where(DecisionItem.decision_id == decision.id)))


def _seal(decision: Decision, resolution: dict[str, Any], actor: str) -> None:
    decision.sealed_at = _now()
    decision.resolution = {**resolution, "by": actor, "at": _now().isoformat()}


def _open_decisions_for(session: Session, claim: Claim, type_: str) -> list[Decision]:
    return list(session.scalars(
        select(Decision).join(DecisionItem, DecisionItem.decision_id == Decision.id).where(
            DecisionItem.claim_id == claim.id, Decision.type == type_, Decision.sealed_at.is_(None))))


def approve_claim(session: Session, org_id: uuid.UUID, claim_id: uuid.UUID, actor: str) -> Claim:
    """Pin the current view. If the claim sits in an open contradiction, its peers are rejected in the same act."""
    claim = _claim(session, org_id, claim_id)
    if claim.status != "proposed":
        raise ReviewError(f"Only a proposed claim can be approved (this one is {claim.status})")
    claim.status, claim.approved_view = "approved", dict(claim.payload)
    claim.approved_view_hash = stints.reconcile.view_hash(claim.approved_view)
    claim.approved_by, claim.approved_at = actor, _now()
    for decision in _open_decisions_for(session, claim, "contradiction"):
        for item in _items(session, decision):
            item.outcome = "approved" if item.claim_id == claim.id else "rejected"
            if item.claim_id != claim.id:
                peer = session.get(Claim, item.claim_id)
                if peer.status in ("proposed", "approved"):
                    peer.status, peer.rejection_reason = "rejected", {"code": "outdated", "note": "lost a contradiction"}
        _seal(decision, {"action": "approved", "claim_id": str(claim.id)}, actor)
    session.flush()
    return claim


def reject_claim(session: Session, org_id: uuid.UUID, claim_id: uuid.UUID, actor: str,
                 code: str = "low_confidence", note: str | None = None) -> Claim:
    claim = _claim(session, org_id, claim_id)
    if code not in REJECT_CODES:
        raise ReviewError(f"Reason code must be one of {REJECT_CODES}")
    if claim.status not in ("proposed", "approved"):
        raise ReviewError(f"A {claim.status} claim cannot be rejected")
    claim.status, claim.rejection_reason = "rejected", {"code": code, "note": note, "by": actor}
    session.flush()
    return claim


def assert_claim(session: Session, org_id: uuid.UUID, actor: str, *, subject_type: str, subject_id: uuid.UUID,
                 claim_type: str, payload: dict[str, Any], valid_from: str | None = None, valid_to: str | None = None,
                 replaces: uuid.UUID | None = None) -> Claim:
    """A fact typed by a human: born approved. A typed ContactClaim is a clean identity key.

    `replaces` rejects the claim it corrects (e.g. an email the text layer garbled) in the same act.
    """
    if subject_type == "candidate":
        owner = session.get(Candidate, subject_id)
    else:
        owner = session.get(Job, subject_id)
    if owner is None or owner.org_id != org_id:
        raise LookupError(f"No {subject_type} {subject_id}")
    if claim_type == "ContactClaim":
        payload = {**payload, "attributable": True, "attribution": "subject"}
    key = natural_key(subject_id, claim_type, payload, valid_from, valid_to)
    view = dict(payload)
    claim = writer.add_claim(
        session, org_id=org_id, subject_type=subject_type, subject_id=subject_id, claim_type=claim_type,
        payload=payload, natural_key=key, status="approved", approved_view=view,
        approved_view_hash=stints.reconcile.view_hash(view), approved_by=actor, approved_at=_now(),
        valid_from=date.fromisoformat(valid_from) if valid_from else None,
        valid_to=date.fromisoformat(valid_to) if valid_to else None,
        temporal_precision="exact" if valid_from else "unknown", observed_as_of=date.today(),
    )
    evidence = Evidence(org_id=org_id, claim_id=claim.id, evidence_type="human_assertion", source_authority="human_assertion",
                        origin="human", snippet=None, observed_as_of=date.today(),
                        span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none", "detail": f"typed by {actor}"})
    session.add(evidence)
    session.flush()
    session.add(ClaimObservation(org_id=org_id, claim_id=claim.id, attribute_path=".", value=payload, evidence_id=evidence.id,
                                 source_authority="human_assertion", origin="human", observed_as_of=date.today()))
    if replaces:
        old = _claim(session, org_id, replaces)
        if old.subject_id != subject_id:
            raise ReviewError("A correction must be about the same subject")
        if old.status in ("proposed", "approved"):
            old.status, old.superseded_by = "superseded", claim.id
    session.flush()
    return claim


def resolve_decision(session: Session, org_id: uuid.UUID, decision_id: uuid.UUID, actor: str, action: str,
                     claim_id: uuid.UUID | None = None) -> Decision:
    decision = _decision(session, org_id, decision_id)
    if decision.sealed_at:
        raise ReviewError("This decision is already resolved")
    items = _items(session, decision)

    if decision.type == "revision_diff":
        claim = session.get(Claim, items[0].claim_id)
        if action == "accept_new":
            new_view = decision.context["new_view"]
            claim.payload, claim.approved_view = dict(new_view), dict(new_view)
            claim.approved_view_hash = stints.reconcile.view_hash(new_view)
            claim.approved_by, claim.approved_at = actor, _now()
        elif action != "keep_old":
            raise ReviewError("revision_diff takes keep_old or accept_new")
        items[0].outcome = action

    elif decision.type == "duplicate_stint":
        left, right = (session.get(Claim, i.claim_id) for i in items)
        if action == "same":
            older, newer = sorted((left, right), key=lambda c: c.created_at)
            for obs in session.scalars(select(ClaimObservation).where(ClaimObservation.claim_id == newer.id)):
                obs.claim_id = older.id
            for ev in session.scalars(select(Evidence).where(Evidence.claim_id == newer.id)):
                ev.claim_id = older.id
            newer.status, newer.superseded_by = "superseded", older.id
            writer.set_flags(session, older, {k: v for k, v in older.flags.items() if k != "possible_duplicate_stint"})
        elif action == "two":
            for claim in (left, right):
                writer.set_flags(session, claim, {k: v for k, v in claim.flags.items() if k != "possible_duplicate_stint"})
        else:
            raise ReviewError("duplicate_stint takes same or two")
        for item in items:
            item.outcome = action

    elif decision.type == "contradiction":
        if action != "pick" or claim_id not in {i.claim_id for i in items}:
            raise ReviewError("contradiction takes pick with one of its claim ids")
        approve_claim(session, org_id, claim_id, actor)  # rejects the peer and seals in the same act
        session.flush()
        return decision

    elif decision.type == "identity_note":
        if action != "acknowledge":
            raise ReviewError("identity_note takes acknowledge (merging people is not part of Slice 0)")

    _seal(decision, {"action": action}, actor)
    session.flush()
    return decision


def override_band(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, band: str,
                  actor: str, reason: str | None = None) -> CandidateJob:
    if band not in ("priority", "review_later", "do_not_submit"):
        raise ReviewError("band must be priority, review_later or do_not_submit")
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job_id, CandidateJob.candidate_id == candidate_id,
                                                     CandidateJob.org_id == org_id))
    if pair is None:
        raise LookupError("No such pair")
    pair.triage_band, pair.triage_reason = band, f"human_override:{reason or 'no reason given'}"
    pair.band_overridden_by, pair.version = actor, pair.version + 1
    session.flush()
    return pair
