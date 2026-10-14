"""Phase 1c (docs/next/PLAN.md section 4c): suggestions stay suggestions until the owner decides; one-click triage with
undo; the contact track (contacted, follow-up, reply, call); a reach is shown as a reach; LinkedIn's notification emails
read from a fake mailbox, only for people contacted on LinkedIn."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from maindscout.api import autosource, mailbox, messages, outreach
from maindscout.db.models import Activity, CandidateJob, Job, Mailbox, Message
from tests.test_api import client, fake  # noqa: F401 (fixtures)
from tests.test_autosource import ADA, BEN, MUNICH, FakeExa, blobs, go, job, person_named, profile  # noqa: F401 (fixtures)

HAL = profile("hal-testperson-demo", "Hal Testperson", "Head of Engineering", MUNICH, "DE",
              [("Head of Engineering", "Orbital Testworks", "Jan 2022", "Present", "2022-01-01", None)], skills=["insar", "python"])


def pair_of(session, job, cid):
    return session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == cid))


def found(session, job, blobs, people=None):
    go(session, job, FakeExa(people=people) if people is not None else FakeExa(), blobs)
    session.commit()
    return person_named(session, "Ada Testperson")


# --- F1, F2, F3: suggestions, one-click decisions, undo --------------------------------------------------------------


def test_a_suggestion_stays_off_the_roles_bands_until_the_owner_chooses(client, session, job, blobs):
    ada = found(session, job, blobs)
    assert pair_of(session, job, ada).triage_band == "priority", "the machine rates her strong"
    role = client.get(f"/v1/jobs/{job.id}").json()
    assert all(p["candidate_id"] != str(ada) for b in role["people"].values() for p in b), "a public profile alone is not Priority"
    assert role["suggestions_waiting"] == 1, "Ben (rated do not submit) stays in his band"
    listed = next(j for j in client.get("/v1/jobs").json() if j["id"] == str(job.id))
    assert listed["bands"]["priority"] == 0 and listed["suggestions"] == 1
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    card = next(s for s in page["suggestions"] if s["candidate_id"] == str(ada))
    assert (card["stage"], card["hint"], card["reach"]) == ("to_review", "looks strong", None)
    assert page["counts"]["to_review"] == 1

    assert client.post(f"/v1/jobs/{job.id}/people/{ada}/viewed").json()["state"] == "seen"
    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/decide", json={"choice": "reach_out"}).json()
    assert (r["stage"], r["band"]) == ("to_contact", "priority")
    role = client.get(f"/v1/jobs/{job.id}").json()
    assert [p["candidate_id"] for p in role["people"]["priority"]] == [str(ada)], "Priority by the owner's hand"
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    assert [s["name"] for s in page["lists"]["to_contact"]] == ["Ada Testperson"] and page["counts"]["to_review"] == 0

    reason = pair_of(session, job, ada).contact["machine"]["reason"]
    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/undo").json()
    assert (r["stage"], r["band"]) == ("to_review", "priority")
    session.expire_all()
    pair = pair_of(session, job, ada)
    assert pair.band_overridden_by is None and pair.triage_reason == reason, "undo gives back the machine's own reading"
    assert client.get(f"/v1/jobs/{job.id}").json()["suggestions_waiting"] == 1

    assert client.post(f"/v1/jobs/{job.id}/people/{ada}/decide", json={"choice": "pass"}).status_code == 422, "a pass says why"
    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/decide", json={"choice": "pass", "reason": "level"}).json()
    assert (r["stage"], r["state"]) == ("passed", "we_passed")
    session.expire_all()
    assert pair_of(session, job, ada).outcome["reason"] == "seniority", "the reason teaches the desk the owner's taste"
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    assert page["lists"]["passed"][0]["name"] == "Ada Testperson", "the latest pass is first, easy to undo"
    assert client.post(f"/v1/jobs/{job.id}/people/{ada}/undo").json()["stage"] == "to_review"
    ben = person_named(session, "Ben Testperson")
    r = client.post(f"/v1/jobs/{job.id}/people/{ben}/decide", json={"choice": "later"}).json()
    assert (r["stage"], r["band"]) == ("later", "review_later")


# --- F4: the contact track -------------------------------------------------------------------------------------------


def test_contacted_then_a_follow_up_is_due_then_a_reply_and_a_call(client, session, job, blobs):
    ada = found(session, job, blobs)
    client.post(f"/v1/jobs/{job.id}/people/{ada}/decide", json={"choice": "reach_out"})
    assert client.post(f"/v1/jobs/{job.id}/people/{ada}/contacted", json={"channel": "fax"}).status_code == 422
    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/contacted", json={"channel": "linkedin_invite"}).json()
    assert (r["stage"], r["state"], r["contact"]["channel"]) == ("contacted", "contacted", "linkedin_invite")
    m = session.scalar(select(Message).where(Message.candidate_id == ada, Message.kind == "candidate_outreach"))
    assert m.status == "sent" and m.provider == "linkedin" and m.to_address.endswith("ada-testperson-demo")
    assert timedelta(days=3, hours=23) < m.follow_up_due - m.sent_at <= timedelta(days=4), "follow up after 4 days"
    assert client.post(f"/v1/jobs/{job.id}/people/{ada}/undo").status_code == 422, "contacted is not undone from here"
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    assert page["lists"]["contacted"][0]["follow_up_due"] is False and page["follow_ups_due"] == 0
    m.follow_up_due = datetime.now(timezone.utc) - timedelta(hours=1)  # four days later, no reply
    session.commit()
    assert client.get(f"/v1/jobs/{job.id}/sourcing").json()["follow_ups_due"] == 1
    from maindscout.api import messages

    messages.due_follow_ups(session, job.org_id)  # the clock drafts it (a LinkedIn follow-up: a draft to copy)
    session.commit()
    card = client.get(f"/v1/jobs/{job.id}/sourcing").json()["lists"]["contacted"][0]
    assert card["follow_up"]["drafted"] and card["follow_up_due"] is False, "drafted: waiting for you to send it, no longer due"

    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/replied", json={"outcome": "interested", "text": "Happy to talk"}).json()
    assert r["stage"] == "replied" and r["contact"]["reply"]["outcome"] == "interested"
    session.expire_all()
    assert session.get(Message, m.id).status == "replied" and session.get(Message, m.id).follow_up_due is None, "a reply stops follow-ups"
    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/call-booked", json={"when": "2026-10-20T10:00:00+00:00"}).json()
    assert r["stage"] == "call_booked"
    timeline = [a.summary for a in session.scalars(select(Activity).where(Activity.subject_id == ada))]
    assert any(t.startswith("Replied: interested") for t in timeline) and any(t.startswith("Call booked for 20 Oct 2026") for t in timeline)


def test_not_now_goes_back_to_the_pool_with_a_date_and_stop_is_final(client, session, job, blobs):
    ada = found(session, job, blobs)
    ben = person_named(session, "Ben Testperson")
    for cid in (ada, ben):
        client.post(f"/v1/jobs/{job.id}/people/{cid}/decide", json={"choice": "reach_out"})
        client.post(f"/v1/jobs/{job.id}/people/{cid}/contacted", json={"channel": "email"})
    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/replied", json={"outcome": "not_now", "check_back": "2027-01-15"}).json()
    assert r["state"] == "we_passed" and r["contact"]["reply"]["check_back"] == "2027-01-15"
    session.expire_all()
    assert pair_of(session, job, ada).outcome["reason"] == "candidate_not_interested"
    client.post(f"/v1/jobs/{job.id}/people/{ben}/replied", json={"outcome": "stop", "note": "no thanks"})
    assert client.get(f"/v1/candidates/{ben}").json()["do_not_contact"]["note"] == "no thanks"
    assert client.post(f"/v1/jobs/{job.id}/people/{ben}/contacted", json={"channel": "email"}).status_code == 422


# --- F5: a reach -----------------------------------------------------------------------------------------------------


def test_a_head_of_engineering_is_a_reach_for_a_hands_on_role(client, session, job, blobs):
    found(session, job, blobs, [ADA, HAL])
    hal = person_named(session, "Hal Testperson")
    why = outreach.reach(session, job.org_id, hal, job)
    assert why.startswith("Head of Engineering now") and "hands-on" in why
    assert outreach.reach(session, job.org_id, person_named(session, "Ada Testperson"), job) is None
    card = next(s for s in client.get(f"/v1/jobs/{job.id}/sourcing").json()["suggestions"] if s["name"] == "Hal Testperson")
    assert card["reach"] == why, "shown as a reach, never blocked"
    lead = Job(org_id=job.org_id, title="Head of Engineering", state="open")
    session.add(lead)
    session.flush()
    assert outreach.reach(session, job.org_id, hal, lead) is None, "a Head of Engineering post is its own job spec"

    p = pair_of(session, job, hal)
    p.triage_band = "priority"
    session.commit()
    before = autosource.strong_waiting(session, job.id)
    client.post(f"/v1/jobs/{job.id}/people/{hal}/decide", json={"choice": "reach_out"})
    assert autosource.strong_waiting(session, job.id) == before + 1, "a reach counts once the owner chooses them"


# --- F6: LinkedIn's emails, from a fake mailbox ------------------------------------------------------------------------


class FakeInbox:
    """Gmail / Outlook with LinkedIn's notifications. Records the names it was asked about: nothing else is searched."""

    def __init__(self, mails):
        self.mails, self.asked = mails, []

    def draft_state(self, did, tid):
        return {"state": "draft"}

    def replies_since(self, tid, since, own):
        return []

    def delete_draft(self, did):
        pass

    def linkedin_mail(self, names, since):
        self.asked.append(list(names))
        return [m for m in self.mails if m["at"] >= since and any(n.lower() in (m["subject"] + m["snippet"]).lower() for n in names)
                and "linkedin.com" in m["from"]]


def mail(n, subject, snippet="", sender="invitations@linkedin.com"):
    return {"id": f"m{n}", "from": f"LinkedIn <{sender}>", "subject": subject, "snippet": snippet,
            "at": datetime.now(timezone.utc)}


@pytest.fixture
def inbox(session, client, monkeypatch):
    monkeypatch.setenv("MAILBOX_KEY", Fernet.generate_key().decode())
    fakebox = FakeInbox([])
    monkeypatch.setattr(mailbox, "provider_override", lambda s, b: fakebox)
    session.add(Mailbox(org_id=uuid.UUID(client.headers["X-Org-Id"]), provider="google", account="me@desk.example",
                        token_enc=mailbox.seal({"access_token": "x"}), connected_by="test"))
    session.flush()
    return fakebox


def test_linkedin_emails_move_the_track_only_for_people_contacted_on_linkedin(client, session, job, blobs, inbox):
    ada = found(session, job, blobs)
    ben = person_named(session, "Ben Testperson")
    r = client.post("/v1/mailbox/sync")
    assert r.json()["linkedin"] == {"accepted": 0, "replied": 0, "unclear": 0}, r.text
    assert inbox.asked == [], "nobody contacted on LinkedIn: the mailbox is not even asked"
    client.post(f"/v1/jobs/{job.id}/people/{ada}/decide", json={"choice": "reach_out"})
    client.post(f"/v1/jobs/{job.id}/people/{ada}/contacted", json={"channel": "linkedin_invite"})
    inbox.mails += [mail(1, "Ada Testperson has accepted your invitation. Let's start a conversation."),
                    mail(2, "Ada sent you a new message", "Ada Testperson: Hi, happy to hear more", sender="messages-noreply@linkedin.com"),
                    mail(3, "Ben Testperson has accepted your invitation"),
                    mail(4, "Lunch with Ada Testperson?", "see you", sender="friend@example.com")]
    r = client.post("/v1/mailbox/sync")
    assert "linkedin" in r.json(), r.text
    out = r.json()["linkedin"]
    assert out == {"accepted": 1, "replied": 1, "unclear": 0}
    assert inbox.asked == [["Ada Testperson"]], "only the names of people contacted on LinkedIn are searched for"
    session.expire_all()
    pair = pair_of(session, job, ada)
    assert pair.contact["accepted_at"] and pair.contact["stage"] == "replied"
    assert pair.contact["reply"]["outcome"] is None and "happy to hear more" in pair.contact["reply"]["text"]
    assert session.scalar(select(Message).where(Message.candidate_id == ada)).status == "replied"
    assert pair_of(session, job, ben).contact is None, "Ben was never contacted: his email changes nothing"
    timeline = [a.summary for a in session.scalars(select(Activity).where(Activity.subject_id == ada))]
    assert "Accepted your LinkedIn invitation" in timeline and any(t.startswith("Replied on LinkedIn") for t in timeline)
    assert client.post("/v1/mailbox/sync").json()["linkedin"] == {"accepted": 0, "replied": 0, "unclear": 0}, "read once"
    r = client.post(f"/v1/jobs/{job.id}/people/{ada}/replied", json={"outcome": "interested"}).json()
    assert r["contact"]["reply"]["outcome"] == "interested", "the owner says what the reply means"


def test_two_contacted_people_with_one_name_ask_the_owner(client, session, job, blobs, inbox):
    ada = found(session, job, blobs)
    ben = person_named(session, "Ben Testperson")
    for cid in (ada, ben):
        client.post(f"/v1/jobs/{job.id}/people/{cid}/decide", json={"choice": "reach_out"})
        client.post(f"/v1/jobs/{job.id}/people/{cid}/contacted", json={"channel": "linkedin_message"})
    from maindscout.api import queries

    real = queries.names
    try:
        queries.names = lambda s, ids: {i: "Sam Testperson" for i in ids}  # two people, one name
        inbox.mails.append(mail(1, "Sam Testperson sent you a new message", "Sam Testperson: yes please"))
        assert client.post("/v1/mailbox/sync").json()["linkedin"]["unclear"] == 1
    finally:
        queries.names = real
    session.expire_all()
    assert pair_of(session, job, ada).contact["unclear"]["kind"] == "message"
    assert pair_of(session, job, ben).contact["unclear"]["others"] == 1
    r = client.post(f"/v1/jobs/{job.id}/people/{ben}/linkedin-email", json={"mine": True}).json()
    assert r["stage"] == "replied" and "unclear" not in r["contact"]
    session.expire_all()
    assert "unclear" not in pair_of(session, job, ada).contact and pair_of(session, job, ada).contact["stage"] == "contacted"


def test_the_google_permission_can_search_and_the_reader_ignores_other_notifications():
    assert "gmail.readonly" in mailbox.GOOGLE_SCOPES and "gmail.metadata" not in mailbox.GOOGLE_SCOPES
    assert outreach.ACCEPTED.search("Ada Testperson hat Ihre Einladung angenommen")
    assert outreach.MESSAGED.search("Ada just messaged you")
    assert not outreach.ACCEPTED.search("Ada Testperson viewed your profile")
    assert not outreach.MESSAGED.search("Ada Testperson viewed your profile")
    assert outreach._named("ada testperson", "Hi from Ada Testperson!") and not outreach._named("ada test", "Ada Testperson")
