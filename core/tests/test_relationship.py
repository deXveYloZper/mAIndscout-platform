"""Slice 4 step 1: relationship memory. Calls, emails and notes; one timeline with what the platform already records;
last contacted and last verified; tags as talent pools; contacts at client companies; erased with the person."""

import uuid

from sqlalchemy import select

from maindscout.db.models import Activity, CandidateTag, Company
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)


def test_a_logged_call_joins_the_timeline_with_what_the_platform_already_knows(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    r = client.post(f"/v1/candidates/{cid}/activities", json={"kind": "call", "direction": "out", "summary": "Intro call, open to move",
                                                             "occurred_at": "2026-09-30T10:00:00", "job_id": job})
    assert r.status_code == 201, r.text
    client.post(f"/v1/candidates/{cid}/activities", json={"kind": "note", "summary": "Prefers remote"})
    rel = client.get(f"/v1/candidates/{cid}").json()["relationship"]
    types = [row["type"] for row in rel["timeline"]]
    assert {"call", "note", "cv", "band"} <= set(types)
    call = next(row for row in rel["timeline"] if row["type"] == "call")
    assert call["job"] == "Radar Interferometry Specialist" and call["direction"] == "out"
    assert rel["last_contacted"].startswith("2026-09-30"), "a note is not contact; the call is"
    assert rel["last_verified"], "the CV read counts as the last time the facts were refreshed"


def test_bad_entries_are_refused(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    for body in ({"kind": "call", "summary": "  "}, {"kind": "fax", "summary": "x"},
                 {"kind": "call", "summary": "x", "occurred_at": "2099-01-01"}, {"kind": "call", "summary": "x", "direction": "sideways"}):
        assert client.post(f"/v1/candidates/{cid}/activities", json=body).status_code == 422, body


def test_tags_are_talent_pools(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    assert client.post(f"/v1/candidates/{cid}/tags", json={"tag": "InSAR Pool"}).json()["tag"] == "insar-pool"
    client.post(f"/v1/candidates/{cid}/tags", json={"tag": "insar-pool"})  # twice is once
    assert client.get("/v1/tags").json() == [{"tag": "insar-pool", "people": 1}]
    assert [p["id"] for p in client.get("/v1/candidates", params={"tag": "insar-pool"}).json()] == [cid]
    assert client.get(f"/v1/candidates/{cid}").json()["relationship"]["tags"] == ["insar-pool"]
    assert client.delete(f"/v1/candidates/{cid}/tags/insar-pool").status_code == 204
    assert client.get("/v1/candidates", params={"tag": "insar-pool"}).json() == []


def test_contacts_at_a_client_and_their_calls(client, fake, session):
    job = make_job(client)
    company = session.scalar(select(Company).where(Company.normalized == "catalyst geo"))
    r = client.post(f"/v1/companies/{company.id}/contacts", json={"name": "Anna Example", "role": "Head of Engineering",
                                                                  "email": "anna@catalyst.example"})
    assert r.status_code == 201
    contact = r.json()["id"]
    client.post(f"/v1/companies/{company.id}/activities", json={"kind": "call", "summary": "Intake for the InSAR role",
                                                               "contact_id": contact, "job_id": job})
    page = client.get(f"/v1/companies/{company.id}").json()
    assert page["contacts"][0]["name"] == "Anna Example" and page["contacts"][0]["last_contacted"]
    call = next(row for row in page["timeline"] if row["type"] == "call")
    assert call["contact"] == "Anna Example" and page["last_contacted"]
    assert any(row["type"] == "job" for row in page["timeline"])
    assert client.delete(f"/v1/contacts/{contact}").status_code == 204
    page = client.get(f"/v1/companies/{company.id}").json()
    assert page["contacts"] == [] and next(row for row in page["timeline"] if row["type"] == "call")["contact"] is None


def test_erasure_removes_activities_and_tags(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    client.post(f"/v1/candidates/{cid}/activities", json={"kind": "call", "summary": "Intro"})
    client.post(f"/v1/candidates/{cid}/tags", json={"tag": "warm"})
    assert client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "request"}).status_code == 200
    assert not session.scalars(select(Activity).where(Activity.subject_id == uuid.UUID(cid))).all()
    assert not session.scalars(select(CandidateTag).where(CandidateTag.candidate_id == uuid.UUID(cid))).all()
    assert client.get(f"/v1/subjects/candidate/{cid}/erase/verify").json()["clean"] is True
