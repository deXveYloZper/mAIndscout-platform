"""Evidence for strong matches (owner, 2026-10-17): alternatives in an ad are one requirement, an employer's own job
adverts make a skill likely (never strong on its own), and a strong match found on the web gets a deeper look at their
public work, which can support or weaken the match. Exa and the model are fakes: synthetic people, nothing spent."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from maindscout.api import autosource, erasure, evidence, hiring, practices, process, queries
from maindscout.db.models import (
    PUBLIC_ORG_ID,
    CandidateJob,
    Claim,
    Company,
    CostEntry,
    Document,
    DocumentSubject,
    Evidence,
    Task,
)
from maindscout.domain import gaps
from maindscout.intelligence import evidence as engine
from maindscout.intelligence import exa, extract
from maindscout.intelligence import practices as reader
from maindscout.intelligence.llm import FakeClient, LLMResult
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import ADA, BEN, MUNICH, FakeExa, blobs, go, job, person_named, profile  # noqa: F401


class Model:
    """Answers each kind of reading with its own canned data."""

    model = "fake-model"

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def complete_json(self, system, user, schema, name):
        self.calls.append({"name": name, "user": user})
        return LLMResult(self.answers[name], self.model, 0, 0, 0.003)


def pair_of(session, job, cid):
    return session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == cid))


# --- alternatives in one sentence ----------------------------------------------------------------------------------------


AD = ("Full Stack Engineer\nGood understanding of JavaScript/TypeScript and familiar with React and/or Node.js\n"
      "Tools we use: Python, SQL, Docker\n")


def skill(text, token, quote, distinctive=False):
    return {"text": text, "category": "skill", "strength": "must", "token": token, "distinctive": distinctive,
            "min_years": None, "education_level": None, "language": None, "quote": quote}


def test_alternatives_in_one_sentence_are_one_requirement():
    first = "Good understanding of JavaScript/TypeScript and familiar with React and/or Node.js"
    data = {"title": {"value": "Full Stack Engineer", "quote": "Full Stack Engineer"}, "hiring_company": None,
            "requirements": [skill("JavaScript/TypeScript", "javascript/typescript", first), skill("React", "react", first, True),
                             skill("Node.js", "node.js", first, True), skill("Python", "python", "Python, SQL, Docker"),
                             skill("SQL", "sql", "Python, SQL, Docker")],
            "mobility": {"residence": {"stated": False, "countries": [], "quote": None},
                         "visa_sponsorship": {"stated": False, "offered": None, "quote": None},
                         "relocation_assistance": {"stated": False, "offered": None, "quote": None}},
            "work_locations": [], "process_dates": []}
    out = extract.extract_jd(AD, uuid.uuid4(), FakeClient(data))
    got = {r.payload["normalized_token"]: r.payload for r in out.requirements if r.payload["category"] == "skill"}
    assert set(got) == {"javascript/typescript", "react/node.js", "python", "sql"}, "React and/or Node.js is one ask"
    assert got["react/node.js"]["text_raw"] == "React and/or Node.js" and got["react/node.js"]["distinctive"]
    assert not got["javascript/typescript"]["distinctive"], "'and familiar with' keeps two asks apart"


def test_a_list_with_or_at_its_end_is_one_set_of_alternatives():
    q = "Experience with React, Vue or Angular"
    staged = [extract.StagedClaim(t, "JobRequirementClaim", {"text_raw": t, "category": "skill", "strength": "must",
                                                             "distinctive": True, "normalized_token": t.lower()},
                                  {"snippet": q, "char_start": 0, "char_end": len(q)}) for t in ("React", "Vue", "Angular")]
    assert [c.payload["normalized_token"] for c in extract.join_alternatives(staged)] == ["react/vue/angular"]


# --- employer evidence -----------------------------------------------------------------------------------------------------


ADVERT = {"url": "https://jobs.example/orbital-testworks/embedded-engineer", "title": "Embedded Engineer at Orbital Testworks",
          "text": "Orbital Testworks is hiring an Embedded Engineer in Munich.\nOur stack: InSAR processing in Python on AWS.\n"
                  "Nice to have: Rust.", "publishedDate": "2026-09-01T00:00:00.000Z", "entities": []}
OTHER = {"url": "https://jobs.example/jobs?q=engineer", "title": "Engineering jobs in Munich",
         "text": "Many companies: Satellite Testlabs uses Kubernetes.", "entities": []}


def practices_model():
    return Model(company_practices={"items": [
        {"page": 1, "label": "InSAR", "token": "insar", "kind": "method", "area": "engineering", "mention": "uses",
         "quote": "Our stack: InSAR processing in Python on AWS."},
        {"page": 1, "label": "Rust", "token": "rust", "kind": "technology", "area": "engineering", "mention": "nice_to_have",
         "quote": "Nice to have: Rust."},
        {"page": 1, "label": "Kubernetes", "token": "kubernetes", "kind": "technology", "area": "engineering", "mention": "uses",
         "quote": "We run everything on Kubernetes."},
    ]})


def found(raw):
    return exa.parse({"results": [raw]}, "q", "web").found[0]


def test_only_the_companys_own_pages_count():
    assert reader.own_page(found(ADVERT), "Orbital Testworks", None)
    assert not reader.own_page(found(OTHER), "Orbital Testworks", None), "an aggregator's other companies lend nothing"
    assert reader.own_page(found(dict(OTHER, url="https://careers.orbital.example/x")), "Orbital Testworks", "orbital.example")
    assert not reader.own_page(found(dict(ADVERT, url="https://www.linkedin.com/in/orbital-testworks-person")), "Orbital Testworks", None)


@pytest.mark.usefixtures("careers_read_at_once")
def test_an_employers_advert_makes_a_missing_core_skill_likely_never_strong(session, job, blobs):
    run, _ = go(session, job, FakeExa(people=[ADA, BEN]), blobs)
    ben = person_named(session, "Ben Testperson")
    assert pair_of(session, job, ben).triage_band == "do_not_submit", "no InSAR on his profile"
    orbital = session.scalar(select(Company).where(Company.name == "Orbital Testworks"))
    caller, model = FakeExa(web=[ADVERT, OTHER]), practices_model()
    out = practices.read_company(session, job.org_id, job.id, orbital.id, caller, model, title="InSAR Engineer")
    assert out["status"] == "read" and out["pages"] == [ADVERT["url"]]
    assert "category" not in caller.calls[0], "a web search, naming the company and the work, never a person"
    assert caller.calls[0]["query"] == "Orbital Testworks InSAR Engineer job"
    assert out["practices"] == ["insar"], "a nice-to-have and a quote not on the page are left out"
    claim = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.claim_type == "CompanyPracticeClaim"))
    assert claim.payload == {"token": "insar", "raw_label": "InSAR", "kind": "method", "area": "engineering"}
    assert claim.status == "proposed" and claim.observed_as_of == date(2026, 9, 1)
    ev = session.scalar(select(Evidence).where(Evidence.claim_id == claim.id))
    assert ev.locator["url"] == ADVERT["url"] and ev.origin == "employer"
    pair = pair_of(session, job, ben)
    assert pair.triage_band == "review_later" and ("likely_from_employer:insar" == pair.triage_reason
                                                   or "only partly met" in pair.triage_reason), "re-judged at once"
    rows = queries._gap_rows_many(session, job.org_id, job, [ben])[ben]
    insar = next(r for r in rows if r.token == "insar")
    assert insar.status == "likely" and "Orbital Testworks uses InSAR" in insar.detail and not insar.official
    assert pair.match_tier in ("possible", "unclear"), "employer evidence never makes a match strong"
    spent = session.scalars(select(CostEntry.purpose).where(CostEntry.subject_id == job.id, CostEntry.purpose == practices.PURPOSE)).all()
    assert len(spent) == 2, "the search and the reading, inside the role's sourcing budget"
    again = practices.read_company(session, job.org_id, job.id, orbital.id, caller, model)
    assert again == {"status": "fresh"} and len(caller.calls) == 1, "read once per 180 days"


def test_employer_evidence_needs_the_same_area_of_work_and_recent_time():
    practice = {"token": "react", "raw_label": "React", "kind": "technology", "area": "engineering", "company": "Tacto",
                "as_of": "2026-09-01"}
    dev = gaps.Fact("p1", gaps.PRACTICE, {**practice, "title": "Software Engineer"}, "proposed", date(2024, 7, 1), None)
    assert gaps.employer_support("react/node.js", [dev], date(2026, 10, 17)) is dev
    sales = gaps.Fact("p2", gaps.PRACTICE, {**practice, "title": "Account Executive"}, "proposed", date(2024, 7, 1), None)
    assert gaps.employer_support("react", [sales], date(2026, 10, 17)) is None, "a sales team does not use the stack"
    gone = gaps.Fact("p3", gaps.PRACTICE, {**practice, "title": "Frontend Developer"}, "proposed", date(2015, 1, 1), date(2018, 1, 1))
    assert gaps.employer_support("react", [gone], date(2026, 10, 17)) is None, "left long before the advert"
    wide = gaps.Fact("p4", gaps.PRACTICE, {**practice, "area": "company_wide", "token": "salesforce", "raw_label": "Salesforce",
                                           "title": "Account Executive"}, "proposed", date(2025, 1, 1), None)
    assert gaps.employer_support("salesforce", [wide], date(2026, 10, 17)) is wide


def test_a_likely_broad_skill_never_counts_against_anyone():
    from maindscout.domain import matching

    row = gaps.Row("r1", "TypeScript", "skill", "must", "likely", "Tacto uses TypeScript", False, [], "typescript")
    m = matching.match([{"id": "r1", "payload": {"category": "skill", "strength": "must", "text_raw": "TypeScript"}}], [row],
                       None, [], ("review_later", "no_distinctive_requirements"))
    assert m.rows[0].verdict == "ask", "a broad skill their employer uses is at least something to ask"


# --- the deeper look at a strong match -----------------------------------------------------------------------------------


ADA_GITHUB = dict(ADA, url="https://www.linkedin.com/in/ada-testperson-demo",
                  text=ADA["text"] + "\n## GitHub\n\n[GitHub Profile](https://github.com/ada-demo)\n")
GITHUB_PAGE = {"url": "https://github.com/ada-demo", "title": "ada-demo (Ada Testperson)",
               "text": "Ada Testperson\nada-demo\nRepositories: insar-timeseries (Python), mostly Java tools for build pipelines.\n"
                       "Since September 2026 at Satellite Testlabs.",
               "publishedDate": None, "entities": []}
TALK = {"url": "https://conf.example/talks/insar-at-scale", "title": "InSAR at scale",
        "text": "Speaker: Ada Testperson, InSAR Engineer at Orbital Testworks.\nShe runs InSAR time series on Kubernetes "
                "clusters every night.", "publishedDate": "2026-05-04T00:00:00.000Z", "entities": []}
NAMESAKE = {"url": "https://bakery.example/team", "title": "Our team",
            "text": "Ada Testperson bakes our sourdough every morning.", "entities": []}


def check_model():
    return Model(evidence_check={
        "pages": [{"page": 1, "about_person": True, "why": "linked from her profile"},
                  {"page": 2, "about_person": True, "why": "names her and her employer"}],
        "findings": [
            {"page": 2, "requirement": "R2", "effect": "supports", "weakens_because": None, "skill_token": "kubernetes",
             "text": "runs InSAR on Kubernetes", "quote": "She runs InSAR time series on Kubernetes clusters every night."},
            {"page": 2, "requirement": "R1", "effect": "supports", "weakens_because": None, "skill_token": "insar", "text": "invented",
             "quote": "She wrote the InSAR textbook."},
            {"page": 1, "requirement": "R2", "effect": "weakens", "weakens_because": None, "skill_token": None,
             "text": "mostly Java tooling", "quote": "mostly Java tools for build pipelines."},
            {"page": 1, "requirement": "R2", "effect": "weakens", "weakens_because": "works_elsewhere_now", "skill_token": None,
             "text": "has moved to Satellite Testlabs", "quote": "Since September 2026 at Satellite Testlabs."},
        ]})


@pytest.fixture
def strong_ada(session, job, blobs):
    hiring.add_requirement(session, job.org_id, job.id, {"category": "skill", "strength": "must", "text_raw": "Kubernetes",
                                                         "normalized_token": "kubernetes"}, "owner@desk.test")
    go(session, job, FakeExa(people=[ADA_GITHUB, BEN]), blobs)
    return person_named(session, "Ada Testperson")


def test_a_strong_match_found_on_the_web_gets_one_deeper_look_queued(session, job, blobs, strong_ada):
    assert pair_of(session, job, strong_ada).triage_band == "priority"
    queued = list(session.scalars(select(Task).where(Task.kind == evidence.KIND)))
    assert [t.payload["candidate_id"] for t in queued] == [str(strong_ada)], "Ben is not strong: no check"
    assert not evidence.due(session, job.id, strong_ada), "never two at once"
    process.retriage_candidate(session, job.org_id, strong_ada, {"act": "test"}, "test")
    assert session.scalar(select(func.count()).select_from(Task).where(Task.kind == evidence.KIND)) == 1


def test_the_deeper_look_reads_their_own_work_and_keeps_only_what_bears_on_the_role(session, job, blobs, strong_ada):
    caller = FakeExa(web=[TALK, NAMESAKE], pages={"https://github.com/ada-demo": GITHUB_PAGE})
    model = check_model()
    out = evidence.run(session, blobs, job.org_id, job.id, strong_ada, caller, model)
    search = caller.calls[-1]
    assert search["query"] == "Ada Testperson Orbital Testworks" and search["excludeDomains"] == ["linkedin.com", "exa.ai"]
    assert caller.fetched and caller.fetched[0]["urls"] == ["https://github.com/ada-demo"], "the link on her own profile"
    looked = {p["url"]: p["theirs"] for p in out["pages"]}
    assert looked == {GITHUB_PAGE["url"]: True, TALK["url"]: True, NAMESAKE["url"]: False}, "a namesake lends nothing"
    assert "bakes our sourdough" not in model.calls[0]["user"], "the model never sees a page about someone else"
    assert out["outcome"] == "mixed" and out["facts_added"] == 1 and out["rejected"] == 2, "an invented quote; other work"
    against = [f for f in out["findings"] if f["effect"] == "weakens"]
    assert [f["because"] for f in against] == ["works_elsewhere_now"], "other work (Java tools) is never evidence against"
    effects = sorted((f["effect"], f["requirement"]) for f in out["findings"])
    assert effects == [("supports", "Kubernetes"), ("weakens", "Kubernetes")]
    k8s = session.scalar(select(Claim).where(Claim.subject_id == strong_ada, Claim.claim_type == "SkillClaim",
                                             Claim.payload["normalized_skill"].astext == "kubernetes"))
    assert k8s.status == "proposed", "nothing believed until a person approves it"
    ev = session.scalar(select(Evidence).where(Evidence.claim_id == k8s.id))
    doc = session.get(Document, ev.document_id)
    assert doc.doc_type == "web_page" and ev.origin == "independent_web" and "Kubernetes clusters" in ev.snippet
    assert session.get(DocumentSubject, (doc.id, "candidate", strong_ada)) is not None
    kept = session.scalars(select(Document.id).join(DocumentSubject, DocumentSubject.document_id == Document.id).where(
        DocumentSubject.subject_id == strong_ada, Document.doc_type == "web_page")).all()
    assert len(kept) == 2, "the two pages with findings; the namesake's page is never stored"
    purposes = set(session.scalars(select(CostEntry.purpose).where(CostEntry.subject_id == job.id)))
    assert evidence.PURPOSE in purposes, "paid inside the role's sourcing budget"
    # The pages kept are public too: she is still known only from public data, a suggestion until the owner decides
    # (a first build moved checked people into the role's bands as if they had sent a CV).
    from maindscout.api import coverage, outreach

    assert coverage.discovered_only(session, strong_ada)
    assert strong_ada in outreach.undecided(session, job.org_id, job.id)
    # The card shows it; erasure takes it all.
    page = autosource.page(session, job.org_id, job.id)
    card = next(s for s in page["suggestions"] if s["candidate_id"] == str(strong_ada))
    assert card["checkable"] is True
    erasure.erase_candidate(session, blobs, job.org_id, strong_ada, "owner@desk.test", "asked to be forgotten")
    assert not session.scalar(select(func.count()).select_from(Document).where(Document.id.in_(kept)))


def test_no_page_about_them_says_so_and_stores_nothing(session, job, blobs, strong_ada):
    out = evidence.run(session, blobs, job.org_id, job.id, strong_ada, FakeExa(web=[NAMESAKE]), Model())
    assert out["outcome"] == "nothing_found" and out["findings"] == []
    assert not session.scalar(select(func.count()).select_from(Document).where(Document.doc_type == "web_page"))


def test_a_spent_budget_or_a_stop_skips_the_look(session, job, blobs, strong_ada):
    from maindscout.db.models import Candidate

    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", monthly_budget_usd=0)
    assert evidence.run(session, blobs, job.org_id, job.id, strong_ada, FakeExa(), Model())["status"] == "skipped"
    session.get(Candidate, strong_ada).do_not_contact_at = datetime.now(timezone.utc)
    assert evidence.run(session, blobs, job.org_id, job.id, strong_ada, FakeExa(), Model())["reason"] == "they asked not to be contacted"


def test_a_check_is_due_again_only_after_ninety_days(session, job, blobs, strong_ada):
    t = evidence.latest(session, job.id, strong_ada)
    t.status, t.finished_at = "done", datetime.now(timezone.utc)
    assert not evidence.due(session, job.id, strong_ada)
    t.finished_at = datetime.now(timezone.utc) - timedelta(days=91)
    assert evidence.due(session, job.id, strong_ada)


def test_check_deeper_by_hand_is_for_web_finds_only(client, session, job, blobs, strong_ada):
    ben = person_named(session, "Ben Testperson")
    r = client.post(f"/v1/jobs/{job.id}/sourcing/people/{ben}/evidence")
    assert r.status_code == 202 and r.json()["status"] == "queued"
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    assert any(s["evidence"] and s["evidence"]["status"] == "queued" for s in page["suggestions"])
    assert client.post(f"/v1/jobs/{job.id}/sourcing/people/{uuid.uuid4()}/evidence").status_code == 404


def test_same_person_needs_their_full_name_and_an_employer_or_their_own_link():
    talk = engine.Page(TALK["url"], "", TALK["text"], False)
    assert engine.same_person(talk, "Ada Testperson", ["Orbital Testworks"])
    assert not engine.same_person(engine.Page("u", "", NAMESAKE["text"], False), "Ada Testperson", ["Orbital Testworks"])
    assert not engine.same_person(engine.Page("u", "", "Ada works at Orbital Testworks", False), "Ada Testperson", ["Orbital Testworks"])
    assert engine.same_person(engine.Page("u", "", "nothing", True), "Ada Testperson", []), "linked from their own profile"
    assert engine.names_them("Lilly Kämmerling (Tacto)", "Lilly Kämmerling") and engine.names_them("JAN P. BRUNCKHORST", "Jan Brunckhorst")
    assert engine.profile_links(ADA_GITHUB["text"]) == ["https://github.com/ada-demo"]


def test_what_the_first_real_checks_got_wrong_is_refused_by_code():
    """2026-10-17, the first real checks: Exa's copy of the profile came back as a page, "no mention of X" was called
    evidence against, and Exa's blurb about the employer was quoted as the person's work."""
    copy = engine.Page("https://exa.ai/library/person/n3677gx2n95", "", "Ada Testperson, InSAR Engineer at Orbital Testworks", False)
    assert not engine.same_person(copy, "Ada Testperson", ["Orbital Testworks"]), "a copy of the profile the desk already has"
    talk = engine.Page(TALK["url"], "", TALK["text"] + "\nOrbital Testworks has 50-60 employees (+10% YoY), founded in 2019.", False)
    model = Model(evidence_check={"pages": [{"page": 1, "about_person": True, "why": "her talk"}], "findings": [
        {"page": 1, "requirement": "R1", "effect": "weakens", "weakens_because": "says_otherwise", "skill_token": None,
         "text": "no mention of Kubernetes",
         "quote": "She runs InSAR time series on Kubernetes clusters every night."},
        {"page": 1, "requirement": "R2", "effect": "supports", "skill_token": None, "text": "works in satellites",
         "quote": "Orbital Testworks has 50-60 employees (+10% YoY), founded in 2019."},
        {"page": 1, "requirement": "R1", "effect": "supports", "skill_token": "kubernetes", "text": "runs it every night",
         "quote": "She runs InSAR time series on Kubernetes clusters every night."}]})
    reqs = [{"id": "k8s", "text": "Kubernetes", "strength": "must", "category": "skill", "token": "kubernetes"},
            {"id": "geo", "text": "satellite industry", "strength": "strong_plus", "category": "domain", "token": None}]
    reading = engine.read([talk], "Ada Testperson, InSAR Engineer at Orbital Testworks", reqs, model)
    assert [(f.effect, f.requirement_id) for f in reading.findings] == [("supports", "k8s")]
    assert sorted(r["reason"] for r in reading.rejected) == ["something not mentioned is not evidence against them",
                                                            "the quote describes a company, not their work"]


def test_only_what_a_public_page_can_show_is_checked(session, job, blobs, strong_ada):
    hiring.add_requirement(session, job.org_id, job.id, {"category": "employment", "strength": "must", "text_raw": "permanent role",
                                                         "employment": "permanent"}, "owner@desk.test")
    asked = [r["text"] for r in evidence._requirements(session, job)]
    assert "Kubernetes" in asked and "InSAR processing experience" in asked
    assert "permanent role" not in asked, "employment, places, level and years are the rules' and the call's"
