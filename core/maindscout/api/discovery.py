"""People found on the web by sourcing (docs/next/PLAN.md S2): public data only, read like a short CV with no model.

A found profile is stored as a document (`web_profile`, the page text as its text layer, the page's address as its
one link) and read through the ordinary CV path by `webprofile.EntityReader`: the same identity rules (the same
LinkedIn page is the same person; no merge on a name alone), the same span check, company links and coverage gate,
the same suppression (someone erased is never stored again). What sourcing adds on top (off-limits, "stop", the
role's pair) lives in `autosource.py`.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import documents, process
from maindscout.db.models import Candidate, Claim, Document, ExtractionArtifact, Job
from maindscout.intelligence import contacts, webprofile
from maindscout.intelligence.exa import Found
from maindscout.storage import BlobStore

LIVE = ("proposed", "approved")


def skill_tokens(session: Session, job: Job) -> list[str]:
    """The role's own skill words (must, strong plus, nice to have): the only skills read from a profile."""
    out: list[str] = []
    for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.status.in_(LIVE))):
        p = c.approved_view or c.payload
        token = (p.get("normalized_token") or "").strip().lower()
        if p.get("category") == "skill" and token and p.get("strength") != "anti" and token not in out:
            out.append(token)
    return out


def person_by_profile(session: Session, org_id: uuid.UUID, url: str) -> uuid.UUID | None:
    """The person whose LinkedIn page this is, if the desk already knows them."""
    norm = contacts.normalise("linkedin", url) if "linkedin.com/in" in url.lower() else None
    if not norm:
        return None
    cid = session.scalar(select(Claim.subject_id).where(
        Claim.org_id == org_id, Claim.claim_type == "ContactClaim", Claim.status.in_(LIVE),
        Claim.payload["normalized"].astext == norm).limit(1))
    while cid is not None:
        person = session.get(Candidate, cid)
        if person is None or person.merged_into_id is None:
            break
        cid = person.merged_into_id
    return cid


def _label(url: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", url.split("://", 1)[-1]).strip("-")
    return f"{slug[:80]}.txt"


def store_profile(session: Session, blobs: BlobStore, org_id: uuid.UUID, found: Found) -> tuple[Document, bool]:
    """The page as a document. The same text is stored once (reused); a changed page is a new document."""
    text = found.text.strip()
    doc, reused = documents.upload_document(session, blobs, org_id=org_id, data=text.encode("utf-8"),
                                            filename=_label(found.url), media_type="text/plain", doc_type_hint="web_profile")
    if not reused:
        doc.source_authority, doc.transformed_by_third_party = "third_party_assertion", True
        session.add(ExtractionArtifact(
            org_id=org_id, document_id=doc.id, method="text_layer", content=text,
            annotations=[{"page": 1, "kind": "link", "uri": found.url}],
            content_sha=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            produced_with={"name": "exa", "reader": webprofile.READER_VERSION, "url": found.url, "published": found.published}))
        doc.as_of, doc.as_of_basis, doc.status = date.today(), "upload_time", "extracted"
        session.flush()
    return doc, reused


def add(session: Session, blobs: BlobStore, org_id: uuid.UUID, found: Found, skills: list[str]) -> tuple[uuid.UUID | None, str]:
    """Store and read one found profile. Returns (person id, outcome): new | known | not_a_profile | stop | unreadable.
    "known" means the desk already had this person (the same page, or someone they already were)."""
    if not found.person or not found.text.strip() or not (found.person.get("name") or "").strip():
        return None, "not_a_profile"
    before = person_by_profile(session, org_id, found.url)
    doc, reused = store_profile(session, blobs, org_id, found)
    reader = webprofile.EntityReader(webprofile.read(found, skills))
    result = process.process_document(session, blobs, reader, org_id=org_id, document_id=doc.id)
    if result.status == "suppressed":
        return None, "stop"
    if result.subject_type != "candidate" or not result.subject_id:
        return None, "unreadable"
    cid = result.subject_id
    while (person := session.get(Candidate, cid)) is not None and person.merged_into_id:
        cid = person.merged_into_id
    return cid, "known" if (before or reused) else "new"
