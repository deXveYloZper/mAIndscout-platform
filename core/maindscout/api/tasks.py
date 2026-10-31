"""Background tasks: a Postgres queue (FOR UPDATE SKIP LOCKED) and the workers that run it.

Uploads return at once; reading a CV, researching a company and building profiles run here, in parallel across
workers, each task in its own transaction. Failed tasks retry with backoff; a task that keeps failing stops with
its error visible. No external queue or orchestrator is needed until long-running conversations arrive (Slice 4).
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from maindscout.db.models import Task

log = logging.getLogger("maindscout.tasks")
HANDLERS: dict[str, Callable[[Session, Task], dict[str, Any]]] = {}
# An idle worker looks at the queue less and less often, up to IDLE_MAX seconds apart; a task queued in this process
# wakes the workers as soon as it is committed, so a button's work still starts at once (2026-10-29: two workers
# idling at one look a second each made ~170,000 queries a day on a desk with nothing to do).
IDLE_MIN, IDLE_MAX = 1.0, 15.0
_wake = threading.Event()


def handler(kind: str):
    """Register the function that runs tasks of this kind. It gets the session and the task; returns a result dict."""
    def register(fn):
        HANDLERS[kind] = fn
        return fn
    return register


def enqueue(session: Session, org_id: uuid.UUID | None, kind: str, payload: dict[str, Any], *, priority: int = 100,
            dedupe_key: str | None = None, max_attempts: int = 3) -> Task:
    """Add a task. With a dedupe key, an equal task that is still queued or running is returned instead."""
    if dedupe_key:
        existing = session.scalar(select(Task).where(Task.dedupe_key == dedupe_key, Task.status.in_(("queued", "running"))))
        if existing:
            return existing
    task = Task(org_id=org_id, kind=kind, payload=payload, priority=priority, dedupe_key=dedupe_key, max_attempts=max_attempts)
    session.add(task)
    session.flush()
    if not event.contains(session, "after_commit", _wake_workers):
        event.listen(session, "after_commit", _wake_workers)  # a session lives for one request or task
    return task


def _wake_workers(_session=None) -> None:
    """New work is committed: idle workers look at the queue now instead of at their next look."""
    _wake.set()


STALE_AFTER = timedelta(minutes=30)  # far longer than any task takes; only a crashed process leaves one this old
_last_reclaim = 0.0


def reclaim_stale(session: Session, older_than: timedelta = STALE_AFTER) -> int:
    """Tasks left `running` by a process that died: back in the queue (or failed once out of attempts), which also
    frees their dedupe key for new work."""
    cutoff = datetime.now(timezone.utc) - older_than
    stale = list(session.scalars(select(Task).where(Task.status == "running", Task.started_at < cutoff).with_for_update(skip_locked=True)))
    for task in stale:
        task.error = f"abandoned while running (started {task.started_at.isoformat()})"
        if task.attempts >= task.max_attempts:
            task.status, task.finished_at = "failed", datetime.now(timezone.utc)
        else:
            task.status, task.locked_by, task.run_after = "queued", None, datetime.now(timezone.utc)
    session.commit()
    return len(stale)


def claim(session: Session, worker: str) -> Task | None:
    """Take the most urgent ready task, skipping ones other workers hold."""
    global _last_reclaim
    if time.monotonic() - _last_reclaim > 60:
        _last_reclaim = time.monotonic()
        reclaim_stale(session)
    row = session.execute(text(
        "SELECT id FROM task WHERE status = 'queued' AND run_after <= now() "
        "ORDER BY priority, created_at FOR UPDATE SKIP LOCKED LIMIT 1")).first()
    if row is None:
        return None
    task = session.get(Task, row[0])
    task.status, task.locked_by, task.started_at, task.attempts = "running", worker, datetime.now(timezone.utc), task.attempts + 1
    session.commit()
    return task


def execute(session: Session, task: Task) -> dict[str, Any]:
    """Run one task's handler in the given session (the caller commits or rolls back)."""
    fn = HANDLERS.get(task.kind)
    if fn is None:
        raise RuntimeError(f"No handler for task kind {task.kind!r}")
    return fn(session, task) or {}


def run_one(factory, worker: str = "worker") -> bool:
    """Claim and run one task. Returns False when the queue had nothing ready."""
    with factory() as session:
        task = claim(session, worker)
        if task is None:
            return False
        task_id = task.id
    from maindscout import activity

    with factory() as session:
        task = session.get(Task, task_id)
        payload = task.payload or {}
        with activity.about(org_id=task.org_id, job_id=payload.get("job_id"), task_id=task.id, actor=payload.get("actor")):
            _run(session, task, task_id, activity)
    return True


# Long sourcing work adds shared companies inside a transaction of several minutes, so two such tasks at once wait for
# each other's new rows (2026-10-30: three roles' company lists built at once; two of them added "Skyrora" and
# "Kongsberg" in opposite order and Postgres ended both as a deadlock). They take turns across the desk: a task whose
# turn has not come waits in the queue, its attempt not spent, and the worker moves on to other work.
ONE_AT_A_TIME = frozenset({"sourcing_strategy", "sourcing_run"})
TURN_KEY = "maindscout:long sourcing work"
TURN_WAIT = timedelta(seconds=15)
_waiting_noted: set[uuid.UUID] = set()


def _my_turn(session, task: Task) -> bool:
    """True for every other kind; for long sourcing work, the desk-wide turn, held until this task's transaction ends."""
    if task.kind not in ONE_AT_A_TIME:
        return True
    return bool(session.scalar(text("SELECT pg_try_advisory_xact_lock(hashtext(:k))"), {"k": TURN_KEY}))


def _deadlock(error: Exception) -> bool:
    from psycopg import errors

    return isinstance(getattr(error, "orig", None), errors.DeadlockDetected)


def _run(session, task: Task, task_id, activity) -> None:
    kind = task.kind
    if not _my_turn(session, task):
        task.status, task.locked_by, task.attempts = "queued", None, task.attempts - 1
        task.run_after = datetime.now(timezone.utc) + TURN_WAIT
        session.commit()
        if task_id not in _waiting_noted:  # said once, not every 15 seconds
            _waiting_noted.add(task_id)
            activity.step(f"{LABEL.get(kind, kind)} waits its turn: another role's search or company list is running")
        return
    _waiting_noted.discard(task_id)
    started = datetime.now(timezone.utc)
    try:
        result = execute(session, task)
        task = session.get(Task, task_id)
        task.status, task.result, task.finished_at, task.error = "done", result, datetime.now(timezone.utc), None
        session.commit()
        secs = (datetime.now(timezone.utc) - started).total_seconds()
        if kind not in QUIET:
            activity.note("task", f"{LABEL.get(kind, kind)}: done in {secs:.1f}s{_said(result)}",
                          {"kind": kind, "result": result, "seconds": round(secs, 1)})
    except Exception as error:  # the task failed: roll its work back, record why, maybe retry
        paid = list(session.info.pop("paid", []))
        session.rollback()
        from maindscout.db.models import CostEntry

        for row in paid:  # paid calls stay in the ledger even when the task's work is undone
            session.add(CostEntry(**row))
        task = session.get(Task, task_id)
        task.error = f"{type(error).__name__}: {error}"[:2000]
        log.warning("task %s %s failed: %s", task.kind, task.id, task.error)
        log.debug(traceback.format_exc())
        # A deadlock is another task's timing, not this task's fault: one more try, even for paid work run only once.
        again = _deadlock(error) and task.attempts <= task.max_attempts
        if (task.attempts >= task.max_attempts and not again) or getattr(error, "permanent", False):
            task.status, task.finished_at = "failed", datetime.now(timezone.utc)
        else:
            task.status = "queued"
            task.run_after = datetime.now(timezone.utc) + timedelta(seconds=5 * 2 ** task.attempts)
        session.commit()
        activity.error(f"{LABEL.get(kind, kind)} failed{' (will retry)' if task.status == 'queued' else ''}: "
                       f"{type(error).__name__}: {str(error)[:200]}", error, {"kind": kind, "attempt": task.attempts})


# Plain names for the activity log; the many per-person readings are noted only when they fail.
LABEL = {"sourcing_run": "Search", "sourcing_strategy": "Build the company list", "profile_job": "Read the hiring profile",
         "profile_candidate": "Career reading", "profile_company": "Company profile", "research_company": "Company research",
         "read_practices": "Read a company's job adverts", "evidence_check": "Deeper public check",
         "read_transcript": "Read a call", "process_document": "Read an upload", "rematch_job": "Re-rate the role",
         "mailbox_sync": "Mailbox check", "work_reading": "Read their work against the role"}
# Their results hold a person's words or are routine: noted only when they fail.
QUIET = {"profile_candidate", "profile_company", "evidence_check", "mailbox_sync", "work_reading"}


def _said(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    bits = [f"{k} {result[k]}" for k in ("status", "stop_reason", "reason", "found", "new", "strong", "round") if result.get(k) not in (None, "", [])]
    return (" · " + ", ".join(str(b) for b in bits)) if bits else ""


def drain(factory, limit: int = 1000) -> int:
    """Run tasks until none is ready (used by tests and the eval)."""
    done = 0
    while done < limit and run_one(factory, "drain"):
        done += 1
    return done


def idle_wait(idle: float) -> float:
    """Wait while the queue is empty: until new work is committed, or `idle` seconds. Returns the next wait: back to the
    shortest after a wake, otherwise twice as long, up to IDLE_MAX (work queued for later, or by another process, is
    therefore seen within IDLE_MAX seconds)."""
    if _wake.wait(idle):
        _wake.clear()
        return IDLE_MIN
    return min(idle * 2, IDLE_MAX)


def work_forever(factory, name: str, stop: threading.Event | None = None) -> None:
    log.info("worker %s started", name)
    idle = IDLE_MIN
    while stop is None or not stop.is_set():
        try:
            if run_one(factory, name):
                idle = IDLE_MIN
            else:
                idle = idle_wait(idle)
        except Exception:  # never let one bad loop kill the worker
            log.exception("worker %s loop error", name)
            idle = idle_wait(idle)


def start_threads(factory, count: int) -> list[threading.Thread]:
    threads = []
    for i in range(count):
        t = threading.Thread(target=work_forever, args=(factory, f"worker-{i + 1}"), daemon=True)
        t.start()
        threads.append(t)
    return threads


def as_dict(t: Task) -> dict[str, Any]:
    return {"id": str(t.id), "kind": t.kind, "status": t.status, "attempts": t.attempts, "error": t.error,
            "result": t.result, "created_at": t.created_at.isoformat() if t.created_at else None,
            "finished_at": t.finished_at.isoformat() if t.finished_at else None}
