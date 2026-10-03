"""Matching v2 rules on synthetic people and jobs (pure): verdicts per requirement, tier by visible rules."""

from datetime import date

from maindscout.domain import gaps, matching
from maindscout.domain.profile import CompanyFacts, Education, build
from tests.test_profile_rubric import AS_OF, d, stint

COARSE_OK = ("review_later", "no_distinctive_requirements")


def req(i, category, strength, text, **f):
    return {"id": str(i), "payload": {"text_raw": text, "category": category, "strength": strength, **f}}


def run(reqs, stints, edu=(), coarse=COARSE_OK, gap_rows=()):
    profile = build(list(stints), list(edu), AS_OF)
    return matching.match(reqs, list(gap_rows), profile, list(stints), coarse), profile


def verdict(m, rid):
    return next(v for v in m.rows if v.requirement_id == str(rid))


GIS = [stint(1, "EO Co", "Geospatial Data Scientist", "2015-09", "2023-06", family="gis_remote_sensing", level="mid",
             domains=["space / earth observation"]),
       stint(2, "Water", "Data Scientist", "2023-09", None, family="data_ml", level="mid", domains=["environment / water"])]


def test_todays_rule_still_decides_when_a_distinctive_must_has_no_evidence():
    m, _ = run([req(1, "role", "must", "InSAR specialist", role_family="gis_remote_sensing")], GIS,
               coarse=("do_not_submit", "no_support_for_must_have:insar"))
    assert (m.tier, m.band, m.reason) == ("unlikely", "do_not_submit", "no_support_for_must_have:insar")
    assert m.rules[0]["id"] == "distinctive_must_missing"


def test_one_level_below_is_possible_unless_a_strong_industry_match_outweighs_it():
    role = req(1, "role", "must", "Senior InSAR specialist", role_family="gis_remote_sensing", level="senior")
    m, _ = run([role], GIS)
    assert m.tier == "possible" and verdict(m, 1).verdict == "partial" and m.rules[-1]["id"] == "partial_must"
    m, _ = run([role, req(2, "domain", "must", "Earth observation", domains=["space / earth observation"])], GIS)
    assert m.tier == "strong" and "domain_over_seniority" in [r["id"] for r in m.rules]
    assert "outweighed by Earth observation" in verdict(m, 1).detail


def test_a_not_wanted_background_makes_it_unlikely():
    consult = CompanyFacts(kind="consultancy")
    people = [stint(1, "BigCo", "Senior Consultant Developer", "2017-01", None, level="senior", facts=consult)]
    m, _ = run([req(1, "employer", "anti", "No big consultancies", employer_kinds=["consultancy"])], people)
    assert m.tier == "unlikely" and verdict(m, 1).verdict == "against" and m.rules[0]["id"] == "not_wanted"


def test_a_substitution_from_the_intake_counts_the_other_requirement_as_met():
    corp = CompanyFacts(kind="product", team_min=5000)
    people = [stint(1, "Coupa", "Senior Software Engineer", "2018-01", None, level="senior", facts=corp, domains=["procurement"])]
    reqs = [req(1, "employer", "strong_plus", "Early-stage start-up experience", employer_kinds=["startup"]),
            req(2, "domain", "strong_plus", "Procurement domain experience", domains=["procurement"],
                note="can substitute for start-up experience")]
    m, _ = run(reqs, people)
    assert verdict(m, 1).verdict == "strong" and "can substitute" in verdict(m, 1).detail
    assert m.tier == "strong" and "substitution" in [r["id"] for r in m.rules]


def test_a_contract_job_lights_up_a_contractor_with_long_engagements():
    people = [stint(i, f"Client{i}", "Senior Developer", s, e, employment="contract", level="senior")
              for i, (s, e) in enumerate([("2017-01", "2019-01"), ("2019-02", "2021-06"), ("2021-07", None)])]
    m, _ = run([req(1, "employment", "must", "Contract", employment="contract")], people)
    assert verdict(m, 1).verdict == "strong" and "contractor_fit" in [r["id"] for r in m.rules]


def test_where_someone_lives_is_never_a_reason_for_unlikely():
    row = gaps.Row("9", "Live in DE or GB", "mobility", "must", "question", "lives in Lisbon; ask")
    m, _ = run([req(1, "role", "must", "Data scientist", role_family="data_ml")], GIS,
               gap_rows=[row])
    assert verdict(m, 9).verdict == "ask" and m.tier == "strong"


def test_without_a_profile_the_coarse_band_stands():
    m = matching.match([req(1, "role", "must", "Engineer", role_family="software_engineering")], [], None, [],
                       ("priority", "supported:insar"))
    assert (m.tier, m.band) == ("unclear", None) and m.rules[0]["id"] == "too_little_known"


def test_two_must_gaps_are_unlikely_and_one_is_possible():
    reqs = [req(1, "role", "must", "Sales lead", role_family="sales"),
            req(2, "domain", "must", "Banking", domains=["banking"])]
    m, _ = run(reqs, GIS)
    assert m.tier == "unlikely" and m.rules[-1]["id"] == "must_gaps"
    m, _ = run(reqs[:1], GIS)
    assert m.tier == "possible"


def test_a_broad_skill_not_on_the_cv_is_a_question_not_a_gap():
    row = gaps.Row("7", "Project management skills", "skill", "must", "missing", "no evidence in skills or titles", False)
    m, _ = run([req(1, "role", "must", "Data scientist", role_family="data_ml")], GIS, gap_rows=[row])
    assert verdict(m, 7).verdict == "ask" and m.tier == "strong"


def test_target_companies_and_never_a_number():
    people = [stint(1, "Acme", "Engineer", "2019-01", None, level="mid")]
    people[0].company_key = "c-1"
    m, _ = run([req(1, "target_company", "strong_plus", "People from Acme", companies=[{"name": "Acme", "company_id": "c-1"}])], people)
    assert verdict(m, 1).verdict == "strong"
    assert "%" not in repr(m.as_dict()) and "score" not in repr(m.as_dict())
