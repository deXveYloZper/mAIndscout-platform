"""Slice 2: the sourcing feeder (desk adapter)."""

from tests.test_api import RoutingFake, client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES, cv_json


class _Reply:
    def __init__(self, status_code, body):
        self.status_code, self._body = status_code, body

    def json(self):
        return self._body


def campaign(session, client, job, json=None):
    """The pool matching every sourcing run starts with. Its endpoint (a search of the desk by hand) was removed as a
    duplicate of the sourcing run (x-ray B4, 2026-10-13); the matching itself is what these tests check."""
    import uuid

    from maindscout.api import sourcing

    body = json or {}
    try:
        c = sourcing.start(session, uuid.UUID(client.headers["X-Org-Id"]), uuid.UUID(job), "test", body.get("source", "auto"),
                           body.get("cap", sourcing.DEFAULT_CAP), body.get("target", sourcing.DEFAULT_TARGET))
    except sourcing.SourcingError as error:
        return _Reply(422, {"detail": str(error)})
    session.flush()
    return _Reply(201, sourcing.as_dict(c))


def pool_person(client, fake, name, email, skills):
    """Read a CV into the pool (no job) for a distinct person with the given skills."""
    fake.cv = cv_json(full_name={"value": name, "quote": "JANE EXAMPLE"},
                      contacts=[{"kind": "email", "value": email, "quote": "jane.example@example.com"}],
                      skills=[{"label": s, "normalized": s, "quote": "Skills: Rust, C++, React"} for s in skills])
    r = client.post("/v1/candidates", files=pdf_file(CV_LINES + [email], f"{email}.pdf"))
    assert r.status_code == 201, r.text
    return r.json()["subject_id"]


def test_a_thin_queue_is_refilled_from_the_desk_through_the_same_triage(client, fake, session):
    job = make_job(client)  # distinctive must-have: insar
    specialist = pool_person(client, fake, "Ana Radar", "jane.example@example.com", ["insar", "python"])
    r = campaign(session, client, job, json={"cap": 10, "target": 5})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["query"] == {"tokens": ["insar"]} and c["source"] == "desk"
    assert c["added"] == 1 and c["priority_added"] == 1 and c["status"] == "exhausted"
    page = client.get(f"/v1/jobs/{job}/people/{specialist}/gaps").json()
    assert page["band"] == "priority" and page["reason"] == "supported:insar"
    assert page["history"][0]["cause"]["act"] == "sourced"


def test_distinctive_tokens_do_not_pull_software_generalists_in(client, fake, session):
    job = make_job(client)
    generalist = pool_person(client, fake, "Gen Eral", "jane.example@example.com", ["python", "react", "typescript"])
    c = campaign(session, client, job, json={}).json()
    assert c["added"] == 0 and c["status"] == "exhausted"
    assert generalist not in [p["candidate_id"] for band in client.get(f"/v1/jobs/{job}").json()["people"].values() for p in band]


def test_a_campaign_stops_at_its_cap(client, fake, session):
    job = make_job(client)
    for i in range(3):
        pool_person(client, fake, f"Radar {i}", f"radar{i}@example.com", ["insar"])
    c = campaign(session, client, job, json={"cap": 2, "target": 10}).json()
    assert (c["spent"], c["added"], c["status"], c["stop_reason"]) == (2, 2, "stopped", "cap")


def test_a_campaign_stops_once_priority_reaches_the_target(client, fake, session):
    job = make_job(client)
    for i in range(3):
        pool_person(client, fake, f"Radar {i}", f"radar{i}@example.com", ["insar"])
    c = campaign(session, client, job, json={"cap": 10, "target": 2}).json()
    assert (c["added"], c["stop_reason"]) == (2, "target_reached")
    again = campaign(session, client, job, json={"target": 2})
    assert again.status_code == 422 and "thin queue" in again.json()["detail"]


def test_a_sourced_person_is_handled_exactly_like_an_uploaded_one(client, fake, session):
    job = make_job(client)
    uploaded = drop_cv(client, job)["subject_id"]  # Jane, do_not_submit on this job
    sourced = pool_person(client, fake, "Bo Radar", "bo@example.com", ["insar"])
    campaign(session, client, job, json={})
    a = client.get(f"/v1/jobs/{job}/people/{uploaded}/gaps").json()
    b = client.get(f"/v1/jobs/{job}/people/{sourced}/gaps").json()
    assert set(a) == set(b), "same shape of record"
    assert [r["requirement"] for r in a["rows"]] == [r["requirement"] for r in b["rows"]]
    # Typing the missing skill moves the uploaded person exactly as it would a sourced one.
    client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": uploaded, "claim_type": "SkillClaim",
                                    "payload": {"raw_label": "InSAR", "normalized_skill": "insar"}})
    assert client.get(f"/v1/jobs/{job}/people/{uploaded}/gaps").json()["band"] == b["band"] == "priority"


def test_a_job_without_must_have_skills_cannot_be_sourced(client, fake, session):
    fake.jd = {**fake.jd, "requirements": []}
    job = make_job(client)
    r = campaign(session, client, job, json={})
    assert r.status_code == 422 and "no must-have skills" in r.json()["detail"]


def test_there_is_no_mail_or_send_path_anywhere():
    from maindscout.api.app import app
    paths = [getattr(r, "path", "") for r in app.routes]
    # Slice 4 step 5 drafts messages and puts them in the recruiter's own mailbox drafts; nothing here can send one.
    assert not [p for p in paths if any(w in p.lower() for w in ("send", "outreach", "deliver", "smtp"))]
    import inspect

    from maindscout.api import mailbox
    source = inspect.getsource(mailbox)
    assert "messages/send" not in source and "/sendMail" not in source and "/send" not in source, "the mailbox never sends"
