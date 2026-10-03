"""I1 part 2: background tasks and the cost ledger."""

import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from maindscout.api import tasks, task_handlers
from maindscout.db.models import CostEntry, Task
from maindscout.storage import LocalBlobStore
from tests.test_api import RoutingFake, client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES

calls = {"ok": 0, "flaky": 0}


@tasks.handler("test_ok")
def _ok(session, task):
    calls["ok"] += 1
    return {"echo": task.payload.get("x")}


@tasks.handler("test_always_fails")
def _bad(session, task):
    raise ValueError("boom")


@pytest.fixture
def factory(engine):
    f = sessionmaker(engine, expire_on_commit=False)
    yield f
    with f() as s:
        s.execute(delete(Task).where(Task.kind.like("test_%")))
        s.commit()


def test_a_queued_task_runs_once_and_keeps_its_result(factory):
    with factory() as s:
        t = tasks.enqueue(s, None, "test_ok", {"x": 7})
        s.commit()
        tid = t.id
    before = calls["ok"]
    assert tasks.drain(factory) >= 1
    with factory() as s:
        t = s.get(Task, tid)
        assert (t.status, t.result, t.attempts) == ("done", {"echo": 7}, 1)
    assert calls["ok"] == before + 1


def test_a_failing_task_retries_with_backoff_then_stops_with_its_error(factory):
    with factory() as s:
        t = tasks.enqueue(s, None, "test_always_fails", {}, max_attempts=2)
        s.commit()
        tid = t.id
    tasks.run_one(factory)
    with factory() as s:
        t = s.get(Task, tid)
        assert t.status == "queued" and t.attempts == 1 and "boom" in t.error
        t.run_after = t.created_at  # skip the backoff wait
        s.commit()
    tasks.run_one(factory)
    with factory() as s:
        t = s.get(Task, tid)
        assert (t.status, t.attempts) == ("failed", 2) and "ValueError: boom" in t.error


def test_an_equal_task_still_waiting_is_not_queued_twice(factory):
    with factory() as s:
        a = tasks.enqueue(s, None, "test_ok", {}, dedupe_key="test-dedupe")
        b = tasks.enqueue(s, None, "test_ok", {}, dedupe_key="test-dedupe")
        s.commit()
        assert a.id == b.id


def test_two_workers_never_take_the_same_task(factory):
    with factory() as s:
        tasks.enqueue(s, None, "test_ok", {})
        s.commit()
    s1, s2 = factory(), factory()
    first = tasks.claim(s1, "w1")
    second = tasks.claim(s2, "w2")
    assert first is not None and (second is None or second.id != first.id)
    s1.close(); s2.close()


def test_a_cv_uploaded_in_the_background_is_read_by_a_task(client, fake, session, tmp_path, monkeypatch):
    job = make_job(client)
    r = client.post(f"/v1/jobs/{job}/documents", params={"background": "true"}, files=pdf_file(CV_LINES, "bg.pdf"))
    assert r.status_code == 202 and r.json()["status"] == "queued"
    task = session.get(Task, uuid.UUID(r.json()["task_id"]))
    monkeypatch.setattr(task_handlers, "llm_factory", lambda: fake)
    from maindscout.api import app as api
    monkeypatch.setattr(task_handlers, "blob_factory", api.app.dependency_overrides[api.get_blobs])
    result = tasks.execute(session, task)
    assert result["band"] == "do_not_submit" and result["status"] == "committed"
    status = client.get("/v1/tasks", params={"ids": str(task.id)}).json()
    assert status[0]["kind"] == "process_document"


def test_every_read_is_in_the_cost_ledger(client, fake, session):
    job = make_job(client)
    drop_cv(client, job)
    purposes = sorted(session.scalars(select(CostEntry.purpose)))
    assert purposes == ["read_cv", "read_jd"]
    summary = client.get("/v1/costs").json()
    assert {p["purpose"] for p in summary["by_purpose"]} == {"read_cv", "read_jd"} and "budget_usd" in summary


def test_paid_work_stops_when_the_monthly_budget_is_reached(client, fake, session, monkeypatch):
    monkeypatch.setenv("MONTHLY_BUDGET_USD", "0")
    r = client.post("/v1/jobs", files=pdf_file(["x"] * 9, "jd.pdf"))
    assert r.status_code == 402 and "budget" in r.json()["detail"].lower()


def test_erasure_keeps_the_numbers_but_unlinks_the_person(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    before = session.scalar(select(func.count()).select_from(CostEntry))
    r = client.post(f"/v1/subjects/candidate/{cid}/erase", json={}).json()
    assert r["clean"] and r["counts"]["cost_entries_unlinked"] >= 1
    assert session.scalar(select(func.count()).select_from(CostEntry)) == before


@tasks.handler("test_pays_then_fails")
def _pays(session, task):
    from maindscout.api import costs

    costs.record(session, None, "test_paid", {"model": "m", "usd": 0.01}, task_id=task.id)
    raise RuntimeError("after paying")


def test_a_paid_call_stays_in_the_ledger_when_its_task_fails_afterwards(factory):
    with factory() as s:
        t = tasks.enqueue(s, None, "test_pays_then_fails", {}, max_attempts=1)
        s.commit()
        tid = t.id
    tasks.run_one(factory)
    with factory() as s:
        rows = s.scalars(select(CostEntry).where(CostEntry.task_id == tid)).all()
        assert [(r.purpose, float(r.usd)) for r in rows] == [("test_paid", 0.01)]
        assert s.get(Task, tid).status == "failed"
        s.execute(delete(CostEntry).where(CostEntry.task_id == tid))
        s.commit()
