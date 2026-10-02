"""Live check: every real CV and job ad goes through the whole pipeline with the real model.

Costs a few cents per run, so it only runs when RUN_LIVE=1 and the artifacts folder and XAI_API_KEY exist.
The rule for real files: every CV must satisfy the general invariants below. A failure is a problem
in the platform, not in the file. Nothing from the folder is copied into the repo.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import documents, process, writer
from maindscout.db.models import Candidate, CandidateJob, Claim, Decision, Evidence, ExtractionArtifact, Job
from maindscout.intelligence.llm import XaiClient, load_env_key
from maindscout.storage import LocalBlobStore

FOLDER = Path(os.environ.get("TEST_ARTIFACTS", Path.home() / "Downloads" / "test_artifacts"))
FILES = sorted(FOLDER.glob("*.pdf")) if FOLDER.exists() else []
JD_FILES = [f for f in FILES if "catalyst" in f.name.lower() or "careers at" in f.name.lower()]
CV_FILES = [f for f in FILES if f not in JD_FILES]

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1" or not FILES or not load_env_key(),
    reason="set RUN_LIVE=1 with test_artifacts and XAI_API_KEY to run the live check",
)


@pytest.fixture(scope="module")
def world(engine, tmp_path_factory):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(conn, join_transaction_mode="create_savepoint")
    writer.seed_registries(session)
    org = writer.create_org(session, "live")
    blobs, client = LocalBlobStore(tmp_path_factory.mktemp("blobs")), XaiClient()

    def ingest(path, doc_type, job_id=None):
        doc, _ = documents.upload_document(session, blobs, org_id=org.id, data=path.read_bytes(), filename=path.name,
                                           media_type="application/pdf", doc_type_hint=doc_type)
        return doc, process.process_document(session, blobs, client, org_id=org.id, document_id=doc.id, job_id=job_id)

    jobs = {path.name: ingest(path, "jd")[1] for path in JD_FILES}
    people = {}
    for path in CV_FILES:
        doc, first = ingest(path, "cv", next(iter(jobs.values())).job_id)
        for job in list(jobs.values())[1:]:
            process.process_document(session, blobs, client, org_id=org.id, document_id=doc.id, job_id=job.job_id)
        people[path.name] = (doc, first)
    yield {"session": session, "org": org, "jobs": jobs, "people": people}
    session.close()
    trans.rollback()
    conn.close()


@pytest.mark.parametrize("path", CV_FILES, ids=[p.name[:30] for p in CV_FILES])
def test_each_cv_is_a_person_with_a_history_and_defensible_evidence(world, path):
    session = world["session"]
    doc, result = world["people"][path.name]
    assert result.status == "committed" and result.subject_type == "candidate"
    claims = list(session.scalars(select(Claim).where(Claim.subject_id == result.subject_id)))
    assert {c.status for c in claims} == {"proposed"}, "nothing is believed before a human acts"
    assert any(c.claim_type == "CareerStepClaim" for c in claims)
    has_name = any(c.claim_type == "IdentityClaim" for c in claims)
    notes = session.scalars(select(Decision).where(Decision.subject_id == result.subject_id, Decision.type == "identity_note")).all()
    assert has_name or notes, "no name must come with an identity note for a human"
    artifact = session.scalar(select(ExtractionArtifact).where(ExtractionArtifact.document_id == doc.id))
    for ev in session.scalars(select(Evidence).where(Evidence.document_id == doc.id)):
        loc = ev.locator or {}
        if loc.get("char_start") is not None:
            assert artifact.content[loc["char_start"]:loc["char_end"]] == ev.snippet
    total = len(result.claim_ids) + len(result.span_failures)
    assert len(result.span_failures) <= 0.4 * total, "too many model claims failed the span check"


def test_one_person_per_cv_never_a_merge_and_job_footers_are_not_people(world):
    session = world["session"]
    assert len(session.scalars(select(Candidate)).all()) == len(CV_FILES)


def test_every_pair_has_a_band_and_a_reason_and_no_number(world):
    session = world["session"]
    pairs = session.scalars(select(CandidateJob)).all()
    assert len(pairs) == len(CV_FILES) * len(JD_FILES)
    for pair in pairs:
        assert pair.triage_band in {"priority", "review_later", "do_not_submit"}
        assert pair.triage_reason and not any(ch.isdigit() and "%" in pair.triage_reason for ch in pair.triage_reason)


def test_the_hiring_company_is_the_employer_not_the_careers_platform(world):
    session = world["session"]
    for result in world["jobs"].values():
        job = session.get(Job, result.job_id)
        assert job.hiring_company is None or "revolut" not in job.hiring_company.lower()


def test_the_specialist_ad_does_not_prioritise_people_without_the_specialism(world):
    session = world["session"]
    catalyst = next((r for n, r in world["jobs"].items() if "catalyst" in n.lower()), None)
    if catalyst is None:
        pytest.skip("no Catalyst ad")
    for pair in session.scalars(select(CandidateJob).where(CandidateJob.job_id == catalyst.job_id)):
        if pair.triage_band == "priority":
            assert pair.triage_reason.startswith("supported:")
