import pytest
from sqlalchemy import select

from maindscout.api import documents, process
from maindscout.db.models import Candidate, CandidateJob, Claim, Decision, Document, Evidence, Job
from maindscout.intelligence.llm import FakeClient
from maindscout.storage import LocalBlobStore
from tests.pdfs import text_pdf

CV_LINES = [
    "JANE EXAMPLE",
    "jane.example@example.com",
    "Flight Software Engineer, Acme Space, Mar 2019 - Present",
    "Contractor, Gamma Labs, Jun 2020 - Dec 2020",
    "Frontend Developer, Beta Web, Jan 2016 - Feb 2019",
    "Skills: Rust, C++, React",
    "Education: BSc Computer Science, Example University, 2012 - 2015",
    "Based in Bristol, UK",
]


def cv_json(**over):
    data = {
        "full_name": {"value": "Jane Example", "quote": "JANE EXAMPLE"},
        "contacts": [{"kind": "email", "value": "jane.example@example.com", "quote": "jane.example@example.com"}],
        "career_steps": [
            {"company": "Acme Space", "title": "Flight Software Engineer", "employment_type": "full_time", "location": None,
             "start": "2019-03", "end": "present", "quote": "Flight Software Engineer, Acme Space, Mar 2019 - Present"},
            {"company": "Gamma Labs", "title": "Contractor", "employment_type": "contract", "location": None,
             "start": "2020-06", "end": "2020-12", "quote": "Contractor, Gamma Labs, Jun 2020 - Dec 2020"},
            {"company": "Beta Web", "title": "Frontend Developer", "employment_type": "full_time", "location": None,
             "start": "2016-01", "end": "2019-02", "quote": "Frontend Developer, Beta Web, Jan 2016 - Feb 2019"},
        ],
        "education": [{"institution": "Example University", "credential": "BSc", "field": "Computer Science",
                       "level": "bachelor", "start": "2012", "end": "2015",
                       "quote": "Education: BSc Computer Science, Example University, 2012 - 2015"}],
        "skills": [{"label": "Rust", "normalized": "rust", "quote": "Skills: Rust, C++, React"},
                   {"label": "React", "normalized": "react", "quote": "Skills: Rust, C++, React"}],
        "locations": [{"place": "Bristol, UK", "country_code": "GB", "kind": "current", "quote": "Based in Bristol, UK"}],
    }
    data.update(over)
    return data


JD_LINES = [
    "Radar Interferometry Specialist",
    "Catalyst Geo builds satellite analytics.",
    "You must have InSAR processing experience.",
    "Applications close 27 Aug 2026.",
    "Contact: hello@catalyst.example",
]

JD_JSON = {
    "title": {"value": "Radar Interferometry Specialist", "quote": "Radar Interferometry Specialist"},
    "hiring_company": {"value": "Catalyst Geo", "quote": "Catalyst Geo builds satellite analytics."},
    "requirements": [{"text": "InSAR processing experience", "category": "skill", "strength": "must", "token": "insar",
                      "distinctive": True, "quote": "You must have InSAR processing experience."}],
    "process_dates": [{"label": "Applications close", "date": "2026-08-27", "year_written": True, "quote": "Applications close 27 Aug 2026."}],
}


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


def run(session, blobs, org, lines, data, doc_type="cv", job_id=None, mailto=None, **kw):
    pdf = text_pdf(lines=lines * 4 if len(lines) < 8 else lines, mailto=mailto)
    doc, _ = documents.upload_document(session, blobs, org_id=org.id, data=pdf, filename="x.pdf",
                                       media_type="application/pdf", doc_type_hint=doc_type)
    return process.process_document(session, blobs, FakeClient(data), org_id=org.id, document_id=doc.id,
                                    job_id=job_id, **kw), doc


def claims(session, subject_id, claim_type=None):
    q = select(Claim).where(Claim.subject_id == subject_id)
    if claim_type:
        q = q.where(Claim.claim_type == claim_type)
    return list(session.scalars(q))


def test_cv_becomes_proposed_claims_with_evidence_never_approved(session, blobs, org):
    result, doc = run(session, blobs, org, CV_LINES, cv_json())
    assert result.status == "committed" and result.subject_type == "candidate"
    got = claims(session, result.subject_id)
    assert {c.claim_type for c in got} == {"IdentityClaim", "ContactClaim", "CareerStepClaim", "EducationClaim", "SkillClaim", "LocationClaim"}
    assert {c.status for c in got} == {"proposed"}
    assert all(c.approved_view is None for c in got)
    for c in got:
        ev = session.scalars(select(Evidence).where(Evidence.claim_id == c.id)).all()
        assert ev and ev[0].snippet and ev[0].locator["char_end"] > ev[0].locator["char_start"]
    assert doc.status == "processed"


def test_evidence_snippet_is_really_at_its_locator(session, blobs, org):
    result, doc = run(session, blobs, org, CV_LINES, cv_json())
    artifact = documents.extract_document(session, blobs, doc.id)
    for ev in session.scalars(select(Evidence)):
        loc = ev.locator
        assert artifact.content[loc["char_start"]:loc["char_end"]] == ev.snippet


def test_invented_quote_is_blocked_and_reported(session, blobs, org):
    data = cv_json()
    data["career_steps"].append({"company": "Ghost Inc", "title": "CTO", "employment_type": "full_time", "location": None,
                                 "start": "2021-01", "end": "2022-01", "quote": "CTO at Ghost Inc 2021-2022"})
    result, _ = run(session, blobs, org, CV_LINES, data)
    assert not any(c.payload["company"]["raw_name"] == "Ghost Inc" for c in claims(session, result.subject_id, "CareerStepClaim"))
    assert any("not in the document" in f["detail"] for f in result.span_failures)


def test_date_not_in_the_quote_blocks_the_claim(session, blobs, org):
    data = cv_json()
    data["career_steps"][2]["start"] = "2014-01"
    result, _ = run(session, blobs, org, CV_LINES, data)
    companies = {c.payload["company"]["raw_name"] for c in claims(session, result.subject_id, "CareerStepClaim")}
    assert "Beta Web" not in companies
    assert any("not written in the quote" in f["detail"] for f in result.span_failures)


def test_overlap_at_different_companies_is_flagged_and_adjacent_months_are_not(session, blobs, org):
    result, _ = run(session, blobs, org, CV_LINES, cv_json())
    by_company = {c.payload["company"]["raw_name"]: c for c in claims(session, result.subject_id, "CareerStepClaim")}
    assert len(by_company) == 3, "overlapping jobs stay separate claims"
    assert "concurrency.overlap_with" in by_company["Acme Space"].flags
    assert "concurrency.overlap_with" in by_company["Gamma Labs"].flags
    assert "concurrency.overlap_with" not in by_company["Beta Web"].flags  # ends Feb 2019, Acme starts Mar 2019


def test_two_roles_at_one_company_in_one_cv_are_not_fused(session, blobs, org):
    lines = ["JANE EXAMPLE", "Senior Engineer, Acme, Jun 2020 - Present", "Engineer, Acme, Jan 2018 - Jun 2020"]
    data = cv_json(contacts=[], education=[], skills=[], locations=[])
    data["career_steps"] = [
        {"company": "Acme", "title": "Senior Engineer", "employment_type": "full_time", "location": None,
         "start": "2020-06", "end": "present", "quote": "Senior Engineer, Acme, Jun 2020 - Present"},
        {"company": "Acme", "title": "Engineer", "employment_type": "full_time", "location": None,
         "start": "2018-01", "end": "2020-06", "quote": "Engineer, Acme, Jan 2018 - Jun 2020"},
    ]
    result, _ = run(session, blobs, org, lines, data)
    assert len(claims(session, result.subject_id, "CareerStepClaim")) == 2


def test_same_clean_contact_in_a_second_cv_is_the_same_person(session, blobs, org):
    first, _ = run(session, blobs, org, CV_LINES, cv_json())
    second, _ = run(session, blobs, org, CV_LINES + ["Updated CV"], cv_json())
    assert second.subject_id == first.subject_id
    assert len(session.scalars(select(Candidate)).all()) == 1


def test_same_name_without_a_shared_contact_makes_a_new_person_and_a_note(session, blobs, org):
    first, _ = run(session, blobs, org, CV_LINES, cv_json())
    other = cv_json(contacts=[])
    second, _ = run(session, blobs, org, CV_LINES + ["No email on this one"], other)
    assert second.subject_id != first.subject_id
    notes = session.scalars(select(Decision).where(Decision.type == "identity_note")).all()
    assert len(notes) == 1 and str(first.subject_id) in notes[0].context["candidate_ids"]


def test_a_text_email_that_disagrees_with_the_link_is_flagged_and_never_a_match_key(session, blobs, org):
    first, _ = run(session, blobs, org, CV_LINES, cv_json())
    garbled = ["JANE EXAMPLE", "jane.exmple@example.com", "Skills: Rust"]
    data = cv_json(career_steps=[], education=[], locations=[], skills=[])
    data["contacts"] = [{"kind": "email", "value": "jane.exmple@example.com", "quote": "jane.exmple@example.com"}]
    second, _ = run(session, blobs, org, garbled, data, mailto="mailto:jane.example@example.com")
    by_value = {c.payload["normalized"]: c for c in claims(session, second.subject_id, "ContactClaim")}
    assert by_value["jane.exmple@example.com"].flags == {"possible_ocr_identifier": True}
    assert by_value["jane.example@example.com"].flags == {}, "the file's own link is the clean contact"
    # The clean link address is a real key, so this is the same person as the first CV.
    assert second.subject_id == first.subject_id


def test_a_flagged_identifier_alone_is_never_a_match_key(session, blobs, org):
    first, _ = run(session, blobs, org, CV_LINES, cv_json())
    garbled = ["JANE EXAMPLE", "jane.exmple@example.com", "Skills: Rust"]
    data = cv_json(career_steps=[], education=[], locations=[], skills=[])
    data["contacts"] = [{"kind": "email", "value": "jane.exmple@example.com", "quote": "jane.exmple@example.com"}]
    second, _ = run(session, blobs, org, garbled, data)
    assert second.subject_id != first.subject_id


def test_same_company_overlap_across_documents_is_flagged_not_merged(session, blobs, org):
    run(session, blobs, org, CV_LINES, cv_json())
    other = cv_json()
    other["career_steps"] = [{"company": "Acme Space", "title": "Software Lead", "employment_type": "full_time",
                              "location": None, "start": "2019-05", "end": "present",
                              "quote": "Flight Software Engineer, Acme Space, Mar 2019 - Present"}]
    other["career_steps"][0]["quote"] = "Flight Software Engineer, Acme Space, Mar 2019 - Present"
    other["career_steps"][0]["start"] = "2019-03"
    second, _ = run(session, blobs, org, CV_LINES + ["Second version"], other)
    # Same key -> an observation on the same claim, not a second claim.
    assert len(claims(session, second.subject_id, "CareerStepClaim")) == 3


def test_jd_becomes_a_job_with_requirements_company_and_stale_flag(session, blobs, org):
    result, doc = run(session, blobs, org, JD_LINES, JD_JSON, doc_type="jd")
    job = session.get(Job, result.job_id)
    assert job.title == "Radar Interferometry Specialist" and job.hiring_company == "Catalyst Geo"
    reqs = claims(session, job.id, "JobRequirementClaim")
    assert any(c.payload.get("distinctive") for c in reqs)
    stale = [c for c in reqs if c.flags.get("job_process_stale")]
    assert len(stale) == 1 and doc.as_of.year >= 2026
    assert not session.scalars(select(Candidate)).all(), "a job ad's footer contact is not a person"


def test_cv_onto_a_job_gets_a_band_and_a_reason_never_a_number(session, blobs, org):
    jd, _ = run(session, blobs, org, JD_LINES, JD_JSON, doc_type="jd")
    result, _ = run(session, blobs, org, CV_LINES, cv_json(), job_id=jd.job_id)
    assert result.band == "do_not_submit" and result.reason == "no_support_for_must_have:insar"
    pair = session.scalar(select(CandidateJob))
    assert pair.triage_band == "do_not_submit"


def test_a_specialist_cv_is_priority(session, blobs, org):
    jd, _ = run(session, blobs, org, JD_LINES, JD_JSON, doc_type="jd")
    data = cv_json()
    data["skills"] = [{"label": "InSAR", "normalized": "insar", "quote": "Skills: Rust, C++, React"}]
    result, _ = run(session, blobs, org, CV_LINES, data, job_id=jd.job_id)
    assert result.band == "priority"


def test_processing_twice_does_not_duplicate_and_can_triage_for_another_job(session, blobs, org):
    first, doc = run(session, blobs, org, CV_LINES, cv_json())
    count = len(claims(session, first.subject_id))
    jd, _ = run(session, blobs, org, JD_LINES, JD_JSON, doc_type="jd")
    again = process.process_document(session, blobs, FakeClient({}), org_id=org.id, document_id=doc.id, job_id=jd.job_id)
    assert again.reused and again.subject_id == first.subject_id and again.band == "do_not_submit"
    assert len(claims(session, first.subject_id)) == count


def test_a_document_that_is_neither_cv_nor_jd_needs_a_human(session, blobs, org):
    result, doc = run(session, blobs, org, CV_LINES, cv_json(), doc_type="other")
    assert result.status == "needs_human" and doc.status == "needs_human"


def test_process_date_without_a_year_takes_the_documents_year_and_marks_the_assumption(session, blobs, org):
    from datetime import date
    lines = ["Hackathon Engineer", "Dates: London 26.08, Berlin 27.08", "You must have React."]
    data = {
        "title": {"value": "Hackathon Engineer", "quote": "Hackathon Engineer"},
        "hiring_company": None,
        "requirements": [],
        "process_dates": [{"label": "Hackathon London", "date": "2024-08-26", "year_written": False,
                           "quote": "Dates: London 26.08, Berlin 27.08"}],
    }
    result, doc = run(session, blobs, org, lines, data, doc_type="jd")
    claim = claims(session, result.job_id, "JobRequirementClaim")[0]
    assert claim.payload["normalized_token"] == f"{doc.as_of.year}-08-26"
    assert "year taken from the document date" in claim.payload["text_raw"]
    assert bool(claim.flags.get("job_process_stale")) == (date(doc.as_of.year, 8, 26) < doc.as_of)


def test_a_year_the_model_invented_is_blocked_when_it_claims_the_year_was_written(session, blobs, org):
    lines = ["Hackathon Engineer", "Dates: London 26.08", "x"]
    data = {"title": {"value": "Hackathon Engineer", "quote": "Hackathon Engineer"}, "hiring_company": None,
            "requirements": [], "process_dates": [{"label": "L", "date": "2024-08-26", "year_written": True,
                                                    "quote": "Dates: London 26.08"}]}
    result, _ = run(session, blobs, org, lines, data, doc_type="jd")
    assert not claims(session, result.job_id, "JobRequirementClaim")
    assert any("not written" in f["detail"] for f in result.span_failures)


def test_a_job_with_no_stated_end_is_not_treated_as_current(session, blobs, org):
    lines = ["JANE EXAMPLE", "Student Developer, Tiny Co, 2015", "Engineer, Acme, Jan 2018 - Present"]
    data = cv_json(contacts=[], education=[], skills=[], locations=[])
    data["career_steps"] = [
        {"company": "Tiny Co", "title": "Student Developer", "employment_type": "internship", "location": None,
         "start": "2015", "end": None, "quote": "Student Developer, Tiny Co, 2015"},
        {"company": "Acme", "title": "Engineer", "employment_type": "full_time", "location": None,
         "start": "2018-01", "end": "present", "quote": "Engineer, Acme, Jan 2018 - Present"},
    ]
    result, _ = run(session, blobs, org, lines, data)
    by = {c.payload["company"]["raw_name"]: c for c in claims(session, result.subject_id, "CareerStepClaim")}
    assert by["Tiny Co"].valid_to.isoformat() == "2015-12-31"
    assert by["Acme"].valid_to is None
    assert not by["Tiny Co"].flags and not by["Acme"].flags, "no false concurrency"
