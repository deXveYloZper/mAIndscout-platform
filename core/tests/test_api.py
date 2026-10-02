import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from maindscout.api import app as api
from maindscout.api import writer
from maindscout.db.models import Claim, Decision
from maindscout.intelligence.llm import LLMResult
from maindscout.storage import LocalBlobStore
from tests.pdfs import text_pdf
from tests.test_process import CV_LINES, JD_JSON, JD_LINES, cv_json

TOKEN = "test-token"


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


@pytest.fixture
def client(session, org, tmp_path, fake, monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", TOKEN)
    api.app.dependency_overrides[api.get_session] = lambda: session
    api.app.dependency_overrides[api.get_blobs] = lambda: LocalBlobStore(tmp_path)
    api.app.dependency_overrides[api.get_llm] = lambda: fake
    c = TestClient(api.app)
    c.headers.update({"Authorization": f"Bearer {TOKEN}", "X-Org-Id": str(org.id)})
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


def test_token_and_org_are_required(client, org):
    bare = TestClient(api.app)
    assert bare.get("/v1/jobs").status_code == 401
    assert bare.get("/v1/jobs", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 400
    assert bare.get("/v1/jobs", headers={"Authorization": f"Bearer {TOKEN}", "X-Org-Id": str(uuid.uuid4())}).status_code == 403
    assert bare.get("/v1/jobs", headers={"Authorization": "Bearer wrong", "X-Org-Id": str(org.id)}).status_code == 401


def test_another_orgs_data_is_not_found(client, session):
    job_id = make_job(client)
    other = writer.create_org(session, "other")
    r = client.get(f"/v1/jobs/{job_id}", headers={"X-Org-Id": str(other.id)})
    assert r.status_code == 404


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
    assert (last["from"], last["to"], last["cause"]["act"], last["actor"]) == ("do_not_submit", "priority", "typed", "operator")
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
