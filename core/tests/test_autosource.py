"""The sourcing engine (docs/next/PLAN.md, phase 1): profiles found on the web become people through the ordinary
path, runs go pool-first then web within budgets, gates refuse off-limits / stop / outside-country people, and
results and spend say what each search strategy brought. Exa is a fake here: synthetic people, nothing spent."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from maindscout.api import autosource, consent, costs, discovery, erasure, messages, review, sourcing, sourcing_stats
from maindscout.db.models import (
    Candidate,
    CandidateJob,
    Claim,
    Company,
    CostEntry,
    Document,
    Evidence,
    Job,
    Message,
    Permission,
    SourcingHit,
    SourcingPlan,
    SourcingRun,
    Task,
)
from maindscout.intelligence import exa, extract, webprofile
from maindscout.storage import LocalBlobStore
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)


def profile(slug, name, headline, place, country, jobs, schools=(), skills=()):
    """A synthetic Exa people result laid out like the real ones (names are clearly fake)."""
    lines = [f"# {name}", "", headline, "", f"{place} ({country})", "", "500 connections", "", "## About", "",
             f"I work as {headline.lower()}.", "", "## Experience", ""]
    work = []
    for title, company, start_txt, end_txt, frm, to in jobs:
        slug_c = company.lower().replace(" ", "-")
        lines += [f"### {title} - [{company}](https://www.linkedin.com/company/{slug_c})", "",
                  f"{start_txt} - {end_txt} (2 years) in {place}", "", f"{company} is a company with 50 employees.", ""]
        work.append({"title": title, "company": {"id": None, "name": company}, "dates": {"from": frm, "to": to}, "location": place})
    edu = []
    if schools:
        lines += ["## Education", ""]
        for degree, school, years in schools:
            lines += [f"### {degree} at [{school}](https://www.linkedin.com/school/x)", "", f"{years} (2 years) in {place}", "",
                      f"{school} is a university.", ""]
            a, b = years.split(" - ")
            edu.append({"degree": degree, "dates": {"from": a, "to": b}, "institution": {"id": None, "name": school}})
    if skills:
        lines += ["## Skills", "", " • ".join(skills), ""]
    return {"url": f"https://www.linkedin.com/in/{slug}", "title": name, "text": "\n".join(lines),
            "publishedDate": "2026-10-01T00:00:00.000Z", "image": "https://example.invalid/photo.jpg",
            "entities": [{"id": slug, "type": "person", "version": 1,
                          "properties": {"name": name, "location": place, "workHistory": work, "educationHistory": edu}}]}


MUNICH = "Munich, Bavaria, Germany"
ADA = profile("ada-testperson-demo", "Ada Testperson", "InSAR Processing Engineer", MUNICH, "DE",
              [("InSAR Engineer", "Orbital Testworks", "Jan 2022", "Present", "2022-01-01", None),
               ("Research Assistant", "Example University", "Oct 2019", "Dec 2021", "2019-10-01", "2021-12-01")],
              schools=[("Master of Science, Geodesy", "Example University", "2017 - 2019")], skills=["insar", "python"])
BEN = profile("ben-testperson-demo", "Ben Testperson", "Embedded Software Engineer", MUNICH, "DE",
              [("Embedded Software Engineer", "Orbital Testworks", "Mar 2021", "Present", "2021-03-01", None)])
CARA = profile("cara-testperson-demo", "Cara Testperson", "InSAR Scientist", MUNICH, "DE",
               [("InSAR Scientist", "Catalyst Geo", "Feb 2020", "Present", "2020-02-01", None)])
DEV = profile("dev-testperson-demo", "Dev Testperson", "InSAR Analyst", "Bangalore, Karnataka, India", "IN",
              [("InSAR Analyst", "Satellite Testlabs", "Jan 2021", "Present", "2021-01-01", None)])
NOT_A_PERSON = {"url": "https://orbital-testworks.example", "title": "Orbital Testworks", "text": "A company page.", "entities": []}


class FakeExa:
    model = "exa"

    def __init__(self, people=None, companies=None, cost=0.007, news=None, pages=None, by_query=None):
        self.people = people if people is not None else [ADA, BEN, CARA, DEV, NOT_A_PERSON]
        self.companies, self.news = companies or [], news or []
        self.pages, self.by_query = pages or {}, by_query or {}
        self.cost, self.calls, self.fetched = cost, [], []

    def contents(self, body):
        self.fetched.append(body)
        found = [self.pages[u] for u in body["urls"] if u in self.pages]
        return {"results": found, "costDollars": {"total": 0.001 * len(found)}}

    def call(self, body):
        self.calls.append(body)
        if body["query"] in self.by_query:
            return {"results": self.by_query[body["query"]], "costDollars": {"total": self.cost}}
        results = {"company": self.companies, "news": self.news}.get(body["category"], self.people)
        return {"results": results[: body.get("numResults", 10)], "costDollars": {"total": self.cost}}


@pytest.fixture
def blobs(tmp_path):
    return LocalBlobStore(tmp_path)


@pytest.fixture
def job(client, session):
    return session.get(Job, uuid.UUID(make_job(client)))


def person_named(session, name):
    return session.scalar(select(Claim.subject_id).where(Claim.claim_type == "IdentityClaim",
                                                         Claim.payload["full_name"].astext == name))


def go(session, job, fake_exa=None, blobs=None):
    """A run with country-wide searches opened (these tests have no target companies; phase 1b opens them last)."""
    p = autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", open_tiers=["A", "B", "market"])
    return autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa or FakeExa()), p


# --- reading a profile -------------------------------------------------------------------------------------------------


def test_a_profile_is_read_like_a_short_cv_with_every_value_quoted():
    found = exa.parse({"results": [ADA], "costDollars": {"total": 0.007}}, "q", "people").found[0]
    assert not hasattr(found, "image"), "a photo is never read"
    data = webprofile.read(found, ["insar", "python"])
    out = extract.extract_cv(found.text, uuid.uuid4(), [{"page": 1, "kind": "link", "uri": found.url}], webprofile.EntityReader(data))
    kinds = sorted(s.claim_type for s in out.staged)
    assert kinds == ["CareerStepClaim", "CareerStepClaim", "ContactClaim", "EducationClaim", "IdentityClaim", "LocationClaim",
                     "SkillClaim", "SkillClaim"]
    assert [r for r in out.span_results if r.result == "fail"] == []
    steps = {s.payload["title_raw"]: s for s in out.staged if s.claim_type == "CareerStepClaim"}
    assert steps["InSAR Engineer"].valid_to is None and steps["Research Assistant"].valid_to is not None
    assert "50 employees" not in " ".join(s.span["snippet"] for s in out.staged), "Exa's company blurbs are never quoted"


def test_roles_grouped_under_one_company_are_quoted_in_pieces():
    text = ("# Eve Testperson\n\nControls Engineer\n\nMunich, Bavaria, Germany (DE)\n\n## Experience\n\n"
            "### [Rover Testworks](https://www.linkedin.com/company/rover)\n\n#### Senior Controls Engineer (Current)\n\n"
            "Mar 2024 - Present (2 years) in Munich, Bavaria, Germany\n\n#### Controls Engineer\n\n"
            "Jan 2021 - Mar 2024 (3 years) in Munich, Bavaria, Germany\n")
    found = exa.Found(url="https://www.linkedin.com/in/eve-demo", title="Eve", text=text, person={
        "name": "Eve Testperson", "location": MUNICH, "educationHistory": [],
        "workHistory": [{"title": "Senior Controls Engineer", "company": {"name": "Rover Testworks"}, "dates": {"from": "2024-03-01"}},
                        {"title": "Controls Engineer", "company": {"name": "Rover Testworks"}, "dates": {"from": "2021-01-01"}}]})
    out = extract.extract_cv(text, uuid.uuid4(), [], webprofile.EntityReader(webprofile.read(found, [])))
    steps = sorted((s for s in out.staged if s.claim_type == "CareerStepClaim"), key=lambda s: s.valid_from)
    assert [s.payload["title_raw"] for s in steps] == ["Controls Engineer", "Senior Controls Engineer"]
    assert not steps[1].span.get("parts"), "the first role sits right under the company heading: one passage"
    assert steps[0].span.get("parts"), "a later role is quoted in pieces: company heading, role, dates"


def test_the_profile_reader_answers_only_profile_reading():
    with pytest.raises(ValueError):
        webprofile.EntityReader({}).complete_json("", "", {}, "jd_extraction")


# --- a found profile becomes a person ------------------------------------------------------------------------------------


def test_a_found_profile_becomes_a_person_with_public_facts_only_and_no_paid_follow_ups(session, job, blobs):
    found = exa.parse({"results": [ADA]}, "q", "people").found[0]
    cid, outcome = discovery.add(session, blobs, job.org_id, found, ["insar"])
    assert outcome == "new"
    doc = session.scalar(select(Document).join(Evidence, Evidence.document_id == Document.id).join(Claim, Claim.id == Evidence.claim_id)
                         .where(Claim.subject_id == cid).limit(1))
    assert doc.doc_type == "web_profile" and doc.source_authority == "third_party_assertion"
    claims = list(session.scalars(select(Claim).where(Claim.subject_id == cid)))
    assert claims and all(c.status == "proposed" for c in claims), "nothing believed before a person approves it"
    origins = set(session.scalars(select(Evidence.origin).where(Evidence.claim_id.in_([c.id for c in claims]))))
    assert origins == {"independent_web"}
    linkedin = [c.payload["value"] for c in claims if c.claim_type == "ContactClaim"]
    assert linkedin == ["linkedin.com/in/ada-testperson-demo"], "their LinkedIn page, normalised like any contact"
    queued = [t.kind for t in session.scalars(select(Task).where(Task.payload["candidate_id"].astext == str(cid)))]
    assert "profile_candidate" not in queued, "no career profile (a model call) for someone known only from the web"
    assert not session.scalar(select(func.count()).select_from(CostEntry).where(CostEntry.subject_id == doc.id)), "reading cost nothing"


def test_the_same_page_again_is_the_same_person_and_a_changed_page_adds_to_them(session, job, blobs):
    found = exa.parse({"results": [ADA]}, "q", "people").found[0]
    first, _ = discovery.add(session, blobs, job.org_id, found, ["insar"])
    again, outcome = discovery.add(session, blobs, job.org_id, found, ["insar"])
    assert (again, outcome) == (first, "known")
    newer = dict(ADA, text=ADA["text"].replace("## Experience\n", "## Experience\n\n### Lead InSAR Engineer - "
                                                "[Orbital Testworks](https://www.linkedin.com/company/orbital-testworks)\n\n"
                                                "Jul 2026 - Present (3 months) in Munich, Bavaria, Germany\n", 1))
    newer["entities"] = [{**ADA["entities"][0], "properties": {**ADA["entities"][0]["properties"], "workHistory": [
        {"title": "Lead InSAR Engineer", "company": {"name": "Orbital Testworks"}, "dates": {"from": "2026-07-01"}},
        *ADA["entities"][0]["properties"]["workHistory"]]}}]
    later, outcome = discovery.add(session, blobs, job.org_id, exa.parse({"results": [newer]}, "q", "people").found[0], ["insar"])
    assert (later, outcome) == (first, "known"), "the same LinkedIn page is the same person"
    titles = {c.payload["title_raw"] for c in session.scalars(select(Claim).where(
        Claim.subject_id == first, Claim.claim_type == "CareerStepClaim"))}
    assert "Lead InSAR Engineer" in titles


# --- runs, gates, budgets ------------------------------------------------------------------------------------------------


def test_a_new_plan_waits_paused_and_every_change_is_a_version(session, job):
    p = autosource.plan(session, job.org_id, job.id, "owner@desk.test")
    assert (p.version, p.mode, p.target, float(p.monthly_budget_usd)) == (1, "paused", 10, 5.0)
    assert p.role_variants[0] == "Radar Interferometry Specialist"
    p2 = autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", target=4)
    assert (p2.version, p2.mode, p2.target) == (2, "weekly", 4)
    assert session.get(SourcingPlan, p.id).superseded_at is not None
    with pytest.raises(autosource.SourcingEngineError):
        autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="hourly")


def test_a_run_finds_people_on_the_web_and_refuses_off_limits_and_outside_countries(session, job, blobs):
    fake_exa = FakeExa()
    row, _ = go(session, job, fake_exa, blobs)
    assert row.status == "done" and fake_exa.calls[0]["category"] == "people"
    assert "Testperson" not in fake_exa.calls[0]["query"], "a search names roles and places, never a person"
    assert (row.found, row.new, row.strong) == (4, 4, 1)
    assert row.report["refused"] == {"not_a_profile": 1, "off_limits": 1, "outside_countries": 1}
    hits = {session.get(Candidate, h.candidate_id).id: h for h in session.scalars(select(SourcingHit).where(SourcingHit.job_id == job.id))}
    ada, ben, cara = person_named(session, "Ada Testperson"), person_named(session, "Ben Testperson"), person_named(session, "Cara Testperson")
    assert set(hits) == {ada, ben}, "Cara works at the client (Catalyst Geo); Dev lives outside the desk's countries"
    assert cara is not None, "refused people stay in the pool, just not suggested here"
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == ada))
    assert pair.triage_band == "priority"
    assert float(row.cost_usd) == pytest.approx(0.007)
    assert costs.sourcing_spent(session, job.org_id, job.id) == pytest.approx(0.007)
    assert costs.month_spent(session, job.org_id) == 0, "sourcing spend never eats the desk's model budget"


def test_someone_found_by_several_searches_in_one_run_counts_once(session, job, blobs):
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", open_tiers=["A", "B", "market"],
                           role_variants=["Radar Interferometry Specialist", "InSAR engineer", "SAR engineer"])
    fake_exa = FakeExa()
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    assert len(fake_exa.calls) == 3, "three searches, each returning the same people"
    assert (row.found, row.strong) == (4, 1) and row.report["refused"] == {"not_a_profile": 1, "off_limits": 1, "outside_countries": 1}


def test_a_search_is_not_repeated_within_30_days_and_the_target_stops_a_run(session, job, blobs):
    fake_exa = FakeExa()
    go(session, job, fake_exa, blobs)
    made = len(fake_exa.calls)
    again = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    assert len(fake_exa.calls) == made and again.stop_reason == "no_queries"
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", target=1, role_variants=["InSAR engineer"])
    reached = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    assert reached.stop_reason == "target", "one strong suggestion is already waiting"


def test_budgets_stop_web_search_but_not_the_free_pool(session, job, blobs):
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", monthly_budget_usd=0,
                           open_tiers=["A", "B", "market"])
    fake_exa = FakeExa()
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    assert (row.status, row.stop_reason, fake_exa.calls) == ("stopped", "budget", [])
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", monthly_budget_usd=5)
    autosource.set_desk_budget(session, job.org_id, 0)
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    assert row.stop_reason == "desk_budget" and fake_exa.calls == []


def test_stop_and_erasure_are_never_suggested_again(client, session, job, blobs, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "test-suppression-key")
    go(session, job, FakeExa(), blobs)
    ada, ben = person_named(session, "Ada Testperson"), person_named(session, "Ben Testperson")
    assert str(ada) in {s["candidate_id"] for s in autosource.page(session, job.org_id, job.id)["suggestions"]}
    assert autosource.strong_waiting(session, job.id) == 1
    consent.stop(session, job.org_id, ada, "owner@desk.test", "replied: not interested, please stop")
    assert autosource.refusal(session, job.org_id, job, ada, {}) == "stop"
    assert str(ada) not in {s["candidate_id"] for s in autosource.page(session, job.org_id, job.id)["suggestions"]}
    assert autosource.strong_waiting(session, job.id) == 0, "someone who said stop never counts towards the target"
    assert client.get(f"/v1/jobs/{job.id}").json()["people"]["priority"][0]["stopped"] is True, "the role's queue says so"
    with pytest.raises(messages.MessageError):
        messages.draft(session, job.org_id, "candidate_outreach", "owner@desk.test", None, candidate_id=ada,
                       job_id=job.id, channel="linkedin")
    contact = client.post(f"/v1/companies/{job.hiring_company_id}/contacts",
                          json={"name": "Anna Example", "email": "anna@catalyst.example"}).json()["id"]
    with pytest.raises(messages.MessageError, match="not put forward"):
        messages.draft(session, job.org_id, "client_submission", "owner@desk.test", None, candidate_id=ada,
                       job_id=job.id, contact_id=uuid.UUID(contact))
    erasure.erase_candidate(session, blobs, job.org_id, ben, "owner@desk.test")
    assert erasure.verify_erasure(session, blobs, job.org_id, ben) == []
    cid, outcome = discovery.add(session, blobs, job.org_id, exa.parse({"results": [BEN]}, "q", "people").found[0], [])
    assert (cid, outcome) == (None, "stop"), "an erased person's profile is not stored again"
    assert person_named(session, "Ben Testperson") is None


def test_the_desk_search_skips_stop_and_off_limits_people_too(session, job, blobs):
    """"Find more people" (the older desk search) follows the same two rules as a run."""
    eve = profile("eve-testperson-demo", "Eve Testperson", "InSAR Engineer", MUNICH, "DE",
                  [("InSAR Engineer", "Radar Testworks", "May 2021", "Present", "2021-05-01", None)], skills=["insar"])
    skills = discovery.skill_tokens(session, job)
    ids = {}
    for raw in (ADA, CARA, eve):
        found = exa.parse({"results": [raw]}, "q", "people").found[0]
        ids[found.title], _ = discovery.add(session, blobs, job.org_id, found, skills)
    ada, cara, eve_id = ids["Ada Testperson"], ids["Cara Testperson"], ids["Eve Testperson"]
    consent.stop(session, job.org_id, ada, "owner@desk.test")
    assert autosource.never_sourced(session, job.org_id) == {ada, cara}, "Cara works at the hiring company, an active client"
    campaign = sourcing.start(session, job.org_id, job.id, "owner@desk.test", source="desk")
    on_job = set(session.scalars(select(CandidateJob.candidate_id).where(CandidateJob.job_id == job.id)))
    assert eve_id in on_job and not on_job & {ada, cara}
    assert campaign.added == 1


def test_the_clock_runs_only_plans_that_are_due(session, job, blobs):
    autosource.plan(session, job.org_id, job.id)
    assert autosource.due(session) == [], "a paused plan never runs"
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly")
    assert autosource.due(session) == [(job.org_id, job.id)]
    autosource.run(session, blobs, job.org_id, job.id, "schedule", None)
    assert autosource.due(session) == []
    assert autosource.due(session, datetime.now(timezone.utc) + timedelta(days=8)) == [(job.org_id, job.id)]
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="continuous", target=1)
    go(session, job, FakeExa(), blobs)
    assert autosource.due(session, datetime.now(timezone.utc) + timedelta(hours=2)) == [], "continuous stops at the target"
    job.state = "filled"
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", target=50)
    assert autosource.due(session, datetime.now(timezone.utc) + timedelta(days=30)) == [], "a filled role is not sourced"


# --- reaching them, and results and spend ---------------------------------------------------------------------------------


def test_linkedin_message_permission_and_results_and_spend(session, job, blobs):
    go(session, job, FakeExa(), blobs)
    ada = person_named(session, "Ada Testperson")
    m = messages.draft(session, job.org_id, "candidate_outreach", "owner@desk.test", None, candidate_id=ada, job_id=job.id,
                       channel="linkedin")
    assert m.to_address == "linkedin.com/in/ada-testperson-demo" and m.provider == "linkedin"
    assert "InSAR Engineer at Orbital Testworks" in m.body, "a first message may use what their public profile says"
    assert "maindscout.com/legal" not in m.body, "no privacy line: public profiles need none (owner, 2026-10-13)"
    with pytest.raises(messages.MessageError):
        messages.to_mailbox(session, job.org_id, m.id)
    messages.mark_sent(session, job.org_id, m.id)
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == ada))
    assert pair.pair_state == "contacted"
    consent.record(session, job.org_id, ada, "owner@desk.test", this_role=True, other_roles=True, job_id=job.id, how="message")
    assert consent.may_put_forward(session, job.org_id, ada, job.id)
    review.set_state(session, job.org_id, job.id, ada, "submitted", "owner@desk.test", note="to the hiring manager")
    review.set_state(session, job.org_id, job.id, ada, "interviewing", "owner@desk.test")

    s = sourcing_stats.stats(session, job.org_id, job.id, "channel")
    t = s["totals"]
    assert (t["found"], t["relevant"], t["contacted"], t["interested"], t["submitted"], t["interviewed"]) == (2, 1, 1, 1, 1, 1)
    assert t["spend_usd"] == pytest.approx(0.007) and t["cost_per_interview"] == pytest.approx(0.01)
    web = next(g for g in s["groups"] if g["key"] == "exa_people")
    assert web["label"] == "web people search" and web["spend_usd"] == pytest.approx(0.007)
    assert any(f["level"] == "good" for f in s["flags"])
    assert sourcing_stats.stats(session, job.org_id, None, "query")["groups"]
    consent.record(session, job.org_id, person_named(session, "Ben Testperson"), "owner@desk.test", this_role=False,
                   other_roles=True, how="call")
    t = sourcing_stats.stats(session, job.org_id, job.id, "channel")["totals"]
    assert (t["contacted"], t["replied"], t["interested"]) == (2, 2, 2), "the funnel only narrows: a yes means they were reached"


def test_erasure_takes_finds_and_permissions(session, job, blobs, monkeypatch):
    monkeypatch.setenv("SUPPRESSION_KEY", "test-suppression-key")
    go(session, job, FakeExa(), blobs)
    ada = person_named(session, "Ada Testperson")
    consent.record(session, job.org_id, ada, "owner@desk.test", this_role=False, other_roles=True)
    erasure.erase_candidate(session, blobs, job.org_id, ada, "owner@desk.test")
    assert erasure.verify_erasure(session, blobs, job.org_id, ada) == []
    assert not session.scalar(select(func.count()).select_from(SourcingHit).where(SourcingHit.candidate_id == ada))
    assert not session.scalar(select(func.count()).select_from(Permission).where(Permission.candidate_id == ada))


def test_peer_companies_from_a_company_search_join_the_plan(session, job):
    autosource.plan(session, job.org_id, job.id)
    company_results = [{"url": "https://orbital-testworks.example", "title": "Orbital Testworks | Satellite radar", "entities": []},
                       {"url": "https://catalyst.example", "title": "Catalyst Geo", "entities": []}]
    with pytest.raises(autosource.SourcingEngineError):  # the hiring company is not researched here: no industries yet
        autosource.find_peers(session, job.org_id, job.id, "owner@desk.test", FakeExa(companies=company_results))
    from maindscout.api import marketmap

    found, usd, query = marketmap.web_peers(session, job, [], ["DE"], "radar engineer", FakeExa(companies=company_results),
                                            {"domains": ["earth observation"], "stage": "series a (2025-01)"})
    assert query == "Series A earth observation startups in Germany hiring radar engineer"
    assert [t["name"] for t in found] == ["Orbital Testworks"], "the hiring company itself is never a target"
    assert usd == pytest.approx(0.007)


# --- the API -------------------------------------------------------------------------------------------------------------


def test_sourcing_routes(client, session, job, blobs):
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    assert page["plan"]["mode"] == "paused" and page["suggestions"] == []
    page = client.patch(f"/v1/jobs/{job.id}/sourcing/plan", json={"mode": "daily", "target": 6}).json()
    assert (page["plan"]["version"], page["plan"]["mode"], page["plan"]["target"]) == (2, "daily", 6)
    page = client.post(f"/v1/jobs/{job.id}/sourcing/targets", json={"name": "Orbital Testworks"}).json()
    target = page["plan"]["targets"][0]
    assert (target["name"], target["tier"], target["pinned"]) == ("Orbital Testworks", "manual", True)
    page = client.patch(f"/v1/jobs/{job.id}/sourcing/targets/{target['company_id']}", json={"removed": True}).json()
    assert page["plan"]["targets"][0]["removed"] is True
    r = client.post(f"/v1/jobs/{job.id}/sourcing/run")
    assert r.status_code == 202 and session.get(Task, uuid.UUID(r.json()["task_id"])).kind == "sourcing_run"
    assert client.get("/v1/sourcing/stats", params={"job_id": str(job.id), "group": "tier"}).json()["totals"]["found"] == 0
    assert client.get("/v1/sourcing/stats", params={"group": "nonsense"}).status_code == 422
    assert client.put("/v1/sourcing/settings", json={"sourcing_budget_usd": 80}).json()["sourcing_budget_usd"] == 80
    off = client.post("/v1/off-limits", json={"name": "Rival Testcorp", "note": "a friend's company"})
    assert off.status_code == 201
    listed = client.get("/v1/off-limits").json()["companies"]
    assert {c["name"] for c in listed} >= {"Rival Testcorp", "Catalyst Geo"}
    assert client.delete(f"/v1/off-limits/{off.json()['id']}").json() == {"removed": True}

    page = client.patch(f"/v1/jobs/{job.id}/sourcing/plan", json={"open_tiers": ["A", "B", "market"]}).json()
    assert page["plan"]["open_tiers"] == ["A", "B", "market"]
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", FakeExa())
    ada = person_named(session, "Ada Testperson")
    assert row.strong == 1
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    assert [s["name"] for s in page["suggestions"]][0] == "Ada Testperson"
    first = page["suggestions"][0]
    assert first["profile"].endswith("ada-testperson-demo") and first["found_by"]["channel"] == "exa_people"
    drafted = client.post("/v1/messages", json={"kind": "candidate_outreach", "candidate_id": str(ada), "job_id": str(job.id),
                                                "channel": "linkedin"})
    assert drafted.status_code == 201 and drafted.json()["to"].endswith("ada-testperson-demo")
    r = client.post(f"/v1/candidates/{ada}/permission", json={"job_id": str(job.id), "this_role": True, "how": "message"})
    assert r.status_code == 201 and r.json()["permissions"][0]["scope"] == "this_role"
    assert client.post(f"/v1/candidates/{ada}/stop", json={"note": "asked to stop"}).json()["do_not_contact_at"]
    person = client.get(f"/v1/candidates/{ada}").json()
    assert person["do_not_contact"]["note"] == "asked to stop" and person["found_by"][0]["channel"] == "exa_people"
    assert client.post(f"/v1/candidates/{ada}/stop/lift", json={}).status_code == 422, "lifting needs a reason"
    assert client.post(f"/v1/candidates/{ada}/stop/lift", json={"note": "she wrote back"}).json() == {"do_not_contact_at": None}


def test_only_an_owner_changes_the_desk_budget(client, session, org):
    from maindscout.api import auth
    from tests.test_api import signed_in

    recruiter, _ = auth.create_user(session, "rec@desk.test", "Rec", org.id, "recruiter", password="another long passphrase 12")
    client.headers["Authorization"] = f"Bearer {signed_in(session, recruiter, org.id)}"
    assert client.put("/v1/sourcing/settings", json={"sourcing_budget_usd": 1}).status_code == 403
