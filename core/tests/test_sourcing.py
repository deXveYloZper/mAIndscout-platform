"""The pool step of every sourcing run: the desk's own people first, found by the role's distinctive skills (or its
hiring profile) and put on the role through the same pairing and matching as an uploaded CV. Through
`autosource.run` with no web client, the way the desk runs it (the old Slice 2 campaign wrapper is gone, 2026-10-19)."""

import uuid

from sqlalchemy import select

from maindscout.api import autosource
from maindscout.db.models import CandidateJob, Job, SourcingHit
from tests.test_api import RoutingFake, client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_autosource import blobs  # noqa: F401
from tests.test_process import CV_LINES, cv_json


def pool_person(client, fake, name, email, skills):
    """Read a CV into the pool (no job) for a distinct person with the given skills."""
    fake.cv = cv_json(full_name={"value": name, "quote": "JANE EXAMPLE"},
                      contacts=[{"kind": "email", "value": email, "quote": "jane.example@example.com"}],
                      skills=[{"label": s, "normalized": s, "quote": "Skills: Rust, C++, React"} for s in skills])
    r = client.post("/v1/candidates", files=pdf_file(CV_LINES + [email], f"{email}.pdf"))
    assert r.status_code == 201, r.text
    return r.json()["subject_id"]


def pool_run(session, job_id, blobs):
    """A sourcing run with no web client: the pool step only."""
    job = session.get(Job, uuid.UUID(job_id))
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly")
    return autosource.run(session, blobs, job.org_id, job.id, "manual", None)


def on_role(session, job_id):
    return {str(p.candidate_id): p for p in session.scalars(select(CandidateJob).where(CandidateJob.job_id == uuid.UUID(job_id)))}


def test_the_pool_step_finds_a_specialist_by_the_roles_distinctive_skill(client, fake, session, blobs):
    job = make_job(client)  # distinctive must-have: insar
    specialist = pool_person(client, fake, "Ana Radar", "jane.example@example.com", ["insar", "python"])
    run = pool_run(session, job, blobs)
    assert (run.status, run.stop_reason) == ("done", "pool_only") and run.report["pool"]["added"] == 1
    page = client.get(f"/v1/jobs/{job}/people/{specialist}/gaps").json()
    assert page["band"] == "priority" and page["reason"] == "supported:insar"
    assert page["history"][0]["cause"]["act"] == "sourced"
    hit = session.scalar(select(SourcingHit).where(SourcingHit.candidate_id == uuid.UUID(specialist)))
    assert hit.channel == "pool" and hit.new_to_desk is False


def test_distinctive_skills_do_not_pull_software_generalists_in(client, fake, session, blobs):
    job = make_job(client)
    generalist = pool_person(client, fake, "Gen Eral", "jane.example@example.com", ["python", "react", "typescript"])
    run = pool_run(session, job, blobs)
    assert run.report["pool"]["added"] == 0 and generalist not in on_role(session, job)


def test_a_person_found_in_the_pool_is_handled_exactly_like_an_uploaded_one(client, fake, session, blobs):
    job = make_job(client)
    uploaded = drop_cv(client, job)["subject_id"]  # Jane, do_not_submit on this job
    sourced = pool_person(client, fake, "Bo Radar", "bo@example.com", ["insar"])
    pool_run(session, job, blobs)
    a = client.get(f"/v1/jobs/{job}/people/{uploaded}/gaps").json()
    b = client.get(f"/v1/jobs/{job}/people/{sourced}/gaps").json()
    assert set(a) == set(b), "same shape of record"
    assert [r["requirement"] for r in a["rows"]] == [r["requirement"] for r in b["rows"]]
    # Typing the missing skill moves the uploaded person exactly as it would a sourced one.
    client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": uploaded, "claim_type": "SkillClaim",
                                    "payload": {"raw_label": "InSAR", "normalized_skill": "insar"}})
    assert client.get(f"/v1/jobs/{job}/people/{uploaded}/gaps").json()["band"] == b["band"] == "priority"


def test_there_is_no_mail_or_send_path_anywhere():
    from maindscout.api.app import app
    paths = [getattr(r, "path", "") for r in app.routes]
    # Slice 4 step 5 drafts messages and puts them in the recruiter's own mailbox drafts; nothing here can send one.
    assert not [p for p in paths if any(w in p.lower() for w in ("send", "outreach", "deliver", "smtp"))]
    import inspect

    from maindscout.api import mailbox
    source = inspect.getsource(mailbox)
    assert "messages/send" not in source and "/sendMail" not in source and "/send" not in source, "the mailbox never sends"
