"""Forget one person: one action that deletes everything about them, then a check that fails loudly.

Scope (Slice 0, single-subject documents, 05 RA-04):
- the person's claims, their observations and evidence, review decisions and their items, pairs,
  not-same records, document links, their documents, text artifacts, runs and the original bytes
  (unless another org's document shares the same bytes);
- pointers to them in other people's identity notes;
- keyed hashes of their identifiers go into the suppression registry, so a later upload of the same
  person is blocked before anything about them is stored.

The verify query never trusts the erase step: it looks again, and lists every survivor it finds.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from maindscout.db.models import (
    Candidate,
    CandidateJob,
    Claim,
    ClaimObservation,
    Decision,
    DecisionItem,
    Document,
    DocumentSubject,
    Erasure,
    Evidence,
    ExtractionArtifact,
    IntelligenceRun,
    Job,
    NotSame,
    PairEvent,
    Score,
    SuppressionEntry,
)
from maindscout.settings import env
from maindscout.storage import BlobStore

KEY_KINDS = ("email", "phone", "linkedin")


class ErasureConflict(RuntimeError):
    """The person's data is entangled with someone else's and cannot be deleted without harming them."""


def identifier_hash(kind: str, normalized: str) -> str | None:
    """Keyed hash (HMAC-SHA256 with SUPPRESSION_KEY). None if no key is configured."""
    key = env("SUPPRESSION_KEY")
    if not key:
        return None
    return hmac.new(key.encode(), f"{kind}:{normalized}".encode(), hashlib.sha256).hexdigest()


def is_suppressed(session: Session, org_id: uuid.UUID, identifiers: list[tuple[str, str]]) -> SuppressionEntry | None:
    hashes = [h for h in (identifier_hash(k, n) for k, n in identifiers if k in KEY_KINDS) if h]
    if not hashes:
        return None
    return session.scalar(select(SuppressionEntry).where(
        SuppressionEntry.org_id == org_id, SuppressionEntry.identifier_hash.in_(hashes)))


def record_encounter(entry: SuppressionEntry) -> None:
    entry.encounters += 1
    entry.last_encounter_at = datetime.now(timezone.utc)


def _documents_of(session: Session, candidate_id: uuid.UUID) -> list[uuid.UUID]:
    linked = set(session.scalars(select(DocumentSubject.document_id).where(DocumentSubject.subject_id == candidate_id)))
    claim_ids = select(Claim.id).where(Claim.subject_id == candidate_id)
    evidenced = set(session.scalars(select(Evidence.document_id).where(Evidence.claim_id.in_(claim_ids), Evidence.document_id.is_not(None))))
    return sorted(linked | evidenced)


def _conflicts(session: Session, candidate_id: uuid.UUID, doc_ids: list[uuid.UUID]) -> list[str]:
    out = []
    if not doc_ids:
        return out
    others = session.scalars(select(DocumentSubject).where(
        DocumentSubject.document_id.in_(doc_ids), DocumentSubject.subject_id != candidate_id)).all()
    out += [f"document {s.document_id} is also about {s.subject_type} {s.subject_id}" for s in others]
    foreign_evidence = session.scalar(select(func.count()).select_from(Evidence).join(Claim, Claim.id == Evidence.claim_id).where(
        Evidence.document_id.in_(doc_ids), Claim.subject_id != candidate_id))
    if foreign_evidence:
        out.append(f"{foreign_evidence} facts about other subjects cite this person's documents")
    jobs = session.scalars(select(Job.id).where(Job.source_document_id.in_(doc_ids))).all()
    out += [f"job {j} was created from one of this person's documents" for j in jobs]
    return out


def erase_candidate(session: Session, blobs: BlobStore, org_id: uuid.UUID, candidate_id: uuid.UUID, actor: str,
                    reason: str | None = None) -> Erasure:
    person = session.get(Candidate, candidate_id)
    if person is None or person.org_id != org_id:
        raise LookupError(f"No candidate {candidate_id}")
    doc_ids = _documents_of(session, candidate_id)
    conflicts = _conflicts(session, candidate_id, doc_ids)
    if conflicts:
        raise ErasureConflict("; ".join(conflicts))

    claim_ids = list(session.scalars(select(Claim.id).where(Claim.subject_id == candidate_id)))
    identifiers = {
        (c.payload["kind"], c.payload["normalized"]) for c in session.scalars(select(Claim).where(
            Claim.id.in_(claim_ids), Claim.claim_type == "ContactClaim", Claim.status != "rejected"))
        if c.payload.get("kind") in KEY_KINDS
    }
    decision_ids = list(session.scalars(select(Decision.id).where(or_(
        Decision.subject_id == candidate_id,
        Decision.context["candidate_id"].astext == str(candidate_id)))))  # e.g. "same company?" cards raised by their CV
    run_ids = list(session.scalars(select(IntelligenceRun.id).where(IntelligenceRun.document_id.in_(doc_ids))))
    storage = {d.id: d.storage_key for d in session.scalars(select(Document).where(Document.id.in_(doc_ids)))}

    erasure = Erasure(org_id=org_id, subject_type="candidate", subject_id=candidate_id, requested_by=actor,
                      reason=reason, document_ids=[str(d) for d in doc_ids])
    session.add(erasure)
    session.flush()

    counts: dict[str, int] = {}

    def run(name: str, statement) -> None:
        counts[name] = session.execute(statement).rowcount or 0

    run("decision_items", delete(DecisionItem).where(or_(DecisionItem.decision_id.in_(decision_ids), DecisionItem.claim_id.in_(claim_ids))))
    run("decisions", delete(Decision).where(Decision.id.in_(decision_ids)))
    run("observations", delete(ClaimObservation).where(ClaimObservation.claim_id.in_(claim_ids)))
    run("evidence", delete(Evidence).where(or_(Evidence.claim_id.in_(claim_ids), Evidence.document_id.in_(doc_ids))))
    session.execute(update(Claim).where(Claim.superseded_by.in_(claim_ids)).values(superseded_by=None))
    run("claims", delete(Claim).where(Claim.id.in_(claim_ids)))
    pair_ids = select(CandidateJob.id).where(CandidateJob.candidate_id == candidate_id)
    # Pairs are permanent (a database trigger refuses deletes); erasure is the one exception, for this transaction only.
    session.execute(text("SET LOCAL maindscout.erasure = 'on'"))
    run("pair_history", delete(PairEvent).where(PairEvent.pair_id.in_(pair_ids)))
    run("pairs", delete(CandidateJob).where(CandidateJob.candidate_id == candidate_id))
    run("breakdown_snapshots", delete(Score).where(Score.candidate_id == candidate_id))
    run("not_same", delete(NotSame).where(or_(NotSame.candidate_a == candidate_id, NotSame.candidate_b == candidate_id)))
    run("document_links", delete(DocumentSubject).where(or_(DocumentSubject.subject_id == candidate_id, DocumentSubject.document_id.in_(doc_ids))))
    run("text_artifacts", delete(ExtractionArtifact).where(ExtractionArtifact.document_id.in_(doc_ids)))
    run("runs", delete(IntelligenceRun).where(IntelligenceRun.id.in_(run_ids)))
    run("documents", delete(Document).where(Document.id.in_(doc_ids)))
    session.execute(update(Candidate).where(Candidate.merged_into_id == candidate_id).values(merged_into_id=None))
    run("candidate", delete(Candidate).where(Candidate.id == candidate_id))

    # Pointers to this person inside other people's identity notes.
    mentions = 0
    for note in session.scalars(select(Decision).where(Decision.org_id == org_id, Decision.type == "identity_note")):
        ids = note.context.get("candidate_ids", [])
        if str(candidate_id) in ids:
            note.context = {**note.context, "candidate_ids": [i for i in ids if i != str(candidate_id)]}
            mentions += 1
    counts["mentions_removed"] = mentions

    session.flush()
    # Original bytes: delete unless another document row (e.g. another org) still uses the same stored file.
    deleted_blobs = 0
    for key in set(storage.values()):
        if not session.scalar(select(func.count()).select_from(Document).where(Document.storage_key == key)):
            blobs.delete(key)
            deleted_blobs += 1
    counts["files"] = deleted_blobs

    suppressed = 0
    for kind, normalized in identifiers:
        digest = identifier_hash(kind, normalized)
        if digest and not session.scalar(select(SuppressionEntry).where(
                SuppressionEntry.org_id == org_id, SuppressionEntry.identifier_hash == digest)):
            session.add(SuppressionEntry(org_id=org_id, identifier_hash=digest, reason="erased", erasure_id=erasure.id))
            suppressed += 1
    counts["suppressed_identifiers"] = suppressed
    if identifiers and not env("SUPPRESSION_KEY"):
        counts["suppression_skipped_no_key"] = len(identifiers)

    erasure.counts = counts
    session.flush()
    erasure.survivors = verify_erasure(session, blobs, org_id, candidate_id, storage_keys=list(storage.values()))
    erasure.verified_at = datetime.now(timezone.utc)
    session.flush()
    return erasure


def verify_erasure(session: Session, blobs: BlobStore, org_id: uuid.UUID, candidate_id: uuid.UUID,
                   storage_keys: list[str] | None = None) -> list[str]:
    """Look again, from scratch. Returns every survivor found; an empty list is the only green result."""
    record = session.scalar(select(Erasure).where(Erasure.org_id == org_id, Erasure.subject_id == candidate_id)
                            .order_by(Erasure.created_at.desc()))
    doc_ids = [uuid.UUID(d) for d in (record.document_ids if record else [])]
    sid = str(candidate_id)
    survivors: list[str] = []

    def count(model, *where) -> int:
        return session.scalar(select(func.count()).select_from(model).where(*where)) or 0

    checks = [
        ("candidate row", count(Candidate, Candidate.id == candidate_id)),
        ("claims", count(Claim, Claim.subject_id == candidate_id)),
        ("decisions", count(Decision, or_(Decision.subject_id == candidate_id, Decision.context["candidate_id"].astext == sid))),
        ("pairs", count(CandidateJob, CandidateJob.candidate_id == candidate_id)),
        ("breakdown snapshots", count(Score, Score.candidate_id == candidate_id)),
        ("document links", count(DocumentSubject, DocumentSubject.subject_id == candidate_id)),
        ("not-same records", count(NotSame, or_(NotSame.candidate_a == candidate_id, NotSame.candidate_b == candidate_id))),
        ("candidates redirected to this person", count(Candidate, Candidate.merged_into_id == candidate_id)),
    ]
    if doc_ids:
        checks += [
            ("documents", count(Document, Document.id.in_(doc_ids))),
            ("text artifacts", count(ExtractionArtifact, ExtractionArtifact.document_id.in_(doc_ids))),
            ("evidence citing the documents", count(Evidence, Evidence.document_id.in_(doc_ids))),
            ("runs over the documents", count(IntelligenceRun, IntelligenceRun.document_id.in_(doc_ids))),
        ]
    survivors += [f"{n} {what}" for what, n in checks if n]

    notes = [d for d in session.scalars(select(Decision).where(Decision.org_id == org_id, Decision.type == "identity_note"))
             if sid in d.context.get("candidate_ids", [])]
    if notes:
        survivors.append(f"{len(notes)} identity notes on other people still point to this person")

    for key in storage_keys or []:
        if blobs.exists(key) and not count(Document, Document.storage_key == key):
            survivors.append(f"original file {key} is still stored")

    # The same human may exist twice (a false split). If another person carries one of the erased
    # identifiers, they were not erased: say so instead of reporting green.
    if record:
        hashes = set(session.scalars(select(SuppressionEntry.identifier_hash).where(SuppressionEntry.erasure_id == record.id)))
        if hashes:
            for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.claim_type == "ContactClaim")):
                if identifier_hash(c.payload.get("kind", ""), c.payload.get("normalized", "")) in hashes:
                    survivors.append(f"another person ({c.subject_id}) has one of the erased identifiers")
    return survivors
