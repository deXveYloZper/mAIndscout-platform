"""Human acts. The only way anything becomes official.

- approve: pin the claim's current view as `approved_view`; it never changes behind anyone's back.
- reject: the claim stops counting; its reason is kept.
- assert: a human types a fact; it is born approved (source `human_assertion`).
- resolve: answer a review card (revision_diff, duplicate_stint, contradiction, identity_note).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import writer
from maindscout.api.process import natural_key, rematch_job, retriage_candidate
from maindscout.db.models import Candidate, CandidateJob, Claim, ClaimObservation, Decision, DecisionItem, Evidence, Job, PairEvent
from maindscout.domain import stints

REJECT_CODES = ("low_confidence", "wrong", "not_about_subject", "duplicate", "outdated", "other")
PASS_REASONS = ("skills", "seniority", "location", "compensation", "candidate_not_interested", "client_rejected",
                "duplicate", "other")


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


def retriage_after(session: Session, claim: Claim, act: str, actor: str) -> None:
    """A human changed a fact: bands that may depend on it are recomputed, and each change is recorded."""
    cause = {"act": act, "claim_id": str(claim.id), "claim_type": claim.claim_type}
    from maindscout.api import coverage

    batch = session.info.get("batch")
    if batch is not None and claim.subject_type == "candidate":  # a bulk approval: once, at the end (see batched)
        batch.setdefault(claim.subject_id, set()).add(claim.claim_type)
        return
    if claim.subject_type == "candidate":
        retriage_candidate(session, claim.org_id, claim.subject_id, cause, actor)
        if claim.claim_type in ("LocationClaim", "CareerStepClaim"):
            coverage.evaluate(session, claim.org_id, claim.subject_id, cause, actor)
        if claim.claim_type in ("CareerStepClaim", "StepClassificationClaim", "EducationClaim"):
            from maindscout.api import profiles

            profiles.build(session, claim.org_id, claim.subject_id)  # code only: a person's correction shows at once
    elif claim.subject_type == "job":
        rematch_job(session, claim.org_id, claim.subject_id, cause, actor)
        if (claim.payload.get("mobility") or {}).get("facet") == "residence":
            from maindscout.db.models import Job

            coverage.reevaluate_job(session, session.get(Job, claim.subject_id), cause, actor)


@contextmanager
def batched(session: Session, org_id: uuid.UUID, cause: dict[str, Any], actor: str):
    """Many fact changes about people in one act (a call review, approving a whole CV): matching, coverage and
    profiles are recomputed once per person at the end, not once per fact."""
    from maindscout.api import coverage, profiles

    if session.info.get("batch") is not None:  # already inside one
        yield
        return
    session.info["batch"] = {}
    try:
        yield
        touched = session.info["batch"]
    finally:
        session.info.pop("batch", None)
    for candidate_id, types in touched.items():
        session.flush()
        if types & {"CareerStepClaim", "StepClassificationClaim", "EducationClaim"}:
            profiles.build(session, org_id, candidate_id)
        if types & {"LocationClaim", "CareerStepClaim"}:
            coverage.evaluate(session, org_id, candidate_id, cause, actor)
        retriage_candidate(session, org_id, candidate_id, cause, actor)


def in_batch(session: Session, candidate_id: uuid.UUID) -> bool:
    """Inside `batched`: note the person for the one re-match at the end and say so."""
    batch = session.info.get("batch")
    if batch is None:
        return False
    batch.setdefault(candidate_id, set())
    return True


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
    retriage_after(session, claim, "approve", actor)
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
    retriage_after(session, claim, "reject", actor)
    return claim


def assert_claim(session: Session, org_id: uuid.UUID, actor: str, *, subject_type: str, subject_id: uuid.UUID,
                 claim_type: str, payload: dict[str, Any], valid_from: str | None = None, valid_to: str | None = None,
                 replaces: uuid.UUID | None = None, precision: str | None = None,
                 said: dict[str, Any] | None = None) -> Claim:
    """A fact typed by a human: born approved. A typed ContactClaim is a clean identity key.

    `replaces` rejects the claim it corrects (e.g. an email the text layer garbled) in the same act.
    `said`: approved by a human but said by someone else, e.g. the candidate on a call. Keys document_id, snippet,
    char_start, char_end, artifact_id, origin, authority: the evidence is that span of that document, not the typist.
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
        temporal_precision=precision or ("exact" if valid_from else "unknown"), observed_as_of=date.today(),
    )
    if said:
        authority, origin = said.get("authority", "candidate_authored"), said.get("origin", "candidate")
        evidence = Evidence(org_id=org_id, claim_id=claim.id, evidence_type="document_span", document_id=said["document_id"],
                            locator={k: said[k] for k in ("artifact_id", "char_start", "char_end") if said.get(k) is not None},
                            snippet=said.get("snippet"), source_authority=authority, origin=origin, observed_as_of=date.today(),
                            span_validation={"tier": "quote", "result": "pass", "metric_bucket": "none",
                                             "detail": f"said on a call; approved by {actor}"})
    else:
        authority, origin = "human_assertion", "human"
        evidence = Evidence(org_id=org_id, claim_id=claim.id, evidence_type="human_assertion", source_authority=authority,
                            origin=origin, snippet=None, observed_as_of=date.today(),
                            span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none", "detail": f"typed by {actor}"})
    session.add(evidence)
    session.flush()
    session.add(ClaimObservation(org_id=org_id, claim_id=claim.id, attribute_path=".", value=payload, evidence_id=evidence.id,
                                 source_authority=authority, origin=origin, observed_as_of=date.today()))
    if replaces:
        old = _claim(session, org_id, replaces)
        if old.subject_id != subject_id:
            raise ReviewError("A correction must be about the same subject")
        if old.status in ("proposed", "approved"):
            old.status, old.superseded_by = "superseded", claim.id
    session.flush()
    retriage_after(session, claim, "typed", actor)
    return claim


def approve_document(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, document_id: uuid.UUID, actor: str) -> dict[str, int]:
    """"Approve all from this CV": every proposed fact about this person read from this document, in one act.
    Facts that wait on a question (two values disagree, an identifier the text layer may have garbled) are left
    for a person to settle one by one."""
    proposed = list(session.scalars(select(Claim).where(
        Claim.org_id == org_id, Claim.subject_id == candidate_id, Claim.status == "proposed",
        Claim.id.in_(select(Evidence.claim_id).where(Evidence.document_id == document_id)))))
    waiting = set(session.scalars(select(DecisionItem.claim_id).join(Decision, Decision.id == DecisionItem.decision_id).where(
        DecisionItem.claim_id.in_([c.id for c in proposed] or [None]), Decision.sealed_at.is_(None))))
    approved = left = 0
    with batched(session, org_id, {"act": "approve_document", "document_id": str(document_id)}, actor):
        for c in proposed:
            if c.id in waiting or (c.flags or {}).get("possible_ocr_identifier"):
                left += 1
                continue
            approve_claim(session, org_id, c.id, actor)
            approved += 1
    return {"approved": approved, "left": left}


def recheck_contacts(session: Session) -> list[dict[str, str]]:
    """Apply today's contact checks to contacts still waiting for "Confirm a contact" (free, no model). A text layer
    that only garbled or shortened what the file's own link says takes the link; an email that is a name with an
    initial is no longer a "misspelling". A contact that duplicates one already on file is retired."""
    from maindscout.db.models import ExtractionArtifact
    from maindscout.intelligence import contacts

    cleared = []
    waiting = session.scalars(select(Claim).where(Claim.claim_type == "ContactClaim", Claim.status == "proposed",
                                                  Claim.flags["possible_ocr_identifier"].astext == "true"))
    for c in list(waiting):
        ev = session.scalar(select(Evidence).where(Evidence.claim_id == c.id, Evidence.locator.is_not(None)).limit(1))
        artifact = session.get(ExtractionArtifact, uuid.UUID(ev.locator["artifact_id"])) if ev and (ev.locator or {}).get("artifact_id") else None
        annotations = (artifact.annotations or []) if artifact else []
        name = next(((n.approved_view or n.payload).get("full_name") for n in session.scalars(select(Claim).where(
            Claim.subject_id == c.subject_id, Claim.claim_type == "IdentityClaim", Claim.status.in_(("approved", "proposed")))
            .order_by(Claim.status))), None)
        verdict = contacts.judge(c.payload["kind"], c.payload["value"], name, annotations)
        if verdict.possible_ocr_identifier:
            continue
        payload = dict(c.payload)
        if verdict.use_value:
            payload["value"] = payload["normalized"] = verdict.use_value
        key = natural_key(c.subject_id, "ContactClaim", payload)
        twin = session.scalar(select(Claim).where(Claim.subject_id == c.subject_id, Claim.claim_type == "ContactClaim",
                                                  Claim.natural_key == key, Claim.id != c.id, Claim.status.in_(("approved", "proposed"))))
        if twin is not None:
            c.status, c.superseded_by = "superseded", twin.id
            if twin.flags.get("possible_ocr_identifier"):
                twin.flags = {k: v for k, v in twin.flags.items() if k != "possible_ocr_identifier"}
        else:
            c.payload, c.natural_key = payload, key
            c.flags = {k: v for k, v in c.flags.items() if k != "possible_ocr_identifier"}
        cleared.append({"claim_id": str(c.id), "kind": payload["kind"], "value": payload["value"],
                        "why": verdict.reason or "nothing left to ask under the current checks"})
    session.flush()
    return cleared


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

    elif decision.type == "company_same":
        from maindscout.api import companies

        if action == "same":
            companies.merge(session, uuid.UUID(decision.context["existing"]["id"]), uuid.UUID(decision.context["new"]["id"]),
                            actor, org_id)
        elif action != "different":
            raise ReviewError("company_same takes same or different")

    elif decision.type == "identity_note":
        if action != "acknowledge":
            raise ReviewError("identity_note takes acknowledge (merging people is not part of Slice 0)")

    _seal(decision, {"action": action}, actor)
    session.flush()
    for item in items:
        claim = session.get(Claim, item.claim_id)
        if claim is not None:
            retriage_after(session, claim, f"resolve:{decision.type}", actor)
            break
    return decision


def override_band(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, band: str,
                  actor: str, reason: str | None = None) -> CandidateJob:
    if band not in ("priority", "review_later", "do_not_submit"):
        raise ReviewError("band must be priority, review_later or do_not_submit")
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job_id, CandidateJob.candidate_id == candidate_id,
                                                     CandidateJob.org_id == org_id))
    if pair is None:
        raise LookupError("No such pair")
    old = pair.triage_band
    pair.triage_band, pair.triage_reason = band, f"human_override:{reason or 'no reason given'}"
    pair.band_overridden_by, pair.version = actor, pair.version + 1
    session.add(PairEvent(org_id=org_id, pair_id=pair.id, kind="band", from_value=old, to_value=band,
                          reason=pair.triage_reason, cause={"act": "override"}, actor=actor))
    session.flush()
    return pair


def set_state(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, state: str, actor: str,
              reason: str | None = None, note: str | None = None) -> CandidateJob:
    """Move a pair along the pipeline. The pair is never deleted; every move is recorded with who and why.

    - we_passed needs a reason code (PASS_REASONS): reasons are how the desk's taste is learned later.
    - submitted needs a note (to whom, how); withdrawn needs a note (why they pulled out).
    - client_rejected needs the client's feedback, and blocks the person at that client (every job there).
    - Moving out of an ending (placed, passed, withdrawn, rejected) needs a note saying why.
    - A person blocked by the client cannot be put in front of that client (submitted, interviewing, offer, placed).
    """
    from maindscout.api import pipeline
    from maindscout.db.models import PAIR_ENDINGS, PAIR_STATES

    if state not in PAIR_STATES or state == "new":
        raise ReviewError(f"state must be one of {PAIR_STATES[1:]}")
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job_id, CandidateJob.candidate_id == candidate_id,
                                                     CandidateJob.org_id == org_id))
    if pair is None:
        raise LookupError("No such pair")
    if state == pair.pair_state:
        return pair
    note = (note or "").strip() or None
    if state == "we_passed" and reason not in PASS_REASONS:
        raise ReviewError(f"we_passed needs a reason: one of {PASS_REASONS}")
    if state == "submitted" and not note:
        raise ReviewError("submitted needs a note (to whom, how)")
    if state == "withdrawn" and not note:
        raise ReviewError("withdrawn needs a note (why they pulled out)")
    if state == "client_rejected" and not note:
        raise ReviewError("client_rejected needs the client's feedback")
    if pair.pair_state in PAIR_ENDINGS and state not in PAIR_ENDINGS and not note:
        raise ReviewError("reopening needs a note saying why")
    pipeline.ensure_not_blocked(session, org_id, job_id, candidate_id, state)
    old = pair.pair_state
    pair.pair_state = state
    pair.version = (pair.version or 1) + 1
    if state in PAIR_ENDINGS or state == "submitted":
        party = "client" if state == "client_rejected" else "candidate" if state == "withdrawn" else "operator"
        pair.outcome = {"party": party, "state": state, "reason": reason, "note": note, "by": actor}
    elif old in PAIR_ENDINGS:
        pair.outcome = None
    words = reason if state == "we_passed" else note
    session.add(PairEvent(org_id=org_id, pair_id=pair.id, kind="state", from_value=old, to_value=state,
                          reason=words, cause={"act": "state", "note": note}, actor=actor))
    session.flush()
    if state == "client_rejected":
        pipeline.block(session, org_id, job_id, candidate_id, note, actor)
    return pair

