"""A role's work, line by line (the core-work reader, owner 2026-10-27: "yes build the reader"). Read from the role's
own material (the ad, the role brief, the requirements) and kept as `WorkLineClaim`s with the reading as evidence.
A person confirms, changes, removes or adds lines; only confirmed or typed lines are used to read people. A new
reading replaces the machine's proposed lines, never a line a person decided. The lines order people within a band
and rate nobody, so a change re-rates no one (`review.NOT_RATED`).

Since 2026-10-30 the same claims hold the role's own titles (`title`), its look-alikes' titles (`not_title`) and the
work in a word (`word`), read after the lines and confirmed with them. Searches use them in place of the shared family
table's titles; they never change who is read or how anyone is rated.
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
TITLES_PURPOSE = "role_titles"
CLAIM = "WorkLineClaim"
LIVE = ("proposed", "approved")
LINE_KINDS = ("work", "not")  # read people against; their version marks a reading stale
TITLE_KINDS = ("title", "not_title", "word")  # the role's own titles, its look-alikes' titles, its word: for searching
KINDS = LINE_KINDS + TITLE_KINDS


def _job(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    return job


def _live(session: Session, job_id: uuid.UUID, kinds: tuple[str, ...] = KINDS) -> list[Claim]:
    rows = session.scalars(select(Claim).where(Claim.subject_id == job_id, Claim.claim_type == CLAIM,
                                               Claim.status.in_(LIVE)).order_by(Claim.created_at, Claim.natural_key))
    out = [c for c in rows if (c.approved_view or c.payload).get("kind") in kinds]
    rank = lambda c: (c.approved_view or c.payload).get("rank")  # noqa: E731 - titles in the reading's order
    return sorted(out, key=lambda c: (rank(c) is None, rank(c) or 0))  # stable: lines keep their order


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


def _propose(session: Session, org_id: uuid.UUID, job: Job, payloads: list[dict[str, Any]], kinds: tuple[str, ...],
             detail: str) -> int:
    """The desk's reading as proposed lines of these kinds; its earlier proposals of the same kinds that this reading
    no longer gives are superseded. A line a person confirmed or typed stays, and so do the other kinds."""
    from maindscout.api.process import natural_key

    live = {c.natural_key: c for c in _live(session, job.id, kinds)}
    seen, written = set(), 0
    for payload in payloads:
        key = natural_key(job.id, CLAIM, payload)
        seen.add(key)
        if key in live:
            continue  # the same line, read again
        claim = writer.add_claim(session, org_id=org_id, subject_type="job", subject_id=job.id, claim_type=CLAIM,
                                 payload=payload, natural_key=key, claim_class="inferred", status="proposed",
                                 observed_as_of=date.today())
        ev = Evidence(org_id=org_id, claim_id=claim.id, evidence_type="inference", locator={}, snippet=payload["words"],
                      source_authority="employer_authored", origin="employer", observed_as_of=date.today(),
                      span_validation={"tier": "paraphrase", "result": "pass", "metric_bucket": "none", "detail": detail})
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
    return written


def read(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, client: LLMClient, task_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Read the role's work lines (one model call, about a fifth of a cent), then its titles while none is confirmed.
    The machine's earlier proposed lines that the new reading does not give again are superseded; a line a person
    confirmed or typed stays."""
    job = _job(session, org_id, job_id)
    src = inputs(session, job)
    if not (src["ad"] or src["requirements"] or src["brief"]):
        return {"skipped": "no ad, brief or requirements to read"}
    costs.ensure_budget(session, org_id)
    lines = engine.read(src["title"], src["company"], src["brief"], src["requirements"], src["ad"], client)
    costs.record(session, org_id, PURPOSE, lines.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    payloads = [{"kind": x.kind, "words": x.words, "central": x.central if x.kind == "work" else None} for x in lines.lines]
    written = _propose(session, org_id, job, payloads, LINE_KINDS,
                       f"work lines read by {lines.cost.get('model') or 'the model'} ({engine.LINES_PROMPT_VERSION}) "
                       "from the ad, brief and requirements")
    read_titles_unless_confirmed(session, org_id, job.id, client, task_id)
    return {"written": written, "lines": len(lines.lines), "rejected": lines.rejected, "usd": lines.cost.get("usd", 0)}


def read_unless_confirmed(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, client: LLMClient) -> dict[str, Any] | None:
    """With the role brief: the lines are read again only while no line is confirmed (afterwards only on request, so a
    re-read never piles paraphrases on top of the owner's lines)."""
    if any(c.status == "approved" for c in _live(session, job_id, LINE_KINDS)):
        return None
    return read(session, org_id, job_id, client)


def read_titles(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, client: LLMClient,
                task_id: uuid.UUID | None = None) -> dict[str, Any]:
    """The titles people doing this role's work carry, the titles of its look-alikes and the work in a word (one model
    call, about a fifth of a cent), from the role's material, its lines, its countries and, once the strategy is built,
    the titles of the client's own people. Proposed for a person to confirm with the lines; nothing searches by them
    until then."""
    from maindscout import activity
    from maindscout.api import autosource

    job = _job(session, org_id, job_id)
    src = inputs(session, job)
    if not (src["ad"] or src["requirements"] or src["brief"]):
        return {"skipped": "no ad, brief or requirements to read"}
    lines = [engine.Line((c.approved_view or c.payload)["kind"], (c.approved_view or c.payload)["words"])
             for c in _live(session, job.id, LINE_KINDS)]
    plan = autosource.current_plan(session, job.id)
    countries = list((plan.countries if plan is not None else None) or job.open_countries or [])
    own = [t for t, _ in ((plan.dna or {}).get("titles") or [])] if plan is not None else []
    costs.ensure_budget(session, org_id)
    got = engine.read_titles(src["title"], src["company"], src["brief"], src["requirements"], src["ad"], lines, countries,
                             own, client)
    costs.record(session, org_id, TITLES_PURPOSE, got.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    payloads = ([{"kind": "title", "words": t, "central": None, "rank": i} for i, t in enumerate(got.titles)]
                + [{"kind": "not_title", "words": t, "central": None, "rank": i} for i, t in enumerate(got.look_alikes)]
                + ([{"kind": "word", "words": got.word, "central": None, "rank": 0}] if got.word else []))
    written = _propose(session, org_id, job, payloads, TITLE_KINDS,
                       f"titles read by {got.cost.get('model') or 'the model'} ({engine.TITLES_PROMPT_VERSION}) from the "
                       f"ad, brief, lines{' and the client’s own people' if own else ''}")
    activity.step(f"Titles for {job.title}: {'; '.join(got.titles) or 'none'} · look-alikes: {'; '.join(got.look_alikes) or 'none'}"
                  f" · in a word: {got.word or 'none'}", {"titles": got.titles, "look_alikes": got.look_alikes, "word": got.word,
                                                          "own_titles": own[:12], "rejected": got.rejected},
                  org_id=org_id, job_id=job.id)
    return {"written": written, "titles": got.titles, "look_alikes": got.look_alikes, "word": got.word,
            "usd": got.cost.get("usd", 0)}


def read_titles_unless_confirmed(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, client: LLMClient,
                                 task_id: uuid.UUID | None = None) -> dict[str, Any] | None:
    """Read the titles while none is confirmed. A failure never costs the lines read before it."""
    from maindscout import activity

    if any(c.status == "approved" for c in _live(session, job_id, TITLE_KINDS)):
        return None
    try:
        with session.begin_nested():
            return read_titles(session, org_id, job_id, client, task_id)
    except costs.BudgetExceeded:
        return None  # the month's model budget: the lines stand without titles
    except Exception as exc:  # noqa: BLE001 - logged, the lines stand
        activity.error("The role's titles could not be read: searches use the usual titles", exc, org_id=org_id, job_id=job_id)
        return None


def titles(session: Session, job_id: uuid.UUID, kind: str = "title") -> list[str]:
    """The confirmed titles of this kind, in the order they were read or typed."""
    return [(c.approved_view or c.payload)["words"] for c in _live(session, job_id, (kind,)) if c.status == "approved"]


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
        actor: str, replaces: uuid.UUID | None = None, rank: int | None = None) -> Claim:
    """A line in the recruiter's own words (born confirmed), or a correction of one (`replaces`)."""
    from maindscout.api import review

    _job(session, org_id, job_id)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if kind in TITLE_KINDS:
        words = engine.clean_title(words)
        most = engine.MAX_WORD_WORDS if kind == "word" else engine.MAX_TITLE_WORDS
        if not words or len(words.split()) > most:
            raise ValueError(f"Write it in one to {most} words, as people write it on a profile.")
    else:
        words = engine.clean(words)
        if len(words.split()) < engine.MIN_WORDS:
            raise ValueError("Write the line in a few words: one thing the person does.")
    if engine.NOT_CRITERIA.search(words):
        raise ValueError("Personality, culture or fit is never a line of the work.")
    payload = {"kind": kind, "words": words, "central": bool(central) if kind == "work" else None}
    if rank is not None and kind in TITLE_KINDS:
        payload["rank"] = rank  # a corrected title keeps its place
    claim = review.assert_claim(session, org_id, actor, subject_type="job", subject_id=job_id, claim_type=CLAIM,
                                payload=payload, replaces=replaces)
    _forget_version(session, job_id)
    return claim


def edit(session: Session, org_id: uuid.UUID, claim_id: uuid.UUID, words: str, central: bool | None, actor: str) -> Claim:
    old = session.get(Claim, claim_id)
    if old is None or old.org_id != org_id or old.claim_type != CLAIM or old.status not in LIVE:
        raise LookupError("That line is no longer on the role: reload the page")
    p = old.approved_view or old.payload
    return add(session, org_id, old.subject_id, p["kind"], words, central if p["kind"] == "work" else None, actor, replaces=old.id,
               rank=p.get("rank"))


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
