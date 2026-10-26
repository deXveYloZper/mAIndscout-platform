"""HTTP surface (`/v1`). Thin: checks the caller, then calls the writer, process, review or query functions.

Every request needs `Authorization: Bearer <session or personal token>` (see api/auth.py); `X-Org-Id` may choose
another desk the user belongs to. The caller is the signed-in user, never a header. One request = one transaction.
"""

from __future__ import annotations

import threading
import urllib.parse
import uuid
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Iterator

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from maindscout.api import auth, companies, costs, documents, erasure, pipeline, process, queries, review, sourcing, tasks
from maindscout.api import mailbox as mailbox_mod
from maindscout.api import task_handlers  # noqa: F401 (registers task kinds)
from maindscout.db.models import Document, ExtractionArtifact, IntelligenceRun
from maindscout.db.session import make_engine, make_session_factory
from maindscout.domain import registry as reg
from maindscout.ingestion import pdf
from maindscout.intelligence import exa as exa_mod
from maindscout.intelligence.llm import LLMClient, LLMError, XaiClient
from maindscout.settings import env
from maindscout.storage import BlobStore, LocalBlobStore

MAX_UPLOAD = 20 * 1024 * 1024

app = FastAPI(title="mAIndscout platform API", version="0.1.0")


@app.middleware("http")
async def activity_log(request: Request, call_next):
    """Every action a page sends (a button), and every error, as a line in the activity log (owner, 2026-10-22)."""
    import time

    from starlette.concurrency import run_in_threadpool

    from maindscout import activity
    from maindscout.api import buttons

    action = buttons.describe(request.method, request.url.path) if request.method in ("POST", "PUT", "PATCH", "DELETE") else None
    job_id = buttons.job_of(request.url.path)
    started = time.monotonic()
    with activity.about(job_id=job_id):
        try:
            response = await call_next(request)
        except Exception as exc:
            who = getattr(request.state, "principal", None)
            await run_in_threadpool(activity.error, f"Server error on {request.method} {request.url.path}: {type(exc).__name__}",
                                    exc, {"action": action}, org_id=getattr(who, "org_id", None),
                                    actor=getattr(who, "email", None), job_id=job_id)
            raise
    ms = int((time.monotonic() - started) * 1000)
    who = getattr(request.state, "principal", None)
    if action or response.status_code >= 500:
        level = "error" if response.status_code >= 500 else "warn" if response.status_code >= 400 else "info"
        await run_in_threadpool(
            activity.note, "error" if level == "error" else "button",
            f"{action or request.method + ' ' + request.url.path}{'' if response.status_code < 400 else f' (refused: {response.status_code})'}",
            {"route": f"{request.method} {request.url.path}", "status": response.status_code, "ms": ms}, level,
            org_id=getattr(who, "org_id", None), actor=getattr(who, "email", None), job_id=job_id)
    return response
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
    from maindscout.intelligence.recording import wrap_chat

    return wrap_chat(XaiClient)  # LLM_REPLAY: record once, replay for free (tests, e2e)


def _principal(session: Session, authorization: str | None, x_org_id: str | None) -> auth.Principal:
    token = (authorization or "").removeprefix("Bearer ").strip() or None
    try:
        p = auth.resolve(session, token, x_org_id)
    except auth.AuthError:
        session.commit()  # an idle session that just ended stays ended
        raise
    if session.dirty:
        session.commit()  # last seen (at most once a minute)
    return p


def get_principal_any(request: Request, authorization: str | None = Header(default=None),
                      x_org_id: str | None = Header(default=None), session: Session = Depends(get_session)) -> auth.Principal:
    """Signed in, even if an owner still has to set up two-step codes (for the account routes only)."""
    p = _principal(session, authorization, x_org_id)
    request.state.principal = p  # for the activity log: who pressed the button
    return p


def get_principal(p: auth.Principal = Depends(get_principal_any)) -> auth.Principal:
    if p.needs_two_step:
        raise auth.Forbidden("Set up two-step verification first (Account page): owners need it")
    return p


def require_owner(p: auth.Principal = Depends(get_principal)) -> auth.Principal:
    if p.role != "owner":
        raise auth.Forbidden("Only a desk owner can do this")
    return p


def get_org(p: auth.Principal = Depends(get_principal)) -> uuid.UUID:
    return p.org_id


def get_actor(p: auth.Principal = Depends(get_principal)) -> str:
    """Who did it: always the signed-in user (their email), never something the caller declares."""
    return p.email


def _address(request: Request) -> str | None:
    """The browser's address, for slowing down guessing. The cockpit passes it on; it is trusted only from this
    machine (the cockpit runs next to the API)."""
    peer = request.client.host if request.client else None
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if peer in ("127.0.0.1", "::1", "testclient") and forwarded:
        return forwarded[:64]
    return peer


# --- errors -------------------------------------------------------------------------------------

ERRORS: list[tuple[type[Exception], int]] = [
    (LookupError, 404),
    (erasure.ErasureConflict, 409),
    (pdf.UnsupportedMedia, 415),
    (LLMError, 502),
    (costs.BudgetExceeded, 402),
    (review.ReviewError, 422),
    (sourcing.SourcingError, 422),
    (exa_mod.ExaError, 502),
    (reg.InvalidPayloadError, 422),
    (reg.UnknownFlagError, 422),
    (reg.UnknownClaimTypeError, 422),
    (pdf.UnreadableDocument, 422),
    (pipeline.BlockedError, 409),
    (mailbox_mod.MailboxError, 502),
    (auth.AuthError, 401),
    (auth.Forbidden, 403),
    (ValueError, 422),
]
for _exc, _code in ERRORS:
    app.add_exception_handler(_exc, lambda request, error, code=_code: JSONResponse({"detail": str(error)}, status_code=code))
app.add_exception_handler(auth.Locked, lambda request, error: JSONResponse(
    {"detail": str(error)}, status_code=429,
    headers={"Retry-After": str(max(1, int((error.until - auth._now()).total_seconds())))}))


# --- helpers ------------------------------------------------------------------------------------


async def _read(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 20 MB")
    return data, _sniff(data)


def _sniff(data: bytes) -> str:
    """The type the bytes really are; the caller's claimed content type is never trusted (it decides how a file is
    served back). Only PDFs and plain text can be read; anything else is stored as opaque bytes."""
    if data[:1024].lstrip().startswith(b"%PDF-"):
        return "application/pdf"
    if b"\x00" not in data[:8192]:
        try:
            data[:65536].decode("utf-8")
            return "text/plain; charset=utf-8"
        except UnicodeDecodeError:
            pass
    return "application/octet-stream"


def _safe_filename(name: str | None) -> str:
    keep = "".join(c if c.isalnum() or c in " ._-()" else "_" for c in (name or "document"))[:120].strip()
    return keep or "document"


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
    """The original file. Only a real PDF (or plain text) opens in the browser; anything else downloads, so an uploaded
    HTML or SVG file can never run as a page on the desk's origin."""
    d = _doc(session, org_id, document_id)
    data = blobs.get(d.storage_key)
    media = _sniff(data)
    disposition = "inline" if media != "application/octet-stream" else "attachment"
    headers = {"Content-Disposition": f'{disposition}; filename="{_safe_filename(d.filename)}"',
               "X-Content-Type-Options": "nosniff"}
    if media != "application/pdf":
        headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return Response(data, media_type=media, headers=headers)


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
    """Move a pair along the pipeline (new → seen → contacted → screened → submitted → interviewing → offer → placed;
    or we passed / withdrawn / client rejected). Notes and reasons as the rules say; pairs are never deleted."""
    pair = review.set_state(session, org_id, job_id, candidate_id, body.state, actor, body.reason, body.note)
    if body.state == "contacted":  # set by hand: the same contact record as every other door (x-ray B2)
        from maindscout.api import outreach

        outreach.record_contact(session, org_id, job_id, candidate_id, "other", actor)
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


# --- phase 1c: the owner's workflow on a role's suggestions, and the contact track (api/outreach.py) ---


def _pair_view(pair) -> dict:
    from maindscout.api import outreach

    return {"stage": outreach.stage(pair), "state": pair.pair_state, "band": pair.triage_band,
            "contact": {k: v for k, v in (pair.contact or {}).items() if k not in ("mail_ids", "machine")} or None}


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/viewed")
def outreach_viewed(job_id: uuid.UUID, candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org),
                    session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """The owner opened their profile."""
    from maindscout.api import outreach

    pair = outreach.viewed(session, org_id, job_id, candidate_id, actor)
    session.commit()
    return _pair_view(pair)


class DecideBody(BaseModel):
    choice: str  # reach_out | later | pass
    reason: str | None = None  # for pass: level | skills | location | domain | other
    note: str | None = None


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/decide")
def outreach_decide(job_id: uuid.UUID, candidate_id: uuid.UUID, body: DecideBody, org_id: uuid.UUID = Depends(get_org),
                    session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Reach out (Priority, by the owner), maybe later, or not for this role (with a reason)."""
    from maindscout.api import outreach

    pair = outreach.decide(session, org_id, job_id, candidate_id, body.choice, actor, body.reason, body.note)
    session.commit()
    return _pair_view(pair)


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/undo")
def outreach_undo(job_id: uuid.UUID, candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org),
                  session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Back to the suggestions (before anyone was contacted)."""
    from maindscout.api import outreach

    pair = outreach.undo(session, org_id, job_id, candidate_id, actor)
    session.commit()
    return _pair_view(pair)


class ContactedBody(BaseModel):
    channel: str  # linkedin_invite | linkedin_message | inmail | email
    note: str | None = None


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/contacted")
def outreach_contacted(job_id: uuid.UUID, candidate_id: uuid.UUID, body: ContactedBody, org_id: uuid.UUID = Depends(get_org),
                       session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Contacted outside the desk: the follow-up reminder starts (4 days)."""
    from maindscout.api import outreach

    outreach.contacted(session, org_id, job_id, candidate_id, body.channel, actor, body.note)
    session.commit()
    return _pair_view(outreach._pair(session, org_id, job_id, candidate_id))


class RepliedBody(BaseModel):
    outcome: str  # interested | not_now | not_interested | stop
    note: str | None = None
    check_back: date | None = None
    text: str | None = None


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/replied")
def outreach_replied(job_id: uuid.UUID, candidate_id: uuid.UUID, body: RepliedBody, org_id: uuid.UUID = Depends(get_org),
                     session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    from maindscout.api import outreach

    pair = outreach.replied(session, org_id, job_id, candidate_id, body.outcome, actor, body.note, body.check_back, body.text)
    session.commit()
    return _pair_view(pair)


class CallBody(BaseModel):
    when: datetime | None = None


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/call-booked")
def outreach_call(job_id: uuid.UUID, candidate_id: uuid.UUID, body: CallBody, org_id: uuid.UUID = Depends(get_org),
                  session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    from maindscout.api import outreach

    pair = outreach.call_booked(session, org_id, job_id, candidate_id, actor, body.when)
    session.commit()
    return _pair_view(pair)


class SettleBody(BaseModel):
    mine: bool


@app.post("/v1/jobs/{job_id}/people/{candidate_id}/linkedin-email")
def outreach_settle(job_id: uuid.UUID, candidate_id: uuid.UUID, body: SettleBody, org_id: uuid.UUID = Depends(get_org),
                    session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Two people contacted on LinkedIn share a name: is LinkedIn's email about this one?"""
    from maindscout.api import outreach

    pair = outreach.settle(session, org_id, job_id, candidate_id, body.mine, actor)
    session.commit()
    return _pair_view(pair)


@app.get("/v1/candidates")
def list_candidates(unassigned: bool = Query(False), tag: str | None = Query(None), org_id: uuid.UUID = Depends(get_org),
                    session: Session = Depends(get_session)):
    people = queries.list_people(session, org_id)
    if tag:
        people = [p for p in people if tag in p["tags"]]
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


@app.get("/v1/activity")
def get_activity(job_id: uuid.UUID | None = Query(None), kind: str | None = Query(None), level: str | None = Query(None),
                 q: str | None = Query(None), limit: int = Query(200, ge=1, le=1000), before: datetime | None = Query(None),
                 org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """The activity log, newest first: buttons, tasks, searches, model calls, steps and errors (owner, 2026-10-22)."""
    from maindscout.db.models import DeskLog, Job

    stmt = select(DeskLog).where(DeskLog.org_id == org_id)
    if job_id:
        stmt = stmt.where(DeskLog.job_id == job_id)
    if kind:
        stmt = stmt.where(DeskLog.kind.in_(kind.split(",")))
    if level:
        stmt = stmt.where(DeskLog.level.in_(level.split(",")))
    if q:
        stmt = stmt.where(DeskLog.summary.ilike(f"%{q}%"))
    if before:
        stmt = stmt.where(DeskLog.at < before)
    rows = list(session.scalars(stmt.order_by(DeskLog.at.desc()).limit(limit)))
    titles = dict(session.execute(select(Job.id, Job.title).where(Job.id.in_({r.job_id for r in rows if r.job_id} or {None}))).all())
    return [{"id": str(r.id), "at": r.at.isoformat(), "kind": r.kind, "level": r.level, "summary": r.summary,
             "detail": r.detail, "actor": r.actor, "task_id": str(r.task_id) if r.task_id else None,
             "job_id": str(r.job_id) if r.job_id else None, "job": titles.get(r.job_id)} for r in rows]


class ClientErrorBody(BaseModel):
    message: str
    stack: str | None = None
    url: str | None = None
    digest: str | None = None


@app.post("/v1/activity/client-error")
def client_error(body: ClientErrorBody, p: auth.Principal = Depends(get_principal)):
    """A page that crashed in the browser says so, so the error can be read later (owner, 2026-10-22)."""
    import re

    from maindscout import activity

    path = urllib.parse.urlparse(body.url or "").path
    m = re.match(r"^/jobs/([0-9a-fA-F-]{36})", path)
    activity.note("error", f"The page crashed in the browser: {body.message[:200]}",
                  {"url": body.url, "stack": activity.cut(body.stack or "", 12000), "digest": body.digest}, "error",
                  org_id=p.org_id, actor=p.email, job_id=m.group(1) if m else None)
    return {"ok": True}


@app.get("/v1/inbox")
def get_inbox(job_id: uuid.UUID | None = Query(None), band: str | None = Query(None),
              org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """With a job: people in `band` (default priority; `all` for everyone on it). Without a job: everyone, since a band
    belongs to a person on a job; asking for a band without a job is refused rather than silently ignored."""
    if job_id is None and band not in (None, "all"):
        raise HTTPException(422, "A band applies to a job: pass job_id, or band=all")
    return queries.inbox(session, org_id, job_id, band or ("priority" if job_id else "all"))


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


# --- the sourcing engine (docs/next/PLAN.md, phase 1) ---------------------------------------------------------------


@app.get("/v1/jobs/{job_id}/sourcing")
def sourcing_page(job_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                  actor: str = Depends(get_actor)):
    """The role's plan (made on first look, paused), budgets, recent runs and the suggestions waiting."""
    from maindscout.api import autosource

    out = autosource.page(session, org_id, job_id, actor)
    session.commit()
    return out


class PlanBody(BaseModel):
    mode: str | None = None
    target: int | None = None
    monthly_budget_usd: float | None = None
    role_variants: list[str] | None = None
    countries: list[str] | None = None
    rules: dict[str, float] | None = None
    open_tiers: list[str] | None = None


@app.patch("/v1/jobs/{job_id}/sourcing/plan")
def change_sourcing_plan(job_id: uuid.UUID, body: PlanBody, org_id: uuid.UUID = Depends(get_org),
                         session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    from maindscout.api import autosource, hiring

    changes = body.model_dump(exclude_none=True)
    if "countries" in changes:  # the role's countries live in its hiring profile ("must live in"): written there
        hiring.set_residence(session, org_id, job_id, changes.pop("countries"), actor)
    if changes:
        autosource.update_plan(session, org_id, job_id, actor, **changes)
    out = autosource.page(session, org_id, job_id, actor)
    session.commit()
    return out


class FocusBody(BaseModel):
    words: str | None = None


@app.put("/v1/jobs/{job_id}/sourcing/focus")
def change_sourcing_focus(job_id: uuid.UUID, body: FocusBody, org_id: uuid.UUID = Depends(get_org),
                          session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Narrow the search to companies the words describe ("luxury apparel"), or widen it again (no words)."""
    from maindscout.api import autosource

    try:
        autosource.set_focus(session, org_id, job_id, body.words, actor)
    except autosource.SourcingEngineError as error:
        raise HTTPException(422, str(error)) from error
    out = autosource.page(session, org_id, job_id, actor)
    session.commit()
    return out


class TargetBody(BaseModel):
    name: str


@app.post("/v1/jobs/{job_id}/sourcing/targets", status_code=201)
def add_sourcing_target(job_id: uuid.UUID, body: TargetBody, org_id: uuid.UUID = Depends(get_org),
                        session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    from maindscout.api import autosource

    autosource.add_target(session, org_id, job_id, body.name, actor)
    out = autosource.page(session, org_id, job_id, actor)
    session.commit()
    return out


class TargetChange(BaseModel):
    pinned: bool | None = None
    removed: bool | None = None


@app.patch("/v1/jobs/{job_id}/sourcing/targets/{company_id}")
def change_sourcing_target(job_id: uuid.UUID, company_id: uuid.UUID, body: TargetChange, org_id: uuid.UUID = Depends(get_org),
                           session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    from maindscout.api import autosource

    autosource.set_target(session, org_id, job_id, str(company_id), actor, pinned=body.pinned, removed=body.removed)
    out = autosource.page(session, org_id, job_id, actor)
    session.commit()
    return out


@app.post("/v1/jobs/{job_id}/sourcing/run", status_code=202)
def run_sourcing_now(job_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                     actor: str = Depends(get_actor)):
    """Search now (in the background): the pool, then the web within the budgets."""
    from maindscout.api import autosource

    from maindscout import activity

    job = autosource._job(session, org_id, job_id)
    if job.state != "open":
        raise HTTPException(422, "Only an open role is sourced")
    autosource.plan(session, org_id, job_id, actor)
    if not autosource.list_built(session, job_id) and task_handlers.exa_factory() is not None:
        # Never searched from a starting list nobody built: the client's competitors first (owner, 2026-10-22: the
        # Ferrari role searched the last role's fashion houses because its list was never built).
        task = tasks.enqueue(session, org_id, "sourcing_strategy", {"job_id": str(job_id), "actor": actor, "then_search": True},
                             priority=60, dedupe_key=f"strategy:{job_id}", max_attempts=1)
        session.commit()
        activity.step("Search now: this role's company list was never built, so it is built first (competitor research, "
                      "about $0.45), then the search starts", org_id=org_id, job_id=job_id, actor=actor)
        return {"task_id": str(task.id), "status": "building"}
    task = tasks.enqueue(session, org_id, "sourcing_run", {"job_id": str(job_id), "trigger": "manual", "actor": actor},
                         priority=60, dedupe_key=f"sourcing:{job_id}", max_attempts=1)
    session.commit()
    return {"task_id": str(task.id), "status": task.status}


@app.post("/v1/jobs/{job_id}/sourcing/strategy", status_code=202)
def build_sourcing_strategy(job_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                            actor: str = Depends(get_actor)):
    """Build the role's strategy in the background: the hiring company's talent DNA and the tiered target list
    (paid, under $0.50; docs/next/PLAN.md section 4b)."""
    from maindscout.api import autosource

    autosource._job(session, org_id, job_id)
    autosource.plan(session, org_id, job_id, actor)
    task = tasks.enqueue(session, org_id, "sourcing_strategy", {"job_id": str(job_id), "actor": actor},
                         priority=60, dedupe_key=f"strategy:{job_id}", max_attempts=1)
    session.commit()
    return {"task_id": str(task.id), "status": task.status}


@app.post("/v1/jobs/{job_id}/sourcing/people/{candidate_id}/evidence", status_code=202)
def check_deeper(job_id: uuid.UUID, candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org),
                 session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """"Check deeper": look at a suggestion's public work against the role, in the background (their links, and a
    search for their name with their company; about 1-3 cents). Strong matches get it on their own."""
    from maindscout.api import autosource, evidence
    from maindscout.db.models import CandidateJob

    job = autosource._job(session, org_id, job_id)
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == candidate_id))
    if pair is None or pair.org_id != org_id:
        raise HTTPException(404, "This person is not on this role")
    if not evidence.found_on_the_web(session, job.id, candidate_id):
        raise HTTPException(422, "Only people found on the web are checked this way: the desk already has their file")
    task = evidence.queue(session, org_id, job.id, candidate_id, actor)
    session.commit()
    return {"task_id": str(task.id), "status": task.status}


class WidenBody(BaseModel):
    option: str
    value: str | list[str] | None = None


@app.post("/v1/jobs/{job_id}/sourcing/widen")
def widen_sourcing(job_id: uuid.UUID, body: WidenBody, org_id: uuid.UUID = Depends(get_org),
                   session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """The owner's choice from a widening proposal: open a tier, add titles or a country, or search the market."""
    from maindscout.api import autosource, strategy

    strategy.widen(session, org_id, job_id, actor, body.option, body.value)
    out = autosource.page(session, org_id, job_id, actor)
    session.commit()
    return out


@app.get("/v1/sourcing/stats")
def sourcing_results(job_id: uuid.UUID | None = Query(None), group: str = Query("channel"), since: str | None = Query(None),
                     org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Results and spend: what each search strategy cost and what it brought."""
    from datetime import date as _date

    from maindscout.api import sourcing_stats

    if job_id is not None:
        from maindscout.api import autosource

        autosource._job(session, org_id, job_id)
    return sourcing_stats.stats(session, org_id, job_id, group, _date.fromisoformat(since) if since else None)


@app.get("/v1/sourcing/settings")
def sourcing_settings(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import autosource

    return {"sourcing_budget_usd": autosource.desk_budget(session, org_id),
            "spent_usd": round(costs.sourcing_spent(session, org_id), 4), "web_ready": bool(env("EXA_API_KEY"))}


class SourcingSettingsBody(BaseModel):
    sourcing_budget_usd: float


@app.put("/v1/sourcing/settings")
def change_sourcing_settings(body: SourcingSettingsBody, org_id: uuid.UUID = Depends(get_org),
                             _owner: auth.Principal = Depends(require_owner), session: Session = Depends(get_session)):
    """The desk's monthly sourcing budget (owners)."""
    from maindscout.api import autosource

    autosource.set_desk_budget(session, org_id, body.sourcing_budget_usd)
    session.commit()
    return {"sourcing_budget_usd": autosource.desk_budget(session, org_id), "spent_usd": round(costs.sourcing_spent(session, org_id), 4)}


@app.get("/v1/off-limits")
def list_off_limits(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Companies never sourced from: active clients and recent placements (derived) and the desk's own list."""
    from maindscout.api import autosource
    from maindscout.db.models import Company, OffLimits

    derived = autosource.off_limits(session, org_id)
    manual = {str(r.company_id): r for r in session.scalars(select(OffLimits).where(OffLimits.org_id == org_id, OffLimits.removed_at.is_(None)))}
    names = dict(session.execute(select(Company.id, Company.name).where(Company.id.in_([uuid.UUID(c) for c in derived] or [None]))).all())
    return {"companies": [{"company_id": cid, "name": names.get(uuid.UUID(cid)), "why": why,
                           "id": str(manual[cid].id) if cid in manual else None,
                           "until": manual[cid].until.isoformat() if cid in manual and manual[cid].until else None}
                          for cid, why in sorted(derived.items(), key=lambda kv: (names.get(uuid.UUID(kv[0])) or "").lower())]}


class OffLimitsBody(BaseModel):
    name: str
    until: str | None = None
    note: str | None = None


@app.post("/v1/off-limits", status_code=201)
def add_off_limits(body: OffLimitsBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                   actor: str = Depends(get_actor)):
    from datetime import date as _date

    from maindscout.db.models import OffLimits

    company, _ = companies.resolve(session, body.name, "human")
    if company is None:
        raise HTTPException(422, f"{body.name!r} is not a company name")
    company = companies.canonical(session, company)
    row = OffLimits(org_id=org_id, company_id=company.id, reason="manual", note=(body.note or "").strip() or None,
                    until=_date.fromisoformat(body.until) if body.until else None, created_by=actor)
    session.add(row)
    session.commit()
    return {"id": str(row.id), "company_id": str(company.id), "name": company.name}


@app.delete("/v1/off-limits/{row_id}")
def remove_off_limits(row_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                      actor: str = Depends(get_actor)):
    from datetime import datetime as _dt, timezone as _tz

    from maindscout.db.models import OffLimits

    row = session.get(OffLimits, row_id)
    if row is None or row.org_id != org_id:
        raise LookupError(f"No off-limits entry {row_id}")
    row.removed_by, row.removed_at = actor, _dt.now(_tz.utc)
    session.commit()
    return {"removed": True}


class PermissionBody(BaseModel):
    job_id: uuid.UUID | None = None
    this_role: bool = False
    other_roles: bool = False
    how: str | None = None
    note: str | None = None


@app.post("/v1/candidates/{candidate_id}/permission", status_code=201)
def record_permission(candidate_id: uuid.UUID, body: PermissionBody, org_id: uuid.UUID = Depends(get_org),
                      session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """What they said yes to: being put forward for this role, and/or for other roles."""
    from maindscout.api import consent

    consent.record(session, org_id, candidate_id, actor, this_role=body.this_role, other_roles=body.other_roles,
                   job_id=body.job_id, how=body.how, note=body.note)
    session.commit()
    return {"permissions": consent.of(session, org_id, candidate_id)}


class NoteBody(BaseModel):
    note: str | None = None


@app.post("/v1/candidates/{candidate_id}/stop")
def stop_contact(candidate_id: uuid.UUID, body: NoteBody | None = None, org_id: uuid.UUID = Depends(get_org),
                 session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """They asked not to be contacted: never suggested or drafted to again."""
    from maindscout.api import consent

    person = consent.stop(session, org_id, candidate_id, actor, (body or NoteBody()).note)
    session.commit()
    return {"do_not_contact_at": person.do_not_contact_at.isoformat() if person.do_not_contact_at else None}


@app.post("/v1/candidates/{candidate_id}/stop/lift")
def lift_stop_contact(candidate_id: uuid.UUID, body: NoteBody, org_id: uuid.UUID = Depends(get_org),
                      session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    from maindscout.api import consent

    consent.lift_stop(session, org_id, candidate_id, actor, body.note or "")
    session.commit()
    return {"do_not_contact_at": None}


@app.get("/v1/companies")
def list_companies(q: str | None = Query(None), org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Companies this desk has touched through people or jobs, most people first; `q` filters by name."""
    return companies.search(session, org_id, q)


@app.get("/v1/companies/{company_id}")
def get_company(company_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """A company: its names, this desk's people who worked there (with title and period), and its jobs here."""
    return companies.company_page(session, org_id, company_id)


class CompanyKeysBody(BaseModel):
    website: str | None = None
    linkedin: str | None = None


@app.put("/v1/companies/{company_id}/keys")
def put_company_keys(company_id: uuid.UUID, body: CompanyKeysBody, org_id: uuid.UUID = Depends(get_org),
                     session: Session = Depends(get_session)):
    """A company's website or LinkedIn page, typed by a person: how Exa confirms it is this company (so a role's talent
    DNA can be learned). A key another company already holds is never moved: a "Same company?" card asks instead."""
    from maindscout.db.models import Company

    company = companies.canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    if body.website and not companies.domain_of(body.website):
        raise ValueError("That is not a company website (a LinkedIn or other profile site is not one): type e.g. buonaventura.it")
    if body.linkedin and not companies.linkedin_of(body.linkedin):
        raise ValueError("Type the company's LinkedIn page, e.g. linkedin.com/company/buonaventura")
    clash = companies.learn_keys(session, company, domain=body.website, linkedin=body.linkedin, org_id=org_id)
    if body.website and companies.domain_of(body.website) and not company.website:
        company.website = f"https://{companies.domain_of(body.website)}"
    session.commit()
    out = companies.company_page(session, org_id, company.id)
    return {**out, "clash": {"id": str(clash.id), "name": clash.name} if clash is not None else None}


class MergeBody(BaseModel):
    into: uuid.UUID


@app.post("/v1/companies/{company_id}/merge")
def merge_company(company_id: uuid.UUID, body: MergeBody, org_id: uuid.UUID = Depends(get_org),
                  session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    keep = companies.merge(session, body.into, company_id, actor, org_id)
    session.commit()
    return {"id": str(keep.id), "name": keep.name}


@app.get("/v1/tasks")
def get_tasks(ids: str = Query(..., description="comma-separated task ids"), org_id: uuid.UUID = Depends(get_org),
              session: Session = Depends(get_session)):
    """Status of background tasks (for showing progress)."""
    from maindscout.db.models import Task

    wanted = [uuid.UUID(i) for i in ids.split(",") if i.strip()][:100]
    # Shared public work (company research) has no desk; the desk that asked for it can still follow it.
    rows = session.scalars(select(Task).where(Task.id.in_(wanted), or_(Task.org_id == org_id, Task.org_id.is_(None))))
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
    """Where people must live for this role (codes or names): the hiring profile's "must live in", the one place the
    role's countries are kept. Its people are re-checked and the sourcing plan follows."""
    from maindscout.api import hiring

    hiring.set_residence(session, org_id, job_id, body.countries, actor)
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


class JobStateBody(BaseModel):
    state: str  # open | on_hold | filled | cancelled
    note: str | None = None


@app.put("/v1/jobs/{job_id}/state")
def put_job_state(job_id: uuid.UUID, body: JobStateBody, org_id: uuid.UUID = Depends(get_org),
                  session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Close a role (on hold, filled, cancelled: sourcing stops, everything is kept) or open it again."""
    from maindscout.api import roles

    roles.set_state(session, org_id, job_id, body.state, actor, body.note)
    session.commit()
    return queries.job_page(session, org_id, job_id)


@app.delete("/v1/jobs/{job_id}")
def delete_job(job_id: uuid.UUID, remove_people: bool = Query(False), org_id: uuid.UUID = Depends(get_org),
               session: Session = Depends(get_session), blobs: BlobStore = Depends(get_blobs), actor: str = Depends(get_actor)):
    """Delete a role added by mistake. `remove_people`: also the people only its own sourcing found (web profiles, on
    no other role), without putting them on the never-again list."""
    from maindscout.api import roles

    counts = roles.delete_role(session, blobs, org_id, job_id, actor, remove_people)
    session.commit()
    return {"deleted": True, "counts": counts}


class HiringCompanyBody(BaseModel):
    name: str


@app.put("/v1/jobs/{job_id}/hiring-company")
def put_hiring_company(job_id: uuid.UUID, body: HiringCompanyBody, org_id: uuid.UUID = Depends(get_org),
                       session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Who is hiring, typed by a person (an anonymised ad names nobody)."""
    from maindscout.api import hiring

    company = hiring.set_hiring_company(session, org_id, job_id, body.name, actor)
    session.commit()
    return {"hiring_company": body.name, "company_id": str(company.id)}


@app.post("/v1/jobs/{job_id}/intake")
def add_intake(job_id: uuid.UUID, body: IntakeBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
               actor: str = Depends(get_actor), llm: LLMClient = Depends(get_llm)):
    """Paste notes from the call with the hiring manager: requirements are read from them, each with its quote."""
    from maindscout.api import hiring

    result = hiring.add_intake(session, org_id, job_id, body.text, actor, llm)
    session.commit()
    return {**result, "job": queries.job_page(session, org_id, job_id)}


@app.post("/v1/jobs/{job_id}/role-brief")
def read_role_brief(job_id: uuid.UUID, reread_notes: bool = False, org_id: uuid.UUID = Depends(get_org),
                    session: Session = Depends(get_session), llm: LLMClient = Depends(get_llm)):
    """Read the role brief (what the hire will really do, from the ad, the notes and research; about a cent), and with
    `reread_notes` read the notes again first with today's reader."""
    from maindscout.api import hiring, role_brief

    notes = hiring.reread_intakes(session, org_id, job_id, llm) if reread_notes else None
    result = role_brief.read(session, org_id, job_id, llm)
    session.commit()
    return {**result, "notes": notes, "brief": role_brief.view(session, job_id)}


class BriefAnswerBody(BaseModel):
    facet: str
    answer: str


@app.post("/v1/jobs/{job_id}/role-brief/answer")
def answer_role_brief(job_id: uuid.UUID, body: BriefAnswerBody, org_id: uuid.UUID = Depends(get_org),
                      session: Session = Depends(get_session), actor: str = Depends(get_actor), llm: LLMClient = Depends(get_llm)):
    """Answer one of the brief's questions: read like notes from the hiring manager, then the brief again (two cents)."""
    from maindscout.api import role_brief

    result = role_brief.answer(session, org_id, job_id, body.facet, body.answer, actor, llm)
    session.commit()
    return {**result, "brief": role_brief.view(session, job_id)}


class TellBody(BaseModel):
    text: str


@app.post("/v1/jobs/{job_id}/tell")
def tell_desk(job_id: uuid.UUID, body: TellBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
              actor: str = Depends(get_actor), llm: LLMClient = Depends(get_llm)):
    """Anything about the role in your own words: read like notes, then the brief again."""
    from maindscout.api import role_brief

    result = role_brief.tell(session, org_id, job_id, body.text, actor, llm)
    session.commit()
    return result


class EditBody(BaseModel):
    text: str
    strength: str | None = None


@app.post("/v1/requirements/{claim_id}/edit")
def edit_requirement(claim_id: uuid.UUID, body: EditBody, org_id: uuid.UUID = Depends(get_org),
                     session: Session = Depends(get_session), actor: str = Depends(get_actor), llm: LLMClient = Depends(get_llm)):
    """A requirement in your own words and how much it matters; its values follow the words."""
    from maindscout.api import hiring

    claim = hiring.edit_requirement(session, org_id, claim_id, body.text, body.strength, actor, llm)
    session.commit()
    return {"id": str(claim.id), "text": claim.payload["text_raw"], "strength": claim.payload["strength"]}


class ConfirmBody(BaseModel):
    ids: list[str]


@app.post("/v1/jobs/{job_id}/requirements/confirm")
def confirm_requirements(job_id: uuid.UUID, body: ConfirmBody, org_id: uuid.UUID = Depends(get_org),
                         session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Confirm the requirements the desk read, together: each approved as read, everyone re-matched once."""
    from maindscout.api import hiring

    result = hiring.confirm(session, org_id, job_id, body.ids, actor)
    session.commit()
    return result


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
    company_words: list[str] | None = None  # an industry as companies describe themselves (leather goods, bags)
    min_staff: int | None = None  # employer: a company size in people (owner, 2026-10-19)
    max_staff: int | None = None
    recent_months: int | None = None  # "not from" a company: leavers of less than this many months count (default 6)


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


_QUERY_CACHE: dict[tuple[uuid.UUID, str], Any] = {}  # per desk: one desk's paid parse is not served to another
_QUERY_LOCK = threading.Lock()


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

        key = (org_id, " ".join(q.lower().split()))
        with _QUERY_LOCK:
            parsed = _QUERY_CACHE.get(key)
        if parsed is None:  # the same search again, by the same desk, costs nothing
            costs.ensure_budget(session, org_id)
            parsed = reader.read(q.strip(), llm)
            costs.record(session, org_id, "search_query", parsed.cost)
            session.commit()
            with _QUERY_LOCK:
                if len(_QUERY_CACHE) >= 500:
                    _QUERY_CACHE.pop(next(iter(_QUERY_CACHE)))  # oldest first
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
        return {"available": False, "reason": str(error), "items": [], "header": brief.header(session, org_id, job_id, candidate_id),
                "contacts": brief.contacts(session, org_id, candidate_id)}
    session.commit()
    return {"available": True, "items": [brief.as_dict(i) for i in items], "header": brief.header(session, org_id, job_id, candidate_id),
            "contacts": brief.contacts(session, org_id, candidate_id)}


@app.post("/v1/candidates/{candidate_id}/documents/{document_id}/approve-all")
def approve_all_from_document(candidate_id: uuid.UUID, document_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org),
                              session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Approve every proposed fact about this person read from this CV, in one act; questions stay one by one."""
    out = review.approve_document(session, org_id, candidate_id, document_id, actor)
    session.commit()
    return out


class MergePeopleBody(BaseModel):
    other_id: uuid.UUID


@app.post("/v1/candidates/{candidate_id}/merge")
def merge_people(candidate_id: uuid.UUID, body: MergePeopleBody, org_id: uuid.UUID = Depends(get_org),
                 session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Same person: two records made one (the older is kept). Can be undone."""
    from maindscout.api import merge

    row = merge.merge(session, org_id, candidate_id, body.other_id, actor)
    session.commit()
    return merge.as_dict(row)


@app.post("/v1/merges/{merge_id}/undo")
def undo_merge(merge_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
               actor: str = Depends(get_actor)):
    from maindscout.api import merge

    row = merge.undo(session, org_id, merge_id, actor)
    session.commit()
    return merge.as_dict(row)


# --- calls: a transcript becomes one Call review, approved in bulk ------------------------------


@app.post("/v1/candidates/{candidate_id}/transcripts", status_code=201)
async def add_transcript(candidate_id: uuid.UUID, file: UploadFile | None = File(None), text: str | None = Form(None),
                         job_id: uuid.UUID | None = Form(None), org_id: uuid.UUID = Depends(get_org),
                         session: Session = Depends(get_session), blobs: BlobStore = Depends(get_blobs),
                         actor: str = Depends(get_actor)):
    """A call transcript, as a file (.txt, .vtt, .srt, .docx) or pasted text. Read in the background into a Call review."""
    from maindscout.api import calls

    if file is not None and file.filename:
        data, _ = await _read(file)
        filename = file.filename
    elif text and text.strip():
        data, filename = text.encode("utf-8"), "pasted call transcript.txt"
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "The text is larger than 20 MB")
    else:
        raise HTTPException(422, "Send a transcript file or paste the text")
    row = calls.add_transcript(session, blobs, org_id, candidate_id, data, filename, actor, job_id)
    session.commit()
    return calls.as_dict(row, session)


@app.get("/v1/candidates/{candidate_id}/calls")
def person_calls(candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """The person's call reviews (newest first) and what they want, as approved."""
    from maindscout.api import calls

    calls._person(session, org_id, candidate_id)
    return {"reviews": [calls.as_dict(r, session) for r in calls.for_person(session, org_id, candidate_id)],
            "preferences": calls.preferences_view(session, org_id, candidate_id)}


@app.get("/v1/call-reviews")
def waiting_call_reviews(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import calls

    return [calls.as_dict(r, session) for r in calls.waiting(session, org_id)]


@app.get("/v1/call-reviews/{review_id}")
def get_call_review(review_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import calls

    return calls.as_dict(calls._review(session, org_id, review_id), session)


class CallApplyBody(BaseModel):
    ticked: list[str] | None = None  # None: the default ticks


@app.post("/v1/call-reviews/{review_id}/apply")
def apply_call_review(review_id: uuid.UUID, body: CallApplyBody, org_id: uuid.UUID = Depends(get_org),
                      session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Approve the ticked lines in one act; the person is matched again once."""
    from maindscout.api import calls

    row = calls.apply(session, org_id, review_id, actor, body.ticked)
    session.commit()
    return calls.as_dict(row, session)


@app.post("/v1/call-reviews/{review_id}/dismiss")
def dismiss_call_review(review_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                        actor: str = Depends(get_actor)):
    from maindscout.api import calls

    row = calls.dismiss(session, org_id, review_id, actor)
    session.commit()
    return calls.as_dict(row, session)


@app.post("/v1/call-reviews/{review_id}/retry")
def retry_call_review(review_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import calls

    row = calls.retry(session, org_id, review_id)
    session.commit()
    return calls.as_dict(row, session)


@app.get("/v1/candidates/{candidate_id}/brief")
def get_person_brief(candidate_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """A Brief without a job (anyone, e.g. someone in the pool): the questions about the person, and how to reach them."""
    from maindscout.api import brief

    try:
        items = brief.build_person(session, org_id, candidate_id)
    except brief.BriefError as error:
        session.rollback()
        return {"available": False, "reason": str(error), "items": [], "header": brief.person_header(session, org_id, candidate_id),
                "contacts": brief.contacts(session, org_id, candidate_id)}
    session.commit()
    return {"available": True, "items": [brief.as_dict(i) for i in items], "header": brief.person_header(session, org_id, candidate_id),
            "contacts": brief.contacts(session, org_id, candidate_id)}


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


# --- relationship memory (Slice 4) ---------------------------------------------------------------

class ActivityBody(BaseModel):
    kind: str
    summary: str
    direction: str | None = None
    occurred_at: str | None = None  # ISO date or date-time; default now
    job_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


def _when(text: str | None):
    from datetime import datetime, timezone

    if not text:
        return None
    when = datetime.fromisoformat(text)
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


@app.post("/v1/candidates/{candidate_id}/activities", status_code=201)
def log_person_activity(candidate_id: uuid.UUID, body: ActivityBody, org_id: uuid.UUID = Depends(get_org),
                        session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Log a call, email, meeting, message or note with a person."""
    from maindscout.api import relationship

    from maindscout.api import outreach

    a = relationship.log(session, org_id, "candidate", candidate_id, body.kind, body.summary, actor, direction=body.direction,
                         occurred_at=_when(body.occurred_at), job_id=body.job_id)
    # About a role, it counts there: "we reached out" is first contact, "they reached out" a reply (x-ray B2).
    outreach.from_activity(session, org_id, candidate_id, body.kind, body.direction, body.job_id, actor, a.occurred_at, body.summary)
    session.commit()
    return {"id": str(a.id)}


@app.post("/v1/companies/{company_id}/activities", status_code=201)
def log_company_activity(company_id: uuid.UUID, body: ActivityBody, org_id: uuid.UUID = Depends(get_org),
                         session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Log a call, email, meeting, message or note with a client (optionally with one of its contacts)."""
    from maindscout.api import companies as comp
    from maindscout.api import relationship
    from maindscout.db.models import Company

    company = comp.canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    a = relationship.log(session, org_id, "company", company.id, body.kind, body.summary, actor, direction=body.direction,
                         occurred_at=_when(body.occurred_at), job_id=body.job_id, contact_id=body.contact_id)
    session.commit()
    return {"id": str(a.id)}


@app.delete("/v1/activities/{activity_id}", status_code=204)
def remove_activity(activity_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import relationship

    relationship.remove_activity(session, org_id, activity_id)
    session.commit()


class TagBody(BaseModel):
    tag: str


@app.post("/v1/candidates/{candidate_id}/tags", status_code=201)
def add_tag(candidate_id: uuid.UUID, body: TagBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
            actor: str = Depends(get_actor)):
    from maindscout.api import relationship

    tag = relationship.add_tag(session, org_id, candidate_id, body.tag, actor)
    session.commit()
    return {"tag": tag}


@app.delete("/v1/candidates/{candidate_id}/tags/{tag}", status_code=204)
def remove_tag(candidate_id: uuid.UUID, tag: str, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import relationship

    relationship.remove_tag(session, org_id, candidate_id, tag)
    session.commit()


@app.get("/v1/tags")
def list_pools(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Tags as talent pools, with how many people are in each."""
    from maindscout.api import relationship

    return relationship.pools(session, org_id)


class ContactBody(BaseModel):
    name: str
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    notes: str | None = None


@app.post("/v1/companies/{company_id}/contacts", status_code=201)
def add_contact(company_id: uuid.UUID, body: ContactBody, org_id: uuid.UUID = Depends(get_org),
                session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Someone we know at a client company (e.g. a hiring manager)."""
    from maindscout.api import companies as comp
    from maindscout.api import relationship
    from maindscout.db.models import Company

    company = comp.canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    c = relationship.add_contact(session, org_id, company.id, body.model_dump(), actor)
    session.commit()
    return {"id": str(c.id)}


@app.delete("/v1/contacts/{contact_id}", status_code=204)
def remove_contact(contact_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import relationship

    relationship.remove_contact(session, org_id, contact_id)
    session.commit()


class LiftBody(BaseModel):
    note: str


@app.post("/v1/blocks/{block_id}/lift")
def lift_block(block_id: uuid.UUID, body: LiftBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
               actor: str = Depends(get_actor)):
    """Lift a client's block (e.g. the client changed its mind), with a note saying why."""
    b = pipeline.lift(session, org_id, block_id, body.note, actor)
    session.commit()
    return {"id": str(b.id), "lifted": b.lifted_at is not None}


@app.get("/v1/freshness")
def refresh_lists(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Who to re-contact (stale people, most valuable first, with why) and which clients to reconnect with."""
    from maindscout.api import freshness

    return {"person_months": freshness.person_months(), "company_months": freshness.company_months(),
            "people": freshness.recontact(session, org_id), "clients": freshness.reconnect(session, org_id)}


# --- import and export (Slice 4, step 4) ---------------------------------------------------------

@app.get("/v1/imports")
def list_imports(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import imports

    return imports.batches(session, org_id)


@app.post("/v1/imports", status_code=201)
async def upload_import(file: UploadFile = File(...), kind: str = Form("candidates"), org_id: uuid.UUID = Depends(get_org),
                        session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Upload a CSV of candidates or clients: a preview, nothing imported yet."""
    from maindscout.api import imports

    raw = await file.read(10 * 1024 * 1024 + 1)  # never buffer more than the limit
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "The file is over 10 MB")
    batch = imports.upload(session, org_id, kind, file.filename, raw, actor)
    session.commit()
    return imports.view(session, batch)


@app.get("/v1/imports/{batch_id}")
def get_import(batch_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import imports

    return imports.view(session, imports.get(session, org_id, batch_id))


class ImportRowsBody(BaseModel):
    row_ids: list[uuid.UUID]


@app.post("/v1/imports/{batch_id}/import")
def import_rows(batch_id: uuid.UUID, body: ImportRowsBody, org_id: uuid.UUID = Depends(get_org),
                session: Session = Depends(get_session), actor: str = Depends(get_actor)):
    """Import the ticked rows (the account holder vouches for them), within the free allowance."""
    from maindscout.api import imports

    result = imports.import_rows(session, org_id, batch_id, body.row_ids, actor)
    session.commit()
    return {**result, "batch": imports.view(session, imports.get(session, org_id, batch_id))}


@app.post("/v1/imports/{batch_id}/quote/accept")
def accept_import_quote(batch_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                        actor: str = Depends(get_actor), _owner: auth.Principal = Depends(require_owner)):
    """Order the paid analysis of the rows beyond the free allowance (compute cost x 1.9)."""
    from maindscout.api import imports

    result = imports.accept_quote(session, org_id, batch_id, actor)
    session.commit()
    return result


@app.get("/v1/export/people.csv")
def export_people(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """The desk's own people as CSV. Always free."""
    from maindscout.api import imports

    return Response(imports.export_people(session, org_id), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="maindscout-people.csv"'})



# --- messages and mailbox (Slice 4, step 5) ------------------------------------------------------

@app.get("/v1/mailbox")
def mailbox_status(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    return mailbox_mod.status(session, org_id)


@app.post("/v1/mailbox/connect/{provider}")
def mailbox_connect(provider: str, org_id: uuid.UUID = Depends(get_org), actor: str = Depends(get_actor),
                    _owner: auth.Principal = Depends(require_owner)):
    """Where to send the person to sign in to Gmail or Outlook."""
    return {"url": mailbox_mod.authorize_url(org_id, provider, actor)}


@app.get("/v1/mailbox/callback/{provider}")
def mailbox_callback(provider: str, code: str | None = None, state: str | None = None, error: str | None = None,
                     session: Session = Depends(get_session)):
    """Google / Microsoft send the browser back here (no operator token: the signed state proves who started it)."""
    from fastapi.responses import RedirectResponse

    cockpit = (env("COCKPIT_URL", "http://localhost:3001") or "").rstrip("/")
    if error or not code or not state:
        return RedirectResponse(f"{cockpit}/mailbox?" + urllib.parse.urlencode({"error": (error or "cancelled")[:200]}))
    try:
        mailbox_mod.complete(session, provider, code, state)
        session.commit()
    except mailbox_mod.MailboxError as failure:
        return RedirectResponse(f"{cockpit}/mailbox?" + urllib.parse.urlencode({"error": str(failure)[:200]}))
    return RedirectResponse(f"{cockpit}/mailbox?connected={provider}")


@app.delete("/v1/mailbox", status_code=204)
def mailbox_disconnect(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                       _owner: auth.Principal = Depends(require_owner)):
    mailbox_mod.disconnect(session, org_id)
    session.commit()


@app.post("/v1/mailbox/sync")
def mailbox_sync_now(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Look at the mailbox now: sent drafts, replies, follow-ups due."""
    from maindscout.api import messages

    result = messages.sync(session, org_id)
    session.commit()
    return result


class DraftBody(BaseModel):
    kind: str
    candidate_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    note: str | None = None
    channel: str = "email"  # email | linkedin


@app.post("/v1/messages", status_code=201)
def draft_message(body: DraftBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session),
                  actor: str = Depends(get_actor), llm: LLMClient = Depends(get_llm)):
    """Draft a message from what may be said outward. Nothing is sent."""
    from maindscout.api import messages

    m = messages.draft(session, org_id, body.kind, actor, llm, candidate_id=body.candidate_id, contact_id=body.contact_id,
                       job_id=body.job_id, note=body.note, channel=body.channel)
    session.commit()
    return messages.as_dict(m)


class EditBody(BaseModel):
    subject: str
    body: str


@app.patch("/v1/messages/{message_id}")
def edit_message(message_id: uuid.UUID, body: EditBody, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    from maindscout.api import messages

    m = messages.edit(session, org_id, message_id, body.subject, body.body)
    session.commit()
    return messages.as_dict(m)


@app.post("/v1/messages/{message_id}/mailbox")
def message_to_mailbox(message_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Put the draft in the connected mailbox's drafts; you send it from there."""
    from maindscout.api import messages

    result = messages.to_mailbox(session, org_id, message_id)
    session.commit()
    return result


@app.post("/v1/messages/{message_id}/sent")
def message_sent(message_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Mark as sent by hand (sent outside a connected mailbox)."""
    from maindscout.api import messages

    m = messages.mark_sent(session, org_id, message_id)
    session.commit()
    return messages.as_dict(m)


@app.post("/v1/messages/{message_id}/replied")
def message_replied(message_id: uuid.UUID, org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Mark as replied by hand: stops the follow-ups."""
    from maindscout.api import messages

    m = messages.mark_replied(session, org_id, message_id)
    session.commit()
    return messages.as_dict(m)



# --- access: sign in, account, members (access plan) ---------------------------------------------------------------

PUBLIC_ROUTES = {"/v1/health", "/v1/auth/login", "/v1/auth/login/code", "/v1/auth/invites/{token}",
                 "/v1/auth/invites/{token}/accept", "/v1/mailbox/callback/{provider}"}


class LoginBody(BaseModel):
    email: str
    password: str


class CodeBody(BaseModel):
    ticket: str
    code: str


def _counted(session: Session, call):
    """Run a sign-in step; a failure's count is kept even though the request fails."""
    try:
        result = call()
    except (auth.AuthError, auth.Locked):
        session.commit()
        raise
    session.commit()
    return result


@app.post("/v1/auth/login")
def auth_login(body: LoginBody, request: Request, session: Session = Depends(get_session)):
    """Email and password: a session token, or a ticket for the two-step code."""
    return _counted(session, lambda: auth.login(session, body.email, body.password, _address(request)))


@app.post("/v1/auth/login/code")
def auth_login_code(body: CodeBody, request: Request, session: Session = Depends(get_session)):
    return _counted(session, lambda: auth.login_code(session, body.ticket, body.code, _address(request)))


@app.post("/v1/auth/logout", status_code=204)
def auth_logout(p: auth.Principal = Depends(get_principal_any), session: Session = Depends(get_session)):
    auth.logout(session, p.session_id)
    session.commit()


@app.get("/v1/auth/me")
def auth_me(p: auth.Principal = Depends(get_principal_any), session: Session = Depends(get_session)):
    return auth.me(session, p)


class PasswordBody(BaseModel):
    current: str
    new: str


@app.post("/v1/auth/password", status_code=204)
def auth_password(body: PasswordBody, p: auth.Principal = Depends(get_principal_any), session: Session = Depends(get_session)):
    """Change your password; your other browser sessions end."""
    auth.change_password(session, p, body.current, body.new)
    session.commit()


@app.post("/v1/auth/two-step/start")
def auth_two_step_start(p: auth.Principal = Depends(get_principal_any), session: Session = Depends(get_session)):
    """A new secret for an authenticator app; it is active only after a code from it is confirmed."""
    from maindscout.db.models import AppUser

    user = session.get(AppUser, p.user_id)
    if user.totp_enabled:
        raise auth.AccessError("Two-step verification is already on")
    out = auth.start_totp(session, user)
    session.commit()
    return out


class TwoStepBody(BaseModel):
    code: str


@app.post("/v1/auth/two-step/confirm", status_code=204)
def auth_two_step_confirm(body: TwoStepBody, p: auth.Principal = Depends(get_principal_any), session: Session = Depends(get_session)):
    from maindscout.db.models import AppUser

    auth.confirm_totp(session, session.get(AppUser, p.user_id), body.code)
    session.commit()


class DisableBody(BaseModel):
    password: str


@app.post("/v1/auth/two-step/disable", status_code=204)
def auth_two_step_disable(body: DisableBody, p: auth.Principal = Depends(get_principal), session: Session = Depends(get_session)):
    from maindscout.db.models import AppUser

    roles = [d["role"] for d in auth.me(session, p)["desks"]]
    auth.disable_totp(session, session.get(AppUser, p.user_id), body.password, roles)
    session.commit()


@app.post("/v1/auth/sessions/end-others")
def auth_end_others(p: auth.Principal = Depends(get_principal_any), session: Session = Depends(get_session)):
    n = auth.revoke_sessions(session, p.user_id, keep=p.session_id, kinds=("web",))
    session.commit()
    return {"ended": n}


@app.get("/v1/auth/invites/{token}")
def auth_invite(token: str, session: Session = Depends(get_session)):
    return auth.invite_info(session, token)


class AcceptBody(BaseModel):
    password: str
    name: str | None = None


@app.post("/v1/auth/invites/{token}/accept")
def auth_invite_accept(token: str, body: AcceptBody, session: Session = Depends(get_session)):
    out = auth.accept_invite(session, token, body.password, body.name)
    session.commit()
    return out


@app.get("/v1/members")
def get_members(p: auth.Principal = Depends(require_owner), session: Session = Depends(get_session)):
    return auth.members(session, p.org_id)


class InviteBody(BaseModel):
    email: str
    role: str = "recruiter"


@app.post("/v1/members/invites", status_code=201)
def invite_member(body: InviteBody, p: auth.Principal = Depends(require_owner), session: Session = Depends(get_session)):
    """A one-time link to join this desk (valid 7 days). Nothing is emailed: send the link yourself."""
    out = auth.create_invite(session, p.org_id, body.email, body.role, p.email)
    session.commit()
    return out


class RoleBody(BaseModel):
    role: str


@app.patch("/v1/members/{user_id}", status_code=204)
def change_member_role(user_id: uuid.UUID, body: RoleBody, p: auth.Principal = Depends(require_owner),
                       session: Session = Depends(get_session)):
    auth.set_role(session, p.org_id, user_id, body.role)
    session.commit()


@app.delete("/v1/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, p: auth.Principal = Depends(require_owner), session: Session = Depends(get_session)):
    """Remove someone from this desk; their sessions for it end at once."""
    auth.remove_member(session, p.org_id, user_id)
    session.commit()


@app.post("/v1/members/{user_id}/reset", status_code=201)
def reset_member(user_id: uuid.UUID, p: auth.Principal = Depends(require_owner), session: Session = Depends(get_session)):
    """A one-time link (24 hours) to set a new password; it also clears two-step codes (a lost phone) and ends the
    person's sessions once used."""
    out = auth.reset_link(session, p.org_id, user_id, p.email)
    session.commit()
    return out


# --- navigation: sidebar counts, ⌘K lookup, Today (design plan) ----------------------------------------------------

@app.get("/v1/nav")
def nav(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """Counts for the sidebar (cheap: a few aggregates)."""
    from maindscout.api import overview

    return overview.nav_counts(session, org_id)


@app.get("/v1/lookup")
def lookup(q: str = Query("", max_length=200), org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """People, jobs and companies whose name contains `q` (for ⌘K)."""
    from maindscout.api import overview

    return overview.lookup(session, org_id, q)


@app.get("/v1/today")
def today(org_id: uuid.UUID = Depends(get_org), session: Session = Depends(get_session)):
    """The start of the day: priority people per job, decisions waiting, people going stale, recent activity."""
    from maindscout.api import overview

    return overview.today(session, org_id)
