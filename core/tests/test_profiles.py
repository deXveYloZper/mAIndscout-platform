"""I3: step classification (one model call per CV, checked) and career profile snapshots."""

import uuid

import pytest
from sqlalchemy import func, select

from maindscout.api import profiles, research
from maindscout.db.models import CareerProfile, Claim, Company, CostEntry, Evidence, Task
from maindscout.intelligence import research as engine
from maindscout.intelligence.llm import LLMResult
from tests.test_api import client, drop_cv, fake, make_job, pdf_file  # noqa: F401 (fixtures)
from tests.test_coverage import PUNE_LINES, pune_cv


class Labeller:
    """Answers the classification call. Steps go newest first: s1 Acme Space (current), s2 Gamma Labs, s3 Beta Web."""

    model = "fake-classifier"

    def __init__(self, steps=None):
        self.calls = 0
        self.steps = steps or [
            {"id": "s1", "role_family": "software_engineering", "level": "senior", "domains": ["aerospace / defence"],
             "signals": [{"kind": "team_lead", "quote": "Flight Software Engineer, Acme Space"},
                         {"kind": "founder", "quote": "founded a rocket company"}]},
            {"id": "s2", "role_family": "software_engineering", "level": "mid", "domains": ["research / academia"], "signals": []},
            {"id": "s3", "role_family": "software_engineering", "level": "mid", "domains": ["e-commerce", "python", "web"], "signals": []},
            {"id": "s9", "role_family": "sales", "level": None, "domains": [], "signals": []},
        ]

    def complete_json(self, system, user, schema, name):
        assert name == "step_classification"
        self.calls += 1
        return LLMResult({"steps": self.steps}, self.model, 900, 120, 0.002)


def cid_of(client, job):
    return uuid.UUID(drop_cv(client, job)["subject_id"])


def org_of(client):
    return uuid.UUID(client.headers["X-Org-Id"])


def test_classification_labels_each_step_once_and_checks_what_it_is_given(client, fake, session):
    job = make_job(client)
    cid, org = cid_of(client, job), org_of(client)
    labeller = Labeller()
    result = profiles.classify(session, org, cid, labeller)
    assert result["classified"] == 3 and labeller.calls == 1
    labels = profiles.classifications(session, org, cid)
    by_company = {session.get(Claim, uuid.UUID(k)).payload["company"]["raw_name"]: c for k, c in labels.items()}
    acme = by_company["Acme Space"]
    assert acme.claim_class == "inferred" and acme.status == "proposed"
    assert acme.payload["signals"] == ["team_lead"], "an unwritten founder quote is dropped"
    assert acme.payload["level"] == "mid", "no level word in the title: mid (by code); leading a team stays a signal"
    assert by_company["Beta Web"].payload["domains"] == ["e-commerce"], "only industries from the list; never a technology"
    ev = session.scalars(select(Evidence).where(Evidence.claim_id == acme.id)).one()
    assert ev.evidence_type == "inference" and "Flight Software Engineer" in ev.snippet
    assert session.scalar(select(CostEntry).where(CostEntry.purpose == "classify_steps")).org_id == org
    assert profiles.classify(session, org, cid, labeller)["skipped"] == "nothing new" and labeller.calls == 1


def test_the_profile_is_built_by_code_and_stored_only_when_its_facts_change(client, fake, session):
    job = make_job(client)
    cid, org = cid_of(client, job), org_of(client)
    profiles.classify(session, org, cid, Labeller())
    first = profiles.build(session, org, cid)
    p = first.profile
    assert p["dimensions"]["relevant_years"]["main"] == "software_engineering"
    assert p["dimensions"]["contractor"]["label"] == "past"  # Gamma Labs, 2020
    assert p["reading"]["label"] in ("strong", "solid") and p["summary"]
    assert profiles.build(session, org, cid).id == first.id, "same facts, same snapshot"
    page = client.get(f"/v1/candidates/{cid}").json()
    assert page["profile"]["reading"]["label"] == p["reading"]["label"] and len(page["classifications"]) == 3


def test_a_recruiters_correction_wins_and_shows_at_once(client, fake, session):
    job = make_job(client)
    cid, org = cid_of(client, job), org_of(client)
    profiles.classify(session, org, cid, Labeller())
    profiles.build(session, org, cid)
    acme = next(c for c in profiles.classifications(session, org, cid).values() if c.payload["signals"] == ["team_lead"])
    r = client.post("/v1/claims", json={"subject_type": "candidate", "subject_id": str(cid), "claim_type": "StepClassificationClaim",
                                         "payload": {**acme.payload, "level": "principal"}, "replaces": str(acme.id)})
    assert r.status_code == 201, r.text
    page = client.get(f"/v1/candidates/{cid}").json()
    assert page["classifications"][acme.payload["career_claim_id"]]["level"] == "principal"
    assert page["profile"]["dimensions"]["seniority"]["label"] == "principal"


def test_archived_people_get_no_profile_and_no_model_call(client, fake, session):
    job = make_job(client)
    fake.cv = pune_cv()
    cid = uuid.UUID(drop_cv(client, job, PUNE_LINES, "pune.pdf")["subject_id"])
    labeller = Labeller()
    assert profiles.run(session, org_of(client), cid, lambda: labeller)["skipped"].startswith("archived")
    assert labeller.calls == 0 and profiles.latest(session, cid) is None
    assert not session.scalars(select(Task).where(Task.kind == "profile_candidate", Task.payload["candidate_id"].astext == str(cid))).all()


def test_reading_a_cv_queues_the_profile_and_new_company_facts_queue_a_rebuild(client, fake, session):
    job = make_job(client)
    cid = cid_of(client, job)
    queued = session.scalars(select(Task).where(Task.kind == "profile_candidate")).all()
    assert [t.payload["candidate_id"] for t in queued] == [str(cid)]
    for t in queued:
        t.status = "done"
    session.flush()
    acme = session.scalar(select(Company).where(Company.normalized == "acme space"))
    url = "https://acme.example/"
    research.apply(session, acme, engine.ResearchOutcome(True, url, [engine.Fact("company_type", "product", url, "we build rockets")], [], [url], {"usd": 0}))
    assert session.scalar(select(func.count()).select_from(Task).where(Task.kind == "profile_candidate", Task.status == "queued")) == 1


def test_profiles_can_be_turned_off(client, fake, session, monkeypatch):
    monkeypatch.setenv("PROFILE_AUTO", "false")
    job = make_job(client)
    cid_of(client, job)
    assert not session.scalars(select(Task).where(Task.kind == "profile_candidate")).all()


def test_erasure_removes_profiles(client, fake, session, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "k")
    job = make_job(client)
    cid, org = cid_of(client, job), org_of(client)
    profiles.classify(session, org, cid, Labeller())
    profiles.build(session, org, cid)
    assert client.post(f"/v1/subjects/candidate/{cid}/erase", json={"reason": "request"}).status_code == 200
    assert session.scalar(select(func.count()).select_from(CareerProfile).where(CareerProfile.candidate_id == cid)) == 0
    assert client.get(f"/v1/subjects/candidate/{cid}/erase/verify").json()["clean"] is True


# --- university rank (QS) ---------------------------------------------------------------------------

from maindscout.api import institutions  # noqa: E402
from maindscout.intelligence import institutions as rank_engine  # noqa: E402

QS = "https://www.topuniversities.com/universities/example-university"


def qs_answer(**over):
    data = {"identified": True, "official_name": "Example University", "country_code": "GB", "ranked": True, "rank": "=42",
            "edition": "2026", "source_url": QS, "quote": "Example University is ranked #42 in the QS World University Rankings 2026"}
    data.update(over)
    return data


@pytest.mark.parametrize("over,band,why", [
    ({}, "top_50", None),
    ({"rank": "601-650", "quote": "QS World University Rankings: 601-650"}, "501_plus", None),
    ({"rank": "42", "quote": "a leading university"}, None, "the rank is not in the quote"),
    ({"source_url": "https://elsewhere.example/page"}, None, "not opened"),
    ({"ranked": False}, "not_ranked", None),
    ({"identified": False}, None, "not confidently identified"),
])
def test_a_rank_is_kept_only_when_its_quote_and_page_support_it(over, band, why):
    out = rank_engine.check(qs_answer(**over), [QS])
    assert out.band == band
    if why:
        assert any(why in r for r in out.rejected)


class QSSearch:
    model = "fake-search"

    def __init__(self):
        self.calls = 0

    def search_json(self, system, user, schema, name):
        assert name == "institution_rank" and "Jane" not in user
        self.calls += 1
        return qs_answer(), [QS], {"usd": 0.04}


def test_the_rank_is_researched_once_per_institution_and_shown_as_merit_evidence(client, fake, session):
    job = make_job(client)
    cid, org = cid_of(client, job), org_of(client)
    search = QSSearch()
    result = profiles.run(session, org, cid, lambda: Labeller(), search_factory=lambda: search)
    assert result["institutions_researched"] == 1 and search.calls == 1
    inst = institutions.find(session, "Example University")
    assert inst.rank == 42 and inst.rank_band == "top_50" and inst.ranking == "QS World University Rankings 2026"
    edu = profiles.latest(session, cid).profile["dimensions"]["education"]
    assert edu["rank_band"] == "top_50" and "QS World University Rankings 2026" in edu["reason"]
    assert session.scalar(select(CostEntry).where(CostEntry.purpose == "research_institution")).org_id is None
    profiles.run(session, org, cid, lambda: Labeller(), search_factory=lambda: search)
    assert search.calls == 1, "fresh for a year: not looked up again"


def test_institution_names_match_across_spellings():
    assert institutions.normalize("The University of Edinburgh") == institutions.normalize("University Of Edinburgh")
    assert institutions.normalize("Imperial College London") != institutions.normalize("King's College London")
