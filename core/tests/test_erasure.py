import json
import uuid

import pytest
from sqlalchemy import func, select

from maindscout.api import documents, erasure, process, writer
from maindscout.db.models import (
    Candidate,
    CandidateJob,
    Claim,
    Decision,
    Document,
    DocumentSubject,
    Erasure,
    Evidence,
    ExtractionArtifact,
    SuppressionEntry,
)
from maindscout.intelligence.llm import FakeClient
from maindscout.storage import LocalBlobStore
from tests.pdfs import text_pdf
from tests.test_process import CV_LINES, JD_JSON, JD_LINES, cv_json


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "test-suppression-key")


def ingest(session, blobs, org, data, lines=CV_LINES, doc_type="cv", job_id=None, pdf=None):
    pdf = pdf or text_pdf(lines=lines)
    doc, _ = documents.upload_document(session, blobs, org_id=org.id, data=pdf, filename="cv.pdf",
                                       media_type="application/pdf", doc_type_hint=doc_type)
    return process.process_document(session, blobs, FakeClient(data), org_id=org.id, document_id=doc.id, job_id=job_id), doc


def count(session, model, *where):
    return session.scalar(select(func.count()).select_from(model).where(*where))


def test_erasing_a_one_cv_person_leaves_nothing_and_verify_is_green(session, blobs, org, key):
    jd, _ = ingest(session, blobs, org, JD_JSON, JD_LINES, "jd")
    result, doc = ingest(session, blobs, org, cv_json(), job_id=jd.job_id)
    cid, storage_key = result.subject_id, doc.storage_key

    record = erasure.erase_candidate(session, blobs, org.id, cid, "operator", "candidate asked")
    assert record.survivors == []
    assert count(session, Candidate, Candidate.id == cid) == 0
    assert count(session, Claim, Claim.subject_id == cid) == 0
    assert count(session, CandidateJob, CandidateJob.candidate_id == cid) == 0
    assert count(session, Document, Document.id == doc.id) == 0
    assert count(session, ExtractionArtifact, ExtractionArtifact.document_id == doc.id) == 0
    assert count(session, Evidence, Evidence.document_id == doc.id) == 0
    assert not blobs.exists(storage_key)
    assert erasure.verify_erasure(session, blobs, org.id, cid, [storage_key]) == []


def test_the_job_and_other_people_are_untouched(session, blobs, org, key):
    jd, _ = ingest(session, blobs, org, JD_JSON, JD_LINES, "jd")
    keep, _ = ingest(session, blobs, org, cv_json(), job_id=jd.job_id)
    other = cv_json(full_name={"value": "Sam Other", "quote": "SAM OTHER"},
                    contacts=[{"kind": "email", "value": "sam@example.com", "quote": "sam@example.com"}])
    gone, _ = ingest(session, blobs, org, other, ["SAM OTHER", "sam@example.com"] + CV_LINES[2:], job_id=jd.job_id)
    before = count(session, Claim, Claim.subject_id == keep.subject_id)
    erasure.erase_candidate(session, blobs, org.id, gone.subject_id, "operator")
    assert count(session, Claim, Claim.subject_id == keep.subject_id) == before
    assert count(session, Claim, Claim.subject_id == jd.job_id) > 0


def test_the_erasure_record_holds_no_personal_data(session, blobs, org, key):
    result, _ = ingest(session, blobs, org, cv_json())
    record = erasure.erase_candidate(session, blobs, org.id, result.subject_id, "operator", "asked")
    dumped = json.dumps({"counts": record.counts, "survivors": record.survivors, "docs": record.document_ids}).lower()
    assert "jane" not in dumped and "example.com" not in dumped and "acme" not in dumped
    hashes = session.scalars(select(SuppressionEntry.identifier_hash)).all()
    assert hashes and all("@" not in h and len(h) == 64 for h in hashes)


def test_a_planted_survivor_makes_verify_fail_loudly(session, blobs, org, key):
    result, doc = ingest(session, blobs, org, cv_json())
    cid = result.subject_id
    erasure.erase_candidate(session, blobs, org.id, cid, "operator")
    writer.add_claim(session, org_id=org.id, subject_type="candidate", subject_id=cid, claim_type="SkillClaim",
                     payload={"raw_label": "Rust", "normalized_skill": "rust"})
    survivors = erasure.verify_erasure(session, blobs, org.id, cid, [])
    assert survivors == ["1 claims"]


def test_a_second_record_of_the_same_human_is_reported_not_hidden(session, blobs, org, key):
    result, _ = ingest(session, blobs, org, cv_json())
    twin = Candidate(org_id=org.id)  # the same human, split into two people earlier
    session.add(twin)
    session.flush()
    writer.add_claim(session, org_id=org.id, subject_type="candidate", subject_id=twin.id, claim_type="ContactClaim",
                     payload={"kind": "email", "value": "jane.example@example.com", "normalized": "jane.example@example.com",
                              "attributable": True, "attribution": "subject"})
    record = erasure.erase_candidate(session, blobs, org.id, result.subject_id, "operator")
    assert record.survivors == [f"another person ({twin.id}) has one of the erased identifiers"]


def test_identity_notes_on_other_people_stop_pointing_at_the_erased_person(session, blobs, org, key):
    first, _ = ingest(session, blobs, org, cv_json())
    second, _ = ingest(session, blobs, org, cv_json(contacts=[]), CV_LINES + ["second"])
    note = session.scalar(select(Decision).where(Decision.type == "identity_note"))
    assert str(first.subject_id) in note.context["candidate_ids"]
    record = erasure.erase_candidate(session, blobs, org.id, first.subject_id, "operator")
    assert record.survivors == []
    assert str(first.subject_id) not in note.context["candidate_ids"]


def test_bytes_shared_with_another_org_are_kept_for_them(session, blobs, org, key):
    pdf = text_pdf(lines=CV_LINES)
    mine, my_doc = ingest(session, blobs, org, cv_json(), pdf=pdf)
    other = writer.create_org(session, "other")
    theirs, their_doc = ingest(session, blobs, other, cv_json(), pdf=pdf)
    assert my_doc.storage_key == their_doc.storage_key
    record = erasure.erase_candidate(session, blobs, org.id, mine.subject_id, "operator")
    assert record.survivors == []
    assert blobs.exists(their_doc.storage_key)
    assert count(session, Claim, Claim.subject_id == theirs.subject_id) > 0


def test_an_erased_person_uploaded_again_is_blocked_and_nothing_is_kept(session, blobs, org, key):
    first, _ = ingest(session, blobs, org, cv_json())
    erasure.erase_candidate(session, blobs, org.id, first.subject_id, "operator")
    again, doc = ingest(session, blobs, org, cv_json(), CV_LINES + ["new version"])
    assert again.status == "suppressed"
    assert count(session, Candidate) == 0
    assert count(session, Document, Document.id == again.document_id) == 0
    assert count(session, Claim, Claim.org_id == org.id) == 0
    entry = session.scalar(select(SuppressionEntry))
    assert entry.encounters == 1


def test_without_a_key_erasure_still_completes_and_says_suppression_was_skipped(session, blobs, org, monkeypatch):
    monkeypatch.delenv("SUPPRESSION_KEY", raising=False)
    monkeypatch.setattr("maindscout.api.erasure.env", lambda name, default=None: None)
    result, _ = ingest(session, blobs, org, cv_json())
    record = erasure.erase_candidate(session, blobs, org.id, result.subject_id, "operator")
    assert record.survivors == []
    assert record.counts["suppression_skipped_no_key"] >= 1


def test_entangled_data_refuses_instead_of_half_erasing(session, blobs, org, key):
    result, doc = ingest(session, blobs, org, cv_json())
    session.add(DocumentSubject(document_id=doc.id, subject_type="candidate", subject_id=uuid.uuid4(), org_id=org.id,
                                established_by="test"))
    session.flush()
    with pytest.raises(erasure.ErasureConflict):
        erasure.erase_candidate(session, blobs, org.id, result.subject_id, "operator")
    assert count(session, Candidate, Candidate.id == result.subject_id) == 1


def test_erasing_another_orgs_person_is_not_found(session, blobs, org, key):
    result, _ = ingest(session, blobs, org, cv_json())
    other = writer.create_org(session, "other")
    with pytest.raises(LookupError):
        erasure.erase_candidate(session, blobs, other.id, result.subject_id, "operator")
    assert session.scalar(select(func.count()).select_from(Erasure)) == 0
