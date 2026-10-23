"""The activity log and the fixes from the Ferrari investigation (owner, 2026-10-22): what each button, task, search
and model call did, in plain words; a CRM role read as CRM; "not necessarily a master's" as any degree; the ad's own
date never a deadline; "Search now" building the company list first. Nothing spent."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from maindscout import activity
from maindscout.api import hiring, marketmap, process, strategy, task_handlers
from maindscout.db.models import Claim, DeskLog, Task
from maindscout.domain import specialism
from maindscout.intelligence import competitors as engine
from maindscout.intelligence.extract import _ABOUT_THE_AD
from maindscout.intelligence.llm import LLMResult
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import FakeExa, job  # noqa: F401
from tests.test_competitors import VISITED, FakeResearch, rival


@pytest.fixture
def log_rows(session):
    """Lines the log wrote during the test (it writes in its own transaction), removed afterwards."""
    since = datetime.now(timezone.utc) - timedelta(seconds=1)
    seen: list[DeskLog] = []

    def read(**where):
        with activity._factory()() as s:
            stmt = select(DeskLog).where(DeskLog.at >= since)
            for k, v in where.items():
                stmt = stmt.where(getattr(DeskLog, k) == v)
            rows = list(s.scalars(stmt.order_by(DeskLog.at)))
            seen.extend(rows)
            return rows
    yield read
    with activity._factory()() as s:
        s.execute(DeskLog.__table__.delete().where(DeskLog.at >= since))
        s.commit()


class Chat:
    model = "fake-model"

    def complete_json(self, system, user, schema, name):
        return LLMResult({"ok": True, "said": "an answer"}, self.model, 10, 5, 0.0012)


def test_a_model_call_is_logged_with_its_prompt_unless_it_carries_a_persons_text(log_rows):
    org, job_id = uuid.uuid4(), uuid.uuid4()
    with activity.about(org_id=org, job_id=job_id, actor="owner@desk.test"):
        activity.ObservedChat(Chat()).complete_json("Read the ad.", "Job advertisement text: CRM Specialist", {}, "jd_extraction")
        activity.ObservedChat(Chat()).complete_json("Read the CV.", "CV text: Una Testperson, CRM manager", {}, "cv_extraction")
    ad, cv = log_rows(org_id=org)
    assert ad.kind == "model" and ad.job_id == job_id and ad.actor == "owner@desk.test"
    assert ad.detail["input"].endswith("CRM Specialist") and "an answer" in ad.detail["answer"] and ad.detail["usd"] == 0.0012
    assert "Una Testperson" not in str(cv.detail) and "not kept" in cv.detail["input"] and cv.detail["answer"] is None


def test_an_exa_search_and_a_failure_are_logged(log_rows):
    org = uuid.uuid4()

    class Exa:
        def call(self, body):
            if body["query"] == "boom":
                raise RuntimeError("Exa said no")
            return {"results": [{"title": "Testsat team page", "url": "https://x"}], "costDollars": {"total": 0.007}}

    with activity.about(org_id=org):
        activity.ObservedExa(Exa()).call({"query": "CRM specialist at Testsat", "category": "people", "userLocation": "IT"})
        with pytest.raises(RuntimeError):
            activity.ObservedExa(Exa()).call({"query": "boom"})
    search, failed = log_rows(org_id=org)
    assert "CRM specialist at Testsat" in search.summary and "in IT" in search.summary and "1 results" in search.summary
    assert failed.level == "error" and "Exa said no" in failed.detail["error"] and "RuntimeError" in failed.detail["trace"]


def test_buttons_and_crashes_are_logged_and_listed(client, session, org, log_rows):
    job_id = make_job(client)
    assert client.post(f"/v1/jobs/{job_id}/tell", json={"text": ""}).status_code in (200, 201, 422)
    client.post("/v1/activity/client-error", json={"message": "x is undefined", "stack": "at Sourcing.tsx:42",
                                                    "url": f"http://127.0.0.1:3001/jobs/{job_id}?tab=find"})
    rows = log_rows(org_id=org.id)
    assert any(r.kind == "button" and r.summary.startswith("Added a role") for r in rows)
    crash = next(r for r in rows if r.kind == "error")
    assert str(crash.job_id) == job_id and "x is undefined" in crash.summary and "Sourcing.tsx:42" in crash.detail["stack"]
    listed = client.get("/v1/activity", params={"job_id": job_id, "level": "error"}).json()
    assert [r["summary"] for r in listed] == [crash.summary]


def test_crm_is_read_from_the_ad_and_never_from_a_marketers_nice_to_have():
    assert specialism.of_role(["CRM & Client Data Specialist"]) == "crm"
    assert specialism.of_role(["Client Data Specialist", "Salesforce knowledge"]) == "crm", "Salesforce is a CRM"
    assert specialism.of_role(["Marketing Manager", "influencer marketing"]) is None
    assert specialism.title_says("crm", "Salesforce Administrator") and not specialism.title_says("crm", "Account Manager")
    assert specialism.titles("crm")[:2] == ["CRM specialist", "CRM manager"]


def test_not_necessarily_a_masters_is_any_degree_and_the_ads_own_date_is_no_deadline():
    assert hiring.least_degree("degree is a must, not ecessarily masters", "master") == "bachelor"
    assert hiring.least_degree("a master's degree in data science", "master") == "master"
    assert hiring.least_degree("a degree, doesn't have to be an MSc", "master") == "bachelor"
    assert _ABOUT_THE_AD.search("Job Description Date: 21/09/2026")
    assert not _ABOUT_THE_AD.search("Applications close on 30 November")


def _crm_role(session, job):
    session.add(Claim(org_id=job.org_id, subject_type="job", subject_id=job.id, claim_type="JobRequirementClaim", status="approved",
                      payload={"category": "skill", "strength": "must", "text_raw": "Salesforce knowledge", "normalized_token": "salesforce",
                               "distinctive": True}, natural_key=f"{job.id}|skill|salesforce"))
    session.flush()


def test_a_crm_role_searches_crm_titles(session, job):
    _crm_role(session, job)
    assert process.client_context(session, job)["specialism"] == "crm"
    variants = marketmap.initial(session, job)["role_variants"]
    assert "CRM specialist" in variants and "account manager" not in variants
    assert strategy.broad_word(session, job) == "CRM"


def test_the_research_is_told_the_role_and_keeps_the_clients_business_lines(session, job):
    from maindscout.api import companies

    _crm_role(session, job)
    client_co, _ = companies.resolve(session, "Client Testcars", "test", keys={"domain": "client-cars.example"})
    client_co.exa_profile = {"employees": 5500, "offering": "sports cars", "domains": ["automotive"]}
    job.hiring_company_id = client_co.id
    session.flush()

    class Lines(FakeResearch):
        def search_json(self, system, user, schema, name):
            self.calls.append((name, user))
            return {"business_lines": ["sports cars", "fashion and lifestyle collection"],
                    "companies": [dict(rival("Testfashion House", website="testfashion.example", staff=4000), line="talent")]}, VISITED, {"usd": 0.2}

    researcher = Lines([])
    targets, report = strategy.competitors(session, job.org_id, job, client_co, FakeExa(people=[], companies=[]), researcher, set(), ["IT"])
    assert "The role we are filling:" in researcher.calls[0][1] and "kind of work: CRM" in researcher.calls[0][1]
    assert report["lines"] == ["sports cars", "fashion and lifestyle collection"]
    assert targets[0]["why"][0].startswith("where such people work")


def test_search_now_on_a_role_whose_list_was_never_built_builds_it_first(client, session, job, monkeypatch):
    monkeypatch.setattr(task_handlers, "exa_factory", lambda: FakeExa(people=[], companies=[]))
    r = client.post(f"/v1/jobs/{job.id}/sourcing/run")
    assert r.status_code == 202 and r.json()["status"] == "building"
    built = session.get(Task, uuid.UUID(r.json()["task_id"]))
    assert built.kind == "sourcing_strategy" and built.payload["then_search"] is True
    monkeypatch.setattr(strategy, "build", lambda *a, **k: {"version": 2, "targets": {"A": 3}})
    built.status = "running"
    task_handlers.sourcing_strategy(session, built)
    follow = session.scalar(select(Task).where(Task.kind == "sourcing_run", Task.dedupe_key == f"sourcing:{job.id}"))
    assert follow is not None and follow.payload["trigger"] == "manual", "the search follows the list by itself"


def test_a_crm_specialist_without_salesforce_on_a_public_profile_is_asked_not_ruled_out():
    from datetime import date

    from maindscout.domain import matching
    from maindscout.domain.profile import Stint, build

    def career(title, family):
        st = [Stint("s1", "Testmoda", title, date(date.today().year - 4, 1, 1), None, "full_time", company_key="Testmoda",
                    family=family, level="mid")]
        return build(st, [], date.today()), st
    role = [{"id": "1", "payload": {"category": "role", "strength": "must", "text_raw": "CRM management", "role_family": "customer_success"}},
            {"id": "2", "payload": {"category": "skill", "strength": "must", "text_raw": "Salesforce knowledge",
                                    "normalized_token": "salesforce", "distinctive": True}}]
    coarse = ("do_not_submit", "no_support_for_must_have:salesforce")
    crm = {"specialism": "crm", "has_cv": False, "level": "mid"}
    profile, st = career("CRM Operations Specialist", "marketing")
    m = matching.match(role, [], profile, st, coarse, client=crm)
    assert m.band != "do_not_submit" and "distinctive_must_unproven" in [r["id"] for r in m.rules], m.reason
    profile, st = career("Global PR and Events Manager", "marketing")
    assert matching.match(role, [], profile, st, coarse, client=crm).band == "do_not_submit", "no CRM in the title"
    profile, st = career("Salesforce Administrator", "it_support")
    assert matching.match(role, [], profile, st, coarse, client=crm).band == "do_not_submit", "IT side: not lifted"
    profile, st = career("CRM Operations Specialist", "marketing")
    assert matching.match(role, [], profile, st, coarse, client={**crm, "has_cv": True}).band == "do_not_submit",         "with a CV on file, a missing must-have still decides"


def test_the_talent_map_researches_each_pool_and_goes_deeper_only_where_it_gives(session, job):
    from maindscout.api import companies

    client_co, _ = companies.resolve(session, "Client Testcars", "test", keys={"domain": "client-cars.example"})
    client_co.exa_profile = {"employees": 5500, "offering": "luxury sports cars"}
    job.hiring_company_id = client_co.id
    session.flush()

    class Map(FakeResearch):
        def search_json(self, system, user, schema, name):
            self.calls.append((name, user))
            if name == "talent_pools":
                return {"business_lines": ["sports cars", "fashion"], "pools": [
                    {"name": "luxury jewellery", "why": "same clients", "examples": ["Testgem", "Testgold"]},
                    {"name": "luxury hospitality", "why": "same service", "examples": ["Testhotel"]}]}, VISITED, {"usd": 0.1}
            if "Only this pool: luxury jewellery" in user and "Look further" not in user:
                return {"companies": [rival(f"Testgem {n}", website=f"gem-{n}.example") for n in "ABC"]}, VISITED, {"usd": 0.2}
            return {"companies": []}, VISITED, {"usd": 0.2}

    researcher = Map([])
    targets, report = strategy.competitors(session, job.org_id, job, client_co, FakeExa(people=[], companies=[]), researcher, set(), ["IT"])
    asked = [u for n, u in researcher.calls if n == "competitors"]
    assert sum("Only this pool: luxury jewellery" in u for u in asked) == 2, "it gave three: one deeper round"
    assert sum("Only this pool: luxury hospitality" in u for u in asked) == 1, "it gave nothing: no deeper round"
    assert {t["pool"] for t in targets} == {"luxury jewellery"} and targets[0]["why"][0].startswith("talent pool (luxury jewellery)")
    assert [p["name"] for p in report["pools"]] == ["luxury jewellery", "luxury hospitality"] and report["pools"][0]["kept"] == 3


def test_a_researched_company_is_never_left_out_by_exas_words():
    assert "competitor" in strategy.RESEARCHED and "peer" not in strategy.RESEARCHED


def test_years_for_a_mid_role_and_the_side_of_the_company():
    from datetime import date

    from maindscout.domain import matching
    from maindscout.domain.profile import Stint

    def since(year):
        return [Stint("s", "Testmoda", "CRM Specialist", date(year, date.today().month, 1), None, "full_time",
                      company_key="Testmoda", family="marketing", level="mid")]
    assert matching.career_years(since(date.today().year - 5)) == 5
    assert matching.YEARS_BAND["mid"] == (2, 5)
    coarse = ("priority", "supported:crm")
    from maindscout.domain.profile import build

    long_ = since(date.today().year - 8)
    m = matching.match([], [], build(long_, [], date.today()), long_, coarse, client={"level": "mid"})
    assert m.band == "do_not_submit" and "too senior" in m.reason, m.reason
    assert matching.same_side("customer_success", "marketing") and not matching.same_side("customer_success", "it_support")
    assert matching.same_side("customer_success", None) and matching.same_side("customer_success", "other")
