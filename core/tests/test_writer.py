import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from maindscout.api import writer
from maindscout.db.models import Candidate, CandidateJob, Claim, Document, Job
from maindscout.domain import registry as reg


def _claim(session, org, subject_id, **kw):
    args = dict(org_id=org.id, subject_type="candidate", subject_id=subject_id,
                claim_type="SkillClaim", payload={"skill": "python"})
    args.update(kw)
    return writer.add_claim(session, **args)


def test_claim_is_written_staged_with_registered_flags(session, org, candidate_id):
    claim = _claim(session, org, candidate_id, flags={"possible_ocr_identifier": True})
    assert claim.status == "staged"
    assert claim.flags == {"possible_ocr_identifier": True}


def test_nested_registered_flag_is_accepted(session, org, candidate_id):
    _claim(session, org, candidate_id, claim_type="CareerStepClaim",
           flags={"concurrency": {"overlap_with": ["other"]}})


def test_unknown_flag_key_is_rejected_on_write(session, org, candidate_id):
    with pytest.raises(reg.UnknownFlagError):
        _claim(session, org, candidate_id, flags={"made_up_flag": True})
    assert session.scalars(select(Claim)).first() is None


def test_unknown_claim_type_rejected(session, org, candidate_id):
    with pytest.raises(reg.UnknownClaimTypeError):
        _claim(session, org, candidate_id, claim_type="PersonalityClaim")


def test_claim_type_cannot_describe_wrong_subject(session, org):
    with pytest.raises(reg.UnknownClaimTypeError):
        _claim(session, org, uuid.uuid4(), subject_type="job", claim_type="SkillClaim")


def test_invalid_claim_status_rejected_by_database(session, org, candidate_id):
    nested = session.begin_nested()
    with pytest.raises(IntegrityError):
        _claim(session, org, candidate_id, status="believed")
    nested.rollback()


def _document(org, sha="a" * 64):
    return Document(org_id=org.id, sha256=sha, storage_key=f"k/{sha}", media_type="application/pdf")


def test_same_bytes_cannot_be_stored_twice_in_one_org(session, org):
    session.add(_document(org))
    session.flush()
    nested = session.begin_nested()
    session.add(_document(org))
    with pytest.raises(IntegrityError):
        session.flush()
    nested.rollback()


def test_same_bytes_allowed_in_different_orgs(session, org):
    other = writer.create_org(session, "other")
    session.add_all([_document(org), _document(other)])
    session.flush()


def test_pair_is_unique_and_band_is_not_a_number(session, org):
    cand, job = Candidate(org_id=org.id), Job(org_id=org.id, title="InSAR specialist")
    session.add_all([cand, job])
    session.flush()
    session.add(CandidateJob(org_id=org.id, candidate_id=cand.id, job_id=job.id, triage_band="priority"))
    session.flush()

    nested = session.begin_nested()
    session.add(CandidateJob(org_id=org.id, candidate_id=cand.id, job_id=job.id))
    with pytest.raises(IntegrityError):
        session.flush()
    nested.rollback()

    other = Candidate(org_id=org.id)
    session.add(other)
    session.flush()
    nested = session.begin_nested()
    session.add(CandidateJob(org_id=org.id, candidate_id=other.id, job_id=job.id, triage_band="38%"))
    with pytest.raises(IntegrityError):
        session.flush()
    nested.rollback()
