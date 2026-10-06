"""A Brief without a job (owner, 2026-10-06): anyone on the desk, e.g. someone in the pool, can be called and briefed;
the person questions count for every job, and the Brief shows how to reach them."""

import uuid

from sqlalchemy import select

from maindscout.db.models import BriefItem
from tests.test_api import client, fake, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES


def pool_person(client) -> str:
    r = client.post("/v1/candidates", files=pdf_file(CV_LINES, "pool.pdf"))
    assert r.status_code == 201, r.text
    return r.json()["subject_id"]


def test_someone_in_the_pool_gets_a_brief_with_how_to_reach_them(client, session):
    cid = pool_person(client)
    b = client.get(f"/v1/candidates/{cid}/brief").json()
    assert b["available"] is True
    questions = [i["question"] for i in b["items"]]
    assert any("Notice period" in q for q in questions) and any("looking for next" in q for q in questions)
    assert all(i["scope"] == "person" for i in b["items"])
    assert {c["kind"]: c["value"] for c in b["contacts"]}["email"] == "jane.example@example.com"


def test_a_pool_answer_counts_when_they_are_put_on_a_job_later(client, session):
    cid = pool_person(client)
    notice = next(i for i in client.get(f"/v1/candidates/{cid}/brief").json()["items"] if "Notice period" in i["question"])
    assert client.post(f"/v1/brief/{notice['id']}/answer", json={"outcome": "noted", "answer": "one month"}).status_code == 200
    again = client.get(f"/v1/candidates/{cid}/brief").json()["items"]
    assert next(i for i in again if i["id"] == notice["id"])["status"] == "answered", "not asked again"
    items = session.scalars(select(BriefItem).where(BriefItem.candidate_id == uuid.UUID(cid))).all()
    assert all(i.job_id is None for i in items), "person questions belong to no job, so every job's Brief shares them"


def test_the_person_list_and_page_carry_the_pipeline_stage(client):
    cid = pool_person(client)
    assert client.get(f"/v1/candidates/{cid}").json()["jobs"] == []
    rows = [p for p in client.get("/v1/candidates").json() if p["id"] == cid]
    assert rows and rows[0]["jobs"] == []
