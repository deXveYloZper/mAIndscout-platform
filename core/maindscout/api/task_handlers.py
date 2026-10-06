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
    return profiles.run(session, task.org_id, uuid.UUID(task.payload["candidate_id"]), llm_factory, task_id=task.id,
                        search_factory=search_factory)


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


@handler("mailbox_sync")
def mailbox_sync(session: Session, task: Task) -> dict[str, Any]:
    return messages.sync(session, task.org_id)
