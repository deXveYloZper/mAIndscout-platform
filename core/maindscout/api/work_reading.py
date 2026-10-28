"""The core-work reader on each person (owner, 2026-10-27: "yes build the reader, test on Ferrari and Bonaventura").

- **When:** everyone strong or possible on a role (bands priority and review later) is read once the role has
  confirmed work lines: all of them when the lines are confirmed (`queue_role`), and anyone who becomes strong or
  possible later (`maybe_queue`, called by matching). Read again when the confirmed lines change, or their CV arrives.
  Never someone who asked not to be contacted. Off with WORK_READER_AUTO=false.
- **What it reads:** their CV when there is one, else their public profile's own words (titles and skills lists are
  never evidence).
- **What it keeps:** the lines their words show, each with its checked quote, and the look-alikes; the task's
  result, erased with the person. What the model writes about them in its own words is never kept.
- **What it does:** orders people within their band (`order_key`) and shows its quotes on the card. It never changes
  a band, a tier or a rating.
- **Cost:** about a fifth of a cent a person (the desk's model), inside the monthly model budget.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs, work_lines
from maindscout.db.models import Candidate, CandidateJob, Claim, Document, DocumentSubject, ExtractionArtifact, Job, Task
from maindscout.intelligence import work_reader as engine

KIND = "work_reading"
PURPOSE = "work_reading"
BANDS = ("priority", "review_later")
LIVE = ("proposed", "approved")


def key(job_id, candidate_id) -> str:
    return f"work:{job_id}:{candidate_id}"


def _auto() -> bool:
    from maindscout.settings import env

    return (env("WORK_READER_AUTO", "true") or "").lower() not in ("0", "false", "no", "off")


def latest(session: Session, job_id, candidate_id) -> Task | None:
    return session.scalar(select(Task).where(Task.kind == KIND, Task.dedupe_key == key(job_id, candidate_id))
                          .order_by(Task.created_at.desc()).limit(1))


def _source(session: Session, candidate_id: uuid.UUID) -> tuple[Document, ExtractionArtifact] | None:
    """Their CV when there is one (their own document, the most of their words), else their public profile."""
    rows = session.execute(select(Document, ExtractionArtifact).join(DocumentSubject, DocumentSubject.document_id == Document.id)
                           .join(ExtractionArtifact, ExtractionArtifact.document_id == Document.id)
                           .where(DocumentSubject.subject_id == candidate_id, DocumentSubject.subject_type == "candidate",
                                  Document.doc_type.in_(("cv", "web_profile")), ExtractionArtifact.method == "text_layer")
                           .order_by((Document.doc_type != "cv"), Document.created_at.desc())).first()
    return (rows[0], rows[1]) if rows else None


def queue(session: Session, org_id: uuid.UUID, job_id, candidate_id, actor: str = "system") -> Task:
    from maindscout.api import tasks

    return tasks.enqueue(session, org_id, KIND, {"job_id": str(job_id), "candidate_id": str(candidate_id), "actor": actor},
                         priority=140, dedupe_key=key(job_id, candidate_id))


def maybe_queue(session: Session, pair: CandidateJob, band: str) -> bool:
    """Read a strong or possible person once the role has confirmed lines; again when the lines change or a CV arrives
    (called from matching, so it stays cheap)."""
    if band not in BANDS or not _auto():
        return False
    version = work_lines.version(session, pair.job_id)
    if version is None:
        return False
    t = latest(session, pair.job_id, pair.candidate_id)
    if t is not None:
        if t.status in ("queued", "running"):
            return False
        r = t.result or {}
        if r.get("version") == version:
            src = _source(session, pair.candidate_id)
            if r.get("document_id") == (str(src[0].id) if src else None):
                return False  # read against these lines, from the text they have now
    queue(session, pair.org_id, pair.job_id, pair.candidate_id)
    return True


def queue_role(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> int:
    """Everyone strong or possible on the role who has no reading against the confirmed lines yet."""
    pairs = session.scalars(select(CandidateJob).where(CandidateJob.job_id == job_id, CandidateJob.triage_band.in_(BANDS)))
    return sum(maybe_queue(session, p, p.triage_band) for p in pairs)


def _titles(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID) -> list[str]:
    """Their job titles as the desk read them: a quote inside one is a title, never evidence."""
    steps = session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE)))
    return [t for t in ((c.approved_view or c.payload).get("title_raw") for c in steps) if t]


def run(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, client,
        task_id: uuid.UUID | None = None) -> dict[str, Any]:
    job, person = session.get(Job, job_id), session.get(Candidate, candidate_id)
    if job is None or job.org_id != org_id or person is None or person.org_id != org_id:
        return {"status": "skipped", "reason": "no such role or person"}
    version = work_lines.version(session, job.id)
    if person.do_not_contact_at is not None:
        return {"status": "skipped", "reason": "they asked not to be contacted", "version": version}
    work, not_work = work_lines.confirmed(session, job.id)
    if version is None:
        return {"status": "skipped", "reason": "no confirmed work lines on the role"}
    src = _source(session, candidate_id)
    if src is None:
        return {"status": "skipped", "reason": "nothing of theirs to read", "version": version, "document_id": None}
    doc, artifact = src
    titles = _titles(session, org_id, candidate_id)
    if doc.doc_type == "web_profile":
        text, profile_titles = engine.own_words(artifact.content)
        titles += profile_titles
    else:
        text = (artifact.content or "")[:engine.CV_CHARS]
    if len(text.split()) < 5:
        return {"status": "skipped", "reason": "nothing of theirs to read", "version": version, "document_id": str(doc.id)}
    try:
        costs.ensure_budget(session, org_id)
    except costs.BudgetExceeded:
        return {"status": "skipped", "reason": "the month's model budget is used up"}
    reading = engine.read([w["words"] for w in work], [n["words"] for n in not_work], text, titles, client)
    costs.record(session, org_id, PURPOSE, reading.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    shown = [{"line": work[v.line - 1]["words"], "central": bool(work[v.line - 1]["central"]), "verdict": v.verdict,
              "quote": v.quote} for v in reading.work]
    looks = [{"line": not_work[v.line - 1]["words"], "verdict": v.verdict, "quote": v.quote} for v in reading.not_work]
    return {"status": "done", "version": version, "source": doc.doc_type, "document_id": str(doc.id),
            "group": engine.group(shown, looks), "work": shown, "not": looks, "lines": len(work),
            "rejected": reading.rejected, "reader": engine.READER_VERSION, "model": reading.cost.get("model"),
            "usd": reading.cost.get("usd")}


# --- for the role's pages --------------------------------------------------------------------------------------------


def summaries(session: Session, job_id: uuid.UUID, candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """Each person's latest reading on this role, as the card shows it and the order uses it. A reading against lines
    since changed is marked stale and orders nobody."""
    if not candidate_ids:
        return {}
    current = work_lines.version(session, job_id)
    wanted = {key(job_id, c): c for c in candidate_ids}
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for t in session.scalars(select(Task).where(Task.kind == KIND, Task.dedupe_key.in_(list(wanted))).order_by(Task.created_at)):
        r = t.result or {}
        status = t.status if t.status != "done" else r.get("status", "done")
        stale = status == "done" and r.get("version") != current
        out[wanted[t.dedupe_key]] = {
            "status": "stale" if stale else status,
            "group": r.get("group") if status == "done" and not stale else None,
            "work": r.get("work") or [], "not": r.get("not") or [], "lines": r.get("lines"), "source": r.get("source"),
            "reason": r.get("reason"), "at": (t.finished_at or t.created_at).isoformat() if (t.finished_at or t.created_at) else None,
            "error": (t.error or "")[:200] if t.status == "failed" else None}
    return out


def order_key(summary: dict[str, Any] | None) -> tuple[int, int, int]:
    return engine.order_key(summary if summary and summary.get("group") else None)


def progress(session: Session, job_id: uuid.UUID, version: str | None) -> dict[str, int]:
    """For the hiring profile: how many strong or possible people are read against the confirmed lines, waiting, or
    read against earlier lines."""
    pairs = list(session.scalars(select(CandidateJob.candidate_id).where(CandidateJob.job_id == job_id,
                                                                       CandidateJob.triage_band.in_(BANDS))))
    got = summaries(session, job_id, pairs)
    count = {"people": len(pairs), "read": 0, "waiting": 0, "stale": 0, "not_read": 0, "skipped": 0}
    for cid in pairs:
        s = got.get(cid)
        status = s["status"] if s else None
        if status == "done":
            count["read"] += 1
        elif status in ("queued", "running"):
            count["waiting"] += 1
        elif status == "stale":
            count["stale"] += 1
        elif status == "skipped":
            count["skipped"] += 1
        else:
            count["not_read"] += 1
    return count


def read_again(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> int:
    """After the lines changed: read again everyone whose reading is against earlier lines (or who was never read)."""
    return queue_role(session, org_id, job_id)
