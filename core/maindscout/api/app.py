"""HTTP surface (`/v1`). Thin: checks the caller, then calls the writer, process, review or query functions.

Every request needs `Authorization: Bearer <OPERATOR_TOKEN>` and `X-Org-Id`. One request = one transaction.
"""

from __future__ import annotations

import hmac
import uuid
from functools import lru_cache
from typing import Any, Iterator

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import companies, costs, documents, erasure, process, queries, review, sourcing, tasks
from maindscout.api import task_handlers  # noqa: F401 (registers task kinds)
from maindscout.db.models import Document, ExtractionArtifact, IntelligenceRun, Org
from maindscout.db.session import make_engine, make_session_factory
from maindscout.domain import registry as reg
from maindscout.ingestion import pdf
from maindscout.intelligence.llm import LLMClient, LLMError, XaiClient
from maindscout.settings import env
from maindscout.storage import BlobStore, LocalBlobStore

MAX_UPLOAD = 20 * 1024 * 1024

app = FastAPI(title="mAIndscout platform API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=(env("COCKPIT_ORIGINS", "http://localhost:3001") or "").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- dependencies -------------------------------------------------------------------------------


@lru_cache
def _factory():
    return make_session_factory(make_engine())


def get_session() -> Iterator[Session]:
    session = _factory()()
    try:
        yield session
    finally:
        session.close()  # anything not committed by the route is discarded


@lru_cache
def get_blobs() -> BlobStore:
    return LocalBlobStore(env("BLOB_DIR"))


@lru_cache
def get_llm() -> LLMClient:
    return XaiClient()


def get_actor(x_actor: str | None = Header(default=None)) -> str:
    return (x_actor or "operator")[:80]


def get_org(authorization: str | None = Header(default=None), x_org_id: str | None = Header(default=None),
            session: Session = Depends(get_session)) -> uuid.UUID:
    token = env("OPERATOR_TOKEN")
    if not token:
        raise HTTPException(503, "OPERATOR_TOKEN is not configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(401, "Bad or missing token")
    try:
        org_id = uuid.UUID(x_org_id or "")
    except ValueError:
        raise HTTPException(400, "X-Org-Id header must be an org id") from None
    from maindscout.db.models import PUBLIC_ORG_ID

    if org_id == PUBLIC_ORG_ID or session.get(Org, org_id) is None:
        raise HTTPException(403, "Unknown org")  # the public-knowledge org is not a desk
    return org_id


# --- errors -------------------------------------------------------------------------------------

ERRORS: list[tuple[type[Exception], int]] = [
    (LookupError, 404),
    (erasure.ErasureConflict, 409),
    (pdf.UnsupportedMedia, 415),
    (LLMError, 502),
    (costs.BudgetExceeded, 402),
    (review.ReviewError, 422),
    (sourcing.SourcingError, 422),
    (reg.InvalidPayloadError, 422),
    (reg.UnknownFlagError, 422),
    (reg.UnknownClaimTypeError, 422),
    (pdf.UnreadableDocument, 422),
    (ValueError, 422),
]
for _exc, _code in ERRORS:
    app.add_exception_handler(_exc, lambda request, error, code=_code: JSONResponse({"detail": str(error)}, status_code=code))


# --- helpers ------------------------------------------------------------------------------------


async def _read(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 20 MB")
    media = file.content_type or "application/octet-stream"
    if (file.filename or "").lower().endswith(".pdf"):
        media = "application/pdf"
    return data, media


def _result(r: process.ProcessResult) -> dict[str, Any]:
    return {
        "run_id": str(r.run_id), "document_id": str(r.document_id), "status": r.status,
        "subject_type": r.subject_type, "subject_id": str(r.subject_id) if r.subject_id else None,
        "job_id": str(r.job_id) if r.job_id else None, "band": r.band, "reason": r.reason,
        "committed_claim_ids": [str(c) for c in r.claim_ids], "decision_ids": [str(d) for d in r.decision_ids],
        "span_failures": r.span_failures, "cost": r.cost, "reused": r.reused,
    }


def _doc(session: Session, org_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    doc = session.get(Document, document_id)
    if doc is None or doc.org_id != org_id:
        raise LookupError(f"No document {document_id}")
    return doc


# --- routes -------------------------------------------------------------------------------------


@app.get("/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/documents", status_code=201)
async def upload(file: UploadFile = File(...), doc_type_hint: str = Form("other"), org_id: uuid.UUID = Depends(get_org),
                 session: Session = Depends(get_session), blobs: BlobStore = Depends(get_blobs)):
    data, media = await _read(file)
    doc, reused = documents.upload_document(session, blobs, org_id=org_id, data=data, filename=file.filename,
                                            media_type=media, doc_type_hint=doc_type_hint)
    session.commit()
    return {"document_id": str(doc.id), "sha256": doc.sha256, "reused": reused}


@app.get("/v1/documents/{document_id}")
def get_document(document_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    d = _doc(session, org_id, document_id)
    return {"id": str(d.id), "filename": d.filename, "doc_type": d.doc_type, "status": d.status, "sha256": d.sha256,
            "media_type": d.media_type, "needs_vision": d.needs_vision, "as_of": queries._iso(d.as_of),
            "as_of_basis": d.as_of_basis}


@app.get("/v1/documents/{document_id}/file")
def get_document_file(document_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                      blobs: BlobStore = Depends(get_blobs)):
    d = _doc(session, org_id, document_id)
    return Response(blobs.get(d.storage_key), media_type=d.media_type,
                    headers={"Content-Disposition": f'inline; filename="{(d.filename or "document").replace(chr(34), "")}"'})


@app.get("/v1/documents/{document_id}/text")
def get_document_text(document_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    d = _doc(session, org_id, document_id)
    artifact = session.scalar(select(ExtractionArtifact).where(ExtractionArtifact.document_id == d.id))
    if artifact is None:
        raise LookupError("Document has not been read yet")
    return {"artifact_id": str(artifact.id), "text": artifact.content, "annotations": artifact.annotations}


class ProcessBody(BaseModel):
    force: bool = False
    job_id: uuid.UUID | None = None


@app.post("/v1/documents/{document_id}/process")
def process_document(document_id: uuid.UUID, body: ProcessBody | None = None, org_id: uuid.UUID = Depends(get_org),
                     session: Session = Depends(get_session), blobs: BlobStore = Depends(get_blobs),
                     llm: LLMClient = Depends(get_llm)):
    body = body or ProcessBody()
    result = process.process_document(session, blobs, llm, org_id=org_id, document_id=document_id,
                                      job_id=body.job_id, force=body.force)
    session.commit()
    return _result(result)


@app.get("/v1/runs/{run_id}")
def get_run(run_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    run = session.get(IntelligenceRun, run_id)
    if run is None or run.org_id != org_id:
        raise LookupError(f"No run {run_id}")
    return {"id": str(run.id), "document_id": str(run.document_id), "status": run.status,
            "manifest": run.version_manifest, "committed_at": queries._iso(run.committed_at)}


@app.get("/v1/jobs")
def list_jobs(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    return queries.list_jobs(session, org_id)


@app.post("/v1/jobs", status_code=201)
async def create_job(file: UploadFile = File(...), org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                     blobs: BlobStore = Depends(get_blobs), llm: LLMClient = Depends(get_llm)):
    """Create a job from its advertisement."""
    data, media = await _read(file)
    doc, _ = documents.upload_document(session, blobs, org_id=org_id, data=data, filename=file.filename,
                                       media_type=media, doc_type_hint="jd")
    if doc.doc_type != "jd":
        raise HTTPException(409, f"This file was already uploaded as a {doc.doc_type}")
    result = process.process_document(session, blobs, llm, org_id=org_id, document_id=doc.id)
    session.commit()
    return _result(result)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    return queries.job_page(session, org_id, job_id)


@app.post("/v1/jobs/{job_id}/documents", status_code=201)
async def upload_onto_job(job_id: uuid.UUID, file: UploadFile = File(...), background: bool = Query(False),
                          org_id: uuid.UUID = Depends(get_org),
                          session: Session = Depends(get_session), blobs: BlobStore = Depends(get_blobs),
                          llm: LLMClient = Depends(get_llm)):
    """Drop a CV onto a job: store, read, extract, and band the person against this job."""
    data, media = await _read(file)
    doc, _ = documents.upload_document(session, blobs, org_id=org_id, data=data, filename=file.filename,
                                       media_type=media, doc_type_hint="cv")
    if doc.doc_type != "cv":
        raise HTTPException(409, f"This file was already uploaded as a {doc.doc_type}")
    if background:
        task = tasks.enqueue(session, org_id, "process_document", {"document_id": str(doc.id), "job_id": str(job_id)},
                             priority=50, dedupe_key=f"process:{doc.id}:{job_id}")
        session.commit()
        return JSONResponse({"document_id": str(doc.id), "task_id": str(task.id), "status": "queued"}, status_code=202)
    result = process.process_document(session, blobs, llm, org_id=org_id, document_id=doc.id, job_id=job_id)
    session.commit()
    return _result(result)


@app.get("/v1/jobs/{job_id}/people")
def job_people(job_id: uuid.UUID, band: str | None = Query(None), org_id: uuid.UUID = Depends(get_org),
               session: Session = Depends(get_session)):
    people = queries.job_page(session, org_id, job_id)["people"]
    return people.get(band, []) if band else people


@app.get("/v1/jobs/{job_id}/people/{candidate_id}/gaps")
def gap_table(job_id: uuid.UUID, candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org),
              session: Session = Depends(get_session)):
    """Every requirement of the job against this person: evidence, missing, conflict or question. Never a number."""
    return queries.gap_page(session, org_id, job_id, candidate_id)


class StateBody(BaseModel):
    state: str
    reason: str | None = None
    note: str | None = None


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/state")
def set_pair_state(job_id: uuid.UUID, candidate_id: uuid.UUID, body: StateBody, org_id: uuid.UUID = Depends(get_org),
                   session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Move a pair: seen, submitted (needs a note) or we_passed (needs a reason). Pairs are never deleted."""
    pair = review.set_state(session, org_id, job_id, candidate_id, body.state, actor, body.reason, body.note)
    session.commit()
    return {"state": pair.pair_state, "outcome": pair.outcome}


class BandBody(BaseModel):
    band: str
    reason: str | None = None


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/triage")
def override_band(job_id: uuid.UUID, candidate_id: uuid.UUID, body: BandBody, org_id: uuid.UUID = Depends(get_org),
                  session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    pair = review.override_band(session, org_id, job_id, candidate_id, body.band, actor, body.reason)
    session.commit()
    return {"band": pair.triage_band, "reason": pair.triage_reason, "overridden_by": pair.band_overridden_by}


@app.get("/v1/candidates")
def list_candidates(unassigned: bool = Query(False), org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    people = queries.list_people(session, org_id)
    return [p for p in people if not p["jobs"]] if unassigned else people


@app.post("/v1/candidates", status_code=201)
async def upload_to_pool(file: UploadFile = File(...), background: bool = Query(False), org_id: uuid.UUID = Depends(get_org),
                         session: Session = Depends(get_session),
                         blobs: BlobStore = Depends(get_blobs), llm: LLMClient = Depends(get_llm)):
    """A CV with no job yet: read it into the unassigned pool. Put the person on a job later."""
    data, media = await _read(file)
    doc, _ = documents.upload_document(session, blobs, org_id=org_id, data=data, filename=file.filename,
                                       media_type=media, doc_type_hint="cv")
    if doc.doc_type != "cv":
        raise HTTPException(409, f"This file was already uploaded as a {doc.doc_type}")
    if background:
        task = tasks.enqueue(session, org_id, "process_document", {"document_id": str(doc.id)}, priority=50,
                             dedupe_key=f"process:{doc.id}:pool")
        session.commit()
        return JSONResponse({"document_id": str(doc.id), "task_id": str(task.id), "status": "queued"}, status_code=202)
    result = process.process_document(session, blobs, llm, org_id=org_id, document_id=doc.id)
    session.commit()
    return _result(result)


@app.post("/v1/jobs/{job_id}/people/{candidate_id}")
def put_on_job(job_id: uuid.UUID, candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org),
               session: Session = Depends(get_session), blobs: BlobStore = Depends(get_blobs), llm: LLMClient = Depends(get_llm)):
    """Pair an existing person with a job and band them. No document is read again."""
    from maindscout.db.models import DocumentSubject

    doc_id = session.scalar(select(DocumentSubject.document_id).where(
        DocumentSubject.subject_id == candidate_id, DocumentSubject.org_id == org_id).limit(1))
    if doc_id is None:
        raise LookupError(f"No documents for candidate {candidate_id}")
    result = process.process_document(session, blobs, llm, org_id=org_id, document_id=doc_id, job_id=job_id)
    session.commit()
    return _result(result)


@app.get("/v1/candidates/{candidate_id}")
def get_candidate(candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    return queries.person_page(session, org_id, candidate_id)


@app.get("/v1/candidates/{candidate_id}/claims")
def candidate_claims(candidate_id: uuid.UUID, status: str | None = Query(None), org_id: uuid.UUID = Depends(get_org),
                     session: Session = Depends(get_session)):
    page = queries.person_page(session, org_id, candidate_id)
    claims = [c for group in page["claims"].values() for c in group]
    return [c for c in claims if not status or c["status"] == status]


@app.get("/v1/inbox")
def get_inbox(job_id: uuid.UUID | None = Query(None), band: str | None = Query("priority"),
              org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    return queries.inbox(session, org_id, job_id, band)


@app.post("/v1/claims/{claim_id}/approve")
def approve(claim_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
            actor: str = Depends(get_actor)):
    claim = review.approve_claim(session, org_id, claim_id, actor)
    session.commit()
    return {"id": str(claim.id), "status": claim.status, "approved_view": claim.approved_view}


class RejectBody(BaseModel):
    code: str = "low_confidence"
    note: str | None = None


@app.post("/v1/claims/{claim_id}/reject")
def reject(claim_id: uuid.UUID, body: RejectBody | None = None, org_id: uuid.UUID = Depends(get_org),
           session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    body = body or RejectBody()
    claim = review.reject_claim(session, org_id, claim_id, actor, body.code, body.note)
    session.commit()
    return {"id": str(claim.id), "status": claim.status}


class AssertBody(BaseModel):
    subject_type: str
    subject_id: uuid.UUID
    claim_type: str
    payload: dict[str, Any]
    valid_from: str | None = None
    valid_to: str | None = None
    replaces: uuid.UUID | None = None


@app.post("/v1/claims", status_code=201)
def assert_claim(body: AssertBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                 actor: str = Depends(get_actor)):
    claim = review.assert_claim(session, org_id, actor, subject_type=body.subject_type, subject_id=body.subject_id,
                                claim_type=body.claim_type, payload=body.payload, valid_from=body.valid_from,
                                valid_to=body.valid_to, replaces=body.replaces)
    session.commit()
    return {"id": str(claim.id), "status": claim.status}


class ResolveBody(BaseModel):
    action: str
    claim_id: uuid.UUID | None = None


@app.post("/v1/decisions/{decision_id}/resolve")
def resolve(decision_id: uuid.UUID, body: ResolveBody, org_id: uuid.UUID = Depends(get_org),
            session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    decision = review.resolve_decision(session, org_id, decision_id, actor, body.action, body.claim_id)
    session.commit()
    return {"id": str(decision.id), "resolution": decision.resolution}


class EraseBody(BaseModel):
    reason: str | None = None


@app.post("/v1/subjects/candidate/{candidate_id}/erase")
def erase(candidate_id: uuid.UUID, body: EraseBody | None = None, org_id: uuid.UUID = Depends(get_org),
          session: Session = Depends(get_session), blobs: BlobStore = Depends(get_blobs), actor: str = Depends(get_actor)):
    """Forget a person. The response includes the verify result; anything but an empty survivor list is a failure."""
    record = erasure.erase_candidate(session, blobs, org_id, candidate_id, actor, (body or EraseBody()).reason)
    session.commit()
    return {"erasure_id": str(record.id), "counts": record.counts, "survivors": record.survivors,
            "clean": not record.survivors}


@app.get("/v1/subjects/candidate/{candidate_id}/erase/verify")
def verify_erase(candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                 blobs: BlobStore = Depends(get_blobs)):
    record = session.scalar(select(erasure.Erasure).where(erasure.Erasure.org_id == org_id,
                                                          erasure.Erasure.subject_id == candidate_id))
    if record is None:
        raise LookupError("This person has not been erased")
    survivors = erasure.verify_erasure(session, blobs, org_id, candidate_id, [])
    return {"clean": not survivors, "survivors": survivors}


class CampaignBody(BaseModel):
    source: str = "auto"
    cap: int = sourcing.DEFAULT_CAP
    target: int = sourcing.DEFAULT_TARGET


@app.post("/v1/jobs/{job_id}/campaigns", status_code=201)
def start_campaign(job_id: uuid.UUID, body: CampaignBody | None = None, org_id: uuid.UUID = Depends(get_org),
                   session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Refill a thin priority queue: a bounded find whose people go through the same triage as uploads."""
    body = body or CampaignBody()
    campaign = sourcing.start(session, org_id, job_id, actor, body.source, body.cap, body.target)
    session.commit()
    return sourcing.as_dict(campaign)


@app.get("/v1/jobs/{job_id}/campaigns")
def list_campaigns(job_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.db.models import Campaign

    rows = session.scalars(select(Campaign).where(Campaign.job_id == job_id, Campaign.org_id == org_id).order_by(Campaign.created_at.desc()))
    from maindscout.db.models import CareerProfile, Job

    job = session.get(Job, job_id)
    profile = sourcing.profile_query(session, job) if job is not None and job.org_id == org_id else None
    has_profiles = bool(session.scalar(select(CareerProfile.id).where(CareerProfile.org_id == org_id).limit(1)))
    return {"priority": sourcing.priority_count(session, job_id), "default_target": sourcing.DEFAULT_TARGET,
            "by_profile": profile["words"] if profile and has_profiles else None,
            "campaigns": [sourcing.as_dict(c) for c in rows]}


@app.post("/v1/campaigns/{campaign_id}/stop")
def stop_campaign(campaign_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                  actor: str = Depends(get_actor)):
    campaign = sourcing.stop(session, org_id, campaign_id, actor)
    session.commit()
    return sourcing.as_dict(campaign)


@app.get("/v1/companies")
def list_companies(q: str | None = Query(None), org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Companies this desk has touched through people or jobs, most people first; `q` filters by name."""
    return companies.search(session, org_id, q)


@app.get("/v1/companies/{company_id}")
def get_company(company_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """A company: its names, this desk's people who worked there (with title and period), and its jobs here."""
    return companies.company_page(session, org_id, company_id)


class MergeBody(BaseModel):
    into: uuid.UUID


@app.post("/v1/companies/{company_id}/merge")
def merge_company(company_id: uuid.UUID, body: MergeBody, org_id: uuid.UUID = Depends(get_org),
                  session: Session = Depends(get_session)):
    keep = companies.merge(session, body.into, company_id)
    session.commit()
    return {"id": str(keep.id), "name": keep.name}


@app.get("/v1/tasks")
def get_tasks(ids: str = Query(..., description="comma-separated task ids"), org_id: uuid.UUID = Depends(get_org),
              session: Session = Depends(get_session)):
    """Status of background tasks (for showing progress)."""
    from maindscout.db.models import Task

    wanted = [uuid.UUID(i) for i in ids.split(",") if i.strip()][:100]
    rows = session.scalars(select(Task).where(Task.id.in_(wanted), Task.org_id == org_id))
    return [tasks.as_dict(t) for t in rows]


@app.get("/v1/costs")
def get_costs(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """This month's spend on model calls and searches, by purpose and day, against the budget."""
    return costs.summary(session, org_id)


@app.post("/v1/companies/{company_id}/research", status_code=202)
def research_company(company_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Queue (re)research of a company's public facts now, even if they are still fresh."""
    from maindscout.db.models import Company

    company = companies.canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    task = tasks.enqueue(session, None, "research_company", {"company_id": str(company.id), "context": "", "force": True},
                         priority=60, dedupe_key=f"research:{company.id}")
    session.commit()
    return {"task_id": str(task.id), "status": task.status}


class CountriesBody(BaseModel):
    countries: list[str]


@app.put("/v1/jobs/{job_id}/countries")
def set_job_countries(job_id: uuid.UUID, body: CountriesBody, org_id: uuid.UUID = Depends(get_org),
                      session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Open a job to countries beyond the desk's coverage (codes or names). Its people are re-checked."""
    from maindscout.api import coverage

    coverage.set_open_countries(session, org_id, job_id, body.countries, actor)
    session.commit()
    return queries.job_page(session, org_id, job_id)


@app.post("/v1/candidates/{candidate_id}/bring-back")
def bring_back(candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
               actor: str = Depends(get_actor)):
    """Un-archive a person the coverage gate archived; the gate then leaves them be."""
    from maindscout.api import coverage

    coverage.bring_back(session, org_id, candidate_id, actor)
    session.commit()
    return queries.person_page(session, org_id, candidate_id)


class IntakeBody(BaseModel):
    text: str


@app.post("/v1/jobs/{job_id}/intake")
def add_intake(job_id: uuid.UUID, body: IntakeBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
               actor: str = Depends(get_actor), llm: LLMClient = Depends(get_llm)):
    """Paste notes from the call with the hiring manager: requirements are read from them, each with its quote."""
    from maindscout.api import hiring

    result = hiring.add_intake(session, org_id, job_id, body.text, actor, llm)
    session.commit()
    return {**result, "job": queries.job_page(session, org_id, job_id)}


class RequirementBody(BaseModel):
    category: str
    strength: str
    text_raw: str
    role_family: str | None = None
    level: str | None = None
    min_years: float | None = None
    employer_kinds: list[str] | None = None
    domains: list[str] | None = None
    companies: list[str] | None = None
    employment: str | None = None
    normalized_token: str | None = None
    note: str | None = None


@app.post("/v1/jobs/{job_id}/requirements", status_code=201)
def add_requirement(job_id: uuid.UUID, body: RequirementBody, org_id: uuid.UUID = Depends(get_org),
                    session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """A requirement the recruiter types (approved at once)."""
    from maindscout.api import hiring

    fields = body.model_dump()
    fields["companies"] = [{"name": n} for n in body.companies or []] or None
    claim = hiring.add_requirement(session, org_id, job_id, fields, actor)
    session.commit()
    return {"id": str(claim.id)}


class StrengthBody(BaseModel):
    strength: str


@app.post("/v1/requirements/{claim_id}/strength")
def set_strength(claim_id: uuid.UUID, body: StrengthBody, org_id: uuid.UUID = Depends(get_org),
                 session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Change how much a requirement matters; the old reading is kept as superseded."""
    from maindscout.api import hiring

    claim = hiring.set_strength(session, org_id, claim_id, body.strength, actor)
    session.commit()
    return {"id": str(claim.id), "strength": claim.payload["strength"]}


_QUERY_CACHE: dict[str, Any] = {}


@app.get("/v1/search")
def search_people(q: str | None = None, family: str | None = None, related: bool = True, min_years: float | None = None,
                  level: str | None = None, employer: list[str] = Query(default=[]), domain: list[str] = Query(default=[]),
                  company: list[str] = Query(default=[]), current: bool = False,
                  org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session), llm: LLMClient = Depends(get_llm)):
    """Search the desk's people. `q`: in the recruiter's own words, read into criteria and ranked best first, each
    result with its reasons. Without `q`: the structured filters (every one must be met; newest first)."""
    from maindscout.api import search

    if q and q.strip():
        from maindscout.intelligence import query as reader

        key = " ".join(q.lower().split())
        parsed = _QUERY_CACHE.get(key)
        if parsed is None:  # the same search again costs nothing
            costs.ensure_budget(session, org_id)
            parsed = reader.read(q.strip(), llm)
            costs.record(session, org_id, "search_query", parsed.cost)
            session.commit()
            if len(_QUERY_CACHE) > 500:
                _QUERY_CACHE.clear()
            _QUERY_CACHE[key] = parsed
        return {"query": q, "understood": search.understood(parsed), "ignored": parsed.ignored,
                "people": search.ranked(session, org_id, parsed) if not parsed.empty() else []}

    f = search.Filters(family=family or None, related=related, min_years=min_years, level=level or None,
                       employer_kinds=[e for e in employer if e], domains=[d for d in domain if d],
                       company_ids=[c for c in company if c], current_only=current)
    return {"filters": f.words(), "people": search.search(session, org_id, f)}


class BriefAnswerBody(BaseModel):
    outcome: str
    answer: str | None = None


@app.get("/v1/jobs/{job_id}/people/{candidate_id}/brief")
def get_brief(job_id: uuid.UUID, candidate_id: uuid.UUID, force: bool = False, org_id: uuid.UUID = Depends(get_org),
              session: Session = Depends(get_session)):
    """The call checklist for a priority person on a job (compiled and reconciled now). `force` for other bands."""
    from maindscout.api import brief

    try:
        items = brief.build(session, org_id, job_id, candidate_id, force=force)
    except brief.BriefError as error:
        session.rollback()
        return {"available": False, "reason": str(error), "items": [], "header": brief.header(session, org_id, job_id, candidate_id)}
    session.commit()
    return {"available": True, "items": [brief.as_dict(i) for i in items], "header": brief.header(session, org_id, job_id, candidate_id)}


@app.post("/v1/brief/{item_id}/answer")
def answer_brief(item_id: uuid.UUID, body: BriefAnswerBody, org_id: uuid.UUID = Depends(get_org),
                 session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Capture an answer from the call as an approved fact; the person is matched again at once."""
    from maindscout.api import brief

    item = brief.answer(session, org_id, item_id, body.outcome, body.answer, actor)
    session.commit()
    return brief.as_dict(item)


@app.post("/v1/brief/{item_id}/asked")
def asked_brief(item_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                actor: str = Depends(get_actor)):
    from maindscout.api import brief

    item = brief.mark_asked(session, org_id, item_id, actor)
    session.commit()
    return brief.as_dict(item)


@app.post("/v1/brief/{item_id}/dismiss")
def dismiss_brief(item_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                  actor: str = Depends(get_actor)):
    from maindscout.api import brief

    item = brief.dismiss(session, org_id, item_id, actor)
    session.commit()
    return brief.as_dict(item)
