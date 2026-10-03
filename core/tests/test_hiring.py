"""I4: hiring profiles from the ad and from intake notes; recruiter edits; the hiring company and target companies."""

import uuid

from sqlalchemy import select

from maindscout.api import hiring, research
from maindscout.db.models import Claim, Company, CostEntry, Evidence, Task
from maindscout.intelligence import hiring as engine
from maindscout.intelligence import research as research_engine
from maindscout.intelligence.llm import LLMResult
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)


def item(kind, strength, text, quote, **f):
    base = {"kind": kind, "strength": strength, "text": text, "quote": quote, "role_family": None, "level": None,
            "min_years": None, "employer_kinds": [], "domains": [], "companies": [], "employment": None,
            "skill_token": None, "note": None}
    base.update(f)
    return base


AD_ITEMS = [
    item("role", "must", "Radar interferometry specialist", "Radar Interferometry Specialist", role_family="gis_remote_sensing",
         level="senior", min_years=5),  # no number written: min_years is dropped
    item("employment", "must", "Permanent", "Applications close", employment="permanent"),
    item("employer", "nice", "A good culture fit", "Catalyst Geo builds satellite analytics.", employer_kinds=["startup"]),
    item("skill", "must", "InSAR", "You must have InSAR processing experience.", skill_token="insar"),
    item("domain", "nice", "Space", "a quote that is not in the ad", domains=["space / earth observation"]),
]

NOTES = ("Call with Anna (hiring manager), 3 Oct. She really wants early-stage start-up experience: that is a strong plus. "
         "Procurement domain experience is a strong plus and can substitute for the start-up experience. "
         "InSAR is only nice to have now, they will train. People from Acme Space would be ideal. "
         "No candidates from big consultancies. Must be a culture fit with the team. Permanent role.")

INTAKE_ITEMS = [
    item("employer", "strong_plus", "Early-stage start-up experience", "early-stage start-up experience", employer_kinds=["startup"]),
    item("domain", "strong_plus", "Procurement domain experience", "Procurement domain experience is a strong plus",
         domains=["procurement"], note="can substitute for the start-up experience"),
    item("skill", "nice", "InSAR", "InSAR is only nice to have now", skill_token="insar"),
    item("target_company", "strong_plus", "People from Acme Space", "People from Acme Space would be ideal", companies=["Acme Space"]),
    item("employer", "anti", "Not from big consultancies", "No candidates from big consultancies", employer_kinds=["consultancy"]),
    item("other", "must", "Culture fit", "Must be a culture fit with the team"),
    item("employment", "must", "Permanent", "Permanent role.", employment="permanent"),
]


class Reader:
    model = "fake-hiring"

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, schema, name):
        assert name == "hiring_profile"
        self.calls.append(system)
        items = INTAKE_ITEMS if "hiring manager" in system else AD_ITEMS
        return LLMResult({"items": items}, self.model, 800, 200, 0.003)


def reqs(session, job_id, source=None):
    rows = session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(job_id), Claim.claim_type == "JobRequirementClaim",
                                               Claim.status.in_(("proposed", "approved"))))
    return [r for r in rows if source is None or r.payload.get("source") == source]


def test_reading_the_ad_adds_the_role_and_employment_and_checks_every_item(client, fake, session):
    job = make_job(client)
    reader = Reader()
    result = hiring.from_ad(session, uuid.UUID(job), reader)
    from_ad = {r.payload["category"]: r for r in reqs(session, job, "ad")}
    assert set(from_ad) == {"role"}, "culture fit, a skill from the ad, an unquoted item and an unsupported employment are dropped"
    role = from_ad["role"].payload
    assert role["role_family"] == "gis_remote_sensing" and role["level"] == "senior" and "min_years" not in role
    assert from_ad["role"].status == "proposed" and result["rejected"] == 4
    ev = session.scalars(select(Evidence).where(Evidence.claim_id == from_ad["role"].id)).one()
    assert ev.origin == "employer" and ev.snippet == "Radar Interferometry Specialist"
    assert session.scalar(select(CostEntry).where(CostEntry.purpose == "hiring_profile")) is not None
    assert hiring.from_ad(session, uuid.UUID(job), reader)["skipped"] == "already read" and len(reader.calls) == 1


def test_intake_notes_become_requirements_with_quotes_and_the_hiring_manager_beats_the_ad(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]  # Jane: worked at Acme Space; InSAR missing -> do not submit
    assert client.get(f"/v1/jobs/{job}").json()["people"]["do_not_submit"][0]["candidate_id"] == cid
    from maindscout.api import app as api

    api.app.dependency_overrides[api.get_llm] = lambda: Reader()
    r = client.post(f"/v1/jobs/{job}/intake", json={"text": NOTES})
    assert r.status_code == 200, r.text
    body = r.json()
    assert any("culture" in x["reason"] for x in body["rejected"])
    rows = {(x.payload["category"], x.payload["strength"]): x for x in reqs(session, job, "intake")}
    assert rows[("domain", "strong_plus")].payload["note"] == "can substitute for the start-up experience"
    assert rows[("employer", "anti")].payload["employer_kinds"] == ["consultancy"]
    insar = rows[("skill", "nice")]
    assert [x for x in reqs(session, job) if x.payload.get("normalized_token") == "insar"] == [insar], "the ad's must is replaced"
    ev = session.scalars(select(Evidence).where(Evidence.claim_id == insar.id)).one()
    assert ev.origin == "relayed" and ev.locator["intake_id"] == body["intake_id"] and NOTES[ev.locator["char_start"]:ev.locator["char_end"]] == ev.snippet
    page = body["job"]
    assert cid not in [p["candidate_id"] for p in page["people"]["do_not_submit"]], "InSAR no longer decides: re-banded"
    target = rows[("target_company", "strong_plus")].payload["companies"][0]
    assert target["name"] == "Acme Space" and page["hiring"]["targets"][target["company_id"]] == 1, "we know Jane there"
    assert page["hiring"]["intakes"][0]["text"] == NOTES


def test_a_recruiter_adds_and_reweighs_requirements(client, fake, session):
    job = make_job(client)
    r = client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus",
                                                          "text_raw": "Fintech experience", "domains": ["fintech"]})
    assert r.status_code == 201, r.text
    added = session.get(Claim, uuid.UUID(r.json()["id"]))
    assert added.status == "approved" and added.payload["source"] == "recruiter"
    r = client.post(f"/v1/requirements/{added.id}/strength", json={"strength": "must"})
    assert r.status_code == 200 and r.json()["strength"] == "must"
    session.refresh(added)
    assert added.status == "superseded"
    assert client.post(f"/v1/requirements/{added.id}/strength", json={"strength": "mandatory"}).status_code == 422


def test_the_job_page_shows_the_hiring_company_from_research(client, fake, session):
    job = make_job(client)
    company = session.scalar(select(Company).where(Company.normalized == "catalyst geo"))
    url = "https://catalyst.example/"
    research.apply(session, company, research_engine.ResearchOutcome(True, url, [
        research_engine.Fact("company_type", "product", url, "our platform"),
        research_engine.Fact("founded", "1982", url, "Founded 1982"),
        research_engine.Fact("headcount", "51-200 employees", url, "Company size 51-200 employees")], [], [url], {"usd": 0}))
    page = client.get(f"/v1/jobs/{job}").json()
    assert page["hiring"]["company"]["kind"] == "product" and page["hiring"]["company"]["founded"] == "1982"
    assert page["hiring"]["company"]["team"] == "51-200 employees"


def test_reading_an_ad_queues_its_hiring_profile(client, fake, session):
    job = make_job(client)
    tasks = session.scalars(select(Task).where(Task.kind == "profile_job")).all()
    assert [t.payload["job_id"] for t in tasks] == [job]


def test_short_notes_are_refused(client):
    job = make_job(client)
    assert client.post(f"/v1/jobs/{job}/intake", json={"text": "call went ok"}).status_code == 422


def test_personality_is_never_a_criterion():
    assert engine.NOT_CRITERIA.search("Must be a culture fit") and engine.NOT_CRITERIA.search("great attitude")
    assert not engine.NOT_CRITERIA.search("0-to-1 product delivery")


def test_employment_needs_a_quote_about_employment_and_the_intake_corrects_its_value(client, fake, session):
    out = engine.read("Radar Interferometry Specialist. Applications close soon.", Reader(), "ad")
    assert not [i for i in out.items if i.kind == "employment"], "'Applications close' says nothing about employment"
    job = make_job(client)
    jid = uuid.UUID(job)
    from maindscout.db.models import Job

    j = session.get(Job, jid)
    either = engine.Item("employment", "must", "Permanent or contract", "an employment agreement or a contract", 0, 10, {"employment": "either"})
    perm = engine.Item("employment", "must", "Permanent", "Permanent role", 0, 10, {"employment": "permanent"})
    ev = {"type": "intake_note", "locator": {}, "authority": "human_assertion", "origin": "relayed"}
    hiring._write(session, j, [either], "ad", {**ev, "type": "document_span", "authority": "employer_authored", "origin": "employer"})
    assert hiring._write(session, j, [perm], "intake", ev)["replaced"] == 1
    live = [r for r in reqs(session, job) if r.payload["category"] == "employment"]
    assert [r.payload["employment"] for r in live] == ["permanent"]


def test_employment_words_are_recognised():
    assert engine.EMPLOYMENT_WORDS.search("Permanent role, not contract.")
    assert engine.EMPLOYMENT_WORDS.search("full-time employment")
    assert not engine.EMPLOYMENT_WORDS.search("Applications close soon")


class OneItem:
    model = "fake"

    def __init__(self, it):
        self.it = it

    def complete_json(self, system, user, schema, name):
        return LLMResult({"items": [self.it]}, self.model, 1, 1, 0.0)


def test_an_intake_role_without_level_or_years_is_a_concrete_ask_not_the_jobs_role():
    text = "0-to-1 product delivery is a strong plus."
    it = item("role", "strong_plus", "0-to-1 product delivery", "0-to-1 product delivery is a strong plus", role_family="product_management")
    out = engine.read(text, OneItem(it), "intake")
    assert [i.kind for i in out.items] == ["other"]


def test_a_background_left_empty_by_the_model_is_read_from_the_quote():
    text = "Early-stage start-up experience is a strong plus. No candidates from big consultancies."
    it = item("employer", "strong_plus", "early-stage start-up experience", "Early-stage start-up experience is a strong plus")
    assert engine.read(text, OneItem(it), "intake").items[0].fields["employer_kinds"] == ["startup"]
    it = item("employer", "anti", "not from consultancies", "No candidates from big consultancies")
    assert engine.read(text, OneItem(it), "intake").items[0].fields["employer_kinds"] == ["consultancy"]
