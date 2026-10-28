"""A role's work, line by line (the core-work reader, owner 2026-10-27: "yes build the reader"). Read from the role's
own material (the ad, the role brief, the requirements) and kept as `WorkLineClaim`s with the reading as evidence.
A person confirms, changes, removes or adds lines; only confirmed or typed lines are used to read people. A new
reading replaces the machine's proposed lines, never a line a person decided. The lines order people within a band
and rate nobody, so a change re-rates no one (`review.NOT_RATED`).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs, writer
from maindscout.db.models import Claim, ClaimObservation, Evidence, Job
from maindscout.intelligence import work_lines as engine
from maindscout.intelligence.llm import LLMClient

PURPOSE = "work_lines"
CLAIM = "WorkLineClaim"
LIVE = ("proposed", "approved")
KINDS = ("work", "not")


def _job(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    return job


def _live(session: Session, job_id: uuid.UUID) -> list[Claim]:
    return list(session.scalars(select(Claim).where(Claim.subject_id == job_id, Claim.claim_type == CLAIM,
                                                    Claim.status.in_(LIVE)).order_by(Claim.created_at, Claim.natural_key)))


def _line(c: Claim) -> dict[str, Any]:
    p = c.approved_view or c.payload
    return {"id": str(c.id), "kind": p["kind"], "words": p["words"], "central": p.get("central"), "status": c.status,
            "by": c.approved_by if c.status == "approved" else None}


def confirmed(session: Session, job_id: uuid.UUID) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The lines a person confirmed or typed: (work, not this work), central work first."""
    rows = [_line(c) for c in _live(session, job_id) if c.status == "approved"]
    work = sorted((r for r in rows if r["kind"] == "work"), key=lambda r: not r["central"])
    return work, [r for r in rows if r["kind"] == "not"]


def version(session: Session, job_id: uuid.UUID) -> str | None:
    """Which confirmed lines a reading was made against: it changes when any line is confirmed, changed or removed.
    None while no work line is confirmed (nobody is read until then)."""
    cache = session.info.setdefault("work_line_version", {})
    if job_id in cache:
        return cache[job_id]
    work, not_work = confirmed(session, job_id)
    out = None
    if work:
        blob = json.dumps([[r["kind"], r["words"], bool(r["central"])] for r in work + not_work], ensure_ascii=False)
        out = hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]
    cache[job_id] = out
    return out


def _forget_version(session: Session, job_id: uuid.UUID) -> None:
    session.info.get("work_line_version", {}).pop(job_id, None)


def inputs(session: Session, job: Job) -> dict[str, Any]:
    from maindscout.api import role_brief

    reqs = [c.approved_view or c.payload for c in session.scalars(select(Claim).where(
        Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim", Claim.status.in_(LIVE)).order_by(Claim.created_at))]
    return {"title": job.title or "", "company": job.hiring_company,
            "brief": [{"facet": b["facet"], "words": b["words"]} for b in role_brief.view(session, job.id)],
            "requirements": [{"strength": r.get("strength"), "text_raw": r.get("text_raw")} for r in reqs
                             if r.get("category") != "process" and r.get("text_raw")],
            "ad": role_brief.inputs(session, job)["ad"]}


def read(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, client: LLMClient, task_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Read the role's work lines (one model call, about a fifth of a cent). The machine's earlier proposed lines that
    the new reading does not give again are superseded; a line a person confirmed or typed stays."""
    from maindscout.api.process import natural_key

    job = _job(session, org_id, job_id)
    src = inputs(session, job)
    if not (src["ad"] or src["requirements"] or src["brief"]):
        return {"skipped": "no ad, brief or requirements to read"}
    costs.ensure_budget(session, org_id)
    lines = engine.read(src["title"], src["company"], src["brief"], src["requirements"], src["ad"], client)
    costs.record(session, org_id, PURPOSE, lines.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    live = {c.natural_key: c for c in _live(session, job.id)}
    seen, written = set(), 0
    for line in lines.lines:
        payload = {"kind": line.kind, "words": line.words, "central": line.central if line.kind == "work" else None}
        key = natural_key(job.id, CLAIM, payload)
        seen.add(key)
        if key in live:
            continue  # the same line, read again
        claim = writer.add_claim(session, org_id=org_id, subject_type="job", subject_id=job.id, claim_type=CLAIM,
                                 payload=payload, natural_key=key, claim_class="inferred", status="proposed",
                                 observed_as_of=date.today())
        ev = Evidence(org_id=org_id, claim_id=claim.id, evidence_type="inference", locator={}, snippet=line.words,
                      source_authority="employer_authored", origin="employer", observed_as_of=date.today(),
                      span_validation={"tier": "paraphrase", "result": "pass", "metric_bucket": "none",
                                       "detail": f"work lines read by {lines.cost.get('model') or 'the model'} "
                                                 f"({engine.LINES_PROMPT_VERSION}) from the ad, brief and requirements"})
        session.add(ev)
        session.flush()
        session.add(ClaimObservation(org_id=org_id, claim_id=claim.id, attribute_path=".", value=payload, evidence_id=ev.id,
                                     source_authority=ev.source_authority, origin=ev.origin, observed_as_of=date.today()))
        written += 1
    for key, old in live.items():
        if old.status == "proposed" and key not in seen:  # a machine line the new reading no longer gives
            old.status = "superseded"
    session.flush()
    _forget_version(session, job.id)
    return {"written": written, "lines": len(lines.lines), "rejected": lines.rejected, "usd": lines.cost.get("usd", 0)}


def read_unless_confirmed(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, client: LLMClient) -> dict[str, Any] | None:
    """With the role brief: the lines are read again only while no line is confirmed (afterwards only on request, so a
    re-read never piles paraphrases on top of the owner's lines)."""
    if any(c.status == "approved" for c in _live(session, job_id)):
        return None
    return read(session, org_id, job_id, client)


def confirm(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, ids: list[str] | None, actor: str) -> dict[str, Any]:
    """Confirm the proposed lines (all, or the ids given), then read everyone strong or possible on the role against
    the confirmed lines (in the background, about a fifth of a cent each)."""
    from maindscout.api import review, work_reading

    _job(session, org_id, job_id)
    wanted = {uuid.UUID(i) for i in ids} if ids else None
    done = 0
    for c in _live(session, job_id):
        if c.status == "proposed" and (wanted is None or c.id in wanted):
            review.approve_claim(session, org_id, c.id, actor)
            done += 1
    _forget_version(session, job_id)
    queued = work_reading.queue_role(session, org_id, job_id) if version(session, job_id) else 0
    return {"confirmed": done, "queued": queued}


def add(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, kind: str, words: str, central: bool | None,
        actor: str, replaces: uuid.UUID | None = None) -> Claim:
    """A line in the recruiter's own words (born confirmed), or a correction of one (`replaces`)."""
    from maindscout.api import review

    _job(session, org_id, job_id)
    words = engine.clean(words)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if len(words.split()) < engine.MIN_WORDS:
        raise ValueError("Write the line in a few words: one thing the person does.")
    if engine.NOT_CRITERIA.search(words):
        raise ValueError("Personality, culture or fit is never a line of the work.")
    payload = {"kind": kind, "words": words, "central": bool(central) if kind == "work" else None}
    claim = review.assert_claim(session, org_id, actor, subject_type="job", subject_id=job_id, claim_type=CLAIM,
                                payload=payload, replaces=replaces)
    _forget_version(session, job_id)
    return claim


def edit(session: Session, org_id: uuid.UUID, claim_id: uuid.UUID, words: str, central: bool | None, actor: str) -> Claim:
    old = session.get(Claim, claim_id)
    if old is None or old.org_id != org_id or old.claim_type != CLAIM or old.status not in LIVE:
        raise LookupError("That line is no longer on the role: reload the page")
    p = old.approved_view or old.payload
    return add(session, org_id, old.subject_id, p["kind"], words, central if p["kind"] == "work" else None, actor, replaces=old.id)


def view(session: Session, job_id: uuid.UUID) -> dict[str, Any]:
    """The lines for the hiring profile, and how far the reading of the role's people is."""
    from maindscout.api import work_reading

    return {"lines": [_line(c) for c in _live(session, job_id)], "version": version(session, job_id),
            "read_at": _read_at(session, job_id), "people": work_reading.progress(session, job_id, version(session, job_id))}


def _read_at(session: Session, job_id: uuid.UUID) -> str | None:
    from maindscout.db.models import CostEntry

    at = session.scalar(select(CostEntry.created_at).where(CostEntry.purpose == PURPOSE, CostEntry.subject_id == job_id)
                        .order_by(CostEntry.created_at.desc()).limit(1))
    return at.isoformat() if at else None
