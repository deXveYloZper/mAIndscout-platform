"""Slice 1 step 1: richer requirements. Mobility is always three facts; every value is in its quote."""

from sqlalchemy import select

from maindscout.db.models import Claim
from maindscout.intelligence import extract
from tests.test_process import CV_LINES, blobs, cv_json, run  # noqa: F401 (blobs is a fixture)

LINES = [
    "AI Product Engineer",
    "This role is based in Germany or the UK.",
    "Unfortunately, this role does not offer visa support or relocation assistance.",
    "5+ years of production experience with TypeScript.",
    "Fluent German is a plus.",
    "A degree in Computer Science or a related field.",
]


def jd(**over):
    data = {
        "title": {"value": "AI Product Engineer", "quote": "AI Product Engineer"},
        "hiring_company": None,
        "requirements": [
            {"text": "5+ years of production experience", "category": "seniority", "strength": "must", "token": None,
             "distinctive": False, "min_years": 5, "education_level": None, "language": None,
             "quote": "5+ years of production experience with TypeScript."},
            {"text": "Fluent German", "category": "language", "strength": "nice", "token": None, "distinctive": False,
             "min_years": None, "education_level": None, "language": "German", "quote": "Fluent German is a plus."},
            {"text": "Degree in Computer Science", "category": "education", "strength": "must", "token": None,
             "distinctive": False, "min_years": None, "education_level": "bachelor", "language": None,
             "quote": "A degree in Computer Science or a related field."},
        ],
        "mobility": {
            "residence": {"countries": [{"name": "Germany", "code": "DE"}, {"name": "UK", "code": "GB"}],
                          "quote": "This role is based in Germany or the UK."},
            "visa_sponsorship": {"offered": False, "quote": "Unfortunately, this role does not offer visa support or relocation assistance."},
            "relocation_assistance": {"offered": False, "quote": "Unfortunately, this role does not offer visa support or relocation assistance."},
        },
        "work_locations": [],
        "process_dates": [],
    }
    data.update(over)
    return data


def reqs(session, job_id):
    return list(session.scalars(select(Claim).where(Claim.subject_id == job_id, Claim.claim_type == "JobRequirementClaim")))


def by_facet(claims):
    return {c.payload["mobility"]["facet"]: c for c in claims if c.payload.get("mobility")}


def test_mobility_is_three_separate_facts(session, blobs, org):
    result, _ = run(session, blobs, org, LINES, jd(), doc_type="jd")
    facets = by_facet(reqs(session, result.job_id))
    assert set(facets) == {"residence", "visa_sponsorship", "relocation_assistance"}
    assert facets["residence"].payload["mobility"]["countries"] == ["DE", "GB"]
    assert facets["visa_sponsorship"].payload["mobility"]["offered"] is False
    assert facets["relocation_assistance"].payload["mobility"]["offered"] is False
    assert len({c.natural_key for c in facets.values()}) == 3


def test_seniority_years_language_and_education_are_kept(session, blobs, org):
    result, _ = run(session, blobs, org, LINES, jd(), doc_type="jd")
    claims = {c.payload["category"]: c for c in reqs(session, result.job_id) if not c.payload.get("mobility")}
    assert claims["seniority"].payload["min_years"] == 5
    assert claims["language"].payload["language"] == "German"
    assert claims["education"].payload["education_level"] == "bachelor"


def test_a_country_not_written_in_the_quote_blocks_residence(session, blobs, org):
    data = jd()
    data["mobility"]["residence"]["countries"].append({"name": "France", "code": "FR"})
    result, _ = run(session, blobs, org, LINES, data, doc_type="jd")
    assert "residence" not in by_facet(reqs(session, result.job_id))
    assert any("country is not written" in f["detail"] for f in result.span_failures)


def test_years_not_written_are_blocked(session, blobs, org):
    data = jd()
    data["requirements"][0]["min_years"] = 7
    result, _ = run(session, blobs, org, LINES, data, doc_type="jd")
    assert not [c for c in reqs(session, result.job_id) if c.payload["category"] == "seniority"]
    assert any("7 years" in f["detail"] for f in result.span_failures)


def test_mobility_never_decides_a_band(session, blobs, org):
    data = jd()
    data["requirements"].append({"text": "React", "category": "skill", "strength": "must", "token": "react",
                                 "distinctive": True, "min_years": None, "education_level": None, "language": None,
                                 "quote": "5+ years of production experience with TypeScript."})
    job, _ = run(session, blobs, org, LINES, data, doc_type="jd")
    person = cv_json(locations=[{"place": "Bucharest, Romania", "country_code": "RO", "kind": "current", "quote": "Based in Bristol, UK"}])
    result, _ = run(session, blobs, org, CV_LINES, person, job_id=job.job_id)
    assert result.band == "priority" and "location" not in result.reason


def test_country_matching_understands_common_names():
    assert extract._country_in_quote("UK", "GB", "based in Germany or the UK.")
    assert extract._country_in_quote("United Kingdom", "GB", "Remote: Germany | United Kingdom")
    assert extract._country_in_quote("U.K.", "GB", "Must live in the U.K.")
    assert not extract._country_in_quote("France", "FR", "based in Germany or the UK.")
    assert not extract._country_in_quote("US", "US", "focus on business results")  # 'us' inside a word does not count
