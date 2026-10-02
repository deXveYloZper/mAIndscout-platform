from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from maindscout.db.models import Score
from maindscout.domain import coverage
from maindscout.domain.gaps import Fact, gap_table
from tests.test_api import _skill_payload, client, drop_cv, fake, make_job  # noqa: F401 (fixtures)

TODAY = date(2026, 10, 2)


def req(i, token, strength="must"):
    return {"id": f"r{i}", "payload": {"text_raw": token, "category": "skill", "strength": strength, "normalized_token": token}}


def skill(token, status):
    return Fact(token, "SkillClaim", {"raw_label": token, "normalized_skill": token}, status)


def test_coverage_counts_must_haves_resting_on_approved_facts():
    reqs = [req(1, "python"), req(2, "rust"), req(3, "go"), req(4, "sql", strength="nice")]
    thin = coverage.coverage(gap_table(reqs, [skill("python", "approved"), skill("rust", "proposed")], TODAY))
    assert (thin.applicable, thin.official, thin.needed, thin.met) == (3, 1, 2, False)
    assert thin.words() == "1 of 3 must-haves rest on approved facts: below the floor (2 needed)"
    solid = coverage.coverage(gap_table(reqs, [skill("python", "approved"), skill("rust", "approved")], TODAY))
    assert solid.met and "above the floor" in solid.words()
    assert "%" not in thin.words() + solid.words()


def test_a_job_with_no_must_haves_never_claims_coverage():
    c = coverage.coverage(gap_table([req(1, "sql", strength="nice")], [], TODAY))
    assert not c.met and c.applicable == 0


def test_the_breakdown_has_one_dimension_per_requirement_and_no_weights():
    b = coverage.breakdown(gap_table([req(1, "python"), req(2, "rust")], [skill("python", "approved")], TODAY))
    assert [d["requirement_id"] for d in b["dimensions"]] == ["r1", "r2"]
    assert all(d["weight"] is None for d in b["dimensions"])
    assert "value" not in b and "score" not in b


def test_the_database_refuses_any_score_value(session, org):
    from maindscout.db.models import Candidate, Job
    cand, job = Candidate(org_id=org.id), Job(org_id=org.id, title="x")
    session.add_all([cand, job])
    session.flush()
    nested = session.begin_nested()
    session.add(Score(org_id=org.id, candidate_id=cand.id, job_id=job.id, value=0.73, coverage={}, breakdown={},
                      claim_set_hash="x", engine_version="x"))
    with pytest.raises(IntegrityError, match="score_value_reserved"):
        session.flush()
    nested.rollback()


def test_snapshots_are_kept_only_when_the_facts_change(client, session):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    count = lambda: session.scalar(select(func.count()).select_from(Score))
    first = count()
    assert first >= 1
    client.post(f"/v1/documents/{drop_cv(client, job_id)['document_id']}/process", json={"job_id": job_id})
    assert count() == first, "nothing changed, nothing new recorded"
    client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": cid, "claim_type": "SkillClaim",
                                    "payload": _skill_payload("insar")})
    assert count() == first + 1
    assert all(s.value is None for s in session.scalars(select(Score)))


def test_the_gap_page_reports_coverage_in_words(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    page = client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").json()
    assert page["coverage"]["met"] is False and "below the floor" in page["coverage"]["words"]
    people = client.get(f"/v1/jobs/{job_id}").json()["people"]["do_not_submit"]
    assert people[0]["coverage"]["met"] is False
