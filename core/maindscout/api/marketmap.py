"""A role's market map (docs/next/PLAN.md S1): the companies to search, each with why; the titles that mean the same
work; the countries. The first version comes from what the desk already knows, for free: target companies the hiring
manager named, and companies in the hiring company's industries (first those our people worked at). A web search for
more peer companies is one click and costs about a cent.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import companies, hiring, search
from maindscout.db.models import PUBLIC_ORG_ID, Claim, Company, Job
from maindscout.domain import geo

LIVE = ("proposed", "approved")
TIERS = ("named", "known", "peer", "adjacent", "release", "manual", "feeder", "feeder_large", "snowball")
TIER_LABEL = {"named": "named by the hiring manager", "known": "our people worked there", "peer": "peer company",
              "adjacent": "adjacent industry", "release": "releasing talent", "manual": "added by you",
              "feeder": "their people came from here", "feeder_large": "large feeder", "snowball": "strong candidates worked here"}

# Titles that mean the same work, per role family (the shared families of career profiles). The job's own title
# comes first; these widen the search. Editable on the plan.
FAMILY_TITLES: dict[str, list[str]] = {
    "embedded_hardware": ["embedded software engineer", "firmware engineer", "embedded systems engineer"],
    "software_engineering": ["software engineer", "C++ software engineer", "backend engineer"],
    "data_ml": ["machine learning engineer", "perception engineer", "computer vision engineer"],
    "research_science": ["research engineer", "research scientist"],
    "devops_infrastructure": ["DevOps engineer", "site reliability engineer", "platform engineer"],
    "qa_testing": ["test engineer", "verification and validation engineer"],
    "security": ["security engineer", "product security engineer"],
    "engineering_management": ["engineering manager", "head of engineering"],
    "gis_remote_sensing": ["remote sensing engineer", "SAR engineer", "GIS engineer"],
    "product_management": ["technical product manager", "product manager"],
}

_GENDER_TAG = re.compile(r"\s*[\(\[](?:m|w|f|d|x|all genders?|gn)(?:\s*/\s*(?:m|w|f|d|x|div))*[\)\]]\s*", re.I)


def clean_title(title: str) -> str:
    """'Senior Flight Software Engineer (m/w/d)' -> 'Senior Flight Software Engineer'."""
    return " ".join(_GENDER_TAG.sub(" ", title or "").split())


def _words(values: list[str]) -> set[str]:
    # Words too broad to say two companies share a market ("software" pairs a procurement start-up with a bank's IT
    # supplier): only the specific words count (seen on a real role, 2026-10-13).
    stop = {"and", "the", "of", "for", "services", "solutions", "industry", "other", "software", "enterprise", "technology",
            "technologies", "tech", "platform", "platforms", "saas", "digital", "internet", "information", "data", "systems",
            "business", "b2b", "b2c", "consulting", "development", "products", "applications", "cloud", "online"}
    return {w for v in values for w in re.findall(r"[a-z]{3,}", v.lower()) if w not in stop}


def _target(company: Company, tier: str, why: list[str], source: str, people: int = 0, pinned: bool = False) -> dict[str, Any]:
    return {"name": company.name, "company_id": str(company.id), "tier": tier, "why": why, "source": source,
            "people_on_desk": people, "pinned": pinned, "removed": False, "country": company.hq_country}


def initial(session: Session, job: Job) -> dict[str, Any]:
    """The first market map: named targets, then companies in the hiring company's industries (desk knowledge only)."""
    org_id = job.org_id
    filters, named = search.job_filters(session, job)
    hiring_company = companies.canonical(session, session.get(Company, job.hiring_company_id)) if job.hiring_company_id else None
    summary = hiring.company_summary(session, hiring_company) or {}
    targets: list[dict[str, Any]] = []
    seen: set[str] = {str(hiring_company.id)} if hiring_company else set()

    for cid in named:
        company = companies.canonical(session, session.get(Company, uuid.UUID(cid)))
        if company is None or str(company.id) in seen:
            continue
        seen.add(str(company.id))
        n = len(companies.people_at(session, org_id, company.id))
        targets.append(_target(company, "named", ["named in the hiring profile"] + ([f"{n} of our people worked there"] if n else []),
                               "hiring_profile", n, pinned=True))

    wanted = _words(list(summary.get("domains") or []) + list(filters.domains))
    if wanted:
        rows = []
        for claim in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.claim_type == "CompanyDomainClaim",
                                                         Claim.status.in_(LIVE))):
            shared = wanted & _words((claim.approved_view or claim.payload).get("domains") or [])
            if shared and str(claim.subject_id) not in seen:
                rows.append((claim.subject_id, sorted(shared)))
        scored = []
        for company_id, shared in rows:
            company = companies.canonical(session, session.get(Company, company_id))
            if company is None or str(company.id) in seen:
                continue
            seen.add(str(company.id))
            n = len(companies.people_at(session, org_id, company.id))
            scored.append((n, len(shared), company, shared))
        scored.sort(key=lambda r: (-r[0], -r[1], r[2].name.lower()))
        for n, _, company, shared in scored[:20]:
            why = [f"same industry: {', '.join(shared[:3])}"] + ([f"{n} of our people worked there"] if n else [])
            targets.append(_target(company, "known" if n else "peer", why, "desk_research", n))

    title = clean_title(job.title)
    variants = [title] + [t for t in FAMILY_TITLES.get(filters.family or "", []) if t.lower() != title.lower()]
    countries = list(job.open_countries or []) or ([hiring_company.hq_country] if hiring_company and hiring_company.hq_country else [])
    return {"targets": targets, "role_variants": variants[:4], "countries": countries[:5],
            "hiring": {"company": summary.get("name"), "stage": summary.get("stage"), "domains": summary.get("domains") or [],
                       "kind": summary.get("kind")}}


def peer_query(hiring_summary: dict[str, Any], countries: list[str], role: str) -> str | None:
    """The words of a company search for peers: stage, industries, country. None when there is nothing to go on."""
    domains = [d for d in hiring_summary.get("domains") or [] if d][:2]
    if not domains:
        return None
    stage = (hiring_summary.get("stage") or "").split("(")[0].strip()
    stage = stage.title() if stage and not stage.lower().startswith(("other", "debt", "grant")) else ""
    where = f" in {geo.name_of(countries[0])}" if countries else ""
    kind = "startups" if stage.lower().startswith(("seed", "pre", "series a", "series b")) else "companies"
    return " ".join(f"{stage} {' and '.join(domains)} {kind}{where} hiring {role}".split())


def web_peers(session: Session, job: Job, plan_targets: list[dict[str, Any]], countries: list[str], role: str,
              caller, hiring_summary: dict[str, Any]) -> tuple[list[dict[str, Any]], float, str | None]:
    """Peer companies from a web company search (paid, about $0.007). Returns (new targets, cost, the query)."""
    from maindscout.intelligence import exa

    query = peer_query(hiring_summary, countries, role)
    if not query:
        return [], 0.0, None
    results = exa.search(caller, query, "company", num_results=10, country=countries[0] if countries else None, text_chars=8000)
    have = {t.get("company_id") for t in plan_targets} | {(t.get("name") or "").lower() for t in plan_targets}
    out = []
    for found in results.found:
        name = re.split(r"\s+[|–—-]\s+", found.title)[0].strip()
        if not name or name.lower() in have:
            continue
        from maindscout.api import company_profiles
        from maindscout.intelligence import company_profile

        profile = company_profile.read(found.text)
        company, _ = companies.resolve(session, profile.name or name, "web",
                                       keys={"exa_id": found.entity_id, "domain": profile.homepage or found.url})
        if company is None:
            continue
        company = companies.canonical(session, company)
        if str(company.id) in have or company.id == job.hiring_company_id:
            continue
        have |= {str(company.id), name.lower()}
        if not company.website:
            company.website = found.url
        if found.entity_id and profile.name:
            company_profiles.apply(session, company, found)  # the result is its profile page: kept, no second call
        target = _target(company, "peer", [f'found by a company search: "{query}"'], "exa_company")
        target["group"] = "B"
        target["website"] = found.url
        out.append(target)
    return out, results.usd, query
