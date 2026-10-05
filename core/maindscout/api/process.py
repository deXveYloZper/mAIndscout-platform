"""process_document: read a stored document into proposed claims and commit them in one transaction.

intelligence/ proposes (pure); this module is the only writer. Nothing here makes anything official:
claims are written as `proposed`, and an approved view only ever changes through a human act.
The caller owns the transaction: this flushes, the caller commits (or rolls everything back).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import documents, erasure, writer
from maindscout.db.models import (
    Candidate,
    CandidateJob,
    Claim,
    ClaimObservation,
    Decision,
    DecisionItem,
    Document,
    DocumentSubject,
    Evidence,
    ExtractionArtifact,
    IntelligenceRun,
    Job,
    PairEvent,
    Score,
)
from maindscout.domain import stints
from maindscout.intelligence import contacts, extract, triage
from maindscout.intelligence.llm import LLMClient
from maindscout.storage import BlobStore

LIVE = ("proposed", "approved")
PRIORITY = {"identity_note": 100, "contradiction": 60, "duplicate_stint": 50, "revision_diff": 40}


@dataclass
class ProcessResult:
    run_id: uuid.UUID
    document_id: uuid.UUID
    status: str  # committed | needs_human | suppressed (an erased person; the upload was deleted)
    subject_type: str | None = None
    subject_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    band: str | None = None
    reason: str | None = None
    claim_ids: list[uuid.UUID] = field(default_factory=list)
    decision_ids: list[uuid.UUID] = field(default_factory=list)
    span_failures: list[dict[str, str]] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)
    reused: bool = False


def _manifest(client: LLMClient) -> dict[str, str]:
    return {
        "prompt_version": extract.PROMPT_VERSION,
        "model_version": client.model,
        "ontology_version": extract.ONTOLOGY_VERSION,
        "rubric_version": extract.RUBRIC_VERSION,
    }


def _d(iso: str | None) -> date | None:
    return date.fromisoformat(iso) if iso else None


def _norm_name(name: str) -> str:
    return " ".join(name.lower().split())


def _decision(session: Session, org_id, type_: str, subject_type: str, subject_id, context: dict, claim_ids: list,
              job_id=None) -> Decision:
    decision = Decision(org_id=org_id, type=type_, priority=PRIORITY[type_], subject_type=subject_type,
                        subject_id=subject_id, job_id=job_id, context=context)
    session.add(decision)
    session.flush()
    for role, claim_id in claim_ids:
        session.add(DecisionItem(org_id=org_id, decision_id=decision.id, claim_id=claim_id, role=role))
    session.flush()
    return decision


def natural_key(subject_id, claim_type: str, p: dict, valid_from: str | None = None, valid_to: str | None = None) -> str:
    """Deduplication key per claim_type_registry.yaml. Same key = same fact, seen again."""
    sid = subject_id
    if claim_type == "IdentityClaim":
        return f"{sid}|{_norm_name(p['full_name'])}"
    if claim_type == "ContactClaim":
        return f"{sid}|{p['kind']}|{p['normalized']}"
    if claim_type == "CareerStepClaim":
        return f"{sid}|{stints.normalize_company(p['company']['raw_name'])}|{valid_from or ''}|{valid_to or 'open'}"
    if claim_type == "EducationClaim":
        return f"{sid}|edu|{_norm_name(p['institution_raw'])}|{valid_from or ''}"
    if claim_type == "SkillClaim":
        return f"{sid}|{p['normalized_skill']}"
    if claim_type == "LocationClaim":
        return f"{sid}|{_norm_name(p['place_raw'])}|{p['basis']}"
    if claim_type == "JobRequirementClaim":
        if p["category"] in ("role", "employer", "domain", "target_company", "employment"):
            from maindscout.api.hiring import key_for

            return key_for(sid, p)
        return f"{sid}|{p['category']}|{p.get('normalized_token') or _norm_name(p['text_raw'])}"
    if claim_type == "StepClassificationClaim":
        return f"{p['career_claim_id']}|class"
    if claim_type == "BriefAnswerClaim":
        return f"{sid}|answer|{p['topic']}|{p.get('job_id') or ''}"
    raise ValueError(f"No natural key for {claim_type}")


# --- writing one claim --------------------------------------------------------------------------


def _write_claim(session: Session, doc: Document, run: IntelligenceRun, subject_type: str, subject_id: uuid.UUID,
                 claim_type: str, payload: dict, natural_key: str, span: dict | None, *, valid_from=None, valid_to=None,
                 precision="unknown", origin="candidate", authority="candidate_authored", flags=None, note=None
                 ) -> tuple[Claim, bool]:
    """Add a claim, or add a new observation to the live claim with the same natural key."""
    existing = session.scalar(
        select(Claim).where(
            Claim.org_id == doc.org_id, Claim.subject_type == subject_type, Claim.subject_id == subject_id,
            Claim.claim_type == claim_type, Claim.natural_key == natural_key, Claim.status.in_(LIVE),
        )
    )
    created = existing is None
    if created:
        claim = writer.add_claim(
            session, org_id=doc.org_id, subject_type=subject_type, subject_id=subject_id, claim_type=claim_type,
            payload=payload, flags=flags or {}, natural_key=natural_key, status="proposed", run_id=run.id,
            valid_from=_d(valid_from), valid_to=_d(valid_to), temporal_precision=precision, observed_as_of=doc.as_of,
        )
    else:
        claim = existing
        # A later file that casts doubt on a contact still awaiting review flags it (an approved one was decided by a
        # person and stays as it is).
        if flags and flags.get("possible_ocr_identifier") and claim.status == "proposed"                 and not claim.flags.get("possible_ocr_identifier"):
            writer.set_flags(session, claim, {**claim.flags, "possible_ocr_identifier": True})
    evidence = Evidence(
        org_id=doc.org_id, claim_id=claim.id, evidence_type="document_span", document_id=doc.id,
        locator={k: span[k] for k in ("artifact_id", "page", "char_start", "char_end", "annotation_id") if k in span} if span else None,
        snippet=span["snippet"] if span else None,
        span_validation={"tier": "typed", "result": "pass", "metric_bucket": "hallucination_rate", "detail": note},
        source_authority=authority, origin=origin, observed_as_of=doc.as_of,
    )
    session.add(evidence)
    session.flush()
    session.add(ClaimObservation(
        org_id=doc.org_id, claim_id=claim.id, attribute_path=".", value=payload, evidence_id=evidence.id,
        source_authority=authority, origin=origin, observed_as_of=doc.as_of,
    ))
    session.flush()
    return claim, created


# --- people -------------------------------------------------------------------------------------


def _resolve_candidate(session: Session, org_id, outcome: extract.ExtractionOutcome) -> tuple[Candidate, dict | None]:
    """Match only on clean, attributable, subject-owned contacts (or ones a human approved).

    Anything less certain creates a new person. A name-only or conflicting match raises an
    identity_note for a human; it never merges.
    """
    keys = [
        (c.payload["kind"], c.payload["normalized"]) for c in outcome.staged
        if c.claim_type == "ContactClaim" and not c.flags.get("possible_ocr_identifier")
        and c.payload["kind"] in ("email", "phone", "linkedin")
        and c.payload["attributable"] and c.payload["attribution"] == "subject"
    ]
    matched: set[uuid.UUID] = set()
    for kind, normalized in keys:
        rows = session.scalars(
            select(Claim).where(
                Claim.org_id == org_id, Claim.claim_type == "ContactClaim", Claim.subject_type == "candidate",
                Claim.status.in_(LIVE), Claim.payload["normalized"].astext == normalized,
                Claim.payload["kind"].astext == kind,
            )
        )
        for row in rows:
            if row.flags.get("possible_ocr_identifier") and row.status != "approved":
                continue
            candidate = session.get(Candidate, row.subject_id)
            while candidate is not None and candidate.merged_into_id:
                candidate = session.get(Candidate, candidate.merged_into_id)
            if candidate is not None:
                matched.add(candidate.id)

    # A shared contact merges only when the names agree too: a recruiter's email or an agency phone printed on many
    # CVs must not fold different people into one. A name that differs (or cannot be read) asks a human instead.
    names = _names_of(session, org_id, matched)
    agreeing = {cid for cid in matched if any(contacts.same_name(outcome.full_name, n) for n in names.get(cid, []))}
    if len(matched) == 1 and agreeing:
        return session.get(Candidate, next(iter(matched))), None

    candidate = Candidate(org_id=org_id, name_variants=[outcome.full_name] if outcome.full_name else [])
    session.add(candidate)
    session.flush()
    note = None
    if len(matched) > 1:
        note = {"reason": "contacts match more than one existing person", "candidate_ids": sorted(map(str, matched))}
    elif matched:
        note = {"reason": "same email, phone or LinkedIn as an existing person, but not the same name" if outcome.full_name
                else "same email, phone or LinkedIn as an existing person, and no name could be read",
                "candidate_ids": sorted(map(str, matched))}
    elif outcome.full_name:
        pattern = _norm_name(outcome.full_name).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        same_name = session.scalars(
            select(Claim).where(
                Claim.org_id == org_id, Claim.claim_type == "IdentityClaim", Claim.status.in_(LIVE),
                Claim.subject_id != candidate.id, Claim.natural_key.like(f"%|{pattern}", escape="\\"),
            )
        )
        twins = sorted({str(c.subject_id) for c in same_name})
        if twins:
            note = {"reason": "same name as an existing person, no clean contact in common", "candidate_ids": twins}
    elif not outcome.full_name:
        note = {"reason": "no name could be read from this document", "candidate_ids": []}
    return candidate, note


def _names_of(session: Session, org_id, candidate_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Every live name (and name variant) of these people."""
    out: dict[uuid.UUID, list[str]] = {cid: [] for cid in candidate_ids}
    if not candidate_ids:
        return out
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.claim_type == "IdentityClaim",
                                                 Claim.status.in_(LIVE), Claim.subject_id.in_(candidate_ids))):
        out[c.subject_id].append((c.approved_view or c.payload)["full_name"])
    for person in session.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids))):
        out[person.id] += person.name_variants or []
    return out


def _live_claims(session: Session, org_id, subject_type: str, subject_id, claim_type: str) -> list[Claim]:
    return list(session.scalars(select(Claim).where(
        Claim.org_id == org_id, Claim.subject_type == subject_type, Claim.subject_id == subject_id,
        Claim.claim_type == claim_type, Claim.status.in_(LIVE))))


def _step(claim: Claim) -> dict[str, Any]:
    return {
        "id": str(claim.id), "company": claim.payload["company"]["raw_name"],
        "employment_type": claim.payload.get("employment_type") or "unknown",
        "valid_from": claim.valid_from.isoformat() if claim.valid_from else None,
        "valid_to": claim.valid_to.isoformat() if claim.valid_to else None,
    }


def _flag_careers(session: Session, org_id, candidate_id, run: IntelligenceRun, new_ids: set[uuid.UUID],
                  decisions: list[uuid.UUID]) -> None:
    careers = _live_claims(session, org_id, "candidate", candidate_id, "CareerStepClaim")
    # Same company + overlapping period across different documents: keep both, flag, ask a human.
    # Within one CV, two roles at one company that overlap are usually a promotion and are left alone; the same title
    # twice over overlapping dates is the same job written (or read) twice, so it is asked about too.
    def same_title(a: Claim, b: Claim) -> bool:
        return _norm_name(a.payload.get("title_raw") or "") == _norm_name(b.payload.get("title_raw") or "") != ""

    seen: set[frozenset] = set()
    for claim in (c for c in careers if c.id in new_ids):
        for other in careers:
            if other.id == claim.id or frozenset((claim.id, other.id)) in seen:
                continue
            within_run = other.run_id == run.id or other.id in new_ids
            if within_run and not same_title(claim, other):
                continue
            if stints.same_company_overlap(_step(claim), _step(other)):
                seen.add(frozenset((claim.id, other.id)))
                for target, partner in ((claim, other), (other, claim)):
                    writer.set_flags(session, target, {**target.flags, "possible_duplicate_stint": True})
                decision = _decision(
                    session, org_id, "duplicate_stint", "candidate", candidate_id,
                    {"company": claim.payload["company"]["raw_name"], "question": "same stint, or two?"},
                    [("option", claim.id), ("option", other.id)],
                )
                decisions.append(decision.id)
    # Different companies, genuinely overlapping employment: a flag on both, never a merge.
    partners: dict[str, list[str]] = {}
    for a, b in stints.concurrent_pairs([_step(c) for c in careers]):
        partners.setdefault(a, []).append(b)
    for claim in careers:
        found = sorted(set(partners.get(str(claim.id), [])))
        flags = {k: v for k, v in claim.flags.items() if k != "concurrency.overlap_with"}
        if found:
            flags["concurrency.overlap_with"] = found
        if flags != claim.flags:
            writer.set_flags(session, claim, flags)
    session.flush()


def _contradictions(session: Session, org_id, candidate_id, decisions: list[uuid.UUID]) -> None:
    """Two current places in different countries, stated as of the same date, cannot both be true.

    Different dates are temporal succession (the person moved): no card, the newer one is current.
    """
    places = [c for c in _live_claims(session, org_id, "candidate", candidate_id, "LocationClaim")
              if c.payload.get("kind", "current") == "current" and c.payload.get("country_code")]
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            if a.payload["country_code"] == b.payload["country_code"] or a.observed_as_of != b.observed_as_of:
                continue
            # Both approved still cannot both be true; picking one rejects the other, so the card does not come back.
            already = session.scalar(
                select(Decision.id).join(DecisionItem, DecisionItem.decision_id == Decision.id).where(
                    Decision.type == "contradiction", Decision.sealed_at.is_(None), DecisionItem.claim_id == a.id,
                    Decision.id.in_(select(DecisionItem.decision_id).where(DecisionItem.claim_id == b.id))))
            if already:
                continue
            decisions.append(_decision(session, org_id, "contradiction", "candidate", candidate_id,
                                       {"question": "which is the current location?"},
                                       [("left", a.id), ("right", b.id)]).id)


def pair_inputs(session: Session, org_id, candidate_id, job: Job) -> tuple[list[Claim], list[Claim]]:
    """Everything matching reads from the database: the job's live requirements and the person's live facts."""
    from maindscout.api.queries import live_requirements

    mine = list(session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id, Claim.status.in_(LIVE))))
    return live_requirements(session, job.id), mine


def _triage_now(session: Session, org_id, candidate_id, job: Job, inputs: tuple[list[Claim], list[Claim]] | None = None) -> triage.Triage:
    reqs, mine = inputs or pair_inputs(session, org_id, candidate_id, job)
    requirements = [c.payload for c in reqs]
    skills = [c.payload["normalized_skill"] for c in mine if c.claim_type == "SkillClaim"]
    titles = [c.payload["title_raw"] for c in mine if c.claim_type == "CareerStepClaim"]
    return triage.triage(requirements, skills, titles)


def _match_now(session: Session, org_id, candidate_id, job: Job, rows=None, coarse: triage.Triage | None = None,
               inputs: tuple[list[Claim], list[Claim]] | None = None):
    """Matching v2: the career profile against the hiring profile; token triage is rule 1 and the fallback.
    `inputs` (pair_inputs), `rows` (the gap table) and `coarse` (token triage) may be passed in when already known."""
    from maindscout.api import profiles
    from maindscout.api.queries import _gap_rows_many
    from maindscout.domain import matching

    inputs = inputs or pair_inputs(session, org_id, candidate_id, job)
    coarse = coarse or _triage_now(session, org_id, candidate_id, job, inputs)
    if rows is None:
        rows = _gap_rows_many(session, org_id, job, [candidate_id], with_snippets=False,
                              preloaded=(inputs[0], {candidate_id: inputs[1]}))[candidate_id]
    reqs = [{"id": str(c.id), "payload": c.approved_view or c.payload} for c in inputs[0] if c.payload.get("category") != "process"]
    snap = profiles.latest(session, candidate_id)
    stints, _ = profiles.inputs(session, org_id, candidate_id) if snap else ([], [])
    from maindscout.api.brief import answers_for
    from maindscout.api.pipeline import active_block

    block = active_block(session, org_id, job.id, candidate_id)
    return matching.match(reqs, rows, snap.profile if snap else None, stints,
                          (coarse.band, coarse.reason), answers_for(session, org_id, candidate_id),
                          blocked=block.reason if block is not None else None)


def snapshot_pair(session: Session, pair: CandidateJob, rows=None) -> Score | None:
    """Store what the machine considered for this pair (breakdown + coverage, never a value), only when it changed."""
    from maindscout.api.queries import _gap_rows_many
    from maindscout.domain import coverage

    if rows is None:
        rows = _gap_rows_many(session, pair.org_id, session.get(Job, pair.job_id), [pair.candidate_id], with_snippets=False)[pair.candidate_id]
    digest = coverage.claim_set_hash(rows)
    latest = session.scalar(select(Score.claim_set_hash).where(Score.candidate_id == pair.candidate_id, Score.job_id == pair.job_id)
                            .order_by(Score.computed_at.desc(), Score.id.desc()).limit(1))
    if latest == digest:
        return None
    score = Score(org_id=pair.org_id, candidate_id=pair.candidate_id, job_id=pair.job_id, value=None,
                  coverage=coverage.coverage(rows).as_dict(), breakdown=coverage.breakdown(rows),
                  claim_set_hash=digest, engine_version=coverage.ENGINE_VERSION)
    session.add(score)
    session.flush()
    return score


def retriage_pair(session: Session, pair: CandidateJob, cause: dict, actor: str = "system") -> PairEvent | None:
    """Recompute the band from live facts. Records a history event when it changes. A band set by hand stays.
    Either way, a new breakdown snapshot is stored if the facts behind the pair changed."""
    from maindscout.api.queries import _gap_rows_many

    job = session.get(Job, pair.job_id)
    inputs = pair_inputs(session, pair.org_id, pair.candidate_id, job)  # two queries; everything below is derived
    rows = _gap_rows_many(session, pair.org_id, job, [pair.candidate_id], with_snippets=False,
                          preloaded=(inputs[0], {pair.candidate_id: inputs[1]}))[pair.candidate_id]
    snapshot_pair(session, pair, rows)
    coarse = _triage_now(session, pair.org_id, pair.candidate_id, job, inputs)
    m = _match_now(session, pair.org_id, pair.candidate_id, job, rows, coarse, inputs)
    pair.match_tier, pair.match = m.tier, m.as_dict()  # kept up to date even when a person set the band
    if pair.band_overridden_by:
        session.flush()
        return None
    if m.band is None:  # unclear: the coarse band stands
        result = triage.Triage(coarse.band, coarse.reason)
    else:
        result = triage.Triage(m.band, m.reason)
    if (pair.triage_band, pair.triage_reason) == (result.band, result.reason):
        session.flush()
        return None
    old = pair.triage_band
    if old != "unassigned":
        pair.version = (pair.version or 1) + 1
    pair.triage_band, pair.triage_reason = result.band, result.reason
    event = PairEvent(org_id=pair.org_id, pair_id=pair.id, kind="band", from_value=old, to_value=result.band,
                      reason=result.reason, cause=cause, actor=actor)
    session.add(event)
    session.flush()
    return event


def retriage_candidate(session: Session, org_id, candidate_id, cause: dict, actor: str) -> list[PairEvent]:
    pairs = session.scalars(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.candidate_id == candidate_id))
    return [e for e in (retriage_pair(session, p, cause, actor) for p in pairs) if e]


INLINE_JOB_REMATCH = 40  # up to this many people, a job re-matches before the request returns (about 2 s)


def retriage_job(session: Session, org_id, job_id, cause: dict, actor: str) -> list[PairEvent]:
    pairs = session.scalars(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.job_id == job_id))
    return [e for e in (retriage_pair(session, p, cause, actor) for p in pairs) if e]


def rematch_job(session: Session, org_id, job_id, cause: dict, actor: str) -> dict[str, Any]:
    """A change to a job's requirements: re-match everyone on it. Small jobs at once; bigger ones in the background
    (matching takes about 0.1 s a person, so 600 people would hold the request for a minute)."""
    from sqlalchemy import func

    from maindscout.api import tasks

    n = session.scalar(select(func.count()).select_from(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.job_id == job_id)) or 0
    if n <= INLINE_JOB_REMATCH:
        return {"rematched": len(retriage_job(session, org_id, job_id, cause, actor)), "background": False}
    task = tasks.enqueue(session, org_id, "rematch_job", {"job_id": str(job_id), "cause": cause, "actor": actor},
                         priority=40, dedupe_key=f"rematch:{job_id}")
    return {"people": n, "background": True, "task_id": str(task.id)}


def rematching(session: Session, job_id) -> bool:
    from maindscout.db.models import Task

    return session.scalar(select(Task.id).where(Task.dedupe_key == f"rematch:{job_id}", Task.status.in_(("queued", "running"))).limit(1)) is not None


def _ensure_pair(session: Session, org_id, candidate_id, job: Job, cause: dict | None = None) -> CandidateJob:
    pair = session.scalar(select(CandidateJob).where(CandidateJob.candidate_id == candidate_id, CandidateJob.job_id == job.id))
    if pair is None:
        pair = CandidateJob(org_id=org_id, candidate_id=candidate_id, job_id=job.id)
        session.add(pair)
        session.flush()
    retriage_pair(session, pair, cause or {"act": "document_processed"}, "system")
    from maindscout.api import coverage

    coverage.evaluate(session, org_id, candidate_id, cause or {"act": "document_processed"})
    return pair


# --- entry point --------------------------------------------------------------------------------


def process_document(session: Session, blobs: BlobStore, client: LLMClient, *, org_id: uuid.UUID,
                     document_id: uuid.UUID, job_id: uuid.UUID | None = None, force: bool = False,
                     as_of: date | None = None) -> ProcessResult:
    """`as_of` overrides the document's own date (used by the golden eval to pin "today")."""
    doc = session.get(Document, document_id)
    if doc is None or doc.org_id != org_id:
        raise LookupError(f"No document {document_id}")
    artifact = documents.extract_document(session, blobs, doc.id, refresh=force)
    if as_of is not None:
        doc.as_of, doc.as_of_basis = as_of, "override"

    prior = session.scalar(select(IntelligenceRun).where(
        IntelligenceRun.document_id == doc.id, IntelligenceRun.status == "committed").order_by(IntelligenceRun.created_at.desc()))
    if prior and not force:
        return _again(session, doc, prior, job_id)

    job = session.get(Job, job_id) if job_id else None
    if job_id and (job is None or job.org_id != org_id):
        raise LookupError(f"No job {job_id}")
    if job is None and doc.doc_type == "jd":
        # Re-reading an ad updates the job it already created; it never makes a second job.
        job = session.scalar(select(Job).where(Job.source_document_id == doc.id, Job.org_id == org_id))

    from maindscout.api import costs

    costs.ensure_budget(session, org_id)
    run = IntelligenceRun(org_id=org_id, document_id=doc.id, version_manifest=_manifest(client), status="running")
    session.add(run)
    session.flush()

    if doc.doc_type == "jd":
        result = _process_jd(session, doc, artifact, run, client, job, forced=force and prior is not None)
    elif doc.doc_type == "cv":
        result = _process_cv(session, blobs, doc, artifact, run, client, job, forced=force and prior is not None)
        if result.status == "suppressed":
            session.flush()
            return result
    else:
        run.status = "failed"
        run.version_manifest = {**run.version_manifest, "reason": "doc_type must be cv or jd"}
        doc.status = "needs_human"
        session.flush()
        return ProcessResult(run.id, doc.id, "needs_human")

    if result.cost:
        costs.record(session, org_id, "read_jd" if doc.doc_type == "jd" else "read_cv", result.cost,
                     subject_type="document", subject_id=doc.id)
    run.status, run.committed_at = "committed", datetime.now(timezone.utc)
    run.version_manifest = {**run.version_manifest, "span_failures": result.span_failures, "cost": result.cost,
                            "result": {"subject_type": result.subject_type, "subject_id": str(result.subject_id),
                                       "job_id": str(result.job_id) if result.job_id else None}}
    doc.status, doc.last_processed_with = "processed", _manifest(client)
    session.flush()
    return result


def _again(session: Session, doc: Document, prior: IntelligenceRun, job_id: uuid.UUID | None) -> ProcessResult:
    """Already processed. Return the earlier outcome; if a job is given, only (re)triage the pair."""
    info = prior.version_manifest.get("result", {})
    result = ProcessResult(prior.id, doc.id, "committed", info.get("subject_type"),
                           uuid.UUID(info["subject_id"]) if info.get("subject_id") not in (None, "None") else None,
                           reused=True)
    if job_id and result.subject_type == "candidate":
        job = session.get(Job, job_id)
        if job is None or job.org_id != doc.org_id:
            raise LookupError(f"No job {job_id}")
        pair = _ensure_pair(session, doc.org_id, result.subject_id, job)
        result.job_id, result.band, result.reason = job.id, pair.triage_band, pair.triage_reason
    return result


def _retire_earlier_reading(session: Session, doc: Document, run: IntelligenceRun, kept: set[uuid.UUID]) -> int:
    """After a forced re-read, the machine's earlier proposals from this same document that the new reading
    did not find again are superseded. Only `proposed` claims whose every piece of evidence is this document;
    anything approved, or also supported by another source, is left alone."""
    retired = 0
    candidates = session.scalars(
        select(Claim).join(Evidence, Evidence.claim_id == Claim.id).where(
            Evidence.document_id == doc.id, Claim.status == "proposed", Claim.run_id != run.id).distinct())
    for claim in candidates:
        if claim.id in kept:
            continue
        sources = set(session.scalars(select(Evidence.document_id).where(Evidence.claim_id == claim.id)))
        if sources == {doc.id}:
            claim.status = "superseded"
            retired += 1
    session.flush()
    return retired


def _queue_research(session: Session, candidate_id, org_id) -> int:
    """Queue company research for the stints that matter: the last 10 years, at least 6 months or still current.
    Shared public work (no org); deduplicated per company; skipped while a company's facts are fresh."""
    from maindscout.api import research, tasks
    from maindscout.db.models import Company
    from maindscout.settings import env

    if (env("RESEARCH_AUTO", "true") or "").lower() in ("0", "false", "no", "off"):
        return 0
    horizon = date.today().replace(year=date.today().year - 10)
    queued = 0
    for c in _live_claims(session, org_id, "candidate", candidate_id, "CareerStepClaim"):
        company_id = (c.payload.get("company") or {}).get("company_id")
        if not company_id:
            continue
        end = c.valid_to or date.today()
        long_enough = c.valid_to is None or (c.valid_from and (end - c.valid_from).days >= 180)
        if end < horizon or not long_enough:
            continue
        company = session.get(Company, uuid.UUID(company_id))
        if company is None or not research.due(company):
            continue
        tasks.enqueue(session, None, "research_company",
                      {"company_id": company_id,
                       "context": research.context_for_step(c.payload["company"]["raw_name"], c.payload.get("location_raw"))},
                      priority=150, dedupe_key=f"research:{company_id}")
        queued += 1
    return queued


def _span_failures(results) -> list[dict[str, str]]:
    return [{"client_key": r.client_key, "detail": r.detail or ""} for r in results if r.result == "fail"]


def _discard_suppressed(session: Session, blobs: BlobStore, doc: Document, run: IntelligenceRun) -> ProcessResult:
    """Delete the upload of an erased person. Only the fact that an upload was blocked is kept."""
    from sqlalchemy import delete, func

    session.execute(delete(ExtractionArtifact).where(ExtractionArtifact.document_id == doc.id))
    run.status = "failed"
    run.document_id = None
    run.version_manifest = {k: v for k, v in run.version_manifest.items() if k.endswith("_version")} | {"reason": "suppressed"}
    key, doc_id = doc.storage_key, doc.id
    session.delete(doc)
    session.flush()
    if not session.scalar(select(func.count()).select_from(Document).where(Document.storage_key == key)):
        blobs.delete(key)
    return ProcessResult(run.id, doc_id, "suppressed")


def _process_cv(session: Session, blobs: BlobStore, doc: Document, artifact: ExtractionArtifact, run: IntelligenceRun,
                client: LLMClient, job: Job | None, forced: bool = False) -> ProcessResult:
    outcome = extract.extract_cv(artifact.content, artifact.id, artifact.annotations or [], client)
    # Suppression first: a person who was erased is not ingested again. Nothing about them is kept.
    identifiers = [(c.payload["kind"], c.payload["normalized"]) for c in outcome.staged if c.claim_type == "ContactClaim"]
    entry = erasure.is_suppressed(session, doc.org_id, identifiers)
    if entry is not None:
        erasure.record_encounter(entry)
        return _discard_suppressed(session, blobs, doc, run)
    candidate, note = _resolve_candidate(session, doc.org_id, outcome)
    cid = candidate.id
    claim_ids: list[uuid.UUID] = []
    decisions: list[uuid.UUID] = []
    new_careers: set[uuid.UUID] = set()
    authority = doc.source_authority
    run_keys: set[str] = set()

    from maindscout.api import companies

    for s in outcome.staged:
        p = s.payload
        if s.claim_type == "CareerStepClaim":
            company, parsed = companies.resolve(session, p["company"]["raw_name"], "cv", doc.org_id, cid)
            p = {**p, "company": {**p["company"], "company_id": str(company.id) if company else None}}
            if parsed.kind == "self_employed" and p.get("employment_type") not in ("contract", "consulting", "side"):
                p["employment_type"] = "contract"  # self-employment is not employment: read it as contracting
        key = natural_key(cid, s.claim_type, p, s.valid_from, s.valid_to)
        # Two entries in one document that share a key are still two entries: never fuse them.
        base, n = key, 1
        while key in run_keys:
            n += 1
            key = f"{base}|dup{n}"
        run_keys.add(key)
        claim, created = _write_claim(
            session, doc, run, "candidate", cid, s.claim_type, p, key, s.span, valid_from=s.valid_from,
            valid_to=s.valid_to, precision=s.temporal_precision, origin=s.origin, authority=authority, flags=s.flags,
            note=s.note)
        claim_ids.append(claim.id)
        if created and s.claim_type == "CareerStepClaim":
            new_careers.add(claim.id)
        if not created and claim.status == "approved" and claim.approved_view:
            if stints.reconcile.view_hash(claim.approved_view) != stints.reconcile.view_hash(p):
                decisions.append(_decision(
                    session, doc.org_id, "revision_diff", "candidate", cid,
                    {"old_view": claim.approved_view, "new_view": p, "claim_id": str(claim.id)},
                    [("current", claim.id)]).id)

    if forced:
        _retire_earlier_reading(session, doc, run, set(claim_ids))
    _flag_careers(session, doc.org_id, cid, run, new_careers, decisions)
    _contradictions(session, doc.org_id, cid, decisions)

    if note:
        decisions.append(_decision(session, doc.org_id, "identity_note", "candidate", cid, note, []).id)

    if session.get(DocumentSubject, (doc.id, "candidate", cid)) is None:
        session.add(DocumentSubject(document_id=doc.id, subject_type="candidate", subject_id=cid, org_id=doc.org_id,
                                    established_by="extraction"))
    # The coverage gate runs once the person is on their job (a job may accept more countries); it queues company
    # research only for people in coverage.
    pair = _ensure_pair(session, doc.org_id, cid, job) if job else None
    if pair is None:
        from maindscout.api import coverage

        coverage.evaluate(session, doc.org_id, cid, {"act": "document_processed"})
    session.flush()
    return ProcessResult(
        run.id, doc.id, "committed", "candidate", cid, job.id if job else None,
        pair.triage_band if pair else None, pair.triage_reason if pair else None,
        claim_ids, decisions, _span_failures(outcome.span_results), outcome.cost)


def _process_jd(session: Session, doc: Document, artifact: ExtractionArtifact, run: IntelligenceRun,
                client: LLMClient, job: Job | None, forced: bool = False) -> ProcessResult:
    outcome = extract.extract_jd(artifact.content, artifact.id, client, doc.as_of)
    if job is None:
        job = Job(org_id=doc.org_id, title=outcome.title or (doc.filename or "Untitled job").rsplit(".", 1)[0])
        session.add(job)
    if outcome.hiring_company:
        from maindscout.api import companies

        job.hiring_company = outcome.hiring_company
        company, _ = companies.resolve(session, outcome.hiring_company, "jd")
        job.hiring_company_id = company.id if company else None
        if company is not None:
            from maindscout.api import research, tasks
            from maindscout.settings import env

            if research.due(company) and (env("RESEARCH_AUTO", "true") or "").lower() not in ("0", "false", "no", "off"):
                tasks.enqueue(session, None, "research_company",
                              {"company_id": str(company.id), "context": f"hiring for '{job.title}' (from a job advertisement)"},
                              priority=80, dedupe_key=f"research:{company.id}")
    job.source_document_id = doc.id
    session.flush()

    claim_ids: list[uuid.UUID] = []
    for r in outcome.requirements:
        p = r.payload
        key = natural_key(job.id, "JobRequirementClaim", p)
        claim, _ = _write_claim(session, doc, run, "job", job.id, "JobRequirementClaim", p, key, r.span,
                                origin="employer", authority="employer_authored")
        claim_ids.append(claim.id)
    for label, iso, assumed in outcome.process_dates:
        stale = doc.as_of is not None and date.fromisoformat(iso) < doc.as_of
        payload = {"text_raw": label, "category": "process", "strength": "unknown", "normalized_token": iso,
                   "distinctive": False}
        claim, _ = _write_claim(session, doc, run, "job", job.id, "JobRequirementClaim", payload,
                                f"{job.id}|process|{iso}", None, origin="employer", authority="employer_authored",
                                flags={"job_process_stale": True} if stale else None,
                                note="year not written; taken from the document date" if assumed else None)
        claim_ids.append(claim.id)

    if forced:
        _retire_earlier_reading(session, doc, run, set(claim_ids))
    if session.get(DocumentSubject, (doc.id, "job", job.id)) is None:
        session.add(DocumentSubject(document_id=doc.id, subject_type="job", subject_id=job.id, org_id=doc.org_id,
                                    established_by="extraction"))
    session.flush()
    if forced:
        from maindscout.api import coverage

        coverage.reevaluate_job(session, job, {"act": "job_read_again"})  # the ad may name other countries now
    from maindscout.api import hiring

    hiring.queue(session, job)  # role, employment, background asks: one more read of the ad, in the background
    return ProcessResult(run.id, doc.id, "committed", "job", job.id, job.id, None, None, claim_ids, [],
                         _span_failures(outcome.span_results), outcome.cost)
