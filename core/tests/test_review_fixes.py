"""Regression tests for the 2026-10-05 external code review. Each test is one of the reviewer's probes (or a defect
found while checking them) and fails on the code before the fix. None needs the real model."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from maindscout.api import companies, erasure, review, tasks
from maindscout.db.models import Activity, Claim, Decision, ImportRow, Task
from maindscout.domain.matching import _covers
from maindscout.intelligence import contacts, spans
from maindscout.intelligence.extract import _Run
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_erasure import blobs, count, ingest, key  # noqa: F401 (fixtures)
from tests.test_process import CV_LINES, cv_json


# --- identity: a shared contact never merges different people ------------------------------------------------------

AGENCY = "talent@agency.example"


def agency_cv(name: str, upper: str):
    data = cv_json(full_name={"value": name, "quote": upper},
                   contacts=[{"kind": "email", "value": AGENCY, "quote": AGENCY}])
    lines = [upper, AGENCY] + CV_LINES[2:]
    return data, lines


def test_a_recruiters_email_on_two_cvs_does_not_merge_two_people(session, blobs, org, key):
    first, _ = ingest(session, blobs, org, *agency_cv("Jane Example", "JANE EXAMPLE"))
    second, _ = ingest(session, blobs, org, *agency_cv("Omar Sample", "OMAR SAMPLE"))
    assert first.subject_id != second.subject_id
    note = session.scalar(select(Decision).where(Decision.subject_id == second.subject_id, Decision.type == "identity_note"))
    assert note is not None and str(first.subject_id) in note.context["candidate_ids"]
    assert "not the same name" in note.context["reason"]


def test_the_same_person_again_still_merges_on_a_clean_contact(session, blobs, org, key):
    first, _ = ingest(session, blobs, org, cv_json())
    again, _ = ingest(session, blobs, org, cv_json(), CV_LINES + ["Updated 2026"])
    assert again.subject_id == first.subject_id


def test_names_agree_with_initials_and_word_order_but_not_with_someone_else():
    assert contacts.same_name("Jure Domajnko", "J. Domajnko")
    assert contacts.same_name("Domajnko Jure", "Jure Domajnko")
    assert contacts.same_name("Gökhan Çiflikli", "Gokhan Ciflikli")
    assert not contacts.same_name("Jure Domajnko", "Ovi Grigorescu")
    assert not contacts.same_name("Jane Example", None)
    assert not contacts.same_name("J.", "Jane Example")


def test_a_misspelt_email_taken_from_a_link_is_flagged_too(session, blobs, org, key):
    from maindscout.intelligence import extract
    from maindscout.intelligence.llm import FakeClient

    annotations = [{"page": 1, "kind": "email", "uri": "mailto:jane.exmple@example.com"}]
    outcome = extract.extract_cv("\n".join(CV_LINES), uuid.uuid4(), annotations, FakeClient(cv_json(contacts=[])))
    link = next(c for c in outcome.staged if c.claim_type == "ContactClaim")
    assert link.payload["normalized"] == "jane.exmple@example.com" and link.flags.get("possible_ocr_identifier")


# --- the span check -----------------------------------------------------------------------------------------------


def test_a_two_digit_number_is_not_a_year_but_a_dated_two_digit_year_is():
    assert not spans.date_supported("2024-01-01", "year_only", "Started on the 24th of March")
    assert not spans.date_supported("2024-01-01", "year_only", "Support 24/7")
    assert spans.date_supported("2019-03-01", "month", "Acme 03/19 - 05/21")
    assert spans.date_supported("2019-03-01", "month", "Acme, Mar '19 to now")


def test_contacts_must_be_one_written_value():
    assert not spans.value_supported("phone", "111222", "Room 111, ticket 222333", [])
    assert spans.value_supported("phone", "+447700900123", "Call +44 (7700) 900-123", [])
    assert not spans.value_supported("email", "domainko@gmail.com", "domain k o@gmail.com", [])
    assert spans.value_supported("email", "jane.example@gmail.com", "Mail: jane.exam ple@gmail.com", [])


def test_a_name_is_not_found_inside_a_longer_word():
    assert not spans.name_supported("Ann", "Joann Smith")
    assert not spans.name_supported("A", "Alexandra")
    assert spans.name_supported("Luiz Gustavo Rocco", "LUIZ GUST AVO ROCCO")


def test_no_end_date_is_open_when_written_open_and_one_period_when_a_lone_date():
    run = _Run("x", uuid.uuid4(), [])
    assert run.dates("a", "2019", None, "Acme, 2019 –")[1] is None
    assert run.dates("b", "2019-03", None, "Acme, since 03/2019")[1] is None
    assert run.dates("c", "2019", None, "2019  Intern, Acme")[1] == "2019-12-31"


# --- official facts stay still --------------------------------------------------------------------------------------


def test_linking_a_company_never_rewrites_an_approved_view(session, blobs, org, key):
    result, _ = ingest(session, blobs, org, cv_json())
    step = session.scalar(select(Claim).where(Claim.subject_id == result.subject_id, Claim.claim_type == "CareerStepClaim"))
    step.payload = {**step.payload, "company": {**step.payload["company"], "company_id": None}}
    session.flush()
    review.approve_claim(session, org.id, step.id, "operator")
    pinned = dict(step.approved_view)
    companies.link_org(session, org.id)
    assert step.approved_view == pinned and step.payload["company"]["company_id"]
    from maindscout.api.profiles import _view
    assert _view(step)["company"]["company_id"] == step.payload["company"]["company_id"]


def test_two_approved_places_that_cannot_both_be_true_still_raise_a_card(session, blobs, org, key):
    places = [{"place": "Bristol, UK", "country_code": "GB", "kind": "current", "quote": "Based in Bristol, UK"},
              {"place": "Lyon, France", "country_code": "FR", "kind": "current", "quote": "Lives in Lyon, France"}]
    result, _ = ingest(session, blobs, org, cv_json(locations=places), CV_LINES + ["Lives in Lyon, France"])
    from maindscout.db.models import DecisionItem
    for d in session.scalars(select(Decision).where(Decision.subject_id == result.subject_id, Decision.type == "contradiction")):
        for item in session.scalars(select(DecisionItem).where(DecisionItem.decision_id == d.id)):
            session.delete(item)
        session.flush()
        session.delete(d)  # pretend both were approved without the card
    session.flush()
    for c in session.scalars(select(Claim).where(Claim.subject_id == result.subject_id, Claim.claim_type == "LocationClaim")):
        c.status, c.approved_view = "approved", dict(c.payload)
    session.flush()
    from maindscout.api.process import _contradictions
    raised: list = []
    _contradictions(session, org.id, result.subject_id, raised)
    assert len(raised) == 1


def test_the_same_job_twice_in_one_cv_is_asked_about_but_a_promotion_is_not(session, blobs, org, key):
    twice = [{"company": "Acme Space", "title": "Engineer", "employment_type": "full_time", "location": None,
              "start": "2019-03", "end": "2021-01", "quote": "Engineer, Acme Space, Mar 2019 - Jan 2021"},
             {"company": "Acme Space", "title": "Engineer", "employment_type": "full_time", "location": None,
              "start": "2019-03", "end": "2021-06", "quote": "Engineer, Acme Space, Mar 2019 - Jun 2021"}]
    lines = ["JANE EXAMPLE", "jane.example@example.com", "Engineer, Acme Space, Mar 2019 - Jan 2021",
             "Engineer, Acme Space, Mar 2019 - Jun 2021"]
    r, _ = ingest(session, blobs, org, cv_json(career_steps=twice), lines)
    assert session.scalar(select(Decision).where(Decision.subject_id == r.subject_id, Decision.type == "duplicate_stint"))

    promoted = [dict(twice[0], title="Engineer"), dict(twice[1], title="Senior Engineer",
                                                       quote="Senior Engineer, Acme Space, Mar 2019 - Jun 2021")]
    lines2 = ["OMAR SAMPLE", "omar@example.com", "Engineer, Acme Space, Mar 2019 - Jan 2021",
              "Senior Engineer, Acme Space, Mar 2019 - Jun 2021"]
    r2, _ = ingest(session, blobs, org, cv_json(full_name={"value": "Omar Sample", "quote": "OMAR SAMPLE"},
                                                contacts=[{"kind": "email", "value": "omar@example.com", "quote": "omar@example.com"}],
                                                career_steps=promoted), lines2)
    assert not session.scalar(select(Decision).where(Decision.subject_id == r2.subject_id, Decision.type == "duplicate_stint"))


def test_a_later_file_that_doubts_a_contact_flags_it_while_it_awaits_review(session, blobs, org, key):
    first, _ = ingest(session, blobs, org, cv_json())
    c = session.scalar(select(Claim).where(Claim.subject_id == first.subject_id, Claim.claim_type == "ContactClaim"))
    assert not c.flags.get("possible_ocr_identifier")
    from maindscout.api import process
    from maindscout.db.models import Document, IntelligenceRun
    process._write_claim(session, session.get(Document, first.document_id), session.get(IntelligenceRun, first.run_id),
                         "candidate", first.subject_id, "ContactClaim", c.payload, c.natural_key, None,
                         flags={"possible_ocr_identifier": True})
    assert c.flags.get("possible_ocr_identifier")


# --- matching ------------------------------------------------------------------------------------------------------


def test_a_substitution_note_must_name_the_requirement_not_share_a_word():
    assert not _covers("can substitute for the role", "Senior backend role in fintech")
    assert _covers("can substitute for start-up experience", "Start-up experience")
    assert _covers("can substitute for kubernetes", "Container orchestration", token="kubernetes")


def test_a_band_without_a_job_is_refused_not_ignored(client):
    assert client.get("/v1/inbox", params={"band": "priority"}).status_code == 422
    assert client.get("/v1/inbox").status_code == 200
    assert client.get("/v1/inbox", params={"band": "all"}).status_code == 200


# --- erasure fails loud -------------------------------------------------------------------------------------------


def test_a_later_verify_still_finds_a_file_that_was_not_deleted(session, blobs, org, key):
    result, doc = ingest(session, blobs, org, cv_json())
    data = blobs.get(doc.storage_key)
    erasure.erase_candidate(session, blobs, org.id, result.subject_id, "operator")
    blobs.put(doc.sha256, data)  # the delete "failed"
    survivors = erasure.verify_erasure(session, blobs, org.id, result.subject_id)
    assert any("original file" in s for s in survivors)


def test_erasure_reaches_stray_import_rows_tasks_client_notes_and_outdated_contacts(session, blobs, org, key):
    from maindscout.db.models import Company, ImportBatch
    result, doc = ingest(session, blobs, org, cv_json())
    cid = result.subject_id
    batch = ImportBatch(org_id=org.id, kind="candidates", filename="ats.csv", columns={}, created_by="t")
    session.add(batch)
    session.flush()
    session.add(ImportRow(org_id=org.id, batch_id=batch.id, row_no=1, status="duplicate",
                          data={"name": "Jane Example", "email": "Jane.Example@example.com"}))
    tasks.enqueue(session, org.id, "profile_candidate", {"candidate_id": str(cid)})
    company = session.scalar(select(Company).limit(1))
    session.add(Activity(org_id=org.id, subject_type="company", subject_id=company.id, kind="note",
                         summary="Client liked Jane Example a lot", occurred_at=datetime.now(timezone.utc), created_by="t"))
    contact = session.scalar(select(Claim).where(Claim.subject_id == cid, Claim.claim_type == "ContactClaim"))
    review.reject_claim(session, org.id, contact.id, "operator", code="outdated")
    session.flush()

    record = erasure.erase_candidate(session, blobs, org.id, cid, "operator")
    assert record.survivors == []
    assert count(session, ImportRow, ImportRow.org_id == org.id) == 0
    assert count(session, Task, Task.payload["candidate_id"].astext == str(cid)) == 0
    note = session.scalar(select(Activity).where(Activity.subject_id == company.id))
    assert "Jane Example" not in note.summary and "[erased person]" in note.summary
    assert record.counts["suppressed_identifiers"] == 1, "an outdated email is still theirs: suppressed"


# --- web ---------------------------------------------------------------------------------------------------------


def test_an_uploaded_html_file_never_opens_as_a_page(client):
    page = b"<html><script>fetch('/v1/candidates')</script></html>"
    doc = client.post("/v1/documents", files={"file": ("cv.html", page, "text/html")}, data={"doc_type_hint": "cv"}).json()
    r = client.get(f"/v1/documents/{doc['document_id']}/file")
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["x-content-type-options"] == "nosniff" and "sandbox" in r.headers["content-security-policy"]
    svg = client.post("/v1/documents", files={"file": ("x.pdf", b"\x89PNG\x00\x00", "application/pdf")},
                      data={"doc_type_hint": "cv"}).json()
    r = client.get(f"/v1/documents/{svg['document_id']}/file")
    assert r.headers["content-type"] == "application/octet-stream" and r.headers["content-disposition"].startswith("attachment")


def test_export_cells_cannot_run_as_spreadsheet_formulas(client):
    from tests.test_imports import upload
    batch = upload(client, 'name,email,notes\n"=HYPERLINK(""http://x"")",eve@example.com,hi\n')
    client.post(f"/v1/imports/{batch['id']}/import", json={"row_ids": [r["id"] for r in batch["rows"]]})
    csv_text = client.get("/v1/export/people.csv").text
    assert "'=HYPERLINK" in csv_text and '\n"=HYPERLINK' not in csv_text


def test_an_import_over_the_row_limit_is_refused_out_loud(client, monkeypatch):
    from maindscout.api import imports
    monkeypatch.setattr(imports, "MAX_ROWS", 3)
    rows = "".join(f"P{i},p{i}@example.com\n" for i in range(5))
    r = client.post("/v1/imports", files={"file": ("big.csv", ("name,email\n" + rows).encode(), "text/csv")},
                    data={"kind": "candidates"})
    assert r.status_code == 422 and "more than 3 rows" in r.json()["detail"]


def test_the_mailbox_error_is_encoded_in_the_redirect(client):
    r = client.get("/v1/mailbox/callback/google", params={"error": "x&connected=google"}, follow_redirects=False)
    assert "connected=google" not in r.headers["location"].split("?", 1)[1].split("&")


# --- background tasks ---------------------------------------------------------------------------------------------


def test_a_task_abandoned_while_running_goes_back_in_the_queue(session, org):
    t = tasks.enqueue(session, org.id, "profile_candidate", {"candidate_id": str(uuid.uuid4())}, dedupe_key="x:1")
    t.status, t.started_at, t.attempts = "running", datetime.now(timezone.utc) - timedelta(hours=2), 1
    session.flush()
    assert tasks.reclaim_stale(session) == 1
    assert t.status == "queued" and "abandoned" in t.error
    assert tasks.enqueue(session, org.id, "profile_candidate", {}, dedupe_key="x:1").id == t.id  # still deduped, now runnable


def test_the_desk_can_follow_the_shared_research_it_asked_for(client, session):
    t = tasks.enqueue(session, None, "research_company", {"company_id": str(uuid.uuid4())})
    session.flush()
    assert [r["id"] for r in client.get("/v1/tasks", params={"ids": str(t.id)}).json()] == [str(t.id)]


def test_settings_follow_edits_to_the_env_file(tmp_path, monkeypatch):
    from maindscout import settings
    f = tmp_path / ".env"
    f.write_text("SOME_KEY=one\n", encoding="utf-8")
    monkeypatch.setattr(settings, "ENV_FILE", f)
    monkeypatch.delenv("SOME_KEY", raising=False)
    assert settings.env("SOME_KEY") == "one"
    import os
    f.write_text("SOME_KEY=two\n", encoding="utf-8")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 5))
    assert settings.env("SOME_KEY") == "two"
