"""Slice 0 tables (unpartitioned). Shape follows 01-system-blueprint section D, trimmed to Slice 0.

Every table carries org_id. Only maindscout.api may write to these tables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


DOC_TYPES = ("cv", "jd", "other")
DOC_STATUS = ("received", "stored", "extracted", "processed", "needs_human", "reprocessable")
SOURCE_AUTHORITY = (
    "verified_primary",
    "human_assertion",
    "candidate_authored",
    "employer_authored",
    "third_party_assertion",
    "web_inference",
)
ORIGINS = ("candidate", "employer", "registry", "independent_web", "human", "relayed", "unknown")
SUBJECT_TYPES = ("candidate", "company", "job")
CLAIM_CLASS = ("observed", "inferred", "computed")
CLAIM_STATUS = ("staged", "proposed", "approved", "rejected", "superseded")
PRECISION = ("exact", "month", "year_only", "ordered_only", "unknown")
VERIFIABILITY = ("registry", "public_record", "scholarly", "web", "unverifiable")
TRIAGE_BANDS = ("priority", "review_later", "do_not_submit", "unassigned")
RUN_STATUS = ("running", "committed", "failed")
DECISION_TYPES = ("revision_diff", "duplicate_stint", "contradiction", "identity_note")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("org.id"), nullable=False)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --- registries (seeded from slice0/registry/*.yaml) -------------------------------------


class ClaimTypeRegistry(Base):
    __tablename__ = "claim_type_registry"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    claim_class: Mapped[str] = mapped_column(String, nullable=False)
    subject_types: Mapped[list] = mapped_column(JSONB, nullable=False)
    natural_key: Mapped[str | None] = mapped_column(Text)
    volatility: Mapped[str | None] = mapped_column(String)
    default_review: Mapped[str | None] = mapped_column(String)
    payload_schema: Mapped[str | None] = mapped_column(String)


class FlagTypeRegistry(Base):
    __tablename__ = "flag_type_registry"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    default_severity: Mapped[str] = mapped_column(String, nullable=False)
    brief_template: Mapped[str | None] = mapped_column(Text)
    blocks_auto_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocks_matching: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_subject_types: Mapped[list] = mapped_column(JSONB, nullable=False)


# --- tenancy and documents ---------------------------------------------------------------


class Org(Base):
    __tablename__ = "org"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created()


class Document(Base):
    """Immutable bytes live in the blob store under storage_key; this row describes them."""

    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("org_id", "sha256"),
        CheckConstraint(_in("doc_type", DOC_TYPES), name="document_doc_type"),
        CheckConstraint(_in("status", DOC_STATUS), name="document_status"),
        CheckConstraint(_in("source_authority", SOURCE_AUTHORITY), name="document_authority"),
    )
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str | None] = mapped_column(String)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False, default="other")
    source_authority: Mapped[str] = mapped_column(String, nullable=False, default="candidate_authored")
    transformed_by_third_party: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str | None] = mapped_column(String)
    as_of: Mapped[date | None] = mapped_column(Date)
    as_of_basis: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="stored")
    needs_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_processed_with: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()


class ExtractionArtifact(Base):
    """The text layer a document was read as. Evidence locators point here, never at raw bytes."""

    __tablename__ = "extraction_artifact"
    __table_args__ = (CheckConstraint(_in("method", ("text_layer", "vision")), name="artifact_method"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id"), nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False, default="text_layer")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    annotations: Mapped[list | None] = mapped_column(JSONB)
    content_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    produced_with: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()


class DocumentSubject(Base):
    """Who a document is about. Erasure depends on this."""

    __tablename__ = "document_subject"
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id"), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String, primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    segment_locator: Mapped[dict | None] = mapped_column(JSONB)
    established_by: Mapped[str] = mapped_column(String, nullable=False)


# --- entities ----------------------------------------------------------------------------


class Candidate(Base):
    __tablename__ = "candidate"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    name_variants: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate.id"))  # redirect, never rewrite
    created_at: Mapped[datetime] = _created()


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (CheckConstraint(_in("state", ("open", "on_hold", "filled", "cancelled")), name="job_state"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    title: Mapped[str] = mapped_column(String, nullable=False)
    hiring_company: Mapped[str | None] = mapped_column(String)  # plain text in Slice 0; no company entity yet
    state: Mapped[str] = mapped_column(String, nullable=False, default="open")
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document.id"))
    created_at: Mapped[datetime] = _created()


class CandidateJob(Base):
    """A pair is permanent: created once, moved, never deleted. The band is not a score."""

    __tablename__ = "candidate_job"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id"),
        CheckConstraint(_in("triage_band", TRIAGE_BANDS), name="pair_band"),
    )
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate.id"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"), nullable=False)
    triage_band: Mapped[str] = mapped_column(String, nullable=False, default="unassigned")
    triage_reason: Mapped[str | None] = mapped_column(String)
    band_overridden_by: Mapped[str | None] = mapped_column(String)
    pair_state: Mapped[str] = mapped_column(String, nullable=False, default="matched")
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_job.id"))
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = _created()


class NotSame(Base):
    """Rejected SameAs: two candidates a human said are different people."""

    __tablename__ = "not_same"
    __table_args__ = (CheckConstraint("candidate_a < candidate_b", name="not_same_ordered"),)
    candidate_a: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate.id"), primary_key=True)
    candidate_b: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate.id"), primary_key=True)
    org_id: Mapped[uuid.UUID] = _org()
    created_at: Mapped[datetime] = _created()


# --- runs, claims, evidence --------------------------------------------------------------


class IntelligenceRun(Base):
    __tablename__ = "intelligence_run"
    __table_args__ = (CheckConstraint(_in("status", RUN_STATUS), name="run_status"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document.id"))
    trigger: Mapped[str] = mapped_column(String, nullable=False, default="process_document")
    version_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Claim(Base):
    __tablename__ = "claim"
    __table_args__ = (
        CheckConstraint(_in("subject_type", SUBJECT_TYPES), name="claim_subject_type"),
        CheckConstraint(_in("class", CLAIM_CLASS), name="claim_class"),
        CheckConstraint(_in("status", CLAIM_STATUS), name="claim_status"),
        CheckConstraint(_in("temporal_precision", PRECISION), name="claim_precision"),
        Index("ix_claim_subject", "org_id", "subject_type", "subject_id"),
        Index("ix_claim_natural_key", "org_id", "claim_type", "natural_key"),
    )
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    claim_type: Mapped[str] = mapped_column(ForeignKey("claim_type_registry.key"), nullable=False)
    claim_class: Mapped[str] = mapped_column("class", String, nullable=False, default="observed")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    natural_key: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    temporal_precision: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    verifiability: Mapped[str | None] = mapped_column(String)
    flags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="staged")
    approved_view: Mapped[dict | None] = mapped_column(JSONB)  # pinned at approval; never mutated
    approved_view_hash: Mapped[str | None] = mapped_column(String)
    approved_by: Mapped[str | None] = mapped_column(String)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[dict | None] = mapped_column(JSONB)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("intelligence_run.id"))
    observed_as_of: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claim.id"))
    created_at: Mapped[datetime] = _created()


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(_in("source_authority", SOURCE_AUTHORITY), name="evidence_authority"),
        CheckConstraint(_in("origin", ORIGINS), name="evidence_origin"),
    )
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String, nullable=False, default="document_span")
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document.id"))
    locator: Mapped[dict | None] = mapped_column(JSONB)  # -> extraction_artifact
    snippet: Mapped[str | None] = mapped_column(Text)
    span_validation: Mapped[dict | None] = mapped_column(JSONB)
    source_authority: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    observed_as_of: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created()


class ClaimObservation(Base):
    """Per-source values for a keyed claim. The reconciled view is a pure function over these."""

    __tablename__ = "claim_observation"
    __table_args__ = (
        CheckConstraint(_in("source_authority", SOURCE_AUTHORITY), name="obs_authority"),
        CheckConstraint(_in("origin", ORIGINS), name="obs_origin"),
    )
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), nullable=False)
    attribute_path: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence.id"))
    source_authority: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    observed_as_of: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _created()


# --- review ------------------------------------------------------------------------------


class Decision(Base):
    __tablename__ = "decision"
    __table_args__ = (CheckConstraint(_in("type", DECISION_TYPES), name="decision_type"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False, default=0)
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job.id"))
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()


class DecisionItem(Base):
    __tablename__ = "decision_item"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision.id"), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # e.g. current, proposed, option
    outcome: Mapped[str | None] = mapped_column(String)  # approved | rejected | kept | null while open


# --- erasure ------------------------------------------------------------------------------------


class Erasure(Base):
    """Record that a person was erased. Holds no personal data: ids, counts and the outcome only."""

    __tablename__ = "erasure"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)  # no FK: the row is gone
    requested_by: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    survivors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class SuppressionEntry(Base):
    """Keyed hash of an erased person's identifier. Blocks re-ingesting them; cannot be reversed to the identifier."""

    __tablename__ = "suppression_registry"
    __table_args__ = (UniqueConstraint("org_id", "identifier_hash"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    erasure_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("erasure.id"))
    encounters: Mapped[int] = mapped_column(nullable=False, default=0)  # later uploads blocked by this entry
    last_encounter_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


# --- pair history -------------------------------------------------------------------------------


class PairEvent(Base):
    """Append-only history of a person-job pair: every band change (and, from Slice 1 step 4, every state change),
    with what caused it and who. Never updated, never deleted except by erasure of the person."""

    __tablename__ = "pair_event"
    __table_args__ = (Index("ix_pair_event_pair", "pair_id", "created_at"),)
    id: Mapped[uuid.UUID] = _pk()
    # Order of events: timestamps tie inside one transaction, a sequence never does.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    org_id: Mapped[uuid.UUID] = _org()
    pair_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_job.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # band | state
    from_value: Mapped[str | None] = mapped_column(String)
    to_value: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    cause: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # e.g. {"act": "approve", "claim_id": ...}
    actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created()
