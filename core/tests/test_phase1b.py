"""Phase 1b (docs/next/PLAN.md section 4b): companies found by their keys, profiled from Exa without people's names,
checked against research; people found by Exa get their employers and a career reading; the search is a strategy
(talent DNA, tiers, batches, exhaustion, snowball, widening). Exa is a fake: synthetic companies and people."""

import copy
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from maindscout.api import autosource, companies, company_profiles, research, strategy
from maindscout.api.process import _ensure_pair
from maindscout.db.models import PUBLIC_ORG_ID, Candidate, CandidateJob, Claim, Company, Decision, SourcingQuery, Task
from maindscout.intelligence import exa
from maindscout.intelligence import research as engine
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import ADA, FakeExa, blobs, job, person_named, profile  # noqa: F401 (fixtures)

ORG_URL = "https://exa.ai/library/organization/"


def page(exa_key, name, homepage, *, industry="Software Development", employees=120, hq="Munich, Bavaria, Germany",
         founded=2018, countries="Germany: 70 (60%), Canada: 20 (20%)", rounds=("Series a (2024-03-01): USD 20.0M",),
         talent="Via (2)", categories="earth observation, remote sensing, satellite data", linkedin=None):
    """A synthetic Exa company page in Exa's layout, with executives and emails that must never be kept."""
    linkedin = linkedin or name.lower().replace(" ", "-")
    text = "\n".join([
        f"# {name}", "", f"{name} is a {industry} company. {name} employs {employees} people (+5% YoY), founded in {founded}. "
        f"Headquartered in {hq}.", "", "## Company Details", f"- Industry: {industry}", "- Type: Privately held",
        f"- Headquarters: {hq}", f"- Founded Year: {founded}", f"- Homepage: {homepage}", f"- Aliases: {name} GmbH",
        f"- LinkedIn: linkedin.com/company/{linkedin}", f"- Emails: hello@{homepage}", "", "## Financials",
        *[f"  - {r}" for r in rounds], "", "## Workforce", f"- Employees: {employees}", "- Key Executives:",
        "  - Jane Example: Chief Executive Officer", "  - John Example: CTO", "- Breakdown:", f"  - By Country: {countries}",
        "  - By Department: Technical: 50 (42%), Sales: 10 (8%)", f"- Talent Sources: {talent}", "", "## Reviews & Ratings",
        "- Employer Rating: 4.0/5.0", "", "## Categories", "", categories])
    return {"url": f"https://linkedin.com/company/{linkedin}", "title": name, "text": text,
            "entities": [{"id": ORG_URL + exa_key, "type": "company", "properties": {"name": name, "foundedYear": founded,
                                                                                     "workforce": {"total": employees}}}]}


def with_ids(person, ids):
    """A synthetic person whose work history carries Exa company ids."""
    out = copy.deepcopy(person)
    for job_ in out["entities"][0]["properties"]["workHistory"]:
        job_["company"]["id"] = ids.get(job_["company"]["name"])
    return out


# --- K1: identity keys ---------------------------------------------------------------------------------------------------


def test_a_company_is_found_by_its_keys_before_its_name(session, job):
    a, _ = companies.resolve(session, "Procure Testai", "test", keys={"exa_id": ORG_URL + "pta", "domain": "https://www.procure-test.example/en"})
    assert (a.exa_id, a.domain) == (ORG_URL + "pta", "procure-test.example")
    b, _ = companies.resolve(session, "ProcureTestai Ltd", "test", keys={"domain": "procure-test.example"})
    assert b.id == a.id, "another name with the same website is the same company"
    assert companies.resolve(session, "ProcureTestai", "test")[0].id == a.id, "and that name is now its alias"
    c, _ = companies.resolve(session, "Procure Testai", "test", keys={"exa_id": ORG_URL + "other"})
    assert c.id != a.id and companies.by_key(session, exa_id=ORG_URL + "other").id == c.id, "same name, another company"
    d, _ = companies.resolve(session, "Unrelated Testco", "test")
    clash = companies.learn_keys(session, d, domain="procure-test.example", org_id=job.org_id)
    assert clash.id == a.id and d.domain is None, "a key held by another company is never moved"
    card = session.scalar(select(Decision).where(Decision.type == "company_same", Decision.subject_id == d.id))
    assert card is not None and card.context["existing"]["id"] == str(a.id) and "share" in card.context["why"]
    assert companies.domain_of("https://www.linkedin.com/company/x") is None, "a profile site is not a company's website"


# --- K2, K3: a profile without people, checked against research ---------------------------------------------------------


def test_a_profile_is_read_without_people_and_checked_against_research(session):
    company, _ = companies.resolve(session, "Orbital Testworks", "test", keys={"domain": "orbital.example"})
    now = datetime.now(timezone.utc)
    research.write_facts(session, company, [
        engine.Fact("founded", "2016-04-20", "https://find-and-update.company-information.service.gov.uk/company/1",
                    "Incorporated on 20 April 2016", registry=True),
        engine.Fact("hq", "Munich, Germany", "https://orbital.example/imprint", "Orbital Testworks GmbH, Munich, Germany"),
        engine.Fact("funding_round", {"stage": "series_a", "date": "2024-03-12", "amount": "$20M", "investors": []},
                    "https://dealroom.co/companies/orbital", "raised a $20M Series A in March 2024"),
    ], now)
    found = exa.parse({"results": [page("orb", "Orbital Testworks", "orbital.example")]}, "", "contents").found[0]
    company_profiles.apply(session, company, found)

    assert (company.exa_id, company.linkedin) == (ORG_URL + "orb", "orbital-testworks")
    kept = json.dumps(company.exa_profile)
    assert "Example" not in kept and "hello@" not in kept and "Employer Rating" not in kept, "never executives, emails or reviews"
    assert company.exa_profile["countries"][0] == {"country": "Germany", "n": 70, "pct": 60}
    assert companies.resolve(session, "Orbital Testworks GmbH", "test")[0].id == company.id, "the profile's other names"

    claims = {c.claim_type: c for c in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id))}
    assert claims["CompanyFoundedClaim"].flags.get("sources_disagree"), "the registry says 2016, Exa 2018: a person sees both"
    assert not claims["FundingRoundClaim"].flags.get("single_source_web"), "two sources agree on the round: no longer single-source"
    assert not claims["CompanyLocationClaim"].flags.get("sources_disagree")
    assert claims["CompanyTypeClaim"].payload == {"type": "product"}
    assert company_profiles.summary(company)["employees"] == 120


def test_an_agreement_to_be_acquired_is_not_an_acquisition():
    fact = engine.Fact("status", "acquired", "https://catalyst.example/news",
                       "Catalyst Testworks today shared that it has entered into a definitive agreement to be acquired by Intermap")
    assert research._payload(fact, date.today()) == ("CompanyStatusClaim", {"status": "active", "date": None,
                                                                             "detail": "agreed to be acquired, not completed"})
    done = engine.Fact("status", "acquired", "https://x.example", "In 2024 the company was acquired by a larger rival.")
    assert research._payload(done, date.today())[1]["status"] == "acquired"


# --- K4: people found by Exa get their employers and a career reading ----------------------------------------------------


def test_people_found_on_the_web_get_their_employers_profiled_and_a_career_reading(session, job, blobs, monkeypatch):
    monkeypatch.setenv("PROFILE_AUTO", "true")
    ids = {"Orbital Testworks": ORG_URL + "orb", "Example University": ORG_URL + "uni"}
    fake_exa = FakeExa(people=[with_ids(ADA, ids)], pages={ORG_URL + "orb": page("orb", "Orbital Testworks", "orbital.example")})
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", open_tiers=["A", "B", "market"])
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    ada = person_named(session, "Ada Testperson")

    assert len(fake_exa.fetched) == 1 and set(fake_exa.fetched[0]["urls"]) == set(ids.values()), "one fetch for all employers"
    orbital = companies.by_key(session, exa_id=ORG_URL + "orb")
    assert orbital is not None and orbital.exa_profile["employees"] == 120
    step = session.scalar(select(Claim).where(Claim.subject_id == ada, Claim.claim_type == "CareerStepClaim",
                                              Claim.valid_to.is_(None)))
    assert step.payload["company"]["company_id"] == str(orbital.id), "the career step links to the exact company"
    assert session.scalar(select(Task.id).where(Task.kind == "profile_candidate", Task.payload["candidate_id"].astext == str(ada)))
    assert row.report["profiles"]["companies"] >= 1
    suggestion = next(s for s in autosource.page(session, job.org_id, job.id)["suggestions"] if s["candidate_id"] == str(ada))
    assert suggestion["employer"]["employees"] == 120 and suggestion["employer"]["kind"] == "product"


# --- S7: the strategy ------------------------------------------------------------------------------------------------------


def _client_person(slug, history):
    """Someone at the hiring company (never stored: they work at the client)."""
    return {"url": f"https://www.linkedin.com/in/{slug}", "title": slug, "text": "# x",
            "entities": [{"id": slug, "type": "person", "properties": {"name": slug, "workHistory": history}}]}


def _job(title, company, cid, start, end=None):
    return {"title": title, "company": {"id": cid, "name": company}, "dates": {"from": start, "to": end}, "location": None}


def test_the_strategy_reads_the_talent_dna_and_builds_tiers(session, job):
    hiring = session.get(Company, job.hiring_company_id)
    hiring.domain = "catalyst.example"
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", role_variants=["InSAR engineer", "SAR engineer"],
                           countries=[])
    cat, orb, club = ORG_URL + "cat", ORG_URL + "orb", ORG_URL + "club"
    p1 = _client_person("client-one-demo", [_job("InSAR Engineer", "Catalyst Geo", cat, "2023-01"),
                                            _job("Radar Engineer", "Orbital Testworks", orb, "2019-01", "2022-12"),
                                            _job("Member", "Testcity Hackathon Club", club, "2017-01", "2018-01")])
    p2 = _client_person("client-two-demo", [_job("InSAR Engineer", "Catalyst Geo", cat, "2022-05"),
                                            _job("SAR Analyst", "Orbital Testworks", orb, "2018-01", "2022-04")])
    stranger = _client_person("stranger-demo", [_job("InSAR Engineer", "Elsewhere Testco", ORG_URL + "else", "2020-01")])
    fake_exa = FakeExa(
        by_query={"Catalyst Geo (catalyst.example)": [page("cat", "Catalyst Geo", "catalyst.example", employees=300,
                                                           countries="Germany: 180 (60%), Canada: 60 (20%), France: 9 (3%)")],
                  "InSAR engineer at Catalyst Geo": [p1, p2, stranger], "SAR engineer at Catalyst Geo": [p1]},
        pages={orb: page("orb", "Orbital Testworks", "orbital.example")},
        companies=[page("rad", "Radar Testworks", "radar.example", employees=40), page("cat", "Catalyst Geo", "catalyst.example"),
                   page("tiny", "Tiny Lookalike", "tiny.example", employees=3)])
    out = strategy.build(session, job.org_id, job.id, fake_exa, "owner@desk.test")
    p = autosource.current_plan(session, job.id)

    assert p.dna["people"] == 2, "only people whose history shows the hiring company by its exact id"
    assert p.dna["titles"][0] == ["InSAR Engineer", 2]
    assert [f["name"] for f in p.dna["feeders"]] == ["Orbital Testworks"], "a hackathon club is not where people came from"
    tiers = {t["name"]: (t["tier"], t["group"]) for t in p.targets}
    assert tiers["Orbital Testworks"] == ("feeder", "A") and tiers["Radar Testworks"] == ("peer", "B")
    assert "Catalyst Geo" not in tiers, "the hiring company is never a target"
    assert p.countries == ["DE", "CA"], "where its team works, not where it is registered"
    assert out["targets"]["A"] >= 1 and out["targets"]["B"] >= 1
    assert session.scalar(select(func.count()).select_from(Candidate).where(Candidate.org_id == job.org_id)) == 0, \
        "nobody at the client is ever stored"
    assert all(c["query"].endswith("at Catalyst Geo") for c in fake_exa.calls if c["category"] == "people")
    peer_searches = [c["query"] for c in fake_exa.calls if c["category"] == "company"][1:]
    assert peer_searches == ["earth observation companies in Germany and Canada", "earth observation startups, Series A to C",
                             "insar companies in Germany and Canada"], "who else does the role's specialist work, too"
    assert "Tiny Lookalike" not in tiers, "micro companies are left out"


def test_companies_are_searched_in_batches_until_exhausted_then_widening_is_proposed(session, job, blobs):
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", role_variants=["InSAR engineer"], target=5)
    names = [f"Batch Testco {i}" for i in range(7)]
    for name in names:
        autosource.add_target(session, job.org_id, job.id, name, "owner@desk.test")
    p = autosource.current_plan(session, job.id)
    first = strategy.next_searches(session, job, p, set(), {})
    assert len({q["company_id"] for q in first}) == 5, "a batch of five companies"
    assert strategy.widening(session, job.org_id, job, p) is None, "nothing is exhausted yet"

    now = datetime.now(timezone.utc)
    for t in p.targets:
        session.add(SourcingQuery(org_id=job.org_id, job_id=job.id, key=f"k-{t['company_id']}", channel="exa_people",
                                  text=f"InSAR engineer at {t['name']}", target=t["name"], tier=t["tier"], runs=1, results=10,
                                  new=1, known=9, relevant=0, cost_usd=0.007, last_run_at=now, company_id=uuid.UUID(t["company_id"])))
    session.flush()
    state = strategy.company_state(session, job.id, p)
    assert all(state[t["company_id"]]["exhausted"] for t in p.targets), "nine of ten already known: exhausted"
    assert strategy.next_searches(session, job, p, set(), {}) == [], "an exhausted company waits 90 days"
    proposal = strategy.widening(session, job.org_id, job, p)
    assert proposal and "exhausted" in proposal["why"]
    assert {o["option"] for o in proposal["options"]} >= {"open_tier", "market"}

    p = strategy.widen(session, job.org_id, job.id, "owner@desk.test", "market")
    assert "market" in p.open_tiers
    assert [q["tier"] for q in strategy.next_searches(session, job, p, set(), {})] == ["market"], "the owner chose the last step"
    with pytest.raises(autosource.SourcingEngineError):
        autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", open_tiers=["B"])


def test_the_list_grows_from_where_strong_people_worked_before(session, job, blobs):
    from maindscout.api import discovery

    autosource.plan(session, job.org_id, job.id)
    people = [profile(f"snow-{i}-demo", f"Snow{i} Testperson", "InSAR Engineer", "Munich, Bavaria, Germany", "DE",
                      [("InSAR Engineer", f"Current Testco {i}", "Jan 2023", "Present", "2023-01-01", None),
                       ("InSAR Engineer", "Feeder Testworks", "Jan 2019", "Dec 2022", "2019-01-01", "2022-12-01")],
                      skills=["insar"]) for i in range(2)]
    for raw in people:
        found = exa.parse({"results": [raw]}, "q", "people").found[0]
        cid, _ = discovery.add(session, blobs, job.org_id, found, ["insar"])
        pair = _ensure_pair(session, job.org_id, cid, job)
        pair.triage_band = "priority"
    session.flush()
    report = {}
    strategy.snowball(session, job.org_id, job, FakeExa(), report)
    p = autosource.current_plan(session, job.id)
    added = next(t for t in p.targets if t["name"] == "Feeder Testworks")
    assert (added["tier"], added["group"]) == ("snowball", "B") and "2 strong" in added["why"][0]
    assert report["snowball"] == ["Feeder Testworks"]


def test_strategy_and_widen_routes(client, session, job):
    r = client.post(f"/v1/jobs/{job.id}/sourcing/strategy")
    assert r.status_code == 202 and session.get(Task, uuid.UUID(r.json()["task_id"])).kind == "sourcing_strategy"
    page_ = client.post(f"/v1/jobs/{job.id}/sourcing/widen", json={"option": "market"}).json()
    assert "market" in page_["plan"]["open_tiers"]
    bad = client.post(f"/v1/jobs/{job.id}/sourcing/widen", json={"option": "everything"})
    assert bad.status_code == 422


# --- domains and searches aimed at a company (owner, 2026-10-13) --------------------------------------------------------


class Reader:
    """A model that reads domains the way the prompt asks (and once tries to sneak in a technology word)."""

    model = "fake-domains"

    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema, name):
        from maindscout.intelligence.llm import LLMResult

        self.calls += 1
        keys = [line.split("key: ", 1)[1] for line in user.split("\n") if line.startswith("### key: ")]
        return LLMResult({"companies": [{"key": k, "offering": "satellite radar analytics", "offering_quote": "earth observation",
                                         "domains": [{"domain": "AI", "quote": "earth observation"},
                                                     {"domain": "earth observation", "quote": "earth observation"},
                                                     {"domain": "insurance", "quote": "a quote that is not in the text"}]}
                                        for k in keys]}, self.model, 10, 5, 0.0004)


def test_a_company_domain_is_its_market_read_with_a_quote_never_a_technology(session):
    company, _ = companies.resolve(session, "Orbital Testworks", "test", keys={"domain": "orbital.example"})
    found = exa.parse({"results": [page("orb", "Orbital Testworks", "orbital.example", industry="Software Development")]}, "",
                      "contents").found[0]
    company_profiles.apply(session, company, found)
    assert company.exa_profile["about"].startswith("Orbital Testworks is a Software Development company"), "its own description"
    reader = Reader()
    assert company_profiles.read_domains(session, [company], None, reader=reader) == 1
    assert company.exa_profile["domains"] == ["earth observation"], "a technology word and an unquoted market are dropped"
    assert company.exa_profile["offering"] == "satellite radar analytics"
    claim = session.scalar(select(Claim).where(Claim.subject_id == company.id, Claim.claim_type == "CompanyDomainClaim",
                                               Claim.status == "proposed"))
    assert claim.payload == {"domains": ["earth observation"]}
    assert company_profiles.read_domains(session, [company], None, reader=reader) == 0 and reader.calls == 1, "read once"
    assert company_profiles.summary(company)["domains"] == ["earth observation"]
    assert strategy.peer_queries(company)[0] == "satellite radar analytics companies in Germany and Canada"


def test_without_a_model_the_domain_falls_back_to_non_technology_tags(session):
    company, _ = companies.resolve(session, "Radar Testworks", "test", keys={"domain": "radar.example"})
    found = exa.parse({"results": [page("rad", "Radar Testworks", "radar.example",
                                        categories="ai, artificial intelligence (ai), automation, insurance claims, b2b")]}, "",
                      "contents").found[0]
    company_profiles.apply(session, company, found)
    company_profiles.read_domains(session, [company], None)  # the test guard refuses the model
    assert company.exa_profile["domains"] == ["insurance claims"]
    assert "domain_reader" not in company.exa_profile, "tried again when a model is available"


def test_a_search_aimed_at_a_company_keeps_only_its_people(session, job, blobs):
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", role_variants=["InSAR engineer"])
    autosource.add_target(session, job.org_id, job.id, "Orbital Testworks", "owner@desk.test")
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", FakeExa())  # Ada and Ben work there; Cara, Dev do not
    entry = row.report["web"]["queries"][0]
    assert entry["text"] == "InSAR engineer at Orbital Testworks" and entry["off_target"] == 2
    assert person_named(session, "Dev Testperson") is None, "a look-alike from a search aimed at a company is never stored"
    ada = next(s for s in autosource.page(session, job.org_id, job.id)["suggestions"] if s["name"] == "Ada Testperson")
    assert ada["found_by"]["at_target"] == "now" and ada["found_by"]["target"] == "Orbital Testworks"


def test_the_plan_follows_the_hiring_profile_and_suggests_only_the_roles_countries(session, job, blobs, monkeypatch):
    from maindscout.api import coverage, search

    named, _ = companies.resolve(session, "Named Testworks", "test")
    monkeypatch.setattr(coverage, "ad_countries", lambda session, job: {"DE"})
    monkeypatch.setattr(search, "job_filters", lambda session, job: (search.Filters(), [str(named.id)]))
    p = strategy.sync(session, job.org_id, job)
    assert "DE" in p.countries, "the hiring profile's 'must live in' countries are the role's countries"
    p = autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", countries=["DE"])
    assert p.targets[0]["name"] == "Named Testworks" and (strategy.group_of(p.targets[0]), p.targets[0]["pinned"]) == ("A", True)
    assert strategy.sync(session, job.org_id, job).version == p.version, "no new version when nothing changed"
    widened = autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", countries=["DE", "AT"])
    assert strategy.sync(session, job.org_id, job).countries == ["DE", "AT"], "a country the owner added is never taken away"
    p = autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", countries=["DE"])

    ion = profile("ion-testperson-demo", "Ion Testperson", "InSAR Engineer", "Bucharest, Bucharest, Romania", "RO",
                  [("InSAR Engineer", "Danube Testworks", "Jan 2021", "Present", "2021-01-01", None)], skills=["insar"])
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", open_tiers=["A", "B", "market"])
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", FakeExa(people=[ADA, ion]))
    assert row.report["refused"].get("outside_countries") == 1, "Romania is in the desk's coverage, but not this role's"
    names = {s["name"] for s in autosource.page(session, job.org_id, job.id)["suggestions"]}
    assert "Ada Testperson" in names and "Ion Testperson" not in names


def test_a_company_with_no_team_in_the_roles_countries_or_shut_down_is_not_searched(session, job):
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", role_variants=["InSAR engineer"], countries=["CA"])
    uk, canada, gone = (autosource.add_target(session, job.org_id, job.id, n, "owner@desk.test") and
                        companies.resolve(session, n, "test")[0] for n in ("Uk Testworks", "Maple Testworks", "Gone Testworks"))
    for c, where in ((uk, "United Kingdom: 40 (95%)"), (canada, "Canada: 30 (60%), United Kingdom: 20 (40%)")):
        found = exa.parse({"results": [page(c.name.split()[0].lower(), c.name, f"{c.name.split()[0].lower()}.example",
                                            countries=where)]}, "", "contents").found[0]
        company_profiles.apply(session, c, found)
    research.write_facts(session, gone, [engine.Fact("status", "shut_down", "https://gone.example/news",
                                                     "Gone Testworks has shut down its operations.")], datetime.now(timezone.utc))
    p = autosource.current_plan(session, job.id)
    for t in p.targets:
        autosource.set_target(session, job.org_id, job.id, t["company_id"], "owner@desk.test", pinned=False)
    p = autosource.current_plan(session, job.id)
    searched = {q["target"] for q in strategy.next_searches(session, job, p, set(), {})}
    assert searched == {"Maple Testworks"}, "a UK-only team gives a Canadian role nobody; a closed company nobody at all"
    assert strategy.fit(session, uk, {"CA"})["why"].startswith("no team in the role's countries")
    assert strategy.fit(session, gone, {"CA"}) == {"searched": False, "why": "shut down"}


def test_peer_searches_also_ask_who_else_does_the_roles_specialist_work(session):
    company, _ = companies.resolve(session, "Maple Radar Testworks", "test", keys={"domain": "maple-radar.example"})
    found = exa.parse({"results": [page("mrt", "Maple Radar Testworks", "maple-radar.example")]}, "", "contents").found[0]
    company_profiles.apply(session, company, found)
    company.exa_profile = {**company.exa_profile, "domains": ["earth observation"], "offering": "earth observation solutions"}
    assert strategy.peer_queries(company, ["CA"], ["insar"]) == [
        "earth observation solutions companies in Canada", "earth observation startups, Series A to C", "insar companies in Canada"]
