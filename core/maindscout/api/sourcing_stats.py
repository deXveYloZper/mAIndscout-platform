"""Results and spend (docs/next/PLAN.md S5): what each search strategy cost and what it brought.

One funnel per person a sourcing run found for a role (the first finder gets the credit):
found → relevant (a strong suggestion) → contacted → replied → interested → CV received → submitted → interviewed
→ offered → placed. "How far they got" is the furthest stage their pair ever reached (an ending such as "we passed"
keeps the stages before it). Spend comes from the cost ledger (the role's or the desk's sourcing purposes); per
strategy it comes from what each search cost. Groups: channel, target-company tier, target company, search, week, role.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs
from maindscout.db.models import (
    CandidateJob,
    CostEntry,
    Document,
    DocumentSubject,
    Job,
    Message,
    PairEvent,
    Permission,
    SourcingHit,
    SourcingQuery,
)

STAGES = ["new", "seen", "contacted", "screened", "submitted", "interviewing", "offer", "placed"]
COUNTS = ["found", "new_to_desk", "relevant", "possible", "contacted", "replied", "interested", "cv", "submitted",
          "interviewed", "offered", "placed"]
GROUPS = ("channel", "tier", "target", "query", "week", "job")
CHANNEL_LABEL = {"pool": "our own pool", "exa_people": "web people search", "exa_news": "talent-release radar (news)"}
TIER_LABEL = {"named": "companies the hiring manager named", "known": "companies our people worked at", "peer": "peer companies",
              "adjacent": "adjacent industries", "release": "companies releasing talent", "manual": "companies you added",
              "market": "market-wide searches", "feeder": "where the hiring company's people came from",
              "feeder_large": "large companies the hiring company's people came from", "snowball": "where strong candidates worked before"}


def _rank(state: str | None) -> int:
    return STAGES.index(state) if state in STAGES else -1


def _empty() -> dict[str, Any]:
    return {k: 0 for k in COUNTS} | {"spend_usd": 0.0}


def _ratios(row: dict[str, Any]) -> dict[str, Any]:
    spend = row["spend_usd"]
    for name, n in (("per_relevant", row["relevant"]), ("per_interview", row["interviewed"]), ("per_placement", row["placed"])):
        row[f"cost_{name}"] = round(spend / n, 2) if n and spend else None
    row["spend_usd"] = round(spend, 4)
    return row


def stats(session: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None, group: str = "channel",
          since: date | None = None) -> dict[str, Any]:
    if group not in GROUPS:
        raise ValueError(f"group must be one of {GROUPS}")
    start = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc) if since else None
    q = select(SourcingHit).where(SourcingHit.org_id == org_id)
    if job_id:
        q = q.where(SourcingHit.job_id == job_id)
    if start:
        q = q.where(SourcingHit.created_at >= start)
    hits = list(session.scalars(q))
    pairs = {(p.job_id, p.candidate_id): p for p in session.scalars(select(CandidateJob).where(
        CandidateJob.org_id == org_id, CandidateJob.candidate_id.in_([h.candidate_id for h in hits] or [None])))}
    furthest: dict[uuid.UUID, int] = defaultdict(lambda: -1)
    for pair_id, to_value in session.execute(select(PairEvent.pair_id, PairEvent.to_value).where(
            PairEvent.kind == "state", PairEvent.pair_id.in_([p.id for p in pairs.values()] or [None]))):
        furthest[pair_id] = max(furthest[pair_id], _rank(to_value))
    people = {h.candidate_id for h in hits}
    messages = list(session.scalars(select(Message).where(Message.org_id == org_id, Message.kind == "candidate_outreach",
                                                         Message.candidate_id.in_(people or [None]))))
    permissions = {(p.candidate_id, p.job_id) for p in session.scalars(select(Permission).where(
        Permission.org_id == org_id, Permission.candidate_id.in_(people or [None])))}
    anyjob_permission = {cid for cid, _ in permissions}
    cvs = defaultdict(list)
    for subject_id, created in session.execute(select(DocumentSubject.subject_id, Document.created_at).join(
            Document, Document.id == DocumentSubject.document_id).where(
            DocumentSubject.subject_id.in_(people or [None]), Document.doc_type == "cv")):
        cvs[subject_id].append(created)
    queries = {sq.id: sq for sq in session.scalars(select(SourcingQuery).where(
        SourcingQuery.org_id == org_id, *( [SourcingQuery.job_id == job_id] if job_id else [])))}
    job_titles = dict(session.execute(select(Job.id, Job.title).where(Job.org_id == org_id)).all())

    def key_of(h: SourcingHit) -> tuple[str, str]:
        if group == "channel":
            return h.channel, CHANNEL_LABEL.get(h.channel, h.channel)
        if group == "tier":
            return h.tier or "-", TIER_LABEL.get(h.tier or "", h.tier) if h.tier else ("our own pool" if h.channel == "pool" else "market-wide searches")
        if group == "target":
            return h.target or "-", h.target or ("our own pool" if h.channel == "pool" else "no target company")
        if group == "query":
            sq = queries.get(h.query_id) if h.query_id else None
            return str(h.query_id or "pool"), sq.text if sq else "our own pool"
        if group == "week":
            monday = (h.created_at - timedelta(days=h.created_at.weekday())).date()
            return monday.isoformat(), f"week of {monday.isoformat()}"
        return str(h.job_id), job_titles.get(h.job_id, "?")

    rows: dict[str, dict[str, Any]] = {}
    total = _empty()
    for h in hits:
        key, label = key_of(h)
        row = rows.setdefault(key, {"key": key, "label": label, **_empty()})
        pair = pairs.get((h.job_id, h.candidate_id))
        reached = max(furthest[pair.id] if pair else -1, _rank(pair.pair_state if pair else None))
        sent = [m for m in messages if m.candidate_id == h.candidate_id and m.status in ("sent", "replied")
                and (m.job_id in (None, h.job_id))]
        replied = any(m.status == "replied" for m in sent)
        flags = {
            "found": True,
            "new_to_desk": h.new_to_desk,
            "relevant": bool(pair and pair.triage_band == "priority"),
            "possible": bool(pair and pair.triage_band == "review_later"),
            "contacted": bool(sent) or reached >= _rank("contacted"),
            "replied": replied or reached >= _rank("screened"),
            "interested": (h.candidate_id, h.job_id) in permissions or h.candidate_id in anyjob_permission or reached >= _rank("screened"),
            "cv": any(c >= h.created_at for c in cvs.get(h.candidate_id, [])),
            "submitted": reached >= _rank("submitted"),
            "interviewed": reached >= _rank("interviewing"),
            "offered": reached >= _rank("offer"),
            "placed": reached >= _rank("placed"),
        }
        if flags["interested"]:  # the funnel only narrows: someone who said yes was reached and answered
            flags["contacted"] = flags["replied"] = True
        for k, v in flags.items():
            if v:
                row[k] += 1
                total[k] += 1

    # Spend: the ledger for the whole scope; per group, what each search cost (company searches are planning).
    total["spend_usd"] = costs.sourcing_spent(session, org_id, job_id, since=start or datetime(2000, 1, 1, tzinfo=timezone.utc))
    if group in ("channel", "tier", "target", "query", "job"):
        for sq in queries.values():
            key = {"channel": sq.channel, "tier": sq.tier or "-", "target": sq.target or "-", "query": str(sq.id),
                   "job": str(sq.job_id)}[group]
            label = {"channel": CHANNEL_LABEL.get(sq.channel, sq.channel), "tier": TIER_LABEL.get(sq.tier or "", sq.tier or "market-wide searches"),
                     "target": sq.target or "no target company", "query": sq.text, "job": job_titles.get(sq.job_id, "?")}[group]
            rows.setdefault(key, {"key": key, "label": label, **_empty()})["spend_usd"] += float(sq.cost_usd or 0)
    elif group == "week":
        week = select(CostEntry.created_at, CostEntry.usd).where(CostEntry.org_id == org_id, CostEntry.purpose.startswith(costs.SOURCING))
        if job_id:
            week = week.where(CostEntry.subject_type == "job", CostEntry.subject_id == job_id)
        for created, usd in session.execute(week):
            monday = (created - timedelta(days=created.weekday())).date()
            if start and created < start:
                continue
            rows.setdefault(monday.isoformat(), {"key": monday.isoformat(), "label": f"week of {monday.isoformat()}", **_empty()})["spend_usd"] += float(usd or 0)

    groups = sorted((_ratios(r) for r in rows.values()), key=lambda r: (-r["relevant"], -r["found"], r["label"]))
    return {"job_id": str(job_id) if job_id else None, "since": since.isoformat() if since else None, "group": group,
            "totals": _ratios(total), "groups": groups, "flags": flags_for(groups, group)}


def flags_for(groups: list[dict[str, Any]], group: str) -> list[dict[str, str]]:
    """What isn't working, and what is, each with its numbers. The owner decides what to change."""
    out = []
    for g in groups:
        if g["contacted"] >= 20 and g["replied"] == 0:
            out.append({"level": "warn", "key": g["key"], "text": f"{g['label']}: {g['contacted']} contacted, no replies yet. "
                        "Change the message, or pause these searches?"})
        if g["spend_usd"] >= 1 and g["relevant"] == 0 and g["found"] >= 10:
            out.append({"level": "warn", "key": g["key"], "text": f"{g['label']}: ${g['spend_usd']:.2f} spent, "
                        f"{g['found']} found, none relevant. Drop or change these searches?"})
        if g["relevant"] >= 5 and g["contacted"] == 0:
            out.append({"level": "info", "key": g["key"], "text": f"{g['label']}: {g['relevant']} strong suggestions not contacted yet."})
    with_interviews = [g for g in groups if g["interviewed"] and g["cost_per_interview"]]
    if with_interviews:
        best = min(with_interviews, key=lambda g: g["cost_per_interview"])
        n = best["interviewed"]
        out.append({"level": "good", "key": best["key"], "text": f"{best['label']}: one interview per ${best['cost_per_interview']:.2f} "
                    f"({n} interview{'s' if n != 1 else ''} from {best['found']} found)."})
    elif any(g["relevant"] for g in groups):
        best = max(groups, key=lambda g: (g["relevant"], -(g["cost_per_relevant"] or 0)))
        if best["relevant"]:
            per = f" at ${best['cost_per_relevant']:.2f} each" if best["cost_per_relevant"] else " at no cost"
            out.append({"level": "good", "key": best["key"], "text": f"{best['label']}: {best['relevant']} relevant{per}."})
    return out
