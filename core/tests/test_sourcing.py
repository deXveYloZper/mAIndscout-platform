"""Slice 2: the sourcing feeder (desk adapter)."""

from tests.test_api import RoutingFake, client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES, cv_json


def pool_person(client, fake, name, email, skills):
    """Read a CV into the pool (no job) for a distinct person with the given skills."""
    fake.cv = cv_json(full_name={"value": name, "quote": "JANE EXAMPLE"},
                      contacts=[{"kind": "email", "value": email, "quote": "jane.example@example.com"}],
                      skills=[{"label": s, "normalized": s, "quote": "Skills: Rust, C++, React"} for s in skills])
    r = client.post("/v1/candidates", files=pdf_file(CV_LINES + [email], f"{email}.pdf"))
    assert r.status_code == 201, r.text
    return r.json()["subject_id"]


def test_a_thin_queue_is_refilled_from_the_desk_through_the_same_triage(client, fake):
    job = make_job(client)  # distinctive must-have: insar
    specialist = pool_person(client, fake, "Ana Radar", "jane.example@example.com", ["insar", "python"])
    r = client.post(f"/v1/jobs/{job}/campaigns", json={"cap": 10, "target": 5})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["query"] == {"tokens": ["insar"]} and c["source"] == "desk"
    assert c["added"] == 1 and c["priority_added"] == 1 and c["status"] == "exhausted"
    page = client.get(f"/v1/jobs/{job}/people/{specialist}/gaps").json()
    assert page["band"] == "priority" and page["reason"] == "supported:insar"
    assert page["history"][0]["cause"]["act"] == "sourced"


def test_distinctive_tokens_do_not_pull_software_generalists_in(client, fake):
    job = make_job(client)
    generalist = pool_person(client, fake, "Gen Eral", "jane.example@example.com", ["python", "react", "typescript"])
    c = client.post(f"/v1/jobs/{job}/campaigns", json={}).json()
    assert c["added"] == 0 and c["status"] == "exhausted"
    assert generalist not in [p["candidate_id"] for band in client.get(f"/v1/jobs/{job}").json()["people"].values() for p in band]


def test_a_campaign_stops_at_its_cap(client, fake):
    job = make_job(client)
    for i in range(3):
        pool_person(client, fake, f"Radar {i}", f"radar{i}@example.com", ["insar"])
    c = client.post(f"/v1/jobs/{job}/campaigns", json={"cap": 2, "target": 10}).json()
    assert (c["spent"], c["added"], c["status"], c["stop_reason"]) == (2, 2, "stopped", "cap")


def test_a_campaign_stops_once_priority_reaches_the_target(client, fake):
    job = make_job(client)
    for i in range(3):
        pool_person(client, fake, f"Radar {i}", f"radar{i}@example.com", ["insar"])
    c = client.post(f"/v1/jobs/{job}/campaigns", json={"cap": 10, "target": 2}).json()
    assert (c["added"], c["stop_reason"]) == (2, "target_reached")
    again = client.post(f"/v1/jobs/{job}/campaigns", json={"target": 2})
    assert again.status_code == 422 and "thin queue" in again.json()["detail"]


def test_a_sourced_person_is_handled_exactly_like_an_uploaded_one(client, fake):
    job = make_job(client)
    uploaded = drop_cv(client, job)["subject_id"]  # Jane, do_not_submit on this job
    sourced = pool_person(client, fake, "Bo Radar", "bo@example.com", ["insar"])
    client.post(f"/v1/jobs/{job}/campaigns", json={})
    a = client.get(f"/v1/jobs/{job}/people/{uploaded}/gaps").json()
    b = client.get(f"/v1/jobs/{job}/people/{sourced}/gaps").json()
    assert set(a) == set(b), "same shape of record"
    assert [r["requirement"] for r in a["rows"]] == [r["requirement"] for r in b["rows"]]
    # Typing the missing skill moves the uploaded person exactly as it would a sourced one.
    client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": uploaded, "claim_type": "SkillClaim",
                                    "payload": {"raw_label": "InSAR", "normalized_skill": "insar"}})
    assert client.get(f"/v1/jobs/{job}/people/{uploaded}/gaps").json()["band"] == b["band"] == "priority"


def test_a_running_campaign_can_be_stopped_and_listed(client, fake):
    job = make_job(client)
    c = client.post(f"/v1/jobs/{job}/campaigns", json={"cap": 1}).json()
    stopped = client.post(f"/v1/campaigns/{c['id']}/stop").json()
    assert stopped["status"] in ("stopped", "exhausted")
    listing = client.get(f"/v1/jobs/{job}/campaigns").json()
    assert listing["campaigns"][0]["id"] == c["id"] and listing["default_target"] == 5


def test_a_job_without_must_have_skills_cannot_be_sourced(client, fake):
    fake.jd = {**fake.jd, "requirements": []}
    job = make_job(client)
    r = client.post(f"/v1/jobs/{job}/campaigns", json={})
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
