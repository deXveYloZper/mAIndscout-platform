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

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from maindscout.db.models import Task

log = logging.getLogger("maindscout.tasks")
HANDLERS: dict[str, Callable[[Session, Task], dict[str, Any]]] = {}


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
    return task


def claim(session: Session, worker: str) -> Task | None:
    """Take the most urgent ready task, skipping ones other workers hold."""
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
    with factory() as session:
        task = session.get(Task, task_id)
        try:
            result = execute(session, task)
            task = session.get(Task, task_id)
            task.status, task.result, task.finished_at, task.error = "done", result, datetime.now(timezone.utc), None
            session.commit()
        except Exception as error:  # the task failed: roll its work back, record why, maybe retry
            session.rollback()
            task = session.get(Task, task_id)
            task.error = f"{type(error).__name__}: {error}"[:2000]
            log.warning("task %s %s failed: %s", task.kind, task.id, task.error)
            log.debug(traceback.format_exc())
            if task.attempts >= task.max_attempts or getattr(error, "permanent", False):
                task.status, task.finished_at = "failed", datetime.now(timezone.utc)
            else:
                task.status = "queued"
                task.run_after = datetime.now(timezone.utc) + timedelta(seconds=5 * 2 ** task.attempts)
            session.commit()
    return True


def drain(factory, limit: int = 1000) -> int:
    """Run tasks until none is ready (used by tests and the eval)."""
    done = 0
    while done < limit and run_one(factory, "drain"):
        done += 1
    return done


def work_forever(factory, name: str, idle_seconds: float = 1.0, stop: threading.Event | None = None) -> None:
    log.info("worker %s started", name)
    while stop is None or not stop.is_set():
        try:
            if not run_one(factory, name):
                time.sleep(idle_seconds)
        except Exception:  # never let one bad loop kill the worker
            log.exception("worker %s loop error", name)
            time.sleep(idle_seconds)


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
