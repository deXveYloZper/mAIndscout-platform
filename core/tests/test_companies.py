"""Intelligence track I1: companies as shared records, linked from career steps and jobs."""

import uuid

from sqlalchemy import select

from maindscout.api import companies
from maindscout.db.models import Company, Decision
from tests.test_api import client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES, cv_json


def person(client, fake, email, steps):
    fake.cv = cv_json(contacts=[{"kind": "email", "value": email, "quote": "jane.example@example.com"}],
                      career_steps=steps, education=[], skills=[], locations=[])
    r = client.post("/v1/candidates", files=pdf_file(CV_LINES + [email], f"{email}.pdf"))
    assert r.status_code == 201, r.text
    return r.json()["subject_id"]


def step(company, title="Engineer", start="2019-03", end="present",
         quote="Flight Software Engineer, Acme Space, Mar 2019 - Present"):
    return {"company": company, "title": title, "employment_type": "full_time", "location": None, "start": start, "end": end, "quote": quote}


def test_the_same_company_written_differently_is_one_company(client, fake, session):
    a = person(client, fake, "a@example.com", [step("Acme Space GmbH")])
    b = person(client, fake, "b@example.com", [step("ACME Space")])
    found = client.get("/v1/companies", params={"q": "acme space"}).json()
    assert len(found) == 1 and found[0]["people_count"] == 2
    page = client.get(f"/v1/companies/{found[0]['id']}").json()
    assert {p["candidate_id"] for p in page["people"]} == {a, b}
    assert page["people"][0]["current"] is True and page["people"][0]["roles"][0]["title"] == "Engineer"


def test_two_roles_at_one_company_show_as_one_person_with_both_roles(client, fake, session):
    person(client, fake, "two@example.com", [
        step("Acme Space", title="Senior Engineer", start="2019-03", end="present", quote="Flight Software Engineer, Acme Space, Mar 2019 - Present"),
        step("Acme Space", title="Engineer", start="2016-01", end="2019-02", quote="Frontend Developer, Beta Web, Jan 2016 - Feb 2019")])
    found = client.get("/v1/companies", params={"q": "acme space"}).json()[0]
    page = client.get(f"/v1/companies/{found['id']}").json()
    assert page["people_count"] == 1 and len(page["people"]) == 1


def test_self_employment_is_not_a_company_and_reads_as_contract(client, fake, session):
    cid = person(client, fake, "c@example.com", [step("Self Employed", title="Consultant")])
    career = next(c for c in client.get(f"/v1/candidates/{cid}/claims").json() if c["claim_type"] == "CareerStepClaim")
    assert career["payload"]["company"]["company_id"] is None
    assert career["payload"]["employment_type"] == "contract"


def test_a_similar_new_name_raises_a_card_and_is_never_merged_automatically(client, fake, session):
    person(client, fake, "d@example.com", [step("Bitpanda")])
    person(client, fake, "e@example.com", [step("Bitpanda Technology Solutions")])
    assert len(client.get("/v1/companies", params={"q": "bitpanda"}).json()) == 2
    card = next(i for i in client.get("/v1/inbox", params={"band": "all"}).json() if i["kind"] == "company_same")
    assert card["context"]["existing"]["name"] == "Bitpanda"
    client.post(f"/v1/decisions/{card['id']}/resolve", json={"action": "same"})
    merged = client.get("/v1/companies", params={"q": "bitpanda"}).json()
    assert len(merged) == 1 and merged[0]["name"] == "Bitpanda" and merged[0]["people_count"] == 2


def test_different_companies_with_similar_names_stay_apart_when_a_human_says_so(client, fake, session):
    person(client, fake, "f@example.com", [step("Semantika")])
    person(client, fake, "g@example.com", [step("Semantikb")])
    card = next(i for i in client.get("/v1/inbox", params={"band": "all"}).json() if i["kind"] == "company_same")
    client.post(f"/v1/decisions/{card['id']}/resolve", json={"action": "different"})
    assert len(client.get("/v1/companies", params={"q": "semantik"}).json()) == 2


def test_who_we_know_at_a_company_is_private_to_each_desk(client, fake, session):
    from maindscout.api import writer
    person(client, fake, "h@example.com", [step("Acme Space")])
    company = session.scalar(select(Company).where(Company.normalized == "acme space"))
    other = writer.create_org(session, "other desk")
    assert companies.people_at(session, other.id, company.id) == []
    assert len(client.get(f"/v1/companies/{company.id}").json()["people"]) == 1


def test_a_job_links_to_its_hiring_company(client, fake, session):
    job_id = make_job(client)  # hiring company "Catalyst Geo"
    found = client.get("/v1/companies", params={"q": "catalyst geo"}).json()
    assert found and client.get(f"/v1/companies/{found[0]['id']}").json()["jobs"][0]["id"] == job_id


def test_existing_steps_without_a_link_are_linked_by_the_backfill(client, fake, session, org):
    from maindscout.db.models import Claim
    cid = person(client, fake, "i@example.com", [step("Acme Space")])
    claim = session.scalar(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "CareerStepClaim"))
    claim.payload = {**claim.payload, "company": {**claim.payload["company"], "company_id": None}}
    session.flush()
    assert companies.link_org(session, org.id)["career_steps_linked"] == 1
    session.refresh(claim)
    assert claim.payload["company"]["company_id"]


def test_erasure_also_removes_company_cards_raised_by_that_persons_cv(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    person(client, fake, "j@example.com", [step("Bitpanda")])
    cid = person(client, fake, "k@example.com", [step("Bitpanda Technology Solutions")])
    assert session.scalars(select(Decision).where(Decision.type == "company_same")).all()
    r = client.post(f"/v1/subjects/candidate/{cid}/erase", json={}).json()
    assert r["clean"], r["survivors"]
    assert not session.scalars(select(Decision).where(Decision.type == "company_same")).all()


def test_name_normalisation_and_suggestions():
    from maindscout.domain.companies import normalize, possibly_same
    assert normalize("Bwin.Party (Entain)").normalized == "bwin party"
    assert normalize("Semantika d.o.o.").normalized == "semantika"
    assert normalize("Stealth Startup").kind == "undisclosed"
    assert possibly_same("bitpanda", "bitpanda technology solutions")
    assert not possibly_same("kpmg moscow", "kpmg toronto")
