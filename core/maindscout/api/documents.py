"""Document writes: store the original, then read its text layer. Extraction does not make claims."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from maindscout.db.models import DOC_TYPES, Document, ExtractionArtifact
from maindscout.ingestion import pdf
from maindscout.storage import BlobStore


def _annotation_dict(a: pdf.Annotation) -> dict:
    return {"page": a.page, "kind": a.kind, "uri": a.uri}


def lock_bytes(session: Session, sha: str) -> None:
    """Serialise storing and deleting the same bytes (shared across orgs) until this transaction ends, so an erasure
    never deletes a file another upload is just starting to use."""
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"blob:{sha}"})


def upload_document(
    session: Session,
    blobs: BlobStore,
    *,
    org_id: uuid.UUID,
    data: bytes,
    filename: str | None,
    media_type: str,
    doc_type_hint: str = "other",
) -> tuple[Document, bool]:
    """Store bytes and describe them. Returns (document, reused). Same bytes in one org are stored once."""
    if doc_type_hint not in DOC_TYPES:
        raise ValueError(f"doc_type_hint must be one of {DOC_TYPES}")
    sha = hashlib.sha256(data).hexdigest()
    lock_bytes(session, sha)
    existing = session.scalar(select(Document).where(Document.org_id == org_id, Document.sha256 == sha))
    if existing:
        return existing, True
    document = Document(
        org_id=org_id,
        sha256=sha,
        storage_key=blobs.put(sha, data),
        filename=filename,
        media_type=media_type,
        doc_type=doc_type_hint,
        status="stored",
    )
    session.add(document)
    session.flush()
    return document, False


def extract_document(session: Session, blobs: BlobStore, document_id: uuid.UUID, refresh: bool = False) -> ExtractionArtifact:
    """Read the text layer once; later calls return the same artifact. With `refresh` (a forced re-read), a PDF read
    before the current text repairs is read again and its artifact updated in place."""
    document = session.get(Document, document_id)
    if document is None:
        raise LookupError(f"No document {document_id}")
    existing = session.scalar(
        select(ExtractionArtifact).where(
            ExtractionArtifact.document_id == document_id, ExtractionArtifact.method == "text_layer"
        )
    )
    stale = (existing is not None and refresh and document.media_type == "application/pdf"
             and (existing.produced_with or {}).get("text_repair") != pdf.TEXT_REPAIR_VERSION)
    if existing and not stale:
        return existing

    result = pdf.extract(blobs.get(document.storage_key), document.media_type)
    if stale:
        existing.content, existing.annotations = result.text, [_annotation_dict(a) for a in result.annotations]
        existing.content_sha = hashlib.sha256(result.text.encode("utf-8")).hexdigest()
        existing.produced_with = {**result.extractor, "pages": result.pages, "needs_vision_reasons": result.needs_vision_reasons}
        document.needs_vision = result.needs_vision
        session.flush()
        return existing
    artifact = ExtractionArtifact(
        org_id=document.org_id,
        document_id=document.id,
        method="text_layer",
        content=result.text,
        annotations=[_annotation_dict(a) for a in result.annotations],
        content_sha=hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
        produced_with={
            **result.extractor,
            "pages": result.pages,
            "needs_vision_reasons": result.needs_vision_reasons,
        },
    )
    session.add(artifact)

    document.needs_vision = result.needs_vision
    if result.created:
        document.as_of, document.as_of_basis = result.created, "pdf_metadata"
    else:
        document.as_of, document.as_of_basis = date.today(), "upload_time"
    document.status = "extracted"
    session.flush()
    return artifact
