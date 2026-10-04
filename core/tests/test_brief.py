"""Slice 3: the Brief. Compiled from what is not known, priority by default, answers become official facts and
re-match, person-wide answers are inherited, answered and dismissed items never come back, no send path."""

import uuid

from sqlalchemy import select

from maindscout.db.models import BriefItem, Claim
from tests.test_api import client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import JD_JSON, JD_LINES

RUST_JD = {**JD_JSON, "requirements": [{"text": "Rust", "category": "skill", "strength": "must", "token": "rust",
                                        "distinctive": True, "quote": "You must have InSAR processing experience."}]}


def priority_job(client, fake, name="rust.pdf"):
    fake.jd = RUST_JD
    job = client.post("/v1/jobs", files=pdf_file(JD_LINES, name)).json()["job_id"]
    cid = drop_cv(client, job)["subject_id"]  # Jane has Rust: priority
    return job, cid


def brief(client, job, cid, **params):
    r = client.get(f"/v1/jobs/{job}/people/{cid}/brief", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def by_key(items):
    return {i["source_key"]: i for i in items}


def test_briefs_are_for_priority_people_by_default(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]  # no InSAR: do not submit
    b = brief(client, job, cid)
    assert b["available"] is False and "priority" in b["reason"]
    assert brief(client, job, cid, force="true")["available"] is True


def test_the_brief_compiles_person_and_job_questions_from_fixed_templates(client, fake, session):
    job, cid = priority_job(client, fake)
    client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "Fintech experience",
                                                     "domains": ["fintech"]})
    items = by_key(brief(client, job, cid)["items"])
    assert {"std:notice", "std:salary", "std:marketable"} <= set(items)
    assert "std:location" not in items, "Jane says she lives in Bristol"
    fintech = next(i for i in items.values() if "Fintech" in i["question"])
    assert fintech["scope"] == "job" and fintech["status"] == "open"
    assert items["std:notice"]["scope"] == "person"


def test_an_answer_becomes_an_official_fact_and_settles_its_requirement(client, fake, session):
    job, cid = priority_job(client, fake)
    client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "Fintech experience",
                                                     "domains": ["fintech"]})
    fintech = next(i for i in brief(client, job, cid)["items"] if "Fintech" in i["question"])
    r = client.post(f"/v1/brief/{fintech['id']}/answer", json={"outcome": "confirmed", "answer": "3 years at a payments start-up"})
    assert r.status_code == 200 and r.json()["status"] == "answered"
    claim = session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "BriefAnswerClaim")).one()
    assert claim.status == "approved" and claim.payload["outcome"] == "confirmed"
    gaps = client.get(f"/v1/jobs/{job}/people/{cid}/gaps").json()
    row = next(v for v in gaps["match"]["rows"] if v["requirement"] == "Fintech experience")
    assert row["verdict"] == "strong" and "confirmed on the call: 3 years" in row["detail"]
    assert client.post(f"/v1/brief/{fintech['id']}/answer", json={"outcome": "confirmed"}).status_code == 422, "answered once"


def test_person_wide_answers_are_inherited_by_every_job(client, fake, session):
    job_a, cid = priority_job(client, fake, "a.pdf")
    notice = by_key(brief(client, job_a, cid)["items"])["std:notice"]
    client.post(f"/v1/brief/{notice['id']}/answer", json={"outcome": "noted", "answer": "one month"})
    fake.jd = RUST_JD
    job_b = client.post("/v1/jobs", files=pdf_file(JD_LINES + ["Second role."], "b.pdf")).json()["job_id"]
    client.post(f"/v1/jobs/{job_b}/people/{cid}")
    on_b = by_key(brief(client, job_b, cid)["items"])["std:notice"]
    assert on_b["id"] == notice["id"] and on_b["status"] == "answered" and on_b["answer"] == "one month"


def test_regeneration_never_brings_back_answered_or_dismissed_items(client, fake, session):
    job, cid = priority_job(client, fake)
    items = by_key(brief(client, job, cid)["items"])
    client.post(f"/v1/brief/{items['std:salary']['id']}/answer", json={"outcome": "noted", "answer": "60k"})
    client.post(f"/v1/brief/{items['std:marketable']['id']}/dismiss")
    client.post(f"/v1/brief/{items['std:notice']['id']}/asked")
    again = by_key(brief(client, job, cid)["items"])
    assert again["std:salary"]["status"] == "answered" and again["std:marketable"]["status"] == "dismissed"
    assert again["std:notice"]["status"] == "asked"
    assert len(session.scalars(select(BriefItem).where(BriefItem.candidate_id == uuid.UUID(cid), BriefItem.source_key == "std:salary")).all()) == 1


def test_an_item_whose_reason_is_gone_expires(client, fake, session):
    job, cid = priority_job(client, fake)
    r = client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "Fintech experience",
                                                         "domains": ["fintech"]})
    fintech = next(i for i in brief(client, job, cid)["items"] if "Fintech" in i["question"])
    client.post(f"/v1/claims/{r.json()['id']}/reject", json={"code": "wrong"})
    after = {i["id"]: i for i in brief(client, job, cid)["items"]}
    assert after[fintech["id"]]["status"] == "expired"


def test_a_location_answer_becomes_where_they_live(client, fake, session):
    from tests.test_process import cv_json

    fake.cv = cv_json(locations=[])
    job, cid = priority_job(client, fake)
    loc = by_key(brief(client, job, cid)["items"])["std:location"]
    client.post(f"/v1/brief/{loc['id']}/answer", json={"outcome": "confirmed", "answer": "Leeds, UK"})
    place = session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "LocationClaim",
                                                Claim.status == "approved")).one()
    assert place.payload["country_code"] == "GB"


def test_erasure_removes_the_brief(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job, cid = priority_job(client, fake)
    brief(client, job, cid)
    assert client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "request"}).status_code == 200
    assert not session.scalars(select(BriefItem).where(BriefItem.candidate_id == uuid.UUID(cid))).all()
    assert client.get(f"/v1/subjects/candidate/{cid}/erase/verify").json()["clean"] is True


def test_job_questions_come_must_haves_first_and_where_they_live_last():
    from maindscout.domain import brief as compiler

    rows = [{"requirement_id": "1", "requirement": "Clients", "kind": "skill", "strength": "nice", "verdict": "ask", "detail": ""},
            {"requirement_id": "2", "requirement": "Live in DE", "kind": "mobility", "strength": "must", "verdict": "ask", "detail": "ask"},
            {"requirement_id": "3", "requirement": "InSAR", "kind": "skill", "strength": "must", "verdict": "ask", "detail": ""},
            {"requirement_id": "4", "requirement": "Start-up", "kind": "employer", "strength": "strong_plus", "verdict": "gap", "detail": "none"}]
    assert [i.source_key for i in compiler.for_job(rows)] == ["req:3", "req:4", "req:1", "req:2"]
