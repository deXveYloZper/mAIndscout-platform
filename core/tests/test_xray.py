"""The desk x-ray fixes (docs/build/XRAY-2026-10-13.md): what is entered reaches every place that should use it.
Each test is one finding of the x-ray, walked the way the cockpit does it."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from maindscout.api import autosource, companies, company_profiles, outreach, process, strategy
from maindscout.db.models import CandidateJob, Company, Document, Job, Message, Task
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import FakeExa, blobs, go, job, person_named  # noqa: F401 (fixtures)
from tests.test_phase1b import page as company_page


def pair(session, job_id, cid):
    session.expire_all()
    return session.scalar(select(CandidateJob).where(CandidateJob.job_id == job_id, CandidateJob.candidate_id == cid))


def card(client, job_id, cid):
    page = client.get(f"/v1/jobs/{job_id}/sourcing").json()
    return next((r for rows in [page["suggestions"], *page["lists"].values()] for r in rows if r["candidate_id"] == str(cid)), None)


def residence(client, job_id):
    return [r["payload"]["mobility"]["countries"] for r in client.get(f"/v1/jobs/{job_id}").json()["requirements"]
            if (r["payload"].get("mobility") or {}).get("facet") == "residence"]


# --- A1, B1: one place for a role's countries -------------------------------------------------------------------------


def test_a_roles_countries_live_in_one_place_and_names_are_understood(client, session, job):
    jid = str(job.id)
    r = client.patch(f"/v1/jobs/{jid}/sourcing/plan", json={"countries": ["Italy", "DE"]})
    assert r.status_code == 200 and set(r.json()["plan"]["countries"]) == {"IT", "DE"}, "a name is understood, never dropped"
    assert residence(client, jid) == [["IT", "DE"]], "written to the hiring profile's 'must live in'"
    client.put(f"/v1/jobs/{jid}/countries", json={"countries": ["Spain"]})
    assert residence(client, jid) == [["ES"]] and client.get(f"/v1/jobs/{jid}/sourcing").json()["plan"]["countries"] == ["ES"], \
        "the hiring profile's countries and the plan's are the same, both ways"
    bad = client.patch(f"/v1/jobs/{jid}/sourcing/plan", json={"countries": ["Narnia"]})
    assert bad.status_code == 422 and "Narnia" in bad.json()["detail"], "an unknown country is refused, not dropped"
    assert client.get(f"/v1/jobs/{jid}/sourcing").json()["plan"]["countries"] == ["ES"]
    assert strategy.role_countries(session, session.get(Job, job.id)) == {"ES"}


# --- A2, B2: one contact record, whichever door -----------------------------------------------------------------------


def test_contact_and_replies_are_one_record_whichever_door_is_used(client, session, job, blobs):
    jid = str(job.id)
    client.patch(f"/v1/jobs/{jid}/sourcing/plan", json={"countries": ["DE"]})
    go(session, job, FakeExa(), blobs)
    session.commit()
    ada, ben = person_named(session, "Ada Testperson"), person_named(session, "Ben Testperson")
    client.post(f"/v1/jobs/{jid}/people/{ada}/decide", json={"choice": "reach_out"})
    m = client.post("/v1/messages", json={"kind": "candidate_outreach", "candidate_id": str(ada), "job_id": jid, "channel": "linkedin"}).json()
    client.post(f"/v1/messages/{m['id']}/sent", json={})
    c = card(client, jid, ada)
    assert c["stage"] == "contacted" and c["contact"]["channel"] == "linkedin_message" and c["contact"]["contacted_at"]
    assert c["follow_up"]["due"], "the follow-up reminder runs from the message"
    assert ada in [p.candidate_id for p in outreach._watched(session, job.org_id)], "the LinkedIn email reader watches them"
    client.post(f"/v1/messages/{m['id']}/replied", json={})
    assert card(client, jid, ada)["stage"] == "replied", "'They replied' on the message moves the card"

    client.post(f"/v1/candidates/{ben}/activities", json={"kind": "call", "summary": "Called about the role", "direction": "out", "job_id": jid})
    p = pair(session, job.id, ben)
    assert p.pair_state == "contacted" and p.contact["channel"] == "phone", "a logged call about the role is first contact"
    client.post(f"/v1/candidates/{ben}/activities", json={"kind": "email", "summary": "He wrote back: keen", "direction": "in", "job_id": jid})
    p = pair(session, job.id, ben)
    assert p.contact["stage"] == "replied" and "keen" in p.contact["reply"]["text"], "'they reached out' is a reply"
    client.post(f"/v1/jobs/{jid}/people/{ben}/replied", json={"outcome": "interested"})
    client.post(f"/v1/candidates/{ben}/activities", json={"kind": "note", "summary": "a note", "direction": "in", "job_id": jid})
    assert pair(session, job.id, ben).contact["reply"]["outcome"] == "interested", "a later reply never blanks the owner's word"

    jane = drop_cv(client, jid)["subject_id"]
    client.post(f"/v1/jobs/{jid}/people/{jane}/state", json={"state": "contacted"})
    p = pair(session, job.id, uuid.UUID(jane))
    assert p.contact["contacted_at"] and p.contact["follow_up_due"], "the stage set by hand plans a follow-up too"

    stats = client.get("/v1/sourcing/stats", params={"job_id": jid, "group": "channel"}).json()["totals"]
    assert (stats["contacted"], stats["replied"], stats["interested"]) == (2, 2, 1), \
        "the results count replies and 'interested' from the same record (A3)"


# --- B3: "not from" ---------------------------------------------------------------------------------------------------


def test_not_from_a_company_or_a_kind_of_company_reaches_sourcing(client, session, job, blobs):
    jid = str(job.id)
    client.post(f"/v1/jobs/{jid}/requirements", json={"category": "target_company", "strength": "anti", "text_raw": "Orbital Testworks",
                                                      "companies": ["Orbital Testworks"]})
    client.post(f"/v1/jobs/{jid}/requirements", json={"category": "employer", "strength": "anti", "text_raw": "No consultancies",
                                                      "employer_kinds": ["consultancy"]})
    client.patch(f"/v1/jobs/{jid}/sourcing/plan", json={"countries": ["DE"]})
    row, _ = go(session, job, FakeExa(), blobs)
    assert row.report["refused"].get("not_from") == 2, "Ada and Ben work at Orbital Testworks now"
    shown = [s["name"] for s in client.get(f"/v1/jobs/{jid}/sourcing").json()["suggestions"]]
    assert "Ada Testperson" not in shown and "Ben Testperson" not in shown
    advisers, _ = companies.resolve(session, "Testing Advisers", "test")
    advisers.exa_profile = {"kind": "consultancy"}
    assert strategy.fit(session, advisers, set(), strategy.not_from(session, session.get(Job, job.id))[1])["searched"] is False


# --- B5: permission, B6: close and delete -----------------------------------------------------------------------------


def test_submitting_without_permission_is_flagged(client, session, job):
    jane = drop_cv(client, str(job.id))["subject_id"]
    page = client.get(f"/v1/jobs/{job.id}/people/{jane}/gaps").json()
    assert page["permission"] == {"this_role": False, "other_roles": False}
    client.post(f"/v1/candidates/{jane}/permission", json={"job_id": str(job.id), "this_role": True, "how": "call"})
    assert client.get(f"/v1/jobs/{job.id}/people/{jane}/gaps").json()["permission"]["this_role"] is True


def test_a_role_can_be_closed_and_a_mistaken_one_deleted(client, session, job, blobs):
    jid = str(job.id)
    client.patch(f"/v1/jobs/{jid}/sourcing/plan", json={"mode": "daily", "countries": ["DE"]})
    r = client.put(f"/v1/jobs/{jid}/state", json={"state": "filled", "note": "placed via another agency"})
    assert r.status_code == 200 and r.json()["state"] == "filled"
    assert autosource.current_plan(session, job.id).mode == "paused", "a closed role stops searching"
    assert all(j["id"] != jid for j in client.get("/v1/today").json()["jobs"]), "and leaves the open lists"
    client.put(f"/v1/jobs/{jid}/state", json={"state": "open"})

    go(session, job, FakeExa(), blobs)
    session.commit()
    ada = person_named(session, "Ada Testperson")
    jane = drop_cv(client, jid)["subject_id"]
    ad = session.get(Job, job.id).source_document_id
    assert client.get(f"/v1/jobs/{jid}").json()["found_only_here"] == 2, "Ada and Ben: public profiles, on no other role"
    r = client.delete(f"/v1/jobs/{jid}", params={"remove_people": "true"})
    assert r.status_code == 200 and r.json()["counts"]["people_removed"] == 2
    session.expire_all()
    assert session.get(Job, job.id) is None and session.get(Document, ad) is None, "the role and its ad are gone"
    assert client.get(f"/v1/candidates/{ada}").status_code == 404, "the people only it found are gone"
    assert client.get(f"/v1/candidates/{jane}").status_code == 200, "someone with a CV stays"


# --- A4, A6, B8, C: company knowledge -----------------------------------------------------------------------------------


def test_a_company_gets_its_website_typed_and_says_why_research_did_not_run(client, session):
    company, _ = companies.resolve(session, "Buona Testventura", "test")
    assert client.put(f"/v1/companies/{company.id}/keys", json={"website": "linkedin.com/in/someone"}).status_code == 422
    out = client.put(f"/v1/companies/{company.id}/keys", json={"website": "https://www.buona-testventura.example/it"}).json()
    assert out["keys"]["domain"] == "buona-testventura.example" and out["clash"] is None
    session.add(Task(kind="research_company", payload={"company_id": str(company.id)}, status="failed",
                     error="BudgetExceeded: Monthly budget reached: $10.21 of $10.00."))
    session.flush()
    assert client.get(f"/v1/companies/{company.id}").json()["research_attempt"]["why"] == "budget"


def test_the_strategy_says_exactly_what_is_missing_about_the_hiring_company(client, session, job):
    company = session.get(Company, job.hiring_company_id)
    company.domain = company.linkedin = company.exa_id = None
    session.flush()
    try:
        strategy.talent_dna(session, job.org_id, job, autosource.plan(session, job.org_id, job.id), FakeExa())
        raise AssertionError("no key: refused")
    except autosource.SourcingEngineError as error:
        assert "no website or LinkedIn page" in str(error) and "company page" in str(error)


def test_a_cvs_companies_get_an_exa_profile_and_grok_is_kept_for_companies_that_matter(client, session, monkeypatch):
    monkeypatch.setenv("RESEARCH_AUTO", "true")
    job_id = make_job(client)
    jane = drop_cv(client, job_id)["subject_id"]
    session.query(Task).delete()
    process._queue_research(session, uuid.UUID(jane), uuid.UUID(client.headers["X-Org-Id"]))
    kinds = {t.kind for t in session.scalars(select(Task))}
    assert kinds == {"profile_company"}, f"a CV's companies get an Exa profile, not Grok research: {kinds}"
    client.put(f"/v1/jobs/{job_id}/hiring-company", json={"name": "Brand New Testclient"})
    assert "research_company" in {t.kind for t in session.scalars(select(Task))}, "a hiring company gets Grok research"

    acme, _ = companies.resolve(session, "Acme Testspace", "test")
    look_alike = company_page("x1", "Acme Testspace Systems", "acme-space-systems.example", hq="Munich, Bavaria, Germany")
    assert not company_profiles.by_name_and_place(session, acme, "DE", FakeExa(companies=[look_alike])), "a similar name is not it"
    same = company_page("x2", "Acme Testspace", "acme-space.example", hq="Munich, Bavaria, Germany", countries="Germany: 70 (90%)")
    elsewhere = company_page("x3", "Acme Testspace", "acme-space.example", hq="Austin, Texas, United States",
                             countries="United States: 70 (100%)")
    assert not company_profiles.by_name_and_place(session, acme, "DE", FakeExa(companies=[elsewhere])), "same name, another place"
    assert company_profiles.by_name_and_place(session, acme, "DE", FakeExa(companies=[same]))
    assert acme.domain == "acme-space.example" and acme.exa_profile
