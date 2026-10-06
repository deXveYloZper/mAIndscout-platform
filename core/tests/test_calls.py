"""Calls: a transcript becomes one Call review, approved in bulk; what people want shapes matching and sourcing.
All without a model: a scripted fake answers the one reading call."""

import re
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from sqlalchemy import func, select

from maindscout.api import calls, process, research, review, task_handlers, tasks
from maindscout.db.models import Activity, BriefItem, CallReview, CandidateJob, Claim, Company, Document, Evidence, Job, Task
from maindscout.domain import preferences
from maindscout.domain.profile import CompanyFacts
from maindscout.ingestion import transcript
from maindscout.intelligence import calls as reader
from maindscout.intelligence import research as engine
from maindscout.intelligence.llm import FakeClient, LLMError, LLMResult
from tests.test_api import client, fake  # noqa: F401 (fixtures)
from tests.test_brief import priority_job

CALL = """Recruiter: Thanks for making time, Jane. Is your email still jane.example@example.com?
Jane Example: Yes, jane.example@example.com is right.
Recruiter: And when could you start?
Jane Example: I have a one month notice period.
Recruiter: What do you want next?
Jane Example: Honestly I am tired of start-ups. I would prefer a scale-up or a larger company.
Jane Example: I won't go anywhere under 200 people again.
Jane Example: I also use Python every day now.
Recruiter: Great, I am a team player myself and think you would fit in well.
"""


def line_ref(user: str, needle: str) -> str:
    """The ref the desk gave the fact or question containing `needle` (the fake reads the prompt like a model)."""
    m = re.search(rf"^([FB]\d+) .*{re.escape(needle)}", user, re.M)
    assert m, f"{needle!r} not in the context"
    return m.group(1)


def finding(kind, text, quote, **over):
    base = {"kind": kind, "ref": None, "outcome": None, "text": text, "quote": quote, "fact_type": None, "value": None,
            "company": None, "title": None, "start_year": None, "end_year": None, "contact_kind": None, "facet": None,
            "strength": None, "min": None, "max": None, "want": [], "avoid": [], "level": None}
    return {**base, **over}


class Scripted:
    """Answers the transcript read from a function of the prompt."""

    model = "fake-model"

    def __init__(self, script):
        self.script, self.calls = script, 0

    def complete_json(self, system, user, schema, name):
        self.calls += 1
        return LLMResult(self.script(user), self.model, 10, 10, 0.0)


def jane_script(user):
    return {"candidate_speaker": "Jane Example", "findings": [
        finding("confirm", "email is right", "Yes, jane.example@example.com is right.", ref=line_ref(user, "jane.example@example.com")),
        finding("brief_answer", "one month notice", "I have a one month notice period.", ref=line_ref(user, "When could they start"),
                outcome="noted"),
        finding("preference", "tired of start-ups", "Honestly I am tired of start-ups. I would prefer a scale-up or a larger company.",
                facet="employer_kind", strength="prefer", want=["scaleup", "large"], avoid=["startup"]),
        finding("preference", "200 people or more", "I won't go anywhere under 200 people again.", facet="company_size",
                strength="must", min=200),
        finding("new_fact", "uses Python", "I also use Python every day now.", fact_type="skill", value="Python"),
        # Never kept: the recruiter's words, and anything about fit.
        finding("new_fact", "team player", "I am a team player myself", fact_type="skill", value="team player"),
        finding("ask", "Which industries interest them most?", ""),
    ]}


@pytest.fixture
def jane(client, fake, session, monkeypatch):
    """Jane, a priority match for a Rust job at Catalyst Geo."""
    job, cid = priority_job(client, fake)
    monkeypatch.setattr(task_handlers, "llm_factory", lambda: Scripted(jane_script))
    return job, cid


def add_call(client, cid, text=CALL, **files):
    r = client.post(f"/v1/candidates/{cid}/transcripts", data={"text": text} if not files else {}, files=files or None)
    assert r.status_code == 201, r.text
    return r.json()


def read_queued(session):
    for task in session.scalars(select(Task).where(Task.kind == "read_transcript", Task.status == "queued")):
        tasks.execute(session, task)
        task.status = "done"
    session.flush()


def lines(review_json, kind=None):
    return [line for s in review_json["sections"] for line in s["lines"] if kind is None or line["kind"] == kind]


# --- transcripts -----------------------------------------------------------------------------------------------


def test_call_tool_exports_become_speaker_lines():
    vtt = ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\n<v Maria Lopez>Hi Ana, thanks for joining.</v>\n\n"
           "2\n00:00:04.500 --> 00:00:09.000\n<v Ana Silva>Honestly I am tired of start-ups.</v>\n\n"
           "3\n00:00:09.000 --> 00:00:12.000\n<v Ana Silva>At least 200 people, please.</v>\n")
    assert transcript.to_text(vtt.encode(), "call.vtt") == (
        "Maria Lopez: Hi Ana, thanks for joining.\nAna Silva: Honestly I am tired of start-ups. At least 200 people, please.")
    srt = "1\n00:00:01,000 --> 00:00:03,000\nRecruiter: What do you want next?\n\n2\n00:00:03,000 --> 00:00:06,000\nAna: Remote and permanent.\n"
    assert transcript.to_text(srt.encode(), "call.srt") == "Recruiter: What do you want next?\nAna: Remote and permanent."
    zoom = "[Maria Lopez] 10:01:22\nHi Ana, how are you doing?\n[Ana Silva] 10:01:30\nGood. I only want remote roles now.\n"
    assert transcript.to_text(zoom.encode(), "zoom.txt").splitlines()[1] == "Ana Silva: Good. I only want remote roles now."
    assert transcript.speakers(transcript.to_text(zoom.encode(), "zoom.txt")) == ["Maria Lopez", "Ana Silva"]


def test_a_docx_transcript_is_read_and_junk_is_refused():
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (f'<w:document xmlns:w="{w}"><w:body><w:p><w:r><w:t>Maria Lopez: What size of company suits you?</w:t></w:r></w:p>'
           f'<w:p><w:r><w:t>Ana Silva: Nothing under two hundred people.</w:t></w:r></w:p></w:body></w:document>')
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    assert transcript.to_text(buf.getvalue(), "Teams call.docx").endswith("Ana Silva: Nothing under two hundred people.")
    with pytest.raises(transcript.TranscriptError):
        transcript.to_text(b"too short", "a.txt")
    with pytest.raises(transcript.TranscriptError):
        transcript.to_text(b"\x00\x01binary" * 50, "a.txt")


# --- the reader (pure) -------------------------------------------------------------------------------------------


def test_the_reader_keeps_only_the_candidates_own_checked_words():
    text = transcript.to_text(CALL.encode(), "call.txt")
    facts = [{"ref": "F1", "kind": "contact", "text": "email: jane.example@example.com"}]
    data = {"candidate_speaker": None, "findings": [
        finding("confirm", "email ok", "Yes, jane.example@example.com is right.", ref="F1"),
        finding("confirm", "invented", "My email is jane@other.example", ref="F1"),  # not in the transcript
        finding("new_fact", "recruiter's words", "Is your email still jane.example@example.com?", fact_type="contact",
                contact_kind="email", value="jane.example@example.com"),
        finding("preference", "fit", "think you would fit in well", facet="employer_kind", strength="prefer", want=["large"]),
        finding("preference", "size", "I won't go anywhere under 200 people again.", facet="company_size", strength="must", min=250),
        finding("confirm", "no such fact", "Yes, jane.example@example.com is right.", ref="F9"),
    ]}
    out = reader.read(text, FakeClient(data), name="Jane Example", facts=facts, questions=[], preferences=[])
    assert out.candidate_speaker == "Jane Example", "found by name, whatever the model said"
    assert [f.text for f in out.findings] == ["email ok"]
    reasons = [r["reason"] for r in out.rejected]
    assert "the quote is not in the transcript" in reasons
    assert "the quote is not the candidate's own words" in reasons
    assert "personality, culture or fit is never recorded" in reasons
    assert "the number is not in their words" in reasons and "no such fact" in reasons


def test_numbers_in_words_count_and_unlabelled_transcripts_are_read_whole():
    assert reader._number_said(200, "nothing under two hundred people")
    assert reader._number_said(1000, "at least a thousand") and reader._number_said(1000, "1k or more")
    assert not reader._number_said(50, "nothing under 200")
    text = "I want a company of at least 200 people and I only work remote these days, nothing else for me."
    data = {"candidate_speaker": None, "findings": [
        finding("preference", "remote", "I only work remote", facet="setting", strength="must", want=["remote", "beach"])]}
    out = reader.read(text, FakeClient(data), name=None, facts=[], questions=[], preferences=[])
    assert out.findings[0].fields == {"facet": "setting", "strength": "must", "want": ["remote"], "avoid": []}


# --- the Call review ---------------------------------------------------------------------------------------------


def test_a_pasted_transcript_becomes_one_review_with_every_line_ticked(client, session, jane):
    job, cid = jane
    row = add_call(client, cid)
    assert row["status"] == "reading" and row["filename"] == "pasted call transcript.txt"
    doc = session.get(Document, uuid.UUID(row["document_id"]))
    assert doc.doc_type == "transcript" and doc.source_authority == "candidate_authored"
    read_queued(session)
    r = client.get(f"/v1/call-reviews/{row['id']}").json()
    assert r["status"] == "pending"
    kinds = {line["kind"] for line in lines(r)}
    assert kinds == {"confirm", "brief_answer", "preference", "new_fact", "ask"}
    assert all(line["ticked"] for line in lines(r))
    assert not any("team player" in line["text"] for line in lines(r)), "the recruiter's words never become facts"
    size = next(line for line in lines(r, "preference") if line["facet"] == "company_size")
    assert size["summary"] == "Must: a company of at least 200 people"
    assert add_call(client, cid)["id"] == row["id"], "the same transcript twice is one review"


def test_approve_all_writes_facts_with_their_words_as_evidence_and_matches_once(client, session, jane, monkeypatch):
    job, cid = jane
    row = add_call(client, cid)
    read_queued(session)
    rematches = []
    real = process.retriage_candidate
    monkeypatch.setattr(review, "retriage_candidate", lambda *a, **k: rematches.append(a[2]) or real(*a, **k))
    r = client.post(f"/v1/call-reviews/{row['id']}/apply", json={}).json()
    assert r["status"] == "applied" and all(line["result"] == "applied" for line in lines(r))
    assert len(rematches) == 1, "one re-match for the whole review"
    person = uuid.UUID(cid)
    email = session.scalar(select(Claim).where(Claim.subject_id == person, Claim.claim_type == "ContactClaim"))
    assert email.status == "approved"
    python = session.scalar(select(Claim).where(Claim.subject_id == person, Claim.claim_type == "SkillClaim",
                                                Claim.payload["normalized_skill"].astext == "python"))
    assert python.status == "approved"
    ev = session.scalar(select(Evidence).where(Evidence.claim_id == python.id))
    assert (ev.document_id, ev.origin, ev.source_authority) == (uuid.UUID(row["document_id"]), "candidate", "candidate_authored")
    assert ev.snippet == "I also use Python every day now."
    notice = session.scalar(select(BriefItem).where(BriefItem.candidate_id == person, BriefItem.source_key == "std:notice"))
    assert notice.status == "answered" and notice.answer == "one month notice"
    asked = session.scalar(select(BriefItem).where(BriefItem.candidate_id == person, BriefItem.kind == "call"))
    assert asked.question == "Which industries interest them most?" and asked.status == "open"
    client.get(f"/v1/candidates/{cid}/brief")
    session.refresh(asked)
    assert asked.status == "open", "a question from the call is not expired by the next Brief"
    wants = client.get(f"/v1/candidates/{cid}/calls").json()["preferences"]
    assert {w["summary"] for w in wants} == {"Must: a company of at least 200 people",
                                            "Prefers: scale-ups or large companies, not start-ups"}
    assert session.scalar(select(Activity).where(Activity.subject_id == person, Activity.kind == "call")) is not None
    assert client.post(f"/v1/call-reviews/{row['id']}/apply", json={}).status_code == 422, "applied once"


def test_unticked_lines_are_dropped(client, session, jane):
    job, cid = jane
    row = add_call(client, cid)
    read_queued(session)
    r = client.get(f"/v1/call-reviews/{row['id']}").json()
    keep = [line["id"] for line in lines(r) if line["kind"] != "new_fact"]
    done = client.post(f"/v1/call-reviews/{row['id']}/apply", json={"ticked": keep}).json()
    assert {line["result"] for line in lines(done, "new_fact")} == {"dropped"}
    assert not session.scalar(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "SkillClaim",
                                                  Claim.payload["normalized_skill"].astext == "python"))


def test_a_correction_of_an_approved_fact_starts_unticked(client, session, jane, monkeypatch):
    job, cid = jane
    email = session.scalar(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "ContactClaim"))
    review.approve_claim(session, email.org_id, email.id, "owner")
    text = CALL + "Jane Example: Actually my email is now jane@newmail.example, the old one is gone.\n"

    def script(user):
        return {"candidate_speaker": "Jane Example", "findings": [finding(
            "correct", "new email", "my email is now jane@newmail.example", ref=line_ref(user, "jane.example@example.com"),
            value="jane@newmail.example", fact_type="contact")]}

    monkeypatch.setattr(task_handlers, "llm_factory", lambda: Scripted(script))
    row = add_call(client, cid, text)
    read_queued(session)
    r = client.get(f"/v1/call-reviews/{row['id']}").json()
    (line,) = lines(r)
    assert line["ticked"] is False and line["current"] == "email: jane.example@example.com"
    client.post(f"/v1/call-reviews/{row['id']}/apply", json={})
    session.refresh(email)
    assert email.status == "approved", "not ticked: nothing changed"


def test_a_ticked_correction_replaces_the_fact(client, session, jane, monkeypatch):
    job, cid = jane
    text = CALL + "Jane Example: Actually my email is now jane@newmail.example, the old one is gone.\n"
    monkeypatch.setattr(task_handlers, "llm_factory", lambda: Scripted(lambda user: {"candidate_speaker": None, "findings": [finding(
        "correct", "new email", "my email is now jane@newmail.example", ref=line_ref(user, "jane.example@example.com"),
        value="jane@newmail.example")]}))
    row = add_call(client, cid, text)
    read_queued(session)
    line = lines(client.get(f"/v1/call-reviews/{row['id']}").json())[0]
    assert line["ticked"] is True, "a proposed fact: ticked"
    client.post(f"/v1/call-reviews/{row['id']}/apply", json={})
    live = session.scalars(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "ContactClaim",
                                               Claim.status == "approved")).all()
    assert [c.payload["normalized"] for c in live] == ["jane@newmail.example"]


def test_a_reading_that_cannot_reach_the_model_fails_and_can_be_tried_again(client, session, jane, monkeypatch):
    job, cid = jane

    class Down:
        model = "x"

        def complete_json(self, *a):
            raise LLMError("no credits")

    monkeypatch.setattr(task_handlers, "llm_factory", lambda: Down())
    row = add_call(client, cid)
    read_queued(session)
    r = client.get(f"/v1/call-reviews/{row['id']}").json()
    assert r["status"] == "failed" and "no credits" in r["error"]
    assert [w["id"] for w in client.get("/v1/call-reviews").json()] == [row["id"]], "waits in the inbox"
    assert client.post(f"/v1/call-reviews/{row['id']}/retry").json()["status"] == "reading"
    monkeypatch.setattr(task_handlers, "llm_factory", lambda: Scripted(jane_script))
    read_queued(session)
    assert client.get(f"/v1/call-reviews/{row['id']}").json()["status"] == "pending"
    assert client.post(f"/v1/call-reviews/{row['id']}/dismiss").json()["status"] == "dismissed"
    assert client.get("/v1/call-reviews").json() == []


def test_erasure_removes_transcripts_and_reviews(client, session, jane, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job, cid = jane
    row = add_call(client, cid)
    read_queued(session)
    client.post(f"/v1/call-reviews/{row['id']}/apply", json={})
    assert client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "request"}).status_code == 200
    assert session.scalar(select(func.count()).select_from(CallReview)) == 0
    assert session.get(Document, uuid.UUID(row["document_id"])) is None
    assert client.get(f"/v1/subjects/candidate/{cid}/erase/verify").json()["clean"] is True


# --- what they want, in matching ---------------------------------------------------------------------------------


def hiring_company(session, job) -> Company:
    j = session.get(Job, uuid.UUID(job))
    return session.get(Company, j.hiring_company_id)


def publish(session, company, *facts):
    url = "https://catalyst.example/"
    research.apply(session, company, engine.ResearchOutcome(True, url, [engine.Fact(k, v, url, "quote") for k, v in facts],
                                                            [], [url], {"usd": 0}))


def rules_of(session, job, cid):
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == uuid.UUID(job), CandidateJob.candidate_id == uuid.UUID(cid)))
    process.retriage_pair(session, pair, {"act": "test"})
    return pair, {r["id"]: r for r in (pair.match or {}).get("rules") or []}


def test_the_owners_example_tired_of_start_ups(client, session, jane):
    """Strong start-up background, but they said they are tired of start-ups and want 200 people or more."""
    job, cid = jane
    row = add_call(client, cid)
    read_queued(session)
    client.post(f"/v1/call-reviews/{row['id']}/apply", json={})
    company = hiring_company(session, job)
    assert company is not None
    publish(session, company, ("headcount", "11-50"), ("funding_round", {"stage": "seed", "date": "2025-03"}))
    assert session.scalar(select(Task).where(Task.kind == "rematch_job", Task.payload["job_id"].astext == job)) is not None
    pair, rules = rules_of(session, job, cid)
    assert pair.triage_band == "do_not_submit", "a priority match until she said what she wants"
    assert "wants_otherwise" in rules and "11-50 people" in rules["wants_otherwise"]["detail"]
    assert "I won't go anywhere under 200 people again." in rules["wants_otherwise"]["detail"], "quotes both sides"
    assert "prefers_otherwise" in rules and "reads as a start-up" in rules["prefers_otherwise"]["detail"]


def test_a_prefer_alone_is_only_a_note_and_a_fitting_job_says_so():
    prefer = {"facet": "employer_kind", "strength": "prefer", "want": ["large"], "avoid": ["startup"], "said": "tired of start-ups"}
    startup = preferences.JobSide("Tiny", CompanyFacts(team_min=11, team_max=50))
    large = preferences.JobSide("Big", CompanyFacts(team_min=5001, status="public"))
    unknown = preferences.JobSide("Who")
    assert preferences.check(prefer, startup)[0] == "gap"
    assert preferences.check(prefer, large) == ("strong", "fits what they want: Big reads as a large company")
    assert preferences.check(prefer, unknown)[0] == "ask"
    size = {"facet": "company_size", "strength": "must", "min": 200, "said": "200 or more"}
    assert preferences.check(size, preferences.JobSide("Mid", CompanyFacts(team_min=201, team_max=500)))[0] == "strong"
    assert preferences.check(size, preferences.JobSide("Mid", CompanyFacts(team_min=51, team_max=200)))[0] == "ask", "may or may not"
    assert preferences.check(size, preferences.JobSide("Mid", CompanyFacts(team_min=11, team_max=50)))[0] == "gap"
    assert preferences.check(size, preferences.JobSide("Mid", CompanyFacts(team_min=51)))[0] == "ask"

    from maindscout.domain import matching

    profile = {"reading": {"label": "clear"}}
    soft = matching.match([], [], profile, [], ("priority", "ok"), preferences=preferences.rows([prefer], startup))
    assert soft.tier == "strong" and {r["id"] for r in soft.rules} >= {"prefers_otherwise", "strong_match"}
    hard = matching.match([], [], profile, [], ("priority", "ok"), preferences=preferences.rows([{**prefer, "strength": "must"}], startup))
    assert hard.tier == "unlikely" and hard.rules[0]["id"] == "wants_otherwise"
    fits = matching.match([], [], profile, [], ("priority", "ok"), preferences=preferences.rows([prefer], large))
    assert fits.tier == "strong" and fits.rules[0]["id"] == "fits_what_they_want"


def test_sourcing_never_puts_people_on_a_job_they_said_no_to(client, session, jane):
    job, cid = jane
    row = add_call(client, cid)
    read_queued(session)
    client.post(f"/v1/call-reviews/{row['id']}/apply", json={})
    publish(session, hiring_company(session, job), ("headcount", "11-50"))
    j = session.get(Job, uuid.UUID(job))
    assert process.not_wanted_by(session, j.org_id, j) == {uuid.UUID(cid)}


def test_old_preferences_are_asked_again_and_a_yes_renews_them(client, session, jane):
    job, cid = jane
    row = add_call(client, cid)
    read_queued(session)
    client.post(f"/v1/call-reviews/{row['id']}/apply", json={})
    old = calls.preferences_of(session, session.get(CallReview, uuid.UUID(row["id"])).org_id, uuid.UUID(cid))
    for c in old:
        c.created_at = datetime.now(timezone.utc) - timedelta(days=200)
    session.flush()
    items = client.get(f"/v1/candidates/{cid}/brief").json()["items"]
    again = [i for i in items if i["kind"] == "preference"]
    assert len(again) == 2 and all(i["question"].startswith("Is this still what they want?") for i in again)
    size = next(i for i in again if "200 people" in i["question"])
    assert client.post(f"/v1/brief/{size['id']}/answer", json={"outcome": "confirmed"}).status_code == 200
    fresh = {v["facet"]: v for v in client.get(f"/v1/candidates/{cid}/calls").json()["preferences"]}
    assert fresh["company_size"]["stale"] is False and fresh["employer_kind"]["stale"] is True


# --- approve all from a CV --------------------------------------------------------------------------------------


def test_approve_all_from_a_cv_leaves_open_questions_alone(client, session, jane):
    job, cid = jane
    person = uuid.UUID(cid)
    doc = session.scalar(select(Evidence.document_id).join(Claim, Claim.id == Evidence.claim_id).where(Claim.subject_id == person).limit(1))
    proposed = session.scalar(select(func.count()).select_from(Claim).where(Claim.subject_id == person, Claim.status == "proposed"))
    assert proposed > 3
    r = client.post(f"/v1/candidates/{cid}/documents/{doc}/approve-all")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["approved"] + out["left"] == proposed
    left = session.scalar(select(func.count()).select_from(Claim).where(Claim.subject_id == person, Claim.status == "proposed"))
    assert left == out["left"]
