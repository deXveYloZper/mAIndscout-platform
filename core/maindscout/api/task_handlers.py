"""What each kind of background task does. Every handler works through `api/` functions, inside the task's
own transaction; a failure rolls back everything it did."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from maindscout.api import calls, hiring, messages, process, profiles, research
from maindscout.api.tasks import handler
from maindscout.db.models import Task
from maindscout.intelligence.llm import LLMClient, XaiClient
from maindscout.settings import env
from maindscout.storage import LocalBlobStore

# Replaced in tests; the real client otherwise.
def _chat_client() -> LLMClient:
    from maindscout.intelligence.recording import wrap_chat

    return wrap_chat(XaiClient)


llm_factory: Callable[[], LLMClient] = _chat_client
blob_factory: Callable[[], Any] = lambda: LocalBlobStore(env("BLOB_DIR"))


def _search_client():
    from maindscout.intelligence.recording import wrap_search
    from maindscout.intelligence.research import XaiSearchClient

    return wrap_search(XaiSearchClient)


search_factory: Callable[[], Any] = _search_client


def _exa_client():
    """Exa for sourcing, recorded and replayed like the model; None when no key is set (the pool only)."""
    from maindscout.intelligence.exa import ExaClient, ExaKeyMissing
    from maindscout.intelligence.recording import mode, wrap_exa

    if mode() != "replay" and not env("EXA_API_KEY"):
        return None
    try:
        return wrap_exa(ExaClient)
    except ExaKeyMissing:
        return None


exa_factory: Callable[[], Any] = _exa_client


@handler("process_document")
def process_document(session: Session, task: Task) -> dict[str, Any]:
    p = task.payload
    result = process.process_document(
        session, blob_factory(), llm_factory(), org_id=task.org_id, document_id=uuid.UUID(p["document_id"]),
        job_id=uuid.UUID(p["job_id"]) if p.get("job_id") else None, force=bool(p.get("force")))
    return {"status": result.status, "subject_type": result.subject_type,
            "subject_id": str(result.subject_id) if result.subject_id else None,
            "job_id": str(result.job_id) if result.job_id else None, "band": result.band, "reason": result.reason,
            "span_failures": len(result.span_failures), "usd": result.cost.get("usd", 0) if result.cost else 0}


@handler("research_company")
def research_company(session: Session, task: Task) -> dict[str, Any]:
    p = task.payload
    return research.run(session, uuid.UUID(p["company_id"]), p.get("context", ""), search_factory(),
                        force=bool(p.get("force")), task_id=task.id)


@handler("profile_candidate")
def profile_candidate(session: Session, task: Task) -> dict[str, Any]:
    from maindscout.api.coverage import discovered_only

    cid = uuid.UUID(task.payload["candidate_id"])
    # Someone known only from a public profile: their career reading, but no paid university research (phase 1b).
    return profiles.run(session, task.org_id, cid, llm_factory, task_id=task.id,
                        search_factory=None if discovered_only(session, cid) else search_factory)


@handler("profile_job")
def profile_job(session: Session, task: Task) -> dict[str, Any]:
    return hiring.from_ad(session, uuid.UUID(task.payload["job_id"]), llm_factory(), force=bool(task.payload.get("force")), task_id=task.id)


@handler("rematch_job")
def rematch_job(session: Session, task: Task) -> dict[str, Any]:
    from maindscout.api.process import retriage_job

    p = task.payload
    return {"band_changes": len(retriage_job(session, task.org_id, uuid.UUID(p["job_id"]), p.get("cause") or {"act": "rematch"},
                                             p.get("actor") or "system"))}


@handler("read_transcript")
def read_transcript(session: Session, task: Task) -> dict[str, Any]:
    """Read one call transcript into its Call review. Out of budget or the model unreachable: the review says so
    and waits for "Try again" (a failure here would otherwise leave it reading for ever)."""
    from maindscout.api.costs import BudgetExceeded
    from maindscout.intelligence.llm import LLMError

    review_id = uuid.UUID(task.payload["review_id"])
    try:
        return calls.read(session, task.org_id, review_id, llm_factory(), task_id=task.id)
    except BudgetExceeded:
        calls.fail(session, review_id, "This month's model budget is spent: try again when it is raised or next month.")
    except LLMError as error:
        calls.fail(session, review_id, f"The model could not be reached ({error}): try again later.")
    return {"status": "failed"}


@handler("sourcing_strategy")
def sourcing_strategy(session: Session, task: Task) -> dict[str, Any]:
    """Build a role's strategy: talent DNA and the tiered target list (needs Exa)."""
    from maindscout.api import autosource, strategy

    caller = exa_factory()
    if caller is None:
        return {"status": "skipped", "reason": "Web search is not set up (no EXA_API_KEY)"}
    try:
        return strategy.build(session, task.org_id, uuid.UUID(task.payload["job_id"]), caller, task.payload.get("actor") or "system",
                              task_id=task.id)
    except autosource.SourcingEngineError as error:
        return {"status": "skipped", "reason": str(error)}


@handler("sourcing_run")
def sourcing_run(session: Session, task: Task) -> dict[str, Any]:
    """One run of a role's sourcing plan (scheduled by the clock, or "Search now")."""
    from maindscout.api import autosource

    p = task.payload
    try:
        row = autosource.run(session, blob_factory(), task.org_id, uuid.UUID(p["job_id"]), p.get("trigger", "schedule"),
                             exa_factory(), actor=p.get("actor") or "system", task_id=task.id)
    except autosource.SourcingEngineError as error:
        return {"status": "skipped", "reason": str(error)}
    return {"status": row.status, "stop_reason": row.stop_reason, "found": row.found, "new": row.new, "strong": row.strong,
            "cost_usd": float(row.cost_usd or 0)}


@handler("mailbox_sync")
def mailbox_sync(session: Session, task: Task) -> dict[str, Any]:
    return messages.sync(session, task.org_id)
