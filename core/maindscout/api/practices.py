"""Employer evidence (owner, 2026-10-17): what a company uses in its own work, and what that says about its people.

- **Reading** (`read_company`): one web search for the company's job adverts, its own pages only (`practices.own_page`),
  one model call that lists its technologies, tools, methods and standards, each quoted from its page. Stored as
  `CompanyPracticeClaim`s in the public tier with the page as evidence; re-read after 180 days. Paid inside the role's
  sourcing budget (about 1-2 cents a company). A search names a company and a kind of role, never a person.
- **Using it** (`employer_facts`): each practice is handed to the gap table once per career step at that company, with
  the step's title and dates, so `gaps.employer_support` can say a skill is likely: the company uses it in their area of
  work, and they were there within two years of the advert. Likely is never proof (matching: partly met, at most
  possible); a person confirms it on the call.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import companies, costs, writer
from maindscout.db.models import PUBLIC_ORG_ID, Claim, ClaimObservation, Company, Evidence, Job
from maindscout.domain import gaps
from maindscout.intelligence import exa
from maindscout.intelligence import practices as engine

LIVE = ("proposed", "approved")
CLAIM = gaps.PRACTICE
FRESH_FOR = timedelta(days=180)
PURPOSE = "sourcing_company_practices"
SEARCH_RESULTS = 8
COST_ESTIMATE = 0.02  # a search ($0.007) and one short model call, with a margin
REMATCH_CAP = 300  # people re-judged after a company is read


def _now() -> datetime:
    return datetime.now(timezone.utc)


def fresh(company: Company | None, now: datetime | None = None) -> bool:
    return bool(company is not None and company.practices_at and (now or _now()) - company.practices_at < FRESH_FOR)


def queue(session: Session, org_id: uuid.UUID, job: Job, company: Company | None, title: str | None = None) -> bool:
    """Read a company's adverts in the background, once per 180 days. Off with PRACTICES_AUTO=false."""
    from maindscout.api import tasks
    from maindscout.settings import env

    company = companies.canonical(session, company)
    if company is None or fresh(company) or (env("PRACTICES_AUTO", "true") or "").lower() in ("0", "false", "no", "off"):
        return False
    tasks.enqueue(session, org_id, "read_practices", {"company_id": str(company.id), "job_id": str(job.id), "title": title},
                  priority=120, dedupe_key=f"practices:{company.id}")
    return True


def read_company(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, company_id: uuid.UUID, caller, client,
                 title: str | None = None, task_id=None) -> dict[str, Any]:
    from maindscout.api import autosource

    job = session.get(Job, job_id)
    company = companies.canonical(session, session.get(Company, company_id))
    if job is None or job.org_id != org_id or company is None:
        return {"status": "skipped", "reason": "no such role or company"}
    if fresh(company):
        return {"status": "fresh"}
    plan = autosource.current_plan(session, job.id)
    if plan is not None and (why := autosource._budget_left(session, org_id, job, plan, COST_ESTIMATE)):
        return {"status": "skipped", "reason": why}
    results = exa.search(caller, engine.query(company.name, title), None, num_results=SEARCH_RESULTS, text_chars=engine.PAGE_CHARS)
    costs.record(session, org_id, PURPOSE, {"model": "exa", "usd": results.usd, "sources": len(results.found)},
                 subject_type="job", subject_id=job.id, task_id=task_id)
    pages = [f for f in results.found if engine.own_page(f, company.name, company.domain)][:engine.MAX_PAGES]
    now = _now()
    company.practices_at = now
    if not pages:
        session.flush()
        return {"status": "no_adverts", "searched": len(results.found)}
    reading = engine.read(pages, company.name, client)
    costs.record(session, org_id, PURPOSE, reading.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    written = write(session, company, pages, reading.items, now.date())
    rematched = rematch_people_at(session, org_id, company)
    return {"status": "read", "pages": [p.url for p in pages], "practices": sorted({i.token for i in reading.items}),
            "written": written, "rejected": reading.rejected, "rematched": rematched,
            "usd": round(results.usd + float(reading.cost.get("usd") or 0), 4)}


def _seen_on(page: exa.Found, today: date) -> date:
    try:
        return date.fromisoformat((page.published or "")[:10])
    except ValueError:
        return today


def write(session: Session, company: Company, pages: list[exa.Found], items: list[engine.Item], today: date) -> int:
    """Each practice with its page as evidence. The same practice seen again is a new observation of one claim, and the
    claim keeps the latest date it was seen (matching measures time from it). Returns how many claims are new."""
    written = 0
    for item in items:
        page = pages[item.page]
        seen = min(_seen_on(page, today), today)
        payload = {"token": item.token, "raw_label": item.raw_label, "kind": item.kind, "area": item.area}
        key = f"{company.id}|practice|{item.token}|{item.area}"
        claim = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                                   Claim.claim_type == CLAIM, Claim.natural_key == key, Claim.status.in_(LIVE)))
        if claim is None:
            claim = writer.add_claim(session, org_id=PUBLIC_ORG_ID, subject_type="company", subject_id=company.id,
                                     claim_type=CLAIM, payload=payload, flags={}, natural_key=key, status="proposed",
                                     observed_as_of=seen, temporal_precision="unknown")
            written += 1
        elif claim.observed_as_of is None or claim.observed_as_of < seen:
            claim.observed_as_of = seen
        already = session.scalar(select(Evidence.id).where(Evidence.claim_id == claim.id, Evidence.snippet == item.quote,
                                                           Evidence.locator["url"].astext == page.url).limit(1))
        if already:
            continue
        evidence = Evidence(org_id=PUBLIC_ORG_ID, claim_id=claim.id, evidence_type="research_result", document_id=None,
                            locator={"url": page.url, "title": page.title}, snippet=item.quote,
                            source_authority="employer_authored", origin="employer", observed_as_of=seen,
                            span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none",
                                             "detail": f"job advert, {engine.READER_VERSION}"})
        session.add(evidence)
        session.flush()
        session.add(ClaimObservation(org_id=PUBLIC_ORG_ID, claim_id=claim.id, attribute_path=".", value=payload,
                                     evidence_id=evidence.id, source_authority="employer_authored", origin="employer",
                                     observed_as_of=seen))
    session.flush()
    return written


def rematch_people_at(session: Session, org_id: uuid.UUID, company: Company) -> int:
    """Everyone on the desk with a career step at the company, matched again with what it uses."""
    from maindscout.api.process import retriage_candidate

    ids = companies._ids_for(session, company)
    people = list(dict.fromkeys(session.scalars(select(Claim.subject_id).where(
        Claim.org_id == org_id, Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
        Claim.payload["company"]["company_id"].astext.in_(ids) | Claim.approved_view["company"]["company_id"].astext.in_(ids)))))
    for cid in people[:REMATCH_CAP]:
        retriage_candidate(session, org_id, cid, {"act": "employer_practices", "company_id": str(company.id)}, "system")
    return min(len(people), REMATCH_CAP)


def employer_facts(session: Session, claims_by_person: dict[uuid.UUID, list[Claim]]) -> dict[uuid.UUID, list[gaps.Fact]]:
    """For each person, their employers' practices as gap-table facts: one per career step and practice, carrying
    the step's title and dates, the company's name and when the advert said so. Three queries for everyone."""
    steps: list[tuple[uuid.UUID, Claim, str]] = []
    for cid, mine in claims_by_person.items():
        for c in mine:
            if c.claim_type != "CareerStepClaim":
                continue
            company_id = ((c.approved_view or c.payload).get("company") or {}).get("company_id")
            if company_id:
                steps.append((cid, c, company_id))
    if not steps:
        return {}
    known = {str(i): (str(m) if m else str(i), n) for i, m, n in session.execute(select(Company.id, Company.merged_into_id, Company.name).where(
        Company.id.in_([uuid.UUID(x) for x in {s[2] for s in steps}])))}
    top = {k: v[0] for k, v in known.items()}
    for _ in range(3):  # merged twice over is rare; follow a few links
        parents = [v for v in set(top.values()) if v not in known]
        if not parents:
            break
        for i, m, n in session.execute(select(Company.id, Company.merged_into_id, Company.name).where(
                Company.id.in_([uuid.UUID(x) for x in parents]))):
            known[str(i)] = (str(m) if m else str(i), n)
        top = {k: (known[v][0] if v in known else v) for k, v in top.items()}
    practices: dict[str, list[Claim]] = defaultdict(list)
    for p in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.claim_type == CLAIM, Claim.status.in_(LIVE),
                                                 Claim.subject_id.in_([uuid.UUID(x) for x in set(top.values())]))):
        practices[str(p.subject_id)].append(p)
    if not practices:
        return {}
    quotes: dict[uuid.UUID, str] = {}
    for claim_id, snippet in session.execute(select(Evidence.claim_id, Evidence.snippet).where(
            Evidence.claim_id.in_([p.id for ps in practices.values() for p in ps])).order_by(Evidence.created_at)):
        quotes[claim_id] = snippet  # the latest quote
    out: dict[uuid.UUID, list[gaps.Fact]] = defaultdict(list)
    for cid, step, company_id in steps:
        canonical = top.get(company_id, company_id)
        name = known.get(canonical, (None, None))[1] or (step.approved_view or step.payload)["company"].get("raw_name")
        for p in practices.get(canonical, []):
            out[cid].append(gaps.Fact(str(p.id), CLAIM, {**(p.approved_view or p.payload), "company": name,
                                                         "title": (step.approved_view or step.payload).get("title_raw"),
                                                         "as_of": p.observed_as_of.isoformat() if p.observed_as_of else None},
                                      p.status, step.valid_from, step.valid_to, quotes.get(p.id)))
    return dict(out)


def of_company(session: Session, company: Company) -> list[dict[str, Any]]:
    """What the desk knows a company uses, with the advert that says so (for the company page)."""
    company = companies.canonical(session, company)
    out = []
    for p in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                                 Claim.claim_type == CLAIM, Claim.status.in_(LIVE)).order_by(Claim.created_at)):
        ev = session.scalar(select(Evidence).where(Evidence.claim_id == p.id).order_by(Evidence.created_at.desc()).limit(1))
        out.append({"id": str(p.id), **(p.approved_view or p.payload), "status": p.status,
                    "seen": p.observed_as_of.isoformat() if p.observed_as_of else None,
                    "quote": ev.snippet if ev else None, "url": (ev.locator or {}).get("url") if ev else None})
    return out
