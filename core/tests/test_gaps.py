from datetime import date

from maindscout.domain.gaps import Fact, counts, gap_table, years_of_experience

TODAY = date(2026, 10, 2)


def career(i, company, start, end=None, kind="full_time", title="Engineer", status="proposed"):
    return Fact(f"c{i}", "CareerStepClaim", {"company": {"raw_name": company}, "title_raw": title, "employment_type": kind},
                status, date.fromisoformat(start), date.fromisoformat(end) if end else None)


def skill(i, token, status="proposed"):
    return Fact(f"s{i}", "SkillClaim", {"raw_label": token.title(), "normalized_skill": token}, status)


def place(code, name, kind="current"):
    return Fact(f"l{code}", "LocationClaim", {"place_raw": name, "country_code": code, "kind": kind, "basis": "stated"}, "proposed")


def req(i, category, text, strength="must", **extra):
    return {"id": f"r{i}", "payload": {"text_raw": text, "category": category, "strength": strength, **extra}}


def row(rows, rid):
    return next(r for r in rows if r.requirement_id == rid)


def test_overlapping_jobs_are_not_counted_twice_and_internships_are_left_out():
    facts = [career(1, "A", "2020-01-01", "2022-01-01"), career(2, "B", "2021-01-01", "2023-01-01"),
             career(3, "C", "2015-01-01", "2016-01-01", kind="internship")]
    years, jobs, undated = years_of_experience(facts, TODAY)
    assert years == 3.0 and jobs == 2 and not undated


def test_a_current_job_counts_up_to_today():
    years, _, _ = years_of_experience([career(1, "A", "2024-10-02")], TODAY)
    assert years == 2.0


def test_skill_found_in_skills_or_titles_is_evidence_else_missing():
    facts = [skill(1, "react"), career(1, "A", "2020-01-01", title="Senior Node.js Developer")]
    rows = gap_table([req(1, "skill", "React", normalized_token="react", distinctive=True),
                      req(2, "skill", "Node", normalized_token="node"),
                      req(3, "skill", "InSAR", normalized_token="insar")], facts, TODAY)
    assert row(rows, "r1").status == "evidence" and row(rows, "r1").distinctive
    assert row(rows, "r2").status == "evidence" and "job title" in row(rows, "r2").detail
    assert row(rows, "r3").status == "missing"


def test_fewer_years_than_asked_is_a_conflict_with_the_numbers_shown():
    rows = gap_table([req(1, "seniority", "5+ years", min_years=5)], [career(1, "A", "2023-10-02")], TODAY)
    assert row(rows, "r1").status == "conflict"
    assert "about 3 years" in row(rows, "r1").detail and "5+ asked" in row(rows, "r1").detail


def test_enough_years_is_evidence_and_no_dates_is_missing():
    assert gap_table([req(1, "seniority", "2+", min_years=2)], [career(1, "A", "2020-01-01")], TODAY)[0].status == "evidence"
    assert gap_table([req(1, "seniority", "2+", min_years=2)], [], TODAY)[0].status == "missing"


def test_education_level_is_compared():
    master = Fact("e1", "EducationClaim", {"institution_raw": "U", "level": "master"}, "proposed")
    bachelor = Fact("e2", "EducationClaim", {"institution_raw": "U", "level": "bachelor"}, "proposed")
    assert gap_table([req(1, "education", "BSc", education_level="bachelor")], [master], TODAY)[0].status == "evidence"
    assert gap_table([req(1, "education", "MSc", education_level="master")], [bachelor], TODAY)[0].status == "conflict"
    assert gap_table([req(1, "education", "MSc", education_level="master")], [], TODAY)[0].status == "missing"


def test_living_elsewhere_is_a_question_never_a_conflict():
    reqs = [req(1, "location", "Live in DE or GB", mobility={"facet": "residence", "countries": ["DE", "GB"]}),
            req(2, "authorization", "No visa", strength="unknown", mobility={"facet": "visa_sponsorship", "offered": False}),
            req(3, "other", "No relocation", strength="unknown", mobility={"facet": "relocation_assistance", "offered": False})]
    elsewhere = gap_table(reqs, [place("RO", "Bucharest, Romania")], TODAY)
    assert [r.status for r in elsewhere] == ["question", "question", "question"]
    assert "Bucharest" in row(elsewhere, "r1").detail and "Germany or United Kingdom" in row(elsewhere, "r1").detail
    there = gap_table(reqs, [place("GB", "Bristol, UK")], TODAY)
    assert row(there, "r1").status == "evidence"
    assert row(there, "r2").status == "question", "living there does not prove the right to work"
    assert row(there, "r3").status == "evidence" and "no move needed" in row(there, "r3").detail
    assert all(r.status != "conflict" for r in elsewhere + there)


def test_process_dates_and_plain_work_locations_are_not_rows():
    rows = gap_table([req(1, "process", "Closes", strength="unknown", normalized_token="2026-08-27"),
                      req(2, "location", "Markham", strength="unknown")], [], TODAY)
    assert rows == []


def test_official_only_when_every_fact_is_approved():
    rows = gap_table([req(1, "skill", "React", normalized_token="react")], [skill(1, "react", status="approved")], TODAY)
    assert rows[0].official
    rows = gap_table([req(1, "skill", "React", normalized_token="react")], [skill(1, "react")], TODAY)
    assert not rows[0].official


def test_counts_are_per_status_and_never_combined():
    rows = gap_table([req(1, "skill", "React", normalized_token="react"), req(2, "skill", "Go", normalized_token="go")],
                     [skill(1, "react")], TODAY)
    c = counts(rows)
    assert c == {"evidence": 1, "missing": 1, "conflict": 0, "question": 0}
    assert not any(k in c for k in ("score", "total", "fit"))
