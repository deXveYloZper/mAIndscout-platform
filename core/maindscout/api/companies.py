"""Companies: resolve names to shared company records, merge by human decision, and answer "who do we know there".

Companies live in the shared public tier. Which people worked at a company is read from each desk's own career
claims (org-scoped), so one desk never sees another desk's people.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from maindscout.db.models import Candidate, Claim, Company, CompanyAlias, Decision, DecisionItem, Job
from maindscout.domain import companies as names

LIVE = ("proposed", "approved")


def canonical(session: Session, company: Company | None) -> Company | None:
    """Follow merge redirects to the company that stands today."""
    seen = set()
    while company is not None and company.merged_into_id and company.id not in seen:
        seen.add(company.id)
        company = session.get(Company, company.merged_into_id)
    return company


# --- identity keys (phase 1b) -----------------------------------------------------------------------------------------
# A company is found by its keys before its name: its website, its Exa company id, its LinkedIn company page. Two names
# that share a key are one company; a key is not a guess, so a new name with a known key becomes an alias of it.

KEYS = ("exa_id", "linkedin", "domain")
NOT_A_WEBSITE = ("linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com", "crunchbase.com", "github.com",
                 "medium.com", "linktr.ee", "wixsite.com", "exa.ai", "google.com", "youtube.com", "angel.co", "wellfound.com")


def domain_of(url: str | None) -> str | None:
    """'https://www.Procure.ai/en' -> 'procure.ai'. Profile and social sites are not a company's website."""
    text = (url or "").strip().lower()
    if not text:
        return None
    host = re.sub(r"^[a-z]+://", "", text).split("/")[0].split("?")[0].split("#")[0].split(":")[0].removeprefix("www.")
    if "." not in host or any(host == h or host.endswith("." + h) for h in NOT_A_WEBSITE):
        return None
    return host


def linkedin_of(value: str | None) -> str | None:
    """'https://www.linkedin.com/company/procureai/' or 'procureai' -> 'procureai'."""
    text = (value or "").strip()
    m = re.search(r"linkedin\.com/company/([^/?#\s]+)", text, re.I)
    slug = m.group(1) if m else (text if re.fullmatch(r"[A-Za-z0-9_.%-]+", text) else None)
    return slug.lower().strip("/") if slug else None


def by_key(session: Session, *, exa_id: str | None = None, linkedin: str | None = None,
           domain: str | None = None) -> Company | None:
    """The company that holds one of these keys (strongest first), followed to the one that stands today."""
    for column, value in ((Company.exa_id, exa_id), (Company.linkedin, linkedin_of(linkedin)), (Company.domain, domain_of(domain))):
        if value:
            hit = session.scalar(select(Company).where(column == value).order_by(Company.created_at).limit(1))
            if hit is not None:
                return canonical(session, hit)
    return None


def learn_keys(session: Session, company: Company, *, exa_id: str | None = None, linkedin: str | None = None,
               domain: str | None = None, aliases: tuple[str, ...] | list[str] = (), org_id: uuid.UUID | None = None,
               subject_id: uuid.UUID | None = None) -> Company | None:
    """Give a company the keys it does not have yet. A key another company already holds is never moved: the two
    may be one company, so a person decides ("Same company?", filed when an org is given). Returns the other company
    in that case. Aliases (other names a profile lists) are added when nobody holds them."""
    found = {"exa_id": exa_id, "linkedin": linkedin_of(linkedin), "domain": domain_of(domain)}
    clash = None
    for key, value in found.items():
        if not value or getattr(company, key) == value:
            continue
        other = canonical(session, session.scalar(select(Company).where(getattr(Company, key) == value,
                                                                        Company.id != company.id).limit(1)))
        if other is not None and other.id != company.id:
            clash = other
            continue
        if getattr(company, key) is None:
            setattr(company, key, value)
    for name in aliases:
        parsed = names.normalize(name)
        if parsed.kind == "company" and parsed.normalized and session.get(CompanyAlias, parsed.normalized) is None:
            session.add(CompanyAlias(normalized=parsed.normalized, company_id=company.id, source="profile"))
            session.flush()
    session.flush()
    if clash is not None and org_id is not None:
        _same_card(session, company, clash, org_id, subject_id, why="they share a website, LinkedIn page or Exa id")
    return clash


def _same_card(session: Session, company: Company, other: Company, org_id: uuid.UUID, subject_id: uuid.UUID | None,
               why: str | None = None) -> None:
    if session.scalar(select(Decision.id).where(Decision.org_id == org_id, Decision.type == "company_same",
                                                Decision.sealed_at.is_(None), Decision.subject_id == company.id,
                                                Decision.context["existing"]["id"].astext == str(other.id)).limit(1)):
        return
    session.add(Decision(org_id=org_id, type="company_same", priority=30, subject_type="company", subject_id=company.id,
                         context={"question": "same company?", "new": {"id": str(company.id), "name": company.name},
                                  "existing": {"id": str(other.id), "name": other.name},
                                  "candidate_id": str(subject_id) if subject_id else None, **({"why": why} if why else {})}))
    session.flush()


def resolve(session: Session, raw_name: str, source: str, org_id: uuid.UUID | None = None,
            subject_id: uuid.UUID | None = None, keys: dict[str, str | None] | None = None) -> tuple[Company | None, names.CompanyName]:
    """A company record for a name. With keys (website, Exa company id, LinkedIn page), the company holding a key
    wins and the name becomes its alias. Otherwise an exact match on the normalised name, else a new company.
    Self-employment and undisclosed names are not companies. A new name that looks like an existing one raises a
    "Same company?" card for a human (when the caller gives an org and subject); it is never merged automatically.
    Two different companies with one name (their Exa ids differ) stay two records: the second is found by its key."""
    parsed = names.normalize(raw_name)
    if parsed.kind != "company":
        return None, parsed
    keys = {k: v for k, v in (keys or {}).items() if k in KEYS and v}
    if keys:
        hit = by_key(session, **keys)
        if hit is not None:
            if session.get(CompanyAlias, parsed.normalized) is None:
                session.add(CompanyAlias(normalized=parsed.normalized, company_id=hit.id, source=source))
                session.flush()
            learn_keys(session, hit, **keys, org_id=org_id, subject_id=subject_id)
            return hit, parsed
    alias = session.get(CompanyAlias, parsed.normalized)
    if alias is not None:
        company = canonical(session, session.get(Company, alias.company_id))
        if keys.get("exa_id") and company is not None and company.exa_id and company.exa_id != keys["exa_id"]:
            # Same name, another company: its own record, reached by its key (the name stays with the first).
            other = Company(name=parsed.display, normalized=f"{parsed.normalized} #{keys['exa_id'].rsplit('/', 1)[-1]}")
            session.add(other)
            session.flush()
            learn_keys(session, other, **keys)
            return other, parsed
        if keys and company is not None:
            learn_keys(session, company, **keys, org_id=org_id, subject_id=subject_id)
        return company, parsed
    company = Company(name=parsed.display, normalized=parsed.normalized)
    session.add(company)
    session.flush()
    session.add(CompanyAlias(normalized=parsed.normalized, company_id=company.id, source=source))
    session.flush()
    if keys:
        learn_keys(session, company, **keys, org_id=org_id, subject_id=subject_id)
    if org_id is not None and subject_id is not None:
        _suggest_duplicates(session, company, org_id, subject_id)
    return company, parsed


def _suggest_duplicates(session: Session, company: Company, org_id: uuid.UUID, subject_id: uuid.UUID) -> None:
    first = company.normalized.split()[0]
    nearby = session.scalars(select(CompanyAlias).where(
        CompanyAlias.company_id != company.id,
        or_(CompanyAlias.normalized.like(f"{first}%"), func.length(CompanyAlias.normalized).between(len(company.normalized) - 1, len(company.normalized) + 1))))
    for alias in nearby:
        if names.possibly_same(company.normalized, alias.normalized):
            other = canonical(session, session.get(Company, alias.company_id))
            if other is None or other.id == company.id:
                continue
            session.add(Decision(org_id=org_id, type="company_same", priority=30, subject_type="company",
                                 subject_id=company.id, context={
                                     "question": "same company?",
                                     "new": {"id": str(company.id), "name": company.name},
                                     "existing": {"id": str(other.id), "name": other.name},
                                     "candidate_id": str(subject_id)}))
            session.flush()
            return


def merge(session: Session, keep_id: uuid.UUID, drop_id: uuid.UUID, actor: str | None = None,
          org_id: uuid.UUID | None = None) -> Company:
    """Fold one company into another: a redirect plus its aliases. Claims keep pointing at the old id and are read
    through the redirect, so nothing about any person is rewritten."""
    keep, drop = canonical(session, session.get(Company, keep_id)), canonical(session, session.get(Company, drop_id))
    if keep is None or drop is None:
        raise LookupError("No such company")
    if keep.id == drop.id:
        return keep
    drop.merged_into_id = keep.id
    drop.merged_by, drop.merged_by_org, drop.merged_at = actor, org_id, datetime.now(timezone.utc)
    for alias in session.scalars(select(CompanyAlias).where(CompanyAlias.company_id == drop.id)):
        alias.company_id = keep.id
    session.flush()
    return keep


def _ids_for(session: Session, company: Company) -> list[str]:
    """The company and everything merged into it."""
    ids, frontier = {company.id}, [company.id]
    while frontier:
        children = list(session.scalars(select(Company.id).where(Company.merged_into_id.in_(frontier))))
        frontier = [c for c in children if c not in ids]
        ids.update(frontier)
    return [str(i) for i in ids]


def people_at(session: Session, org_id: uuid.UUID, company_id: uuid.UUID) -> list[dict[str, Any]]:
    """Who this desk knows at a company: people with a live career step there, with title and period."""
    company = canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    ids = _ids_for(session, company)
    steps = session.scalars(select(Claim).where(
        Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
        Claim.payload["company"]["company_id"].astext.in_(ids)).order_by(Claim.valid_from.desc().nulls_last()))
    from maindscout.api.queries import names as person_names

    rows = list(steps)
    who = person_names(session, list({c.subject_id for c in rows}))
    return [{"candidate_id": str(c.subject_id), "name": who.get(c.subject_id), "title": c.payload.get("title_raw"),
             "valid_from": c.valid_from.isoformat() if c.valid_from else None,
             "valid_to": c.valid_to.isoformat() if c.valid_to else None, "current": c.valid_to is None,
             "status": c.status} for c in rows]


def company_page(session: Session, org_id: uuid.UUID, company_id: uuid.UUID) -> dict[str, Any]:
    from maindscout.api import practices as company_practices

    company = canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    aliases = list(session.scalars(select(CompanyAlias.normalized).where(CompanyAlias.company_id == company.id)))
    jobs = session.scalars(select(Job).where(Job.org_id == org_id, Job.hiring_company_id.in_([uuid.UUID(i) for i in _ids_for(session, company)])))
    stints = people_at(session, org_id, company.id)
    grouped: dict[str, dict[str, Any]] = {}
    for st in stints:  # one row per person, every role they held there
        row = grouped.setdefault(st["candidate_id"], {"candidate_id": st["candidate_id"], "name": st["name"], "roles": [], "current": False})
        row["roles"].append({k: st[k] for k in ("title", "valid_from", "valid_to", "current")})
        row["current"] = row["current"] or st["current"]
    from maindscout.api import company_profiles, freshness, relationship, research
    from maindscout.db.models import Task

    # What the last research attempt did: a failure (the shared research budget used up, the model unreachable) is said
    # as it is, not as "not researched yet" (x-ray A4, 2026-10-13).
    last = session.scalar(select(Task).where(Task.kind == "research_company", Task.payload["company_id"].astext.in_(_ids_for(session, company)))
                          .order_by(Task.created_at.desc()).limit(1))
    attempt = None
    if last is not None and last.status in ("queued", "running", "failed"):
        error = last.error or ""
        attempt = {"status": last.status, "at": (last.finished_at or last.created_at).isoformat() if (last.finished_at or last.created_at) else None,
                   "why": "budget" if "BudgetExceeded" in error else "model" if "LLMError" in error else ("other" if error else None),
                   "error": error.split(": ", 1)[-1][:200] if error else None}
    return {"id": str(company.id), "name": company.name, "website": company.website, "hq_country": company.hq_country,
            # Its keys (how Exa confirms it is this company) and its Exa profile (what the sourcing strategy reads).
            "keys": {"domain": company.domain, "linkedin": company.linkedin, "exa": bool(company.exa_id)},
            "profile": company_profiles.summary(company),
            "research_attempt": attempt,
            "research_status": company.research_status,
            "researched_at": company.researched_at.isoformat() if company.researched_at else None,
            "facts": research.facts(session, company),
            # What it uses in its own work, from its job adverts (employer evidence, owner 2026-10-17).
            "practices": company_practices.of_company(session, company),
            "practices_at": company.practices_at.isoformat() if company.practices_at else None,
            "aliases": sorted(aliases), "people": list(grouped.values()), "people_count": len(grouped),
            "jobs": [{"id": str(j.id), "title": j.title} for j in jobs],
            "contacts": relationship.contacts_at(session, org_id, [uuid.UUID(i) for i in _ids_for(session, company)]),
            "timeline": relationship.timeline(session, org_id, "company", company.id),
            "last_contacted": (lambda d: d.isoformat() if d else None)(relationship.last_contacted(session, org_id, "company", company.id)),
            "freshness": freshness.of_company(session, org_id, company)}


def search(session: Session, org_id: uuid.UUID, q: str | None, limit: int = 50) -> list[dict[str, Any]]:
    """Companies this desk has touched (through people or jobs), optionally filtered by name, most people first."""
    steps = session.execute(select(Claim.payload["company"]["company_id"].astext, Claim.subject_id).where(
        Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
        Claim.payload["company"]["company_id"].astext.is_not(None))).all()
    job_companies = list(session.scalars(select(Job.hiring_company_id).where(Job.org_id == org_id, Job.hiring_company_id.is_not(None))))
    wanted = {uuid.UUID(cid) for cid, _ in steps} | set(job_companies)
    # Every company referenced, and what each was merged into, in one query per hop (merges are rare and shallow).
    known: dict[uuid.UUID, Company] = {}
    frontier = wanted
    while frontier:
        found = list(session.scalars(select(Company).where(Company.id.in_(frontier))))
        known.update({c.id: c for c in found})
        frontier = {c.merged_into_id for c in found if c.merged_into_id and c.merged_into_id not in known}

    def top(cid: uuid.UUID) -> Company | None:
        company = known.get(cid)
        while company is not None and company.merged_into_id:
            company = known.get(company.merged_into_id)
        return company

    counts: dict[uuid.UUID, set] = {}
    for cid, person in steps:
        if company := top(uuid.UUID(cid)):
            counts.setdefault(company.id, set()).add(person)
    for cid in job_companies:
        if company := top(cid):
            counts.setdefault(company.id, set())
    needle = names.normalize(q).normalized if q else None
    aliases: dict[uuid.UUID, set[str]] = {}
    if needle:
        for cid, alias in session.execute(select(CompanyAlias.company_id, CompanyAlias.normalized).where(CompanyAlias.company_id.in_(list(counts) or [None]))):
            aliases.setdefault(cid, set()).add(alias)
    out = []
    for company_id, people in counts.items():
        company = known[company_id]
        if needle and not any(needle in a for a in aliases.get(company_id, set()) | {company.normalized}):
            continue
        out.append({"id": str(company.id), "name": company.name, "people_count": len(people)})
    out.sort(key=lambda c: (-c["people_count"], c["name"].lower()))
    return out[:limit]


def link_org(session: Session, org_id: uuid.UUID) -> dict[str, int]:
    """Resolve companies for this desk's existing career steps and jobs that have no company link yet."""
    linked = 0
    for claim in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim",
                                                     Claim.status.in_(LIVE))):
        company_part = (claim.payload or {}).get("company") or {}
        if company_part.get("company_id"):
            continue
        company, _ = resolve(session, company_part.get("raw_name", ""), "cv", org_id, claim.subject_id)
        if company is not None:
            # The link is machine bookkeeping, not a fact: it goes on the payload only. The approved view is pinned at
            # approval and never rewritten; readers take the company link from the payload (see profiles._view).
            claim.payload = {**claim.payload, "company": {**company_part, "company_id": str(company.id)}}
            linked += 1
    jobs = 0
    for job in session.scalars(select(Job).where(Job.org_id == org_id, Job.hiring_company_id.is_(None), Job.hiring_company.is_not(None))):
        company, _ = resolve(session, job.hiring_company, "jd")
        if company is not None:
            job.hiring_company_id = company.id
            jobs += 1
    session.flush()
    return {"career_steps_linked": linked, "jobs_linked": jobs}
