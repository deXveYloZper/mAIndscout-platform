"""Slice 4 step 2: the full pipeline, and a client's rejection as a wall at that client."""

import uuid

from sqlalchemy import select

from maindscout.api import sourcing
from maindscout.db.models import ClientBlock, Job
from tests.test_api import client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import JD_LINES


def move(client, job, cid, state, **extra):
    return client.post(f"/v1/jobs/{job}/people/{cid}/state", json={"state": state, **extra})


def second_job(client):
    r = client.post("/v1/jobs", files=pdf_file(JD_LINES + ["A second role at the same company."], "second.pdf"))
    assert r.status_code == 201, r.text
    return r.json()["job_id"]


def test_a_pair_moves_through_the_whole_pipeline_and_every_move_is_kept(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    for state, extra in [("seen", {}), ("contacted", {}), ("screened", {}), ("submitted", {"note": "to Anna, by email"}),
                         ("interviewing", {}), ("offer", {}), ("placed", {"note": "starts 1 Nov"})]:
        r = move(client, job, cid, state, **extra)
        assert r.status_code == 200, (state, r.text)
    assert move(client, job, cid, "screened").status_code == 422, "leaving an ending needs a note"
    history = [(e["from"], e["to"]) for e in client.get(f"/v1/jobs/{job}/people/{cid}/gaps").json()["history"] if e["kind"] == "state"]
    assert history[-1] == ("offer", "placed") and len(history) == 7
    page = client.get(f"/v1/jobs/{job}").json()
    assert page["stages"]["placed"] == 1


def test_endings_need_their_reasons(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    assert move(client, job, cid, "withdrawn").status_code == 422
    assert move(client, job, cid, "client_rejected").status_code == 422
    r = move(client, job, cid, "withdrawn", note="accepted a counter-offer").json()
    assert r["state"] == "withdrawn" and r["outcome"]["party"] == "candidate"


def test_a_client_rejection_is_a_wall_at_that_client(client, fake, session):
    job_a = make_job(client)
    cid = drop_cv(client, job_a)["subject_id"]
    move(client, job_a, cid, "submitted", note="to Anna")
    r = move(client, job_a, cid, "client_rejected", note="not enough InSAR depth")
    assert r.status_code == 200 and r.json()["outcome"]["party"] == "client"
    block = session.scalars(select(ClientBlock).where(ClientBlock.candidate_id == uuid.UUID(cid))).one()
    assert block.reason == "not enough InSAR depth"
    job_b = second_job(client)
    client.post(f"/v1/jobs/{job_b}/people/{cid}")
    refused = move(client, job_b, cid, "submitted", note="try again")
    assert refused.status_code == 409 and "said no" in refused.json()["detail"]
    gaps = client.get(f"/v1/jobs/{job_b}/people/{cid}/gaps").json()
    assert gaps["match"]["tier"] == "unlikely" and gaps["match"]["rules"][0]["id"] == "client_block"
    assert [p["blocked"] for band in client.get(f"/v1/jobs/{job_b}").json()["people"].values() for p in band] == [True]
    page = client.get(f"/v1/candidates/{cid}").json()
    assert page["blocks"][0]["company"] and page["blocks"][0]["lifted"] is False
    assert client.post(f"/v1/blocks/{block.id}/lift", json={"note": ""}).status_code == 422
    assert client.post(f"/v1/blocks/{block.id}/lift", json={"note": "new hiring manager, open to them"}).status_code == 200
    assert move(client, job_b, cid, "submitted", note="to the new hiring manager").status_code == 200
    assert client.get(f"/v1/jobs/{job_b}/people/{cid}/gaps").json()["match"]["rules"][0]["id"] != "client_block"


def test_blocked_people_are_not_sourced_for_that_client(client, fake, session):
    job_a = make_job(client)
    cid = uuid.UUID(drop_cv(client, job_a)["subject_id"])
    move(client, job_a, str(cid), "client_rejected", note="no")
    job_b = second_job(client)
    found = sourcing.ADAPTERS["desk"].find(session, uuid.UUID(client.headers["X-Org-Id"]), session.get(Job, uuid.UUID(job_b)),
                                           {"tokens": ["insar"]}, limit=10)
    assert cid not in found


def test_the_clients_timeline_shows_submissions_and_its_answers(client, fake, session):
    from maindscout.db.models import Company

    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    move(client, job, cid, "submitted", note="to Anna")
    move(client, job, cid, "client_rejected", note="wants more radar work")
    company = session.scalar(select(Company).where(Company.normalized == "catalyst geo"))
    rows = [r for r in client.get(f"/v1/companies/{company.id}").json()["timeline"] if r["type"] == "pipeline"]
    texts = " ".join(r["text"] for r in rows)
    assert "submitted (to Anna)" in texts and "client rejected (wants more radar work)" in texts


def test_erasure_removes_client_blocks(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    move(client, job, cid, "client_rejected", note="no")
    assert client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "request"}).status_code == 200
    assert not session.scalars(select(ClientBlock).where(ClientBlock.candidate_id == uuid.UUID(cid))).all()
    assert client.get(f"/v1/subjects/candidate/{cid}/erase/verify").json()["clean"] is True
