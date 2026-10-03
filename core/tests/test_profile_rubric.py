"""The career profile rubric on synthetic careers (plan section 4.3): pure code, no database, no model."""

from datetime import date

from maindscout.domain.profile import CompanyFacts, Education, Stint, build, stint_category

AS_OF = date(2026, 10, 1)


def d(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def stint(i, company, title, start, end=None, family="software_engineering", level=None, employment="full_time", **kw):
    return Stint(str(i), company, title, d(start), d(end) if end else None, employment, company_key=company,
                 family=family, level=level, **kw)


def test_restaurant_then_software_counts_only_the_software_years():
    p = build([
        stint(1, "Bistro", "Waiter", "2010-01", "2014-01", family="hospitality", level="junior"),
        stint(2, "Acme", "Software Engineer", "2014-02", "2018-01", level="mid"),
        stint(3, "Beta", "Senior Software Engineer", "2018-02", None, level="senior"),
    ], [], AS_OF)
    ry = p["dimensions"]["relevant_years"]
    assert ry["main"] == "software_engineering" and 12.0 <= ry["main_years"] <= 12.8
    assert ry["years"]["hospitality"] == 4.0
    assert "also 4 years in hospitality" in ry["reason"]


def _three(company_kind=None, moves=False, promoted=True):
    facts = CompanyFacts(kind=company_kind or "product", rounds=[("series_b", d("2015-01"))])
    if moves:
        spans = [("2016-10", "2018-01"), ("2018-02", "2019-01"), ("2019-02", "2020-03"), ("2020-04", "2021-02"),
                 ("2021-03", "2022-06"), ("2022-07", "2023-09"), ("2023-10", None)]
        return [stint(i, f"Co{i}", "Software Engineer", s, e, level="senior" if i > 3 else "mid", facts=facts)
                for i, (s, e) in enumerate(spans)]
    return [
        stint(1, "Alpha", "Software Engineer", "2016-09", "2019-12", level="mid", facts=facts),
        stint(2, "Beta", "Software Engineer", "2020-01", "2022-06", level="mid", facts=facts),
        stint(3, "Beta", "Senior Software Engineer" if promoted else "Software Engineer", "2022-07", None,
              level="senior" if promoted else "mid", facts=facts),
    ]


def test_the_three_engineers_read_as_the_plan_says():
    first = build(_three(), [], AS_OF)
    assert first["reading"]["label"] == "strong"
    assert first["dimensions"]["progression"]["label"] == "rising" and "Promoted at Beta" in first["dimensions"]["progression"]["reason"]
    assert first["dimensions"]["employer_mix"]["label"] == "scaleup"

    second = build(_three(moves=True), [], AS_OF)
    assert second["dimensions"]["stability"]["label"] == "frequent_moves"
    assert second["reading"]["label"] == "solid"
    assert any(q.startswith("What led to the short stays") for q in second["questions"])

    third = build(_three(company_kind="consultancy", promoted=False), [], AS_OF)
    assert third["dimensions"]["employer_mix"]["label"] == "consultancy"
    assert third["reading"]["label"] == "solid"
    assert any("which products did they own" in q for q in third["questions"])


def test_contractors_are_read_against_contractor_norms_never_as_unstable():
    long = [stint(i, f"Client{i}", "Contract Developer", s, e, employment="contract", level="senior")
            for i, (s, e) in enumerate([("2016-01", "2017-06"), ("2017-07", "2019-01"), ("2019-02", "2021-01"), ("2021-02", None)])]
    p = build(long, [], AS_OF)
    assert p["dimensions"]["stability"]["label"] == "long_engagements"
    assert p["dimensions"]["contractor"]["label"] == "current"
    assert not any("short stays" in q for q in p["questions"])

    short = [stint(i, f"Client{i}", "Contract Developer", s, e, employment="contract", level="senior")
             for i, (s, e) in enumerate([("2023-01", "2023-03"), ("2023-04", "2023-07"), ("2023-08", "2023-11"), ("2024-01", "2024-03")])]
    p = build(short, [], AS_OF)
    assert p["dimensions"]["stability"]["label"] == "short_engagements"
    assert any("contracts were mostly short" in q for q in p["questions"])


def test_an_early_joiner_is_noticed():
    facts = CompanyFacts(kind="product", founded=d("2019-01"), rounds=[("seed", d("2019-06"))])
    p = build([stint(1, "Rocket", "Founding Engineer", "2019-04", None, level="senior", facts=facts, signals=["first_hire"])], [], AS_OF)
    assert p["dimensions"]["early_joiner"]["label"] == "yes"
    assert "3 months after it was founded" in p["dimensions"]["early_joiner"]["reason"]
    kinds = {n["kind"] for n in p["notable"]}
    assert {"early_joiner", "first_hire"} <= kinds


def test_a_short_stay_at_a_company_that_shut_down_is_not_counted_against_them():
    dead = CompanyFacts(kind="product", status="shut_down")
    p = build([
        stint(1, "A", "Engineer", "2016-01", "2019-01", level="mid"),
        stint(2, "Gone", "Engineer", "2019-02", "2019-08", level="mid", facts=dead),
        stint(3, "C", "Engineer", "2019-09", "2023-01", level="senior"),
        stint(4, "D", "Engineer", "2023-02", None, level="senior"),
    ], [], AS_OF)
    emp = p["dimensions"]["stability"]["parts"]["employed"]
    assert emp["short"] == [] and emp["softened"] == ["2"]
    assert any("Gone shut down or was sold" in q for q in p["questions"])


def test_too_little_is_unclear_and_there_is_never_a_number():
    p = build([stint(1, "X", "Engineer", "2025-01", None, family=None)], [], AS_OF)
    assert p["reading"]["label"] == "unclear"
    flat = repr(p)
    assert "score" not in flat and "%" not in flat


def test_education_shows_the_rank_band_as_merit_evidence():
    p = build([], [Education("e1", "Example University", "master", "Computer Science", d("2015-06"), 42, "top_50", "QS World University Rankings 2026"),
                   Education("e2", "Another College", "bachelor", "Physics", d("2013-06"))], AS_OF)
    edu = p["dimensions"]["education"]
    assert edu["label"] == "master" and edu["rank_band"] == "top_50" and "QS" in edu["reason"]


def test_employer_kind_comes_from_the_stage_when_they_joined():
    facts = CompanyFacts(kind="product", rounds=[("seed", d("2018-01")), ("series_c", d("2022-01"))])
    assert stint_category(stint(1, "S", "E", "2019-01", facts=facts)) == "startup"
    assert stint_category(stint(2, "S", "E", "2023-01", facts=facts)) == "scaleup"
    assert stint_category(stint(3, "Big", "E", "2023-01", facts=CompanyFacts(kind="product", team_min=5001))) == "large"
    assert stint_category(stint(4, "Unknown", "E", "2023-01")) == "unknown"


def test_a_gap_of_more_than_six_months_becomes_a_question_not_a_verdict():
    p = build([stint(1, "A", "Engineer", "2018-01", "2020-01", level="mid"),
               stint(2, "B", "Engineer", "2021-03", None, level="senior")], [], AS_OF)
    assert any(q.startswith("What were they doing between Jan 2020 and Mar 2021") for q in p["questions"])


def test_related_kinds_of_work_count_together():
    """A GIS data scientist for 8 years who is now a data scientist is not a beginner."""
    p = build([stint(1, "EO Co", "Geospatial Data Scientist", "2015-09", "2023-06", family="gis_remote_sensing", level="senior"),
               stint(2, "Water", "Data Scientist", "2023-09", None, family="data_ml", level="mid")], [], AS_OF)
    ry = p["dimensions"]["relevant_years"]
    assert ry["main"] == "data_ml" and ry["family_years"] < 4 and ry["main_years"] > 10
    assert "of technical work in all" in ry["reason"]
    assert p["reading"]["label"] != "developing"


def test_a_promotion_is_not_a_move_and_a_students_shop_job_does_not_count():
    p = build([stint(1, "Shop", "Sales Associate", "2012-07", "2013-07", family="retail"),
               stint(2, "Conquest", "Support Analyst", "2014-01", "2015-06", level="mid"),
               stint(3, "Conquest", "Product Specialist", "2015-07", "2017-03", level="mid"),
               stint(4, "Conquest", "Product Owner", "2017-04", "2019-04", level="senior"),
               stint(5, "Next", "Consultant", "2019-05", None, level="senior")], [], AS_OF)
    emp = p["dimensions"]["stability"]["parts"]["employed"]
    assert emp["label"] == "long_tenures" and emp["short"] == []
    assert "2 employers" in emp["reason"]


def test_year_only_dates_never_make_a_stay_short():
    p = build([stint(1, "A", "Engineer", "2016-01", "2017-01", level="mid", precise=False),
               stint(2, "B", "Engineer", "2017-01", "2018-01", level="mid", precise=False),
               stint(3, "C", "Engineer", "2018-01", "2022-01", level="senior"),
               stint(4, "D", "Engineer", "2022-02", None, level="senior")], [], AS_OF)
    assert p["dimensions"]["stability"]["parts"]["employed"]["short"] == []


def test_an_old_funding_round_does_not_make_a_big_company_a_scale_up():
    sky = CompanyFacts(kind="product", rounds=[("series_b", d("2005-01"))], team_min=10001)
    assert stint_category(stint(1, "Sky", "Engineer", "2023-05", facts=sky)) == "large"


def test_an_undated_job_asks_for_its_dates_instead_of_inventing_a_gap():
    p = build([stint(1, "A", "Analyst", "2013-03", "2017-10", level="senior"),
               Stint("2", "Clevest", "Consultant", None, None, "full_time", family="software_engineering", level="senior"),
               stint(3, "Vena", "Consultant", "2020-01", None, level="senior")], [], AS_OF)
    assert any("no dates for Consultant at Clevest" in q for q in p["questions"])
    assert not any(q.startswith("What were they doing between") for q in p["questions"])


def test_levels_come_from_title_words_by_code():
    from maindscout.intelligence.classify import title_level

    assert title_level("Junior Software Engineer", []) == "junior"
    assert title_level("Software Engineer", []) == "mid"
    assert title_level("Senior Full Stack Developer", []) == "senior"
    assert title_level("Engineering Team Leader", []) == "lead"
    assert title_level("Head of Data & Analytics", []) == "head"
    assert title_level("VP Data (Contract)", []) == "director"
    assert title_level("Co-Founder & Head of Business Development", []) == "founder"
    assert title_level("Technical industrial placement", []) == "intern"
    assert title_level("Flight Software Engineer", ["team_lead"]) == "mid"  # leading shows as a signal, not a level


def test_progression_ends_at_the_highest_role_held_today():
    p = build([stint(1, "Shop", "Junior Developer", "2016-01", "2019-01", level="junior"),
               stint(2, "Big", "Senior Developer", "2019-02", None, level="senior"),
               stint(3, "Self", "Consultant", "2024-01", None, level="mid", employment="consulting")], [], AS_OF)
    assert "to senior" in p["dimensions"]["progression"]["reason"] and p["dimensions"]["progression"]["label"] == "rising"
