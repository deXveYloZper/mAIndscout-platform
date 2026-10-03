"""I2: targeted company research, checked and stored as public facts with sources."""

import uuid

import pytest
from sqlalchemy import func, select

from maindscout.api import research
from maindscout.db.models import PUBLIC_ORG_ID, Claim, Company, CostEntry, Evidence, Task
from maindscout.intelligence import research as engine
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)

REGISTRY = "https://find-and-update.company-information.service.gov.uk/company/12564716"
PRESS = "https://siliconangle.com/2025/11/27/procure-ai-lands-13m-funding/"
OWN = "https://www.procure.ai/"


def answer(**over):
    data = {
        "identified": True, "website": OWN,
        "domains": {"value": ["procurement", "AI"], "source_url": OWN, "quote": "AI-native Procurement Automation Platform", "as_of": None},
        "company_type": {"value": "product", "source_url": OWN, "quote": "our platform", "as_of": None},
        "founded": {"value": "2020-04-20", "source_url": REGISTRY, "quote": "Incorporated on 20 April 2020", "as_of": None},
        "funding_rounds": [{"stage": "seed", "date": "2025-11-26", "amount": "$13M", "investors": ["Headline"],
                            "source_url": PRESS, "quote": "it has raised $13 million in an investment round led by Headline"}],
        "headcount": {"value": "51-200 employees", "source_url": "https://uk.linkedin.com/company/procureai",
                      "quote": "Company size 51-200 employees", "as_of": "2026-10-02"},
        "status": {"value": "active", "source_url": REGISTRY, "quote": "Company status Active", "as_of": None},
        "hq": {"value": "London, United Kingdom", "source_url": OWN, "quote": "London, United Kingdom", "as_of": None},
    }
    data.update(over)
    return data


VISITED = [REGISTRY, PRESS, OWN, "https://uk.linkedin.com/company/procureai/"]


class FakeSearch:
    model = "fake-search"

    def __init__(self, data=None, visited=VISITED, usd=0.08):
        self.data, self.visited, self.usd, self.calls = data or answer(), visited, usd, 0

    def search_json(self, system, user, schema, name):
        self.calls += 1
        assert "Engineer" not in user and "Jane" not in user, "research must never include a person"
        return self.data, self.visited, {"model": self.model, "input_tokens": 1000, "output_tokens": 100, "sources": 4, "usd": self.usd}


# --- the mechanical checks ------------------------------------------------------------------------


def test_a_fact_whose_page_was_never_opened_is_dropped():
    facts, rejected = engine.check(answer(), [OWN])
    assert "founded" not in {f.kind for f in facts} and any("not opened" in r["reason"] for r in rejected)


def test_a_funding_amount_must_match_its_quote():
    data = answer(funding_rounds=[{"stage": "series_b", "date": "2021-03", "amount": "$170M", "investors": [],
                                   "source_url": OWN, "quote": "Bitpanda raised a total of $160 million in March 2021"}])
    facts, rejected = engine.check(data, VISITED)
    assert not [f for f in facts if f.kind == "funding_round"]
    assert any("amount" in r["reason"] for r in rejected)


def test_a_funding_year_may_come_from_the_articles_address():
    facts, _ = engine.check(answer(), VISITED)
    assert [f for f in facts if f.kind == "funding_round"], "year 2025 is in the URL /2025/11/27/"


def test_a_founding_year_not_in_its_quote_is_dropped_and_registries_are_recognised():
    data = answer(founded={"value": "2019", "source_url": REGISTRY, "quote": "Incorporated on 20 April 2020", "as_of": None})
    facts, _ = engine.check(data, VISITED)
    assert "founded" not in {f.kind for f in facts}
    assert next(f for f in facts if f.kind == "status").registry is True


@pytest.mark.parametrize("kind,value,quote,ok", [
    ("status", "active", "Company status Active", True),
    ("status", "active", "IT Services and IT Consulting", False),  # says nothing about status
    ("status", "shut_down", "Defunct 1 June 2025", True),
    ("company_type", "product", "Type Privately Held", False),  # legal form, not what it sells
    ("company_type", "other", "Company type   Private limited Company", False),
    ("company_type", "product", "Developer of a market research platform", True),
    ("funding_round", {"stage": "other", "date": "2019-09-03", "amount": "$5.26M"}, "Seed Round / 03-Sep-2019 / $5.26M", False),
    ("funding_round", {"stage": "seed", "date": "2019-09-03", "amount": "$5.26M"}, "Seed Round / 03-Sep-2019 / $5.26M", True),
    ("funding_round", {"stage": "other", "date": None, "amount": None}, "Attest has raised $85.5M", False),  # a total
    ("funding_round", {"stage": "series_a", "date": "2019-03-15", "amount": None}, "Early Stage VC (Series A) 15-Mar-2019", True),
    ("funding_round", {"stage": "seed", "date": "2016", "amount": None}, "pre-seed round in 2016", False),
])
def test_quotes_must_support_status_kind_and_stage(kind, value, quote, ok):
    assert (engine.fact_problem(kind, value, quote) is None) is ok


def test_the_prompt_never_asks_for_people_or_technologies():
    assert "Do not research any person" in engine.SYSTEM and "Do not research technologies" in engine.SYSTEM


def test_recheck_rejects_stored_facts_that_fail_newer_checks(session, company):
    data = answer(status={"value": "active", "source_url": OWN, "quote": "IT Services and IT Consulting", "as_of": None})
    outcome = engine.ResearchOutcome(True, OWN, [engine.Fact("status", "active", OWN, "IT Services and IT Consulting")]
                                     + engine.check(data, VISITED)[0], [], VISITED, {"usd": 0})
    research.apply(session, company, outcome)
    dropped = research.recheck(session)
    assert [d["claim_type"] for d in dropped] == ["CompanyStatusClaim"], "the other facts still pass"
    status = session.scalars(select(Claim).where(Claim.subject_id == company.id, Claim.claim_type == "CompanyStatusClaim")).one()
    assert status.status == "rejected" and "does not say" in status.rejection_reason["note"]


def test_an_unidentified_company_writes_nothing():
    out = engine.research_company("Acme", "", FakeSearch(answer(identified=False)))
    assert not out.identified and out.facts == []


def test_amount_and_size_parsing():
    assert research._usd("$13M") == 13e6 and research._usd("$1.2 billion") == 1.2e9 and research._usd("EUR 5M") is None
    assert research._team("51-200 employees") == (51, 200) and research._team("more than 800 people") == (800, None)


# --- storing and scheduling -------------------------------------------------------------------------


@pytest.fixture
def company(session):
    c = Company(name="Procure Ai", normalized=f"procure ai {uuid.uuid4().hex[:6]}")
    session.add(c)
    session.flush()
    return c


def test_research_stores_public_facts_with_sources_and_cost(session, company):
    result = research.run(session, company.id, "AI procurement start-up", FakeSearch())
    assert result["facts_written"] == 7
    claims = list(session.scalars(select(Claim).where(Claim.subject_id == company.id)))
    assert {c.org_id for c in claims} == {PUBLIC_ORG_ID} and {c.status for c in claims} == {"proposed"}
    founded = next(c for c in claims if c.claim_type == "CompanyFoundedClaim")
    ev = session.scalars(select(Evidence).where(Evidence.claim_id == founded.id)).one()
    assert ev.source_authority == "verified_primary" and ev.locator["url"] == REGISTRY and "2020" in ev.snippet
    funding = next(c for c in claims if c.claim_type == "FundingRoundClaim")
    assert funding.payload["amount_usd"] == 13e6 and funding.flags == {"single_source_web": True}
    own = next(c for c in claims if c.claim_type == "CompanyTypeClaim")
    assert session.scalars(select(Evidence).where(Evidence.claim_id == own.id)).one().origin == "employer"
    assert company.research_status == "identified" and company.website == OWN
    cost = session.scalar(select(CostEntry).where(CostEntry.purpose == "research_company"))
    assert cost.org_id is None and float(cost.usd) == pytest.approx(0.08)


def test_fresh_facts_are_not_researched_again_and_repeats_add_observations(session, company):
    search = FakeSearch()
    research.run(session, company.id, "", search)
    assert research.run(session, company.id, "", search)["skipped"] == "fresh" and search.calls == 1
    research.run(session, company.id, "", search, force=True)
    assert search.calls == 2
    assert session.scalar(select(func.count()).select_from(Claim).where(Claim.subject_id == company.id)) == 7, "same facts, no duplicates"


def test_shared_research_has_its_own_budget(session, company, monkeypatch):
    monkeypatch.setenv("RESEARCH_MONTHLY_BUDGET_USD", "0")
    from maindscout.api.costs import BudgetExceeded
    with pytest.raises(BudgetExceeded):
        research.run(session, company.id, "", FakeSearch())


def test_reading_a_cv_queues_research_for_companies_that_matter_without_naming_the_person(client, fake, session):
    job = make_job(client)
    drop_cv(client, job)
    queued = list(session.scalars(select(Task).where(Task.kind == "research_company")))
    contexts = " ".join(t.payload.get("context", "") for t in queued)
    names = {session.get(Company, uuid.UUID(t.payload["company_id"])).name for t in queued}
    # current job, a 7-month contract (Jun-Dec 2020 inclusive), a 3-year job in the last decade, and the hiring company
    assert names == {"Acme Space", "Gamma Labs", "Beta Web", "Catalyst Geo"}, names
    assert "Jane" not in contexts and "Engineer" not in contexts
    assert all(t.org_id is None for t in queued) and len({t.dedupe_key for t in queued}) == len(queued)


def test_research_can_be_turned_off(client, fake, session, monkeypatch):
    monkeypatch.setenv("RESEARCH_AUTO", "false")
    job = make_job(client)
    drop_cv(client, job)
    assert not session.scalars(select(Task).where(Task.kind == "research_company")).all()


def test_the_company_page_shows_facts_with_sources(client, fake, session):
    make_job(client)
    cid = client.get("/v1/companies", params={"q": "catalyst geo"}).json()[0]["id"]
    research.run(session, uuid.UUID(cid), "", FakeSearch())
    page = client.get(f"/v1/companies/{cid}").json()
    assert page["research_status"] == "identified"
    founded = next(f for f in page["facts"] if f["claim_type"] == "CompanyFoundedClaim")
    assert founded["payload"]["founded"] == "2020-04-20" and founded["sources"][0]["url"] == REGISTRY
    assert client.post(f"/v1/companies/{cid}/research").status_code == 202
