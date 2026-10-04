"""Slice 4 step 5: drafts from outward-safe facts, the mailbox (Gmail / Outlook, faked here), sent and replied detection,
follow-ups that a reply stops. Nothing is ever sent by the platform."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from maindscout.api import mailbox, messages
from maindscout.db.models import Activity, Claim, ClientContact, Company, Mailbox, Message
from maindscout.intelligence import drafts
from maindscout.intelligence.llm import LLMResult
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)


class FakeMailbox:
    """Stands in for Gmail / Outlook: drafts, threads, sends and replies are controlled by the test."""

    def __init__(self):
        self.drafts, self.sent, self.replies, self.deleted, n = {}, {}, {}, [], 0

    def create_draft(self, to, subject, body, thread_id):
        did = f"d{len(self.drafts) + 1}"
        tid = thread_id or f"t{len(self.drafts) + 1}"
        self.drafts[did] = {"to": to, "subject": subject, "body": body, "thread": tid}
        return {"draft_id": did, "thread_id": tid, "web_link": f"https://mail.example/{did}"}

    def send(self, did):  # the recruiter pressed send in their mailbox
        self.sent[did] = datetime.now(timezone.utc)

    def reply(self, tid):
        self.replies.setdefault(tid, []).append(datetime.now(timezone.utc) + timedelta(seconds=1))

    def draft_state(self, did, tid):
        if did in self.sent:
            return {"state": "sent", "thread_id": self.drafts[did]["thread"], "at": self.sent[did]}
        return {"state": "draft"} if did in self.drafts and did not in self.deleted else {"state": "gone"}

    def replies_since(self, tid, since, own):
        return [r for r in self.replies.get(tid, []) if since is None or r > since]

    def delete_draft(self, did):
        self.deleted.append(did)


@pytest.fixture
def box(session, client, monkeypatch):
    monkeypatch.setenv("MAILBOX_KEY", Fernet.generate_key().decode())
    fakebox = FakeMailbox()
    monkeypatch.setattr(mailbox, "provider_override", lambda s, b: fakebox)
    org = uuid.UUID(client.headers["X-Org-Id"])
    session.add(Mailbox(org_id=org, provider="google", account="me@desk.example", token_enc=mailbox.seal({"access_token": "x"}),
                        connected_by="test"))
    session.flush()
    return fakebox


def org_of(client):
    return uuid.UUID(client.headers["X-Org-Id"])


def outreach(client, job, cid):
    r = client.post("/v1/messages", json={"kind": "candidate_outreach", "candidate_id": cid, "job_id": job})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_draft_uses_only_approved_facts_and_never_internal_words(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]  # Jane: in Do not submit; facts proposed, not approved
    m = outreach(client, job, cid)
    assert m["to"] == "jane.example@example.com" and m["status"] == "draft"
    assert "Acme" not in m["body"], "proposed (unapproved) facts are not said outward"
    assert not drafts.INTERNAL.search(m["subject"] + m["body"])
    career = session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "CareerStepClaim",
                                                 Claim.valid_to.is_(None))).first()
    client.post(f"/v1/claims/{career.id}/approve")
    assert "Acme Space" in outreach(client, job, cid)["body"], "approved facts may be used"


def test_a_model_draft_that_mentions_internal_judgements_is_replaced_by_the_template():
    class Leaky:
        model = "leaky"

        def complete_json(self, system, user, schema, name):
            return LLMResult({"subject": "Role", "body": "Hi Jane, you scored 82% and are in our priority band."}, self.model, 1, 1, 0.0)

    out = drafts.write(drafts.Projection("candidate_outreach", "Jane", job={"title": "InSAR role"}), Leaky())
    assert out.written_by == "template" and "score" not in out.body and out.refused


def test_editing_cannot_add_internal_words(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    m = outreach(client, job, cid)
    assert client.patch(f"/v1/messages/{m['id']}", json={"subject": "Hi", "body": "You are in our do not submit band"}).status_code == 422
    assert client.patch(f"/v1/messages/{m['id']}", json={"subject": "Hi", "body": "Fancy a chat?"}).json()["body"] == "Fancy a chat?"


def test_without_a_mailbox_the_draft_stays_here(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    m = outreach(client, job, cid)
    r = client.post(f"/v1/messages/{m['id']}/mailbox")
    assert r.status_code == 422 and "connect Gmail or Outlook" in r.json()["detail"]


def test_sent_in_the_mailbox_then_a_reply_stops_the_follow_up(client, fake, session, box):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    m = outreach(client, job, cid)
    r = client.post(f"/v1/messages/{m['id']}/mailbox").json()
    assert r["status"] == "in_mailbox" and r["open"].startswith("https://mail.example/")
    assert client.post("/v1/mailbox/sync").json()["sent"] == 0, "not sent yet: the platform never sends"
    box.send("d1")
    assert client.post("/v1/mailbox/sync").json()["sent"] == 1
    sent = session.get(Message, uuid.UUID(m["id"]))
    assert sent.status == "sent" and sent.follow_up_due is not None
    assert client.get(f"/v1/candidates/{cid}").json()["relationship"]["last_contacted"], "a sent email is contact"
    follow = messages.due_follow_ups(session, org_of(client), None, now=datetime.now(timezone.utc) + timedelta(days=5))
    assert len(follow) == 1 and follow[0].status == "in_mailbox" and follow[0].kind == "follow_up"
    box.reply(sent.provider_thread_id)
    assert client.post("/v1/mailbox/sync").json()["replied"] == 1
    session.refresh(follow[0])
    assert follow[0].status == "cancelled" and follow[0].provider_draft_id in box.deleted, "a reply stops the follow-up"
    acts = session.scalars(select(Activity).where(Activity.subject_id == uuid.UUID(cid), Activity.kind == "email")).all()
    assert sorted(a.direction for a in acts) == ["in", "out"]


def test_a_client_submission_goes_to_a_contact_with_what_may_be_shared(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    company = session.scalar(select(Company).where(Company.normalized == "catalyst geo"))
    contact = client.post(f"/v1/companies/{company.id}/contacts", json={"name": "Anna Example", "email": "anna@catalyst.example"}).json()["id"]
    r = client.post("/v1/messages", json={"kind": "client_submission", "candidate_id": cid, "job_id": job, "contact_id": contact})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["to"] == "anna@catalyst.example" and m["body"].startswith("Hi Anna")
    page = client.get(f"/v1/candidates/{cid}").json()
    assert page["jobs"] and page["client_contacts"] == [{"id": contact, "name": "Anna Example", "role": None, "job_id": job,
                                                         "job": page["jobs"][0]["title"]}]
    assert page["messages"][0]["kind"] == "client_submission"
    client.post(f"/v1/jobs/{job}/people/{cid}/state", json={"state": "client_rejected", "note": "no"})
    blocked = client.post("/v1/messages", json={"kind": "client_submission", "candidate_id": cid, "job_id": job, "contact_id": contact})
    assert blocked.status_code == 422 and "said no" in blocked.json()["detail"]


def test_the_sign_in_link_is_signed_and_tokens_are_encrypted(monkeypatch):
    monkeypatch.setenv("MAILBOX_KEY", Fernet.generate_key().decode())
    org = uuid.uuid4()
    state = mailbox.make_state(org, "google", "operator")
    assert mailbox.read_state(state, "google") == (org, "operator")
    with pytest.raises(mailbox.MailboxError):
        mailbox.read_state(state, "microsoft")
    with pytest.raises(mailbox.MailboxError):
        mailbox.read_state(state[:-4] + "AAAA", "google")
    sealed = mailbox.seal({"access_token": "secret-token"})
    assert "secret-token" not in sealed and mailbox.unseal(sealed)["access_token"] == "secret-token"


def test_connecting_needs_the_providers_app_set_up(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    r = client.post("/v1/mailbox/connect/google")
    assert r.status_code == 422 and "setup guide" in r.json()["detail"]
    status = client.get("/v1/mailbox").json()
    assert status["connected"] is False and status["google_ready"] is False
    bad = client.get("/v1/mailbox/callback/google", params={"code": "x", "state": "nonsense"}, follow_redirects=False)
    assert bad.status_code in (302, 307) and "error=" in bad.headers["location"]


def test_erasure_removes_messages(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]
    outreach(client, job, cid)
    assert client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "request"}).status_code == 200
    assert not session.scalars(select(Message).where(Message.candidate_id == uuid.UUID(cid))).all()
    assert client.get(f"/v1/subjects/candidate/{cid}/erase/verify").json()["clean"] is True
