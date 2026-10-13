"""The sourcing engine (docs/next/PLAN.md, phase 1): each open role keeps finding people on its own.

- **The plan** of a role (market map, role variants, countries, mode, target, budget) is versioned: every change is a
  new version, so we know which version found whom.
- **A run** goes cheapest first: the desk's own pool (free), then web discovery through Exa (paid, only queries not
  run in the last 30 days), then the talent-release radar (`radar.py`: news that companies are releasing talent). It
  stops when the role has its target of strong suggestions waiting, or at the budget.
- **Gates** on everyone found, on top of the ordinary ones (identity, coverage, client blocks, their own "not for
  me"): off-limits companies (active clients, a client we placed someone at in the last 12 months, the desk's own
  list) and "stop" (they asked not to be contacted). Refused people stay in the pool; they are just not suggested.
- **Who found whom** (`sourcing_hit`, first finder per role) and what each search cost feed results and spend
  (`sourcing_stats.py`).
- Modes: daily, weekly, continuous until the target (checked hourly), paused. The clock (`__main__`) queues due runs.
- Phase 1b (`strategy.py`): the plan carries the hiring company's talent DNA, target companies in tiers (A, B, C), the
  tiers open for searching and the rules for exhaustion and widening. A run searches the next batch of companies,
  profiles the employers of the people it adds (Exa, by id) and queues their career readings, then grows the list
  (snowball). Country-wide searches only when the owner opens them.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.api import costs
from maindscout.db.models import (
    Candidate,
    CandidateJob,
    Claim,
    Company,
    Job,
    OffLimits,
    Org,
    PairEvent,
    SourcingHit,
    SourcingPlan,
    SourcingQuery,
    SourcingRun,
    Task,
)
from maindscout.storage import BlobStore

DEFAULT_TARGET = 10
DEFAULT_BUDGET_USD = 5.0
DEFAULT_DESK_BUDGET_USD = 50.0
QUERY_COOLDOWN = timedelta(days=30)
MAX_WEB_QUERIES_PER_RUN = 8
RESULTS_PER_QUERY = 10
SEARCH_COST_ESTIMATE = 0.01  # a search is about $0.007; the budget check keeps a margin
POOL_LOOK = 40  # most desk people one run looks at
PLACEMENT_OFF_LIMITS_DAYS = 365
LIVE = ("proposed", "approved")
WAITING = ("new", "seen")  # suggestions not yet contacted


class SourcingEngineError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- the plan ------------------------------------------------------------------------------------------------------


def current_plan(session: Session, job_id: uuid.UUID) -> SourcingPlan | None:
    return session.scalar(select(SourcingPlan).where(SourcingPlan.job_id == job_id, SourcingPlan.superseded_at.is_(None))
                          .order_by(SourcingPlan.version.desc()))


def plan(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, actor: str = "system") -> SourcingPlan:
    """The role's current plan; the first one is built from the market map (desk knowledge only, free)."""
    job = _job(session, org_id, job_id)
    existing = current_plan(session, job.id)
    if existing is not None:
        return existing
    from maindscout.api import marketmap

    m = marketmap.initial(session, job)
    # Paused until a person chooses how often to search: no paid search starts because a tab was opened.
    row = SourcingPlan(org_id=org_id, job_id=job.id, version=1, mode="paused", target=DEFAULT_TARGET,
                       monthly_budget_usd=DEFAULT_BUDGET_USD, targets=m["targets"], role_variants=m["role_variants"],
                       countries=m["countries"], created_by=actor)
    session.add(row)
    session.flush()
    return row


def update_plan(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, actor: str, **changes: Any) -> SourcingPlan:
    """A new version with the changes: mode, target, monthly_budget_usd, role_variants, countries, targets."""
    old = plan(session, org_id, job_id, actor)
    fields = {k: getattr(old, k) for k in ("mode", "target", "monthly_budget_usd", "targets", "role_variants", "countries",
                                           "dna", "rules", "open_tiers")}
    for key, value in changes.items():
        if key not in fields:
            raise SourcingEngineError(f"Unknown plan field {key!r}")
        if value is not None:
            fields[key] = value
    if fields["mode"] not in ("daily", "weekly", "continuous", "paused"):
        raise SourcingEngineError("mode must be daily, weekly, continuous or paused")
    if not 1 <= int(fields["target"]) <= 200:
        raise SourcingEngineError("target must be 1-200")
    if not 0 <= float(fields["monthly_budget_usd"]) <= 1000:
        raise SourcingEngineError("the monthly budget must be $0-1000")
    variants = [" ".join(str(v).split()) for v in fields["role_variants"] if str(v).strip()]
    if not variants:
        raise SourcingEngineError("a plan needs at least one role title to search for")
    fields["role_variants"] = list(dict.fromkeys(variants))[:8]
    fields["countries"] = [c.upper() for c in fields["countries"] if isinstance(c, str) and len(c) == 2][:8]
    tiers = [t for t in dict.fromkeys(fields["open_tiers"] or ["A", "B"]) if t in ("A", "B", "C", "market")]
    if "A" not in tiers:
        raise SourcingEngineError("tier A (the companies named and the feeders) is always searched")
    fields["open_tiers"] = tiers
    from maindscout.api.strategy import RULES

    rules = dict(fields["rules"] or {})
    for k, v in list(rules.items()):
        if k not in RULES or not isinstance(v, (int, float)) or v < 0:
            raise SourcingEngineError(f"Unknown or invalid rule {k!r}")
    if not 1 <= rules.get("batch", RULES["batch"]) <= 20 or not 0 <= rules.get("known_share", RULES["known_share"]) <= 1:
        raise SourcingEngineError("batch must be 1-20 companies and known_share 0-1")
    fields["rules"] = rules
    old.superseded_at = _now()
    row = SourcingPlan(org_id=org_id, job_id=job_id, version=old.version + 1, created_by=actor, **fields)
    session.add(row)
    session.flush()
    return row


def add_target(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, name: str, actor: str) -> SourcingPlan:
    from maindscout.api import companies

    company, _ = companies.resolve(session, name, "human")
    if company is None:
        raise SourcingEngineError(f"{name!r} is not a company name")
    company = companies.canonical(session, company)
    p = plan(session, org_id, job_id, actor)
    targets = [dict(t) for t in p.targets]
    for t in targets:
        if t.get("company_id") == str(company.id):
            t.update(removed=False, pinned=True)
            break
    else:
        targets.insert(0, {"name": company.name, "company_id": str(company.id), "tier": "manual", "why": ["added by you"],
                           "source": "manual", "people_on_desk": 0, "pinned": True, "removed": False,
                           "country": company.hq_country})
    return update_plan(session, org_id, job_id, actor, targets=targets)


def set_target(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, company_id: str, actor: str, *,
               pinned: bool | None = None, removed: bool | None = None) -> SourcingPlan:
    p = plan(session, org_id, job_id, actor)
    targets = [dict(t) for t in p.targets]
    hit = next((t for t in targets if t.get("company_id") == company_id), None)
    if hit is None:
        raise LookupError(f"No target company {company_id} on this plan")
    if pinned is not None:
        hit["pinned"] = pinned
    if removed is not None:
        hit["removed"] = removed
    return update_plan(session, org_id, job_id, actor, targets=targets)


def find_peers(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, actor: str, caller, task_id=None) -> dict[str, Any]:
    """More peer companies from a web company search (paid, about $0.007), added to the plan."""
    from maindscout.api import hiring, marketmap

    job = _job(session, org_id, job_id)
    p = plan(session, org_id, job_id, actor)
    _check_budgets(session, org_id, job, p)
    hiring_company = session.get(Company, job.hiring_company_id) if job.hiring_company_id else None
    summary = hiring.company_summary(session, hiring_company) or {}
    found, usd, query = marketmap.web_peers(session, job, p.targets, p.countries, p.role_variants[0], caller, summary)
    if query is None:
        raise SourcingEngineError("The hiring company's industries are not known yet: research it first, or add companies by hand")
    costs.record(session, org_id, "sourcing_company_search", {"model": "exa", "usd": usd, "sources": len(found)},
                 subject_type="job", subject_id=job.id, task_id=task_id)
    updated = update_plan(session, org_id, job_id, actor, targets=[*p.targets, *found]) if found else p
    return {"query": query, "added": len(found), "cost_usd": usd, "version": updated.version}


# --- gates -----------------------------------------------------------------------------------------------------------


def off_limits(session: Session, org_id: uuid.UUID) -> dict[str, str]:
    """company id -> why the desk never sources from it: an active client (an open role), a client we placed someone
    at in the last 12 months, or the desk's own list. Companies merged into one share its status."""
    out: dict[str, str] = {}
    for company_id in session.scalars(select(Job.hiring_company_id).where(
            Job.org_id == org_id, Job.state.in_(("open", "on_hold")), Job.hiring_company_id.is_not(None))):
        out.setdefault(str(company_id), "active client")
    since = _now() - timedelta(days=PLACEMENT_OFF_LIMITS_DAYS)
    placed = select(Job.hiring_company_id).join(CandidateJob, CandidateJob.job_id == Job.id).join(
        PairEvent, PairEvent.pair_id == CandidateJob.id).where(
        Job.org_id == org_id, PairEvent.kind == "state", PairEvent.to_value == "placed", PairEvent.created_at >= since,
        Job.hiring_company_id.is_not(None))
    for company_id in session.scalars(placed):
        out.setdefault(str(company_id), "placement in the last 12 months")
    for row in session.scalars(select(OffLimits).where(OffLimits.org_id == org_id, OffLimits.removed_at.is_(None))):
        if row.until is None or row.until >= date.today():
            out.setdefault(str(row.company_id), row.note or "on the desk's off-limits list")
    for child, parent in session.execute(select(Company.id, Company.merged_into_id).where(
            Company.merged_into_id.in_([uuid.UUID(c) for c in out] or [None]))):
        out.setdefault(str(child), out[str(parent)])
    return out


def never_sourced(session: Session, org_id: uuid.UUID) -> set[uuid.UUID]:
    """People no search may put on a role: they asked not to be contacted, or they work at an off-limits company now.
    Used by the desk search ("Find more people"); a run checks each person with `refusal` so it can count why."""
    out = set(session.scalars(select(Candidate.id).where(Candidate.org_id == org_id, Candidate.do_not_contact_at.is_not(None))))
    limits = off_limits(session, org_id)
    if limits:
        ids = list(limits)
        for c in session.scalars(select(Claim).where(
                Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE), Claim.valid_to.is_(None),
                Claim.payload["company"]["company_id"].astext.in_(ids) | Claim.approved_view["company"]["company_id"].astext.in_(ids))):
            if ((c.approved_view or c.payload).get("company") or {}).get("company_id") in limits:
                out.add(c.subject_id)
    return out


def current_employers(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID) -> set[str]:
    out = set()
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                 Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
                                                 Claim.valid_to.is_(None))):
        company_id = ((c.approved_view or c.payload).get("company") or {}).get("company_id")
        if company_id:
            out.add(company_id)
    return out


def refusal(session: Session, org_id: uuid.UUID, job: Job, candidate_id: uuid.UUID, limits: dict[str, str],
            not_wanted: set[uuid.UUID] | None = None) -> str | None:
    """Why this person is not suggested for this role, or None."""
    from maindscout.api import coverage
    from maindscout.api.pipeline import active_block
    from maindscout.api.process import not_wanted_by

    if not_wanted is None:
        not_wanted = not_wanted_by(session, org_id, job)
    person = session.get(Candidate, candidate_id)
    if person is None or person.do_not_contact_at is not None:
        return "stop"
    if current_employers(session, org_id, candidate_id) & set(limits):
        return "off_limits"
    if active_block(session, org_id, job.id, candidate_id) is not None:
        return "client_block"
    if candidate_id in not_wanted:
        return "not_for_them"
    if not coverage.would_accept(session, org_id, candidate_id, job):
        return "outside_countries"
    return None


# --- budgets ---------------------------------------------------------------------------------------------------------


def desk_budget(session: Session, org_id: uuid.UUID) -> float:
    org = session.get(Org, org_id)
    try:
        return float((org.settings or {}).get("sourcing_budget_usd", DEFAULT_DESK_BUDGET_USD)) if org else DEFAULT_DESK_BUDGET_USD
    except (TypeError, ValueError):
        return DEFAULT_DESK_BUDGET_USD


def set_desk_budget(session: Session, org_id: uuid.UUID, usd: float) -> float:
    if not 0 <= usd <= 10000:
        raise SourcingEngineError("the desk's sourcing budget must be $0-10000 a month")
    org = session.get(Org, org_id)
    org.settings = {**(org.settings or {}), "sourcing_budget_usd": round(float(usd), 2)}
    session.flush()
    return float(usd)


def _check_budgets(session: Session, org_id: uuid.UUID, job: Job, p: SourcingPlan) -> None:
    if costs.sourcing_spent(session, org_id, job.id) + SEARCH_COST_ESTIMATE > float(p.monthly_budget_usd):
        raise SourcingEngineError(f"This role's sourcing budget is used up this month (${float(p.monthly_budget_usd):.2f})")
    if costs.sourcing_spent(session, org_id) + SEARCH_COST_ESTIMATE > desk_budget(session, org_id):
        raise SourcingEngineError(f"The desk's sourcing budget is used up this month (${desk_budget(session, org_id):.2f})")


def _budget_left(session: Session, org_id: uuid.UUID, job: Job, p: SourcingPlan) -> str | None:
    """None if one more search fits both budgets, else which one is used up."""
    if costs.sourcing_spent(session, org_id, job.id) + SEARCH_COST_ESTIMATE > float(p.monthly_budget_usd):
        return "budget"
    if costs.sourcing_spent(session, org_id) + SEARCH_COST_ESTIMATE > desk_budget(session, org_id):
        return "desk_budget"
    return None


# --- runs ------------------------------------------------------------------------------------------------------------


def _job(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    return job


def strong_waiting(session: Session, job_id: uuid.UUID) -> int:
    """Strong suggestions found by sourcing that nobody has contacted yet (never someone who said stop)."""
    return session.scalar(select(func.count()).select_from(CandidateJob).join(
        SourcingHit, (SourcingHit.job_id == CandidateJob.job_id) & (SourcingHit.candidate_id == CandidateJob.candidate_id)).join(
        Candidate, Candidate.id == CandidateJob.candidate_id).where(
        CandidateJob.job_id == job_id, CandidateJob.triage_band == "priority", CandidateJob.pair_state.in_(WAITING),
        Candidate.do_not_contact_at.is_(None))) or 0


def _key(channel: str, text: str, country: str | None) -> str:
    return hashlib.sha1(f"{channel}|{text.lower()}|{country or ''}".encode("utf-8")).hexdigest()


def run(session: Session, blobs: BlobStore, org_id: uuid.UUID, job_id: uuid.UUID, trigger: str, caller,
        actor: str = "system", task_id=None) -> SourcingRun:
    """One run of the role's plan. `caller` is the Exa client (None: the pool only)."""
    from maindscout.api import discovery, radar, sourcing
    from maindscout.api.process import _ensure_pair
    from maindscout.intelligence import exa

    job = _job(session, org_id, job_id)
    if job.state != "open":
        raise SourcingEngineError("Only an open role is sourced")
    p = plan(session, org_id, job_id, actor)
    row = SourcingRun(org_id=org_id, job_id=job.id, plan_id=p.id, trigger=trigger, status="running", report={})
    session.add(row)
    session.flush()
    from maindscout.api.process import not_wanted_by

    limits, not_wanted = off_limits(session, org_id), not_wanted_by(session, org_id, job)
    report: dict[str, Any] = {"pool": {"looked": 0, "added": 0, "strong": 0}, "web": {"queries": [], "people": 0},
                              "refused": {}, "plan_version": p.version}

    def refuse(why: str) -> None:
        report["refused"][why] = report["refused"].get(why, 0) + 1
        row.refused += 1

    def put_on(cid: uuid.UUID, channel: str, query: SourcingQuery | None, new_to_desk: bool) -> tuple[bool, bool]:
        """Put a found person on the role. Returns (added, strong suggestion)."""
        if session.scalar(select(CandidateJob.id).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == cid)):
            row.known += 1
            if query is not None:
                query.known += 1
            return False, False
        if why := refusal(session, org_id, job, cid, limits, not_wanted):
            refuse(why)
            return False, False
        pair = _ensure_pair(session, org_id, cid, job, cause={"act": "sourced", "run_id": str(row.id), "channel": channel})
        session.add(SourcingHit(org_id=org_id, job_id=job.id, candidate_id=cid, run_id=row.id,
                                query_id=query.id if query else None, channel=channel,
                                target=query.target if query else None, tier=query.tier if query else None,
                                new_to_desk=new_to_desk))
        session.flush()
        strong = pair.triage_band == "priority"
        row.strong += strong
        return True, strong

    def done(status: str, reason: str | None) -> SourcingRun:
        row.status, row.stop_reason, row.ended_at, row.report = status, reason, _now(), report
        session.flush()
        return row

    # 1. The desk's own pool: free, and the warmest people.
    try:
        source = "profile" if sourcing.profile_query(session, job) else "desk"
        query = sourcing.profile_query(session, job) if source == "profile" else {"tokens": sourcing.query_tokens(session, job)}
        if source == "desk" and not query["tokens"]:
            raise sourcing.SourcingError("nothing to search the pool by")
        for cid in sourcing.ADAPTERS[source].find(session, org_id, job, query, limit=POOL_LOOK):
            if strong_waiting(session, job.id) >= p.target:
                return done("done", "target")
            report["pool"]["looked"] += 1
            row.found += 1
            added, strong = put_on(cid, "pool", None, new_to_desk=False)
            report["pool"]["added"] += added
            report["pool"]["strong"] += strong
    except sourcing.SourcingError:
        pass

    # 2. The web, when there is an Exa client: only searches not made in the last 30 days.
    if caller is None:
        return done("done", "pool_only")
    from maindscout.api import company_profiles, profiles, strategy

    skills = discovery.skill_tokens(session, job)
    made = 0
    seen_people: set[uuid.UUID] = set()  # the same person found by two searches in one run counts once
    seen_pages: set[str] = set()
    added_people: list[uuid.UUID] = []
    employer_ids: dict[str, None] = {}
    reason = None
    for q in strategy.next_searches(session, job, p, set(radar.live(session, org_id)), limits):
        if strong_waiting(session, job.id) >= p.target:
            return done("done", "target")
        if made >= MAX_WEB_QUERIES_PER_RUN:
            reason = "run_limit"
            break
        if why := _budget_left(session, org_id, job, p):
            return done("stopped", why)
        key = _key("exa_people", q["text"], q["country"])
        sq = session.scalar(select(SourcingQuery).where(SourcingQuery.job_id == job.id, SourcingQuery.key == key))
        if sq is not None and sq.last_run_at and sq.last_run_at > _now() - QUERY_COOLDOWN:
            continue
        if sq is None:
            sq = SourcingQuery(org_id=org_id, job_id=job.id, key=key, channel="exa_people", text=q["text"],
                               target=q["target"], tier=q["tier"], country=q["country"], runs=0, results=0, new=0, cost_usd=0,
                               relevant=0, known=0, company_id=uuid.UUID(q["company_id"]) if q.get("company_id") else None)
            session.add(sq)
            session.flush()
        try:
            results = exa.search(caller, q["text"], "people", num_results=RESULTS_PER_QUERY, country=q["country"])
        except exa.ExaError as error:
            row.error = str(error)[:500]
            return done("failed" if made == 0 else "stopped", "error")
        made += 1
        costs.record(session, org_id, "sourcing_exa_people", {"model": "exa", "usd": results.usd, "sources": len(results.found)},
                     subject_type="job", subject_id=job.id, task_id=task_id)
        sq.runs += 1
        sq.results += len(results.found)
        sq.cost_usd = float(sq.cost_usd or 0) + results.usd
        sq.last_run_at = _now()
        row.cost_usd = float(row.cost_usd or 0) + results.usd
        entry = {"text": q["text"], "target": q["target"], "results": len(results.found), "new": 0, "strong": 0}
        for found in results.found:
            if found.url in seen_pages:
                continue
            seen_pages.add(found.url)
            cid, outcome = discovery.add(session, blobs, org_id, found, skills)
            if cid is None:
                refuse(outcome)
                continue
            if cid in seen_people:
                continue
            seen_people.add(cid)
            row.found += 1
            report["web"]["people"] += 1
            is_new = outcome == "new"
            if is_new:
                row.new += 1
                sq.new += 1
                entry["new"] += 1
            elif outcome == "known":
                sq.known += 1
            added, strong = put_on(cid, "exa_people", sq, new_to_desk=is_new)
            entry["strong"] += strong
            sq.relevant += strong
            if added:
                added_people.append(cid)
                employer_ids.update({i: None for i in discovery.register_employers(session, found)})
        report["web"]["queries"].append(entry)

    # 3. Who they worked for: each new employer profiled by its Exa id (about $0.001), then their career reading.
    if employer_ids and not _budget_left(session, org_id, job, p):
        try:
            done_ids = company_profiles.by_ids(session, employer_ids, caller, org_id, job.id, task_id)
            report["profiles"] = {"companies": len(done_ids), "people": len(added_people)}
        except exa.ExaError as error:
            row.error = str(error)[:500]
    for cid in added_people:
        profiles.queue(session, org_id, cid)

    # 4. The list grows: earlier employers of strong people, and companies like the ones that produce.
    if made:
        strategy.snowball(session, org_id, job, caller, report, task_id)

    # 5. The talent-release radar: its own few searches, last (its finds lead the next run).
    news = radar.sweep(session, org_id, job, p, caller, row, report, task_id)
    if report["radar"]["stopped"] in ("budget", "desk_budget") and not reason:
        return done("stopped", report["radar"]["stopped"])
    return done("done", reason or ("no_queries" if made == 0 and news == 0 else "searched"))


# --- the clock -------------------------------------------------------------------------------------------------------


def due(session: Session, now: datetime | None = None) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(desk, role) pairs whose plan says a run is due: daily after 24 hours, weekly after 7 days, continuous every
    hour while the role is short of its target. Paused plans and roles that are not open never run."""
    now = now or _now()
    out = []
    for p in session.scalars(select(SourcingPlan).join(Job, Job.id == SourcingPlan.job_id).where(
            SourcingPlan.superseded_at.is_(None), SourcingPlan.mode != "paused", Job.state == "open")):
        last = session.scalar(select(func.max(SourcingRun.started_at)).where(SourcingRun.job_id == p.job_id))
        gap = {"daily": timedelta(hours=24), "weekly": timedelta(days=7), "continuous": timedelta(hours=1)}[p.mode]
        if last is not None and now - last < gap:
            continue
        if p.mode == "continuous" and strong_waiting(session, p.job_id) >= p.target:
            continue
        out.append((p.org_id, p.job_id))
    return out


# --- the role's sourcing page ------------------------------------------------------------------------------------


def _people_facts(session: Session, org_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    from maindscout.api import company_profiles

    out: dict[uuid.UUID, dict[str, Any]] = {i: {"current": None, "location": None, "profile": None, "employer": None} for i in ids}
    for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id.in_(ids or [None]),
                                                 Claim.status.in_(LIVE),
                                                 Claim.claim_type.in_(("CareerStepClaim", "LocationClaim", "ContactClaim")))):
        p, row = c.approved_view or c.payload, out[c.subject_id]
        if c.claim_type == "CareerStepClaim" and c.valid_to is None and not row["current"]:
            row["current"] = f"{p.get('title_raw')} at {(p.get('company') or {}).get('raw_name')}"
            company_id = (p.get("company") or {}).get("company_id")
            if company_id:  # where they work, in facts: kind, size, stage (phase 1b)
                row["employer"] = company_profiles.summary(session.get(Company, uuid.UUID(company_id)))
        elif c.claim_type == "LocationClaim" and not row["location"]:
            row["location"] = p.get("place_raw")
        elif c.claim_type == "ContactClaim" and p.get("kind") == "linkedin" and not row["profile"]:
            row["profile"] = p.get("value")
    return out


def page(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, actor: str = "system") -> dict[str, Any]:
    """Everything the role's sourcing tab shows: the plan, budgets, recent runs, and the suggestions waiting."""
    from maindscout.api import company_profiles, hiring, radar, strategy
    from maindscout.api.queries import _gap_rows_many, _gap_summary, names
    from maindscout.settings import env

    job = _job(session, org_id, job_id)
    p = plan(session, org_id, job_id, actor)
    limits = off_limits(session, org_id)
    signals = radar.live(session, org_id)
    state = strategy.company_state(session, job.id, p)
    profiles_by_id = {str(c.id): c for c in session.scalars(select(Company).where(
        Company.id.in_([uuid.UUID(t["company_id"]) for t in p.targets if t.get("company_id")] or [None])))}
    targets = [{**t, "group": strategy.group_of(t), "off_limits": limits.get(t.get("company_id") or ""),
                "release": signals.get(t.get("company_id") or ""),
                "progress": {k: v for k, v in (state.get(t.get("company_id") or "") or {}).items() if k not in ("texts", "recent")} or None,
                "profile": company_profiles.summary(profiles_by_id.get(t.get("company_id") or ""))}
               for t in p.targets]
    hits = {h.candidate_id: h for h in session.scalars(select(SourcingHit).where(SourcingHit.job_id == job.id))}
    pairs = [x for x in session.scalars(select(CandidateJob).where(CandidateJob.job_id == job.id,
                                                                   CandidateJob.candidate_id.in_(list(hits) or [None])))]
    stopped = set(session.scalars(select(Candidate.id).where(Candidate.id.in_(list(hits) or [None]),
                                                             Candidate.do_not_contact_at.is_not(None))))
    waiting = [x for x in pairs if x.pair_state in WAITING and x.triage_band in ("priority", "review_later")
               and x.candidate_id not in stopped]
    waiting.sort(key=lambda x: (x.triage_band != "priority", -(hits[x.candidate_id].created_at.timestamp())))
    ids = [x.candidate_id for x in waiting[:100]]
    who, facts = names(session, ids), _people_facts(session, org_id, ids)
    rows = _gap_rows_many(session, org_id, job, ids) if ids else {}
    queries = {q.id: q for q in session.scalars(select(SourcingQuery).where(SourcingQuery.job_id == job.id))}
    suggestions = []
    for x in waiting[:100]:
        h = hits[x.candidate_id]
        q = queries.get(h.query_id) if h.query_id else None
        suggestions.append({"candidate_id": str(x.candidate_id), "name": who.get(x.candidate_id), "band": x.triage_band,
                            "reason": x.triage_reason, "match_tier": x.match_tier, "state": x.pair_state,
                            **facts[x.candidate_id], **_gap_summary(rows.get(x.candidate_id, [])),
                            "found_by": {"channel": h.channel, "target": h.target, "tier": h.tier, "query": q.text if q else None,
                                         "at": h.created_at.isoformat() if h.created_at else None, "new_to_desk": h.new_to_desk}})
    runs = list(session.scalars(select(SourcingRun).where(SourcingRun.job_id == job.id).order_by(SourcingRun.started_at.desc()).limit(10)))
    return {
        "job_id": str(job.id), "title": job.title, "state": job.state,
        "plan": {"version": p.version, "mode": p.mode, "target": p.target, "monthly_budget_usd": float(p.monthly_budget_usd),
                 "role_variants": p.role_variants, "countries": p.countries, "targets": targets,
                 "dna": p.dna, "rules": strategy.rules(p), "open_tiers": p.open_tiers,
                 "changed_by": p.created_by, "changed_at": p.created_at.isoformat() if p.created_at else None},
        "hiring": hiring.company_summary(session, session.get(Company, job.hiring_company_id) if job.hiring_company_id else None),
        "budget": {"role_spent_usd": round(costs.sourcing_spent(session, org_id, job.id), 4),
                   "role_budget_usd": float(p.monthly_budget_usd),
                   "desk_spent_usd": round(costs.sourcing_spent(session, org_id), 4), "desk_budget_usd": desk_budget(session, org_id)},
        "strong_waiting": strong_waiting(session, job.id),
        "widening": strategy.widening(session, org_id, job, p),
        "building": session.scalar(select(func.count()).select_from(Task).where(
            Task.kind == "sourcing_strategy", Task.dedupe_key == f"strategy:{job.id}", Task.status.in_(("queued", "running")))) > 0,
        "web_ready": bool(env("EXA_API_KEY")),
        "running": any(r.status == "running" for r in runs),
        "runs": [{"id": str(r.id), "trigger": r.trigger, "status": r.status, "stop_reason": r.stop_reason, "found": r.found,
                  "new": r.new, "known": r.known, "refused": r.refused, "strong": r.strong, "cost_usd": float(r.cost_usd or 0),
                  "report": r.report, "error": r.error, "started_at": r.started_at.isoformat() if r.started_at else None,
                  "ended_at": r.ended_at.isoformat() if r.ended_at else None} for r in runs],
        "suggestions": suggestions,
        "suggestions_total": len(waiting),
    }
