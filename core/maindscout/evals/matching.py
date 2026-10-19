"""Before a rule change goes live: what it would do to the desk's verdicts (owner, 2026-10-19: "what we do not want is
to have worse results once this is implemented").

    python -m maindscout match-eval [--job ID ...] [--labels FILE] [--show N]

Every person on the given roles (all open roles by default) is matched again with the code as it is now, over the facts
as they are now, with a career profile built afresh (a stored profile was built with the rules of its day). The result
is compared with the verdict the desk shows, with the owner's own decisions on the Sourcing tab (reach out = should be
strong; not for this role = should not), and with hand labels from a file. Nothing is written: the session is rolled
back. Free: no model or search calls.

Run it before a change (it must report no moves: the stored verdicts are current), then after: every move is listed
with the requirement rows that changed, so each one can be checked before the change is applied.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

TIERS = ("strong", "possible", "unlikely", "unclear")
YES = ("to_contact", "contacted", "replied", "call_booked", "screened", "submitted", "interviewing", "offer", "placed")
LABELS = Path(__file__).resolve().parents[2] / "eval-reports" / "match-labels.json"  # git-ignored: it names real people


@dataclass
class Move:
    candidate_id: str
    name: str | None
    before: str | None
    after: str
    rows: list[str] = field(default_factory=list)  # "requirement: verdict (detail) -> verdict (detail)"


@dataclass
class RoleResult:
    job_id: str
    title: str
    people: int = 0
    before: Counter = field(default_factory=Counter)
    after: Counter = field(default_factory=Counter)
    moves: list[Move] = field(default_factory=list)
    row_changes: int = 0  # people whose rows changed without their verdict changing
    quiet: list[Move] = field(default_factory=list)  # those people, with the rows that changed
    checks: list[dict[str, Any]] = field(default_factory=list)  # owner decisions and labels, before and after


def owner_says(pair) -> tuple[str, str | None] | None:
    """The owner's own decision on a suggestion: yes (reached out or further), no (not for this role, why), later."""
    from maindscout.api.outreach import stage

    st = stage(pair)
    if st in YES:
        return "yes", st
    if st == "passed":
        return "no", (pair.contact or {}).get("passed_for")
    if st == "later":
        return "later", None
    return None


def fresh_match(session: Session, pair, job, today: date | None = None):
    """The match the current code makes over today's facts, with a profile built now. Mirrors process._match_now."""
    from maindscout.api import process, profiles
    from maindscout.api.brief import answers_for
    from maindscout.api.pipeline import active_block
    from maindscout.api.queries import _gap_rows_many
    from maindscout.domain import matching
    from maindscout.domain import profile as rubric

    inputs = process.pair_inputs(session, pair.org_id, pair.candidate_id, job)
    rows = _gap_rows_many(session, pair.org_id, job, [pair.candidate_id], with_snippets=False,
                          preloaded=(inputs[0], {pair.candidate_id: inputs[1]}))[pair.candidate_id]
    coarse = process._triage_now(session, pair.org_id, pair.candidate_id, job, inputs)
    snap = profiles.latest(session, pair.candidate_id)
    stints, edu = profiles.inputs(session, pair.org_id, pair.candidate_id) if snap else ([], [])
    profile = rubric.build(stints, edu, today or date.today()) if snap else None
    reqs = [{"id": str(c.id), "payload": c.approved_view or c.payload} for c in inputs[0] if c.payload.get("category") != "process"]
    block = active_block(session, pair.org_id, job.id, pair.candidate_id)
    return matching.match(reqs, rows, profile, stints, (coarse.band, coarse.reason), answers_for(session, pair.org_id, pair.candidate_id),
                          blocked=block.reason if block is not None else None,
                          preferences=process.preference_rows(session, job, inputs[1], [r["payload"] for r in reqs]))


def _row_words(r: dict[str, Any]) -> str:
    return f"{r.get('verdict')} ({(r.get('detail') or '')[:120]})"


def compare(session: Session, job_ids: list[uuid.UUID], labels: list[dict[str, Any]] | None = None) -> list[RoleResult]:
    from maindscout.api.queries import names
    from maindscout.db.models import CandidateJob, Job

    by_pair = {(lb["job_id"], lb["candidate_id"]): lb for lb in labels or []}
    out = []
    for job_id in job_ids:
        job = session.get(Job, job_id)
        pairs = list(session.scalars(select(CandidateJob).where(CandidateJob.job_id == job_id)))
        who = names(session, [p.candidate_id for p in pairs])
        res = RoleResult(str(job_id), job.title, len(pairs))
        for pair in pairs:
            before = pair.match_tier or "unclear"
            m = fresh_match(session, pair, job)
            res.before[before] += 1
            res.after[m.tier] += 1
            old = {r.get("requirement_id"): r for r in ((pair.match or {}).get("rows") or [])}
            changed = []
            for v in m.rows:
                o = old.get(v.requirement_id)
                if o is None or (o.get("verdict"), o.get("detail")) != (v.verdict, v.detail):
                    changed.append(f"{v.requirement[:70]}: {_row_words(o) if o else 'new'} -> {_row_words(v.__dict__)}")
            if before != m.tier:
                res.moves.append(Move(str(pair.candidate_id), who.get(pair.candidate_id), before, m.tier, changed))
            elif changed:
                res.row_changes += 1
                res.quiet.append(Move(str(pair.candidate_id), who.get(pair.candidate_id), before, m.tier, changed))
            says = owner_says(pair)
            label = by_pair.get((str(job_id), str(pair.candidate_id)))
            for source, expect, why in ([("owner", says[0], says[1])] if says and says[0] != "later" else []) + \
                                       ([("label", label["expect"], label.get("why"))] if label else []):
                want_strong = expect in ("yes", "strong")
                res.checks.append({"source": source, "name": who.get(pair.candidate_id), "expect": expect, "why": why,
                                   "before_ok": (before == "strong") == want_strong, "after_ok": (m.tier == "strong") == want_strong,
                                   "before": before, "after": m.tier})
        out.append(res)
    return out


def report(results: list[RoleResult], show: int = 40, quiet: int = 0) -> str:
    lines = []
    for r in results:
        lines.append(f"== {r.title} ({r.people} people)")
        lines.append("   now:   " + " · ".join(f"{t} {r.before.get(t, 0)}" for t in TIERS))
        lines.append("   after: " + " · ".join(f"{t} {r.after.get(t, 0)}" for t in TIERS))
        flows = Counter(f"{m.before} -> {m.after}" for m in r.moves)
        lines.append(f"   moves: {len(r.moves)}" + (f" ({', '.join(f'{k}: {n}' for k, n in flows.most_common())})" if flows else "")
                     + (f"; rows changed with no move: {r.row_changes}" if r.row_changes else ""))
        for m in r.moves[:show]:
            lines.append(f"     {m.before} -> {m.after}: {m.name}")
            for c in m.rows[:4]:
                lines.append(f"         {c}")
        if len(r.moves) > show:
            lines.append(f"     … and {len(r.moves) - show} more")
        for m in r.quiet[:quiet]:
            lines.append(f"     (no move) {m.after}: {m.name}")
            for c in m.rows[:3]:
                lines.append(f"         {c}")
        if r.checks:
            ok_b, ok_a = sum(c["before_ok"] for c in r.checks), sum(c["after_ok"] for c in r.checks)
            lines.append(f"   checks (owner decisions and labels): agree now {ok_b}/{len(r.checks)}, after {ok_a}/{len(r.checks)}")
            for c in r.checks:
                if c["before_ok"] != c["after_ok"] or not c["after_ok"]:
                    lines.append(f"     {'FIXED' if c['after_ok'] else 'WORSE' if c['before_ok'] else 'still wrong'}: "
                                 f"{c['name']} ({c['source']} says {c['expect']}{': ' + c['why'] if c['why'] else ''}; "
                                 f"{c['before']} -> {c['after']})")
    return "\n".join(lines)


def main(job_ids: list[str] | None = None, labels_path: Path | None = None, show: int = 40, quiet: int = 0) -> int:
    from maindscout.db.models import CandidateJob, Job
    from maindscout.db.session import make_engine, make_session_factory

    path = labels_path or LABELS
    labels = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    with make_session_factory(make_engine())() as session:
        ids = [uuid.UUID(j) for j in job_ids] if job_ids else list(session.scalars(
            select(Job.id).where(Job.state == "open", Job.id.in_(select(CandidateJob.job_id))).order_by(Job.created_at)))
        try:
            results = compare(session, ids, labels)
        finally:
            session.rollback()  # nothing is ever written
    print(report(results, show, quiet))
    worse = sum(1 for r in results for c in r.checks if c["before_ok"] and not c["after_ok"])
    return 1 if worse else 0
