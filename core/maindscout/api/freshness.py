"""Freshness (Slice 4, step 3): who and which clients have gone stale, and who is most worth re-contacting.

A person is fresh while the later of "last contacted" and "facts last verified" is within FRESH_PERSON_MONTHS (default
6); a client while the later of our last contact and its facts' research is within FRESH_COMPANY_MONTHS (default 12).
The re-contact list orders stale people by what makes them valuable to the desk now, with the reasons shown: priority
on a live job, a strong match on a live job, a talent pool, a strong career; the longest-silent first among equals.
An order with reasons, never a score.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.api import relationship
from maindscout.db.models import (Activity, Candidate, CandidateJob, CandidateTag, ClientContact, Company, Job)
from maindscout.settings import env

LIVE_JOB = ("open", "on_hold")


def _months(name: str, default: int) -> int:
    try:
        return max(1, int(env(name, str(default)) or default))
    except ValueError:
        return default


def person_months() -> int:
    return _months("FRESH_PERSON_MONTHS", 6)


def company_months() -> int:
    return _months("FRESH_COMPANY_MONTHS", 12)


def _status(last: datetime | None, months: int, now: datetime) -> dict[str, Any]:
    if last is None:
        return {"status": "stale", "since": None, "words": "never contacted or verified"}
    age = now - last
    stale = age > timedelta(days=30.4 * months)
    return {"status": "stale" if stale else "fresh", "since": last.isoformat(), "words": f"last touched {_ago(age)}"}


def _ago(age: timedelta) -> str:
    if age.days < 1:
        return "today"
    if age.days < 31:
        return f"{age.days} days ago"
    months = int(age.days / 30.4)
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = months // 12
    return f"{years} year{'s' if years != 1 else ''} ago"


def of_person(session: Session, org_id, candidate_id, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    dates = [relationship.last_contacted(session, org_id, "candidate", candidate_id),
             relationship.last_verified(session, org_id, candidate_id)]
    return _status(max([d for d in dates if d], default=None), person_months(), now)


def of_company(session: Session, org_id, company: Company, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    dates = [relationship.last_contacted(session, org_id, "company", company.id), company.researched_at]
    return _status(max([d for d in dates if d], default=None), company_months(), now)


def recontact(session: Session, org_id, limit: int = 50, now: datetime | None = None) -> list[dict[str, Any]]:
    """Stale people, most valuable to the desk first, each with why."""
    from maindscout.api import profiles
    from maindscout.api.queries import names

    now = now or datetime.now(timezone.utc)
    people = list(session.scalars(select(Candidate).where(Candidate.org_id == org_id, Candidate.archived_at.is_(None),
                                                          Candidate.merged_into_id.is_(None))))
    live = {j.id: j for j in session.scalars(select(Job).where(Job.org_id == org_id, Job.state.in_(LIVE_JOB)))}
    pairs: dict[uuid.UUID, list[CandidateJob]] = {}
    for p in session.scalars(select(CandidateJob).where(CandidateJob.org_id == org_id, CandidateJob.job_id.in_(list(live) or [None]))):
        pairs.setdefault(p.candidate_id, []).append(p)
    tags: dict[uuid.UUID, list[str]] = {}
    for cid, tag in session.execute(select(CandidateTag.candidate_id, CandidateTag.tag).where(CandidateTag.org_id == org_id)):
        tags.setdefault(cid, []).append(tag)
    rows = []
    for person in people:
        fresh = of_person(session, org_id, person.id, now)
        if fresh["status"] != "stale":
            continue
        mine = [p for p in pairs.get(person.id, []) if p.pair_state not in ("we_passed", "withdrawn", "client_rejected", "placed")]
        priority = [live[p.job_id].title for p in mine if p.triage_band == "priority"]
        strong = [live[p.job_id].title for p in mine if p.match_tier == "strong" and live[p.job_id].title not in priority]
        snap = profiles.latest(session, person.id)
        reading = snap.profile["reading"]["label"] if snap else None
        why = []
        if priority:
            why.append(f"priority on {', '.join(priority[:2])}")
        if strong:
            why.append(f"strong match for {', '.join(strong[:2])}")
        if tags.get(person.id):
            why.append(f"in {', '.join(sorted(tags[person.id])[:3])}")
        if reading == "strong":
            why.append("strong career")
        since = fresh["since"] or ""
        rows.append({"candidate_id": str(person.id), "why": why, "freshness": fresh,
                     "_key": (not priority, not strong, not tags.get(person.id), reading != "strong", since)})
    rows.sort(key=lambda r: r["_key"])
    rows = rows[:limit]
    who = names(session, [uuid.UUID(r["candidate_id"]) for r in rows])
    for r in rows:
        r.pop("_key")
        r["name"] = who.get(uuid.UUID(r["candidate_id"]))
    return rows


def reconnect(session: Session, org_id, now: datetime | None = None) -> list[dict[str, Any]]:
    """Stale clients that matter: a live job there, or people we know there."""
    now = now or datetime.now(timezone.utc)
    with_jobs = {cid for (cid,) in session.execute(select(Job.hiring_company_id).where(
        Job.org_id == org_id, Job.state.in_(LIVE_JOB), Job.hiring_company_id.is_not(None)))}
    with_contacts = {cid for (cid,) in session.execute(select(ClientContact.company_id).where(ClientContact.org_id == org_id))}
    talked = {cid for (cid,) in session.execute(select(Activity.subject_id).where(Activity.org_id == org_id, Activity.subject_type == "company"))}
    out = []
    for cid in with_jobs | with_contacts | talked:
        company = session.get(Company, cid)
        if company is None:
            continue
        fresh = of_company(session, org_id, company, now)
        if fresh["status"] != "stale":
            continue
        why = (["live job"] if cid in with_jobs else []) + (["contacts on file"] if cid in with_contacts else [])
        out.append({"company_id": str(cid), "name": company.name, "why": why, "freshness": fresh,
                    "_key": (cid not in with_jobs, fresh["since"] or "")})
    out.sort(key=lambda r: r["_key"])
    for r in out:
        r.pop("_key")
    return out


def stale_ids(session: Session, org_id) -> set[uuid.UUID]:
    """People who are stale now (for tags on lists)."""
    now = datetime.now(timezone.utc)
    return {p for p in session.scalars(select(Candidate.id).where(Candidate.org_id == org_id, Candidate.archived_at.is_(None)))
            if of_person(session, org_id, p, now)["status"] == "stale"}
