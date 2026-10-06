"""Same person: two records made one on a human's word, everything moved, undoable, erased together."""

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from maindscout.db.models import BriefItem, Candidate, CandidateJob, Claim, Decision, NotSame, PairEvent, PersonMerge
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES, cv_json


def session_of(client):
    from maindscout.api import app as api

    return api.app.dependency_overrides[api.get_session]()


def two_janes(client, fake):
    """The same Jane read twice onto one job, with no contact in common: a "Who is this?" card."""
    job = make_job(client)
    fake.cv = cv_json(contacts=[])
    first = drop_cv(client, job, CV_LINES + ["a"], "a.pdf")["subject_id"]
    second = drop_cv(client, job, CV_LINES + ["b"], "b.pdf")["subject_id"]
    assert first != second
    # One test transaction gives both the same timestamp; in real use the second CV arrives later.
    later = session_of(client)
    later.get(Candidate, uuid.UUID(second)).created_at += timedelta(seconds=1)
    later.flush()
    return job, first, second


def note(session, cid):
    return session.scalar(select(Decision).where(Decision.type == "identity_note", Decision.subject_id == uuid.UUID(cid)))


def live_facts(session, cid, claim_type):
    return session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == claim_type,
                                               Claim.status.in_(("proposed", "approved")))).all()


def test_same_person_merge_moves_everything_onto_the_older_record(client, fake, session):
    job, first, second = two_janes(client, fake)
    card = note(session, second)
    assert card is not None and card.sealed_at is None
    client.get(f"/v1/jobs/{job}/people/{second}/brief", params={"force": "true"})
    events_before = session.scalar(select(func.count()).select_from(PairEvent))
    r = client.post(f"/v1/candidates/{second}/merge", json={"other_id": first})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["keep_id"] == first and m["drop_id"] == second, "the older record is kept, whichever page asked"

    session.expire_all()
    assert session.get(Candidate, uuid.UUID(second)).merged_into_id == uuid.UUID(first)
    assert len(live_facts(session, second, "SkillClaim")) == 0
    names = live_facts(session, first, "IdentityClaim")
    assert len(names) == 1, "a fact both records had is kept once"
    pairs = session.scalars(select(CandidateJob).where(CandidateJob.job_id == uuid.UUID(job))).all()
    assert [p.candidate_id for p in pairs] == [uuid.UUID(first)], "one person on the job, not two"
    assert session.scalar(select(func.count()).select_from(PairEvent)) >= events_before, "no history lost"
    assert session.scalars(select(BriefItem).where(BriefItem.candidate_id == uuid.UUID(second))).all() == []
    assert session.get(Decision, card.id).sealed_at is not None, "the question is answered"
    people = [p["id"] for p in client.get("/v1/candidates").json()]
    assert second not in people and first in people
    page = client.get(f"/v1/candidates/{second}").json()
    assert page["merged_into"] == first
    assert client.get(f"/v1/candidates/{first}").json()["merges"][0]["id"] == m["id"]
    assert client.post(f"/v1/candidates/{second}/merge", json={"other_id": first}).status_code == 422, "once"


def test_a_merge_can_be_undone(client, fake, session):
    job, first, second = two_janes(client, fake)
    card = note(session, second)
    before = {cid: sorted(str(c.id) for c in live_facts(session, cid, "SkillClaim")) for cid in (first, second)}
    m = client.post(f"/v1/candidates/{first}/merge", json={"other_id": second}).json()
    r = client.post(f"/v1/merges/{m['id']}/undo")
    assert r.status_code == 200, r.text
    session.expire_all()
    assert session.get(Candidate, uuid.UUID(second)).merged_into_id is None
    assert {cid: sorted(str(c.id) for c in live_facts(session, cid, "SkillClaim")) for cid in (first, second)} == before
    pairs = session.scalars(select(CandidateJob).where(CandidateJob.job_id == uuid.UUID(job))).all()
    assert sorted(str(p.candidate_id) for p in pairs) == sorted([first, second]), "both on the job again"
    card = session.get(Decision, card.id)
    assert card.sealed_at is None and card.subject_id == uuid.UUID(second), "the question is open again, about them"
    assert client.post(f"/v1/merges/{m['id']}/undo").status_code == 422


def test_different_people_is_remembered_and_blocks_a_later_merge(client, fake, session):
    job, first, second = two_janes(client, fake)
    r = client.post(f"/v1/decisions/{note(session, second).id}/resolve", json={"action": "different"})
    assert r.status_code == 200, r.text
    assert session.scalar(select(func.count()).select_from(NotSame)) == 1
    r = client.post(f"/v1/candidates/{first}/merge", json={"other_id": second})
    assert r.status_code == 422 and "different people" in r.json()["detail"]


def test_erasing_a_merged_person_erases_both_records(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job, first, second = two_janes(client, fake)
    client.post(f"/v1/candidates/{first}/merge", json={"other_id": second})
    assert client.post(f"/v1/subjects/candidate/{first}/erase", json={"reason": "request"}).status_code == 200
    session.expire_all()
    assert session.get(Candidate, uuid.UUID(first)) is None and session.get(Candidate, uuid.UUID(second)) is None
    assert session.scalar(select(func.count()).select_from(PersonMerge)) == 0
    assert client.get(f"/v1/subjects/candidate/{first}/erase/verify").json()["clean"] is True
