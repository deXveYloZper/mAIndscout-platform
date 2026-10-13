"""The talent-release radar (docs/next/PLAN.md S1, S3): recent news that companies are releasing talent (layoffs,
insolvency, a shutdown, a site closing, being acquired, restructuring, a hiring freeze, funding trouble).

- **About the role's companies:** a news search for each target company on the market map (not off-limits ones).
- **Across the role's market:** a news search for the hiring company's industries in each of the role's first two
  countries. Exa proposes which companies an article is about; code keeps only a name that looks like a company (or is
  one the desk knows) and that the article names with the event (`intelligence/release.py`), and only then makes it a
  company record.

Every signal keeps the sentence that says so, its page and its date: company news only, never a person's name. A
company releasing talent is searched first on the role's next run, and one found by the market-wide news joins the
plan as "releasing talent". Paid (Exa news, about a cent a search), inside the sourcing budgets: at most 3 searches a
run, the last step of a run, and a search is not repeated within 14 days for the role.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs
from maindscout.db.models import Company, CompanyAlias, CompanySignal, Job, SourcingPlan, SourcingQuery, SourcingRun
from maindscout.domain import companies as company_names
from maindscout.intelligence import release

NEWS_COOLDOWN = timedelta(days=14)
NEWS_DAYS = 120  # "in recent months"
SIGNAL_DAYS = 180  # how long a signal moves a company up a role's searches
MAX_NEWS_PER_RUN = 3
NEWS_RESULTS = 5
NEWS_CHARS = 4000
COMPANIES = {
    "query": "Which companies does this article say are cutting jobs, closing a site or office, insolvent, shutting down, "
             "being acquired, restructuring, freezing hiring or short of funding? Company names only.",
    "schema": {"type": "object", "properties": {"companies": {"type": "array", "items": {"type": "string"}}},
               "required": ["companies"]},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10]) if value else None
    except ValueError:
        return None


def view(s: CompanySignal) -> dict[str, Any]:
    return {"kind": s.kind, "label": release.LABEL.get(s.kind, s.kind), "quote": s.quote, "url": s.url,
            "source": urlparse(s.url).netloc.removeprefix("www."), "published": s.published.isoformat() if s.published else None}


def live(session: Session, org_id: uuid.UUID, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """company id -> its latest signal from the last 6 months (a company merged into another counts for that one)."""
    since = ((now or _now()) - timedelta(days=SIGNAL_DAYS)).date()
    out: dict[str, dict[str, Any]] = {}
    rows = session.scalars(select(CompanySignal).where(CompanySignal.org_id == org_id).order_by(
        CompanySignal.published.desc().nulls_last(), CompanySignal.created_at.desc()))
    for s in rows:
        if (s.published or s.created_at.date()) < since:
            continue
        company = session.get(Company, s.company_id)
        while company is not None and company.merged_into_id is not None:
            company = session.get(Company, company.merged_into_id)
        if company is not None:
            out.setdefault(str(company.id), view(s))
    return out


def _known(session: Session, name: str) -> bool:
    parsed = company_names.normalize(name)
    return parsed.kind == "company" and session.get(CompanyAlias, parsed.normalized) is not None


def _same(seen: dict[str, Company], name: str) -> Company | None:
    """A company already met in this sweep under another form of its name: the same name with a legal form or more
    words ("Acme GmbH", "Acme Holding"), or the acronym in its brackets ("Energiekonzepte Deutschland (EKD)" and "EKD").
    Only to avoid two targets for one company in one sweep: records are never merged here."""
    key = company_names.normalize(name).normalized
    return seen.get(key) or next((c for k, c in seen.items() if company_names.possibly_same(k, key)), None)


def _remember(seen: dict[str, Company], name: str, company: Company) -> None:
    parsed = company_names.normalize(name)
    seen[parsed.normalized] = company
    if parsed.note and re.fullmatch(r"[A-Z0-9&.-]{2,10}", parsed.note):
        seen[parsed.note.lower()] = company


def _names(session: Session, company: Company) -> list[str]:
    aliases = session.scalars(select(CompanyAlias.normalized).where(CompanyAlias.company_id == company.id))
    return [company.name, *aliases]


def queries(p: SourcingPlan, hiring_summary: dict[str, Any], limits: dict[str, str]) -> list[dict[str, Any]]:
    """The radar's searches for a plan, in order: the role's market (its industries, first two countries), then each
    target company (pinned first). They name industries, companies and places, never a person."""
    from maindscout.domain import geo

    out: list[dict[str, Any]] = []
    domains = [d for d in hiring_summary.get("domains") or [] if d][:2]
    if domains:
        for c in (p.countries or [None])[:2]:
            where = f" in {geo.name_of(c)}" if c else ""
            out.append({"text": f"{' and '.join(domains)} companies cutting jobs, closing sites or insolvent{where}",
                        "market": True, "company_id": None, "name": None, "country": c})
    order = {t: i for i, t in enumerate(("named", "manual", "known", "peer", "adjacent"))}
    for t in sorted((t for t in p.targets if not t.get("removed") and t.get("tier") != "release"),
                    key=lambda t: (not t.get("pinned"), order.get(t.get("tier"), 9))):
        if t.get("company_id") in limits:
            continue  # never sourced from, so its news does not matter here
        out.append({"text": f"{t['name']} layoffs, job cuts, restructuring or closure", "market": False,
                    "company_id": t.get("company_id"), "name": t["name"], "country": None})
    return out


def _store(session: Session, org_id: uuid.UUID, job: Job, company: Company, signal: release.Signal, url: str,
           published: date | None) -> bool:
    if session.scalar(select(CompanySignal.id).where(CompanySignal.org_id == org_id, CompanySignal.company_id == company.id,
                                                     CompanySignal.url == url, CompanySignal.kind == signal.kind)):
        return False
    session.add(CompanySignal(org_id=org_id, company_id=company.id, kind=signal.kind, quote=signal.quote, url=url,
                              published=published, job_id=job.id))
    session.flush()
    return True


def sweep(session: Session, org_id: uuid.UUID, job: Job, p: SourcingPlan, caller, row: SourcingRun,
          report: dict[str, Any], task_id=None) -> int:
    """The radar step of a run: up to 3 news searches not made in the last 14 days. Returns how many it made."""
    from maindscout.api import autosource, companies, hiring, marketmap
    from maindscout.intelligence import exa

    hiring_company = session.get(Company, job.hiring_company_id) if job.hiring_company_id else None
    limits = autosource.off_limits(session, org_id)
    out: dict[str, Any] = {"queries": [], "flagged": [], "added": [], "stopped": None}
    report["radar"] = out
    since = (_now() - timedelta(days=NEWS_DAYS)).date()
    on_plan = {t.get("company_id") for t in p.targets}
    new_targets: list[dict[str, Any]] = []
    seen: dict[str, Company] = {}  # names (and acronyms) met in this sweep -> their company
    made = 0
    from maindscout.api import company_profiles

    summary = hiring.company_summary(session, hiring_company) or {}
    markets = (company_profiles.summary(hiring_company) or {}).get("domains")
    if markets:
        summary = {**summary, "domains": markets}  # its markets, read from its own description (phase 1b)
    for q in queries(p, summary, limits):
        if made >= MAX_NEWS_PER_RUN:
            break
        key = autosource._key("exa_news", q["text"], q["country"])
        sq = session.scalar(select(SourcingQuery).where(SourcingQuery.job_id == job.id, SourcingQuery.key == key))
        if sq is not None and sq.last_run_at and sq.last_run_at > _now() - NEWS_COOLDOWN:
            continue
        if why := autosource._budget_left(session, org_id, job, p):
            out["stopped"] = why
            break
        if sq is None:
            sq = SourcingQuery(org_id=org_id, job_id=job.id, key=key, channel="exa_news", text=q["text"], target=q["name"],
                               tier="release", country=q["country"], runs=0, results=0, new=0, cost_usd=0)
            session.add(sq)
            session.flush()
        try:
            results = exa.search(caller, q["text"], "news", num_results=NEWS_RESULTS, country=q["country"],
                                 text_chars=NEWS_CHARS, since=since.isoformat(), summary=COMPANIES if q["market"] else None)
        except exa.ExaError as error:
            row.error = str(error)[:500]
            out["stopped"] = "error"
            break
        made += 1
        costs.record(session, org_id, "sourcing_exa_news", {"model": "exa", "usd": results.usd, "sources": len(results.found)},
                     subject_type="job", subject_id=job.id, task_id=task_id)
        sq.runs += 1
        sq.results += len(results.found)
        sq.cost_usd = float(sq.cost_usd or 0) + results.usd
        sq.last_run_at = _now()
        row.cost_usd = float(row.cost_usd or 0) + results.usd
        entry = {"text": q["text"], "results": len(results.found), "signals": 0, "companies": []}
        for found in results.found:
            published = _day(found.published)
            if published is not None and published < since:
                continue
            if q["market"] and markets and not any(m.lower() in (found.title + " " + found.text).lower() for m in markets):
                continue  # market news must be about the hiring company's market (a diamond mine is not earth observation)
            if q["market"]:
                proposed = (found.summary or {}).get("companies") if isinstance(found.summary, dict) else None
                names = [n.strip() for n in proposed or [] if isinstance(n, str) and n.strip()][:5]
            else:
                names = [q["name"]]
            for name in names:
                if q["market"]:
                    if not (_known(session, name) or release.looks_like_a_company(name, found.title, found.text)):
                        continue  # two plain capitalised words could be a person: never a company record
                    signals = release.read(found.title, found.text, [name])
                    if not signals:
                        continue  # no sentence of the article names it with the event: not even a company record
                    company = _same(seen, name)
                    if company is None:
                        company, _ = companies.resolve(session, name, "web")
                        company = companies.canonical(session, company)
                    if company is not None:
                        _remember(seen, name, company)
                else:
                    company = companies.canonical(session, session.get(Company, uuid.UUID(q["company_id"])))
                    signals = release.read(found.title, found.text, _names(session, company)) if company else []
                if company is None or not signals:
                    continue
                stored = sum(_store(session, org_id, job, company, s, found.url, published) for s in signals)
                entry["signals"] += stored
                sq.new += stored
                if company.name not in entry["companies"]:
                    entry["companies"].append(company.name)
                if str(company.id) in on_plan:
                    if company.name not in out["flagged"]:
                        out["flagged"].append(company.name)
                elif (str(company.id) not in limits and company.id != (hiring_company.id if hiring_company else None)
                      and str(company.id) not in {t["company_id"] for t in new_targets}):
                    first = signals[0]
                    when = f" ({published.isoformat()})" if published else ""
                    target = marketmap._target(company, "release", [f"{release.LABEL[first.kind]} in the news{when}: “{first.quote}”"],
                                               "exa_news")
                    new_targets.append(target)
                    out["added"].append(company.name)
        out["queries"].append(entry)
    if new_targets:
        current = autosource.current_plan(session, job.id)
        autosource.update_plan(session, org_id, job.id, "talent-release radar", targets=[*current.targets, *new_targets])
    return made
