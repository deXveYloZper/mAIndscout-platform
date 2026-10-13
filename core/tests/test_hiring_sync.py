"""The hiring profile and sourcing in step (owner, 2026-10-13, on an anonymised ad): the intake notes name the hiring
company and where the person must be; a role without a confirmed company still gets a strategy, from its hiring
profile; a search title never carries the ad's places; a strategy that could not run says why."""

import uuid

from sqlalchemy import select

from maindscout.api import autosource, strategy
from maindscout.api.marketmap import clean_title
from maindscout.db.models import Claim, Job, Task
from maindscout.intelligence.llm import LLMResult
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import FakeExa
from tests.test_hiring import item
from tests.test_phase1b import page as company_page

NOTES = "Buona Testventura is the Hiring company, this person must be in Milan or willing to move to Milan."


class Reader:
    model = "fake-hiring"

    def complete_json(self, system, user, schema, name):
        assert "hiring_company" in system and "location" in system
        return LLMResult({"items": [
            item("hiring_company", "must", "Buona Testventura", "Buona Testventura is the Hiring company"),  # the name as text only
            item("location", "must", "Milan, or willing to move there", "must be in Milan or willing to move to Milan",
                 countries=["it"], cities=["Milan"], relocation=True),
        ]}, self.model, 500, 100, 0.002)


def requirements(session, job_id):
    return [c.approved_view or c.payload for c in session.scalars(select(Claim).where(
        Claim.subject_id == job_id, Claim.claim_type == "JobRequirementClaim", Claim.status.in_(("proposed", "approved"))))]


def test_intake_notes_name_the_hiring_company_and_where_the_person_must_be(client, fake, session):
    job_id = make_job(client)
    client.post(f"/v1/jobs/{job_id}/requirements", json={"category": "location", "strength": "must", "text_raw": "Live in Italy",
                                                         "mobility": {"facet": "residence", "countries": ["IT"]},
                                                         "normalized_token": "residence"})
    ad = next(c for c in session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(job_id), Claim.status == "approved"))
              if (c.payload or {}).get("category") == "location")
    ad.status, ad.payload, ad.approved_view = "proposed", {**ad.payload, "source": "ad"}, None  # as the ad reader leaves it
    ad.natural_key = f"{job_id}|location|residence"
    session.flush()
    from maindscout.api import app as api

    api.app.dependency_overrides[api.get_llm] = lambda: Reader()
    r = client.post(f"/v1/jobs/{job_id}/intake", json={"text": NOTES})
    assert r.status_code == 200, r.text
    assert r.json()["hiring_company"] == "Buona Testventura"
    job = session.get(Job, uuid.UUID(job_id))
    session.refresh(job)
    assert job.hiring_company == "Buona Testventura" and job.hiring_company_id is not None
    places = [p for p in requirements(session, job.id) if p.get("category") == "location"]
    assert len(places) == 1, "the hiring manager's place replaces the one already there, with its city and relocation"
    place = places[0]
    assert place["mobility"] == {"facet": "residence", "countries": ["IT"]} and place["cities"] == ["Milan"] and place["relocation"] is True
    assert strategy.role_countries(session, job) == {"IT"}, "the role's countries follow the hiring manager's word"
    assert "hiring_company" not in {p["category"] for p in requirements(session, job.id)}, "who is hiring is not a requirement"


def test_the_hiring_company_can_be_typed_and_a_vague_background_is_refused(client, session):
    job_id = make_job(client)
    r = client.put(f"/v1/jobs/{job_id}/hiring-company", json={"name": "Buona Testventura"})
    assert r.status_code == 200 and session.get(Job, uuid.UUID(job_id)).hiring_company == "Buona Testventura"
    bad = client.post(f"/v1/jobs/{job_id}/requirements", json={"category": "employer", "strength": "strong_plus", "text_raw": "luxury"})
    assert bad.status_code == 422 and "Industry" in bad.json()["detail"], "an industry is not a kind of employer"
    ok = client.post(f"/v1/jobs/{job_id}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "luxury",
                                                               "domains": ["luxury / fashion / beauty"]})
    assert ok.status_code in (200, 201), ok.text


def test_a_search_title_never_carries_the_ads_places():
    assert clean_title("Marketing Manager Italy and Europe") == "Marketing Manager"
    assert clean_title("Sales Lead - DACH") == "Sales Lead"
    assert clean_title("Head of Marketing, EMEA") == "Head of Marketing"
    assert clean_title("AI Product Engineer (m/f/d) - full stack; all levels") == "AI Product Engineer"
    assert clean_title("Remote Sensing Engineer") == "Remote Sensing Engineer", "a title's own words stay"


def test_without_a_confirmed_company_the_strategy_is_built_from_the_hiring_profile(client, session):
    job_id = make_job(client)
    job = session.get(Job, uuid.UUID(job_id))
    job.hiring_company_id, job.hiring_company = None, None
    session.flush()
    p = autosource.plan(session, job.org_id, job.id, "owner@desk.test")
    with_nothing = FakeExa()
    try:
        strategy.build(session, job.org_id, job.id, with_nothing, "owner@desk.test")
        raise AssertionError("no company and no industry: nothing to build from")
    except autosource.SourcingEngineError as error:
        assert "industry or background" in str(error)
    client.post(f"/v1/jobs/{job_id}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "luxury",
                                                         "domains": ["luxury / fashion / beauty"]})
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", countries=["IT"])
    assert strategy.profile_queries(session, job, ["IT"]) == ["luxury, fashion and beauty companies in Italy"]
    brands = FakeExa(companies=[company_page("lux1", "Maison Testoro", "testoro.example", industry="Luxury Goods", hq="Milan, Italy",
                                             countries="Italy: 300 (80%)", employees=400)])
    out = strategy.build(session, job.org_id, job.id, brands, "owner@desk.test")
    assert out["note"].startswith("No talent DNA: The role has no hiring company")
    assert [c["query"] for c in brands.calls] == ["luxury, fashion and beauty companies in Italy"]
    plan = autosource.current_plan(session, job.id)
    assert [t["name"] for t in plan.targets] == ["Maison Testoro"] and plan.version > p.version


def test_a_strategy_that_could_not_run_says_why_on_the_page(client, session):
    job_id = make_job(client)
    job = session.get(Job, uuid.UUID(job_id))
    session.add(Task(org_id=job.org_id, kind="sourcing_strategy", payload={"job_id": job_id}, status="done",
                     dedupe_key=f"strategy:{job_id}", result={"status": "skipped", "reason": "The role has no hiring company"}))
    session.flush()
    note = autosource.page(session, job.org_id, job.id)["strategy_note"]
    assert note["level"] == "error" and "no hiring company" in note["text"]
