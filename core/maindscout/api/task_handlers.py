"""What each kind of background task does. Every handler works through `api/` functions, inside the task's
own transaction; a failure rolls back everything it did."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import String, func
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


@handler("profile_company")
def profile_company(session: Session, task: Task) -> dict[str, Any]:
    """A company from a CV: its Exa profile, confirmed by its exact name and the job's country (x-ray C)."""
    from maindscout.api import company_profiles
    from maindscout.db.models import Company

    caller = exa_factory()
    company = session.get(Company, uuid.UUID(task.payload["company_id"]))
    if caller is None or company is None:
        return {"status": "skipped", "reason": "no web search (EXA_API_KEY)" if caller is None else "no such company"}
    ok = company_profiles.by_name_and_place(session, company, task.payload.get("country"), caller, task_id=task.id)
    return {"status": "profiled" if ok else "not_confirmed"}


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


def _researcher():
    """The competitor research's web search (Grok), with a deeper search budget than a company's facts need."""
    from maindscout.intelligence.recording import wrap_search
    from maindscout.intelligence.research import XaiSearchClient

    try:
        return wrap_search(lambda: XaiSearchClient(max_tool_calls=12, timeout=300))
    except Exception:  # no model key: the list is built from Exa searches alone
        return None


@handler("sourcing_strategy")
def sourcing_strategy(session: Session, task: Task) -> dict[str, Any]:
    """Build a role's strategy: talent DNA and the tiered target list (needs Exa)."""
    from maindscout.api import autosource, strategy

    caller = exa_factory()
    if caller is None:
        return {"status": "skipped", "reason": "Web search is not set up (no EXA_API_KEY)"}
    try:
        return strategy.build(session, task.org_id, uuid.UUID(task.payload["job_id"]), caller, task.payload.get("actor") or "system",
                              task_id=task.id, researcher=_researcher())
    except autosource.SourcingEngineError as error:
        return {"status": "skipped", "reason": str(error)}


# "Search now" goes on, batch after batch, until the role has its strong suggestions (owner, 2026-10-21: "we should not
# stop until we have found at least 10-15 strong candidates"): each batch's career readings first, since nobody is strong
# before them; at most this many batches, and always within the role's and the desk's budgets.
MAX_ROUNDS = 8
READ_WAIT = timedelta(seconds=60)
MAX_WAITS = 20  # about 20 minutes of waiting for one batch's readings


def _next_round(session: Session, task: Task, payload: dict[str, Any], after: timedelta) -> Task:
    """The next round of the same search, under the same key (the tab keeps showing "Searching…")."""
    nxt = Task(org_id=task.org_id, kind="sourcing_run", payload=payload, priority=task.priority, dedupe_key=task.dedupe_key,
               max_attempts=1, run_after=datetime.now(timezone.utc) + after)
    session.add(nxt)
    session.flush()
    return nxt


@handler("sourcing_run")
def sourcing_run(session: Session, task: Task) -> dict[str, Any]:
    """One run of a role's sourcing plan (scheduled by the clock, or "Search now", which then goes on by itself)."""
    from sqlalchemy import select

    from maindscout.api import autosource
    from maindscout.db.models import SourcingHit

    p = task.payload
    job_id = uuid.UUID(p["job_id"])
    if p.get("trigger") == "continue":
        hits = select(SourcingHit.candidate_id.cast(String)).where(SourcingHit.job_id == job_id)
        reading = session.scalar(select(func.count()).select_from(Task).where(
            Task.kind == "profile_candidate", Task.status.in_(("queued", "running")), Task.payload["candidate_id"].astext.in_(hits)))
        if reading and p.get("waits", 0) < MAX_WAITS:
            _next_round(session, task, {**p, "waits": p.get("waits", 0) + 1}, READ_WAIT)
            return {"status": "waiting", "reason": f"{reading} career readings first"}
    try:
        row = autosource.run(session, blob_factory(), task.org_id, job_id, p.get("trigger", "schedule"),
                             exa_factory(), actor=p.get("actor") or "system", task_id=task.id)
    except autosource.SourcingEngineError as error:
        return {"status": "skipped", "reason": str(error)}
    rounds = p.get("round", 1)
    more = row.stop_reason in ("run_limit", "searched") and p.get("trigger") in ("manual", "continue") and rounds < MAX_ROUNDS
    if more:  # more to search and not enough strong yet: the next batch, once this one is read
        _next_round(session, task, {"job_id": p["job_id"], "trigger": "continue", "actor": p.get("actor"), "round": rounds + 1,
                                    "waits": 0}, READ_WAIT)
    return {"status": row.status, "stop_reason": row.stop_reason, "found": row.found, "new": row.new, "strong": row.strong,
            "cost_usd": float(row.cost_usd or 0), "round": rounds, "next_round": more}


@handler("read_practices")
def read_practices(session: Session, task: Task) -> dict[str, Any]:
    """What a company uses, from its own job adverts (employer evidence); its people are matched again after."""
    from maindscout.api import practices

    caller = exa_factory()
    if caller is None:
        return {"status": "skipped", "reason": "no web search (EXA_API_KEY)"}
    p = task.payload
    return practices.read_company(session, task.org_id, uuid.UUID(p["job_id"]), uuid.UUID(p["company_id"]), caller,
                                  llm_factory(), title=p.get("title"), task_id=task.id)


@handler("evidence_check")
def evidence_check(session: Session, task: Task) -> dict[str, Any]:
    """A strong match's public work against the role (their name with their company may be searched)."""
    from maindscout.api import evidence

    caller = exa_factory()
    if caller is None:
        return {"status": "skipped", "reason": "no web search (EXA_API_KEY)"}
    p = task.payload
    return evidence.run(session, blob_factory(), task.org_id, uuid.UUID(p["job_id"]), uuid.UUID(p["candidate_id"]), caller,
                        llm_factory(), task_id=task.id)


@handler("mailbox_sync")
def mailbox_sync(session: Session, task: Task) -> dict[str, Any]:
    return messages.sync(session, task.org_id)
