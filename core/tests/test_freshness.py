"""Slice 4 step 3: freshness. Stale people and clients, and who to re-contact first, with why."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from maindscout.api import freshness
from maindscout.db.models import Company
from tests.test_api import client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_brief import RUST_JD
from tests.test_process import JD_LINES

LATER = datetime.now(timezone.utc) + timedelta(days=250)  # past six months


def org_of(client):
    return uuid.UUID(client.headers["X-Org-Id"])


def test_a_new_cv_is_fresh_and_goes_stale_after_six_months(client, fake, session):
    job = make_job(client)
    cid = uuid.UUID(drop_cv(client, job)["subject_id"])
    assert freshness.of_person(session, org_of(client), cid)["status"] == "fresh"
    later = freshness.of_person(session, org_of(client), cid, now=LATER)
    assert later["status"] == "stale" and "months ago" in later["words"]
    assert client.get(f"/v1/candidates/{cid}").json()["freshness"]["status"] == "fresh"


def test_a_logged_call_makes_a_person_fresh_again(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    assert freshness.of_person(session, org_of(client), uuid.UUID(cid), now=LATER)["status"] == "stale"
    # A call today counts from today: 100 days on, still fresh.
    client.post(f"/v1/candidates/{cid}/activities", json={"kind": "call", "summary": "catch-up"})
    assert freshness.of_person(session, org_of(client), uuid.UUID(cid), now=datetime.now(timezone.utc) + timedelta(days=100))["status"] == "fresh"


def test_the_recontact_list_puts_the_most_valuable_stale_people_first(client, fake, session):
    fake.jd = RUST_JD
    job = client.post("/v1/jobs", files=pdf_file(JD_LINES, "rust.pdf")).json()["job_id"]
    jane = drop_cv(client, job)["subject_id"]  # priority (has Rust)
    from tests.test_coverage import PUNE_LINES, pune_cv

    fake.cv = pune_cv("London, UK", "GB")
    other = client.post("/v1/candidates", files=pdf_file(PUNE_LINES[:-1] + ["Based in London, UK"], "other.pdf")).json()["subject_id"]
    client.post(f"/v1/candidates/{other}/tags", json={"tag": "warm"})
    rows = freshness.recontact(session, org_of(client), now=LATER)
    order = [r["candidate_id"] for r in rows]
    assert order.index(jane) < order.index(other), "priority on a live job comes before a talent pool"
    jane_row = next(r for r in rows if r["candidate_id"] == jane)
    assert any("priority on" in w for w in jane_row["why"])
    assert any("in warm" in w for w in next(r for r in rows if r["candidate_id"] == other)["why"])
    assert freshness.recontact(session, org_of(client)) == [], "nobody is stale today"


def test_clients_with_live_jobs_go_stale_without_contact(client, fake, session):
    make_job(client)
    company = session.scalar(select(Company).where(Company.normalized == "catalyst geo"))
    rows = freshness.reconnect(session, org_of(client), now=LATER + timedelta(days=200))
    assert [r["company_id"] for r in rows] == [str(company.id)] and rows[0]["why"] == ["live job"]
    client.post(f"/v1/companies/{company.id}/activities", json={"kind": "call", "summary": "check-in"})
    assert freshness.reconnect(session, org_of(client), now=datetime.now(timezone.utc) + timedelta(days=30)) == []


def test_the_refresh_route_and_stale_tags(client, fake, session):
    make_job(client)
    body = client.get("/v1/freshness").json()
    assert body["person_months"] == 6 and body["company_months"] == 12 and body["people"] == []
    assert all("stale" in p for p in client.get("/v1/candidates").json())


def test_the_whole_desk_at_once_agrees_with_one_person_at_a_time(client, fake, session):
    """people_status (a few grouped queries, for lists) must give exactly what of_person gives."""
    from tests.test_process import CV_LINES

    job = make_job(client)
    a = drop_cv(client, job)["subject_id"]
    b = drop_cv(client, job, CV_LINES[:1] + ["omar@example.com"] + CV_LINES[2:], name="b.pdf")["subject_id"]
    client.post(f"/v1/candidates/{a}/activities", json={"kind": "call", "summary": "call"})
    client.post(f"/v1/candidates/{b}/activities", json={"kind": "note", "summary": "a note is not contact"})
    org = org_of(client)
    for now in (datetime.now(timezone.utc), LATER, LATER + timedelta(days=400)):
        everyone = freshness.people_status(session, org, now)
        for cid in (uuid.UUID(a), uuid.UUID(b)):
            assert everyone[cid] == freshness.of_person(session, org, cid, now)
