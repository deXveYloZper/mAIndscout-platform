"""Performance work (2026-10-05): batched code must give the same answers as the one-at-a-time code it replaced, and a
big job re-matches in the background. Timings themselves are measured by `python -m maindscout perf-check`."""

import uuid

from sqlalchemy import select

from maindscout.api import process, queries, tasks
from maindscout.db.models import CandidateJob, Job, Task
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES


def org_of(client):
    return uuid.UUID(client.headers["X-Org-Id"])


def test_a_big_job_re_matches_in_the_background_and_says_so(client, session, monkeypatch):
    job = make_job(client)
    drop_cv(client, job)
    monkeypatch.setattr(process, "INLINE_JOB_REMATCH", 0)  # every job counts as big
    r = client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "Fintech experience",
                                                       "domains": ["fintech"]})
    assert r.status_code == 201, r.text
    queued = session.scalars(select(Task).where(Task.kind == "rematch_job", Task.status == "queued")).all()
    assert len(queued) == 1 and client.get(f"/v1/jobs/{job}").json()["rematching"] is True
    client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "nice", "text_raw": "Payments", "domains": ["payments"]})
    assert len(session.scalars(select(Task).where(Task.kind == "rematch_job", Task.status == "queued")).all()) == 1, "deduplicated"
    tasks.execute(session, queued[0])
    queued[0].status = "done"
    session.flush()
    assert client.get(f"/v1/jobs/{job}").json()["rematching"] is False


def test_a_small_job_still_re_matches_at_once(client, session):
    job = make_job(client)
    drop_cv(client, job)
    client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "Fintech experience",
                                                   "domains": ["fintech"]})
    assert not session.scalars(select(Task).where(Task.kind == "rematch_job")).all()


def test_matching_without_snippets_gives_the_same_gap_table(client, session):
    job_id = make_job(client)
    cid = uuid.UUID(drop_cv(client, job_id)["subject_id"])
    job = session.get(Job, uuid.UUID(job_id))
    full = queries._gap_rows_many(session, org_of(client), job, [cid])[cid]
    lean = queries._gap_rows_many(session, org_of(client), job, [cid], with_snippets=False)[cid]
    strip = lambda rows: [(r.requirement_id, r.status, r.official, sorted(f.id for f in r.facts)) for r in rows]  # noqa: E731
    assert strip(full) == strip(lean)
    inputs = process.pair_inputs(session, org_of(client), cid, job)
    pre = queries._gap_rows_many(session, org_of(client), job, [cid], with_snippets=False, preloaded=(inputs[0], {cid: inputs[1]}))[cid]
    assert strip(pre) == strip(full)


def test_the_jobs_list_counts_the_same_as_each_jobs_inbox(client, session):
    job_a, job_b = make_job(client), make_job(client)
    drop_cv(client, job_a)
    drop_cv(client, job_b, CV_LINES[:1] + ["omar@example.com"] + CV_LINES[2:], name="b.pdf")
    for row in client.get("/v1/jobs").json():
        expected = len(queries.inbox(session, org_of(client), uuid.UUID(row["id"]), "priority"))
        assert row["to_review"] == expected


def test_re_matching_a_pair_twice_records_nothing_new(client, session):
    job = make_job(client)
    drop_cv(client, job)
    pair = session.scalars(select(CandidateJob)).first()
    assert process.retriage_pair(session, pair, {"act": "again"}) is None, "a stable reason: no spurious band event"
