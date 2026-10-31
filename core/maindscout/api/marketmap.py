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
TIERS = ("named", "known", "peer", "adjacent", "release", "manual", "feeder", "feeder_one", "feeder_large", "snowball")
TIER_LABEL = {"named": "named by the hiring manager", "known": "our people worked there", "peer": "peer company",
              "adjacent": "adjacent industry", "release": "releasing talent", "manual": "added by you",
              "feeder": "their people came from here", "feeder_one": "one of their people came from here",
              "feeder_large": "large feeder", "snowball": "strong candidates worked here"}

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
    "marketing": ["marketing manager", "brand manager", "senior marketing manager"],
    "sales": ["account executive", "sales manager", "business development manager"],
    "customer_success": ["customer success manager", "account manager"],
    "design": ["product designer", "UX designer"],
    "finance": ["finance manager", "financial controller"],
    "hr_recruiting": ["HR manager", "talent acquisition partner"],
    "operations": ["operations manager"],
}
# The ad's places and regions after a title ("Marketing Manager Italy and Europe", "Sales Lead - DACH") are not
# part of the title: a search with them finds titles, not people (seen on a real role, 2026-10-13).
_REGIONS = r"europe|emea|dach|nordics?|benelux|apac|americas|latam|global|international|worldwide|remote|hybrid"

_GENDER_TAG = re.compile(r"\s*[\(\[](?:m|w|f|d|x|all genders?|gn)(?:\s*/\s*(?:m|w|f|d|x|div))*[\)\]]\s*", re.I)


def role_titles(session: Session, job: Job) -> list[str]:
    """The titles a person confirmed for this role (read from its own material with its work lines, 2026-10-30), in
    place of the family table above: none until then."""
    from maindscout.api import work_lines

    return work_lines.titles(session, job.id, "title")


def clean_title(title: str) -> str:
    """'Senior Flight Software Engineer (m/w/d)' -> 'Senior Flight Software Engineer';
    'Marketing Manager Italy and Europe' -> 'Marketing Manager'; 'Sales Lead - DACH' -> 'Sales Lead'."""
    from maindscout.domain.geo import NAMES

    text = " ".join(_GENDER_TAG.sub(" ", title or "").split())
    text = re.split(r"\s+[-–|]\s+|,\s*|\s+\(", text)[0].strip() or text
    places = "|".join(sorted({re.escape(n) for names in NAMES.values() for n in names} | {_REGIONS}, key=len, reverse=True))
    tail = re.compile(rf"(?:\s+(?:in|for|and|&|/)?\s*(?:{places}))+\s*$", re.I)
    short = tail.sub("", text).strip()
    return short or text


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
        from maindscout.api.process import client_context
        from maindscout.api.strategy import much_bigger

        client_staff = client_context(session, job)["staff"]
        scored = []
        for company_id, shared in rows:
            company = companies.canonical(session, session.get(Company, company_id))
            if company is None or str(company.id) in seen or much_bigger(company, client_staff):
                continue  # 20x the client's size is no peer (step C)
            seen.add(str(company.id))
            n = len(companies.people_at(session, org_id, company.id))
            scored.append((n, len(shared), company, shared))
        # The most shared industry first; how many of our people worked there only breaks a tie. Ranking by our own
        # people first made a new role's list the last role's (the luxury pool for Ferrari's CRM role, 2026-10-22).
        scored.sort(key=lambda r: (-r[1], -r[0], r[2].name.lower()))
        for n, _, company, shared in scored[:20]:
            why = [f"same industry: {', '.join(shared[:3])}"] + ([f"{n} of our people worked there"] if n else [])
            targets.append(_target(company, "known" if n else "peer", why, "desk_research", n))

    from maindscout.api.process import client_context
    from maindscout.domain import specialism

    title = clean_title(job.title)
    own = role_titles(session, job)
    if own:  # the role's own titles, confirmed by a person, the most common first; the ad's own title after them
        variants = own + [t for t in [title] if t.lower() not in {o.lower() for o in own}]
    else:
        # A specialist role searches its specialism's titles, not its broad family's ("CRM specialist", not "account
        # manager" for a CRM role read as customer success; owner, 2026-10-22).
        spec = client_context(session, job)["specialism"]
        usual = specialism.titles(spec) or FAMILY_TITLES.get(filters.family or "", [])
        variants = [title] + [t for t in usual if t.lower() != title.lower()]
    countries = list(job.open_countries or []) or ([hiring_company.hq_country] if hiring_company and hiring_company.hq_country else [])
    return {"targets": targets, "role_variants": variants[:6 if own else 4], "countries": countries[:5],
            "hiring": {"company": summary.get("name"), "stage": summary.get("stage"), "domains": summary.get("domains") or [],
                       "kind": summary.get("kind")}}
