"""A synthetic demo desk for testing search, sourcing and matching at a realistic size (I6).

Clearly fake people: every name starts with "Demo · " and every email ends in @example.invalid (a reserved domain
that can never belong to anyone). Careers are generated from a fixed seed at companies already on the desk, with
facts written straight to the desk's claims (no model calls, no cost). `clear` erases them through the ordinary
erasure path. Never use this on a production desk.
"""

from __future__ import annotations

import random
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import writer
from maindscout.db.models import Candidate, Claim, ClaimObservation, Company, Evidence, Institution

MARK = "Demo · "
EMAIL_DOMAIN = "example.invalid"

FIRST = ["Alex", "Sam", "Jordan", "Robin", "Maria", "Luca", "Anna", "Tomas", "Sofia", "Elif", "Noah", "Mia", "Jonas",
         "Lea", "Kai", "Nina", "Ivan", "Zoe", "Omar", "Clara", "Felix", "Ines", "Mateo", "Hannah", "Arjun", "Leila"]
LAST = ["Novak", "Schmidt", "Rossi", "Kowalski", "Garcia", "Dubois", "Jensen", "Horvat", "Silva", "Meyer", "Popescu",
        "Nowak", "Costa", "Weber", "Moreau", "Larsen", "Fischer", "Varga", "Lindqvist", "Brennan", "Okafor", "Petrov"]
PLACES = [("London, UK", "GB"), ("Berlin, Germany", "DE"), ("Munich, Germany", "DE"), ("Amsterdam, Netherlands", "NL"),
          ("Manchester, UK", "GB"), ("Toronto, Canada", "CA"), ("Lisbon, Portugal", "PT"), ("Warsaw, Poland", "PL"),
          ("Dublin, Ireland", "IE"), ("Zurich, Switzerland", "CH"), ("Austin, TX", "US"), ("Vienna, Austria", "AT")]
OUTSIDE = [("Pune, India", "IN"), ("São Paulo, Brazil", "BR"), ("Dubai, UAE", "AE")]

# Archetype: (family, titles by level, domains, employment, typical stint months)
ARCHETYPES = [
    ("software_engineering", ["Junior Software Engineer", "Software Engineer", "Senior Software Engineer", "Lead Engineer"],
     ["fintech", "e-commerce", "enterprise software", "procurement"], "full_time", (20, 48)),
    ("software_engineering", ["Junior Frontend Developer", "Frontend Developer", "Senior Frontend Developer", "Staff Engineer"],
     ["media / entertainment", "e-commerce", "payments"], "full_time", (14, 36)),
    ("software_engineering", ["Developer", "Contract Developer", "Senior Contract Developer", "Principal Contractor"],
     ["banking", "insurance", "public sector"], "contract", (6, 24)),
    ("data_ml", ["Junior Data Analyst", "Data Scientist", "Senior Data Scientist", "Head of Data"],
     ["fintech", "healthcare", "ai / data", "marketing / advertising"], "full_time", (18, 40)),
    ("gis_remote_sensing", ["GIS Analyst", "Remote Sensing Scientist", "Senior InSAR Specialist", "Lead Geospatial Engineer"],
     ["space / earth observation", "environment / water", "energy / utilities"], "full_time", (24, 60)),
    ("devops_infrastructure", ["Junior DevOps Engineer", "DevOps Engineer", "Senior Platform Engineer", "Lead SRE"],
     ["cybersecurity", "telecommunications", "enterprise software"], "full_time", (18, 42)),
    ("product_management", ["Associate Product Manager", "Product Manager", "Senior Product Manager", "Head of Product"],
     ["procurement", "fintech", "e-commerce"], "full_time", (16, 36)),
    ("business_consulting", ["Junior Consultant", "Consultant", "Senior Consultant", "Principal Consultant"],
     ["it services / consulting", "energy / utilities", "banking"], "full_time", (20, 48)),
]
SKILLS = {"software_engineering": ["typescript", "react", "node", "python", "java", "aws"],
          "data_ml": ["python", "sql", "pytorch", "spark"], "gis_remote_sensing": ["insar", "python", "gdal", "qgis"],
          "devops_infrastructure": ["kubernetes", "terraform", "aws", "linux"], "product_management": ["jira", "sql", "figma"],
          "business_consulting": ["excel", "sql", "power bi"]}


def _ev(session: Session, org_id, claim: Claim) -> None:
    ev = Evidence(org_id=org_id, claim_id=claim.id, evidence_type="human_assertion", source_authority="human_assertion",
                  origin="human", snippet="Demo data (synthetic)", observed_as_of=date.today(),
                  span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none", "detail": "synthetic demo data"})
    session.add(ev)
    session.flush()
    session.add(ClaimObservation(org_id=org_id, claim_id=claim.id, attribute_path=".", value=claim.payload, evidence_id=ev.id,
                                 source_authority="human_assertion", origin="human", observed_as_of=date.today()))


def _claim(session: Session, org_id, cid, claim_type: str, payload: dict[str, Any], key: str, **fields) -> Claim:
    c = writer.add_claim(session, org_id=org_id, subject_type="candidate", subject_id=cid, claim_type=claim_type,
                         payload=payload, natural_key=key, status="proposed", observed_as_of=date.today(), **fields)
    _ev(session, org_id, c)
    return c


def _months_back(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    return date(y, m + 1, 1)


def seed(session: Session, org_id: uuid.UUID, count: int = 60, seed_value: int = 42, number_from: int = 0) -> dict[str, int]:
    """`number_from` numbers the people (and their emails) after an earlier batch."""
    from maindscout.api import coverage, profiles

    rnd = random.Random(seed_value)
    companies = list(session.scalars(select(Company).where(Company.merged_into_id.is_(None), Company.research_status == "identified")))
    institutions = list(session.scalars(select(Institution).where(Institution.rank_band.is_not(None))))
    today = date.today().replace(day=1)
    made = 0
    for n in range(count):
        family, titles, domains, employment, (lo, hi) = rnd.choice(ARCHETYPES)
        name = f"{MARK}{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        person = Candidate(org_id=org_id, name_variants=[name])
        session.add(person)
        session.flush()
        cid = person.id
        _claim(session, org_id, cid, "IdentityClaim", {"full_name": name, "name_variants": []}, f"{cid}|name")
        email = f"demo{number_from + n + 1}@{EMAIL_DOMAIN}"
        _claim(session, org_id, cid, "ContactClaim", {"kind": "email", "value": email, "normalized": email,
                                                     "attributable": True, "attribution": "subject"}, f"{cid}|email|{email}")
        place, code = rnd.choice(OUTSIDE) if rnd.random() < 0.08 else rnd.choice(PLACES)
        _claim(session, org_id, cid, "LocationClaim", {"place_raw": place, "country_code": code, "basis": "stated", "kind": "current"},
               f"{cid}|{place.lower()}|stated")
        # Career: newest job first, going back in time; level rises with each move or promotion.
        stints = rnd.randint(2, 5)
        end: date | None = None
        level = min(len(titles) - 1, stints - 1 + rnd.choice([-1, 0, 0, 1]))
        cursor = today
        for k in range(stints):
            months = rnd.randint(lo, hi)
            start = _months_back(cursor, months)
            company = rnd.choice(companies) if companies else None
            raw = company.name if company else f"Example Co {rnd.randint(1, 40)}"
            title = titles[max(0, level)]
            emp = employment if not (employment == "contract" and level == 0) else "full_time"
            payload = {"company": {"raw_name": raw, "company_id": str(company.id) if company else None, "provisional": False},
                       "title_raw": title, "employment_type": emp, "location_raw": place, "location_country": code}
            career = _claim(session, org_id, cid, "CareerStepClaim", payload, f"{cid}|{raw.lower()}|{start}|{end or 'open'}",
                            valid_from=start, valid_to=end, temporal_precision="month")
            _claim(session, org_id, cid, "StepClassificationClaim",
                   {"career_claim_id": str(career.id), "role_family": family, "level": None,
                    "domains": [rnd.choice(domains)], "signals": ["team_lead"] if "Lead" in title else []},
                   f"{career.id}|class", claim_class="inferred", valid_from=start, valid_to=end, temporal_precision="month")
            end = _months_back(start, rnd.randint(0, 2))
            cursor = end
            level = max(0, level - rnd.choice([0, 1, 1]))
        for skill in rnd.sample(SKILLS[family], k=min(3, len(SKILLS[family]))):
            _claim(session, org_id, cid, "SkillClaim", {"raw_label": skill, "normalized_skill": skill}, f"{cid}|{skill}")
        inst = rnd.choice(institutions).name if institutions and rnd.random() < 0.8 else "Example Technical University"
        _claim(session, org_id, cid, "EducationClaim", {"institution_raw": inst, "level": rnd.choice(["bachelor", "master", "master"]),
                                                        "field": "Computer Science"}, f"{cid}|edu|{inst.lower()}",
               valid_from=_months_back(cursor, 48), valid_to=_months_back(cursor, 1), temporal_precision="year_only")
        session.flush()
        coverage.evaluate(session, org_id, cid, {"act": "demo_seed"})
        profiles.build(session, org_id, cid)
        made += 1
    session.flush()
    return {"people": made, "companies_used": len(companies)}


def demo_people(session: Session, org_id: uuid.UUID) -> list[uuid.UUID]:
    return list(session.scalars(select(Claim.subject_id).where(
        Claim.org_id == org_id, Claim.claim_type == "ContactClaim",
        Claim.payload["normalized"].astext.like(f"%@{EMAIL_DOMAIN}")).distinct()))


def clear(session: Session, blobs, org_id: uuid.UUID) -> int:
    """Erase every demo person through the ordinary erasure path."""
    from maindscout.api import erasure

    ids = demo_people(session, org_id)
    for cid in ids:
        erasure.erase_candidate(session, blobs, org_id, cid, "system:demo-clear", "synthetic demo data")
    return len(ids)
