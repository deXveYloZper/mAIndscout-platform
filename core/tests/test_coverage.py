"""The coverage gate: people living or working outside the countries the desk and their jobs accept are archived,
and no further paid intelligence is spent on them. Never nationality, only where someone lives and works now."""

import uuid

import pytest
from sqlalchemy import select

from maindscout.api import coverage, research
from maindscout.db.models import Candidate, Company, Job, Task
from maindscout.domain import geo
from maindscout.intelligence import research as engine
from tests.test_api import client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import JD_JSON, JD_LINES, cv_json

PUNE_LINES = [
    "ARJUN EXAMPLE",
    "arjun.example@example.com",
    "Senior Engineer, Infosys, Jan 2021 - Present",
    "Engineer, Wipro, Jan 2018 - Dec 2020",
    "Skills: Rust, Python",
    "Based in Pune, India",
]


def pune_cv(location="Pune, India", code="IN", job_location=None, job_code=None):
    return cv_json(
        full_name={"value": "Arjun Example", "quote": "ARJUN EXAMPLE"},
        contacts=[{"kind": "email", "value": "arjun.example@example.com", "quote": "arjun.example@example.com"}],
        career_steps=[
            {"company": "Infosys", "title": "Senior Engineer", "employment_type": "full_time", "location": job_location,
             "country_code": job_code, "start": "2021-01", "end": "present", "quote": "Senior Engineer, Infosys, Jan 2021 - Present"},
            {"company": "Wipro", "title": "Engineer", "employment_type": "full_time", "location": None, "country_code": None,
             "start": "2018-01", "end": "2020-12", "quote": "Engineer, Wipro, Jan 2018 - Dec 2020"},
        ],
        skills=[{"label": "Rust", "normalized": "rust", "quote": "Skills: Rust, Python"}],
        locations=[{"place": location, "country_code": code, "kind": "current", "quote": f"Based in {location}"}] if location else [],
    )


def research_tasks(session):
    return list(session.scalars(select(Task).where(Task.kind == "research_company")))


def person(session, cid) -> Candidate:
    return session.get(Candidate, uuid.UUID(cid))


# --- the rule itself (pure) -------------------------------------------------------------------------


def test_country_lookup_reads_countries_never_guesses_cities():
    assert geo.country_in("Pune, India") == "IN" and geo.country_in("London, UK") == "GB"
    assert geo.country_in("Austin, TX") == "US" and geo.country_in("Toronto, ON") == "CA"
    assert geo.country_in("London") is None and geo.country_in("Remote") is None


def test_default_coverage_is_eea_uk_switzerland_us_canada_not_mexico():
    cover = geo.DEFAULT_COVERAGE
    assert {"DE", "FR", "NO", "IS", "LI", "GB", "CH", "US", "CA"} <= cover
    assert not {"MX", "IN", "BR", "AE"} & cover


def test_where_someone_lives_and_works_decides_never_where_they_are_from():
    cover = geo.DEFAULT_COVERAGE
    assert geo.decide(["IN"], [], cover).outside  # lives in India
    assert not geo.decide(["DE"], [("DE", "role")], cover).outside  # an Indian national living and working in Berlin
    assert geo.decide(["GB"], [("IN", "role")], cover).outside  # lives in the UK, current job is in India
    assert not geo.decide(["GB"], [("GB", "role")], cover).outside  # TCS consultant in London: the job is in London
    assert geo.decide([], [("IN", "employer")], cover).basis == "employer"  # job place unknown: the employer's base
    assert not geo.decide([], [], cover).outside  # unknown is never outside


# --- the gate in the flow ---------------------------------------------------------------------------


def test_a_cv_from_outside_coverage_is_archived_and_costs_nothing_more(client, fake, session):
    job = make_job(client)
    fake.cv = pune_cv()
    cid = drop_cv(client, job, PUNE_LINES, "pune.pdf")["subject_id"]
    p = person(session, cid)
    assert p.archived_at is not None and "India" in p.archived_reason["text"]
    hiring = str(session.get(Job, uuid.UUID(job)).hiring_company_id)
    assert [t.payload["company_id"] for t in research_tasks(session)] == [hiring], \
        "only the hiring company is researched: nothing for an archived person's employers"
    page = client.get(f"/v1/jobs/{job}").json()
    assert [a["candidate_id"] for a in page["archived"]] == [cid]
    assert cid not in [x["candidate_id"] for band in page["people"].values() for x in band]
    assert all(i["subject"]["id"] != cid for i in client.get("/v1/inbox", params={"band": "all"}).json())
    assert client.get(f"/v1/candidates/{cid}").json()["archived"]["reason"].startswith("lives in India")


def test_a_cv_in_coverage_is_not_archived_and_its_companies_are_researched(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]  # Jane, Bristol UK
    assert person(session, cid).archived_at is None
    names = {session.get(Company, uuid.UUID(t.payload["company_id"])).name for t in research_tasks(session)}
    assert "Acme Space" in names


def test_opening_a_job_to_a_country_brings_its_people_back(client, fake, session):
    job = make_job(client)
    fake.cv = pune_cv()
    cid = drop_cv(client, job, PUNE_LINES, "pune.pdf")["subject_id"]
    assert person(session, cid).archived_at is not None
    page = client.put(f"/v1/jobs/{job}/countries", json={"countries": ["India"]}).json()
    assert page["coverage"]["opened"] == ["IN"] and page["archived"] == []
    assert person(session, cid).archived_at is None
    assert {session.get(Company, uuid.UUID(t.payload["company_id"])).name for t in research_tasks(session)} >= {"Infosys"}
    assert client.put(f"/v1/jobs/{job}/countries", json={"countries": ["Atlantis"]}).status_code == 422


def test_a_job_ad_that_names_a_country_accepts_people_living_there(client, fake, session):
    fake.jd = {**JD_JSON, "mobility": {"residence": {"stated": True, "countries": [{"name": "Brazil", "code": "BR"}],
                                                     "quote": "Catalyst Geo builds satellite analytics."}}}
    # The quote must name the country: use an ad line that does.
    lines = JD_LINES + ["Remote from Brazil is welcome."]
    fake.jd["mobility"]["residence"]["quote"] = "Remote from Brazil is welcome."
    r = client.post("/v1/jobs", files=pdf_file(lines, "jd-br.pdf"))
    job = r.json()["job_id"]
    assert client.get(f"/v1/jobs/{job}").json()["coverage"]["from_ad"] == ["BR"]
    fake.cv = pune_cv("São Paulo, Brazil", "BR")
    lines_cv = PUNE_LINES[:-1] + ["Based in São Paulo, Brazil"]
    cid = drop_cv(client, job, lines_cv, "sp.pdf")["subject_id"]
    assert person(session, cid).archived_at is None


def test_the_place_of_the_job_decides_and_the_employer_base_is_only_a_fallback(client, fake, session):
    job = make_job(client)
    # Lives in London, works for Infosys in London: in coverage although Infosys is based in India.
    fake.cv = pune_cv("London, UK", "GB", job_location="London", job_code="GB")
    lines = PUNE_LINES[:-1] + ["Based in London, UK"]
    cid = drop_cv(client, job, lines, "ldn.pdf")["subject_id"]
    infosys = session.scalar(select(Company).where(Company.normalized == "infosys"))
    infosys.hq_country = "IN"
    coverage.evaluate(session, uuid.UUID(client.headers["X-Org-Id"]), uuid.UUID(cid), {"act": "test"})
    assert person(session, cid).archived_at is None


def test_an_unknown_job_place_falls_back_to_the_employer_base_once_research_finds_it(client, fake, session):
    job = make_job(client)
    fake.cv = pune_cv(None, None)  # no home stated, no job place stated
    cid = drop_cv(client, job, PUNE_LINES[:-1], "nowhere.pdf")["subject_id"]
    assert person(session, cid).archived_at is None, "unknown is never outside"
    infosys = session.scalar(select(Company).where(Company.normalized == "infosys"))

    class Search:
        model = "fake"

        def search_json(self, system, user, schema, name):
            assert "funding_rounds" not in schema["properties"], "Infosys gets light research only"
            url = "https://www.infosys.com/about.html"
            return ({"identified": True, "website": "https://www.infosys.com",
                     "company_type": {"value": "consultancy", "source_url": url, "quote": "Infosys is a global leader in consulting", "as_of": None},
                     "hq": {"value": "Bengaluru, India", "source_url": url, "quote": "Headquartered in Bengaluru, India", "as_of": None}},
                    [url], {"usd": 0.03})

    research.run(session, infosys.id, "", Search())
    assert infosys.hq_country == "IN"
    p = person(session, cid)
    assert p.archived_at is not None and p.archived_reason["basis"] == "employer"


def test_bring_back_sticks(client, fake, session):
    job = make_job(client)
    fake.cv = pune_cv()
    cid = drop_cv(client, job, PUNE_LINES, "pune.pdf")["subject_id"]
    page = client.post(f"/v1/candidates/{cid}/bring-back").json()
    assert page["archived"] is None and page["coverage_override"] is True
    client.post(f"/v1/jobs/{job}/people/{cid}")  # any later re-check leaves them be
    assert person(session, cid).archived_at is None


def test_sourcing_skips_archived_people_unless_the_job_accepts_their_country(client, fake, session):
    fake.cv = pune_cv()
    r = client.post("/v1/candidates", files=pdf_file(PUNE_LINES, "pool.pdf"))
    cid = r.json()["subject_id"]
    assert person(session, cid).archived_at is not None
    fake.jd = {**JD_JSON, "requirements": [{"text": "Rust", "category": "skill", "strength": "must", "token": "rust",
                                            "distinctive": True, "quote": "You must have InSAR processing experience."}]}
    job = client.post("/v1/jobs", files=pdf_file(JD_LINES, "rust.pdf")).json()["job_id"]
    found = client.post(f"/v1/jobs/{job}/campaigns", json={}).json()
    assert found["added"] == 0
    client.put(f"/v1/jobs/{job}/countries", json={"countries": ["IN"]})
    found = client.post(f"/v1/jobs/{job}/campaigns", json={}).json()
    assert found["added"] == 1 and person(session, cid).archived_at is None


# --- light research for large consultancies ---------------------------------------------------------


def test_big_consultancies_get_light_research_refreshed_yearly(session):
    epam = Company(name="EPAM Systems", normalized="epam systems")
    other = Company(name="Small Product Co", normalized=f"small product {uuid.uuid4().hex[:5]}")
    session.add_all([epam, other])
    session.flush()
    assert research.depth(epam) == "basic" and research.depth(other) == "full"


def test_a_large_consultancy_found_by_research_switches_to_light_research(session):
    c = Company(name="Mega Consulting", normalized=f"mega consulting {uuid.uuid4().hex[:5]}")
    session.add(c)
    session.flush()
    url = "https://mega.example/about"
    outcome = engine.ResearchOutcome(True, url, [
        engine.Fact("company_type", "consultancy", url, "a global consulting firm"),
        engine.Fact("headcount", "10,001+ employees", url, "Company size 10,001+ employees"),
        engine.Fact("hq", "Paris, France", url, "Headquarters Paris, France")], [], [url], {"usd": 0})
    research.apply(session, c, outcome)
    assert c.research_depth == "basic" and c.hq_country == "FR"


def test_cv_reading_keeps_the_country_of_each_job_place(client, fake, session):
    job = make_job(client)
    fake.cv = pune_cv(job_location="Bangalore", job_code="IN")
    cid = drop_cv(client, job, PUNE_LINES, "blr.pdf")["subject_id"]
    steps = client.get(f"/v1/candidates/{cid}").json()["claims"]["CareerStepClaim"]
    assert any(s["payload"].get("location_country") == "IN" for s in steps)
