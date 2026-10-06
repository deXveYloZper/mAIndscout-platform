"""Navigation reads (design plan): the sidebar's inbox count, the ⌘K lookup, the Today page."""

import uuid

from maindscout.api import overview, queries
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES


def org_of(client):
    return uuid.UUID(client.headers["X-Org-Id"])


def test_the_sidebar_count_is_what_the_inbox_shows(client, session):
    job = make_job(client)
    drop_cv(client, job)
    drop_cv(client, job, ["Name not here"] + CV_LINES[1:], name="noname.pdf")  # a nameless CV raises a card
    shown = len(queries.inbox(session, org_of(client), None, "all"))
    assert shown >= 1
    assert overview.inbox_count(session, org_of(client)) == shown
    assert client.get("/v1/nav").json() == {"inbox": shown}


def test_lookup_finds_people_jobs_and_companies_by_part_of_a_name(client):
    job = make_job(client)
    drop_cv(client, job)
    found = client.get("/v1/lookup", params={"q": "jane"}).json()
    assert [p["name"] for p in found["people"]] == ["Jane Example"] and found["people"][0]["meta"] == "on 1 job"
    assert client.get("/v1/lookup", params={"q": "radar"}).json()["jobs"][0]["name"] == "Radar Interferometry Specialist"
    assert client.get("/v1/lookup", params={"q": "acme"}).json()["companies"][0]["name"].lower().startswith("acme")
    assert client.get("/v1/lookup", params={"q": "j"}).json() == {"people": [], "jobs": [], "companies": []}
    assert client.get("/v1/lookup", params={"q": "%_"}).json()["people"] == [], "wildcards are literal"


def test_today_gathers_the_start_of_the_day(client):
    job = make_job(client)
    drop_cv(client, job)
    t = client.get("/v1/today").json()
    assert set(t) == {"inbox", "priority", "stale", "pool", "jobs", "recent"}
    assert t["jobs"][0]["id"] == job and t["recent"] and t["recent"][0]["person"] == "Jane Example"
