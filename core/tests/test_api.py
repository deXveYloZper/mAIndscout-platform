import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from maindscout.api import app as api
from maindscout.api import auth, writer
from maindscout.db.models import Claim, Decision
from maindscout.intelligence.llm import LLMResult
from maindscout.storage import LocalBlobStore
from tests.pdfs import text_pdf
from tests.test_process import CV_LINES, JD_JSON, JD_LINES, cv_json

from tests.conftest import OWNER, PASSWORD, TOTP  # noqa: E402,F401 (the owner fixture lives in conftest)


class RoutingFake:
    """Answers CV and JD extraction with different canned data."""

    model = "fake-model"

    def __init__(self, cv=None, jd=None):
        self.cv, self.jd = cv or cv_json(), jd or JD_JSON

    def complete_json(self, system, user, schema, name):
        return LLMResult(self.cv if name == "cv_extraction" else self.jd, self.model, 0, 0, 0.0)


@pytest.fixture
def fake():
    return RoutingFake()


def signed_in(session, user, org_id) -> str:
    return auth._start_session(session, user, org_id)["token"]


@pytest.fixture
def client(session, org, tmp_path, fake, owner):
    api.app.dependency_overrides[api.get_session] = lambda: session
    api.app.dependency_overrides[api.get_blobs] = lambda: LocalBlobStore(tmp_path)
    api.app.dependency_overrides[api.get_llm] = lambda: fake
    c = TestClient(api.app)
    c.headers.update({"Authorization": f"Bearer {signed_in(session, owner, org.id)}", "X-Org-Id": str(org.id)})
    yield c
    api.app.dependency_overrides.clear()


def pdf_file(lines, name="x.pdf"):
    return {"file": (name, text_pdf(lines=lines * 4 if len(lines) < 8 else lines), "application/pdf")}


def make_job(client):
    r = client.post("/v1/jobs", files=pdf_file(JD_LINES, "jd.pdf"))
    assert r.status_code == 201, r.text
    return r.json()["job_id"]


def drop_cv(client, job_id, lines=CV_LINES, name="cv.pdf"):
    r = client.post(f"/v1/jobs/{job_id}/documents", files=pdf_file(lines, name))
    assert r.status_code == 201, r.text
    return r.json()


# --- access ---------------------------------------------------------------------------------------


def test_health_needs_no_token(client):
    assert TestClient(api.app).get("/v1/health").json() == {"status": "ok"}


def test_a_session_is_required_and_the_desk_must_be_yours(client, org):
    bare = TestClient(api.app)
    token = client.headers["Authorization"]
    assert bare.get("/v1/jobs").status_code == 401
    assert bare.get("/v1/jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert bare.get("/v1/jobs", headers={"Authorization": token}).status_code == 200  # the session's own desk
    assert bare.get("/v1/jobs", headers={"Authorization": token, "X-Org-Id": str(uuid.uuid4())}).status_code == 403


def test_another_desks_data_is_refused(client, session):
    job_id = make_job(client)
    other = writer.create_org(session, "other")
    r = client.get(f"/v1/jobs/{job_id}", headers={"X-Org-Id": str(other.id)})
    assert r.status_code == 403


# --- documents and jobs ---------------------------------------------------------------------------


def test_upload_reuses_by_hash_and_serves_the_original(client):
    data = text_pdf(lines=CV_LINES)
    first = client.post("/v1/documents", files={"file": ("x.pdf", data, "application/pdf")}, data={"doc_type_hint": "cv"}).json()
    second = client.post("/v1/documents", files={"file": ("x.pdf", data, "application/pdf")}, data={"doc_type_hint": "cv"}).json()
    assert second["reused"] and second["document_id"] == first["document_id"]
    original = client.get(f"/v1/documents/{first['document_id']}/file")
    assert original.status_code == 200 and original.content.startswith(b"%PDF")


def test_unsupported_file_is_refused(client):
    r = client.post("/v1/documents", files={"file": ("a.png", b"\x89PNG", "image/png")}, data={"doc_type_hint": "cv"})
    doc = r.json()["document_id"]
    assert client.post(f"/v1/documents/{doc}/process").status_code == 415


def test_job_from_an_ad_shows_requirements_and_a_stale_warning(client):
    job_id = make_job(client)
    page = client.get(f"/v1/jobs/{job_id}").json()
    assert page["title"] == "Radar Interferometry Specialist" and page["hiring_company"] == "Catalyst Geo"
    assert page["process_stale"] is True
    assert any(r["payload"].get("distinctive") for r in page["requirements"])
    assert client.get("/v1/jobs").json()[0]["id"] == job_id


def test_cv_dropped_on_a_job_is_banded_and_grouped(client):
    job_id = make_job(client)
    result = drop_cv(client, job_id)
    assert result["band"] == "do_not_submit" and result["reason"] == "no_support_for_must_have:insar"
    people = client.get(f"/v1/jobs/{job_id}").json()["people"]
    assert [p["name"] for p in people["do_not_submit"]] == ["Jane Example"]
    assert people["priority"] == []
    assert client.get("/v1/jobs").json()[0]["bands"]["do_not_submit"] == 1


def test_person_page_lists_facts_with_snippets_and_jobs(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    page = client.get(f"/v1/candidates/{cid}").json()
    assert page["name"] == "Jane Example"
    careers = page["claims"]["CareerStepClaim"]
    assert len(careers) == 3 and all(c["evidence"][0]["snippet"] for c in careers)
    assert page["jobs"][0]["band"] == "do_not_submit"
    assert page["documents"][0]["filename"] == "cv.pdf"


def test_band_override_sticks_through_reprocessing(client):
    job_id = make_job(client)
    result = drop_cv(client, job_id)
    cid, doc = result["subject_id"], result["document_id"]
    r = client.post(f"/v1/jobs/{job_id}/people/{cid}/triage", json={"band": "priority", "reason": "knows the team"})
    assert r.json()["band"] == "priority"
    client.post(f"/v1/documents/{doc}/process", json={"job_id": job_id})
    assert client.get(f"/v1/jobs/{job_id}/people", params={"band": "priority"}).json()[0]["candidate_id"] == cid
    assert client.post(f"/v1/jobs/{job_id}/people/{cid}/triage", json={"band": "73%"}).status_code == 422


# --- review ---------------------------------------------------------------------------------------


def test_approve_pins_the_view_and_reject_keeps_a_reason(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    claims = client.get(f"/v1/candidates/{cid}/claims").json()
    skill = next(c for c in claims if c["claim_type"] == "SkillClaim")
    approved = client.post(f"/v1/claims/{skill['id']}/approve").json()
    assert approved["status"] == "approved" and approved["approved_view"] == skill["payload"]
    assert client.post(f"/v1/claims/{skill['id']}/approve").status_code == 422, "approving twice is refused"
    other = next(c for c in claims if c["claim_type"] == "LocationClaim")
    assert client.post(f"/v1/claims/{other['id']}/reject", json={"code": "wrong"}).json()["status"] == "rejected"
    assert client.post(f"/v1/claims/{other['id']}/reject", json={"code": "meh"}).status_code == 422


def test_a_typed_contact_is_born_approved_replaces_the_suspect_one_and_becomes_a_key(client, fake):
    job_id = make_job(client)
    fake.cv = cv_json(career_steps=[], education=[], locations=[], skills=[],
                      contacts=[{"kind": "email", "value": "jane.exmple@example.com", "quote": "jane.exmple@example.com"}])
    first = drop_cv(client, job_id, ["JANE EXAMPLE", "jane.exmple@example.com", "x"], "a.pdf")
    cid = first["subject_id"]
    inbox = client.get("/v1/inbox", params={"job_id": job_id, "band": "all"}).json()
    suspect = [i for i in inbox if i["kind"] == "ocr_contact"]
    # No link in this file, so the misspelling is caught by the name check.
    assert suspect and suspect[0]["blocking"]
    bad_id = suspect[0]["claim"]["claim_id"]
    r = client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": cid, "claim_type": "ContactClaim",
                                        "payload": {"kind": "email", "value": "jane.example@example.com",
                                                    "normalized": "jane.example@example.com"}, "replaces": bad_id})
    assert r.status_code == 201 and r.json()["status"] == "approved"
    assert not [i for i in client.get("/v1/inbox", params={"job_id": job_id, "band": "all"}).json() if i["kind"] == "ocr_contact"]
    # A later CV with the typed address now finds the same person.
    fake.cv = cv_json()
    second = drop_cv(client, job_id, CV_LINES + ["v2"], "b.pdf")
    assert second["subject_id"] == cid


def test_a_typed_claim_with_an_invented_field_is_refused(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    r = client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": cid, "claim_type": "SkillClaim",
                                        "payload": {"raw_label": "Charm", "normalized_skill": "charm", "culture_fit": 9}})
    assert r.status_code == 422


def test_inbox_defaults_to_priority_people_and_hides_do_not_submit(client, fake):
    job_id = make_job(client)
    fake.cv = cv_json(contacts=[])
    drop_cv(client, job_id, CV_LINES + ["a"], "a.pdf")
    drop_cv(client, job_id, CV_LINES + ["b"], "b.pdf")  # same name, no shared contact -> identity note
    assert client.get("/v1/inbox", params={"job_id": job_id}).json() == []
    everyone = client.get("/v1/inbox", params={"job_id": job_id, "band": "do_not_submit"}).json()
    assert [i["kind"] for i in everyone] == ["identity_note"] and everyone[0]["blocking"]


def test_contradiction_pick_approves_one_and_rejects_the_other(client, fake, session):
    job_id = make_job(client)
    data = cv_json()
    data["locations"] = [
        {"place": "Bristol, UK", "country_code": "GB", "kind": "current", "quote": "Based in Bristol, UK"},
        {"place": "Lyon, France", "country_code": "FR", "kind": "current", "quote": "Lyon, France"},
    ]
    fake.cv = data
    cid = drop_cv(client, job_id, CV_LINES + ["Lyon, France"])["subject_id"]
    card = next(i for i in client.get("/v1/inbox", params={"job_id": job_id, "band": "all"}).json() if i["kind"] == "contradiction")
    pick = card["left"]["claim_id"]
    client.post(f"/v1/decisions/{card['id']}/resolve", json={"action": "pick", "claim_id": pick})
    statuses = {c["id"]: c["status"] for c in client.get(f"/v1/candidates/{cid}/claims").json() if c["claim_type"] == "LocationClaim"}
    assert statuses[pick] == "approved" and statuses[card["right"]["claim_id"]] == "rejected"
    assert client.post(f"/v1/decisions/{card['id']}/resolve", json={"action": "pick", "claim_id": pick}).status_code == 422


def test_duplicate_stint_same_folds_the_newer_into_the_older(client, fake, session):
    job_id = make_job(client)
    first = drop_cv(client, job_id)
    other = cv_json()
    other["career_steps"] = [{"company": "Acme Space", "title": "Software Lead", "employment_type": "full_time",
                              "location": None, "start": "2019-05", "end": "present", "quote": "Software Lead, Acme Space, May 2019 - Present"}]
    fake.cv = other
    drop_cv(client, job_id, CV_LINES + ["Software Lead, Acme Space, May 2019 - Present"], "v2.pdf")
    card = next(i for i in client.get("/v1/inbox", params={"job_id": job_id, "band": "all"}).json() if i["kind"] == "duplicate_stint")
    client.post(f"/v1/decisions/{card['id']}/resolve", json={"action": "same"})
    careers = [c for c in client.get(f"/v1/candidates/{first['subject_id']}/claims").json() if c["claim_type"] == "CareerStepClaim"]
    acme = [c for c in careers if c["payload"]["company"]["raw_name"] == "Acme Space"]
    assert sorted(c["status"] for c in acme) == ["proposed", "superseded"]
    kept = next(c for c in acme if c["status"] == "proposed")
    assert "possible_duplicate_stint" not in kept["flags"] and len(kept["evidence"]) == 2


def test_revision_diff_keeps_the_approved_view_until_a_human_accepts(client, fake, session):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    acme = next(c for c in client.get(f"/v1/candidates/{cid}/claims").json()
                if c["claim_type"] == "CareerStepClaim" and c["payload"]["company"]["raw_name"] == "Acme Space")
    client.post(f"/v1/claims/{acme['id']}/approve")
    changed = cv_json()
    changed["career_steps"][0]["title"] = "Principal Flight Software Engineer"
    fake.cv = changed
    drop_cv(client, job_id, CV_LINES + ["v2"], "v2.pdf")
    card = next(i for i in client.get("/v1/inbox", params={"job_id": job_id, "band": "all"}).json() if i["kind"] == "revision_diff")
    assert card["changed_paths"] == ["title_raw"]
    claim = session.get(Claim, uuid.UUID(acme["id"]))
    assert claim.approved_view["title_raw"] == "Flight Software Engineer", "the official view did not move"
    client.post(f"/v1/decisions/{card['id']}/resolve", json={"action": "accept_new"})
    session.refresh(claim)
    assert claim.approved_view["title_raw"] == "Principal Flight Software Engineer"
    assert session.get(Decision, uuid.UUID(card["id"])).sealed_at is not None



def test_erase_route_reports_clean_and_verify_agrees(client, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    r = client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "asked"}).json()
    assert r["clean"] is True and r["survivors"] == [] and r["counts"]["claims"] > 0
    assert client.get(f"/v1/subjects/candidate/{cid}/erase/verify").json() == {"clean": True, "survivors": []}
    assert client.get(f"/v1/candidates/{cid}").status_code == 404
    assert client.get(f"/v1/jobs/{job_id}").json()["people"]["do_not_submit"] == []


def test_verify_for_someone_never_erased_is_not_found(client):
    assert client.get(f"/v1/subjects/candidate/{uuid.uuid4()}/erase/verify").status_code == 404



def test_a_cv_without_a_job_joins_the_pool_and_can_be_put_on_a_job_later(client):
    r = client.post("/v1/candidates", files=pdf_file(CV_LINES, "pool.pdf"))
    assert r.status_code == 201 and r.json()["band"] is None
    cid = r.json()["subject_id"]
    pool = client.get("/v1/candidates", params={"unassigned": True}).json()
    assert [p["id"] for p in pool] == [cid]
    job_id = make_job(client)
    placed = client.post(f"/v1/jobs/{job_id}/people/{cid}").json()
    assert placed["band"] == "do_not_submit" and placed["reused"] is True
    assert client.get("/v1/candidates", params={"unassigned": True}).json() == []
    assert client.get("/v1/candidates").json()[0]["jobs"][0]["band"] == "do_not_submit"



def test_gap_table_lists_every_requirement_with_a_status_and_never_a_number(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    page = client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").json()
    assert page["person"]["name"] == "Jane Example" and page["band"] == "do_not_submit"
    insar = next(r for r in page["rows"] if r["requirement"] == "InSAR processing experience")
    assert insar["status"] == "missing" and insar["distinctive"] is True and insar["official"] is False
    assert set(page["counts"]) == {"evidence", "missing", "conflict", "question"}
    assert not any(k in page for k in ("score", "fit", "total"))
    people = client.get(f"/v1/jobs/{job_id}").json()["people"]["do_not_submit"]
    assert people[0]["gaps"]["missing"] >= 1


def test_gap_table_for_someone_not_on_the_job_is_not_found(client):
    job_id = make_job(client)
    r = client.post("/v1/candidates", files=pdf_file(CV_LINES, "pool.pdf")).json()
    assert client.get(f"/v1/jobs/{job_id}/people/{r['subject_id']}/gaps").status_code == 404



def _skill_payload(token):
    return {"raw_label": token.upper(), "normalized_skill": token}


def test_typing_a_missing_must_have_moves_the_band_and_records_why(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    before = client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").json()
    assert before["band"] == "do_not_submit"
    r = client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": cid, "claim_type": "SkillClaim",
                                        "payload": _skill_payload("insar")})
    assert r.status_code == 201
    after = client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").json()
    assert after["band"] == "priority" and after["reason"] == "supported:insar"
    insar = next(row for row in after["rows"] if row["token"] == "insar")
    assert insar["status"] == "evidence" and insar["official"] is True
    last = after["history"][-1]
    assert (last["from"], last["to"], last["cause"]["act"], last["actor"]) == ("do_not_submit", "priority", "typed", OWNER)
    assert after["history"][0]["cause"]["act"] == "document_processed"


def test_rejecting_the_only_supporting_skill_moves_the_band_back(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    typed = client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": cid, "claim_type": "SkillClaim",
                                            "payload": _skill_payload("insar")}).json()
    client.post(f"/v1/claims/{typed['id']}/reject", json={"code": "wrong"})
    page = client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").json()
    assert page["band"] == "do_not_submit" and page["history"][-1]["cause"]["act"] == "reject"


def test_a_band_set_by_hand_is_never_changed_by_new_facts(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    client.post(f"/v1/jobs/{job_id}/people/{cid}/triage", json={"band": "review_later", "reason": "talk first"})
    client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": cid, "claim_type": "SkillClaim",
                                    "payload": _skill_payload("insar")})
    page = client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").json()
    assert page["band"] == "review_later"
    assert page["history"][-1]["cause"]["act"] == "override"


def test_rejecting_a_jobs_distinctive_requirement_re_triages_everyone_on_it(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    req = next(r for r in client.get(f"/v1/jobs/{job_id}").json()["requirements"] if r["payload"].get("distinctive"))
    client.post(f"/v1/claims/{req['id']}/reject", json={"code": "wrong"})
    page = client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").json()
    assert page["band"] == "review_later" and page["reason"] == "no_distinctive_requirements"
    assert page["history"][-1]["cause"]["claim_type"] == "JobRequirementClaim"


def test_erasure_takes_the_pair_history_with_it(client, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    r = client.post(f"/v1/subjects/candidate/{cid}/erase", json={}).json()
    assert r["clean"] and r["counts"]["pair_history"] >= 1


def test_a_pair_moves_through_states_with_reasons_and_every_move_is_recorded(client):
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    base = f"/v1/jobs/{job_id}/people/{cid}"
    assert client.get(f"{base}/gaps").json()["state"] == "new"
    assert client.post(f"{base}/state", json={"state": "seen"}).json()["state"] == "seen"
    assert client.post(f"{base}/state", json={"state": "we_passed"}).status_code == 422, "passing needs a reason"
    assert client.post(f"{base}/state", json={"state": "we_passed", "reason": "vibes"}).status_code == 422
    r = client.post(f"{base}/state", json={"state": "we_passed", "reason": "skills", "note": "no radar work"}).json()
    assert r["state"] == "we_passed" and r["outcome"]["reason"] == "skills"
    assert client.post(f"{base}/state", json={"state": "seen"}).status_code == 422, "reopening needs a note"
    client.post(f"{base}/state", json={"state": "seen", "note": "client widened the brief"})
    assert client.post(f"{base}/state", json={"state": "submitted"}).status_code == 422, "submitting needs a note"
    client.post(f"{base}/state", json={"state": "submitted", "note": "sent to hiring manager"})
    states = [(e["from"], e["to"]) for e in client.get(f"{base}/gaps").json()["history"] if e["kind"] == "state"]
    assert states == [("new", "seen"), ("seen", "we_passed"), ("we_passed", "seen"), ("seen", "submitted")]
    assert client.post(f"{base}/state", json={"state": "new"}).status_code == 422


def test_a_pair_cannot_be_deleted(client, session):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    job_id = make_job(client)
    cid = drop_cv(client, job_id)["subject_id"]
    assert client.delete(f"/v1/jobs/{job_id}/people/{cid}").status_code == 405, "there is no delete route"
    nested = session.begin_nested()
    with pytest.raises(DBAPIError, match="permanent"):
        session.execute(text("DELETE FROM candidate_job WHERE candidate_id = :c"), {"c": cid})
    nested.rollback()
    assert client.get(f"/v1/jobs/{job_id}/people/{cid}/gaps").status_code == 200


def test_a_cv_with_no_readable_text_waits_for_a_person_instead_of_do_not_submit(client, fake, session):
    """2026-10-08 golden eval: an image-only CV (Bianca) was put in do_not_submit for "no evidence of JavaScript"."""
    from tests.pdfs import blank_pdf

    job_id = make_job(client)  # InSAR is a distinctive must-have
    fake.cv = cv_json(full_name={"value": "", "quote": ""}, contacts=[], career_steps=[], education=[], skills=[], locations=[])
    r = client.post(f"/v1/jobs/{job_id}/documents", files={"file": ("photo-cv.pdf", blank_pdf(), "application/pdf")})
    assert r.status_code == 201, r.text
    assert (r.json()["band"], r.json()["reason"]) == ("review_later", "cv_unreadable")


def test_a_career_step_quoted_in_pieces_is_kept_and_says_so(client, fake, session):
    from maindscout.db.models import Evidence

    job_id = make_job(client)
    data = cv_json()
    step = data["career_steps"][0]
    step["quote"] = "Mar 2019 - Present\n\nFlight Software Engineer, Acme Space"  # the date and the title, apart
    fake.cv = data
    cid = drop_cv(client, job_id)["subject_id"]
    claim = session.scalar(select(Claim).where(Claim.subject_id == uuid.UUID(cid), Claim.claim_type == "CareerStepClaim",
                                               Claim.payload["company"]["raw_name"].astext == "Acme Space"))
    ev = session.scalar(select(Evidence).where(Evidence.claim_id == claim.id))
    assert claim.status == "proposed" and len(ev.locator["parts"]) == 2
    assert ev.span_validation["tier"] == "assembled" and "pieced together from 2 places" in ev.span_validation["detail"]
    assert ev.snippet == "Mar 2019 - Present … Flight Software Engineer, Acme Space"
