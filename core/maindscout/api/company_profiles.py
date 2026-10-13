"""Company profiles from Exa (docs/next/PLAN.md section 4b, K2): the middle level of company knowledge.

1. Known: a company profiled in the last 6 months (or researched in depth) costs nothing.
2. Profile (here): by Exa company id, about $0.001 a page and up to 100 a call; by name, about $0.007, accepted only
   when a key confirms it is the same company (its website, LinkedIn page or Exa id). The page is read without a model
   (`intelligence/company_profile.py`): its keys and other names, its facts quoted line by line into the shared public
   tier through the research writer (third-party estimates: web inference), and the fields the search strategy uses
   (where the team works, departments, talent sources), kept on the company record. Never executives or emails.
3. Depth: Grok research (`research.py`), only for hiring companies, live targets and employers of candidates about
   to be submitted. Where both give a fact, `research.cross_check` marks agreement or disagreement.

Paid calls go to the cost ledger as sourcing spend (`sourcing_company_profile`), inside the sourcing budgets.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from maindscout.api import companies, costs, research
from maindscout.db.models import Company
from maindscout.intelligence import company_profile, exa

FRESH = timedelta(days=180)
PURPOSE = "sourcing_company_profile"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fresh(company: Company, now: datetime | None = None) -> bool:
    now = now or _now()
    return company.profiled_at is not None and now - company.profiled_at < FRESH


def summary(company: Company | None) -> dict[str, Any] | None:
    """What a person needs at a glance: kind, size, where, stage, and where its team works."""
    p = (company.exa_profile or {}) if company is not None else {}
    if not p:
        return None
    latest = (p.get("rounds") or [{}])[0]
    return {"industry": p.get("industry"), "kind": p.get("kind"), "employees": p.get("employees"), "hq": p.get("hq"),
            "founded": p.get("founded"), "latest_round": f"{latest.get('stage')} {latest.get('date', '')[:7]}".strip() if latest else None,
            "team_countries": [c for c in p.get("countries") or [] if (c.get("pct") or 0) >= 10][:3],
            "categories": (p.get("categories") or [])[:4]}


def apply(session: Session, company: Company, found: exa.Found, org_id: uuid.UUID | None = None,
          subject_id: uuid.UUID | None = None) -> Company:
    """Store one Exa company page on the company: keys, other names, profile fields, quoted facts."""
    profile = company_profile.read(found.text)
    companies.learn_keys(session, company, exa_id=found.entity_id, linkedin=profile.linkedin or found.url,
                         domain=profile.homepage, aliases=profile.aliases, org_id=org_id, subject_id=subject_id)
    company.exa_profile = profile.as_json()
    company.profiled_at = _now()
    if profile.hq_country and not company.hq_country:
        company.hq_country = profile.hq_country
    source = found.entity_id or found.url
    written = research.write_facts(session, company, company_profile.facts(profile, source), _now(),
                                   detail=f"Exa company profile {company_profile.PROFILE_VERSION}")
    research.cross_check(session, company)
    session.flush()
    if written:
        from maindscout.api import profiles

        profiles.queue_for_company(session, company.id)  # kind, size and stage feed the career readings
    return company


def by_ids(session: Session, wanted: dict[str, Company | None], caller, org_id: uuid.UUID | None,
           job_id: uuid.UUID | None = None, task_id=None) -> dict[str, Company]:
    """Profile companies by their Exa ids in one call per 100. `wanted` maps an Exa id to the company it belongs to
    (or None: found by the id, or made from the page's name). Fresh ones are not fetched again."""
    out: dict[str, Company] = {}
    todo = []
    for exa_id, company in wanted.items():
        known = company or companies.by_key(session, exa_id=exa_id)
        if known is not None and fresh(known):
            out[exa_id] = known
        else:
            todo.append(exa_id)
    for start in range(0, len(todo), exa.MAX_FETCH):
        batch = todo[start:start + exa.MAX_FETCH]
        results = exa.fetch(caller, batch)
        costs.record(session, org_id, PURPOSE, {"model": "exa", "usd": results.usd, "sources": len(results.found)},
                     subject_type="job" if job_id else None, subject_id=job_id, task_id=task_id)
        for found in results.found:
            exa_id = found.entity_id or found.url
            company = wanted.get(exa_id) or companies.by_key(session, exa_id=exa_id)
            if company is None:
                name = (found.company or {}).get("name") or company_profile.read(found.text).name
                if not name:
                    continue
                company, _ = companies.resolve(session, name, "exa", keys={"exa_id": exa_id})
                if company is None:
                    continue
            out[exa_id] = apply(session, companies.canonical(session, company), found, org_id)
    return out


def by_name(session: Session, company: Company, caller, org_id: uuid.UUID | None, job_id: uuid.UUID | None = None,
            task_id=None) -> bool:
    """Profile a company we know by name and at least one key, through a company search. A result counts only when a
    key confirms it (the same website, LinkedIn page or Exa id): a similar name is never enough."""
    if fresh(company):
        return True
    if not (company.domain or company.linkedin or company.exa_id):
        return False
    if company.exa_id:
        return bool(by_ids(session, {company.exa_id: company}, caller, org_id, job_id, task_id))
    hint = company.domain or f"linkedin.com/company/{company.linkedin}"
    results = exa.search(caller, f"{company.name} ({hint})", "company", num_results=3, text_chars=8000)
    costs.record(session, org_id, PURPOSE, {"model": "exa", "usd": results.usd, "sources": len(results.found)},
                 subject_type="job" if job_id else None, subject_id=job_id, task_id=task_id)
    for found in results.found:
        p = company_profile.read(found.text)
        same = ((company.domain and companies.domain_of(p.homepage or found.url) == company.domain)
                or (company.linkedin and companies.linkedin_of(p.linkedin) == company.linkedin))
        if same:
            apply(session, company, found, org_id)
            return True
    return False
