"""Fixes from the architecture review (2026-10-28): no route holds up the others while it reads an ad; every button has
its words in the activity log, a refusal says why, and a change to a requirement is logged under its role; the clocks
say when they fail; two-step codes can be turned off from the Account page. Nothing spent."""

import inspect
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from maindscout import __main__ as cli
from maindscout import activity
from maindscout.api import app as api
from maindscout.api import buttons
from maindscout.db.models import Claim, DeskLog
from tests.conftest import PASSWORD
from tests.test_access import as_user, bare
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)


@pytest.fixture
def log_rows():
    """Lines the log wrote during the test (it writes in its own transaction), removed afterwards."""
    since = datetime.now(timezone.utc) - timedelta(seconds=1)

    def read(**where):
        with activity._factory()() as s:
            stmt = select(DeskLog).where(DeskLog.at >= since)
            for k, v in where.items():
                stmt = stmt.where(getattr(DeskLog, k) == v)
            return list(s.scalars(stmt.order_by(DeskLog.at)))
    yield read
    with activity._factory()() as s:
        s.execute(DeskLog.__table__.delete().where(DeskLog.at >= since))
        s.commit()


def _writes():
    return [(m, re.sub(r"\{[^}]+\}", "{}", r.path)) for r in api.app.routes for m in (getattr(r, "methods", None) or ())
            if m in ("POST", "PUT", "PATCH", "DELETE") and not r.path.startswith(buttons.QUIET)]


def test_no_route_holds_up_the_others():
    """An `async def` route runs on the server's one event loop: reading an ad with the model there (5 to 15 seconds)
    stopped every other page. Plain `def` routes run in the thread pool."""
    held = [r.path for r in api.app.routes if r.path.startswith("/v1/") and inspect.iscoroutinefunction(r.endpoint)]
    assert held == []


def test_every_button_has_its_words_in_the_log():
    assert [w for w in _writes() if w not in buttons.ACTIONS] == [], "a write route the log would show as its route"
    assert [k for k in buttons.ACTIONS if k not in _writes()] == [], "words for a route that is gone"


def test_a_refusal_says_why_in_the_log(client, org, log_rows):
    assert client.post(f"/v1/candidates/{uuid.uuid4()}/transcripts", data={"text": " "}).status_code == 422
    missing = uuid.uuid4()
    assert client.post(f"/v1/requirements/{missing}/strength", json={"strength": "must"}).status_code == 404
    rows = [r for r in log_rows(org_id=org.id) if "refused" in r.summary]
    assert rows[0].summary == "Added a call transcript (refused: 422: Send a transcript file or paste the text)"
    assert rows[0].level == "warn" and rows[0].detail["reason"] == "Send a transcript file or paste the text"
    assert rows[1].summary.startswith("Changed must / nice of a requirement (refused: 404: ") and str(missing) in rows[1].summary


def test_a_change_to_a_requirement_is_logged_under_its_role(client, session, org, log_rows, monkeypatch):
    job_id = make_job(client)
    r = client.post(f"/v1/jobs/{job_id}/requirements", json={"category": "domain", "strength": "strong_plus",
                                                              "text_raw": "Fintech experience", "domains": ["fintech"]})
    claim_id = r.json()["id"]
    assert api._role_of_line(claim_id, session) == job_id
    person = Claim(org_id=org.id, subject_type="candidate", subject_id=uuid.uuid4(), claim_type="IdentityClaim", status="approved",
                   payload={"full_name": "Una Testperson"}, natural_key=f"{uuid.uuid4()}|identity")
    session.add(person)
    session.flush()
    assert api._role_of_line(str(person.id), session) is None, "a fact about a person has no role"
    assert api._role_of_line(str(uuid.uuid4()), session) is None
    role_of = api._role_of_line  # the log reads with its own connection; the test's data is in the test's transaction
    monkeypatch.setattr(api, "_role_of_line", lambda line: role_of(line, session))
    assert client.post(f"/v1/requirements/{claim_id}/strength", json={"strength": "must"}).status_code == 200
    row = next(r for r in log_rows(org_id=org.id) if r.summary == "Changed must / nice of a requirement")
    assert str(row.job_id) == job_id


def test_a_clock_says_once_when_it_fails_and_when_it_works_again(log_rows):
    def boom():
        raise RuntimeError("the database is away")

    failed = cli._tick("test clock", boom, None)
    assert failed == "RuntimeError: the database is away"
    assert cli._tick("test clock", boom, failed) == failed, "the same failure"
    assert cli._tick("test clock", lambda: None, failed) is None
    rows = [r for r in log_rows() if "test clock" in r.summary]
    assert [(r.level, r.summary) for r in rows] == [("error", "The test clock failed: it tries again at its next tick"),
                                                    ("info", "The test clock works again")], "once each, not every tick"
    assert "the database is away" in rows[0].detail["error"]


def test_two_step_codes_can_be_turned_off_unless_owners_must_keep_them(client, monkeypatch):
    token = client.headers["Authorization"].removeprefix("Bearer ")
    me = bare().get("/v1/auth/me", headers=as_user(token)).json()
    assert me["two_step"] is True and me["two_step_required"] is False, "the Account page shows Turn off"
    monkeypatch.setenv("OWNER_TWO_STEP", "required")
    assert bare().get("/v1/auth/me", headers=as_user(token)).json()["two_step_required"] is True, "it says owners keep it on"
    monkeypatch.setenv("OWNER_TWO_STEP", "optional")
    assert bare().post("/v1/auth/two-step/disable", headers=as_user(token), json={"password": "wrong one"}).status_code == 422
    assert bare().post("/v1/auth/two-step/disable", headers=as_user(token), json={"password": PASSWORD}).status_code == 204
    assert bare().get("/v1/auth/me", headers=as_user(token)).json()["two_step"] is False
