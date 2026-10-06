"""Write company research into the shared public tier as proposed facts with sources, and decide when to research.

Company facts are claims about a company stored under the reserved public-knowledge org (PUBLIC_ORG_ID), so every
desk reads them and every trust rule applies: evidence with a URL and quote, registry sources as official records,
consequential web facts flagged single-source, nothing approved without a human.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs, writer
from maindscout.api.companies import _ids_for, canonical
from maindscout.db.models import PUBLIC_ORG_ID, Claim, ClaimObservation, Company, Evidence
from maindscout.domain import geo
from maindscout.intelligence import research as engine
from maindscout.intelligence.extract import COUNTRY_ALIASES

LIVE = ("proposed", "approved")
REFRESH_AFTER = {"identified": timedelta(days=180), "not_identified": timedelta(days=30), "failed": timedelta(days=7)}
BASIC_REFRESH = timedelta(days=365)
# Large consultancies and outsourcers: light research only (kind and base). Normalized names (domain.companies).
LIGHT_RESEARCH = frozenset({
    "accenture", "capgemini", "cognizant", "cognizant technology solutions", "deloitte", "epam", "epam systems",
    "infosys", "tata consultancy services", "tcs", "wipro", "hcl", "hcltech", "hcl technologies", "tech mahindra",
    "ltimindtree", "lti", "mindtree", "mphasis", "ntt data", "dxc", "dxc technology", "atos", "sopra steria", "cgi",
    "globant", "luxoft", "endava", "genpact", "ibm consulting", "kpmg", "pwc", "pricewaterhousecoopers", "ey",
    "ernst young", "ernst and young", "persistent systems", "hexaware", "lt technology services", "virtusa", "softserve",
    "sii", "alten", "akkodis", "kpit", "birlasoft", "zensar", "coforge", "unisys", "bearingpoint", "publicis sapient",
})
LIGHT_HEADCOUNT = 5000  # a consultancy / outsourcer at least this big switches to light research after its first look


def depth(company: Company) -> str:
    return "basic" if company.research_depth == "basic" or company.normalized in LIGHT_RESEARCH else "full"
COMPANY_CLAIMS = ("CompanyDomainClaim", "CompanyTypeClaim", "CompanyFoundedClaim", "FundingRoundClaim", "TeamSizeClaim",
                  "CompanyStatusClaim", "CompanyLocationClaim")


def due(company: Company, now: datetime | None = None) -> bool:
    """Research a company that was never researched, or whose last result is older than its freshness window."""
    if company.researched_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    window = REFRESH_AFTER.get(company.research_status or "failed", timedelta(days=7))
    if company.research_status == "identified" and depth(company) == "basic":
        window = BASIC_REFRESH
    return now - company.researched_at > window


def _date(text: str | None) -> str | None:
    """Normalise to YYYY, YYYY-MM or YYYY-MM-DD; None if unreadable."""
    m = re.match(r"(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", (text or "").strip())
    if not m:
        return None
    y, mo, d = m.groups()
    return y + (f"-{int(mo):02d}" if mo else "") + (f"-{int(d):02d}" if mo and d else "")


def _usd(amount: str | None) -> float | None:
    """'$13M' -> 13000000. Only dollars; other currencies keep amount_raw and leave this empty."""
    if not amount or "$" not in amount:
        return None
    m = re.search(r"([\d.,]+)\s*(m|million|b|bn|billion|k|thousand)?", amount.lower().replace(",", ""))
    if not m:
        return None
    scale = {"m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "k": 1e3, "thousand": 1e3}.get(m.group(2) or "", 1)
    return float(m.group(1)) * scale


def _team(raw: str) -> tuple[int | None, int | None]:
    nums = [int(n) for n in re.findall(r"\d+", raw.replace(",", ""))]
    if not nums:
        return None, None
    if len(nums) >= 2:
        return min(nums[:2]), max(nums[:2])
    return (nums[0], None) if re.search(r"more than|over|\+", raw.lower()) else (nums[0], nums[0])


def _country(text: str) -> str | None:
    lowered = text.lower()
    for code, names in COUNTRY_ALIASES.items():
        if any(re.search(rf"\b{re.escape(n)}\b", lowered) for n in names if len(n) > 3):
            return code
    return None


def _payload(fact: engine.Fact, today: date) -> tuple[str, dict[str, Any]] | None:
    v = fact.value
    if fact.kind == "domains":
        domains = sorted({d.strip().lower() for d in v if isinstance(d, str) and len(d.strip()) >= 2})
        return ("CompanyDomainClaim", {"domains": domains}) if domains else None
    if fact.kind == "company_type":
        return "CompanyTypeClaim", {"type": v}
    if fact.kind == "founded":
        d = _date(v)
        return ("CompanyFoundedClaim", {"founded": d}) if d else None
    if fact.kind == "funding_round":
        return "FundingRoundClaim", {"stage": v["stage"], "date": _date(v.get("date")), "amount_raw": v.get("amount"),
                                     "amount_usd": _usd(v.get("amount")), "investors": [i for i in v.get("investors") or [] if i][:10]}
    if fact.kind == "headcount":
        lo, hi = _team(v)
        return "TeamSizeClaim", {"raw": v, "min": lo, "max": hi, "as_of": _date(fact.as_of) or today.isoformat()}
    if fact.kind == "status":
        return "CompanyStatusClaim", {"status": v, "date": None, "detail": None}
    if fact.kind == "hq":
        return "CompanyLocationClaim", {"hq_raw": v, "hq_country": _country(v), "offices": []}
    return None


def _key(company_id: uuid.UUID, claim_type: str, p: dict[str, Any]) -> str:
    part = {"CompanyDomainClaim": "domains", "CompanyTypeClaim": "type", "CompanyFoundedClaim": "founded",
            "CompanyStatusClaim": "status", "CompanyLocationClaim": "hq"}.get(claim_type)
    if part:
        return f"{company_id}|{part}"
    if claim_type == "FundingRoundClaim":
        return f"{company_id}|funding|{p['stage']}|{(p.get('date') or '')[:7]}"
    return f"{company_id}|team|{(p.get('as_of') or '')[:7]}"


def _origin(fact: engine.Fact, website: str | None) -> tuple[str, str]:
    """(source_authority, origin): registries are official records; the company's own site is the company speaking."""
    if fact.registry:
        return "verified_primary", "registry"
    host = engine._host(fact.source_url)
    own = website and engine._host(website) and host.endswith(engine._host(website))
    if own or host.endswith("linkedin.com"):
        return "employer_authored", "employer"
    return "web_inference", "independent_web"


def apply(session: Session, company: Company, outcome: engine.ResearchOutcome) -> dict[str, Any]:
    """Store a research outcome. Returns counts. Same fact seen again = a new observation, not a new claim."""
    now = datetime.now(timezone.utc)
    company.researched_at = now
    company.research_status = "identified" if outcome.identified else "not_identified"
    if outcome.identified and outcome.website and not company.website:
        company.website = outcome.website[:300]
    written = 0
    for fact in outcome.facts:
        made = _payload(fact, now.date())
        if made is None:
            continue
        claim_type, payload = made
        key = _key(company.id, claim_type, payload)
        authority, origin = _origin(fact, company.website)
        claim = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                                   Claim.claim_type == claim_type, Claim.natural_key == key, Claim.status.in_(LIVE)))
        if claim is None:
            consequential = claim_type in ("FundingRoundClaim", "TeamSizeClaim") or payload.get("status") in ("shut_down", "acquired", "merged")
            flags = {"single_source_web": True} if consequential and origin == "independent_web" else {}
            claim = writer.add_claim(session, org_id=PUBLIC_ORG_ID, subject_type="company", subject_id=company.id,
                                     claim_type=claim_type, payload=payload, flags=flags, natural_key=key, status="proposed",
                                     observed_as_of=now.date(), temporal_precision="unknown")
            written += 1
        evidence = Evidence(org_id=PUBLIC_ORG_ID, claim_id=claim.id, evidence_type="research_result", document_id=None,
                            locator={"url": fact.source_url}, snippet=fact.quote, source_authority=authority, origin=origin,
                            observed_as_of=now.date(),
                            span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none",
                                             "detail": f"web research {engine.RESEARCH_PROMPT_VERSION}"})
        session.add(evidence)
        session.flush()
        session.add(ClaimObservation(org_id=PUBLIC_ORG_ID, claim_id=claim.id, attribute_path=".", value=payload,
                                     evidence_id=evidence.id, source_authority=authority, origin=origin, observed_as_of=now.date()))
    _settle(session, company, outcome)
    session.flush()
    if written:
        _rematch_wishes(session, company.id)
    return {"identified": outcome.identified, "facts_written": written, "facts_seen": len(outcome.facts),
            "rejected": len(outcome.rejected), "usd": outcome.cost.get("usd", 0)}


def _settle(session: Session, company: Company, outcome: engine.ResearchOutcome) -> None:
    """Record where the company is based (the coverage gate's fallback) and whether it needs only light research."""
    for fact in outcome.facts:
        if fact.kind == "hq" and not company.hq_country:
            company.hq_country = _country(fact.value) or geo.country_in(fact.value)
        if fact.kind == "company_type" and fact.value in ("consultancy", "outsourcing"):
            size = next((f for f in outcome.facts if f.kind == "headcount"), None)
            lo = _team(size.value)[0] if size else None
            if lo is not None and lo >= LIGHT_HEADCOUNT:
                company.research_depth = "basic"
    if company.hq_country:
        from maindscout.api import coverage

        coverage.reevaluate_company(session, company.id)
    from maindscout.api import profiles

    profiles.queue_for_company(session, company.id)  # employer kind, stage, founding date feed the profiles


def run(session: Session, company_id: uuid.UUID, context: str, client: engine.SearchClient, force: bool = False,
        task_id: uuid.UUID | None = None) -> dict[str, Any]:
    company = canonical(session, session.get(Company, company_id))
    if company is None:
        raise LookupError(f"No company {company_id}")
    if not force and not due(company):
        return {"skipped": "fresh", "research_status": company.research_status}
    costs.ensure_budget(session, None)
    try:
        outcome = engine.research_company(company.name, context, client, basic=depth(company) == "basic")
    except Exception:
        company.research_status, company.researched_at = "failed", datetime.now(timezone.utc)
        session.flush()
        raise
    costs.record(session, None, "research_company", outcome.cost, subject_type="company", subject_id=company.id, task_id=task_id)
    return apply(session, company, outcome)


def facts(session: Session, company: Company) -> list[dict[str, Any]]:
    """The company's public facts with their sources, for the company page."""
    ids = [uuid.UUID(i) for i in _ids_for(session, company)]
    rows = list(session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id.in_(ids),
                                                    Claim.claim_type.in_(COMPANY_CLAIMS), Claim.status.in_(LIVE))
                                .order_by(Claim.claim_type, Claim.natural_key)))
    out = []
    for c in rows:
        ev = list(session.scalars(select(Evidence).where(Evidence.claim_id == c.id).order_by(Evidence.created_at.desc())))
        out.append({"id": str(c.id), "claim_type": c.claim_type, "status": c.status, "payload": c.approved_view or c.payload,
                    "flags": c.flags, "sources": [{"url": (e.locator or {}).get("url"), "quote": e.snippet,
                                                   "authority": e.source_authority, "seen": e.observed_as_of.isoformat() if e.observed_as_of else None}
                                                  for e in ev[:3]]})
    return out


def context_for_step(raw_name: str, location: str | None) -> str:
    """Company-only context from a career step: never the person's title or name."""
    return f"named '{raw_name}' on a CV" + (f"; location given: {location}" if location else "")


def _as_fact(claim: Claim) -> tuple[str, Any] | None:
    p = claim.payload
    return {"CompanyFoundedClaim": lambda: ("founded", p.get("founded")), "TeamSizeClaim": lambda: ("headcount", p.get("raw")),
            "CompanyStatusClaim": lambda: ("status", p.get("status")), "CompanyTypeClaim": lambda: ("company_type", p.get("type")),
            "FundingRoundClaim": lambda: ("funding_round", {"stage": p.get("stage"), "date": p.get("date"), "amount": p.get("amount_raw")}),
            }.get(claim.claim_type, lambda: None)()


def recheck(session: Session) -> list[dict[str, str]]:
    """Apply the current mechanical checks to stored public facts (free: no new research). A proposed fact whose
    every source now fails is rejected with the reason; approved facts are a person's call and are left alone."""
    from maindscout.api import review

    out = []
    for claim in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.status == "proposed",
                                                     Claim.claim_type.in_(COMPANY_CLAIMS))):
        made = _as_fact(claim)
        if made is None:
            continue
        kind, value = made
        problems = [engine.fact_problem(kind, value, e.snippet or "", (e.locator or {}).get("url") or "")
                    for e in session.scalars(select(Evidence).where(Evidence.claim_id == claim.id))]
        if problems and all(problems):
            review.reject_claim(session, PUBLIC_ORG_ID, claim.id, "system:recheck", "low_confidence", problems[0])
            out.append({"claim_id": str(claim.id), "claim_type": claim.claim_type, "reason": problems[0]})
    return out


def _rematch_wishes(session: Session, company_id) -> None:
    """New public facts about a hiring company can settle what people said they want (its size, what kind of
    employer it is): re-match its jobs that have such people on them, in the background."""
    from maindscout.api import tasks
    from maindscout.db.models import CandidateJob, Job

    wishes = select(Claim.subject_id).where(Claim.claim_type == "PreferenceClaim", Claim.status == "approved")
    jobs = session.execute(select(Job.id, Job.org_id).where(Job.hiring_company_id == company_id, Job.id.in_(
        select(CandidateJob.job_id).where(CandidateJob.candidate_id.in_(wishes))))).all()
    for job_id, org_id in jobs:
        tasks.enqueue(session, org_id, "rematch_job", {"job_id": str(job_id), "cause": {"act": "company_facts", "company_id": str(company_id)},
                                                       "actor": "system"}, dedupe_key=f"rematch:{job_id}", priority=40)
