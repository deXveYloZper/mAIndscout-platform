"""What each kind of background task does. Every handler works through `api/` functions, inside the task's
own transaction; a failure rolls back everything it did."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from maindscout.api import process
from maindscout.api.tasks import handler
from maindscout.db.models import Task
from maindscout.intelligence.llm import LLMClient, XaiClient
from maindscout.settings import env
from maindscout.storage import LocalBlobStore

# Replaced in tests; the real client otherwise.
llm_factory: Callable[[], LLMClient] = lambda: XaiClient()
blob_factory: Callable[[], Any] = lambda: LocalBlobStore(env("BLOB_DIR"))


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
